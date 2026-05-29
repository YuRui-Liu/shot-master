"""试听 BGM/SFX 候选时视频应自动暂停。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config()
    c.settings_path = tmp_path / "s.json"
    return c


def _task(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    return {"id": "t1", "name": "测试", "mp4": str(mp4),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}


def test_bgm_review_widget_has_preview_started_signal():
    from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
    assert hasattr(SegmentReviewWidget, "previewStarted")


def test_sfx_review_widget_has_preview_started_signal():
    from drama_shot_master.ui.widgets.sfx_review_widget import SfxReviewWidget
    assert hasattr(SfxReviewWidget, "previewStarted")


def test_bgm_preview_started_pauses_video(tmp_path):
    """SoundtrackEditor 收到 BGM 试听 signal → 调 video_preview.pause."""
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from sound_track_agent.session import ScoringSession
    stub = ScoringSession(source_mp4="", source_hash="", global_style="",
                          frame_rate=24.0, segments=[])
    ed._session = stub
    ed._mount_session_tabs()
    paused = {"n": 0}
    ed._video_preview.pause = lambda: paused.__setitem__("n", paused["n"] + 1)
    ed._review.previewStarted.emit()
    assert paused["n"] == 1


def test_sfx_preview_started_pauses_video(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
    ed._sfx_session = SFXSession(
        source_mp4="", source_hash="", frame_rate=24.0,
        shots=[SFXShot(0, 0.0, 3.0, status="generated",
                       candidates=[SFXCandidate("/a.mp3", 1, "x")],
                       chosen_candidate=0)])
    ed._rebuild_sfx_review()
    paused = {"n": 0}
    ed._video_preview.pause = lambda: paused.__setitem__("n", paused["n"] + 1)
    sfx_review = None
    for i in range(ed._sfx_review_lay.count()):
        w = ed._sfx_review_lay.itemAt(i).widget()
        if w is not None and w.__class__.__name__ == "SfxReviewWidget":
            sfx_review = w; break
    assert sfx_review is not None
    sfx_review.previewStarted.emit()
    assert paused["n"] == 1
