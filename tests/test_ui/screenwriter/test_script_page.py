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


def test_outline_action_column_fits_gen_button(tmp_path):
    """操作列须够宽容纳「生成此集」按钮（不裁切）。"""
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 1,
        "episodes": [{"id": "E1", "title": "t1", "summary": "s1"}],
    }), encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    # 操作列宽 + 按钮 min 宽都应 >= 80px（「生成此集」4 字 + padding）
    assert p._outline_table.columnWidth(3) >= 80
    btn = p._outline_table.cellWidget(0, 3)
    assert btn is not None and btn.minimumWidth() >= 80


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


def test_revalidate_clears_banner_after_in_session_idea(tmp_path):
    """会话内：set_project 时无创意→banner+禁用；之后生成创意，
    revalidate_upstream 必须清 banner 并启用生成（修 stale 误报"上游缺失"）。"""
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)                    # 无 创意.json
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False
    _setup_idea(tmp_path)                      # 会话内才生成创意
    p.revalidate_upstream()
    assert p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is True


def test_single_episode_done_renders_outline_without_panel_switch(tmp_path):
    """单集快路径：episode done 后应直接渲染大纲 + 载入编辑器，无需切任务面板。

    多集靠 outline done(saved=剧本.json)→_load_index；单集 done 的 saved 是
    剧本_E1.md，旧逻辑不 reload index → 大纲表空、编辑器空，必须切任务面板才刷新。
    """
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)                        # 此刻无 剧本.json
    assert p._outline_table.rowCount() == 0
    assert p._current_episode == ""
    # 模拟 agent 单集落盘：剧本.json(含 E1) + 剧本_E1.md
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "T", "episode_count": 1, "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": "第一集", "summary": "s"}],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("E1 正文内容", encoding="utf-8")
    # 单集 done 事件：saved 是 .md 路径
    p._on_sse_event("done",
                    {"saved": str(tmp_path / "剧本_E1.md"), "episode_id": "E1"},
                    str(tmp_path))
    assert p._outline_table.rowCount() == 1, "大纲表应已渲染"
    assert p._current_episode == "E1"
    assert "E1 正文内容" in p._episode_editor.toPlainText()


def test_layout_has_splitter_and_hidden_preview(tmp_path):
    """左右分栏：splitter 存在、大纲预览默认隐藏、左右栏控件就位。"""
    _app()
    p = ScriptPage(_StubClient())
    assert p._splitter is not None
    assert p._outline_preview.isHidden()
    assert p._outline_collapsed is False
    assert p._collapse_btn.text() == "◀ 大纲"
    assert p._episode_title_lbl.text().startswith("剧集")


def test_outline_delta_goes_to_preview_not_editor(tmp_path):
    """大纲流式时 delta 进 _outline_preview，剧集编辑器保持空。"""
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_streaming = True
    p._on_sse_event("delta", {"text": '{"episodes":['}, str(tmp_path))
    assert '{"episodes":[' in p._outline_preview.toPlainText()
    assert p._episode_editor.toPlainText() == ""


def test_outline_done_restores_list_view(tmp_path):
    """大纲 done(saved=剧本.json) 后：预览隐藏、列表显示并渲染、标志复位。"""
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "T", "episode_count": 2, "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": "a", "summary": "s"},
                     {"id": "E2", "title": "b", "summary": "s2"}],
    }, ensure_ascii=False), encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_streaming = True
    p._outline_table.hide()
    p._outline_preview.show()
    p._on_sse_event("done", {"saved": str(tmp_path / "剧本.json")}, str(tmp_path))
    assert p._outline_streaming is False
    assert p._outline_preview.isHidden()
    assert not p._outline_table.isHidden()
    assert p._outline_table.rowCount() == 2


def test_collapse_toggle_hides_left_pane(tmp_path):
    """折叠钮按显式状态切换：折叠→宽度0/文案▶；展开→文案◀。"""
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._splitter.setSizes([300, 700])
    p._toggle_outline_pane()
    assert p._outline_collapsed is True
    assert p._collapse_btn.text() == "▶ 大纲"
    assert p._splitter.sizes()[0] == 0
    p._toggle_outline_pane()
    assert p._outline_collapsed is False
    assert p._collapse_btn.text() == "◀ 大纲"


def test_episode_select_updates_right_editor_and_title(tmp_path):
    """选第 2 行：current_episode=E2、右栏编辑器载入 E2、标题含 E2。"""
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "T", "episode_count": 2, "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": "a", "summary": "s"},
                     {"id": "E2", "title": "b", "summary": "s2"}],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "剧本_E2.md").write_text("E2 正文", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_table.selectRow(1)
    assert p._current_episode == "E2"
    assert "E2 正文" in p._episode_editor.toPlainText()
    assert "E2" in p._episode_title_lbl.text()
