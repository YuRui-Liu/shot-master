"""POST /script/outline — SSE：读 创意.json.selected → LLM JSON → 落盘 剧本.json。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.downstream import purge_downstream
from screenwriter_agent.core.json_repair import repair_json_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import idea_read_path, script_index_path
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import ScriptOutlineReq
from screenwriter_agent.models.script_index_schema import ScriptIndex

router = APIRouter()


def build_outline_prompt(tpl_text: str, sel: dict, episode_count: int,
                         opts: dict) -> str:
    """组装剧本大纲 user prompt：模板 + 选定候选 + 参数 + （非空时）题材规则。

    ②c 题材驱动：opts['genre_context'] 非空时追加 '## 题材规则'；空则同现状。"""
    prompt = (tpl_text
              + "\n\n## 选定候选\n```json\n"
              + json.dumps(sel, ensure_ascii=False, indent=2)
              + "\n```\n\n## 参数\n"
              + f"episode_count={episode_count}\n"
              + f"duration_sec={opts['duration_sec']}\n"
              + f"language_style={opts['language_style']}\n")
    genre_ctx = (opts.get("genre_context") or "").strip()
    if genre_ctx:
        prompt += "## 题材规则\n" + genre_ctx + "\n"
    prompt += "**只输出一个 JSON 代码块**。"
    return prompt


@router.post("/script/outline")
async def script_outline(req: ScriptOutlineReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}", "hint": "项目目录打不开。"}})

    idea_path = idea_read_path(project_dir)
    if idea_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "创意.json missing",
                      "hint": "请先在「创意」步生成候选并选定一个。"}})

    if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
        purge_downstream(project_dir, stage="script_outline")

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_SCRIPT_MODEL")
             or cfg.default_models.get("script"))
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_SCRIPT_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_SCRIPT_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))
    print(f"[script_outline] model={model!r} base_url={base_url!r} "
          f"cred_src={'body' if body_key else 'env'}", flush=True)

    async def gen():
        import traceback
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
            selected_id = idea.get("selected_id", "")
            sel = next((c for c in idea.get("candidates", [])
                          if c.get("id") == selected_id),
                        idea.get("candidates", [{}])[0]
                        if idea.get("candidates") else {})

            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("script_outline", project_dir=project_dir)
            opts = req.options.model_dump()
            prompt = build_outline_prompt(tpl_text, sel, req.episode_count, opts)
            messages = [{"role": "user", "content": prompt}]

            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort,
                               response_format={"type": "json_object"})

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if await request.is_disconnected():
                    return
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            raw = "".join(acc)

            yield sse_event("status", {"phase": "validating"})
            rr = repair_json_text(raw)
            if not rr.ok:
                raw_path = project_dir / ".outline_raw.txt"
                atomic_write_text(raw_path, raw)
                yield sse_event("error", {
                    "code": "JSON_REPAIR_FAILED",
                    "message": rr.error,
                    "hint": "LLM 输出无法解析为合法 JSON。",
                    "details": {"raw_output_path": str(raw_path)}})
                return

            obj = rr.obj
            obj.setdefault("episode_count", req.episode_count)
            obj.setdefault("selected_episode", "")
            obj["input"] = sel
            obj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                ScriptIndex.model_validate(obj)
            except Exception as e:
                yield sse_event("error", {
                    "code": "SCHEMA_INVALID",
                    "message": str(e),
                    "hint": "大纲格式不合规。"})
                return

            yield sse_event("status", {"phase": "saving"})
            si_path = script_index_path(project_dir)
            atomic_write_text(si_path, json.dumps(obj, ensure_ascii=False, indent=2))
            yield sse_event("done", {"saved": str(si_path),
                                      "result": {"episodes": obj.get("episodes", [])}})
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[script_outline] EXCEPTION\n{tb}", flush=True)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "hint": "看 ~/.drama_shot_master/logs/screenwriter_agent.log 末尾"})

    return StreamingResponse(gen(), media_type="text/event-stream")
