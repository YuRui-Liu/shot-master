"""POST /prompts — SSE：分镜_E{id}.json → 角色参考图 + N 宫格分镜图提示词。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.downstream import purge_downstream
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import storyboard_episode_read_path, episode_prompts_dir
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import PromptsReq

router = APIRouter()


def build_grid_user_prompt(tpl_text: str, sb: dict, grp: list,
                           group_index: int, opts: dict) -> str:
    """拼出"本组宫格提示词"的 user prompt：模板 + 尺寸/角色/本组镜头上下文。

    注入 aspect_ratio（尺寸映射）+ characters（Character Lock）+ globalStyle，
    供模型按 9 节英文结构生成带布局约束的合成宫格图提示词。
    """
    return (
        tpl_text
        + "\n\n## 运行参数\n"
        + f"grid_mode={opts.get('grid_mode', '9')}\n"
        + f"aspect_ratio={sb.get('aspectRatio', '16:9')}\n"
        + f"group_index={group_index}\n"
        + f"quality_boost={opts.get('quality_boost', True)}\n"
        + f"style_extra={opts.get('style_extra', '')}\n"
        + f"negative_preset={opts.get('negative_preset', '')}\n"
        + "\n## 全局风格 globalStyle\n"
        + sb.get("globalStyle", "")
        + "\n\n## 角色（# Character Lock 来源）\n```json\n"
        + json.dumps(sb.get("characters", []), ensure_ascii=False, indent=2)
        + "\n```\n\n## 本组镜头（按顺序映射 F1, F2, …）\n```json\n"
        + json.dumps(grp, ensure_ascii=False, indent=2)
        + "\n```\n"
    )


@router.post("/prompts")
async def prompts(req: PromptsReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}", "hint": "项目目录打不开。"}})
    sb_path = storyboard_episode_read_path(project_dir, req.episode_id)
    if sb_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": f"分镜_{req.episode_id}.json missing",
                      "hint": "请先在「分镜」步生成该集。"}})
    try:
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "分镜.json parse failed", "hint": ""}})
    # 重生：清 prompts/（partial 落盘前先空目录，让 _ProductTree 状态点重置）
    if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
        purge_downstream(project_dir, stage="prompts", episode_id=req.episode_id)

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_PROMPTS_MODEL")
             or cfg.default_models.get("prompts"))
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_PROMPTS_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_PROMPTS_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))
    print(f"[prompts] req: model={model!r} base_url={base_url!r} "
          f"cred_src={'body' if body_key else 'env'} key_set={bool(api_key)}",
          flush=True)

    async def gen():
        try:
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)
            opts = req.options.model_dump()
            saved_paths: list[str] = []

            ep_dir = episode_prompts_dir(project_dir, req.episode_id)
            ref_dir = ep_dir / "角色参考图"
            grid_dir = ep_dir / "N宫格"

            # 1) 角色参考图（每个 character 一份 .md）
            if opts["include_character_refs"]:
                tpl_text, _ = load_template("character_ref", project_dir=project_dir)
                for ch in sb.get("characters", []):
                    name = ch.get("name", "")
                    if not name:
                        continue
                    yield sse_event("status", {"phase": "streaming"})
                    prompt = (tpl_text
                              + "\n\n## 角色\n```json\n"
                              + json.dumps(ch, ensure_ascii=False, indent=2)
                              + "\n```\n## 全局风格\n"
                              + sb.get("globalStyle", "")
                              + f"\n## 风格补充\n{opts['style_extra']}\n")
                    acc: list[str] = []
                    for c in client.stream_chat([{"role": "user", "content": prompt}]):
                        if await request.is_disconnected():
                            print("[prompts] disconnected mid-char-ref",
                                   flush=True)
                            return
                        if c.kind == "delta":
                            acc.append(c.text)
                    out_md = "".join(acc)
                    ref_path = ref_dir / f"{name}_ref.md"
                    atomic_write_text(ref_path, out_md)
                    saved_paths.append(str(ref_path))
                    yield sse_event("partial", {"saved": str(ref_path),
                                                "kind": "character_ref",
                                                "episode_id": req.episode_id})

            # 2) N 宫格分镜图
            tpl_grid, _ = load_template("grid_prompt", project_dir=project_dir)
            grid_size = {"single": 1, "4": 4, "9": 9}.get(opts["grid_mode"], 9)
            shots = sb.get("shots", [])
            groups = [shots[i:i + grid_size] for i in range(0, len(shots), grid_size)]
            for gi, grp in enumerate(groups, start=1):
                yield sse_event("status", {"phase": "streaming"})
                prompt = build_grid_user_prompt(tpl_grid, sb, grp, gi, opts)
                acc: list[str] = []
                for c in client.stream_chat([{"role": "user", "content": prompt}]):
                    if await request.is_disconnected():
                        print("[prompts] disconnected mid-grid", flush=True)
                        return
                    if c.kind == "delta":
                        acc.append(c.text)
                sheet_md = "".join(acc)
                sheet_path = grid_dir / f"S{gi}.md"
                atomic_write_text(sheet_path, sheet_md)
                saved_paths.append(str(sheet_path))
                yield sse_event("partial", {"saved": str(sheet_path),
                                            "kind": "grid_prompt",
                                            "episode_id": req.episode_id})

            yield sse_event("done", {"saved": saved_paths,
                                     "episode_id": req.episode_id,
                                     "result": {
                "character_refs": len(sb.get("characters", [])) if opts["include_character_refs"] else 0,
                "grid_sheets": len(groups)}, "warnings": []})
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            print(f"[prompts] EXCEPTION model={model!r} base_url={base_url!r}\n{tb}",
                   flush=True)
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": f"{type(e).__name__}: {e}",
                                       "hint": "看 agent log 末尾 traceback"})

    return StreamingResponse(gen(), media_type="text/event-stream")
