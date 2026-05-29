"""ScriptPage v2（多集）测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _setup_idea(tmp_path):
    (tmp_path / "创意.json").write_text(json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "X"}],
    }), encoding="utf-8")


def test_set_project_none_disables(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_n1_button_label_is_生成剧本(tmp_path):
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_count_spin.setValue(1)
    assert p._gen_btn.text() == "生成剧本"


def test_n3_button_label_is_生成大纲(tmp_path):
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_count_spin.setValue(3)
    assert p._gen_btn.text() == "生成大纲"


def test_loads_script_json_renders_outline_rows(tmp_path):
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 2,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
        ],
    }), encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._outline_table.rowCount() == 2


def test_click_row_loads_episode_md(tmp_path):
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 2,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
        ],
    }), encoding="utf-8")
    (tmp_path / "剧本_E2.md").write_text("# E2 内容", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_table.selectRow(1)   # 选 E2
    p._on_outline_row_selected()
    assert "E2 内容" in p._episode_editor.toPlainText()


def test_legacy_script_md_treated_as_E1(tmp_path):
    """旧项目（只有 剧本.md）→ set_project 不抛 + 行为兼容。"""
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.md").write_text("# legacy", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    # legacy 模式：editor 装 legacy 内容 或 大纲表空行（两种实现皆可）
    assert "legacy" in p._episode_editor.toPlainText() or \
           p._outline_table.rowCount() == 0


def test_advance_emits_with_selected_episode(tmp_path):
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 1,
        "episodes": [{"id": "E1", "title": "t1", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("ok", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_table.selectRow(0)
    p._on_outline_row_selected()
    got = []
    p.stageAdvanceRequested.connect(got.append)
    p._on_advance_clicked()
    # 落 selected_episode 到磁盘
    si = json.loads((tmp_path / "剧本.json").read_text(encoding="utf-8"))
    assert si["selected_episode"] == "E1"
    assert got == [2]


def test_upstream_missing_creative_disables_gen(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)   # 无创意.json
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False
