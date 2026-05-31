"""CV 智能转场分析：相邻片段衔接处视觉评分 + 转场映射。Qt-free。

评分函数吃 numpy BGR 帧（cv2 读），便于注入单测。
权重/阈值固定（spec §5）：综合 = 0.4*hist + 0.4*feature + 0.2*(1-motion_disc)。
"""
from __future__ import annotations

import numpy as np

_W_HIST, _W_FEAT, _W_MOTION = 0.4, 0.4, 0.2
_HIGH, _LOW = 0.7, 0.4
_DUR_UNIVERSAL, _DUR_DIRECTIONAL, _DUR_CREATIVE = 0.5, 0.6, 0.7
_DIR_TRANSITION = {"left": "smoothleft", "right": "smoothright",
                   "up": "smoothup", "down": "smoothdown"}


def hist_similarity(a: np.ndarray, b: np.ndarray) -> float:
    import cv2
    # Use all 3 HSV channels so achromatic images with different brightness differ.
    # Compute per-channel histograms and average their correlations.
    ha_hsv = cv2.cvtColor(a, cv2.COLOR_BGR2HSV)
    hb_hsv = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    bins = [50, 60, 32]
    ranges = [0, 180, 0, 256, 0, 256]
    ha = cv2.calcHist([ha_hsv], [0, 1, 2], None, bins, ranges)
    hb = cv2.calcHist([hb_hsv], [0, 1, 2], None, bins, ranges)
    cv2.normalize(ha, ha); cv2.normalize(hb, hb)
    c = cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL)
    return float(max(0.0, min(1.0, c)))


def feature_similarity(a: np.ndarray, b: np.ndarray) -> float:
    import cv2
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create()
    ka, da = sift.detectAndCompute(ga, None)
    kb, db = sift.detectAndCompute(gb, None)
    if da is None or db is None or len(ka) < 2 or len(kb) < 2:
        return 0.5
    bf = cv2.BFMatcher()
    try:
        matches = bf.knnMatch(da, db, k=2)
    except cv2.error:
        return 0.5
    good = 0; pairs = 0
    for m_n in matches:
        if len(m_n) < 2:
            continue
        pairs += 1
        m, n = m_n
        if m.distance < 0.75 * n.distance:
            good += 1
    if pairs == 0:
        return 0.5
    return float(max(0.0, min(1.0, good / pairs)))


def motion_estimate(a: np.ndarray, b: np.ndarray) -> tuple[float, str]:
    import cv2
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    try:
        flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    except cv2.error:
        return 0.5, "none"
    fx, fy = float(flow[..., 0].mean()), float(flow[..., 1].mean())
    mag = float(np.sqrt(fx * fx + fy * fy))
    disc = float(max(0.0, min(1.0, mag / 10.0)))
    if mag < 0.5:
        return disc, "none"
    if abs(fx) >= abs(fy):
        return disc, ("right" if fx > 0 else "left")
    return disc, ("down" if fy > 0 else "up")


def combine_score(hist: float, feature: float, motion_disc: float) -> float:
    return float(_W_HIST * hist + _W_FEAT * feature + _W_MOTION * (1.0 - motion_disc))


def map_to_transition(score: float, direction: str) -> tuple[str, float]:
    if score >= _HIGH:
        return "dissolve", _DUR_UNIVERSAL
    if score >= _LOW:
        return _DIR_TRANSITION.get(direction, "dissolve"), _DUR_DIRECTIONAL
    return "circleopen", _DUR_CREATIVE
