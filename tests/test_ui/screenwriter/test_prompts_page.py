import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.prompts_page import PromptsPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _sb_min():
    return {
        "title": "demo",
        "characters": [{"name": "狐妖"}],
        "shots": [{"shotId": "S01"}, {"shotId": "S02"}],
    }


def _sb_fixture():
    return _sb_min()


def test_set_project_none_disables_gen():
    _app()
    p = PromptsPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_loads_sb_builds_tree(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    # 1 角色 + ceil(2/9)=1 网格 = 2 文件占位
    assert len(p._tree.tree_items) == 2


def test_partial_event_updates_tree_dot(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    char_dir = tmp_path / "prompts" / "E1" / "角色参考图"
    char_dir.mkdir(parents=True)
    (char_dir / "狐妖_ref.md").write_text("done content", encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    p._on_sse_event("partial", {
        "saved": str(char_dir / "狐妖_ref.md"),
        "kind": "character_ref",
    }, str(tmp_path))
    item = p._tree.tree_items[char_dir / "狐妖_ref.md"]
    assert "✓" in item.text(0)


def test_upstream_missing_shows_banner_and_disables_gen(tmp_path):
    _app()
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)   # 无 分镜.json
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False


def test_upstream_present_hides_banner(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    assert p._upstream_banner.isHidden()


def test_revalidate_upstream_clears_stale_banner(tmp_path):
    """会话内：set_project 时分镜还没生成→banner 显示；之后生成了分镜，
    revalidate_upstream() 应清掉"上游缺失"并启用生成（修复切 stage 不刷新）。"""
    _app()
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)                       # 此刻无 分镜_E1.json
    assert not p._upstream_banner.isHidden()      # 显示缺失
    # 用户在分镜阶段生成了分镜
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(_sb_min()), encoding="utf-8")
    p.revalidate_upstream()                       # 切回本 stage 时触发
    assert p._upstream_banner.isHidden()          # banner 已清
    assert p._gen_btn.isEnabled() is True


def test_partial_for_inactive_project_does_not_touch_tree(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    (pA / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(pA)
    # B 的 partial 不应动 A 的树（虽然路径相同 schema，但 _project_dir 是 A）
    items_count_before = len(p._tree.tree_items)
    p._on_sse_event("partial", {
        "saved": str(pB / "prompts" / "E1" / "角色参考图" / "X_ref.md"),
        "kind": "character_ref",
    }, str(pB))
    # 树结构不变
    assert len(p._tree.tree_items) == items_count_before


def test_episode_selector_renders(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                     {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    assert p._episode_selector.combo.count() == 2


def test_generate_body_includes_episode_id(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    captured = {}
    orig_start = p._start_stream
    def _intercept(path, body, params=None):
        captured.update(body)
    p._start_stream = _intercept
    try:
        p._on_generate_clicked()
    except Exception:
        pass
    assert captured.get("episode_id") == "E1"


def test_generate_all_body_includes_groups(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    captured = {}
    p._start_stream = lambda path, body, params=None: captured.update(body)
    p._group_editor.generateAll.emit()
    assert "groups" in captured["options"]
    assert captured["options"].get("only_group_index") is None


def test_generate_single_group_body_includes_index(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    captured = {}
    p._start_stream = lambda path, body, params=None: captured.update(body)
    p._group_editor.generateGroup.emit(1)
    assert captured["options"]["only_group_index"] == 1
    assert "groups" in captured["options"]


def test_group_editor_is_full_width_above_splitter(tmp_path):
    """分组编辑器应直属 page（全宽在 splitter 之上），不嵌在窄的左 pane 里
    （否则 6 列表被右侧预览挤压、列/行显示不全）。"""
    _app()
    p = PromptsPage(_StubClient())
    # 直接父级是 page 本身，而非左侧 pane QWidget
    assert p._group_editor.parentWidget() is p
