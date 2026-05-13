"""GET /api/files/list      — 列文件夹中的图片
GET /api/files/thumbnail — 返回缩略图（内存生成，PNG 流）
"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from PIL import Image


router = APIRouter()
SUPPORTED = {".png", ".jpg", ".jpeg", ".webp"}


@router.get("/api/files/list")
async def list_files(folder: str = Query(...)):
    p = Path(folder)
    if not p.is_dir():
        raise HTTPException(400, f"folder not found: {folder}")
    items = []
    for entry in sorted(p.iterdir()):
        if entry.is_file() and entry.suffix.lower() in SUPPORTED:
            try:
                stat = entry.stat()
                size = stat.st_size
            except OSError:
                size = 0
            items.append({
                "name": entry.name,
                "path": str(entry.absolute()),
                "size": size,
            })
    return {"folder": str(p.absolute()), "items": items}


@router.get("/api/files/thumbnail")
async def thumbnail(path: str = Query(...), size: int = Query(160)):
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(400, f"file not found: {path}")
    try:
        img = Image.open(p)
    except Exception as e:
        raise HTTPException(400, f"not an image: {e}")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    fmt = "PNG" if p.suffix.lower() == ".png" else "JPEG"
    if fmt == "JPEG" and img.mode in ("RGBA", "LA"):
        img = img.convert("RGB")
    img.save(buf, fmt)
    buf.seek(0)
    return StreamingResponse(buf, media_type=f"image/{fmt.lower()}")
