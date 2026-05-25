"""配乐会话数据结构 + 持久化 + 续跑。零外部依赖，可单测。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Status = Literal["pending", "tagged", "prompted", "generated", "chosen", "aligned"]


@dataclass
class EmotionTag:
    labels: list[str] = field(default_factory=list)
    valence: float = 0.0       # -1..1
    arousal: float = 0.0       # 0..1
    intensity: float = 0.5     # 0..1

    def to_dict(self) -> dict:
        # labels 显式拷贝，避免序列化 dict 与实例共享同一 list
        return {
            "labels": list(self.labels),
            "valence": self.valence,
            "arousal": self.arousal,
            "intensity": self.intensity,
        }


@dataclass
class BGMCandidate:
    path: str
    seed: int
    prompt: str


@dataclass
class AccentPoint:
    t: float
    intensity: float
    confirmed: bool = False


@dataclass
class SegmentScore:
    index: int
    t_start: float
    t_end: float
    shot_ids: list[int] = field(default_factory=list)
    emotion: Optional[EmotionTag] = None
    music_prompt: str = ""
    candidates: list[BGMCandidate] = field(default_factory=list)
    chosen_candidate: Optional[int] = None
    status: Status = "pending"

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "shot_ids": list(self.shot_ids),
            "emotion": (self.emotion.to_dict() if self.emotion else None),
            "music_prompt": self.music_prompt,
            "candidates": [vars(c) for c in self.candidates],
            "chosen_candidate": self.chosen_candidate,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SegmentScore":
        emo = d.get("emotion")
        return cls(
            index=int(d["index"]),
            t_start=float(d["t_start"]),
            t_end=float(d["t_end"]),
            shot_ids=list(d.get("shot_ids", [])),
            emotion=(EmotionTag(**emo) if emo else None),
            music_prompt=d.get("music_prompt", ""),
            candidates=[BGMCandidate(**c) for c in d.get("candidates", [])],
            chosen_candidate=d.get("chosen_candidate"),
            status=d.get("status", "pending"),
        )


@dataclass
class ScoringSession:
    source_mp4: str
    source_hash: str
    global_style: str
    frame_rate: float
    segments: list[SegmentScore] = field(default_factory=list)
    accent_points: list[AccentPoint] = field(default_factory=list)
    output: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source_mp4": self.source_mp4,
            "source_hash": self.source_hash,
            "global_style": self.global_style,
            "frame_rate": self.frame_rate,
            "segments": [s.to_dict() for s in self.segments],
            "accent_points": [vars(a) for a in self.accent_points],
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScoringSession":
        return cls(
            source_mp4=d["source_mp4"],
            source_hash=d["source_hash"],
            global_style=d.get("global_style", ""),
            frame_rate=float(d.get("frame_rate", 24.0)),
            segments=[SegmentScore.from_dict(s) for s in d.get("segments", [])],
            accent_points=[AccentPoint(**a) for a in d.get("accent_points", [])],
            output=d.get("output"),
        )
