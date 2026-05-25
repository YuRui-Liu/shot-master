"""提示词反推优化：构造模型请求 + 解析 JSON 响应。

Qt-free，可单测。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from drama_shot_master.core.video_timeline_model import TimelineModel

DEFAULT_REFINE_META_PROMPT_PATH = Path("templates/ltx_refine_meta_prompt.md")


class RefineParseError(Exception):
    """模型返回无法解析为预期 JSON。"""


@dataclass
class RefineRequest:
    images: list[Path]
    user_message: str
    seg_ids: list[str]


@dataclass
class RefineResult:
    global_prompt: Optional[str]
    segment_locals: list[tuple[str, str]]   # [(seg_id, refined_local)]
    warnings: list[str] = field(default_factory=list)


def load_refine_meta_prompt(path: str = "") -> str:
    """path 空 → bundled 默认；否则读自定义路径。缺失 → FileNotFoundError。"""
    p = Path(path) if path else DEFAULT_REFINE_META_PROMPT_PATH
    return p.read_text(encoding="utf-8")


def build_refine_request(model: TimelineModel) -> RefineRequest:
    """收集 global + 所有段 → 模型输入。

    images 仅含 image 段的 image_path（按段序）；seg_ids 含全部段。
    """
    images: list[Path] = []
    seg_ids: list[str] = []
    lines: list[str] = [
        f"GLOBAL PROMPT (current): {model.global_prompt!r}",
        f"Frame rate: {model.frame_rate} fps",
        "SEGMENTS:",
    ]
    fr = max(model.frame_rate, 1)
    for i, seg in enumerate(model.segments):
        seg_ids.append(seg.seg_id)
        dur = seg.length_frames / fr
        has_img = seg.segment_type == "image" and seg.image_path is not None
        if has_img:
            note = f", attached_image=#{len(images)}"
            images.append(seg.image_path)
        else:
            note = ""
        lines.append(
            f"[seg {i}] type={seg.segment_type}, "
            f"has_image={'yes' if has_img else 'no'}, "
            f"duration={dur:.2f}s, current_local={seg.local_prompt!r}{note}"
        )
    return RefineRequest(images=images,
                         user_message="\n".join(lines),
                         seg_ids=seg_ids)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text.split("\n")
    if body and body[0].startswith("```"):
        body = body[1:]
    if body and body[-1].strip() == "```":
        body = body[:-1]
    return "\n".join(body).strip()


def parse_refine_response(raw: str, seg_ids: list[str]) -> RefineResult:
    """解析模型 JSON 输出，把 index 映射回 seg_id。失败 → RefineParseError。"""
    text = _strip_code_fence(raw)
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        raise RefineParseError(
            f"无法解析模型返回为 JSON：{raw[:300]}") from e
    if not isinstance(obj, dict):
        raise RefineParseError(f"模型返回不是 JSON 对象：{raw[:300]}")

    warnings: list[str] = []
    gp = obj.get("global_prompt")
    global_prompt = gp if isinstance(gp, str) and gp.strip() else None

    segment_locals: list[tuple[str, str]] = []
    seg_items = obj.get("segments")
    if isinstance(seg_items, list):
        for item in seg_items:
            if not isinstance(item, dict):
                warnings.append(f"跳过非对象 segment 项：{str(item)[:80]}")
                continue
            idx = item.get("index")
            local = item.get("local_prompt")
            if not isinstance(idx, int) or not isinstance(local, str):
                warnings.append(f"跳过格式错误 segment 项：{str(item)[:80]}")
                continue
            if idx < 0 or idx >= len(seg_ids):
                warnings.append(f"段 index={idx} 越界，跳过")
                continue
            segment_locals.append((seg_ids[idx], local))
    return RefineResult(global_prompt=global_prompt,
                        segment_locals=segment_locals, warnings=warnings)
