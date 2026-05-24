"""shot-master 图像核心操作的薄封装层。

桌面 UI 直接调用这些函数（不经 HTTP），返回 PIL.Image 或落盘的 Path。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from shot_master.core.specs import GridSpec, Margins, AspectRatio, CombineSpec, ScaleMode
from shot_master.core.splitter import split_image
from shot_master.core.combiner import combine_images
from shot_master.core.aspect_ops import trim_white_edges, center_crop_to_aspect
from shot_master.core.saver import save_image


class ResampleAlgo(str, Enum):
    LANCZOS = "lanczos"
    AI = "ai"


@dataclass(frozen=True)
class ResampleSpec:
    """拆图重采样后处理规格。enabled=False 时其他字段被忽略。"""
    enabled: bool = False
    aspect_w: int = 0           # 0 = 跟随原图（与 aspect_h=0 同义 Auto）
    aspect_h: int = 0
    long_edge: int = 2048
    algorithm: ResampleAlgo = ResampleAlgo.LANCZOS
    ai_model: str = ""

    @property
    def is_auto_aspect(self) -> bool:
        return self.aspect_w == 0 or self.aspect_h == 0


# ---------- 拆图 ----------

def make_grid_spec(src_rows: int, src_cols: int,
                   sub_rows: int = 1, sub_cols: int = 1,
                   margin_top: int = 0, margin_right: int = 0,
                   margin_bottom: int = 0, margin_left: int = 0,
                   gap: int = 0) -> GridSpec:
    return GridSpec(
        src_rows=src_rows, src_cols=src_cols,
        sub_rows=sub_rows, sub_cols=sub_cols,
        margins=Margins(top=margin_top, right=margin_right,
                        bottom=margin_bottom, left=margin_left),
        gap=gap,
        target_aspect=AspectRatio.auto(),
    )


def split_to_tiles(src_path: Path, spec: GridSpec) -> list[Image.Image]:
    """拆图，返回 PIL.Image 列表（左→右上→下）。"""
    src = Image.open(src_path)
    return split_image(src, spec)


def split_to_files(src_path: Path, spec: GridSpec,
                   output_dir: Path,
                   name_prefix: Optional[str] = None,
                   output_format: str = "PNG") -> list[Path]:
    """拆图并落盘，返回保存路径列表。"""
    tiles = split_to_tiles(src_path, spec)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = name_prefix or src_path.stem
    fmt = output_format.upper()
    ext = ".png" if fmt == "PNG" else ".jpg"
    saved = []
    for i, tile in enumerate(tiles):
        p = output_dir / f"{prefix}_{i+1}{ext}"
        save_image(tile, p, fmt)
        saved.append(p)
    return saved


def split_to_preview_cache(src_path: Path, spec: GridSpec,
                           cache_root: Path) -> list[Path]:
    """把拆图结果缓存到 cache_root 下一个 hash 子目录，返回 tile 路径列表。
    用于反推前的人工预览确认。"""
    key = (f"{src_path}|{spec.src_rows}x{spec.src_cols}|"
           f"{spec.sub_rows}x{spec.sub_cols}|{spec.margins}|{spec.gap}")
    hsh = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    out_dir = cache_root / hsh
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清空旧 tile
    for old in out_dir.glob("tile_*.png"):
        old.unlink()
    tiles = split_to_tiles(src_path, spec)
    saved = []
    for i, tile in enumerate(tiles):
        p = out_dir / f"tile_{i}.png"
        save_image(tile, p, "PNG")
        saved.append(p)
    return saved


# ---------- 拼图 ----------

def combine_to_file(image_paths: list[Path],
                    output_path: Path,
                    target_rows: int, target_cols: int,
                    gap: int = 0,
                    scale_mode: str = "letterbox",
                    target_aspect_w: int = 0, target_aspect_h: int = 0,
                    bg: tuple[int, int, int, int] = (255, 255, 255, 255),
                    output_format: str = "PNG") -> Path:
    imgs = [Image.open(p) for p in image_paths]
    sm = {"letterbox": ScaleMode.LETTERBOX,
          "crop": ScaleMode.CROP,
          "stretch": ScaleMode.STRETCH}.get(scale_mode, ScaleMode.LETTERBOX)
    spec = CombineSpec(
        target_rows=target_rows, target_cols=target_cols,
        gap=gap,
        target_aspect=AspectRatio(target_aspect_w, target_aspect_h),
        scale_mode=sm,
    )
    merged = combine_images(imgs, spec, bg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(merged, output_path, output_format,
               bg=(bg[0], bg[1], bg[2]))
    return output_path


# ---------- 去白边 ----------

SUPPORTED_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def trim_one(src_path: Path, out_path: Path,
             threshold: int = 240, max_iter: int = 5,
             output_format: str = "PNG") -> Path:
    img = Image.open(src_path)
    trimmed = trim_white_edges(img, threshold=threshold, max_iter=max_iter)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(trimmed, out_path, output_format)
    return out_path


def trim_batch(src_folder: Path, out_folder: Path,
               threshold: int = 240, max_iter: int = 5,
               output_format: str = "PNG",
               name_suffix: str = "") -> list[Path]:
    out_folder.mkdir(parents=True, exist_ok=True)
    ext = ".png" if output_format.upper() == "PNG" else ".jpg"
    saved = []
    for p in sorted(src_folder.iterdir()):
        if p.suffix.lower() not in SUPPORTED_IMG_EXTS:
            continue
        out = out_folder / f"{p.stem}{name_suffix}{ext}"
        trim_one(p, out, threshold=threshold, max_iter=max_iter,
                 output_format=output_format)
        saved.append(out)
    return saved


# ---------- 重采样辅助 ----------

def resize_tile(tile: Image.Image,
                spec: ResampleSpec,
                upscaler: Optional["ComfyUIUpscaler"] = None,
                status_cb: Optional[Callable[[str], None]] = None,
                ) -> Image.Image:
    """重采样后处理：可选中心裁剪 + 选定算法缩放到 long_edge。

    spec.enabled=False 直接返回原图。
    spec.algorithm=AI 时尝试 ComfyUI 超分，失败回退 LANCZOS 并通过 status_cb 提示。
    最终都用 LANCZOS 把长边压/拉到 spec.long_edge（AI 输出通常 4× 需收尾）。
    """
    if not spec.enabled:
        return tile

    if not spec.is_auto_aspect:
        tile = center_crop_to_aspect(
            tile, AspectRatio(spec.aspect_w, spec.aspect_h))

    if spec.algorithm == ResampleAlgo.AI and upscaler is not None:
        # AI 分支在 Task 7 接入，目前未达此条件
        pass

    return _resize_to_long_edge(tile, spec.long_edge, Image.LANCZOS)


def _resize_to_long_edge(img: Image.Image, long_edge: int,
                          resample: Image.Resampling) -> Image.Image:
    """按 max(w,h)==long_edge 等比缩放。已经满足则返回同一对象。"""
    w, h = img.size
    if max(w, h) == long_edge:
        return img
    scale = long_edge / max(w, h)
    return img.resize((round(w * scale), round(h * scale)), resample)
