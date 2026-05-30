"""mix_frame：按播放头叠加活跃片段 → 输出缓冲（纯 numpy）。"""
import numpy as np
from drama_shot_master.ui.widgets.daw.mix_core import ActiveClip, mix_frame

SR = 48000


def _const_clip(t_start, seconds, value, volume=1.0):
    n = int(seconds * SR)
    pcm = np.full((n, 2), value, dtype=np.float32)
    return ActiveClip(pcm=pcm, t_start=t_start, volume=volume)


def test_empty_clips_zero():
    out = mix_frame([], 0.0, 100, SR)
    assert out.shape == (100, 2)
    assert np.all(out == 0.0)


def test_single_clip_in_window():
    clip = _const_clip(0.0, 1.0, 0.5)
    out = mix_frame([clip], 0.0, 100, SR)
    assert np.allclose(out, 0.5)


def test_volume_scales():
    clip = _const_clip(0.0, 1.0, 0.4, volume=0.5)
    out = mix_frame([clip], 0.0, 100, SR)
    assert np.allclose(out, 0.2)


def test_two_clips_add():
    a = _const_clip(0.0, 1.0, 0.3)
    b = _const_clip(0.0, 1.0, 0.2)
    out = mix_frame([a, b], 0.0, 100, SR)
    assert np.allclose(out, 0.5)


def test_clip_starts_mid_window():
    # clip 从 50 帧处开始（t_start = 50/SR）
    clip = _const_clip(50.0 / SR, 1.0, 0.5)
    out = mix_frame([clip], 0.0, 100, SR)
    assert np.allclose(out[:50], 0.0)
    assert np.allclose(out[50:], 0.5)


def test_clip_before_window_silent():
    clip = _const_clip(0.0, 0.0005, 0.5)   # ~24 帧，早于播放头 1.0s
    out = mix_frame([clip], 1.0, 100, SR)
    assert np.all(out == 0.0)


def test_hard_clip_to_one():
    a = _const_clip(0.0, 1.0, 0.8)
    b = _const_clip(0.0, 1.0, 0.8)         # 0.8+0.8=1.6 → clip 1.0
    out = mix_frame([a, b], 0.0, 100, SR)
    assert np.allclose(out, 1.0)


def test_clip_shorter_than_window():
    clip = _const_clip(0.0, 30.0 / SR, 0.5)  # 仅 30 帧
    out = mix_frame([clip], 0.0, 100, SR)
    assert np.allclose(out[:30], 0.5)
    assert np.allclose(out[30:], 0.0)
