"""Tests for _format_cursor_label in timeline_widget."""
from __future__ import annotations

from drama_shot_master.ui.widgets.timeline_widget import _format_cursor_label


def test_frames_basic():
    # x=100, ppf=5 → 20 frames → "20f"
    assert _format_cursor_label(100.0, 5.0, 24, "frames") == "20f"


def test_seconds_basic():
    # x=120, ppf=5 → 24 frames; 24/24 = 1.0 → "1.00s"
    assert _format_cursor_label(120.0, 5.0, 24, "seconds") == "1.00s"


def test_seconds_fractional():
    # x=100, ppf=5 → 20 frames; 20/24 ≈ 0.833 → "0.83s"
    assert _format_cursor_label(100.0, 5.0, 24, "seconds") == "0.83s"


def test_ppf_zero_guard():
    # ppf <= 0 → frame=0 → "0f"
    assert _format_cursor_label(100.0, 0.0, 24, "frames") == "0f"


def test_frame_rate_zero_guard():
    # x=120, ppf=5 → 24 frames; 24/max(0,1)=24 → "24.00s"
    assert _format_cursor_label(120.0, 5.0, 0, "seconds") == "24.00s"


def test_negative_x_clamped():
    # x=-50, ppf=5 → round(-10) → max(0,-10)=0 → "0f"
    assert _format_cursor_label(-50.0, 5.0, 24, "frames") == "0f"
