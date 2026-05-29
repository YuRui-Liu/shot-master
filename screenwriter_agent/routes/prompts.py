"""POST /prompts — SSE：分镜.json → 角色参考图 + N 宫格分镜图提示词。"""
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
from screenwriter_agent.models.requests import PromptsReq

router = APIRouter()


@router.post("/prompts")
async def prompts(req: PromptsReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}", "hint": "项目目录打不开。"}})
    sb_path = project_dir / "分镜.json"
    if not sb_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "分镜.json missing",
                      "hint": "请先在「分镜」步生成分镜.json。"}})
    try:
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "分镜.json parse failed", "hint": ""}})

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_PROMPTS_MODEL")
             or cfg.default_models.get("prompts"))

    async def gen():
        try:
            api_key = (os.environ.get("SCREENWRITER_PROMPTS_API_KEY")
                       or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
            base_url = (os.environ.get("SCREENWRITER_PROMPTS_BASE_URL")
                        or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                           "https://api.deepseek.com"))
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)
            opts = req.options.model_dump()
            saved_paths: list[str] = []

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
                        if c.kind == "delta":
                            acc.append(c.text)
                    out_md = "".join(acc)
                    ref_dir = project_dir / "prompts" / "角色参考图"
                    ref_path = ref_dir / f"{name}_ref.md"
                    atomic_write_text(ref_path, out_md)
                    saved_paths.append(str(ref_path))
                    yield sse_event("partial", {"saved": str(ref_path),
                                                "kind": "character_ref"})

            # 2) N 宫格分镜图
            tpl_grid, _ = load_template("grid_prompt", project_dir=project_dir)
            grid_size = {"single": 1, "4": 4, "9": 9}.get(opts["grid_mode"], 9)
            shots = sb.get("shots", [])
            groups = [shots[i:i + grid_size] for i in range(0, len(shots), grid_size)]
            for gi, grp in enumerate(groups, start=1):
                yield sse_event("status", {"phase": "streaming"})
                prompt = (tpl_grid
                          + "\n\n## 全局风格\n"
                          + sb.get("globalStyle", "")
                          + f"\n## grid_mode\n{opts['grid_mode']}\n"
                          + f"## quality_boost\n{opts['quality_boost']}\n"
                          + f"## negative_preset\n{opts['negative_preset']}\n"
                          + f"## 风格补充\n{opts['style_extra']}\n"
                          + "## 本组镜头\n```json\n"
                          + json.dumps(grp, ensure_ascii=False, indent=2)
                          + "\n```\n")
                acc: list[str] = []
                for c in client.stream_chat([{"role": "user", "content": prompt}]):
                    if c.kind == "delta":
                        acc.append(c.text)
                sheet_md = "".join(acc)
                sheet_path = project_dir / "prompts" / "N宫格" / f"S{gi}.md"
                atomic_write_text(sheet_path, sheet_md)
                saved_paths.append(str(sheet_path))
                yield sse_event("partial", {"saved": str(sheet_path),
                                            "kind": "grid_prompt"})

            yield sse_event("done", {"saved": saved_paths, "result": {
                "character_refs": len(sb.get("characters", [])) if opts["include_character_refs"] else 0,
                "grid_sheets": len(groups)}, "warnings": []})
        except Exception as e:
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": str(e), "hint": ""})

    return StreamingResponse(gen(), media_type="text/event-stream")
