"""段落代表帧 → 情绪标签（豆包 vision）。解析失败降级中性，不中断管线。"""
from __future__ import annotations

import json
from pathlib import Path

from sound_track_agent.session import EmotionTag

_NEUTRAL = EmotionTag(labels=[], valence=0.0, arousal=0.3, intensity=0.5)


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_emotion(raw: str) -> EmotionTag:
    """解析模型 JSON → EmotionTag；任何异常降级为中性。"""
    try:
        obj = json.loads(_strip_code_fence(raw))
        if not isinstance(obj, dict):
            return _NEUTRAL
        labels = obj.get("labels") or []
        if not isinstance(labels, list):
            labels = []
        return EmotionTag(
            labels=[str(x) for x in labels],
            valence=float(obj.get("valence", 0.0)),
            arousal=float(obj.get("arousal", 0.3)),
            intensity=float(obj.get("intensity", 0.5)),
        )
    except (ValueError, TypeError):
        return _NEUTRAL


_SYS = ("你是视频配乐的情绪分析助手。仔细观察画面，结合作品总体风格，"
        "判断这一段落的情绪基调与氛围。")
_USR_TMPL = ('作品总体风格：{style}\n'
             '用 JSON 输出该画面情绪（只输出 JSON）：'
             '{{"labels":[2-4个英文情绪标签], "valence":-1到1小数, '
             '"arousal":0到1小数, "intensity":0到1小数}}')


def tag_emotion(provider, frame_path: Path, global_style: str) -> EmotionTag:
    """用 vision provider 把代表帧判成 EmotionTag。"""
    raw = provider.generate([Path(frame_path)], _SYS,
                            _USR_TMPL.format(style=global_style))
    return _parse_emotion(raw)


def tag_emotion_multi(provider, frame_paths: list[Path],
                      global_style: str) -> EmotionTag:
    """多帧同 prompt 测情绪。复用 _SYS/_USR_TMPL/_parse_emotion；
    provider.generate 原生接受 image list。

    空列表 → _NEUTRAL（不调 provider）。
    解析失败 → _NEUTRAL（不抛）。
    """
    if not frame_paths:
        return _NEUTRAL
    raw = provider.generate(list(frame_paths), _SYS,
                            _USR_TMPL.format(style=global_style))
    return _parse_emotion(raw)
