"""POST /api/border/trim     — 单图去白边
POST /api/border/trim_batch — 批量去白边
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image

from shot_master.core.aspect_ops import trim_white_edges
from shot_master.core.saver import save_image


router = APIRouter()


class TrimRequest(BaseModel):
    image_path: str
    output_path: str
    threshold: int = 240
    max_iter: int = 5
    output_format: str = "PNG"


class TrimBatchRequest(BaseModel):
    folder: str
    output_dir: str
    threshold: int = 240
    max_iter: int = 5
    output_format: str = "PNG"
    name_suffix: str = ""           # "" → 覆盖式同名；"_trim" → 加后缀


@router.post("/api/border/trim")
async def trim(req: TrimRequest):
    src = Path(req.image_path)
    if not src.exists():
        raise HTTPException(400, f"image not found: {src}")
    img = Image.open(src)
    trimmed = trim_white_edges(img, threshold=req.threshold, max_iter=req.max_iter)
    out = Path(req.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_image(trimmed, out, req.output_format)
    return {"output_path": str(out),
            "size": [trimmed.width, trimmed.height]}


SUPPORTED = {".png", ".jpg", ".jpeg", ".webp"}


@router.post("/api/border/trim_batch")
async def trim_batch(req: TrimBatchRequest):
    folder = Path(req.folder)
    if not folder.is_dir():
        raise HTTPException(400, f"folder not found: {folder}")
    out_dir = Path(req.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in SUPPORTED:
            continue
        img = Image.open(p)
        trimmed = trim_white_edges(img, threshold=req.threshold, max_iter=req.max_iter)
        if req.output_format.upper() == "PNG":
            name = f"{p.stem}{req.name_suffix}.png"
        else:
            name = f"{p.stem}{req.name_suffix}.jpg"
        out = out_dir / name
        save_image(trimmed, out, req.output_format)
        saved.append(str(out))
    return {"files": saved}
