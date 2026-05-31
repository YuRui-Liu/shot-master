"""题材模板 loader 单测（纯逻辑，无 Qt）。

覆盖：
- 6 个内置模板都能 load 且通过 validate_template；
- list_genres 返回全部 6 个 genre_id；
- 故意留占位符（"...", "TODO" 等）的样例被 validate 拒；
- 缺必填字段的样例被 validate 拒；
- 题材叠加 validate_stack：≤3 通过、4 个不通过、空/重复处理。
"""
from __future__ import annotations

import copy

import pytest

from drama_shot_master.core import genre_templates as gt

# 研究 §3 锁定的 6 题材
EXPECTED_GENRES = {
    "short-drama",
    "single-episode",
    "commercial",
    "vlog",
    "mv",
    "oral-skit",
}


def test_list_genres_returns_six():
    ids = gt.list_genres()
    assert isinstance(ids, list)
    assert len(ids) == 6
    assert set(ids) == EXPECTED_GENRES


@pytest.mark.parametrize("genre_id", sorted(EXPECTED_GENRES))
def test_each_template_loads(genre_id):
    t = gt.load_genre(genre_id)
    assert isinstance(t, dict)
    assert t["genre_id"] == genre_id
    assert t["display_name"]


@pytest.mark.parametrize("genre_id", sorted(EXPECTED_GENRES))
def test_each_template_passes_validate(genre_id):
    t = gt.load_genre(genre_id)
    ok, errors = gt.validate_template(t)
    assert ok, f"{genre_id} 校验失败: {errors}"
    assert errors == []


def test_load_unknown_genre_raises():
    with pytest.raises((KeyError, FileNotFoundError)):
        gt.load_genre("does-not-exist")


def test_template_has_expected_schema_keys():
    t = gt.load_genre("short-drama")
    for key in (
        "genre_id",
        "display_name",
        "hard_constraints",
        "identity",
        "rhythm",
        "satisfaction_weights",
        "writing_rules",
        "donts",
        "params_default",
        "inner_slots",
    ):
        assert key in t, f"缺字段 {key}"
    # identity 子字段
    for key in ("one_liner", "audience", "conflict_source"):
        assert key in t["identity"]
    # rhythm 子字段
    for key in ("open_3s", "open_30s", "beat_density"):
        assert key in t["rhythm"]
    # params_default 子字段
    for key in ("split_unit", "duration_per_unit_sec", "rhythm_driver", "grids_per_unit"):
        assert key in t["params_default"]
    # inner_slots 子字段
    for key in ("decompose_strategy", "polish_style"):
        assert key in t["inner_slots"]


def test_params_default_match_research_table():
    """研究 §3 表：各题材分片单位/节奏驱动。"""
    assert gt.load_genre("short-drama")["params_default"]["split_unit"] == "episode"
    assert gt.load_genre("short-drama")["params_default"]["rhythm_driver"] == "plot"
    assert gt.load_genre("single-episode")["params_default"]["split_unit"] == "episode"
    assert gt.load_genre("commercial")["params_default"]["split_unit"] == "shot"
    assert gt.load_genre("commercial")["params_default"]["rhythm_driver"] == "sell-point"
    assert gt.load_genre("vlog")["params_default"]["split_unit"] == "shot"
    assert gt.load_genre("vlog")["params_default"]["rhythm_driver"] == "narration"
    assert gt.load_genre("mv")["params_default"]["split_unit"] == "segment"
    assert gt.load_genre("mv")["params_default"]["rhythm_driver"] == "music-beat"
    assert gt.load_genre("oral-skit")["params_default"]["split_unit"] == "shot"
    assert gt.load_genre("oral-skit")["params_default"]["rhythm_driver"] == "script"


# ---- validate_template 负例 ----

def _good_template() -> dict:
    return copy.deepcopy(gt.load_genre("short-drama"))


def test_validate_rejects_placeholder_string():
    t = _good_template()
    t["identity"]["one_liner"] = "..."
    ok, errors = gt.validate_template(t)
    assert not ok
    assert errors


def test_validate_rejects_todo_placeholder():
    t = _good_template()
    t["writing_rules"] = ["TODO"]
    ok, errors = gt.validate_template(t)
    assert not ok
    assert errors


def test_validate_rejects_missing_required_field():
    t = _good_template()
    del t["rhythm"]
    ok, errors = gt.validate_template(t)
    assert not ok
    assert any("rhythm" in e for e in errors)


def test_validate_rejects_empty_required_list():
    t = _good_template()
    t["writing_rules"] = []
    ok, errors = gt.validate_template(t)
    assert not ok
    assert errors


def test_validate_rejects_nested_missing_subfield():
    t = _good_template()
    del t["identity"]["one_liner"]
    ok, errors = gt.validate_template(t)
    assert not ok
    assert any("one_liner" in e for e in errors)


# ---- validate_stack 题材叠加 ----

def test_validate_stack_three_ok():
    assert gt.validate_stack(["short-drama", "commercial", "mv"]) is True


def test_validate_stack_four_rejected():
    assert gt.validate_stack(["short-drama", "commercial", "mv", "vlog"]) is False


def test_validate_stack_one_ok():
    assert gt.validate_stack(["short-drama"]) is True


def test_validate_stack_empty_rejected():
    assert gt.validate_stack([]) is False
