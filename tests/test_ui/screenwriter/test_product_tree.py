import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._product_tree import _ProductTree


def _app():
    return QApplication.instance() or QApplication([])


def _sb_fixture():
    return {
        "title": "demo",
        "characters": [{"name": "狐妖"}, {"name": "书生"}],
        "shots": [{"shotId": f"S{i:02d}"} for i in range(1, 11)],   # 10 shots
    }


def test_build_from_sb_creates_expected_placeholders(tmp_path):
    _app()
    t = _ProductTree()
    t.build_from_sb(tmp_path / "prompts", _sb_fixture(),
                     grid_mode="9", include_character_refs=True)
    # 2 角色 + ceil(10/9)=2 网格 = 4 文件
    paths = list(t.tree_items.keys())
    assert len(paths) == 4
    char_dir = tmp_path / "prompts" / "角色参考图"
    grid_dir = tmp_path / "prompts" / "N宫格"
    assert (char_dir / "狐妖_ref.md") in paths
    assert (char_dir / "书生_ref.md") in paths
    assert (grid_dir / "S1.md") in paths
    assert (grid_dir / "S2.md") in paths


def test_status_dot_updates_when_file_exists(tmp_path):
    _app()
    (tmp_path / "prompts" / "角色参考图").mkdir(parents=True)
    (tmp_path / "prompts" / "角色参考图" / "狐妖_ref.md").write_text("x",
                                                                    encoding="utf-8")
    t = _ProductTree()
    t.build_from_sb(tmp_path / "prompts", _sb_fixture(),
                     grid_mode="9", include_character_refs=True)
    item = t.tree_items[tmp_path / "prompts" / "角色参考图" / "狐妖_ref.md"]
    assert "✓" in item.text(0)
    item2 = t.tree_items[tmp_path / "prompts" / "N宫格" / "S1.md"]
    assert "○" in item2.text(0)


def test_set_status_streaming():
    _app()
    t = _ProductTree()
    t.build_from_sb(Path("/tmp/nothing"), _sb_fixture(),
                     grid_mode="single", include_character_refs=False)
    # grid single：10 shots → 10 网格文件
    grid_dir = Path("/tmp/nothing") / "N宫格"
    p = grid_dir / "S1.md"
    assert p in t.tree_items
    t.set_status(p, "streaming")
    assert "●" in t.tree_items[p].text(0)


def test_build_from_sb_with_groups(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from drama_shot_master.ui.widgets.screenwriter._product_tree import _ProductTree
    sb = {"characters": [], "shots": [{"shotId": f"S{i}"} for i in range(10)]}
    t = _ProductTree()
    t.build_from_sb(tmp_path, sb, groups=[{"shot_ids": ["a"] * 9},
                                          {"shot_ids": ["b"]}],
                    include_character_refs=False)
    names = [p.name for p in t.tree_items]
    assert "S1.md" in names and "S2.md" in names and "S3.md" not in names
