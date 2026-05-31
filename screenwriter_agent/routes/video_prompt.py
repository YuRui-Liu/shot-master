"""POST /video_prompt — SSE：分镜_E{id}.json → LTX2.3 global_prompt + per-shot local_prompt。"""
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
    storyboard_episode_read_path, video_prompts_dir,
)
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import VideoPromptReq

router = APIRouter()


def video_template_id(template_id: str) -> str:
    """模板选择：ltx→video_prompt_ltx（画面/运镜/音效），其余→video_prompt（简洁）。"""
    return "video_prompt_ltx" if template_id == "ltx" else "video_prompt"


def build_video_user_prompt(tpl_text: str, sb: dict, opts) -> str:
    """渲染视频提示词 user prompt：注入分镜 JSON + fps + 比例 + 语言。

    ②c 风格+题材驱动（导演台 LTX 2.3，保持 global + per-shot + 时间结构）：
      - opts.style_context 非空 → 追加 '## 导演台全局风格 global_prompt（基底）'，
        提示模型据此产出 global_prompt（风格统一全片）；
      - opts.genre_context 非空 → 追加 '## 题材基调' 供全片基调参考。
    空则与现状完全一致（向后兼容）。"""
    prompt = tpl_text.format(
        storyboard_json=json.dumps(sb, ensure_ascii=False, indent=2),
        fps=opts.fps,
        aspect_ratio=opts.aspect_ratio,
        language=opts.language,
    )
    style_ctx = (getattr(opts, "style_context", "") or "").strip()
    if style_ctx:
        prompt += ("\n\n## 导演台全局风格 global_prompt（基底，请据此产出 global_prompt）\n"
                   + style_ctx)
    genre_ctx = (getattr(opts, "genre_context", "") or "").strip()
    if genre_ctx:
        prompt += "\n\n## 题材基调\n" + genre_ctx
    return prompt


def write_video_output(out_dir, data: dict) -> str:
    """把 LLM 输出对象 {global_prompt, shots:[...]} 原子写入单文件 shots.json。
    返回写出文件名（'shots.json'）。"""
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "global_prompt": data.get("global_prompt", ""),
        "shots": data.get("shots", []),
    }
    shots_path = out_dir / "shots.json"
    atomic_write_text(
        shots_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return "shots.json"


@router.post("/video_prompt")
async def video_prompt(req: VideoPromptReq, request: Request):
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

    out_dir = video_prompts_dir(project_dir, req.episode_id)

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_VIDEO_PROMPT_MODEL")
             or cfg.default_models.get("video_prompt"))
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_VIDEO_PROMPT_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_VIDEO_PROMPT_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))
    print(f"[video_prompt] req: model={model!r} base_url={base_url!r} "
          f"cred_src={'body' if body_key else 'env'} key_set={bool(api_key)}",
          flush=True)

    async def generate():
        try:
            yield sse_event("start", {"message": f"正在生成 {req.episode_id} 视频提示词…"})

            sb_text = sb_path.read_text(encoding="utf-8")
            try:
                sb = json.loads(sb_text)
            except Exception:
                sb = {}

            tpl_id = video_template_id(req.options.template_id)
            tpl_text, _ = load_template(tpl_id, project_dir=project_dir)
            prompt = build_video_user_prompt(tpl_text, sb, req.options)

            client = LLMClient(
                api_key=api_key,
                base_url=base_url,
                model=model,
                reasoning_effort=req.reasoning_effort,
                response_format={"type": "json_object"},
            )

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for chunk in client.stream_chat([{"role": "user", "content": prompt}]):
                if await request.is_disconnected():
                    print("[video_prompt] client disconnected; aborting LLM stream",
                           flush=True)
                    return
                if chunk.kind == "delta":
                    acc.append(chunk.text)
            raw = "".join(acc)

            rr = repair_json_text(raw)
            if not rr.ok:
                yield sse_event("error", {"message": f"JSON 解析失败: {rr.error}",
                                           "raw": raw[:500]})
                return

            data = rr.obj

            write_video_output(out_dir, data)
            shots_path = out_dir / "shots.json"
            yield sse_event("partial", {
                "file": str(shots_path.relative_to(project_dir)),
                "content": shots_path.read_text(encoding="utf-8"),
            })

            yield sse_event("done", {"saved_dir": str(out_dir.relative_to(project_dir))})

        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            print(f"[video_prompt] EXCEPTION model={model!r} base_url={base_url!r}\n{tb}",
                   flush=True)
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": f"{type(e).__name__}: {e}",
                                       "hint": "看 agent log 末尾 traceback"})

    return StreamingResponse(generate(), media_type="text/event-stream")
