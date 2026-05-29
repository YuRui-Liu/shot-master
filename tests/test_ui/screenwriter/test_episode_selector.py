"""_EpisodeSelector 单元测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector


def _app():
    return QApplication.instance() or QApplication([])


def test_renders_from_script_index(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 3,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
            {"id": "E3", "title": "t3", "summary": "s3"},
        ],
    }), encoding="utf-8")
    sel = _EpisodeSelector()
    sel.set_project(tmp_path)
    assert sel.combo.count() == 3


def test_status_dots_reflect_disk_files(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    sel = _EpisodeSelector(file_pattern_for_status="分镜_{ep}.json")
    sel.set_project(tmp_path)
    # E1 完成 → 项前缀含 ✓；E2 未完成 → ○
    assert "✓" in sel.combo.itemText(0)
    assert "○" in sel.combo.itemText(1)


def test_episode_changed_signal_emits_id(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    sel = _EpisodeSelector()
    sel.set_project(tmp_path)
    got = []
    sel.episodeChanged.connect(got.append)
    sel.combo.setCurrentIndex(1)
    assert got and got[-1] == "E2"


def test_set_project_none_clears(tmp_path):
    _app()
    sel = _EpisodeSelector()
    sel.set_project(None)
    assert sel.combo.count() == 0


def test_select_episode_programmatically(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 3,
        "episodes": [{"id": f"E{i}", "title": "t", "summary": "s"}
                      for i in (1, 2, 3)],
    }), encoding="utf-8")
    sel = _EpisodeSelector()
    sel.set_project(tmp_path)
    sel.select_episode("E2")
    assert sel.current_episode() == "E2"
