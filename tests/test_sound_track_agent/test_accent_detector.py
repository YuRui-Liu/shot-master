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
