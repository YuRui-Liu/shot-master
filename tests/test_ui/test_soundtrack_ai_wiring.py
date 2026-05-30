"""SoundtrackEditor AI 接线：面板存在 + 指令→方向→写prompt→刷新（直接调 _on_directive_built）。"""
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


def test_ai_chat_panel_exists(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._ai_chat is not None


def test_directive_requested_without_session_shows_error(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._session = None
    errs = []
    ed._ai_chat.append_error = lambda m: errs.append(m)
    ed._on_directive_requested("史诗感", True)
    assert len(errs) == 1


def test_directive_built_apply_writes_prompts(tmp_path):
    _app()
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, SoundtrackDirective)
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="旧",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0)])
    new_dir = SoundtrackDirective(global_directive="史诗管弦",
        conversation=[{"role": "user", "text": "史诗"},
                      {"role": "assistant", "text": "ok"}])
    ed._on_directive_built(new_dir, apply_prompts=True)
    assert ed._session.directive.global_directive == "史诗管弦"
    assert "史诗管弦" in ed._session.segments[0].music_prompt
    assert ed._session.global_style == "史诗管弦"


def test_directive_built_no_apply_keeps_prompts(tmp_path):
    _app()
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, SoundtrackDirective)
    ed = _ed(tmp_path)
    seg = SegmentScore(0, 0.0, 5.0); seg.music_prompt = "原prompt"
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="旧",
        frame_rate=24.0, segments=[seg])
    ed._on_directive_built(SoundtrackDirective(global_directive="史诗"),
                           apply_prompts=False)
    assert ed._session.directive.global_directive == "史诗"
    assert ed._session.segments[0].music_prompt == "原prompt"
