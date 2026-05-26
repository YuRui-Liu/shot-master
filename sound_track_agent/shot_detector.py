"""成片 MP4 → 镜头切点（PySceneDetect）。输出 Shot 列表喂 segment_planner。"""
from __future__ import annotations

from pathlib import Path

from scenedetect import detect, ContentDetector

from sound_track_agent.segment_planner import Shot


def _video_duration_seconds(video_path) -> float:
    """用 cv2 读出视频时长（秒）。读不到则返回 0.0。"""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    return float(n / fps) if fps else 0.0


def detect_shots(video_path, threshold: float = 27.0) -> list[Shot]:
    """检测镜头切点 → Shot 列表（index 从 0、t_start/t_end 单位秒）。

    无切点（单镜头）时回退为整段一个 Shot。
    """
    scenes = detect(str(video_path), ContentDetector(threshold=threshold))
    if not scenes:
        return [Shot(index=0, t_start=0.0,
                     t_end=_video_duration_seconds(video_path))]
    return [
        Shot(index=i, t_start=float(start.seconds), t_end=float(end.seconds))
        for i, (start, end) in enumerate(scenes)
    ]
