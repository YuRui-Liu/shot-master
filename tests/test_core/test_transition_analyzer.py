import numpy as np
import pytest
from drama_shot_master.core import transition_analyzer as ta

cv2 = pytest.importorskip("cv2")


def _solid(color, h=64, w=64):
    img = np.zeros((h, w, 3), np.uint8); img[:] = color; return img


def test_hist_score_identical_high():
    a = _solid((30, 60, 120)); b = _solid((30, 60, 120))
    assert ta.hist_similarity(a, b) > 0.95


def test_hist_score_opposite_low():
    a = _solid((10, 10, 10)); b = _solid((240, 240, 240))
    assert ta.hist_similarity(a, b) < 0.5


def test_feature_score_in_range():
    rng = np.random.default_rng(0)
    a = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    s = ta.feature_similarity(a, a.copy())
    assert 0.0 <= s <= 1.0


def test_motion_discontinuity_in_range():
    a = _solid((50, 50, 50)); b = _solid((50, 50, 50))
    m, direction = ta.motion_estimate(a, b)
    assert 0.0 <= m <= 1.0
    assert direction in ("left", "right", "up", "down", "none")


def test_combine_score_weights():
    assert abs(ta.combine_score(hist=1.0, feature=1.0, motion_disc=0.0) - 1.0) < 1e-6
    assert abs(ta.combine_score(hist=0.0, feature=0.0, motion_disc=1.0) - 0.0) < 1e-6


def test_map_high_score_universal():
    eff, dur = ta.map_to_transition(0.85, "none")
    assert eff in ("dissolve", "fade")
    assert 0.3 <= dur <= 2.0


def test_map_mid_score_directional_by_motion():
    eff, dur = ta.map_to_transition(0.55, "left")
    assert eff == "smoothleft"


def test_map_low_score_creative():
    eff, dur = ta.map_to_transition(0.2, "none")
    assert eff in ("circleopen", "pixelize")
