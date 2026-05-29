"""POST /script — SSE：读 idea.json.selected → LLM → 落盘 剧本.md。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import ScriptReq

router = APIRouter()


@router.post("/script")
async def script(req: ScriptReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"path not found: {req.project_dir}",
                      "hint": "项目目录打不开。"}})
    idea_path = project_dir / "idea.json"
    if not idea_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "idea.json missing",
                      "hint": "请先在「创意」步生成候选并选定一个。"}})
    try:
        idea = json.loads(idea_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "idea.json parse failed",
                      "hint": ""}})
    if not idea.get("selected_id"):
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "no selected candidate",
                      "hint": "请先回到「创意」步骤选定一个候选。"}})

    sel = next((c for c in idea["candidates"]
                if c["id"] == idea["selected_id"]), None)
    if not sel:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "selected_id not in candidates",
                      "hint": ""}})

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_SCRIPT_MODEL")
             or cfg.default_models.get("script"))

    async def gen():
        try:
            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("script", project_dir=project_dir)
            opts = req.options.model_dump()
            prompt = (tpl_text
                      + "\n\n## 选定候选\n```json\n"
                      + json.dumps(sel, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 原始输入\n```json\n"
                      + json.dumps(idea.get("input", {}), ensure_ascii=False, indent=2)
                      + f"\n```\n\n## 参数\nfps={opts['fps']}, "
                      + f"duration_sec={opts['duration_sec']}, "
                      + f"length_preset={opts['length_preset']}, "
                      + f"language_style={opts['language_style']}\n")
            messages = [{"role": "user", "content": prompt}]

            api_key = (os.environ.get("SCREENWRITER_SCRIPT_API_KEY")
                       or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
            base_url = (os.environ.get("SCREENWRITER_SCRIPT_BASE_URL")
                        or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                           "https://api.deepseek.com"))
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            md = "".join(acc)

            yield sse_event("status", {"phase": "saving"})
            script_path = project_dir / "剧本.md"
            atomic_write_text(script_path, md)
            summary = {"shot_count": md.count("## 镜头"),
                       "total_duration": opts["duration_sec"],
                       "title": sel.get("title", "")}
            yield sse_event("done", {"saved": str(script_path),
                                      "result": {"summary": summary, "warnings": []}})
        except Exception as e:
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": str(e), "hint": ""})

    return StreamingResponse(gen(), media_type="text/event-stream")
