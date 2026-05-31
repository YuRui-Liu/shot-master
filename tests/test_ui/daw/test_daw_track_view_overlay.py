"""DawTrackView overlay 扩展 smoke + 纯逻辑：动态高度 / hit-test / 折叠头+片段信号。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.daw.daw_track_view import DawTrackView, _FIXED_H
from drama_shot_master.ui.widgets.daw.selection import Selection
from drama_shot_master.ui.widgets.daw.overlay_layout import _OV_HEAD_H, _OV_LANE_H


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _seg(sid, kind, lane, t0, t1):
    return SimpleNamespace(id=sid, kind=kind, lane=lane, t_start=t0, t_end=t1)


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
