import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import (
    auto_fit_mode, default_groups, group_capacity, group_is_valid,
)


def test_auto_fit_mode():
    assert auto_fit_mode(1) == "single"
    assert auto_fit_mode(2) == "4"
    assert auto_fit_mode(4) == "4"
    assert auto_fit_mode(5) == "9"
    assert auto_fit_mode(9) == "9"


def test_group_capacity():
    assert group_capacity("single") == 1
    assert group_capacity("4") == 4
    assert group_capacity("9") == 9


def test_default_groups_10_shots():
    ids = [f"S01_{i}" for i in range(1, 11)]
    g = default_groups(ids, "9")          # 显式按 9 切（默认已改为 4）
    assert len(g) == 2
    assert g[0]["grid_mode"] == "9"
    assert g[0]["shot_ids"] == ids[:9]
    assert g[1]["grid_mode"] == "single"
    assert g[1]["shot_ids"] == ["S01_10"]


def test_default_groups_4_shots():
    ids = ["A", "B", "C", "D"]
    g = default_groups(ids)
    assert len(g) == 1
    assert g[0]["grid_mode"] == "4"


def test_default_groups_empty():
    assert default_groups([]) == []


def test_group_is_valid():
    assert group_is_valid({"grid_mode": "9", "shot_ids": ["a", "b"]}) is True
    assert group_is_valid({"grid_mode": "single", "shot_ids": ["a", "b"]}) is False
    assert group_is_valid({"grid_mode": "4", "shot_ids": []}) is False


from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def test_editor_set_shots_builds_default_groups():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor(default_grid_mode="9")   # 显式 9 验证切块
    ed.set_shots([f"S01_{i}" for i in range(1, 11)])
    g = ed.groups()
    assert len(g) == 2
    assert g[0]["grid_mode"] == "9" and len(g[0]["shot_ids"]) == 9
    assert g[1]["grid_mode"] == "single"


def test_editor_generate_group_signal():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()
    ed.set_shots(["A", "B"])
    got = []
    ed.generateGroup.connect(got.append)
    ed._emit_generate_group(1)        # 1-based
    assert got == [1]


def test_editor_generate_all_signal():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()
    ed.set_shots(["A", "B", "C", "D"])
    got = []
    ed.generateAll.connect(lambda: got.append(True))
    ed._gen_all_btn.click()
    assert got == [True]


def test_editor_add_group_appends():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()
    ed.set_shots(["A", "B", "C"])
    n0 = len(ed.groups())
    ed._add_group()
    assert len(ed.groups()) == n0 + 1


# ── 默认宫格可配置（默认四宫格）──────────────────────────────

def test_default_groups_default_mode_is_4():
    ids = [f"S{i}" for i in range(1, 11)]   # 10 镜
    g = default_groups(ids)                 # 默认按 4 切
    assert len(g) == 3                       # 4 + 4 + 2
    assert [len(x["shot_ids"]) for x in g] == [4, 4, 2]
    assert all(x["grid_mode"] == "4" for x in g)


def test_default_groups_explicit_9():
    ids = [f"S{i}" for i in range(1, 11)]
    g = default_groups(ids, "9")
    assert len(g) == 2 and g[0]["grid_mode"] == "9" and g[1]["grid_mode"] == "single"


def test_editor_default_grid_mode_4():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()                  # 默认四宫格
    ed.set_shots([f"S{i}" for i in range(1, 9)])   # 8 镜 → 2 组 4
    g = ed.groups()
    assert len(g) == 2 and all(x["grid_mode"] == "4" for x in g)
