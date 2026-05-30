"""SoundtrackEditor 混音接线：header 列存在 + _apply_audio_state 解算 + 落盘。"""
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


def test_header_column_and_mix_exist(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._track_header is not None
    assert ed._mix is not None


def test_mute_bgm_disables_overlay_bgm_in_bgm_mode(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._play_mode = "bgm"
    calls = {}
    ed._overlay.set_enabled = lambda trk, on: calls.__setitem__(trk, on)
    ed._overlay.set_volume = lambda trk, v: None
    ed._video_preview.set_muted = lambda on: None
    ed._video_preview.set_volume = lambda v: None
    ed._mix.set_muted("bgm", True)
    ed._apply_audio_state()
    assert calls["bgm"] is False


def test_solo_video_silences_bgm(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._play_mode = "mix"
    vid = {}
    ov = {}
    ed._video_preview.set_muted = lambda on: vid.__setitem__("muted", on)
    ed._video_preview.set_volume = lambda v: None
    ed._overlay.set_enabled = lambda trk, on: ov.__setitem__(trk, on)
    ed._overlay.set_volume = lambda trk, v: None
    ed._mix.set_soloed("video", True)
    ed._apply_audio_state()
    assert vid["muted"] is False
    assert ov["bgm"] is False and ov["sfx"] is False


def test_mute_toggle_persists_mix_json(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._on_mute_toggled("sfx", True)
    from drama_shot_master.ui.widgets.daw.track_mix import load_mix
    reloaded = load_mix(ed._work_dir())
    assert reloaded.is_muted("sfx") is True
