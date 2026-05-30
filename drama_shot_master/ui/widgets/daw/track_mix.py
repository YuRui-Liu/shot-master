"""三轨混音状态（原声/BGM/SFX）：mute/solo/volume + 独奏解算 + mix.json 持久化。

纯逻辑，无 Qt 依赖，可单测。dialogue 轨无独立音频，不在此管理。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TRACKS = ("video", "bgm", "sfx")


@dataclass
class _TrackState:
    muted: bool = False
    soloed: bool = False
    volume: float = 1.0


class TrackMixState:
    def __init__(self):
        self._st = {t: _TrackState() for t in TRACKS}

    def set_muted(self, track: str, on: bool) -> None:
        self._st[track].muted = bool(on)

    def is_muted(self, track: str) -> bool:
        return self._st[track].muted

    def set_soloed(self, track: str, on: bool) -> None:
        self._st[track].soloed = bool(on)

    def is_soloed(self, track: str) -> bool:
        return self._st[track].soloed

    def set_volume(self, track: str, v: float) -> None:
        self._st[track].volume = max(0.0, min(1.5, float(v)))

    def volume(self, track: str) -> float:
        return self._st[track].volume

    def _any_solo(self) -> bool:
        return any(s.soloed for s in self._st.values())

    def audible(self, track: str) -> bool:
        s = self._st[track]
        if s.muted:
            return False
        if self._any_solo():
            return s.soloed
        return True

    def effective_volume(self, track: str) -> float:
        return self._st[track].volume if self.audible(track) else 0.0

    def to_dict(self) -> dict:
        return {t: {"muted": s.muted, "soloed": s.soloed, "volume": s.volume}
                for t, s in self._st.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "TrackMixState":
        m = cls()
        for t in TRACKS:
            e = (d or {}).get(t) or {}
            m._st[t] = _TrackState(
                muted=bool(e.get("muted", False)),
                soloed=bool(e.get("soloed", False)),
                volume=max(0.0, min(1.5, float(e.get("volume", 1.0)))))
        return m


def _mix_path(work_dir) -> Path:
    return Path(work_dir) / "mix.json"


def load_mix(work_dir) -> TrackMixState:
    p = _mix_path(work_dir)
    if not p.is_file():
        return TrackMixState()
    try:
        return TrackMixState.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return TrackMixState()


def save_mix(work_dir, state: TrackMixState) -> None:
    p = _mix_path(work_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                 encoding="utf-8")
