"""VideoPreviewWidget.set_volume/set_muted：懒建前后都生效。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_set_volume_before_player_no_crash(app):
    w = VideoPreviewWidget()
    w.set_volume(0.5)
    assert w._pending_volume == 0.5


def test_set_muted_before_player_no_crash(app):
    w = VideoPreviewWidget()
    w.set_muted(True)
    assert w._pending_muted is True


def test_volume_applied_after_player_built(app, tmp_path):
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"x")
    w = VideoPreviewWidget()
    w.set_volume(0.3)
    w.set_muted(True)
    w.set_source(str(mp4))
    assert w._audio.volume() == pytest.approx(0.3, abs=0.01)
    assert w._audio.isMuted() is True
