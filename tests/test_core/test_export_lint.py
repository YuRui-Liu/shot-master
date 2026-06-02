"""导出前 lint 纯函数单测（R6，无 Qt / 无网络 / 用假 dict）。

依据研究 §5 失败模式（拆镜/时长/占位符未填/资源完备性闸门/限长）：
- lint_storyboard：单镜 >12s 警告、静态镜 >6s、相邻 ≤15s 重复可合并、
  占位符未填（prompt 含 '...'/TODO/空）= block、非叙事空镜占比 >20% 警告。
- lint_refs：status != ready 或缺图 = block（完备性闸门）。
- lint_prompt_length：超长（默认 1500）= warn。
- Issue：level(warn|block)/code/msg/where。
- export_lint(project_dir)：汇总（读 分镜_EN.json / ref_index）。

RED/GREEN：各规则触发对应 Issue；干净输入 → 空；block 与 warn 区分。
"""
from __future__ import annotations

import json

from drama_shot_master.core.export_lint import (
    Issue,
    export_lint,
    lint_prompt_length,
    lint_refs,
    lint_storyboard,
)


# --- Issue dataclass ------------------------------------------------------

def test_issue_fields():
    issue = Issue(level="warn", code="X", msg="m", where="w")
    assert issue.level == "warn"
    assert issue.code == "X"
    assert issue.msg == "m"
    assert issue.where == "w"


def _codes(issues):
    return {i.code for i in issues}


def _by_level(issues, level):
    return [i for i in issues if i.level == level]


# --- lint_storyboard ------------------------------------------------------

def _clean_storyboard():
    """干净分镜：各镜时长合规、prompt 已填、空镜占比低。"""
    return {
        "shots": [
            {"shotId": "S001", "description": "女主推门而入", "prompt": "a woman opens the door", "duration": 4.0},
            {"shotId": "S002", "description": "特写茶杯落地", "prompt": "close up of a teacup falling", "duration": 3.0},
            {"shotId": "S003", "description": "众人惊愕对视", "prompt": "crowd staring in shock", "duration": 5.0},
            {"shotId": "S004", "description": "男主缓步走来", "prompt": "a man walks slowly forward", "duration": 4.0},
            {"shotId": "S005", "description": "两人对峙", "prompt": "the two confront each other", "duration": 6.0},
        ]
    }


def test_lint_storyboard_clean_returns_empty():
    assert lint_storyboard(_clean_storyboard()) == []


def test_lint_storyboard_long_shot_over_12s_warns():
    sb = {"shots": [{"shotId": "S001", "description": "长镜", "prompt": "a long take", "duration": 13.0}]}
    issues = lint_storyboard(sb)
    long_issues = [i for i in issues if i.code == "SHOT_TOO_LONG"]
    assert len(long_issues) == 1
    assert long_issues[0].level == "warn"
    assert "S001" in long_issues[0].where


def test_lint_storyboard_static_shot_over_6s_warns():
    # 静态镜（无动作/static 标记）> 6s
    sb = {"shots": [{"shotId": "S001", "description": "静止远景", "prompt": "a static wide shot", "duration": 8.0, "static": True}]}
    issues = lint_storyboard(sb)
    static_issues = [i for i in issues if i.code == "STATIC_SHOT_TOO_LONG"]
    assert len(static_issues) == 1
    assert static_issues[0].level == "warn"
    assert "S001" in static_issues[0].where


def test_lint_storyboard_adjacent_mergeable_warns():
    # 相邻镜累计 ≤15s 且描述重复 → 可合并提示
    sb = {
        "shots": [
            {"shotId": "S001", "description": "女主站立凝视", "prompt": "woman standing and staring", "duration": 5.0},
            {"shotId": "S002", "description": "女主站立凝视", "prompt": "woman standing and staring", "duration": 5.0},
        ]
    }
    issues = lint_storyboard(sb)
    merge_issues = [i for i in issues if i.code == "ADJACENT_MERGEABLE"]
    assert len(merge_issues) == 1
    assert merge_issues[0].level == "warn"


def test_lint_storyboard_placeholder_unfilled_blocks():
    # prompt 含 '...' / TODO / 空 → block
    sb = {
        "shots": [
            {"shotId": "S001", "description": "占位", "prompt": "TODO 待补", "duration": 3.0},
            {"shotId": "S002", "description": "占位", "prompt": "a scene ...", "duration": 3.0},
            {"shotId": "S003", "description": "占位", "prompt": "", "duration": 3.0},
        ]
    }
    issues = lint_storyboard(sb)
    ph = [i for i in issues if i.code == "PLACEHOLDER_UNFILLED"]
    assert len(ph) == 3
    assert all(i.level == "block" for i in ph)
    wheres = {i.where for i in ph}
    assert "S001" in wheres and "S002" in wheres and "S003" in wheres


