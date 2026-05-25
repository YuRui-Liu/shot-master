"""总风格 + 段落情绪 + 时长 → ACE-Step BGM-only prompt。纯模板，可单测。"""
from __future__ import annotations

from typing import Optional

from sound_track_agent.session import EmotionTag


def _tempo_hint(arousal: float) -> str:
    """情绪唤起度 → BPM 区间提示。"""
    if arousal >= 0.66:
        return "110-140 BPM"
    if arousal >= 0.33:
        return "85-110 BPM"
    return "60-80 BPM"


def compose_music_prompt(global_style: str,
                         emotion: Optional[EmotionTag],
                         duration: float) -> str:
    """组装一段 BGM-only 的 ACE-Step prompt。

    确定性：相同输入永远得到相同文本（便于缓存与测试）。
    """
    labels = emotion.labels if emotion else []
    arousal = emotion.arousal if emotion else 0.3
    mood = ", ".join(labels) if labels else "neutral, restrained"
    lines = [
        "[BGM-only]",
        f"Overall style: {global_style}",
        f"Mood: {mood}",
        f"Tempo: {_tempo_hint(arousal)}",
        f"Length: {duration:.1f}s",
        "Mix: dialogue-friendly, leave headroom for speech, no vocal, no lyrics",
    ]
    return "\n".join(lines)
