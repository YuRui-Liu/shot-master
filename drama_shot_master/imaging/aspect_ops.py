"""Aspect ratio / cell-fit helpers shared by splitter and combiner."""
import numpy as np
from PIL import Image
from .specs import AspectRatio, ScaleMode


def trim_white_edges(img: Image.Image,
                     threshold: int = 240,
                     max_iter: int = 5) -> Image.Image:
    """迭代去除四边残留白边（与 scripts/split_4_to_1.py 一致逻辑）。

    每轮扫描：找到「至少有一个通道 < threshold」的最外层行/列，
    把图像裁剪到这个范围内。最多迭代 max_iter 轮，达不动则停。
    """
    for _ in range(max_iter):
        arr = np.array(img.convert("RGB"))
        h, w = arr.shape[:2]
        if h == 0 or w == 0:
            return img
        row_min = arr.min(axis=(1, 2))
        col_min = arr.min(axis=(0, 2))
        rows = np.where(row_min < threshold)[0]
        cols = np.where(col_min < threshold)[0]
        if len(rows) == 0 or len(cols) == 0:
            return img
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        x0, x1 = int(cols[0]), int(cols[-1]) + 1
        if y0 == 0 and y1 == h and x0 == 0 and x1 == w:
            break
        img = img.crop((x0, y0, x1, y1))
    return img


def center_crop_to_aspect(img: Image.Image, aspect: AspectRatio) -> Image.Image:
    """Center-crop `img` so its aspect equals `aspect`. No upscaling."""
    target = aspect.value
    cur = img.width / img.height
    if cur > target:
        new_w = int(img.height * target)
        x0 = (img.width - new_w) // 2
        return img.crop((x0, 0, x0 + new_w, img.height))
    if cur < target:
        new_h = int(img.width / target)
        y0 = (img.height - new_h) // 2
        return img.crop((0, y0, img.width, y0 + new_h))
    return img


def fit_to_cell(img: Image.Image, cell_w: int, cell_h: int,
                mode: ScaleMode) -> Image.Image:
    """Fit `img` into a `cell_w × cell_h` region per `mode`."""
    if mode == ScaleMode.STRETCH:
        return img.resize((cell_w, cell_h), Image.LANCZOS)
    if mode == ScaleMode.CROP:
        scale = max(cell_w / img.width, cell_h / img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        x0 = (new_w - cell_w) // 2
        y0 = (new_h - cell_h) // 2
        return resized.crop((x0, y0, x0 + cell_w, y0 + cell_h))
    # LETTERBOX
    scale = min(cell_w / img.width, cell_h / img.height, 1.0)
    new_w = int(img.width * scale)
    new_h = int(img.height * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)
