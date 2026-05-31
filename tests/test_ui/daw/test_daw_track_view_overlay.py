"""DawTrackView overlay 扩展 smoke + 纯逻辑：动态高度 / hit-test / 折叠头+片段信号。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.daw.daw_track_view import (
    DawTrackView, _FIXED_H, _overlay_block_style,
)
from drama_shot_master.ui.widgets.daw.selection import Selection
from drama_shot_master.ui.widgets.daw.overlay_layout import _OV_HEAD_H, _OV_LANE_H


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _seg(sid, kind, lane, t0, t1, status="generated"):
    return SimpleNamespace(id=sid, kind=kind, lane=lane,
                           t_start=t0, t_end=t1, status=status)


def _segs_2bgm_1sfx():
    return [
        _seg("b0", "bgm", 0, 0.0, 10.0),
        _seg("b1", "bgm", 1, 5.0, 15.0),
        _seg("s0", "sfx", 0, 2.0, 4.0),
    ]


def _press(w, x, y, mod=Qt.NoModifier):
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(x, y),
                     Qt.LeftButton, Qt.LeftButton, mod)
    w.mousePressEvent(ev)


# ── 动态高度 ────────────────────────────────────────────────────────

def test_set_overlay_nonempty_increases_min_height(app):
    w = DawTrackView(Selection())
    base = w.minimumHeight()
    assert base == _FIXED_H
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    assert w.minimumHeight() > base
    assert w.minimumHeight() == _FIXED_H + _OV_HEAD_H + 3 * _OV_LANE_H


def test_set_overlay_collapsed_falls_back_to_head_only(app):
    w = DawTrackView(Selection())
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=True)
    assert w.minimumHeight() == _FIXED_H + _OV_HEAD_H


def test_set_overlay_empty_equals_fixed_region(app):
    w = DawTrackView(Selection())
    w.set_overlay([], collapsed=False)
    assert w.minimumHeight() == _FIXED_H


def test_set_overlay_paints_without_crash(app):
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    w.grab()


# ── _overlay_seg_at 纯逻辑 ──────────────────────────────────────────

def test_overlay_seg_at_hits_segment(app):
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    # bgm lane0 行 y = _FIXED_H + _OV_HEAD_H (行中段)
    row_y = _FIXED_H + _OV_HEAD_H + _OV_LANE_H // 2
    # seg b0 [0,10s] -> x 中段约 100
    x = int(w._t_to_x(3.0))
    assert w._overlay_seg_at(x, row_y) == "b0"


def test_overlay_seg_at_miss_on_head(app):
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    # 折叠头 y 在 _FIXED_H .. _FIXED_H+_OV_HEAD_H
    assert w._overlay_seg_at(100, _FIXED_H + 2) is None


def test_overlay_seg_at_miss_on_blank(app):
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    row_y = _FIXED_H + _OV_HEAD_H + _OV_LANE_H // 2
    # x 在所有片段之外（duration 末端）
    x = int(w._t_to_x(29.0))
    assert w._overlay_seg_at(x, row_y) is None


# ── 点击信号 ────────────────────────────────────────────────────────

def test_click_collapse_head_emits_toggle(app):
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    fired = []
    w.overlayCollapseToggled.connect(lambda: fired.append(True))
    _press(w, 100, _FIXED_H + 2)
    assert len(fired) == 1


def test_click_overlay_segment_emits_clicked(app):
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    got = []
    w.overlaySegmentClicked.connect(lambda sid, mod: got.append((sid, mod)))
    row_y = _FIXED_H + _OV_HEAD_H + _OV_LANE_H // 2
    x = int(w._t_to_x(3.0))
    _press(w, x, row_y, Qt.ControlModifier)
    assert len(got) == 1
    assert got[0][0] == "b0"
    assert got[0][1] & Qt.ControlModifier


def test_click_blank_overlay_area_swallowed(app):
    """空白叠加区点击不应触发 playhead 拖拽。"""
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    w.set_overlay(_segs_2bgm_1sfx(), collapsed=False)
    ph = []
    w.playheadDragged.connect(lambda t: ph.append(t))
    row_y = _FIXED_H + _OV_HEAD_H + _OV_LANE_H // 2
    x = int(w._t_to_x(29.0))
    _press(w, x, row_y)
    assert ph == []
    assert w._mode is None


# ── 按 status 上色（D6） ────────────────────────────────────────────

def test_overlay_block_style_three_states_differ():
    """三态各产出不同的（颜色/样式, 文案前缀）。"""
    gen = _overlay_block_style("generated")
    ing = _overlay_block_style("generating")
    fail = _overlay_block_style("failed")
    # 前缀各不相同
    prefixes = {gen[1], ing[1], fail[1]}
    assert len(prefixes) == 3
    # generating / failed 带状态标记前缀，generated 不带
    assert gen[1] == ""
    assert ing[1].startswith("⟳")
    assert fail[1].startswith("✕")


def test_overlay_block_style_failed_is_reddish():
    """失败态用偏红色调，与 generated 区分。"""
    _, _ = _overlay_block_style("generated")
    fail_color, _ = _overlay_block_style("failed")
    # 红分量明显大于绿/蓝
    assert fail_color.red() > fail_color.green()
    assert fail_color.red() > fail_color.blue()


def test_overlay_block_style_unknown_status_falls_back_to_generated():
    """未知 status 兜底走 generated（无前缀）。"""
    assert _overlay_block_style("whatever") == _overlay_block_style("generated")


def test_set_overlay_three_status_paints_without_crash(app):
    """generating/failed/generated 三态混合 → set_overlay + grab 不崩。"""
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    segs = [
        _seg("b0", "bgm", 0, 0.0, 10.0, status="generated"),
        _seg("b1", "bgm", 1, 5.0, 15.0, status="generating"),
        _seg("s0", "sfx", 0, 2.0, 4.0, status="failed"),
    ]
    w.set_overlay(segs, collapsed=False)
    w.grab()


def test_set_overlay_segment_without_status_defaults_generated(app):
    """无 status 属性的 segment（旧数据）→ getattr 兜底 generated，不崩。"""
    w = DawTrackView(Selection())
    w.resize(800, 400)
    w.set_duration(30.0)
    seg = SimpleNamespace(id="x", kind="bgm", lane=0, t_start=0.0, t_end=5.0)
    w.set_overlay([seg], collapsed=False)
    w.grab()
