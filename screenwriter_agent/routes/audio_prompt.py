"""POST /audio_prompt — SSE：分镜_E{id}.json + 剧本_E{id}.md → 角色音色设计 + 分镜音效配表。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.json_repair import repair_json_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import (
    storyboard_episode_read_path,
    script_episode_read_path,
    audio_prompts_dir,
)
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import AudioPromptReq

router = APIRouter()


@router.post("/audio_prompt")
async def audio_prompt(req: AudioPromptReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": str(req.project_dir),
                      "hint": "项目目录打不开。"}})

    sb_path = storyboard_episode_read_path(project_dir, req.episode_id)
    if sb_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": f"分镜_{req.episode_id}.json missing",
                      "hint": "请先在「分镜」步生成该集分镜。"}})

    out_dir = audio_prompts_dir(project_dir, req.episode_id)

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_AUDIO_PROMPT_MODEL")
             or cfg.default_models.get("audio_prompt"))
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_AUDIO_PROMPT_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_AUDIO_PROMPT_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))
    print(f"[audio_prompt] req: model={model!r} base_url={base_url!r} "
          f"cred_src={'body' if body_key else 'env'} key_set={bool(api_key)}",
          flush=True)

    async def generate():
        try:
            yield sse_event("start", {"message": f"正在生成 {req.episode_id} 音频提示词…"})

            sb_text = sb_path.read_text(encoding="utf-8")
            try:
                sb = json.loads(sb_text)
            except Exception:
                sb = {}

            # 可选剧本文本
            script_path = script_episode_read_path(project_dir, req.episode_id)
            script_text = script_path.read_text(encoding="utf-8") if script_path else ""

            storyboard_json_str = json.dumps(sb, ensure_ascii=False, indent=2)

            # --- Phase 1: 角色音色设计 ---
            tpl_voice, _ = load_template("voice_design", project_dir=project_dir)
            prompt_voice = tpl_voice.format(
                storyboard_json=storyboard_json_str,
                script_text=script_text,
            )

            client = LLMClient(
                api_key=api_key,
                base_url=base_url,
                model=model,
                reasoning_effort=req.reasoning_effort,
                response_format={"type": "json_object"},
            )

            yield sse_event("status", {"phase": "streaming_voice_design"})
            acc: list[str] = []
            for chunk in client.stream_chat([{"role": "user", "content": prompt_voice}]):
                if await request.is_disconnected():
                    print("[audio_prompt] client disconnected; aborting LLM stream",
                           flush=True)
                    return
                if chunk.kind == "delta":
                    acc.append(chunk.text)
            raw_voice = "".join(acc)

            rr_voice = repair_json_text(raw_voice)
            if not rr_voice.ok:
                yield sse_event("error", {"message": f"voice_design JSON 解析失败: {rr_voice.error}",
                                           "raw": raw_voice[:500]})
                return

            out_dir.mkdir(parents=True, exist_ok=True)

            voices_json = json.dumps(rr_voice.obj, ensure_ascii=False, indent=2)
            voices_path = out_dir / "voices.json"
            atomic_write_text(voices_path, voices_json)
            yield sse_event("partial", {"file": str(voices_path.relative_to(project_dir)),
                                        "content": voices_json})

            # --- Phase 2: 分镜音效配表 ---
            tpl_sfx, _ = load_template("sfx_cues", project_dir=project_dir)
            prompt_sfx = tpl_sfx.format(
                storyboard_json=storyboard_json_str,
                script_text=script_text,
            )

            client2 = LLMClient(
                api_key=api_key,
                base_url=base_url,
                model=model,
                reasoning_effort=req.reasoning_effort,
                response_format={"type": "json_object"},
            )

            yield sse_event("status", {"phase": "streaming_sfx_cues"})
            acc2: list[str] = []
            for chunk in client2.stream_chat([{"role": "user", "content": prompt_sfx}]):
                if await request.is_disconnected():
                    print("[audio_prompt] client disconnected; aborting LLM stream",
                           flush=True)
                    return
                if chunk.kind == "delta":
                    acc2.append(chunk.text)
            raw_sfx = "".join(acc2)

            rr_sfx = repair_json_text(raw_sfx)
            if not rr_sfx.ok:
                yield sse_event("error", {"message": f"sfx_cues JSON 解析失败: {rr_sfx.error}",
                                           "raw": raw_sfx[:500]})
                return

            sfx_json = json.dumps(rr_sfx.obj, ensure_ascii=False, indent=2)
            sfx_path = out_dir / "sfx_cues.json"
            atomic_write_text(sfx_path, sfx_json)
            yield sse_event("partial", {"file": str(sfx_path.relative_to(project_dir)),
                                        "content": sfx_json})

            yield sse_event("done", {"saved_dir": str(out_dir.relative_to(project_dir))})

        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            print(f"[audio_prompt] EXCEPTION model={model!r} base_url={base_url!r}\n{tb}",
                   flush=True)
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": f"{type(e).__name__}: {e}",
                                       "hint": "看 agent log 末尾 traceback"})

    return StreamingResponse(generate(), media_type="text/event-stream")
