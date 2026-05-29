"""POST /script/episode — SSE：读 剧本.json 该 episode → LLM → 落盘 剧本_E{id}.md。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.downstream import purge_downstream
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import (
    idea_read_path, script_index_path, script_episode_path,
)
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import ScriptEpisodeReq

router = APIRouter()


@router.post("/script/episode")
async def script_episode(req: ScriptEpisodeReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}", "hint": ""}})

    si_path = script_index_path(project_dir)
    if not si_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "剧本.json missing",
                      "hint": "请先在剧本阶段生成大纲。"}})
    try:
        si = json.loads(si_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "剧本.json parse failed", "hint": ""}})
    ep_entry = next((e for e in si.get("episodes", [])
                      if e.get("id") == req.episode_id), None)
    if ep_entry is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "EPISODE_NOT_FOUND",
                      "message": f"{req.episode_id} not in 剧本.json",
                      "hint": "集 id 不存在于大纲。"}})

    if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
        purge_downstream(project_dir, stage="script_episode",
                          episode_id=req.episode_id)

    idea_path = idea_read_path(project_dir)
    sel = {}
    if idea_path is not None:
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
            sel = next((c for c in idea.get("candidates", [])
                          if c.get("id") == idea.get("selected_id")), {})
        except Exception:
            pass

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
    print(f"[script_episode] ep={req.episode_id} model={model!r} "
          f"cred_src={'body' if body_key else 'env'}", flush=True)

    async def gen():
        import traceback
        try:
            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("script_episode", project_dir=project_dir)
            opts = req.options.model_dump()
            prompt = (tpl_text
                      + "\n\n## 选定候选\n```json\n"
                      + json.dumps(sel, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 本集大纲\n```json\n"
                      + json.dumps(ep_entry, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 参数\n"
                      + f"duration_sec={opts['duration_sec']}\n"
                      + f"language_style={opts['language_style']}\n")
            messages = [{"role": "user", "content": prompt}]

            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if await request.is_disconnected():
                    return
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            md = "".join(acc)

            yield sse_event("status", {"phase": "saving"})
            out_path = script_episode_path(project_dir, req.episode_id)
            atomic_write_text(out_path, md)
            yield sse_event("done", {"saved": str(out_path),
                                      "episode_id": req.episode_id,
                                      "result": {"summary": ep_entry.get("summary", ""),
                                                  "title": ep_entry.get("title", "")}})
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[script_episode] EXCEPTION ep={req.episode_id}\n{tb}", flush=True)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "episode_id": req.episode_id,
                "hint": "看 agent log 末尾 traceback"})

    return StreamingResponse(gen(), media_type="text/event-stream")
