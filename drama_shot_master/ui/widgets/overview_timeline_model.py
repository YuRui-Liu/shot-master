"""数据派生：4 个数据源 → 统一 _Cue 列表。无 IO，可单测。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class _Cue:
    track: Literal["video", "bgm", "sfx", "dialogue"]
    t_start: float
    t_end: float
    label: str
    seg_index: int


def _label_from_prompt(text: str, max_chars: int = 8) -> str:
    t = (text or "").strip()
    return t[:max_chars] if t else ""


def derive_video_cues(shot_boundaries: list[float],
                      total_duration: float) -> list[_Cue]:
    if total_duration <= 0:
        return []
    if not shot_boundaries:
        return [_Cue("video", 0.0, total_duration, "", 0)]
    edges = [0.0] + list(shot_boundaries) + [total_duration]
    cues = []
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        if b > a:
            cues.append(_Cue("video", float(a), float(b), "", i))
    return cues


def derive_bgm_cues(bgm_session) -> list[_Cue]:
    if bgm_session is None:
        return []
    out = []
    for i, seg in enumerate(getattr(bgm_session, "segments", []) or []):
        prompt = getattr(seg, "music_prompt", "") or ""
        label = (_label_from_prompt(prompt, 8)
                 if seg.chosen_candidate is not None else "(未选)")
        out.append(_Cue("bgm", float(seg.t_start), float(seg.t_end),
                        label, i))
    return out


def derive_sfx_cues(sfx_session) -> list[_Cue]:
    if sfx_session is None:
        return []
    out = []
    for i, shot in enumerate(getattr(sfx_session, "shots", []) or []):
        if not getattr(shot, "enabled", True):
            continue
        if getattr(shot, "status", "") != "generated":
            continue
        label = _label_from_prompt(getattr(shot, "prompt_short", ""), 6)
        out.append(_Cue("sfx", float(shot.t_start),
                        float(shot.t_start + shot.duration),
                        label, i))
    return out


def derive_dialogue_cues(timeline_dict: Optional[dict],
                          frame_rate: float = 24.0) -> list[_Cue]:
    if not timeline_dict:
        return []
    audios = timeline_dict.get("audios") or []
    fps = float(timeline_dict.get("frame_rate", frame_rate)) or frame_rate
    out = []
    for i, a in enumerate(audios):
        try:
            start_f = float(a.get("start_frame", 0))
            length_f = float(a.get("length_frames", 0))
        except (TypeError, ValueError):
            continue
        if length_f <= 0:
            continue
        t_start = start_f / fps
        t_end = t_start + length_f / fps
        path = a.get("audio_path") or ""
        label = (path.rsplit("/", 1)[-1].rsplit(".", 1)[0][:6]
                 if path else f"对白{i}")
        out.append(_Cue("dialogue", t_start, t_end, label, i))
    return out


def derive_total_duration(*, bgm_session, sfx_session,
                          dialogue_audios: Optional[dict],
                          video_duration: float = 0.0) -> float:
    candidates = [float(video_duration)]
    if bgm_session is not None:
        for s in getattr(bgm_session, "segments", []) or []:
            candidates.append(float(s.t_end))
    if sfx_session is not None:
        for s in getattr(sfx_session, "shots", []) or []:
            candidates.append(float(s.t_start + s.duration))
    if dialogue_audios:
        fps = float(dialogue_audios.get("frame_rate", 24.0)) or 24.0
        for a in dialogue_audios.get("audios") or []:
            try:
                candidates.append(
                    (float(a["start_frame"]) + float(a["length_frames"])) / fps)
            except (TypeError, ValueError, KeyError):
                continue
    pos = max([c for c in candidates if c > 0], default=0.0)
    return pos if pos > 0 else 30.0
