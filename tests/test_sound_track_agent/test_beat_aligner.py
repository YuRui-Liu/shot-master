from sound_track_agent.beat_aligner import (
    snap_boundaries_to_beats, align_accents,
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
