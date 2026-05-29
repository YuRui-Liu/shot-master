"""SoundtrackEditor DAW 主区 smoke：DAW widget 存在 + selection → inspector 切换 + 快捷键。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _task(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    return {"id": "t1", "name": "test", "mp4": str(mp4),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}


def test_daw_widgets_exist(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    assert ed._daw_toolbar is not None
    assert ed._track_view is not None
    assert ed._minimap is not None
    assert ed._inspector_container is not None
    assert ed._undo is not None
    assert ed._selection is not None


def test_no_tabs_attribute(tmp_path):
    """4 tab 完全消失（self.tabs 不再存在）。"""
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    assert not hasattr(ed, "tabs")


def test_selection_change_swaps_inspector(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    from drama_shot_master.ui.widgets.daw.inspector import (
        EmptyInspector, BgmInspector,
    )
    # 初始: empty
    assert isinstance(ed._current_inspector, EmptyInspector)
    # 加 bgm session + 选 cue 0 → BgmInspector
    from sound_track_agent.session import ScoringSession, SegmentScore
    ed._session = ScoringSession(
        source_mp4="", source_hash="", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(0, 0.0, 5.0)])
    ed._selection.set([_CueRef("bgm", 0)])
    assert isinstance(ed._current_inspector, BgmInspector)
    # 清选 → Empty
    ed._selection.clear()
    assert isinstance(ed._current_inspector, EmptyInspector)


def test_config_button_opens_dialog(tmp_path, monkeypatch):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    opened = {"n": 0}
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    orig_exec = ConfigDialog.exec
    monkeypatch.setattr(ConfigDialog, "exec",
                        lambda self: opened.__setitem__("n", opened["n"] + 1)
                                     or ConfigDialog.Rejected)
    ed._on_open_config_dialog()
    assert opened["n"] == 1


def test_undo_via_toolbar(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from drama_shot_master.ui.widgets.daw.commands import MoveCue
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    from sound_track_agent.session import ScoringSession, SegmentScore
    ed._session = ScoringSession(
        source_mp4="", source_hash="", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(0, 0.0, 5.0)])
    cmd = MoveCue(ed._session, ed._sfx_session, [_CueRef("bgm", 0)], 2.0)
    ed._undo.push(cmd)
    assert ed._session.segments[0].t_start == 2.0
    ed._daw_toolbar.btn_undo.click()
    assert ed._session.segments[0].t_start == 0.0


def test_delete_key_removes_selected(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate
    ed._session = ScoringSession(
        source_mp4="", source_hash="", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(0, 0.0, 5.0,
                                 candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="x")],
                                 chosen_candidate=0)])
    ed._selection.set([_CueRef("bgm", 0)])
    ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
    ed.keyPressEvent(ev)
    # BGM 软删 chosen=None
    assert ed._session.segments[0].chosen_candidate is None
