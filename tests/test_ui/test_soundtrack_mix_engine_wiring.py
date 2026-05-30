"""SoundtrackEditor 实时混音引擎接线：引擎存在 + position 驱动 set_playhead + overlay 载入。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _ed(tmp_path):
    mp4 = tmp_path / "raw.mp4"; mp4.write_bytes(b"x")
    return SoundtrackEditor({"id": "t1", "name": "t", "mp4": str(mp4),
                             "style": "x", "output_dir": str(tmp_path)},
                            _cfg(tmp_path), tmp_path)


def test_engine_exists(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._mix_engine is not None
    assert ed._mix_output is not None


def test_position_changed_drives_playhead(tmp_path):
    _app()
    ed = _ed(tmp_path)
    seen = []
    ed._mix_engine.set_playhead = lambda t: seen.append(t)
    ed._on_video_position_changed(3.5)
    assert 3.5 in seen


def test_playing_changed_plays_engine(tmp_path):
    _app()
    ed = _ed(tmp_path)
    calls = []
    ed._mix_engine.play = lambda: calls.append("play")
    ed._mix_engine.pause = lambda: calls.append("pause")
    ed._mix_output.start = lambda: calls.append("start")
    ed._on_video_playing_changed(True)
    assert "play" in calls
    ed._on_video_playing_changed(False)
    assert "pause" in calls


def test_overlay_loaded_into_engine(tmp_path):
    _app()
    from sound_track_agent.overlay_session import OverlaySession, save_overlay
    sess = OverlaySession(); sess.add("bgm", 0.0, 5.0, "p", seg_id="x1")
    save_overlay(tmp_path / "t1", sess)
    ed = _ed(tmp_path)
    assert ed._overlay_session is not None
    assert ed._overlay_session.get("x1") is not None
