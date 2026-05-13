"""POST /api/grid/combine — 多张图按 R×C 网格合并"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image

from shot_master.core.specs import CombineSpec, AspectRatio, ScaleMode
from shot_master.core.combiner import combine_images
from shot_master.core.saver import save_image
from shot_master.core.exceptions import CombineCountError


router = APIRouter()


class GridCombineRequest(BaseModel):
    images: list[str]
    output_path: str
    target_rows: int
    target_cols: int
    gap: int = 0
    scale_mode: str = "letterbox"
    target_aspect_w: int = 0
    target_aspect_h: int = 0
    bg_r: int = 255
    bg_g: int = 255
    bg_b: int = 255
    bg_a: int = 255
    output_format: str = "PNG"


@router.post("/api/grid/combine")
async def combine(req: GridCombineRequest):
    imgs: list[Image.Image] = []
    for s in req.images:
        p = Path(s)
        if not p.exists():
            raise HTTPException(400, f"image not found: {p}")
        imgs.append(Image.open(p))

    scale = {
        "letterbox": ScaleMode.LETTERBOX,
        "crop": ScaleMode.CROP,
        "stretch": ScaleMode.STRETCH,
    }.get(req.scale_mode, ScaleMode.LETTERBOX)

    aspect = AspectRatio(req.target_aspect_w, req.target_aspect_h)
    spec = CombineSpec(
        target_rows=req.target_rows,
        target_cols=req.target_cols,
        gap=req.gap,
        target_aspect=aspect,
        scale_mode=scale,
    )
    bg = (req.bg_r, req.bg_g, req.bg_b, req.bg_a)
    try:
        merged = combine_images(imgs, spec, bg)
    except CombineCountError as e:
        raise HTTPException(400, f"image count mismatch: expected {e.expected}, got {e.actual}")

    out_path = Path(req.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(merged, out_path, req.output_format, bg=(req.bg_r, req.bg_g, req.bg_b))
    return {"output_path": str(out_path),
            "size": [merged.width, merged.height]}
