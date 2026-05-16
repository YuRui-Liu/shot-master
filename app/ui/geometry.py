"""拆图 overlay 红线坐标计算（纯函数，不依赖 Qt）。

坐标系：以显示图（display）左上为原点。
- 源网格线：solid（src_rows × src_cols 把内容区均分）
- 子分组线：dashed（每 sub_rows / sub_cols 个源格为一组的边界）
内容区 = 原图去掉四周 margin 后的区域；显示按 display/img 比例缩放。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GridLine:
    orientation: str  # "v" 竖线 | "h" 横线
    pos: float        # 显示坐标系下的 x（竖线）或 y（横线）
    style: str        # "solid" 源网格 | "dashed" 子分组


def tile_count(src_rows: int, src_cols: int,
               sub_rows: int, sub_cols: int) -> int:
    """切出的子图数量 = (src_rows/sub_rows) * (src_cols/sub_cols)。"""
    if src_rows % sub_rows != 0 or src_cols % sub_cols != 0:
        raise ValueError(
            f"子图 {sub_rows}×{sub_cols} 必须能整除源图 {src_rows}×{src_cols}")
    return (src_rows // sub_rows) * (src_cols // sub_cols)


def compute_grid_lines(img_w: int, img_h: int,
                       src_rows: int, src_cols: int,
                       sub_rows: int, sub_cols: int,
                       margin_top: int, margin_right: int,
                       margin_bottom: int, margin_left: int,
                       gap: int,
                       display_w: int, display_h: int) -> list[GridLine]:
    """返回所有红线（已换算到 display 坐标）。

    Raises:
        ValueError: 子网格不能整除源网格。
    """
    if src_rows % sub_rows != 0 or src_cols % sub_cols != 0:
        raise ValueError(
            f"子图 {sub_rows}×{sub_cols} 必须能整除源图 {src_rows}×{src_cols}")

    sx = display_w / img_w
    sy = display_h / img_h

    content_w = img_w - margin_left - margin_right
    content_h = img_h - margin_top - margin_bottom
    if content_w <= 0 or content_h <= 0:
        return []

    cell_w = content_w / src_cols
    cell_h = content_h / src_rows

    lines: list[GridLine] = []

    # 子分组边界：sub_cols > 1 时，每隔 sub_cols 列画一条 dashed；
    # sub_cols == 1 表示每格自成一组，无子分组边界，全部 solid。
    for i in range(1, src_cols):
        x_img = margin_left + i * cell_w
        is_sub_boundary = (sub_cols > 1) and (i % sub_cols == 0)
        style = "dashed" if is_sub_boundary else "solid"
        lines.append(GridLine("v", x_img * sx, style))

    for j in range(1, src_rows):
        y_img = margin_top + j * cell_h
        is_sub_boundary = (sub_rows > 1) and (j % sub_rows == 0)
        style = "dashed" if is_sub_boundary else "solid"
        lines.append(GridLine("h", y_img * sy, style))

    return lines
