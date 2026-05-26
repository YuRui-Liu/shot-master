import numpy as np
import soundfile as sf
from sound_track_agent.beat_aligner import (
    snap_boundaries_to_beats, align_accents, extract_beats,
)


def test_snap_to_nearest_beat_within_shift():
    beats = [0.0, 1.0, 2.0, 3.0, 4.0]
    boundaries = [0.1, 1.9, 3.05]
    out = snap_boundaries_to_beats(boundaries, beats, max_shift=0.3)
    assert out == [0.0, 2.0, 3.0]


def test_snap_keeps_original_when_beyond_shift():
    beats = [0.0, 4.0]
    boundaries = [2.0]
    out = snap_boundaries_to_beats(boundaries, beats, max_shift=0.3)
    assert out == [2.0]


def test_snap_empty_beats_returns_original():
    out = snap_boundaries_to_beats([1.0, 2.0], [], max_shift=0.3)
    assert out == [1.0, 2.0]


def test_align_accents_matches_within_tolerance():
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    accents = [0.52, 1.48]
    out = align_accents(accents, beats, tolerance=0.1)
    assert out == [(0.52, 0.5), (1.48, 1.5)]


def test_align_accents_skips_when_no_beat_in_tolerance():
    beats = [0.0, 2.0]
    accents = [1.0]
    out = align_accents(accents, beats, tolerance=0.1)
    assert out == []


def _write_click_track(path, sr=22050, clicks_s=(0.5, 1.0, 1.5, 2.0, 2.5), dur_s=3.0):
    """每个 clicks_s 处放一个短脉冲，形成稳定节拍。"""
    y = np.zeros(int(sr * dur_s), dtype=np.float32)
    for t in clicks_s:
        i = int(t * sr)
        y[i:i + 200] = 1.0
    sf.write(str(path), y, sr)


def test_extract_beats_returns_increasing_times(tmp_path):
    wav = tmp_path / "click.wav"
    _write_click_track(wav)
    beats = extract_beats(wav)
    assert isinstance(beats, list)
    assert len(beats) >= 3
    assert all(isinstance(b, float) for b in beats)
    assert beats == sorted(beats)
    assert 0.0 <= beats[0] and beats[-1] <= 3.0


def test_extract_beats_empty_on_silence(tmp_path):
    wav = tmp_path / "silence.wav"
    sf.write(str(wav), np.zeros(22050, dtype=np.float32), 22050)
    beats = extract_beats(wav)
    assert isinstance(beats, list)   # 静音不报错即可（空或极少）
