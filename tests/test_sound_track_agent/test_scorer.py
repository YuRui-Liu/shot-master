import numpy as np

from sound_track_agent import scorer
from sound_track_agent.session import BGMCandidate


def _sine(freq, dur=2.0, sr=22050, amp=0.3):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype("float64")


def test_health_penalizes_clipping():
    sr = 22050
    clean = _sine(440, sr=sr)
    clipped = np.ones(sr, dtype="float64")          # 全削波
    assert scorer.health_score(clean, sr, 2.0) > 0.8
    assert scorer.health_score(clipped, sr, 1.0) < 0.2


def test_health_penalizes_silence_and_too_short():
    sr = 22050
    silence = np.zeros(sr, dtype="float64")
    assert scorer.health_score(silence, sr, 1.0) < 0.3
    short = _sine(440, dur=0.2, sr=sr)
    assert scorer.health_score(short, sr, 2.0) < 0.7   # 远短于期望


def test_headroom_prefers_low_speech_band_energy():
    sr = 22050
    low_band = _sine(120, sr=sr)        # 低频，落在语音带外
    speech = _sine(1000, sr=sr)         # 落在 300-3400Hz
    assert scorer.headroom_score(low_band, sr) > scorer.headroom_score(speech, sr)


def test_pick_best_returns_argmax_score():
    cands = [
        BGMCandidate(path="a", seed=1, prompt="p", score=0.4),
        BGMCandidate(path="b", seed=2, prompt="p", score=0.9),
        BGMCandidate(path="c", seed=3, prompt="p", score=0.7),
    ]
    assert scorer.pick_best(cands) == 1


def test_pick_best_all_none_defaults_zero():
    cands = [BGMCandidate(path="a", seed=1, prompt="p"),
             BGMCandidate(path="b", seed=2, prompt="p")]
    assert scorer.pick_best(cands) == 0


def test_beat_score_degrades_to_neutral_on_empty_or_bad_input():
    # 空输入/无效采样率 → 中性 0.5（不需要 librosa）
    assert scorer.beat_score(np.array([], dtype="float64"), 22050) == 0.5
    assert scorer.beat_score(_sine(440, dur=0.1), 0) == 0.5
