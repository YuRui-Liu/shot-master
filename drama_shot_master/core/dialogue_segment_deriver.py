"""按 mp4 路径匹配 cfg.video_tasks 派生 DialogueSegment 列表。

供 SoundtrackEditor 在调 facade.prepare_session 前调用，让 mix 阶段跳过 Demucs 盲分离。
匹配不到（用户手工导入 MP4 / VideoTask 无 audio / 字段缺失）→ 返回 []，
caller 不传 dialogue_segments → mix 阶段按原回退路径走 Demucs（零回归）。

零外部依赖（除 DialogueSegment），可单测。
"""
from __future__ import annotations

from sound_track_agent.session import DialogueSegment


def derive_dialogue_segments(cfg, mp4_path: str) -> list[DialogueSegment]:
    """扫 cfg.video_tasks，找 last_result == mp4_path 的第一个 task，
    从其 timeline.audios 派生 DialogueSegment（frame → 秒）。

    所有失败路径（无 video_tasks / 无匹配 / 缺字段 / fps=0）都安全返回空列表，不抛。
    """
    video_tasks = getattr(cfg, "video_tasks", None) or []
    for task in video_tasks:
        if str(task.get("last_result", "")) != str(mp4_path):
            continue
        timeline = task.get("timeline") or {}
        try:
            fps = float(timeline.get("frame_rate", 24.0)) or 24.0
        except (TypeError, ValueError):
            fps = 24.0
        audios = timeline.get("audios") or []
        result: list[DialogueSegment] = []
        for a in audios:
            audio_path = a.get("audio_path") if isinstance(a, dict) else None
            if not audio_path:
                continue
            try:
                result.append(DialogueSegment(
                    audio_path=str(audio_path),
                    t_start=float(a["start_frame"]) / fps,
                    duration=float(a["length_frames"]) / fps,
                ))
            except (TypeError, ValueError, KeyError):
                continue
        return result
    return []
