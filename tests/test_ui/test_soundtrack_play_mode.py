"""SoundtrackEditor 叠加播放：调度时间表（零渲染）+ 模式 enable 映射。"""
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


def _bgm_session(tmp_path, n=2):
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate, AccentPoint)
    segs = []
    for i in range(n):
        mp3 = tmp_path / f"bgm{i}.mp3"; mp3.write_bytes(b"x")
        segs.append(SegmentScore(i, i * 10.0, (i + 1) * 10.0,
            candidates=[BGMCandidate(path=str(mp3), seed=1, prompt="p")],
            chosen_candidate=0))
    return ScoringSession(source_mp4="", source_hash="", global_style="x",
        frame_rate=24.0, segments=segs,
        accent_points=[AccentPoint(t=1.0, intensity=0.7, confirmed=True)])


def test_has_overlay_mixer(tmp_path):
    _app()
    assert _ed(tmp_path)._overlay is not None


def test_build_schedules_from_session(tmp_path):
    """_build_overlay_schedules：各段选定候选 → bgm 时间表（不渲染）。"""
    _app()
    ed = _ed(tmp_path)
    ed._session = _bgm_session(tmp_path, n=2)
    ed._build_overlay_schedules()
    assert ed._overlay.schedule_len("bgm") == 2


def test_raw_mode_disables_overlays(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._apply_play_mode_tracks("raw")
    assert ed._overlay.is_enabled("bgm") is False
    assert ed._overlay.is_enabled("sfx") is False


def test_bgm_mode_enables_bgm_only(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._apply_play_mode_tracks("bgm")
    assert ed._overlay.is_enabled("bgm") is True
    assert ed._overlay.is_enabled("sfx") is False


def test_mix_mode_enables_both(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._apply_play_mode_tracks("mix")
    assert ed._overlay.is_enabled("bgm") is True
    assert ed._overlay.is_enabled("sfx") is True


def test_play_mode_changed_no_synthesis_no_worker(tmp_path):
    """选配乐：即时建表 + 启用，绝不调 build_accent_preview（不合成、不卡）。"""
    _app()
    ed = _ed(tmp_path)
    ed._session = _bgm_session(tmp_path, n=2)
    import sound_track_agent.facade as fac
    called = {"n": 0}
    orig = fac.build_accent_preview
    fac.build_accent_preview = lambda *a, **k: called.__setitem__("n", called["n"] + 1)
    try:
        ed._on_play_mode_changed("bgm")
    finally:
        fac.build_accent_preview = orig
    assert called["n"] == 0
    assert ed._overlay.is_enabled("bgm") is True
    assert ed._overlay.schedule_len("bgm") == 2


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
