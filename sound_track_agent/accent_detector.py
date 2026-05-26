"""动作爆点检测：光流运动序列 → 显著峰值 → AccentPoint。

find_accent_peaks 是纯逻辑（可单测）；_motion_series/detect_accents 接 cv2（Task 3）。
"""
from __future__ import annotations

from statistics import mean, pstdev

from sound_track_agent.session import AccentPoint

# 光流计算前缩放到的固定宽度（提速；运动相对关系不变）
_FLOW_WIDTH = 256


def find_accent_peaks(motion: list[float],
                      fps: float,
                      *,
                      k: float = 1.0,
                      min_gap_s: float = 0.3,
                      min_intensity: float = 0.0,
                      max_count: int | None = None) -> list[AccentPoint]:
    """从逐帧运动强度序列中找显著爆点。

    motion[i] = 第 i→i+1 帧运动量，时间约 (i+1)/fps。
    判据：motion[i] 是局部极大且 > mean + k*std。相邻爆点间隔 < min_gap_s
    时只保留更强者。intensity = motion[i] / max(motion)（0-1）。
    min_intensity：丢弃归一化强度低于此的弱峰（滤噪）。
    max_count：仅保留强度最高的前 N 个（避免一堆弱点淹没真正爆点）。
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

    # min_gap：按强度降序贪心选，拒绝过近者
    min_gap_frames = min_gap_s * fps
    chosen: list[int] = []
    for i, _v in sorted(cands, key=lambda c: c[1], reverse=True):
        if all(abs(i - j) >= min_gap_frames for j in chosen):
            chosen.append(i)

    # 强度下限过滤 + 数量上限（按强度取 top-N，再按时间排序输出）
    chosen = [i for i in chosen if motion[i] / peak_max >= min_intensity]
    if max_count is not None and len(chosen) > max_count:
        chosen = sorted(chosen, key=lambda i: motion[i], reverse=True)[:max_count]

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
        # 光流前缩到固定宽度，运动幅值的相对关系不变但大幅提速
        # （全分辨率逐帧 Farneback 对 1-2min 成片要数分钟，会卡死 align 阶段）
        if _FLOW_WIDTH and gray.shape[1] > _FLOW_WIDTH:
            scale = _FLOW_WIDTH / gray.shape[1]
            gray = cv2.resize(gray, (_FLOW_WIDTH, max(1, int(gray.shape[0] * scale))))
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
                   k: float = 0.6,
                   min_gap_s: float = 0.3) -> list:
    """成片 MP4 → 动作爆点 AccentPoint 列表。

    k 默认 0.6（较 find_accent_peaks 的 1.0 更灵敏）：AI 生成视频运动平缓、
    std 小，阈值太严会检不出爆点。
    """
    motion, fps = _motion_series(video_path)
    return find_accent_peaks(motion, fps, k=k, min_gap_s=min_gap_s,
                             min_intensity=0.3, max_count=12)
