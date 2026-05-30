"""VideoPreviewWidget.playingChanged：播放状态变化时 emit bool。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_has_playing_changed_signal(app):
    assert hasattr(VideoPreviewWidget, "playingChanged")


def test_state_change_emits_playing_changed(app):
    w = VideoPreviewWidget()
    got = []
    w.playingChanged.connect(got.append)
    # 直接调状态回调（不依赖真实音视频后端）
    w._on_state_changed(None)   # 无 player → is_playing False
    assert got == [False]
