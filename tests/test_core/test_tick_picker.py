"""Tests for _pick_tick_interval in timeline_widget."""
from __future__ import annotations

from drama_shot_master.ui.widgets.timeline_widget import _pick_tick_interval


def test_zoom_in_seconds_returns_half_second_major():
    # ppf=20, fr=24 → 0.5s=12f, 12*20=240px >= 80 → (12, 12//5=2)
    assert _pick_tick_interval(20.0, 24, "seconds") == (12, 2)


def test_mid_zoom_seconds_returns_1s_major():
    # ppf=5, fr=24 → 0.5s=12f, 12*5=60 < 80; 1s=24f, 24*5=120 >= 80 → (24, 4)
    assert _pick_tick_interval(5.0, 24, "seconds") == (24, 4)


def test_zoom_out_seconds_returns_10s_major():
    # ppf=0.5, fr=24 → 0.5/1/2/5s 全 <80px; 10s=240f, 240*0.5=120 >= 80
    assert _pick_tick_interval(0.5, 24, "seconds") == (240, 48)


def test_zoom_in_frames_returns_5f_major():
    # ppf=20, fr=24 → 1f=20<80; 5f=100>=80 → (5, 1)
    assert _pick_tick_interval(20.0, 24, "frames") == (5, 1)


def test_zoom_out_frames_returns_300f_major():
    # ppf=0.5, fr=24 → 1..120f 全 <80; 300f=150 >= 80 → (300, 60)
    assert _pick_tick_interval(0.5, 24, "frames") == (300, 60)


def test_max_zoom_frames_returns_5f_major():
    # ppf=50, fr=24 → 1f=50<80; 5f=250>=80 → (5, 1)
    assert _pick_tick_interval(50.0, 24, "frames") == (5, 1)


def test_zero_frame_rate_does_not_crash_seconds():
    # 内部 max(frame_rate, 1) 兜底 → 等价 fr=1
    # ppf=5, fr=0, mode=seconds: 0.5s→1f(round), 1*5=5<80; 1s=1f, 5<80; 2s=2f,10<80;
    # 5s=5f,25<80; 10s=10f,50<80; 30s=30f, 30*5=150>=80 → (30, 6)
    assert _pick_tick_interval(5.0, 0, "seconds") == (30, 6)


def test_minor_at_least_1():
    # 任何返回，minor 都 >= 1（避免 zero-step 循环）
    cases = [
        (50.0, 24, "frames"),
        (50.0, 24, "seconds"),
        (0.5, 1, "frames"),
    ]
    for ppf, fr, mode in cases:
        major, minor = _pick_tick_interval(ppf, fr, mode)
        assert major >= 1
        assert minor >= 1
        assert minor <= major


def test_seconds_fallback_when_all_candidates_too_small():
    # ppf far below valid range forces every SECONDS candidate < 80px,
    # exercising the fallback to the largest candidate (600s = 14400f @ 24fps).
    assert _pick_tick_interval(0.001, 24, "seconds") == (14400, 2880)
