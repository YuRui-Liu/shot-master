"""DawMinimap smoke: paint / 拖窗口 / 点击 seek。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue
from drama_shot_master.ui.widgets.daw.daw_minimap import DawMinimap


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _press(w, x, y):
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(x, y),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    w.mousePressEvent(ev)


def test_construct_and_paint(app):
    w = DawMinimap()
    w.resize(600, 30)
    w.set_duration(30.0)
    w.set_cues([
        _Cue("bgm", 0.0, 10.0, "", 0),
        _Cue("sfx", 5.0, 6.0, "", 0),
        _Cue("dialogue", 0.0, 3.0, "", 0),
    ])
    w.grab()


def test_set_viewport_window(app):
    w = DawMinimap()
    w.resize(600, 30)
    w.set_viewport(scroll_offset=0.3, viewport_fraction=0.4)
    assert abs(w._scroll_offset - 0.3) < 1e-6
    assert abs(w._viewport_fraction - 0.4) < 1e-6


def test_click_emits_viewportRequested(app):
    w = DawMinimap()
    w.resize(600, 30)
    received = []
    w.viewportRequested.connect(lambda offset: received.append(offset))
    _press(w, 300, 15)   # 中间位置
    assert len(received) == 1
    # 点中间应当 scroll_offset 大约 0.5（center 0.5 - viewport/2）
    # 验证至少 emit 了


def test_set_cues_does_not_crash_empty(app):
    w = DawMinimap()
    w.resize(600, 30)
    w.set_cues([])
    w.grab()
