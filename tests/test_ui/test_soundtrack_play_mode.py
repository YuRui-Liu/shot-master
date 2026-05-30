"""SoundtrackEditor 叠加播放模式：原声/配乐/混音 → OverlayMixer enable 映射。"""
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


def test_has_overlay_mixer(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._overlay is not None


def test_raw_mode_disables_overlays(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._apply_play_mode_tracks("raw")
    assert ed._overlay.is_enabled("bgm") is False
    assert ed._overlay.is_enabled("sfx") is False


def test_bgm_mode_enables_bgm_only(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._overlay.set_track("bgm", str(tmp_path / "raw.mp4"))
    ed._apply_play_mode_tracks("bgm")
    assert ed._overlay.is_enabled("bgm") is True
    assert ed._overlay.is_enabled("sfx") is False


def test_mix_mode_enables_both(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._overlay.set_track("bgm", str(tmp_path / "raw.mp4"))
    ed._overlay.set_track("sfx", str(tmp_path / "raw.mp4"))
    ed._apply_play_mode_tracks("mix")
    assert ed._overlay.is_enabled("bgm") is True
    assert ed._overlay.is_enabled("sfx") is True


def test_raw_mode_video_source_is_original_mp4(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._play_mode = "raw"
    assert ed._resolve_video_source() == ed._task["mp4"]


def test_scored_mp4_helper_prefers_session_then_task(tmp_path):
    _app()
    sess_out = tmp_path / "s.mp4"; sess_out.write_bytes(b"v")
    ed = _ed(tmp_path)
    ed._session = type("S", (), {"output": str(sess_out)})()
    assert ed._scored_mp4() == str(sess_out)
