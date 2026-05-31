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


_MARGIN = 0.25   # 避开段内淡入淡出过渡帧的余量（秒）
_NFRAMES = 5     # 每侧取帧数（取中位抗噪）


def _read_frames_cv2(path, t_sec, n):
    """真实帧抽取：从 t_sec 起取 n 帧 BGR。失败 → []。"""
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t_sec * fps)))
        out = []
        for _ in range(n):
            ok, fr = cap.read()
            if not ok:
                break
            out.append(fr)
        return out
    finally:
        cap.release()


def _median_frame(frames):
    if not frames:
        return None
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def default_score_fn(prev_frames, next_frames):
    """边界帧组取中位帧 → 三维评分 → (score, scores_dict, direction)。空帧→中性。"""
    pa = _median_frame(prev_frames)
    pb = _median_frame(next_frames)
    if pa is None or pb is None:
        return 0.5, {"hist": 0.5, "feature": 0.5, "motion": 0.5, "score": 0.5}, "none"
    h = hist_similarity(pa, pb)
    f = feature_similarity(pa, pb)
    md, direction = motion_estimate(pa, pb)
    s = combine_score(h, f, md)
    return s, {"hist": round(h, 3), "feature": round(f, 3),
               "motion": round(md, 3), "score": round(s, 3)}, direction


def analyze_composition(comp, frame_provider=None, score_fn=None, progress_cb=None,
                        clip_duration=None):
    """对每个未锁定切口跑 CV，回填 auto_transition/auto_duration/cv_scores。

    frame_provider(path, t_sec, n)->frames（默认 cv2）；score_fn(prev,next)->
    (score, scores, direction)（默认 default_score_fn）；progress_cb(done, total)。
    locked 切口跳过（仍计入进度）。clip_duration(path)->秒（默认用 clip.duration）。
    """
    frame_provider = frame_provider or _read_frames_cv2
    score_fn = score_fn or default_score_fn
    kept = comp.kept_clips()
    cuts = list(range(len(kept) - 1))
    total = len(cuts)
    for done, i in enumerate(cuts, start=1):
        a, b = kept[i], kept[i + 1]
        if a.locked:
            if progress_cb:
                progress_cb(done, total)
            continue
        a_dur = (clip_duration(a.path) if clip_duration else a.duration) or 0.0
        a_out = a.out_point if a.out_point is not None else a_dur
        prev_t = max(0.0, a_out - _MARGIN - _NFRAMES / 30.0)
        b_in = b.in_point or 0.0
        next_t = b_in + _MARGIN
        prev_frames = frame_provider(a.path, prev_t, _NFRAMES)
        next_frames = frame_provider(b.path, next_t, _NFRAMES)
        score, scores, direction = score_fn(prev_frames, next_frames)
        eff, dur = map_to_transition(score, direction)
        a.auto_transition = eff
        a.auto_duration = dur
        a.cv_scores = scores
        if progress_cb:
            progress_cb(done, total)
