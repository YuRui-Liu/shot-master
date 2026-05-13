"""POST /api/inference — 单次反推"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import Config
from app.core.output_writer import resolve_output_dir, write_outputs
from app.core.result_parser import parse_result
from app.core.template_engine import list_templates, render_template
from app.providers import factory


router = APIRouter()


class Override(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


class InferenceRequest(BaseModel):
    images: list[str]
    template_id: str
    supplement: dict = {}
    override: Optional[Override] = None
    output_dir: Optional[str] = None
    base_name: Optional[str] = None


@router.post("/api/inference")
async def inference(req: InferenceRequest, request: Request):
    cfg: Config = request.app.state.config

    # 校验图片
    image_paths = [Path(p) for p in req.images]
    for p in image_paths:
        if not p.exists():
            raise HTTPException(400, f"image not found: {p}")

    # 找模板
    tpls = list_templates(Path("templates"))
    matched = [t for t in tpls if t.id == req.template_id]
    if not matched:
        raise HTTPException(400, f"template '{req.template_id}' not found")
    tpl = matched[0]

    # 渲染 system_prompt
    try:
        system_prompt = render_template(tpl, req.supplement)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 选 provider/model（override 优先）
    provider_name = (req.override and req.override.provider) or cfg.current_provider
    model = (req.override and req.override.model) or cfg.current_model

    try:
        provider = factory.build_provider(cfg, provider_name=provider_name, model=model)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"provider build failed: {e}")

    # 调用 vision
    try:
        raw = provider.generate(image_paths, system_prompt, "")
    except Exception as e:
        raise HTTPException(502, f"vision API error: {e}")

    parsed = parse_result(raw)

    # 落盘
    base_name = req.base_name or image_paths[0].stem
    if req.output_dir:
        out_dir = Path(req.output_dir)
    else:
        out_dir = resolve_output_dir(image_paths[0], cfg.default_output_dir)
    md_path, json_path = write_outputs(
        result=parsed,
        output_dir=out_dir,
        base_name=base_name,
        template_id=tpl.id,
        provider=provider_name,
        model=model,
    )

    return {
        "global_prompt": parsed.global_prompt,
        "timeline_data": parsed.timeline_data,
        "local_prompts": parsed.local_prompts,
        "segment_lengths": parsed.segment_lengths,
        "max_frames": parsed.max_frames,
        "frame_indices": parsed.frame_indices,
        "strengths": parsed.strengths,
        "epsilon": parsed.epsilon,
        "notes": parsed.notes,
        "raw": parsed.raw,
        "md_path": str(md_path),
        "json_path": str(json_path),
        "meta": {
            "template_id": tpl.id,
            "provider": provider_name,
            "model": model,
        },
    }


class SaveRequest(BaseModel):
    md_path: str
    json_path: str
    fields: dict
    meta: dict


@router.post("/api/inference/save")
async def save_edited(req: SaveRequest):
    md_path = Path(req.md_path)
    json_path = Path(req.json_path)
    if not md_path.parent.exists():
        raise HTTPException(400, f"md path's parent missing: {md_path.parent}")

    # 用 fields + meta 重建 ParsedResult，复用 output_writer
    from app.core.result_parser import ParsedResult
    r = ParsedResult(raw=req.fields.get("raw", ""))
    r.global_prompt = req.fields.get("global_prompt", "")
    r.timeline_data = req.fields.get("timeline_data", "")
    r.local_prompts = req.fields.get("local_prompts", "")
    r.segment_lengths = req.fields.get("segment_lengths", []) or []
    r.max_frames = req.fields.get("max_frames")
    r.frame_indices = req.fields.get("frame_indices", []) or []
    r.strengths = req.fields.get("strengths", []) or []
    r.epsilon = req.fields.get("epsilon")
    r.notes = req.fields.get("notes", "")

    out_dir = md_path.parent
    base_name = md_path.stem
    new_md, new_json = write_outputs(
        result=r, output_dir=out_dir, base_name=base_name,
        template_id=req.meta.get("template_id", ""),
        provider=req.meta.get("provider", ""),
        model=req.meta.get("model", ""),
    )
    return {"md_path": str(new_md), "json_path": str(new_json)}
