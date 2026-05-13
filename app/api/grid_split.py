"""POST /api/grid/preview  → 临时拆图（用于反推前的人工确认）
POST /api/grid/split    → 拆图落盘到指定目录
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image

from shot_master.core.specs import GridSpec, Margins, AspectRatio
from shot_master.core.splitter import split_image
from shot_master.core.saver import save_image
from shot_master.core.exceptions import (
    SplitGridError, MarginsTooLargeError, CellTooSmallError, AspectCropError,
)


router = APIRouter()
PREVIEW_DIR = Path("app/.cache/preview")


class GridPreviewRequest(BaseModel):
    image_path: str
    src_rows: int
    src_cols: int
    sub_rows: int = 1
    sub_cols: int = 1
    margin_top: int = 0
    margin_right: int = 0
    margin_bottom: int = 0
    margin_left: int = 0
    gap: int = 0


class GridSplitRequest(GridPreviewRequest):
    output_dir: str
    output_format: str = "PNG"
    name_prefix: str = ""


def _spec_from_req(req: GridPreviewRequest) -> GridSpec:
    return GridSpec(
        src_rows=req.src_rows,
        src_cols=req.src_cols,
        sub_rows=req.sub_rows,
        sub_cols=req.sub_cols,
        margins=Margins(top=req.margin_top, right=req.margin_right,
                        bottom=req.margin_bottom, left=req.margin_left),
        gap=req.gap,
        target_aspect=AspectRatio.auto(),
    )


def _load_src(path_str: str) -> Image.Image:
    p = Path(path_str)
    if not p.exists():
        raise HTTPException(400, f"image not found: {p}")
    return Image.open(p)


@router.post("/api/grid/preview")
async def preview(req: GridPreviewRequest):
    src = _load_src(req.image_path)
    spec = _spec_from_req(req)
    try:
        tiles = split_image(src, spec)
    except (SplitGridError, MarginsTooLargeError, CellTooSmallError, AspectCropError) as e:
        raise HTTPException(400, str(e))

    # 缓存目录：基于 image_path + spec hash
    key_src = (
        f"{req.image_path}|{spec.src_rows}x{spec.src_cols}"
        f"|{spec.sub_rows}x{spec.sub_cols}|{spec.margins}|{spec.gap}"
    )
    hsh = hashlib.md5(key_src.encode("utf-8")).hexdigest()[:12]
    out_dir = PREVIEW_DIR / hsh
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清空旧 tile
    for old in out_dir.glob("tile_*.png"):
        old.unlink()

    urls: list[str] = []
    for i, tile in enumerate(tiles):
        fname = f"tile_{i}.png"
        save_image(tile, out_dir / fname, "PNG")
        urls.append(f"/cache/preview/{hsh}/{fname}")
    return {"tiles": urls, "cache_key": hsh}


@router.post("/api/grid/split")
async def split(req: GridSplitRequest):
    src_path = Path(req.image_path)
    src = _load_src(req.image_path)
    spec = _spec_from_req(req)
    try:
        tiles = split_image(src, spec)
    except (SplitGridError, MarginsTooLargeError, CellTooSmallError, AspectCropError) as e:
        raise HTTPException(400, str(e))

    out_dir = Path(req.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = req.name_prefix or src_path.stem
    fmt = req.output_format.upper()
    ext = ".png" if fmt == "PNG" else ".jpg"
    saved: list[str] = []
    for i, tile in enumerate(tiles):
        out_path = out_dir / f"{prefix}_{i + 1}{ext}"
        save_image(tile, out_path, fmt)
        saved.append(str(out_path))
    return {"files": saved}
