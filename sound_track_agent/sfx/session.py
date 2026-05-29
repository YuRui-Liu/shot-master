"""SFXShot / SFXCandidate / SFXSession dataclasses + JSON 持久化。

与 BGM ScoringSession 平级、独立持久化到 <work_dir>/sfx_session.json。
粒度按镜头（shot_detector 输出），与 BGM 的 segment 大段粒度不同。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal, Optional


@dataclass
class SFXCandidate:
    """单次 RunningHub stable_audio_3 输出。"""
    path: str                                   # 绝对路径，cache/sfx/<hash>.mp3
    seed: int
    prompt: str                                 # 最终提交给 workflow 的描述（含 Length: Xs）
    score: Optional[float] = None               # MVP 不打分，留字段供 Phase 4c 使用


@dataclass
class SFXShot:
    """与 shot_detector 输出的镜头一一对应。"""
    shot_index: int
    t_start: float
    t_end: float
    representative_frame: str = ""              # 缩略图路径
    prompt_short: str = ""                      # LLM/用户给的短描述
    duration: float = 0.0                       # 默认 = shot_duration，1-15s 之间
    candidates: list[SFXCandidate] = field(default_factory=list)
    chosen_candidate: Optional[int] = None
    status: Literal["pending", "planned", "generated", "skipped"] = "pending"
    next_seed: int = 1
    volume: float = 1.0                         # 0.0-1.5
    enabled: bool = True                        # mix 是否纳入

    @property
    def shot_duration(self) -> float:
        return self.t_end - self.t_start


@dataclass
class SFXSession:
    """SFX 编辑会话；与 BGM ScoringSession 平级独立持久化。"""
    source_mp4: str
    source_hash: str
    frame_rate: float
    shots: list[SFXShot] = field(default_factory=list)
    sfx_planned: bool = False                   # event_planner 已跑过

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Optional["SFXSession"]:
        """损坏 / 不存在返回 None；调用方据此决定新建空 session。"""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            shots_data = data.pop("shots", [])
            shots = []
            for s in shots_data:
                cands = [SFXCandidate(**c) for c in s.pop("candidates", [])]
                shots.append(SFXShot(**s, candidates=cands))
            return cls(**data, shots=shots)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError,
                TypeError, KeyError, ValueError):
            return None
