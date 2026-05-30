"""PcmCache：ffmpeg 解码音频 → 48k 立体声 float32 + 缓存。"""
import subprocess
import numpy as np
import pytest
from drama_shot_master.ui.widgets.daw.pcm_cache import (
    decode_to_pcm, PcmCache, SAMPLE_RATE, CHANNELS)


def _make_mp3(path, seconds=1.0, freq=440):
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i",
         f"sine=frequency={freq}:duration={seconds}", "-ac", "2", "-y", str(path)],
        check=True, capture_output=True)


def test_constants():
    assert SAMPLE_RATE == 48000 and CHANNELS == 2


def test_decode_real_mp3(tmp_path):
    mp3 = tmp_path / "a.mp3"; _make_mp3(mp3, seconds=1.0)
    pcm = decode_to_pcm(str(mp3))
    assert pcm.dtype == np.float32
    assert pcm.ndim == 2 and pcm.shape[1] == 2
    # 1 秒 @48k ≈ 48000 帧（mp3 编码有少量 padding，给容差）
    assert abs(pcm.shape[0] - 48000) < 5000


def test_decode_missing_path_returns_empty():
    pcm = decode_to_pcm("/no/such/file.mp3")
    assert pcm.shape == (0, 2) and pcm.dtype == np.float32


def test_decode_garbage_file_returns_empty(tmp_path):
    bad = tmp_path / "bad.mp3"; bad.write_bytes(b"not audio")
    pcm = decode_to_pcm(str(bad))
    assert pcm.shape == (0, 2)


def test_cache_reuses_decode(tmp_path, monkeypatch):
    mp3 = tmp_path / "a.mp3"; _make_mp3(mp3)
    cache = PcmCache()
    calls = {"n": 0}
    import drama_shot_master.ui.widgets.daw.pcm_cache as m
    real = m.decode_to_pcm
    def counting(p):
        calls["n"] += 1
        return real(p)
    monkeypatch.setattr(m, "decode_to_pcm", counting)
    a = cache.get(str(mp3))
    b = cache.get(str(mp3))
    assert calls["n"] == 1          # 第二次命中缓存
    assert a is b
    assert len(cache) == 1


def test_cache_caches_empty_for_bad(tmp_path):
    cache = PcmCache()
    pcm = cache.get("/no/such.mp3")
    assert pcm.shape == (0, 2)
    assert len(cache) == 1          # 坏文件也缓存，避免反复重试


def test_clear(tmp_path):
    mp3 = tmp_path / "a.mp3"; _make_mp3(mp3)
    cache = PcmCache(); cache.get(str(mp3))
    assert len(cache) == 1
    cache.clear()
    assert len(cache) == 0
