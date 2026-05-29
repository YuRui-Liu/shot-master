"""POST /storyboard — SSE：读剧本_E{id}.md → LLM JSON → 修复 + 校验 → 落盘 分镜_E{id}.json。"""
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
from screenwriter_agent.core.paths import script_episode_read_path, storyboard_episode_path
from screenwriter_agent.core.schema_validator import validate_storyboard
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import StoryboardReq

router = APIRouter()


@router.post("/storyboard")
async def storyboard(req: StoryboardReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}",
                      "hint": "项目目录打不开。"}})
    script_path = script_episode_read_path(project_dir, req.episode_id)
    if script_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": f"剧本_{req.episode_id}.md missing",
                      "hint": "请先在「剧本」步生成该集。"}})
    # 重生：清下游（分镜.json / prompts/）
    if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
        purge_downstream(project_dir, stage="storyboard", episode_id=req.episode_id)

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_STORYBOARD_MODEL")
             or cfg.default_models.get("storyboard"))
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_STORYBOARD_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_STORYBOARD_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))
    print(f"[storyboard] req: model={model!r} base_url={base_url!r} "
          f"cred_src={'body' if body_key else 'env'} key_set={bool(api_key)}",
          flush=True)

    async def gen():
        try:
            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("storyboard", project_dir=project_dir)
            md = script_path.read_text(encoding="utf-8")
            opts = req.options.model_dump()
            prompt = (tpl_text
                      + "\n\n## 剧本.md（输入）\n"
                      + md
                      + f"\n\n## 参数\nfps={opts['fps']}, "
                      + f"aspect_ratio={opts['aspect_ratio']}, "
                      + f"default_duration={opts['shot_duration_default']}, "
                      + f"density={opts['density']}\n\n"
                      + "**只输出一个 JSON 代码块**。")
            messages = [{"role": "user", "content": prompt}]

            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort,
                               response_format={"type": "json_object"})

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if await request.is_disconnected():
                    print("[storyboard] client disconnected; aborting LLM stream",
                           flush=True)
                    return
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            raw = "".join(acc)

            yield sse_event("status", {"phase": "validating"})
            rr = repair_json_text(raw)
            if not rr.ok:
                ts = time.strftime("%Y%m%dT%H%M%S")
                raw_path = project_dir / f"分镜_raw_{ts}.txt"
                atomic_write_text(raw_path, raw)
                yield sse_event("error", {
                    "code": "JSON_REPAIR_FAILED",
                    "message": rr.error,
                    "hint": "模型这次没给出 JSON，原始输出存到了 raw 文件，可换模型再试。",
                    "details": {"raw_output_path": str(raw_path),
                                "repair_steps_tried": rr.steps}})
                return

            try:
                validated, warns = validate_storyboard(
                    rr.obj,
                    fallback_title=_extract_title_from_script(md),
                    default_aspect_ratio=opts["aspect_ratio"],
                    default_fps=opts["fps"],
                    default_shot_duration=opts["shot_duration_default"])
            except ValueError as e:
                yield sse_event("error", {
                    "code": "SCHEMA_VALIDATION_FAILED",
                    "message": str(e), "hint": "分镜数据缺关键字段，请重试。"})
                return

            yield sse_event("status", {"phase": "saving"})
            sb_path = storyboard_episode_path(project_dir, req.episode_id)
            atomic_write_text(sb_path, json.dumps(validated,
                                                   ensure_ascii=False, indent=2))
            yield sse_event("done", {
                "saved": str(sb_path),
                "episode_id": req.episode_id,
                "result": validated,
                "warnings": [w.__dict__ for w in warns],
            })
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            print(f"[storyboard] EXCEPTION model={model!r} base_url={base_url!r}\n{tb}",
                   flush=True)
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": f"{type(e).__name__}: {e}",
                                       "hint": "看 agent log 末尾 traceback"})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _extract_title_from_script(md: str) -> str:
    for ln in md.splitlines()[:30]:
        ln = ln.strip()
        for tag in ("标题：", "标题:"):
            if ln.startswith(tag):
                return ln[len(tag):].strip()
    return ""
