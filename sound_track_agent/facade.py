"""配乐 agent 对外门面：GUI 只依赖本模块。

不 import 任何 drama_shot_master；cfg 以鸭子类型读取（getattr）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from sound_track_agent.shot_detector import detect_shots
from sound_track_agent.segment_planner import plan_segments
from sound_track_agent.session import ScoringSession, hash_file


def _read_fps(video_path) -> float:
    """读视频帧率；读不到返回 24.0。"""
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        cap.release()
        return float(fps) if fps and fps > 0 else 24.0
    except Exception:
        return 24.0


def prepare_session(mp4, style: str, work_dir, *,
                    detect: Callable = detect_shots) -> ScoringSession:
    """MP4 → 切镜头 → 段落聚合 → 新建 ScoringSession（快，不调豆包/ACE-Step）。"""
    mp4 = Path(mp4)
    shots = detect(mp4)
    segments = plan_segments(shots)
    return ScoringSession(
        source_mp4=str(mp4),
        source_hash=hash_file(mp4),
        global_style=style,
        frame_rate=_read_fps(mp4),
        segments=segments,
    )
