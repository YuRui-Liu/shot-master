import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.screenwriter.video_prompt_page import VideoPromptPage


def _app():
    return QApplication.instance() or QApplication([])


class _Stub:
    pass


def _min_sb():
    return {
        "title": "test", "globalStyle": "ink-wash",
        "characters": [{"name": "A"}],
        "shots": [{"shotId": "S01", "duration": 3.0}],
    }


def test_constructs():
    _app()
    p = VideoPromptPage(_Stub())
    assert hasattr(p, "_gen_btn")
    assert hasattr(p, "_global_prompt_edit")
    assert hasattr(p, "_shots_table")


def test_set_project_none_disables_gen():
    _app()
    p = VideoPromptPage(_Stub())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_set_project_no_storyboard_disables_gen(tmp_path):
    _app()
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._gen_btn.isEnabled() is False


def test_set_project_with_storyboard_enables_gen(tmp_path):
    _app()
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(_min_sb()), encoding="utf-8")
    p = VideoPromptPage(_Stub())
    p.set_project(tmp_path)
    assert p._gen_btn.isEnabled() is True


def test_advance_signal_emitted():
    _app()
    p = VideoPromptPage(_Stub())
    received = []
    p.stageAdvanceRequested.connect(lambda i: received.append(i))
    p._on_advance_clicked()
    assert received == [4]           # Stage 5 = index 4
