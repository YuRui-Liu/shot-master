"""JSON 容错修复链（spec §6.2）。专给 LLM 输出回收用。

按顺序尝试：strict json → 剥代码栅 → json5（如可用）→ regex 兜底。
任一步成功立即返回。json5 包未装时静默跳过该步，靠 regex 兜底。
全失败时 raw_text 保留以供落盘 raw 文件。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

try:
    import json5 as _json5
    _HAS_JSON5 = True
except ImportError:
    _json5 = None
    _HAS_JSON5 = False


@dataclass
class RepairResult:
    ok: bool
    obj: Any | None = None
    steps: list[str] = field(default_factory=list)
    raw: str = ""              # 原始 text；ok=False 时供落盘
    error: str = ""


_CODEFENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.IGNORECASE)


def _strip_codefence(text: str) -> str:
    """剥 ```json ... ``` 包裹；找第一个 '{' 到最末 '}'。"""
    t = text.strip()
    t = _CODEFENCE_RE.sub("", t).strip()
    # 截取第一个 { 到最末 }
    i = t.find("{")
    j = t.rfind("}")
    if i >= 0 and j > i:
        return t[i:j + 1]
    return t


def _regex_fixup(text: str) -> str:
    """兜底修复：中文标点 / 尾逗号。"""
    # 中文冒号 / 引号 → ASCII
    text = text.replace("：", ":").replace("，", ",")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    # 去除尾逗号 ,] → ] / ,} → }
    text = re.sub(r",(\s*[\]\}])", r"\1", text)
    return text


def repair_json_text(raw: str) -> RepairResult:
    """执行修复链；返回 RepairResult。"""
    steps: list[str] = []
    err = ""

    # Step 1: strict json
    try:
        obj = json.loads(raw)
        return RepairResult(ok=True, obj=obj, steps=["strict"], raw=raw)
    except Exception as e:
        err = str(e)

    # Step 2: 剥代码栅
    cand = _strip_codefence(raw)
    steps.append("strip_codefence")
    try:
        obj = json.loads(cand)
        return RepairResult(ok=True, obj=obj, steps=steps, raw=raw)
    except Exception as e:
        err = str(e)

    # Step 3: json5（如可用）
    if _HAS_JSON5:
        try:
            obj = _json5.loads(cand)
            steps.append("json5")
            return RepairResult(ok=True, obj=obj, steps=steps, raw=raw)
        except Exception as e:
            err = str(e)

    # Step 4: regex 兜底 → 再 strict
    fixed = _regex_fixup(cand)
    steps.append("regex")
    try:
        obj = json.loads(fixed)
        return RepairResult(ok=True, obj=obj, steps=steps, raw=raw)
    except Exception as e:
        err = str(e)

    return RepairResult(ok=False, obj=None, steps=steps, raw=raw, error=err)
