"""White-band detection (numpy-based) and cell-box localization.

主算法借鉴 scripts/split_16_to_4.py：扫描连续白色行/列形成「白带」(bands)，
用白带间的内容区间作为 cell 边界——这种方法对不均匀间距/外边距天然鲁棒。

`detect_borders` 仍保留作为 UI 提示用途；`find_cell_boxes` 是 splitter 实际调用的接口。
"""
from collections import Counter
import numpy as np
from PIL import Image
from .specs import Margins

# 网格分隔线（白带）的最小厚度（像素）。比这更薄的白带视为抗锯齿/JPEG
# 噪声——不是真实的行/列分隔线，否则会把 1px 白条误当分隔线，导致
# 网格误判（2x2→2x3）和切出退化 cell（下游 resize 抛 ValueError）。
_MIN_GRID_BAND = 3


def _grid_bands(bands: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """仅保留厚度 >= _MIN_GRID_BAND 的白带，滤掉亚像素噪声条。"""
    return [b for b in bands if b[1] - b[0] >= _MIN_GRID_BAND]


def detect_white_bands(arr: np.ndarray, axis: int,
                       white_threshold: int = 240,
                       min_ratio: float = 0.95) -> list[tuple[int, int]]:
    """检测连续白色行/列带（band），返回 [(start, end), ...]。

    Args:
        arr: H×W×C numpy 数组（C ≥ 3，只看前 3 个通道）。
        axis: 0 → 水平带（每行的白比例）；1 → 垂直带（每列的白比例）。
        white_threshold: 像素三个通道都 > 该值才算白（0-255）。
        min_ratio: 行/列中至少这个比例的像素满足「白」，该行/列才算「白线」。

    Returns:
        [(start, end), ...] 闭开区间，长度即 end - start。
    """
    rgb = arr[:, :, :3] if arr.shape[2] >= 3 else arr
    is_white = np.all(rgb > white_threshold, axis=2)
    if axis == 0:
        white_ratio = is_white.mean(axis=1)
    else:
        white_ratio = is_white.mean(axis=0)
    is_border = white_ratio > min_ratio

    bands: list[tuple[int, int]] = []
    in_band = False
    start = 0
    for i, b in enumerate(is_border):
        if b and not in_band:
            start, in_band = i, True
        elif not b and in_band:
            bands.append((start, i))
            in_band = False
    if in_band:
        bands.append((start, len(is_border)))
    return bands


def find_cell_boxes(
    img: Image.Image,
    n_rows: int,
    n_cols: int,
    white_threshold: int = 240,
    min_ratio: float = 0.95,
    uniform_outer: int = 30,
    uniform_border: int = 25,
) -> tuple[list[tuple[int, int, int, int]], str]:
    """返回 n_rows×n_cols 个 cell 的 (left, top, right, bottom)，row-major。

    主路径：用白带定位（与参考脚本一致）。
    Fallback：白带数量不足时按 uniform(outer, border) 等分。

    Returns:
        (boxes, mode) — mode 是 "bands" 或 "uniform"。
    """
    W, H = img.size
    rgb_img = img.convert("RGB") if img.mode != "RGB" else img
    arr = np.array(rgb_img)

    v_bands = _grid_bands(sorted(detect_white_bands(
        arr, axis=1, white_threshold=white_threshold, min_ratio=min_ratio)))
    h_bands = _grid_bands(sorted(detect_white_bands(
        arr, axis=0, white_threshold=white_threshold, min_ratio=min_ratio)))

    # 合成「虚拟边缘带」：若内容紧贴图像边界（首/末像素非白），
    # 视为存在 0 宽度的边带，使得「内部 n-1 条 + 2 条虚拟边」凑齐 n+1。
    if not v_bands or v_bands[0][0] > 0:
        v_bands = [(0, 0)] + v_bands
    if v_bands and v_bands[-1][1] < W:
        v_bands = v_bands + [(W, W)]
    if not h_bands or h_bands[0][0] > 0:
        h_bands = [(0, 0)] + h_bands
    if h_bands and h_bands[-1][1] < H:
        h_bands = h_bands + [(H, H)]

    if len(v_bands) >= n_cols + 1 and len(h_bands) >= n_rows + 1:
        v_bands = v_bands[: n_cols + 1]
        h_bands = h_bands[: n_rows + 1]
        boxes: list[tuple[int, int, int, int]] = []
        for r in range(n_rows):
            top = h_bands[r][1]
            bottom = h_bands[r + 1][0]
            for c in range(n_cols):
                left = v_bands[c][1]
                right = v_bands[c + 1][0]
                boxes.append((left, top, right, bottom))
        return boxes, "bands"

    return _uniform_boxes(W, H, n_rows, n_cols,
                          outer=uniform_outer, border=uniform_border), "uniform"


def _uniform_boxes(W: int, H: int, n_rows: int, n_cols: int,
                   outer: int, border: int) -> list[tuple[int, int, int, int]]:
    """Pure equal-split fallback (与参考脚本 uniform 分支语义一致)."""
    cell_w = (W - 2 * outer - (n_cols - 1) * border) / n_cols
    cell_h = (H - 2 * outer - (n_rows - 1) * border) / n_rows
    out: list[tuple[int, int, int, int]] = []
    for r in range(n_rows):
        for c in range(n_cols):
            left = int(outer + c * (cell_w + border))
            top = int(outer + r * (cell_h + border))
            out.append((left, top, int(left + cell_w), int(top + cell_h)))
    return out


def infer_grid(
    src: Image.Image,
    white_threshold: int = 240,
    min_white_ratio: float = 0.95,
) -> tuple[int, int]:
    """从白带数量推断网格 (rows, cols)。

    规则：
    - 内部水平白带 N 条 → rows = N + 1（每两条内部带之间是一行）
    - 内部垂直白带 N 条 → cols = N + 1
    - 没有任何白带 → (1, 1)
    """
    if src.mode != "RGB":
        src = src.convert("RGB")
    arr = np.array(src)
    W, H = src.width, src.height

    h_bands = sorted(detect_white_bands(arr, axis=0,
                                         white_threshold=white_threshold,
                                         min_ratio=min_white_ratio))
    v_bands = sorted(detect_white_bands(arr, axis=1,
                                         white_threshold=white_threshold,
                                         min_ratio=min_white_ratio))

    inner_h = _grid_bands([b for b in h_bands if b[0] > 0 and b[1] < H])
    inner_v = _grid_bands([b for b in v_bands if b[0] > 0 and b[1] < W])
    rows = max(1, len(inner_h) + 1)
    cols = max(1, len(inner_v) + 1)
    return rows, cols


def detect_borders(
    src: Image.Image,
    white_threshold: int = 240,
    min_white_ratio: float = 0.95,
) -> tuple[Margins, int]:
    """检测外边距 + 估算 cell 间距。用于 UI 填表单。

    内部用 numpy 白带算法。返回的 margins/gap 仅作参考显示——
    splitter 不依赖这两个值（直接走 bands）。
    """
    if src.mode != "RGB":
        src = src.convert("RGB")
    arr = np.array(src)
    W, H = src.width, src.height

    h_bands = sorted(detect_white_bands(arr, axis=0,
                                         white_threshold=white_threshold,
                                         min_ratio=min_white_ratio))
    v_bands = sorted(detect_white_bands(arr, axis=1,
                                         white_threshold=white_threshold,
                                         min_ratio=min_white_ratio))

    top = h_bands[0][1] if h_bands and h_bands[0][0] == 0 else 0
    bottom = (H - h_bands[-1][0]) if h_bands and h_bands[-1][1] == H else 0
    left = v_bands[0][1] if v_bands and v_bands[0][0] == 0 else 0
    right = (W - v_bands[-1][0]) if v_bands and v_bands[-1][1] == W else 0

    # 退化：图全白
    if top + bottom >= H or left + right >= W:
        return Margins(0, 0, 0, 0), 0

    # gap = 中间白带的众数（不含贴边的外缘）
    inner_h_bands = [b for b in h_bands
                     if b[0] != 0 and b[1] != H]
    inner_v_bands = [b for b in v_bands
                     if b[0] != 0 and b[1] != W]
    widths = [b[1] - b[0] for b in inner_h_bands + inner_v_bands if b[1] - b[0] >= 2]

    if not widths:
        return Margins(top, right, bottom, left), 0

    counter = Counter(widths)
    mode, mode_freq = counter.most_common(1)[0]
    if mode_freq / len(widths) < 0.6:
        return Margins(top, right, bottom, left), 0
    return Margins(top, right, bottom, left), mode
