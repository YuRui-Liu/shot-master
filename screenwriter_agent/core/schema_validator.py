"""教学系列 02 schema 校验 + 字段补全。spec §6.2 Step 5/6。

返回 (validated_dict, [ValidationWarn])。critical 字段缺失抛 ValueError。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from screenwriter_agent.models.storyboard_schema import Storyboard


@dataclass
class ValidationWarn:
    path: str
    issue: str
    severity: str = "warning"          # info / warning / error / critical
    suggested_fix: str = ""
    auto_fix_applied: bool = False


_MIN_STYLE_PROMPT_LEN = 30
_MIN_APPEARANCE_LEN = 10


def validate_storyboard(obj: Any,
                        fallback_title: str = "",
                        default_aspect_ratio: str = "9:16",
                        default_fps: int = 24,
                        default_shot_duration: float = 3.0,
                        default_global_style: str = "") -> tuple[dict, list[ValidationWarn]]:
    """字段补全 + Schema 校验。critical 缺失抛 ValueError。"""
    if not isinstance(obj, dict):
        raise ValueError("storyboard must be a JSON object")

    warns: list[ValidationWarn] = []

    # 顶层字段补全
    if not obj.get("title"):
        obj["title"] = fallback_title or "未命名分镜"
        warns.append(ValidationWarn(
            "title", "缺 title，已用剧本/默认值兜底",
            severity="warning", auto_fix_applied=True))

    obj.setdefault("aspectRatio", default_aspect_ratio)
    obj.setdefault("fps", default_fps)
    obj.setdefault("globalStyle", default_global_style)
    obj.setdefault("characters", [])

    shots = obj.get("shots") or []
    if not shots:
        raise ValueError("storyboard.shots is empty (critical)")

    # 镜头逐条补全
    for i, sh in enumerate(shots):
        if not isinstance(sh, dict):
            raise ValueError(f"shots[{i}] must be an object")
        if not sh.get("shotId"):
            sh["shotId"] = f"S01_{i + 1}"
            warns.append(ValidationWarn(
                f"shots[{i}].shotId", "缺 shotId，已按位置补",
                severity="info", auto_fix_applied=True))
        if not sh.get("description"):
            warns.append(ValidationWarn(
                f"shots[{i}].description", "缺 description",
                severity="error"))
        sh.setdefault("duration", default_shot_duration)
        sh.setdefault("composition", "")
        sp = sh.get("stylePrompt", "")
        if len(sp) < _MIN_STYLE_PROMPT_LEN:
            warns.append(ValidationWarn(
                f"shots[{i}].stylePrompt",
                f"过短（<{_MIN_STYLE_PROMPT_LEN} 字），可能锁不住画风",
                severity="warning"))

    # 角色字段
    for i, ch in enumerate(obj["characters"]):
        if not isinstance(ch, dict) or not ch.get("name"):
            warns.append(ValidationWarn(
                f"characters[{i}].name", "无 name", severity="error"))
        if len(ch.get("appearance", "")) < _MIN_APPEARANCE_LEN:
            warns.append(ValidationWarn(
                f"characters[{i}].appearance", "appearance 过短", severity="warning"))

    # totalDuration 推断
    if not obj.get("totalDuration"):
        obj["totalDuration"] = sum(float(s.get("duration", default_shot_duration))
                                   for s in shots)
        warns.append(ValidationWarn(
            "totalDuration", "缺字段，按 shots 时长求和补",
            severity="info", auto_fix_applied=True))

    # pydantic 二次校验（类型）
    sb = Storyboard.model_validate(obj)
    return sb.model_dump(), warns
