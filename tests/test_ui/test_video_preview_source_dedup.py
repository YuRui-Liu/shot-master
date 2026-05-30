"""VideoPreviewWidget：同源 set_source 去重（不打断播放）+ position() getter。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_position_returns_zero_without_player(app):
    w = VideoPreviewWidget()
    assert w.position() == 0.0


def test_set_source_same_path_skips_reload(app, tmp_path):
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"x")
    w = VideoPreviewWidget()
    w.set_source(str(mp4))
    calls = []
    # 截获底层 setSource，验证同源第二次不再调用（不 stop 打断播放）
    w._player.setSource = lambda url: calls.append(url)
    w._player.stop = lambda: calls.append("STOP")
    w.set_source(str(mp4))
    assert calls == []


def test_set_source_different_path_reloads(app, tmp_path):
    a = tmp_path / "a.mp4"; a.write_bytes(b"x")
    b = tmp_path / "b.mp4"; b.write_bytes(b"x")
    w = VideoPreviewWidget()
    w.set_source(str(a))
    calls = []
    w._player.setSource = lambda url: calls.append("SET")
    w.set_source(str(b))
    assert "SET" in calls
