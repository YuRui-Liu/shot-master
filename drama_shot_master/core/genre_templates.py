"""题材模板 loader（纯逻辑，无 Qt，全单测）。

读 templates/genres/ 下的 6 个内置题材模板（共用骨架，研究 §3）：
short-drama / single-episode / commercial / vlog / mv / oral-skit。

对外接口：
- load_genre(genre_id)   -> dict       加载单个题材模板（yaml -> dict）
- list_genres()          -> list[str]  返回全部 genre_id（读 index.json）
- validate_template(t)   -> (ok, errors)  schema 必填 + 占位符未填检测
- validate_stack(ids)    -> bool       题材叠加 ≤3（且非空）

设计要点（照研究 §3 / 设计 spec 内容资产段）：
- 组织法：统一目录 templates/genres/ + 每题材一个 template.yaml + index.json 登记。
- 入库门槛：真实跑通、无未填占位符（Yvonne）——validate_template 把占位符当硬错误。
- 题材叠加（0xsline）：主 + 副 ≤3 类，validate_stack 做上限校验。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import yaml

# core/ -> drama_shot_master/；模板随包分发（drama_shot_master/templates 被 build spec 打包）
_PKG_ROOT = Path(__file__).resolve().parents[1]
_GENRES_DIR = _PKG_ROOT / "templates" / "genres"
_INDEX_FILE = _GENRES_DIR / "index.json"

# 题材叠加上限（主 + 副，研究 §3）
STACK_MAX = 3

# 共用骨架 schema：顶层必填字段及其嵌套必填子字段（研究 §3）
# 值为 None 表示该字段只要求"存在且非空"；值为 tuple 表示需校验的子字段。
_REQUIRED_TOP = (
    "genre_id",
    "display_name",
    "identity",
    "rhythm",
    "satisfaction_weights",
    "writing_rules",
    "donts",
    "params_default",
    "inner_slots",
)
# hard_constraints 必填但允许为空列表（仅高风险题材填，§0），单独处理。
_REQUIRED_SUBFIELDS = {
    "identity": ("one_liner", "audience", "conflict_source"),
    "rhythm": ("open_3s", "open_30s", "beat_density"),
    "params_default": (
        "split_unit",
        "duration_per_unit_sec",
        "rhythm_driver",
        "grids_per_unit",
    ),
    "inner_slots": ("decompose_strategy", "polish_style"),
}

# 占位符标记：出现即视为"未填"，validate 拒绝（入库门槛）
_PLACEHOLDER_TOKENS = ("...", "todo", "tbd", "xxx", "fixme", "待填", "占位", "placeholder")


def _genre_dir(genre_id: str) -> Path:
    return _GENRES_DIR / genre_id


def load_genre(genre_id: str) -> dict:
    """加载单个题材模板，返回 dict。

    未知 genre_id 或缺文件抛 FileNotFoundError。
    """
    path = _genre_dir(genre_id) / "template.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"题材模板不存在: {genre_id} ({path})")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"题材模板格式错误（非映射）: {genre_id}")
    return data


def list_genres() -> list:
    """返回全部 genre_id 列表（读 index.json 登记表）。"""
    if not _INDEX_FILE.is_file():
        return []
    with _INDEX_FILE.open("r", encoding="utf-8") as f:
        index = json.load(f)
    return [g["genre_id"] for g in index.get("genres", [])]


def _is_placeholder(value: str) -> bool:
    s = str(value).strip().lower()
    if not s:
        return True
    return any(tok in s for tok in _PLACEHOLDER_TOKENS)


def _check_value(label: str, value, errors: list) -> None:
    """递归检查某个值是否"已填且无占位符"。空容器/空串/占位符 → 报错。"""
    if value is None:
        errors.append(f"{label} 为空（未填）")
        return
    if isinstance(value, str):
        if _is_placeholder(value):
            errors.append(f"{label} 含未填占位符或为空: {value!r}")
        return
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            errors.append(f"{label} 为空列表（未填）")
            return
        for i, item in enumerate(value):
            _check_value(f"{label}[{i}]", item, errors)
        return
    if isinstance(value, dict):
        if len(value) == 0:
            errors.append(f"{label} 为空映射（未填）")
            return
        for k, v in value.items():
            _check_value(f"{label}.{k}", v, errors)
        return
    # 数字/布尔等标量：存在即视为已填


def validate_template(t: dict) -> Tuple[bool, list]:
    """校验题材模板：schema 必填 + 占位符未填检测。

    返回 (ok, errors)；ok 为 True 当且仅当 errors 为空。
    """
    errors: list = []

    if not isinstance(t, dict):
        return False, ["模板不是 dict"]

    # hard_constraints 必须存在（可为空列表，§0 仅高风险题材填）
    if "hard_constraints" not in t:
        errors.append("缺字段 hard_constraints")
    elif not isinstance(t["hard_constraints"], list):
        errors.append("hard_constraints 须为列表")
    else:
        # 列表内若有元素，则不得为占位符
        for i, item in enumerate(t["hard_constraints"]):
            _check_value(f"hard_constraints[{i}]", item, errors)

    # 顶层必填字段：存在且非空、无占位符
    for key in _REQUIRED_TOP:
        if key not in t:
            errors.append(f"缺字段 {key}")
            continue
        _check_value(key, t[key], errors)

    # 嵌套必填子字段
    for parent, subkeys in _REQUIRED_SUBFIELDS.items():
        section = t.get(parent)
        if not isinstance(section, dict):
            # 顶层检查已报缺失/类型问题，这里只补子字段缺失
            if parent in t and not isinstance(section, dict):
                errors.append(f"{parent} 须为映射")
            continue
        for sub in subkeys:
            if sub not in section:
                errors.append(f"缺字段 {parent}.{sub}")
            else:
                _check_value(f"{parent}.{sub}", section[sub], errors)

    return (len(errors) == 0), errors


def validate_stack(ids) -> bool:
    """题材叠加校验：选 1 个主 + 若干副，总数 1..STACK_MAX 视为合法。

    空列表非法；超过 STACK_MAX（默认 3）非法。重复按去重后计数。
    """
    if not ids:
        return False
    unique = list(dict.fromkeys(ids))
    return 1 <= len(unique) <= STACK_MAX
