"""SoundtrackEditor 顶部预览 smoke：widget 存在 + tab 切换触发 rebuild + cue 点击切 tab."""
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


def test_editor_has_overview_widgets(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    assert ed._video_preview is not None
    assert ed._overview_timeline is not None


def test_rebuild_overview_does_not_crash_with_empty_session(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    ed._rebuild_overview()


def test_tab_change_triggers_rebuild(tmp_path, monkeypatch):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    rebuilt = {"n": 0}
    orig = ed._rebuild_overview
    def fake_rebuild():
        rebuilt["n"] += 1
        return orig()
    monkeypatch.setattr(ed, "_rebuild_overview", fake_rebuild)
    ed.tabs.setCurrentIndex(2)
    assert rebuilt["n"] >= 1


def test_overview_playhead_drag_calls_video_seek(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    seeks = []
    ed._video_preview.seek = lambda t: seeks.append(t)
    ed._overview_timeline.playheadDragged.emit(5.5)
    assert seeks == [5.5]


def test_overview_cue_clicked_switches_tab(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    # BGM tab 是 index 1（试听选优）；SFX tab 是 index 3
    seeks = []
    ed._video_preview.seek = lambda t: seeks.append(t)
    ed._overview_timeline.cueClicked.emit("bgm", 0, 2.5)
    assert ed.tabs.currentIndex() == 1
    assert seeks == [2.5]
    ed._overview_timeline.cueClicked.emit("sfx", 0, 6.0)
    assert ed.tabs.currentIndex() == 3
