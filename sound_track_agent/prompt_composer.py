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


def _bpm_from_arousal(arousal: float) -> int:
    """arousal → BPM 整数（取 _tempo_hint 分档的区间中值）。"""
    if arousal >= 0.66:
        return 125          # 110-140 中值
    if arousal >= 0.33:
        return 98           # 85-110 中值
    return 70               # 60-80 中值


def compose_acestep_inputs(global_style: str,
                           emotion: Optional[EmotionTag],
                           duration: float,
                           *,
                           fade_out: bool = False) -> tuple[str, int, float]:
    """生成 ACE-Step 三元组：(tags, bpm, duration)。

    tags 为逗号分隔的纯器乐风格/情绪标签 + 结构标记（贴合 TextEncodeAceStepAudio1.5）。
    bpm/duration 走 ACE-Step 的独立数值节点，不塞进 tags 文字。

    fade_out=False（默认）：不加 `[Quick smooth fade out]` 结构标记，BGM 末尾保持
    完整有声 —— ACE-Step 把该标记解读为 outro 段，会让短段（20-30s）末尾约 25%
    自然衰减到静音，对剧用场景观感不佳。fade_out=True 还原老行为。
    """
    labels = emotion.labels if emotion else []
    arousal = emotion.arousal if emotion else 0.3
    mood = ", ".join(labels) if labels else "neutral, restrained"
    structure = "[Intro soft opening], [Short main theme]"
    if fade_out:
        structure += ", [Quick smooth fade out]"
    tags = (f"Instrumental, no vocals, pure instrumental BGM, "
            f"{global_style}, {mood}, soft dynamics, dialogue-friendly, "
            f"{structure}")
    return tags, _bpm_from_arousal(arousal), float(duration)
