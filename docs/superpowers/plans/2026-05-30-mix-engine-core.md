# 实时混音引擎 PCM缓存+混音核 实施计划（子项目 #3b-1 / #3b-2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 建实时混音引擎的两个纯逻辑地基——PcmCache（ffmpeg 解码音频→48k 立体声 numpy + 缓存）+ mix_frame（按播放头叠加活跃片段的纯函数）。

**Architecture:** `pcm_cache.py`(decode_to_pcm/PcmCache) + `mix_core.py`(ActiveClip/mix_frame)，纯 numpy/subprocess、无 Qt、无音频设备、全可单测。3b-3 实时输出流依赖这两块。

**Tech Stack:** numpy / ffmpeg(subprocess) / pytest

**Spec:** `docs/superpowers/specs/2026-05-30-mix-engine-core-design.md`

**Branch:** main

---

## Task 1: PcmCache（ffmpeg 解码 + 缓存）

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/pcm_cache.py`
- Test: `tests/test_ui/daw/test_pcm_cache.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/daw/test_pcm_cache.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/daw/test_pcm_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: ... pcm_cache`

- [ ] **Step 3: 实现** — 新建 `drama_shot_master/ui/widgets/daw/pcm_cache.py`：

```python
"""PCM 片段缓存：ffmpeg 解码任意音频 → 48k 立体声 float32 numpy + 懒缓存。

纯 numpy/subprocess，无 Qt。供实时混音引擎按播放头取样。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
CHANNELS = 2

_EMPTY = np.zeros((0, CHANNELS), dtype=np.float32)


def decode_to_pcm(audio_path: str) -> np.ndarray:
    """ffmpeg 解码 → float32 (frames, 2) @48k。失败/空 → (0,2) 空数组（不抛）。"""
    if not audio_path or not Path(str(audio_path)).is_file():
        return _EMPTY.copy()
    cmd = ["ffmpeg", "-i", str(audio_path),
           "-f", "f32le", "-acodec", "pcm_f32le",
           "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except Exception:
        return _EMPTY.copy()
    if proc.returncode != 0 or not proc.stdout:
        return _EMPTY.copy()
    try:
        arr = np.frombuffer(proc.stdout, dtype=np.float32)
    except Exception:
        return _EMPTY.copy()
    if arr.size < CHANNELS:
        return _EMPTY.copy()
    # 丢弃不足一帧的尾部
    usable = (arr.size // CHANNELS) * CHANNELS
    return arr[:usable].reshape(-1, CHANNELS).copy()


class PcmCache:
    def __init__(self):
        self._cache: dict[str, np.ndarray] = {}

    def get(self, audio_path: str) -> np.ndarray:
        key = str(audio_path)
        pcm = self._cache.get(key)
        if pcm is None:
            pcm = decode_to_pcm(key)
            self._cache[key] = pcm
        return pcm

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)
```

注意：测试 `test_cache_reuses_decode` monkeypatch 模块级 `decode_to_pcm`，故 `PcmCache.get` 必须调用模块级名字 `decode_to_pcm(key)`（上面实现正是裸调用，monkeypatch 生效）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/daw/test_pcm_cache.py -q`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/pcm_cache.py tests/test_ui/daw/test_pcm_cache.py
git commit -m "feat(soundtrack): + PcmCache ffmpeg解码音频→48k立体声numpy缓存

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: mix_frame 混音核

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/mix_core.py`
- Test: `tests/test_ui/daw/test_mix_core.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/daw/test_mix_core.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/daw/test_mix_core.py -q`
Expected: FAIL — `ModuleNotFoundError: ... mix_core`

- [ ] **Step 3: 实现** — 新建 `drama_shot_master/ui/widgets/daw/mix_core.py`：

```python
"""实时混音核：给定播放头 + 活跃片段 → 叠加出输出缓冲。纯 numpy 无副作用。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ActiveClip:
    pcm: np.ndarray      # (frames, 2) float32
    t_start: float       # 片段在时间线上的起点（秒）
    volume: float = 1.0


def mix_frame(clips, playhead_sec: float, n_frames: int,
              sample_rate: int = 48000) -> np.ndarray:
    """混出从 playhead_sec 起 n_frames 帧立体声 (n_frames, 2) float32。hard clip [-1,1]。"""
    out = np.zeros((n_frames, 2), dtype=np.float32)
    win0 = int(round(playhead_sec * sample_rate))      # 窗口起始绝对帧
    for c in clips:
        pcm = c.pcm
        m = pcm.shape[0]
        if m == 0:
            continue
        clip0 = int(round(c.t_start * sample_rate))     # clip 起始绝对帧
        # clip 覆盖绝对帧 [clip0, clip0+m)；窗口绝对帧 [win0, win0+n_frames)
        lo = max(win0, clip0)
        hi = min(win0 + n_frames, clip0 + m)
        if hi <= lo:
            continue
        out_off = lo - win0          # 写入 out 的起点
        clip_off = lo - clip0        # 读 pcm 的起点
        k = hi - lo
        seg = pcm[clip_off:clip_off + k]
        if c.volume != 1.0:
            seg = seg * np.float32(c.volume)
        out[out_off:out_off + k] += seg
    np.clip(out, -1.0, 1.0, out=out)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/daw/test_mix_core.py -q`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/mix_core.py tests/test_ui/daw/test_mix_core.py
git commit -m "feat(soundtrack): + mix_frame 混音核（按播放头叠加活跃片段+hardclip）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec 覆盖**：decode_to_pcm/PcmCache→T1；ActiveClip/mix_frame→T2。✓（requirements.txt 的 sounddevice 推迟到 3b-3，本块不 import，spec 已注明本块不依赖）
- **类型一致**：`decode_to_pcm(str)->ndarray(n,2)`、`PcmCache.get/clear/__len__`、`ActiveClip(pcm,t_start,volume)`、`mix_frame(clips,playhead_sec,n_frames,sample_rate)` 在 spec 与 plan 一致。✓
- **测试可靠**：PcmCache 用 ffmpeg 真解码（CI 有 ffmpeg，已验证管线）；mix_frame 纯 numpy 构造 clip 不依赖 ffmpeg。✓
- **无占位符**：完整代码。✓
- **边界正确**：mix_frame 用绝对帧交集，clip 早于/晚于/短于窗口均测；hard clip 测 0.8+0.8→1.0。✓
- 注：spec 提到 requirements.txt 改动列在文件清单，但本计划两个 task 不含——sounddevice 留给 3b-3 实际 import 时再加，避免登记未用依赖。
```
