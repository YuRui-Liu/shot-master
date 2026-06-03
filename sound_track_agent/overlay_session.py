"""动态多子轨叠加片段模型：框选生成的 BGM/SFX 片段，与固定轨整段配乐并存。

独立 overlay.json，纯逻辑无 Qt。自动分轨：新片段放入同 kind 内第一条无时间
重叠的 lane，否则新建 lane。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class OverlaySegment:
    id: str
    kind: str
    lane: int
    t_start: float
    t_end: float
    prompt: str
    audio_path: str = ""
    volume: float = 1.0
    enabled: bool = True
    # 生成状态：pending|generating|generated|failed
    status: str = "generated"

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "lane": self.lane,
                "t_start": self.t_start, "t_end": self.t_end,
                "prompt": self.prompt, "audio_path": self.audio_path,
                "volume": self.volume, "enabled": self.enabled,
                "status": self.status}

    @classmethod
    def from_dict(cls, d: dict) -> "OverlaySegment":
        return cls(
            id=d["id"], kind=d["kind"], lane=int(d["lane"]),
            t_start=float(d["t_start"]), t_end=float(d["t_end"]),
            prompt=d.get("prompt", ""), audio_path=d.get("audio_path", ""),
            volume=float(d.get("volume", 1.0)),
            enabled=bool(d.get("enabled", True)),
            status=d.get("status", "generated"))   # 旧数据无 status → 迁移


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1


class OverlaySession:
    def __init__(self, segments: Optional[list] = None):
        self.segments: list[OverlaySegment] = list(segments or [])

    def _assign_lane(self, kind: str, t_start: float, t_end: float) -> int:
        same = [s for s in self.segments if s.kind == kind]
        max_lane = max((s.lane for s in same), default=-1)
        for lane in range(max_lane + 1):
            clash = any(_overlaps(t_start, t_end, s.t_start, s.t_end)
                        for s in same if s.lane == lane)
            if not clash:
                return lane
        return max_lane + 1

    def add(self, kind: str, t_start: float, t_end: float, prompt: str,
            *, seg_id: str, status: str = "generated") -> OverlaySegment:
        lane = self._assign_lane(kind, t_start, t_end)
        seg = OverlaySegment(id=seg_id, kind=kind, lane=lane,
                             t_start=float(t_start), t_end=float(t_end),
                             prompt=prompt, status=status)
        self.segments.append(seg)
        return seg

    def remove(self, seg_id: str) -> bool:
        for i, s in enumerate(self.segments):
            if s.id == seg_id:
                del self.segments[i]
                return True
        return False

    def get(self, seg_id: str) -> Optional[OverlaySegment]:
        return next((s for s in self.segments if s.id == seg_id), None)

    def lanes_for(self, kind: str) -> int:
        lanes = [s.lane for s in self.segments if s.kind == kind]
        return (max(lanes) + 1) if lanes else 0

    def segments_in_lane(self, kind: str, lane: int) -> list:
        return [s for s in self.segments if s.kind == kind and s.lane == lane]

    def to_dict(self) -> dict:
        return {"segments": [s.to_dict() for s in self.segments]}

    @classmethod
    def from_dict(cls, d: dict) -> "OverlaySession":
        return cls([OverlaySegment.from_dict(s)
                    for s in (d or {}).get("segments", [])])


def _overlay_path(work_dir) -> Path:
    return Path(work_dir) / "overlay.json"


def load_overlay(work_dir) -> OverlaySession:
    p = _overlay_path(work_dir)
    if not p.is_file():
        return OverlaySession()
    try:
        return OverlaySession.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return OverlaySession()


def save_overlay(work_dir, session: OverlaySession) -> None:
    """原子写：先写 .tmp 再 os.replace，避免并发请求写坏 overlay.json。"""
    import os
    p = _overlay_path(work_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(str(tmp), str(p))
