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
    g = default_groups(ids)
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
