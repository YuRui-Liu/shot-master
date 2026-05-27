import numpy as np
from sound_track_agent.session import AccentPoint
from sound_track_agent.accent_mixer import build_pump_envelope


def test_envelope_dips_to_floor_at_accent():
    # sr=1000 → attack=12 samples, release=350 samples; accent t=0.5 → idx=500
    env = build_pump_envelope(2000, 1000, [AccentPoint(t=0.5, intensity=1.0)],
                              strength=1.0)
    assert env.shape == (2000,)
    assert abs(env[500] - 0.0) < 1e-6        # floor = 1 - 1*1 = 0
    assert abs(env[100] - 1.0) < 1e-6        # 远离卡点 → 基线 1.0


def test_envelope_depth_scales_with_strength_and_intensity():
    env = build_pump_envelope(2000, 1000, [AccentPoint(t=0.5, intensity=0.6)],
                              strength=0.5)
    assert abs(env[500] - 0.7) < 1e-6        # floor = 1 - 0.5*0.6 = 0.7


def test_envelope_clamps_intensity_above_one():
    env = build_pump_envelope(2000, 1000, [AccentPoint(t=0.5, intensity=2.0)],
                              strength=1.0)
    assert env[500] >= 0.0                    # 不为负
    assert abs(env[500] - 0.0) < 1e-6         # intensity 夹到 1 → floor 0


def test_envelope_zero_strength_is_flat():
    env = build_pump_envelope(100, 1000, [AccentPoint(t=0.05, intensity=1.0)],
                              strength=0.0)
    assert np.allclose(env, 1.0)


def test_envelope_no_accents_is_flat():
    env = build_pump_envelope(100, 1000, [], strength=1.0)
    assert np.allclose(env, 1.0)


def test_envelope_accent_past_end_is_ignored():
    env = build_pump_envelope(100, 1000, [AccentPoint(t=5.0, intensity=1.0)],
                              strength=1.0)
    assert np.allclose(env, 1.0)        # idx=5000 远超缓冲 → 整段不变


def test_envelope_negative_time_accent_does_not_contaminate():
    env = build_pump_envelope(100, 1000, [AccentPoint(t=-0.001, intensity=1.0)],
                              strength=1.0)
    assert np.allclose(env, 1.0)        # 负时间卡点被忽略,不留 release 余尾


import soundfile as sf
from sound_track_agent.accent_mixer import apply_pump


def test_apply_pump_attenuates_at_accent(tmp_path):
    sr = 8000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sig = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    inp = tmp_path / "in.wav"; sf.write(str(inp), sig, sr)
    out = tmp_path / "out.wav"
    res = apply_pump(inp, out, [AccentPoint(t=0.5, intensity=1.0)], strength=1.0)
    assert res == out and out.exists()
    data, _sr = sf.read(str(out))
    assert abs(data[4000]) < 1e-3                 # 卡点(idx=4000)处被压到近 0
    assert abs(abs(data[100]) - abs(sig[100])) < 1e-3   # 远处基本不变
