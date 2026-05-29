"""DawTrackView smoke: 构造 / 选中 / 拖动 / 边界 resize / 双击 / Shift rubber band."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue
from drama_shot_master.ui.widgets.daw.daw_track_view import DawTrackView
from drama_shot_master.ui.widgets.daw.selection import Selection, _CueRef


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _press(w, x, y, mod=Qt.NoModifier):
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(x, y),
                     Qt.LeftButton, Qt.LeftButton, mod)
    w.mousePressEvent(ev)


def _move(w, x, y, mod=Qt.NoModifier):
    ev = QMouseEvent(QMouseEvent.MouseMove, QPoint(x, y),
                     Qt.NoButton, Qt.LeftButton, mod)
    w.mouseMoveEvent(ev)


def _release(w, x, y, mod=Qt.NoModifier):
    ev = QMouseEvent(QMouseEvent.MouseButtonRelease, QPoint(x, y),
                     Qt.LeftButton, Qt.NoButton, mod)
    w.mouseReleaseEvent(ev)


def test_construct(app):
    w = DawTrackView(Selection())
    assert w.minimumHeight() > 100


def test_set_cues_and_paint(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "末日", 0)])
    w.grab()    # paintEvent 不崩


def test_set_zoom_and_scroll(app):
    w = DawTrackView(Selection())
    w.set_zoom(2.0)
    w.set_scroll_offset(0.3)
    assert w._zoom == 2.0
    assert w._scroll_offset == 0.3


def test_click_on_cue_emits_cueClicked(app):
    sel = Selection()
    w = DawTrackView(sel)
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "末日", 0)])
    received = []
    w.cueClicked.connect(lambda r, m: received.append((r, m)))
    # BGM 轨 y ≈ axis(14) + video(36) + gap(2) + bgm 中段(20) ≈ 72
    # cue x ≈ label(60) + (800-60)*(0~10/30) = 60..306; 点 200 在 cue 内
    _press(w, 200, 72)
    assert len(received) == 1
    assert received[0][0].track == "bgm"
    assert received[0][0].seg_index == 0


def test_ctrl_click_on_cue_modifier_pass_through(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    received = []
    w.cueClicked.connect(lambda r, m: received.append(m))
    _press(w, 200, 72, Qt.ControlModifier)
    assert received and (received[0] & Qt.ControlModifier)


def test_shift_drag_creates_rubber_band(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    released = []
    w.rubberBandReleased.connect(lambda rect, mod: released.append(rect))
    # Shift+drag 起在空白处（最底部）
    _press(w, 400, 200, Qt.ShiftModifier)
    _move(w, 500, 250, Qt.ShiftModifier)
    _release(w, 500, 250, Qt.ShiftModifier)
    assert len(released) == 1


def test_drag_cue_center_emits_MoveCue_on_release(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    cmds = []
    w.dragCommandIssued.connect(lambda c: cmds.append(c))
    # 在 cue 中心拖：200,72 → 280,72
    _press(w, 200, 72)
    _move(w, 280, 72)
    _release(w, 280, 72)
    from drama_shot_master.ui.widgets.daw.commands import MoveCue
    assert len(cmds) == 1
    assert isinstance(cmds[0], MoveCue)


def test_resize_at_cue_boundary_emits_ResizeCue(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    # cue [0, 10s]: 60 → 60 + 740*10/30 ≈ 60 + 247 = 307
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    cmds = []
    w.dragCommandIssued.connect(lambda c: cmds.append(c))
    _press(w, 307, 72)         # 在 end 边界 ±4px
    _move(w, 350, 72)
    _release(w, 350, 72)
    from drama_shot_master.ui.widgets.daw.commands import ResizeCue
    assert len(cmds) == 1
    assert isinstance(cmds[0], ResizeCue)
    assert cmds[0].side == "end"


def test_double_click_emits_cueDoubleClicked(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    received = []
    w.cueDoubleClicked.connect(lambda r: received.append(r))
    ev = QMouseEvent(QMouseEvent.MouseButtonDblClick, QPoint(200, 72),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    w.mouseDoubleClickEvent(ev)
    assert len(received) == 1


def test_cross_track_drag_limited_to_origin_track(app):
    """BGM cue 拖到 SFX 轨 y 范围应仍认为是 BGM 轨内移动。"""
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    cmds = []
    w.dragCommandIssued.connect(lambda c: cmds.append(c))
    _press(w, 200, 72)
    _move(w, 280, 112)      # 鼠标拖到 SFX 轨 y
    _release(w, 280, 112)
    if cmds:
        for r in cmds[0].refs:
            assert r.track == "bgm"


def test_selection_paint_updates(app):
    sel = Selection()
    w = DawTrackView(sel)
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    sel.set([_CueRef("bgm", 0)])
    w.grab()


def test_playhead_drag_on_empty_track(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    received = []
    w.playheadDragged.connect(lambda t: received.append(t))
    # 在最底（无 cue 的空白处）
    _press(w, 400, 250)
    _move(w, 500, 250)
    _release(w, 500, 250)
    assert len(received) >= 1
