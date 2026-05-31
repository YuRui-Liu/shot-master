"""imaging 端点：拆图/去白边/拼接（同步 JSON）+ 批量拆图（SSE）。

复用 drama_shot_master.imaging 的纯 PIL 实现（零 Qt）。本地服务，图片以
文件路径传递（同机），不走 base64，避免大文件过 IPC。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from PIL import Image

from drama_shot_master.imaging.splitter import split_image
from drama_shot_master.imaging.combiner import combine_images
from drama_shot_master.imaging.aspect_ops import trim_white_edges, center_crop_to_aspect
from drama_shot_master.imaging.border_detector import (
    infer_grid, detect_borders, find_cell_boxes,
)
from drama_shot_master.imaging.saver import save_image
from drama_shot_master.imaging.specs import (
    GridSpec, CombineSpec, Margins, AspectRatio, ScaleMode,
)
from drama_shot_master.core.task_runner import TaskRunner, TaskItem
from media_agent.core.sse import sse_event

router = APIRouter(prefix="/imaging")

_EXT = {"PNG": "png", "JPG": "jpg"}


class MarginsModel(BaseModel):
    top: int = 0
    right: int = 0
    bottom: int = 0
    left: int = 0


class AspectModel(BaseModel):
    w: int = 0
    h: int = 0


def _aspect(a: AspectModel | None) -> AspectRatio:
    if a is None:
        return AspectRatio.auto()
    return AspectRatio(a.w, a.h)


class SplitRequest(BaseModel):
    src_path: str
    src_rows: int = 1
    src_cols: int = 1
    sub_rows: int = 1
    sub_cols: int = 1
    margins: MarginsModel = MarginsModel()
    gap: int = 0
    target_aspect: AspectModel = AspectModel()
    out_dir: str
    base_name: str = "cell"
    fmt: str = "PNG"


def _do_split(req: SplitRequest) -> list[str]:
    spec = GridSpec(
        src_rows=req.src_rows, src_cols=req.src_cols,
        sub_rows=req.sub_rows, sub_cols=req.sub_cols,
        margins=Margins(req.margins.top, req.margins.right,
                        req.margins.bottom, req.margins.left),
        gap=req.gap, target_aspect=_aspect(req.target_aspect),
    )
    fmt = req.fmt.upper()
    ext = _EXT.get(fmt, "png")
    out_dir = Path(req.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(req.src_path) as src:
        cells = split_image(src, spec)
    outputs: list[str] = []
    for i, cell in enumerate(cells):
        p = out_dir / f"{req.base_name}_{i:02d}.{ext}"
        save_image(cell, p, fmt)
        outputs.append(str(p))
    return outputs


@router.post("/split")
def split(req: SplitRequest):
    return {"outputs": _do_split(req)}


class TrimRequest(BaseModel):
    src_path: str
    threshold: int = 240
    max_iter: int = 5
    out_path: str
    fmt: str = "PNG"


@router.post("/trim")
def trim(req: TrimRequest):
    with Image.open(req.src_path) as src:
        out = trim_white_edges(src, threshold=req.threshold, max_iter=req.max_iter)
        out.load()
    p = Path(req.out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    save_image(out, p, req.fmt.upper())
    return {"output": str(p)}


class CombineRequest(BaseModel):
    src_paths: list[str]
    target_rows: int
    target_cols: int
    gap: int = 0
    target_aspect: AspectModel = AspectModel()
    scale_mode: str = "letterbox"
    out_path: str
    fmt: str = "PNG"


@router.post("/combine")
def combine(req: CombineRequest):
    imgs = [Image.open(p) for p in req.src_paths]
    try:
        spec = CombineSpec(
            target_rows=req.target_rows, target_cols=req.target_cols,
            gap=req.gap, target_aspect=_aspect(req.target_aspect),
            scale_mode=ScaleMode(req.scale_mode),
        )
        out = combine_images(imgs, spec, bg=(255, 255, 255, 255))
    finally:
        for im in imgs:
            im.close()
    p = Path(req.out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    save_image(out, p, req.fmt.upper())
    return {"output": str(p)}


# ── 自动检测（返回 JSON，供前端填表单，不存盘）──
class DetectRequest(BaseModel):
    src_path: str
    white_threshold: int = 240
    min_white_ratio: float = 0.95


@router.post("/infer_grid")
def infer_grid_route(req: DetectRequest):
    with Image.open(req.src_path) as src:
        rows, cols = infer_grid(src, white_threshold=req.white_threshold,
                                min_white_ratio=req.min_white_ratio)
    return {"rows": rows, "cols": cols}


@router.post("/detect_borders")
def detect_borders_route(req: DetectRequest):
    with Image.open(req.src_path) as src:
        m, gap = detect_borders(src, white_threshold=req.white_threshold,
                                min_white_ratio=req.min_white_ratio)
    return {"margins": {"top": m.top, "right": m.right,
                        "bottom": m.bottom, "left": m.left}, "gap": gap}


class CellBoxesRequest(BaseModel):
    src_path: str
    n_rows: int
    n_cols: int
    white_threshold: int = 240
    min_ratio: float = 0.95


@router.post("/cell_boxes")
def cell_boxes_route(req: CellBoxesRequest):
    with Image.open(req.src_path) as src:
        boxes, mode = find_cell_boxes(
            src, req.n_rows, req.n_cols,
            white_threshold=req.white_threshold, min_ratio=req.min_ratio)
    return {"boxes": [list(b) for b in boxes], "mode": mode}


# ── aspect 居中裁剪（存盘）──
class CropAspectRequest(BaseModel):
    src_path: str
    aspect: AspectModel
    out_path: str
    fmt: str = "PNG"


@router.post("/crop_aspect")
def crop_aspect_route(req: CropAspectRequest):
    with Image.open(req.src_path) as src:
        out = center_crop_to_aspect(src, _aspect(req.aspect))
        out.load()
    p = Path(req.out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    save_image(out, p, req.fmt.upper())
    return {"output": str(p)}


class BatchSplitRequest(BaseModel):
    items: list[SplitRequest]


@router.post("/batch_split")
async def batch_split(req: BatchSplitRequest):
    """批量拆图 → SSE。事件对齐 core.task_runner.TaskEvent。"""
    items = [
        TaskItem(idx=i, payload={"req": r}, base_name=Path(r.src_path).name)
        for i, r in enumerate(req.items)
    ]

    async def worker(item: TaskItem) -> dict:
        r: SplitRequest = item.payload["req"]
        outputs = await asyncio.to_thread(_do_split, r)
        return {"outputs": outputs}

    runner = TaskRunner(items, worker)

    async def gen():
        async for ev in runner.stream():
            yield sse_event(ev.type, ev.payload)

    return StreamingResponse(gen(), media_type="text/event-stream")
