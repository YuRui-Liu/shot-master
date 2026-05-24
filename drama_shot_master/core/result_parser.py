"""从 vision 模型输出文本提取结构化字段。

策略：按 field 名匹配 markdown 标题或行首关键字，取其后的第一个 ``` 代码块。
若某字段缺失，对应属性为空（''/None/[]），不抛错——保留原文供 UI 编辑。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedResult:
    global_prompt: str = ""
    timeline_data: str = ""              # 原始 JSON 字符串
    local_prompts: str = ""
    segment_lengths: list[int] = field(default_factory=list)
    max_frames: Optional[int] = None
    frame_indices: list[int] = field(default_factory=list)
    strengths: list[float] = field(default_factory=list)
    epsilon: Optional[float] = None
    notes: str = ""
    raw: str = ""


def _extract_block(text: str, field_name: str) -> Optional[str]:
    """匹配 '## N. field_name' 或 '## field_name' 或行首 'field_name:'，
    取其后第一个 ``` 代码块的内容。"""
    pattern = re.compile(
        rf"(?:^|\n)(?:#+\s*\d*\.?\s*{re.escape(field_name)}|{re.escape(field_name)}\s*[:：])"
        rf".*?```[a-zA-Z]*\n(.*?)\n```",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _parse_int_list(s: str) -> list[int]:
    parts = re.split(r"[,，\s]+", s.strip())
    out: list[int] = []
    for p in parts:
        if p.strip():
            try:
                out.append(int(p.strip()))
            except ValueError:
                continue
    return out


def _parse_frame_indices(s: str) -> list[int]:
    """支持两种格式：纯逗号列表 / `frame_idx_1 = N` 多行。补足到 5 位。"""
    if "=" in s:
        idx_map: dict[int, int] = {}
        for line in s.splitlines():
            m = re.match(r"\s*frame_idx_(\d+)\s*=\s*(-?\d+)", line)
            if m:
                idx_map[int(m.group(1))] = int(m.group(2))
        out = [idx_map.get(i, -1) for i in range(1, 6)]
    else:
        out = _parse_int_list(s)
    while len(out) < 5:
        out.append(-1)
    return out[:5]


def _parse_strengths(s: str) -> list[float]:
    if "=" in s:
        idx_map: dict[int, float] = {}
        for line in s.splitlines():
            m = re.match(r"\s*strength_(\d+)\s*=\s*(-?\d+\.?\d*)", line)
            if m:
                idx_map[int(m.group(1))] = float(m.group(2))
        out = [idx_map.get(i, 0.0) for i in range(1, 6)]
    else:
        out = [float(x) for x in re.split(r"[,，\s]+", s.strip()) if x]
    while len(out) < 5:
        out.append(0.0)
    return out[:5]


def parse_result(text: str) -> ParsedResult:
    r = ParsedResult(raw=text)

    if (b := _extract_block(text, "global_prompt")):
        r.global_prompt = b
    if (b := _extract_block(text, "timeline_data")):
        r.timeline_data = b
    if (b := _extract_block(text, "local_prompts")):
        r.local_prompts = b
    if (b := _extract_block(text, "segment_lengths")):
        r.segment_lengths = _parse_int_list(b)
    if (b := _extract_block(text, "max_frames")):
        try:
            r.max_frames = int(b.strip())
        except ValueError:
            pass
    if (b := _extract_block(text, "frame_indices")):
        r.frame_indices = _parse_frame_indices(b)
    if (b := _extract_block(text, "strengths")):
        r.strengths = _parse_strengths(b)
    if (b := _extract_block(text, "epsilon")):
        try:
            r.epsilon = float(b.strip())
        except ValueError:
            pass
    # notes 通常是列表，不在代码块里，取标题后到结尾的所有文本
    m = re.search(r"(?:^|\n)#+\s*\d*\.?\s*notes\b(.*?)(?=\n#+\s|\Z)",
                  text, re.DOTALL | re.IGNORECASE)
    if m:
        r.notes = m.group(1).strip()

    return r
