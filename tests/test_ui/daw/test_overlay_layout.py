"""overlay_layout 纯函数单测：行布局/lane 计数（无 Qt）。"""
from types import SimpleNamespace

from drama_shot_master.ui.widgets.daw.overlay_layout import (
    OverlayRow,
    overlay_rows,
    lane_count,
    lanes_of,
    _OV_LANE_H,
    _OV_HEAD_H,
    _OV_KIND_ORDER,
)


def _seg(kind, lane, t_start, t_end=0.0):
    return SimpleNamespace(kind=kind, lane=lane, t_start=t_start, t_end=t_end)


def test_consts():
    assert _OV_LANE_H == 28
    assert _OV_HEAD_H == 18
    assert _OV_KIND_ORDER == ["bgm", "sfx"]


def test_empty():
    rows, region_h = overlay_rows([], base_y=0, collapsed=False)
    assert rows == []
    assert region_h == 0
    assert lane_count([]) == 0


def test_2bgm_1sfx_order_y_region():
    segs = [
        _seg("bgm", 0, 1.0),
        _seg("bgm", 1, 2.0),
        _seg("sfx", 0, 3.0),
    ]
    rows, region_h = overlay_rows(segs, base_y=0, collapsed=False)
    assert len(rows) == 3
    assert [(r.kind, r.lane) for r in rows] == [("bgm", 0), ("bgm", 1), ("sfx", 0)]
    # y 从 base_y + _OV_HEAD_H 起逐行 +_OV_LANE_H
    assert [r.y for r in rows] == [
        _OV_HEAD_H,
        _OV_HEAD_H + _OV_LANE_H,
        _OV_HEAD_H + 2 * _OV_LANE_H,
    ]
    assert region_h == _OV_HEAD_H + 3 * _OV_LANE_H


def test_base_y_offset():
    segs = [_seg("bgm", 0, 1.0)]
    rows, _ = overlay_rows(segs, base_y=100, collapsed=False)
    assert rows[0].y == 100 + _OV_HEAD_H


def test_collapsed_nonempty():
    segs = [_seg("bgm", 0, 1.0)]
    rows, region_h = overlay_rows(segs, base_y=0, collapsed=True)
    assert rows == []
    assert region_h == _OV_HEAD_H


def test_same_lane_multi_seg_grouped_sorted():
    segs = [
        _seg("bgm", 0, 5.0),
        _seg("bgm", 0, 1.0),
        _seg("bgm", 0, 3.0),
    ]
    rows, _ = overlay_rows(segs, base_y=0, collapsed=False)
    assert len(rows) == 1
    assert [s.t_start for s in rows[0].segments] == [1.0, 3.0, 5.0]


def test_lanes_of_and_lane_count():
    segs = [
        _seg("bgm", 0, 1.0),
        _seg("bgm", 1, 2.0),
        _seg("sfx", 0, 3.0),
    ]
    assert lanes_of(segs, "bgm") == 2
    assert lanes_of(segs, "sfx") == 1
    assert lane_count(segs) == 3


def test_overlay_row_dataclass():
    r = OverlayRow(kind="bgm", lane=0, y=18, segments=[])
    assert r.kind == "bgm"
    assert r.lane == 0
    assert r.y == 18
    assert r.segments == []
