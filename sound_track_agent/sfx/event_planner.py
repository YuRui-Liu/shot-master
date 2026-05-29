"""LLM 多帧检测：判断每个 shot 是否需要 SFX + 生成 prompt_short。

复用 emotion_tagger 同款的 provider.generate(frames, sys, usr) 接口。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from sound_track_agent.sfx.session import SFXShot, SFXSession


_SFX_SYS = """你是短剧音效设计助手。我会给你一个镜头的若干帧画面，请判断是否需要 Foley 音效（开门/脚步/打击/物体掉落/衣服摩擦/环境音等），并给出生成提示。

输出严格 JSON 格式（不要带 markdown 代码块包裹）：
{"needs_sfx": bool, "prompt_short": "简短中文描述（5-20 字）", "duration_hint": 浮点秒数}

判定规则：
- 镜头主要是对话/静态特写 / 信息字幕 → needs_sfx=false
- 有可见动作 / 物体运动 / 场景转换 / 明显环境氛围 → needs_sfx=true
- prompt_short 例如："门吱呀打开，脚步进屋" / "马蹄声从远到近" / "玻璃杯碎裂在地" / "雨夜雷声远处"
- duration_hint 通常 = 镜头实际时长（我会告诉你），上限 15 秒
"""

_SFX_USR_TMPL = "镜头实际时长 {shot_dur:.1f} 秒。请判定是否需要 SFX 并给出简短描述。"


def _strip_code_fence(text: str) -> str:
    """剥掉可能的 ```json ... ``` 包裹。"""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def plan_one_shot(provider, shot: SFXShot, frame_paths: list[Path]) -> SFXShot:
    """对单镜头跑 LLM，写回 SFXShot 状态。"""
    if not frame_paths:
        shot.status = "skipped"
        return shot
    try:
        raw = provider.generate(
            [Path(p) for p in frame_paths],
            _SFX_SYS,
            _SFX_USR_TMPL.format(shot_dur=shot.shot_duration))
        data = json.loads(_strip_code_fence(raw))
        needs = bool(data.get("needs_sfx", False))
        prompt = str(data.get("prompt_short", "")).strip()
        dur = float(data.get("duration_hint", shot.shot_duration))
    except (json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError):
        shot.status = "skipped"
        return shot
    if not needs or not prompt:
        shot.status = "skipped"
        return shot
    shot.prompt_short = prompt
    shot.duration = max(1.0, min(15.0, dur))
    shot.status = "planned"
    return shot


def plan_all(session: SFXSession, provider, *,
             frames_provider: Callable[[SFXShot, int], list[Path]],
             frames_per_shot: int = 3) -> None:
    """对所有 status=pending 的 shot 调 plan_one_shot；任一失败不抛。"""
    for shot in session.shots:
        if shot.status != "pending":
            continue
        try:
            frames = frames_provider(shot, frames_per_shot)
            plan_one_shot(provider, shot, frames)
        except Exception:
            shot.status = "skipped"
    session.sfx_planned = True
