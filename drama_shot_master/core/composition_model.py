"""成片合成数据模型：有序片段 + 切口转场参数。Qt-free，可单测。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from secrets import token_hex

_DEFAULT_TRANSITION = "dissolve"
_DEFAULT_DURATION = 0.5
_DUR_MIN, _DUR_MAX = 0.3, 2.0


def _gen_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


@dataclass
class ReelClip:
    clip_id: str
    path: str
    keep: bool = True
    in_point: float | None = None
    out_point: float | None = None
    duration: float = 0.0
    auto_transition: str | None = None
    auto_duration: float | None = None
    user_transition: str | None = None
    user_duration: float | None = None
    locked: bool = False
    cv_scores: dict = field(default_factory=dict)

    @classmethod
    def new(cls, path: str, duration: float = 0.0, **kw) -> "ReelClip":
        return cls(clip_id=_gen_id(), path=str(path), duration=float(duration), **kw)

    def effective_transition(self) -> str:
        return self.user_transition or self.auto_transition or _DEFAULT_TRANSITION

    def effective_duration(self) -> float:
        d = self.user_duration if self.user_duration is not None else self.auto_duration
        if d is None:
            d = _DEFAULT_DURATION
        return max(_DUR_MIN, min(_DUR_MAX, float(d)))

    def trimmed_duration(self) -> float:
        start = self.in_point if self.in_point is not None else 0.0
        end = self.out_point if self.out_point is not None else self.duration
        return max(0.0, end - start)

    def to_dict(self) -> dict:
        return {
            "clip_id": self.clip_id, "path": self.path, "keep": self.keep,
            "in_point": self.in_point, "out_point": self.out_point,
            "duration": self.duration,
            "auto_transition": self.auto_transition, "auto_duration": self.auto_duration,
            "user_transition": self.user_transition, "user_duration": self.user_duration,
            "locked": self.locked, "cv_scores": self.cv_scores,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReelClip":
        return cls(
            clip_id=str(d.get("clip_id") or _gen_id()),
            path=str(d.get("path") or ""),
            keep=bool(d.get("keep", True)),
            in_point=d.get("in_point"),
            out_point=d.get("out_point"),
            duration=float(d["duration"]) if d.get("duration") is not None else 0.0,
            auto_transition=d.get("auto_transition"),
            auto_duration=d.get("auto_duration"),
            user_transition=d.get("user_transition"),
            user_duration=d.get("user_duration"),
            locked=bool(d.get("locked", False)),
            cv_scores=d.get("cv_scores") or {},
        )


@dataclass
class CompositionModel:
    clips: list[ReelClip] = field(default_factory=list)
    fps: int = 30
    width: int = 1920
    height: int = 1080
    pix_fmt: str = "yuv420p"
    output_prefix: str = "compose"

    def kept_clips(self) -> list[ReelClip]:
        return [c for c in self.clips if c.keep]

    def get(self, clip_id: str) -> ReelClip | None:
        return next((c for c in self.clips if c.clip_id == clip_id), None)

    def reorder_clips(self, ordered_ids: list[str]) -> None:
        index = {c.clip_id: c for c in self.clips}
        self.clips = [index[i] for i in ordered_ids if i in index] + \
                     [c for c in self.clips if c.clip_id not in set(ordered_ids)]

    def update_clip(self, clip_id: str, **fields) -> None:
        c = self.get(clip_id)
        if c is None:
            return
        for k, v in fields.items():
            if hasattr(c, k):
                setattr(c, k, v)

    def validate(self) -> tuple[bool, str]:
        kept = self.kept_clips()
        if not kept:
            return False, "至少需要保留 1 个片段"
        warns = []
        for i, c in enumerate(kept[:-1]):
            if c.trimmed_duration() < c.effective_duration():
                warns.append(f"片段#{i+1} 时长不足转场时长，将降级为硬切")
        return True, ("；".join(warns) if warns else "ok")

    def to_dict(self) -> dict:
        return {
            "clips": [c.to_dict() for c in self.clips],
            "fps": self.fps, "width": self.width, "height": self.height,
            "pix_fmt": self.pix_fmt, "output_prefix": self.output_prefix,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CompositionModel":
        d = d or {}
        return cls(
            clips=[ReelClip.from_dict(x) for x in (d.get("clips") or [])],
            fps=int(d.get("fps") or 30),
            width=int(d.get("width") or 1920),
            height=int(d.get("height") or 1080),
            pix_fmt=str(d.get("pix_fmt") or "yuv420p"),
            output_prefix=str(d.get("output_prefix") or "compose"),
        )
