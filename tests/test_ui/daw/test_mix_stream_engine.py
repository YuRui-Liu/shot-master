"""MixStreamEngine：overlay 片段 → 播放头驱动 → pull 混音帧；输出层降级。"""
import numpy as np
import pytest
from drama_shot_master.ui.widgets.daw.mix_stream_engine import (
    MixStreamEngine, MixStreamOutput)


class _FakeCache:
    def __init__(self, table):
        self._t = table
    def get(self, path):
        return self._t.get(path, np.zeros((0, 2), np.float32))


class _Seg:
    def __init__(self, audio_path, t_start, t_end, volume=1.0, enabled=True):
        self.audio_path = audio_path; self.t_start = t_start
        self.t_end = t_end; self.volume = volume; self.enabled = enabled


SR = 48000


def test_construct_default():
    eng = MixStreamEngine()
    assert eng.current_playhead() == 0.0


def test_set_segments_filters_disabled_and_empty():
    pcm = np.full((SR, 2), 0.5, np.float32)
    cache = _FakeCache({"/a.mp3": pcm})
    eng = MixStreamEngine(pcm_cache=cache)
    eng.set_segments([
        _Seg("/a.mp3", 0.0, 1.0),
        _Seg("/a.mp3", 2.0, 3.0, enabled=False),
        _Seg("", 4.0, 5.0),
    ])
    assert eng.clip_count() == 1


def test_pull_not_playing_is_silent():
    pcm = np.full((SR, 2), 0.5, np.float32)
    eng = MixStreamEngine(pcm_cache=_FakeCache({"/a.mp3": pcm}))
    eng.set_segments([_Seg("/a.mp3", 0.0, 1.0)])
    eng.set_playhead(0.0)
    out = eng.pull(100)
    assert out.shape == (100, 2)
    assert np.all(out == 0.0)


def test_pull_playing_mixes():
    pcm = np.full((SR, 2), 0.5, np.float32)
    eng = MixStreamEngine(pcm_cache=_FakeCache({"/a.mp3": pcm}))
    eng.set_segments([_Seg("/a.mp3", 0.0, 1.0)])
    eng.set_playhead(0.0); eng.play()
    out = eng.pull(100)
    assert np.allclose(out, 0.5)


def test_pull_advances_playhead():
    pcm = np.full((SR, 2), 0.5, np.float32)
    eng = MixStreamEngine(pcm_cache=_FakeCache({"/a.mp3": pcm}))
    eng.set_segments([_Seg("/a.mp3", 0.0, 1.0)])
    eng.set_playhead(0.0); eng.play()
    eng.pull(SR // 2)
    assert abs(eng.current_playhead() - 0.5) < 1e-3


def test_set_playhead_resets_advance():
    eng = MixStreamEngine(pcm_cache=_FakeCache({}))
    eng.set_playhead(2.0); eng.play()
    eng.pull(SR)
    assert abs(eng.current_playhead() - 3.0) < 1e-3
    eng.set_playhead(5.0)
    assert abs(eng.current_playhead() - 5.0) < 1e-3


def test_two_overlapping_clips_add():
    a = np.full((SR, 2), 0.3, np.float32)
    b = np.full((SR, 2), 0.2, np.float32)
    eng = MixStreamEngine(pcm_cache=_FakeCache({"/a.mp3": a, "/b.mp3": b}))
    eng.set_segments([_Seg("/a.mp3", 0.0, 1.0), _Seg("/b.mp3", 0.0, 1.0)])
    eng.set_playhead(0.0); eng.play()
    out = eng.pull(100)
    assert np.allclose(out, 0.5)


def test_volume_applied():
    pcm = np.full((SR, 2), 0.4, np.float32)
    eng = MixStreamEngine(pcm_cache=_FakeCache({"/a.mp3": pcm}))
    eng.set_segments([_Seg("/a.mp3", 0.0, 1.0, volume=0.5)])
    eng.set_playhead(0.0); eng.play()
    out = eng.pull(100)
    assert np.allclose(out, 0.2)


def test_output_degrades_when_sounddevice_missing(monkeypatch):
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **k):
        if name == "sounddevice":
            raise ImportError("no sounddevice")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    eng = MixStreamEngine()
    out = MixStreamOutput(eng)
    assert out.available is False
    out.start(); out.stop(); out.close()
