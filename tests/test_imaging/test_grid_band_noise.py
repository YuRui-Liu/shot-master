"""回归：1px 噪声白带不应被当成网格分隔线。

复现真实图 img_20260530_181822_1.png 的故障：紧贴左边距有一条 1px 宽的白条，
导致 (a) infer_grid 把 2x2 误判为 2x3；(b) 强制 2x2 拆图时切出 1px 宽 cell，
下游 resize 抛 `ValueError: height and width must be > 0`。
"""
import numpy as np
from PIL import Image

from drama_shot_master.imaging.border_detector import find_cell_boxes, infer_grid
from drama_shot_master.grid_ops import make_grid_spec
from drama_shot_master.imaging.splitter import split_image


def _noisy_2x2() -> Image.Image:
    """200x120 的 2x2 网格：左边距(0-9) 后有 1px 噪声白条(列 11)。

    复刻真实 v_bands = [(0,33),(34,35),(1409,1427),(2816,2848)] 的 (34,35) 噪声。
    """
    W, H = 200, 120
    arr = np.full((H, W, 3), 100, np.uint8)        # 灰底=非白内容
    for s, e in [(0, 10), (11, 12), (96, 104), (190, 200)]:  # 竖白带（含 1px 噪声）
        arr[:, s:e, :] = 255
    for s, e in [(0, 8), (56, 64)]:                 # 横白带（顶边 + 中缝，无底边）
        arr[s:e, :, :] = 255
    return Image.fromarray(arr, "RGB")


def test_infer_grid_ignores_1px_noise_band():
    """1px 噪声白带不计入网格 → 2x2 不被误判为 2x3。"""
    assert infer_grid(_noisy_2x2()) == (2, 2)


def test_find_cell_boxes_no_degenerate_cell():
    """强制 2x2 时不应切出 <2px 的退化 cell。"""
    boxes, _mode = find_cell_boxes(_noisy_2x2(), 2, 2)
    assert len(boxes) == 4
    for (l, t, r, b) in boxes:
        assert r - l >= 2 and b - t >= 2, f"退化 cell: ({l},{t},{r},{b})"


def test_split_2x2_does_not_raise(tmp_path):
    """端到端：强制 2x2 拆图不再抛 ValueError，产出 4 张非空子图。"""
    p = tmp_path / "noisy.png"
    _noisy_2x2().save(p)
    spec = make_grid_spec(2, 2, 1, 1)
    tiles = split_image(Image.open(p), spec)
    assert len(tiles) == 4
    for t in tiles:
        assert t.width >= 1 and t.height >= 1