def test_lint_storyboard_empty_shot_ratio_over_20pct_warns():
    # 非叙事空镜（如纯空镜/无叙事内容）占比 > 20%
    shots = []
    for i in range(1, 6):
        shots.append({"shotId": f"S00{i}", "description": "正常叙事镜", "prompt": "a narrative shot", "duration": 3.0, "narrative": True})
    # 5 个正常 + 2 个空镜 = 2/7 ≈ 28.6% > 20%
    shots.append({"shotId": "S006", "description": "空镜", "prompt": "an establishing empty shot", "duration": 3.0, "narrative": False})
    shots.append({"shotId": "S007", "description": "空镜", "prompt": "an establishing empty shot", "duration": 3.0, "narrative": False})
    issues = lint_storyboard({"shots": shots})
    er = [i for i in issues if i.code == "EMPTY_SHOT_RATIO_HIGH"]
    assert len(er) == 1
    assert er[0].level == "warn"


def test_lint_storyboard_empty_input_returns_empty():
    assert lint_storyboard({}) == []
    assert lint_storyboard({"shots": []}) == []


# --- lint_refs ------------------------------------------------------------

def test_lint_refs_all_ready_returns_empty():
    entries = [
        {"name": "女主", "path": "女主_ref.png", "status": "ready"},
        {"name": "男主", "path": "男主_ref.png", "status": "ready"},
    ]
    assert lint_refs(entries) == []


def test_lint_refs_not_ready_blocks():
    entries = [
        {"name": "女主", "path": "女主_ref.png", "status": "ready"},
        {"name": "男主", "path": "男主_ref.png", "status": "pending"},
    ]
    issues = lint_refs(entries)
    assert len(issues) == 1
    assert issues[0].level == "block"
    assert issues[0].code == "REF_NOT_READY"
    assert "男主" in issues[0].where


def test_lint_refs_missing_path_blocks():
    # ready 但没有落盘文件 path → 缺图阻断
    entries = [
        {"name": "场景01", "path": "", "status": "ready"},
    ]
    issues = lint_refs(entries)
    assert len(issues) == 1
    assert issues[0].level == "block"
    assert issues[0].code == "REF_MISSING_IMAGE"


def test_lint_refs_empty_returns_empty():
    assert lint_refs([]) == []


# --- lint_prompt_length ---------------------------------------------------

def test_lint_prompt_length_under_max_returns_none():
    assert lint_prompt_length("a short prompt") is None


def test_lint_prompt_length_over_max_returns_warn_issue():
    issue = lint_prompt_length("x" * 1600, max=1500)
    assert issue is not None
    assert issue.level == "warn"
    assert issue.code == "PROMPT_TOO_LONG"


def test_lint_prompt_length_at_max_returns_none():
    assert lint_prompt_length("x" * 1500, max=1500) is None


# --- export_lint (汇总) ---------------------------------------------------

def test_export_lint_reads_storyboard_and_refs(tmp_path):
    # 准备 分镜_E1.json：含占位符未填（block）
    sb = {
        "shots": [
            {"shotId": "S001", "description": "占位", "prompt": "TODO", "duration": 3.0},
        ]
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8"
    )
    # 准备 characters/ref_index.json：缺图（block）
    char_dir = tmp_path / "characters"
    char_dir.mkdir()
    ref = {"schema_version": 1, "refs": [{"name": "女主", "path": "", "status": "pending"}]}
    (char_dir / "ref_index.json").write_text(
        json.dumps(ref, ensure_ascii=False), encoding="utf-8"
    )

    issues = export_lint(str(tmp_path))
    codes = _codes(issues)
    assert "PLACEHOLDER_UNFILLED" in codes
    assert "REF_NOT_READY" in codes
    # 都是 block 级
    assert all(i.level == "block" for i in _by_level(issues, "block"))
    assert len(_by_level(issues, "block")) >= 2


def test_export_lint_clean_project_returns_empty(tmp_path):
    sb = {
        "shots": [
            {"shotId": "S001", "description": "女主推门", "prompt": "a woman opens the door", "duration": 4.0},
        ]
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8"
    )
    char_dir = tmp_path / "characters"
    char_dir.mkdir()
    img = char_dir / "女主_ref.png"
    img.write_bytes(b"\x89PNG")
    ref = {"schema_version": 1, "refs": [{"name": "女主", "path": "女主_ref.png", "status": "ready"}]}
    (char_dir / "ref_index.json").write_text(
        json.dumps(ref, ensure_ascii=False), encoding="utf-8"
    )

    issues = export_lint(str(tmp_path))
    assert _by_level(issues, "block") == []


def test_export_lint_missing_files_no_crash(tmp_path):
    # 空项目目录：无分镜无 ref → 不崩，返回 list
    issues = export_lint(str(tmp_path))
    assert isinstance(issues, list)
