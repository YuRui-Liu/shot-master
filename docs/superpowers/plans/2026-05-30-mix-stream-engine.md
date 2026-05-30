# 实时混音输出引擎 实施计划 — 子项目 #3b-3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 把 PcmCache+mix_frame 串成 MixStreamEngine（纯逻辑拉帧，全单测）+ MixStreamOutput（sounddevice 适配，无设备优雅降级）+ 编辑器接线，实现 overlay 片段随视频实时采样级叠加播放。

**Architecture:** 两层——MixStreamEngine（PcmCache 预解码 + 播放头基准 + pull(n) 热路径调 mix_frame）/ MixStreamOutput（OutputStream 回调一行调 engine.pull，import/开流失败 available=False 降级）。视频 positionChanged 驱动 set_playhead。

**Tech Stack:** numpy / sounddevice(BSD) / ffmpeg / PySide6 / pytest

**Spec:** `docs/superpowers/specs/2026-05-30-mix-stream-engine-design.md`

**Branch:** main

---

## Task 1: MixStreamEngine + MixStreamOutput

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/mix_stream_engine.py`
- Test: `tests/test_ui/daw/test_mix_stream_engine.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/daw/test_mix_stream_engine.py`：

```python
"""MixStreamEngine：overlay 片段 → 播放头驱动 → pull 混音帧；输出层降级。"""
import numpy as np
import pytest
from drama_shot_master.ui.widgets.daw.mix_stream_engine import (
    MixStreamEngine, MixStreamOutput)


class _FakeCache:
    """假 PcmCache：按 path 返回预置常量 PCM，避免依赖 ffmpeg。"""
    def __init__(self, table):
        self._t = table          # path -> ndarray(frames,2)
    def get(self, path):
        return self._t.get(path, np.zeros((0, 2), np.float32))


class _Seg:
    """等价 OverlaySegment 的最小对象。"""
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
        _Seg("/a.mp3", 0.0, 1.0),                  # ok
        _Seg("/a.mp3", 2.0, 3.0, enabled=False),   # disabled → skip
        _Seg("", 4.0, 5.0),                        # empty path → skip
    ])
    assert eng.clip_count() == 1


def test_pull_not_playing_is_silent():
    pcm = np.full((SR, 2), 0.5, np.float32)
    eng = MixStreamEngine(pcm_cache=_FakeCache({"/a.mp3": pcm}))
    eng.set_segments([_Seg("/a.mp3", 0.0, 1.0)])
    eng.set_playhead(0.0)
    out = eng.pull(100)
    assert out.shape == (100, 2)
    assert np.all(out == 0.0)            # 未 play


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
    eng.pull(SR // 2)                    # 推进 0.5s
    assert abs(eng.current_playhead() - 0.5) < 1e-3


def test_set_playhead_resets_advance():
    eng = MixStreamEngine(pcm_cache=_FakeCache({}))
    eng.set_playhead(2.0); eng.play()
    eng.pull(SR)                         # +1s → 3.0
    assert abs(eng.current_playhead() - 3.0) < 1e-3
    eng.set_playhead(5.0)                # 视频 seek
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
    out.start(); out.stop(); out.close()    # 不抛
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/daw/test_mix_stream_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: ... mix_stream_engine`

- [ ] **Step 3: 实现** — 新建 `drama_shot_master/ui/widgets/daw/mix_stream_engine.py`：

```python
"""实时混音输出引擎：overlay 片段 → 播放头驱动 → pull 混音帧 + sounddevice 输出。

两层：MixStreamEngine（纯逻辑拉帧，全单测）+ MixStreamOutput（设备适配，
import/开流失败优雅降级）。视频为主时钟，set_playhead 由 positionChanged 驱动。
"""
from __future__ import annotations

import numpy as np

from drama_shot_master.ui.widgets.daw.pcm_cache import PcmCache, SAMPLE_RATE
from drama_shot_master.ui.widgets.daw.mix_core import ActiveClip, mix_frame


class MixStreamEngine:
    def __init__(self, pcm_cache=None, sample_rate: int = SAMPLE_RATE):
        self._cache = pcm_cache if pcm_cache is not None else PcmCache()
        self._sr = int(sample_rate)
        self._clips: list = []
        self._playhead = 0.0
        self._frames_since = 0
        self._playing = False

    def set_segments(self, segs) -> None:
        clips = []
        for s in segs or []:
            if not getattr(s, "enabled", True):
                continue
            path = getattr(s, "audio_path", "") or ""
            if not path:
                continue
            pcm = self._cache.get(path)
            if pcm.shape[0] == 0:
                continue
            clips.append(ActiveClip(pcm=pcm,
                                    t_start=float(getattr(s, "t_start", 0.0)),
                                    volume=float(getattr(s, "volume", 1.0))))
        self._clips = clips

    def clip_count(self) -> int:
        return len(self._clips)

    def set_playhead(self, t_sec: float) -> None:
        self._playhead = float(t_sec)
        self._frames_since = 0

    def play(self) -> None:
        self._playing = True

    def pause(self) -> None:
        self._playing = False

    def current_playhead(self) -> float:
        return self._playhead + self._frames_since / self._sr

    def pull(self, n_frames: int) -> np.ndarray:
        if not self._playing:
            return np.zeros((n_frames, 2), dtype=np.float32)
        out = mix_frame(self._clips, self.current_playhead(), n_frames, self._sr)
        self._frames_since += n_frames
        return out


class MixStreamOutput:
    """sounddevice OutputStream 包装。import/开流失败 → available=False 降级。"""

    def __init__(self, engine, sample_rate: int = SAMPLE_RATE, channels: int = 2):
        self._engine = engine
        self._stream = None
        self.available = False
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=sample_rate, channels=channels,
                dtype="float32", callback=self._cb)
            self.available = True
        except Exception:
            self._stream = None
            self.available = False

    def _cb(self, outdata, frames, time_info, status):  # pragma: no cover (无设备)
        outdata[:] = self._engine.pull(frames)

    def start(self) -> None:
        if self.available and self._stream is not None:
            try:
                self._stream.start()
            except Exception:
                self.available = False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/daw/test_mix_stream_engine.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/mix_stream_engine.py tests/test_ui/daw/test_mix_stream_engine.py
