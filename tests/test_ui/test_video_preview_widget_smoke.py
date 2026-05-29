"""VideoPreviewWidget smoke：构造不崩 + set_source 路径校验 + seek 节流 + 状态机."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct_does_not_crash(app):
    w = VideoPreviewWidget()
    assert w.duration() == 0.0
    assert w.is_playing() is False


def test_set_source_nonexistent_does_not_raise(app, tmp_path):
    w = VideoPreviewWidget()
    w.set_source(str(tmp_path / "nope.mp4"))
    w.set_source(None)
    w.set_source("")
    assert w.is_playing() is False


def test_seek_throttles(app, tmp_path, monkeypatch):
    """连续调 seek 应只触发 1 次 timer.start（节流）。"""
    w = VideoPreviewWidget()
    w._ensure_player()
    starts = {"n": 0}
    orig_start = w._seek_timer.start
    def fake_start(*a, **kw):
        starts["n"] += 1
        return orig_start(*a, **kw)
    monkeypatch.setattr(w._seek_timer, "start", fake_start)
    w.seek(1.0); w.seek(2.0); w.seek(3.0)
    assert starts["n"] == 1


def test_play_pause_no_player_returns_silently(app):
    w = VideoPreviewWidget()
    w.play()
    w.pause()
    assert w.is_playing() is False


def test_position_changed_signal_emitted(app):
    """模拟 player.positionChanged → widget 应 emit positionChanged(秒)."""
    w = VideoPreviewWidget()
    w._ensure_player()
    received = []
    w.positionChanged.connect(lambda t: received.append(t))
    w._on_position_changed(2500)        # ms
    assert len(received) == 1
    assert abs(received[0] - 2.5) < 1e-6
