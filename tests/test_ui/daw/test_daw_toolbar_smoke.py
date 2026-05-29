"""DawToolbar smoke."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.undo_stack import UndoStack
from drama_shot_master.ui.widgets.daw.daw_toolbar import DawToolbar


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct_and_widgets_exist(app):
    tb = DawToolbar(UndoStack())
    for attr in ("btn_play", "time_label", "btn_zoom_in", "btn_zoom_out",
                 "zoom_slider", "btn_fit", "btn_undo", "btn_redo",
                 "btn_config"):
        assert hasattr(tb, attr), f"missing {attr}"


def test_play_button_emits(app):
    tb = DawToolbar(UndoStack())
    received = []
    tb.playPauseRequested.connect(lambda: received.append(True))
    tb.btn_play.click()
    assert received == [True]


def test_config_button_emits(app):
    tb = DawToolbar(UndoStack())
    received = []
    tb.configRequested.connect(lambda: received.append(True))
    tb.btn_config.click()
    assert received == [True]


def test_undo_redo_button_state_from_stack(app):
    stk = UndoStack()
    tb = DawToolbar(stk)
    # 初始 stack 空 → 按钮 disabled
    assert tb.btn_undo.isEnabled() is False
    assert tb.btn_redo.isEnabled() is False
    # 模拟 stack 信号
    stk.canUndoChanged.emit(True)
    assert tb.btn_undo.isEnabled() is True
