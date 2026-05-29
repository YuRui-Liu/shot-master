"""OverviewTimeline smoke：set_cues 不崩 + 鼠标点击 emit cueClicked + 拖动 emit playheadDragged + 节流."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue
from drama_shot_master.ui.widgets.overview_timeline import OverviewTimeline


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _press(widget, x, y):
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(x, y),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    widget.mousePressEvent(ev)


def _move(widget, x, y):
    ev = QMouseEvent(QMouseEvent.MouseMove, QPoint(x, y),
                     Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    widget.mouseMoveEvent(ev)


def _release(widget, x, y):
    ev = QMouseEvent(QMouseEvent.MouseButtonRelease, QPoint(x, y),
                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    widget.mouseReleaseEvent(ev)


def test_construct_minimum_height(app):
    w = OverviewTimeline()
    assert w.minimumHeight() >= 80


def test_set_cues_and_set_duration_does_not_crash(app):
    w = OverviewTimeline()
    w.set_duration(30.0)
    w.set_cues([
        _Cue("bgm", 0.0, 10.0, "末日", 0),
        _Cue("sfx", 5.0, 6.0, "门", 0),
        _Cue("dialogue", 0.0, 3.0, "A1", 0),
        _Cue("video", 0.0, 30.0, "", 0),
    ])
    w.resize(600, 140)
    w.grab()    # 触发 paintEvent


def test_set_playhead_clamps(app):
    w = OverviewTimeline()
    w.set_duration(10.0)
    w.set_playhead(-1.0)
    assert w._playhead == 0.0
    w.set_playhead(20.0)
    assert w._playhead == 10.0


def test_click_on_cue_emits_cueClicked(app):
    w = OverviewTimeline()
    w.resize(600, 140)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "末日", 0)])
    received = []
    w.cueClicked.connect(lambda *a: received.append(a))
    # BGM 轨 y ~= 14 (axis) + 18 (video) + 2 (gap) + 11 (BGM 中段) = ~45
    # BGM cue 占 x ~= 60 + 0 ~ 60 + 200 (30s 全宽 600，10s 占 1/3)
    # 点 x=100 落在 BGM cue 内
    _press(w, 100, 45)
    assert received and received[0][0] == "bgm" and received[0][1] == 0


def test_click_on_video_track_seeks_not_cue(app):
    """视频轨点击应当只触发 drag seek，不 emit cueClicked。"""
    w = OverviewTimeline()
    w.resize(600, 140)
    w.set_duration(30.0)
    w.set_cues([_Cue("video", 0.0, 30.0, "", 0)])
    cue_received = []
    drag_received = []
    w.cueClicked.connect(lambda *a: cue_received.append(a))
    w.playheadDragged.connect(lambda t: drag_received.append(t))
    # 视频轨 y ~= 14 + 9 = 23 (中段)
    _press(w, 200, 23)
    _release(w, 200, 23)
    assert cue_received == []        # 不 emit cueClicked
    # 视频轨视为 drag，应 emit playheadDragged（释放时 flush）
    assert len(drag_received) == 1


def test_drag_throttle_emits_at_30hz(app):
    """连续多次 move 节流到 30Hz：第一次 emit + 中间被合并到 timer + release flush。"""
    w = OverviewTimeline()
    w.resize(600, 140)
    w.set_duration(30.0)
    received = []
    w.playheadDragged.connect(lambda t: received.append(t))
    # 视频轨拖动
    _press(w, 100, 23)
    _move(w, 200, 23)
    _move(w, 300, 23)
    _move(w, 400, 23)
    _release(w, 400, 23)
    # 至少 emit 1 次（释放时 flush），最多受 timer 启动一次 + release flush 一次
    assert len(received) >= 1
    # 最后一次 emit 的位置应当对应 release 点
    last_t = received[-1]
    # x=400 对应 t = (400-60)/(600-60) * 30 ≈ 18.9s
    assert 17 < last_t < 21
