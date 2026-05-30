"""SoundtrackEditor 预览轨指纹：影响产物的字段变化 → 指纹变。"""
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


def test_bgm_fingerprint_changes_with_chosen(tmp_path):
    _app()
    from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="x",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0,
            candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="p"),
                        BGMCandidate(path="/b.mp3", seed=2, prompt="p")],
            chosen_candidate=0)])
    fp1 = ed._preview_fingerprint("bgm")
    ed._session.segments[0].chosen_candidate = 1
    fp2 = ed._preview_fingerprint("bgm")
    assert fp1 != fp2


def test_bgm_fingerprint_stable_when_unchanged(tmp_path):
    _app()
    from sound_track_agent.session import ScoringSession, SegmentScore
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="x",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0)])
    assert ed._preview_fingerprint("bgm") == ed._preview_fingerprint("bgm")


def test_sfx_fingerprint_changes_with_enabled(tmp_path):
    _app()
    from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
    ed = _ed(tmp_path)
    ed._sfx_session = SFXSession(source_mp4="", source_hash="", frame_rate=24.0,
        shots=[SFXShot(0, 0.0, 3.0, duration=3.0,
            candidates=[SFXCandidate(path="/s.mp3", seed=1, prompt="p")],
            chosen_candidate=0, enabled=True)])
    fp1 = ed._preview_fingerprint("sfx")
    ed._sfx_session.shots[0].enabled = False
    fp2 = ed._preview_fingerprint("sfx")
    assert fp1 != fp2


def test_bgm_fingerprint_serializes_accent_points(tmp_path):
    """accent_points 含 AccentPoint 对象时指纹不崩（真实场景回归）。"""
    _app()
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, AccentPoint)
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="x",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0)],
        accent_points=[AccentPoint(t=1.5, intensity=0.8, confirmed=True)])
    fp = ed._preview_fingerprint("bgm")          # 不应抛 TypeError
    assert isinstance(fp, str) and fp
    # 改 accent 强度 → 指纹变
    ed._session.accent_points[0].intensity = 0.2
    assert ed._preview_fingerprint("bgm") != fp