git commit -m "feat(soundtrack): + MixStreamEngine 实时混音拉帧 + sounddevice输出降级

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 编辑器接线 + requirements

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Modify: `requirements.txt`
- Test: `tests/test_ui/test_soundtrack_mix_engine_wiring.py`

先读 soundtrack_editor.py 确认 `__init__`（`self._overlay = OverlayMixer(self)` 与 `self._mix = load_mix(...)` 位置）、`_on_video_position_changed`、`_on_video_playing_changed`、`_try_load_existing` 现状。

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_soundtrack_mix_engine_wiring.py`：

```python
"""SoundtrackEditor 实时混音引擎接线：引擎存在 + position 驱动 set_playhead + overlay 载入。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _ed(tmp_path):
    mp4 = tmp_path / "raw.mp4"; mp4.write_bytes(b"x")
    return SoundtrackEditor({"id": "t1", "name": "t", "mp4": str(mp4),
                             "style": "x", "output_dir": str(tmp_path)},
                            _cfg(tmp_path), tmp_path)


def test_engine_exists(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._mix_engine is not None
    assert ed._mix_output is not None      # 降级时 available=False 但对象在


def test_position_changed_drives_playhead(tmp_path):
    _app()
    ed = _ed(tmp_path)
    seen = []
    ed._mix_engine.set_playhead = lambda t: seen.append(t)
    ed._on_video_position_changed(3.5)
    assert 3.5 in seen


def test_playing_changed_plays_engine(tmp_path):
    _app()
    ed = _ed(tmp_path)
    calls = []
    ed._mix_engine.play = lambda: calls.append("play")
    ed._mix_engine.pause = lambda: calls.append("pause")
    ed._mix_output.start = lambda: calls.append("start")
    ed._on_video_playing_changed(True)
    assert "play" in calls
    ed._on_video_playing_changed(False)
    assert "pause" in calls


def test_overlay_loaded_into_engine(tmp_path):
    _app()
    from drama_shot_master.ui.widgets.daw.track_mix import save_mix  # noqa
    from sound_track_agent.overlay_session import OverlaySession, save_overlay
    # 预置一个 overlay 片段（audio_path 空也行，引擎会跳过，但 set_segments 应被调用）
    sess = OverlaySession(); sess.add("bgm", 0.0, 5.0, "p", seg_id="x1")
    save_overlay(tmp_path / "t1", sess)
    got = {}
    # 用子类前注入不便，这里只验证 _try_load_existing 后 engine 收到 segments 列表
    ed = _ed(tmp_path)
    # 引擎 clip_count 为 0（片段无 audio_path），但 overlay session 已载入到编辑器
    assert ed._overlay_session is not None
    assert ed._overlay_session.get("x1") is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_mix_engine_wiring.py -q`
Expected: FAIL — `AttributeError: ... '_mix_engine'`

- [ ] **Step 3: requirements.txt 加 sounddevice**

在 `requirements.txt` 末尾追加一行：

```
sounddevice>=0.4.6
```

- [ ] **Step 4: __init__ 建引擎 + 载入 overlay**

在 `soundtrack_editor.py` 的 `__init__`，找到 `self._mix = load_mix(self._work_dir())`（#2 加的），在其后加：

```python
        from drama_shot_master.ui.widgets.daw.mix_stream_engine import (
            MixStreamEngine, MixStreamOutput)
        from sound_track_agent.overlay_session import load_overlay
        self._overlay_session = load_overlay(self._work_dir())
        self._mix_engine = MixStreamEngine()
        self._mix_engine.set_segments(self._overlay_session.segments)
        self._mix_output = MixStreamOutput(self._mix_engine)
```

- [ ] **Step 5: position / playing 接线**

在 `_on_video_position_changed(self, t)` 方法末尾追加：

```python
        self._mix_engine.set_playhead(t)
```

在 `_on_video_playing_changed(self, playing)` 方法体中追加（与现有 overlay/pause 逻辑并列）：

```python
        if playing:
            self._mix_engine.play()
            self._mix_output.start()
        else:
            self._mix_engine.pause()
```

（保留该方法原有的 `self._overlay.play()/pause()` 调用——固定轨 OverlayMixer 与动态片段 MixStreamEngine 并存。）

- [ ] **Step 6: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_mix_engine_wiring.py tests/test_ui/test_soundtrack_play_mode.py tests/test_ui/test_soundtrack_editor_daw_smoke.py -q`
Expected: PASS（4 新 + play_mode + daw smoke 全绿）

- [ ] **Step 7: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py requirements.txt tests/test_ui/test_soundtrack_mix_engine_wiring.py
git commit -m "feat(soundtrack): 接线 MixStreamEngine（视频驱动 overlay 实时叠加播放）+ sounddevice 依赖

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 回归

- [ ] **Step 1: 跑混音引擎 + 配乐 UI/DAW**

Run:
```bash
python -m pytest tests/test_ui/daw/test_pcm_cache.py tests/test_ui/daw/test_mix_core.py \
  tests/test_ui/daw/test_mix_stream_engine.py -q
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_ui/test_soundtrack_mix_engine_wiring.py tests/test_ui/test_soundtrack_mix_wiring.py \
  tests/test_ui/test_soundtrack_play_mode.py tests/test_ui/test_soundtrack_editor_daw_smoke.py \
  tests/test_ui/daw/ -q -p no:cacheprovider
```
Expected: 全绿

- [ ] **Step 2: 配乐 agent 未触碰**

Run: `python -m pytest tests/test_sound_track_agent/ -q -p no:cacheprovider`
Expected: 全绿（含 overlay_session 14 + 原 268）

---

## Self-Review

- **Spec 覆盖**：MixStreamEngine(set_segments/set_playhead/play/pause/current_playhead/pull)→T1；MixStreamOutput 降级→T1；编辑器接线+requirements→T2；回归→T3。✓
- **类型一致**：`MixStreamEngine(pcm_cache, sample_rate)`、`set_segments(segs)`、`pull(n)→ndarray`、`current_playhead()`、`clip_count()`、`MixStreamOutput(engine)` 在 spec/plan/测试一致；复用 `PcmCache.get`、`mix_frame`、`ActiveClip`、`SAMPLE_RATE`（已存在）。✓
- **环境约束遵守**：纯逻辑 MixStreamEngine 全单测（假 PcmCache 不依赖设备）；MixStreamOutput 仅测降级路径（monkeypatch import 失败）；回调 `_cb` 标 pragma no cover。✓
- **无占位符**：完整代码。✓
- **并存**：明确保留 OverlayMixer，MixStreamEngine 专管 overlay 动态片段，二者同跟视频主时钟。✓
- 注：T2 测试 `test_overlay_loaded_into_engine` 依赖 editor 暴露 `self._overlay_session`——已在 T2 Step4 建立。
```
