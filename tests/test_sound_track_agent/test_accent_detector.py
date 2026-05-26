import pytest
from sound_track_agent.accent_detector import find_accent_peaks
from sound_track_agent.session import AccentPoint


def test_find_peaks_basic():
    # 两个明显尖峰：index2(=5) 与 index5(=4)，背景全 0
    # （背景为 0 + 峰值足够高，确保两者都超 mean+1*std 阈值）
    motion = [0.0, 0.0, 5.0, 0.0, 0.0, 4.0, 0.0]
    pts = find_accent_peaks(motion, fps=10.0, k=1.0, min_gap_s=0.05)
    assert all(isinstance(p, AccentPoint) for p in pts)
    ts = [round(p.t, 3) for p in pts]
    # motion[i] 对应 t=(i+1)/fps → index2→0.3s, index5→0.6s
    assert ts == [0.3, 0.6]
    assert max(p.intensity for p in pts) == 1.0
    assert all(0.0 <= p.intensity <= 1.0 for p in pts)
    assert all(p.confirmed is False for p in pts)


def test_find_peaks_respects_min_gap():
    # 两个局部极大 index1(=5)、index3(=4)，间隔 2 帧 < min_gap(=0.3s*10fps=3 帧)
    # → 只保留更强的 index1
    motion = [0.0, 5.0, 0.0, 4.0, 0.0]
    pts = find_accent_peaks(motion, fps=10.0, k=0.5, min_gap_s=0.3)
    assert len(pts) == 1
    assert round(pts[0].t, 3) == 0.2        # index1 → (1+1)/10


def test_find_peaks_empty_or_flat():
    assert find_accent_peaks([], fps=24.0) == []
    assert find_accent_peaks([1.0, 1.0, 1.0, 1.0], fps=24.0, k=1.0) == []


import numpy as np
import cv2
from sound_track_agent.accent_detector import _motion_series, detect_accents


def _write_motion_video(path, fps=24):
    """平移噪声纹理：前后静止、中间某帧突然大平移 → 该处运动峰值。

    Farneback 需纹理梯度，纯色无效，故用随机噪声底图。
    """
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    shifts = [0] * 20 + [10] + [0] * 19   # 第 20 帧(index19→20)突然平移 10px
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         float(fps), (64, 64))
    assert vw.isOpened()
    pos = 0
    for s in shifts:
        pos += s
        vw.write(np.roll(base, pos, axis=1))
    vw.release()


def test_motion_series_shape(tmp_path):
    v = tmp_path / "m.mp4"
    _write_motion_video(v, fps=24)
    motion, fps = _motion_series(v)
    assert fps == 24.0
    assert len(motion) == 39            # 40 帧 → 39 个相邻对
    assert max(motion) > 0.0            # 噪声平移产生非零光流


def test_detect_accents_finds_motion_spike(tmp_path):
    v = tmp_path / "m.mp4"
    _write_motion_video(v, fps=24)
    pts = detect_accents(v, k=1.0, min_gap_s=0.2)
    assert len(pts) >= 1
    # 平移发生在 frame19→frame20（pos 0→10），即 motion index 19 → t≈20/24≈0.833s
    assert any(abs(p.t - 20 / 24) < 0.2 for p in pts)


def test_find_peaks_min_intensity_and_max_count():
    # 一个强峰(=10) + 多个弱峰(=2)，背景 0
    motion = [0, 10, 0, 2, 0, 2, 0, 2, 0, 2, 0]
    # min_intensity=0.3 → 弱峰(2/10=0.2)被滤掉，只剩强峰
    pts = find_accent_peaks(motion, fps=10.0, k=0.1, min_gap_s=0.05,
                            min_intensity=0.3)
    assert len(pts) == 1
    assert round(pts[0].intensity, 2) == 1.0
    # max_count=2 → 即便很多候选也只留最强 2 个
    motion2 = [0, 9, 0, 8, 0, 7, 0, 6, 0, 5, 0]
    pts2 = find_accent_peaks(motion2, fps=10.0, k=0.1, min_gap_s=0.05,
                             max_count=2)
    assert len(pts2) == 2
    ints = sorted(p.intensity for p in pts2)
    assert round(ints[-1], 2) == 1.0          # 含最强(9/9)
