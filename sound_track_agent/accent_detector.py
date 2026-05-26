"""动作爆点检测：光流运动序列 → 显著峰值 → AccentPoint。

find_accent_peaks 是纯逻辑（可单测）；_motion_series/detect_accents 接 cv2（Task 3）。
"""
from __future__ import annotations

from statistics import mean, pstdev

from sound_track_agent.session import AccentPoint


def find_accent_peaks(motion: list[float],
                      fps: float,
                      *,
                      k: float = 1.0,
                      min_gap_s: float = 0.3) -> list[AccentPoint]:
    """从逐帧运动强度序列中找显著爆点。

    motion[i] = 第 i→i+1 帧运动量，时间约 (i+1)/fps。
    判据：motion[i] 是局部极大且 > mean + k*std。相邻爆点间隔 < min_gap_s
    时只保留更强者。intensity = motion[i] / max(motion)（0-1）。
    """
    n = len(motion)
    if n == 0 or fps <= 0:
        return []
    mu = mean(motion)
    sd = pstdev(motion)
    thresh = mu + k * sd
    peak_max = max(motion)
    if peak_max <= 0:
        return []

    cands: list[tuple[int, float]] = []
    for i in range(n):
        left = motion[i - 1] if i > 0 else float("-inf")
        right = motion[i + 1] if i < n - 1 else float("-inf")
        if motion[i] > thresh and motion[i] >= left and motion[i] >= right:
            cands.append((i, motion[i]))

    min_gap_frames = min_gap_s * fps
    chosen: list[int] = []
    for i, _v in sorted(cands, key=lambda c: c[1], reverse=True):
        if all(abs(i - j) >= min_gap_frames for j in chosen):
            chosen.append(i)

    pts = [
        AccentPoint(t=(i + 1) / fps, intensity=motion[i] / peak_max,
                    confirmed=False)
        for i in sorted(chosen)
    ]
    return pts


def _motion_series(video_path) -> tuple[list[float], float]:
    """逐帧 Farneback 光流的平均幅值序列。返回 (motion, fps)。

    motion[i] = 第 i 帧到第 i+1 帧的平均运动幅值。
    """
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    motion: list[float] = []
    prev = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.sqrt((flow ** 2).sum(-1)).mean()
            motion.append(float(mag))
        prev = gray
    cap.release()
    return motion, float(fps)


def detect_accents(video_path,
                   *,
                   k: float = 1.0,
                   min_gap_s: float = 0.3) -> list:
    """成片 MP4 → 动作爆点 AccentPoint 列表。"""
    motion, fps = _motion_series(video_path)
    return find_accent_peaks(motion, fps, k=k, min_gap_s=min_gap_s)
