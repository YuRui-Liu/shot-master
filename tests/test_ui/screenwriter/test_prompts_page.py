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
    char_dir = tmp_path / "prompts" / "角色参考图"
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
        "saved": str(pB / "prompts" / "角色参考图" / "X_ref.md"),
        "kind": "character_ref",
    }, str(pB))
    # 树结构不变
    assert len(p._tree.tree_items) == items_count_before
