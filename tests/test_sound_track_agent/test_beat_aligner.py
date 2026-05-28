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


# ===== 新增：_plan_alignment / _chunks_from_plan / align_beats_to_accents =====

from sound_track_agent.beat_aligner import (
    _plan_alignment, _chunks_from_plan, align_beats_to_accents,
)
from sound_track_agent.session import AccentPoint


def _ap(t, intensity=0.9):
    return AccentPoint(t=t, intensity=intensity, confirmed=False)


# ===== _plan_alignment（纯逻辑）=====

def test_plan_alignment_empty_inputs():
    assert _plan_alignment([], [], 0.1, 0.7) == []
    assert _plan_alignment([1.0, 2.0], [], 0.1, 0.7) == []
    assert _plan_alignment([], [_ap(1.0)], 0.1, 0.7) == []


def test_plan_alignment_ignores_small_accents():
    """intensity < big_threshold 的 accent 不参与对齐。"""
    accents = [_ap(1.0, intensity=0.3), _ap(2.0, intensity=0.9)]
    aligned = _plan_alignment([1.8, 2.0], accents, max_stretch=0.1,
                              big_threshold=0.7)
    assert len(aligned) == 1
    assert aligned[0][0] == 1                     # 只对齐 index=1


def test_plan_alignment_picks_nearest_forward_beat_within_stretch():
    """beats=[1.8] accent t=2.0 → factor=1.8/2.0=0.9，|0.9-1|=0.10 在 ±10% 边界，可对齐。"""
    aligned = _plan_alignment([1.8], [_ap(2.0)], max_stretch=0.10,
                              big_threshold=0.7)
    assert aligned == [(0, 2.0, 1.8)]


def test_plan_alignment_rejects_factor_beyond_stretch():
    """beats=[1.5] accent t=2.0 → factor=1.5/2.0=0.75 超 ±10% 跳过。"""
    aligned = _plan_alignment([1.5], [_ap(2.0)], max_stretch=0.10,
                              big_threshold=0.7)
    assert aligned == []


def test_plan_alignment_only_forward_beats():
    """只用 b ≤ t 的 beat，未来 beat 不参与（避免反向拉伸）。"""
    aligned = _plan_alignment([2.5], [_ap(2.0)], max_stretch=0.5,
                              big_threshold=0.7)
    assert aligned == []                          # 无前向候选


def test_plan_alignment_multi_accents_sequential():
    """两个 accent 顺序对齐，第二个相对第一个判定 factor。"""
    aligned = _plan_alignment([1.9, 3.8], [_ap(2.0), _ap(4.0)],
                              max_stretch=0.10, big_threshold=0.7)
    assert len(aligned) == 2
    assert aligned[0] == (0, 2.0, 1.9)
    assert aligned[1] == (1, 4.0, 3.8)


def test_plan_alignment_used_beats_not_reused():
    """同一 beat 不能被两个 accent 共用。"""
    aligned = _plan_alignment([1.9, 1.95], [_ap(2.0), _ap(2.1)],
                              max_stretch=0.10, big_threshold=0.7)
    seen = {b for (_, _, b) in aligned}
    assert len(seen) == len(aligned)              # 无重复 beat


# ===== _chunks_from_plan（纯逻辑）=====

def test_chunks_from_empty_plan_returns_single_tail():
    chunks = _chunks_from_plan([], total_dur=5.0)
    assert chunks == [("tail", 0.0, 5.0, 5.0)]


def test_chunks_from_single_aligned():
    chunks = _chunks_from_plan([(0, 2.0, 1.8)], total_dur=5.0)
    assert chunks[0] == ("stretch", 0.0, 1.8, 2.0)
    assert chunks[1] == ("tail", 1.8, 5.0, 3.0)


# ===== align_beats_to_accents（注入 fake 集成）=====

def test_align_writes_stretched_with_injected_fakes(tmp_path):
    sr = 22050
    n = int(sr * 5.0)
    data = np.zeros(n, dtype="float32")

    def fake_reader(p): return data, sr
    written = {}
    def fake_writer(p, d, s):
        written["path"] = p; written["data"] = d; written["sr"] = s
    def fake_stretcher(y, rate):
        out_len = max(1, int(round(len(y) / rate)))
        return np.resize(y, out_len)

    accents = [_ap(2.0)]
    out, aligned = align_beats_to_accents(
        tmp_path / "bgm.wav", accents,
        max_stretch=0.10, big_threshold=0.7,
        out_path=tmp_path / "out.wav",
        extractor=lambda p: [1.9],
        reader=fake_reader, writer=fake_writer,
        stretcher=fake_stretcher)
    assert out == tmp_path / "out.wav"
    assert aligned == frozenset({0})
    assert written["sr"] == sr


def test_align_writes_stretched_with_2d_mono_data(tmp_path):
    """模拟 soundfile.read(always_2d=True) 返回 (N, 1) 形状的单声道路径。"""
    sr = 22050
    n = int(sr * 5.0)
    data = np.zeros((n, 1), dtype="float32")          # 2D mono

    def fake_reader(p): return data, sr
    written = {}
    def fake_writer(p, d, s):
        written["data_ndim"] = d.ndim; written["sr"] = s
    def fake_stretcher(y, rate):
        out_len = max(1, int(round(len(y) / rate)))
        return np.resize(y, out_len)

    out, aligned = align_beats_to_accents(
        tmp_path / "bgm.wav", [_ap(2.0)],
        max_stretch=0.10, big_threshold=0.7,
        out_path=tmp_path / "out.wav",
        extractor=lambda p: [1.9],
        reader=fake_reader, writer=fake_writer,
        stretcher=fake_stretcher)
    assert out == tmp_path / "out.wav"
    assert aligned == frozenset({0})
    assert written["data_ndim"] == 2                  # 保持 (N, 1) 形状


def test_align_degrades_when_no_beats(tmp_path):
    bgm = tmp_path / "bgm.wav"
    out, aligned = align_beats_to_accents(
        bgm, [_ap(2.0)],
        extractor=lambda p: [],
        reader=lambda p: (np.zeros(1024, dtype="float32"), 22050),
        writer=lambda *a, **k: None,
        stretcher=lambda y, rate: y)
    assert out == bgm                             # 原路径
    assert aligned == frozenset()


def test_align_degrades_on_extractor_exception(tmp_path):
    bgm = tmp_path / "bgm.wav"
    def boom(p): raise RuntimeError("librosa missing")
    out, aligned = align_beats_to_accents(
        bgm, [_ap(2.0)], extractor=boom,
        reader=lambda p: (np.zeros(1024, dtype="float32"), 22050),
        writer=lambda *a, **k: None,
        stretcher=lambda y, rate: y)
    assert out == bgm
    assert aligned == frozenset()
