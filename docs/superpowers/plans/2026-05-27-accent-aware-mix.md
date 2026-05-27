# 卡点感知混音 (Accent-Aware Mix) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 ③卡点页收集的 `accent_points` 真正影响出片——出片时对每个卡点做 sidechain 泵感(主力),并把段接缝吸附到大卡点(辅助)。

**Architecture:** 新增纯逻辑模块 `accent_mixer.py`(泵感增益包络 + 段切目标时长计算,后者复用已存在但未接线的 `beat_aligner.snap_boundaries_to_beats`)。`mixdown.assemble_and_mix` 按任务级开关接入:开关关或无卡点 → 完全等同现状(零回归)。任务级参数(开关/泵感强度)存进 `session.json` 由 ③卡点页控制;全局参数(大卡点阈值/吸附窗口)存进 cfg 由 设置→配乐 控制。

**Tech Stack:** numpy(已有依赖)、soundfile(env 已装,加进 pyproject)、ffmpeg/Demucs(沿用 `audio_mixer`/`bgm_assembler`)。PySide6 UI。**不引入 librosa**(本期不做 onset/time-warp)。

**测试解释器(全程用 conda UniRig,含 numpy/soundfile/cv2/ffmpeg/PySide6):**
`/root/miniconda3/envs/UniRig/bin/python`(下文记作 `$PY`)。UI 测试需前缀 `QT_QPA_PLATFORM=offscreen`。

**关键约束(必须遵守):**
- 永远不要 `git add -A` / `git add .`。每次 commit 只 `git add` 本任务明确列出的文件。工作树里有用户**并行进行中**的 imggen/dubbing 改动,绝不能误提交或改动它们。
- 不碰任何 `dub_*` / `imggen*` 文件。
- 不要 commit 任何密钥(`.env`、`settings.json` 真实文件)。

---

## File Structure

| 文件 | 角色 | 改动 |
|------|------|------|
| `sound_track_agent/accent_mixer.py` | 新模块:泵感包络 + 段切目标时长(纯逻辑+薄 I/O) | Create |
| `sound_track_agent/session.py` | 加 2 个任务级字段 + 序列化 | Modify |
| `sound_track_agent/bgm_assembler.py` | `assemble_bgm` 支持按目标时长裁剪 clip(trim-only) | Modify |
| `sound_track_agent/mixdown.py` | `assemble_and_mix` 接入卡点路径(门控) | Modify |
| `sound_track_agent/facade.py` | mix_fn 注入 cfg 的阈值/窗口 | Modify |
| `drama_shot_master/config.py` | 加 2 个全局字段 + 持久化 + 读取 | Modify |
| `drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py` | 加阈值/窗口两栏 | Modify |
| `drama_shot_master/ui/widgets/accent_editor_widget.py` | 卡点混音开关 + 泵感强度滑块 + 大卡点更大菱形 | Modify |
| `drama_shot_master/ui/windows/soundtrack_task_window.py` | 构造 AccentEditorWidget 时传入大卡点阈值 | Modify |

复用(不改):`sound_track_agent/beat_aligner.py` 的 `snap_boundaries_to_beats`(它本是孤儿,本计划给它接上第一个真实调用方)。

---

## Task 1: 泵感增益包络 `build_pump_envelope`(纯函数)

**Files:**
- Create: `sound_track_agent/accent_mixer.py`
- Test: `tests/test_sound_track_agent/test_accent_mixer.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sound_track_agent/test_accent_mixer.py
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_accent_mixer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sound_track_agent.accent_mixer'`

- [ ] **Step 3: 写最小实现**

```python
# sound_track_agent/accent_mixer.py
"""卡点感知混音纯算法 + 薄 I/O：泵感增益包络、段切目标时长。

build_pump_envelope / clip_targets / snapped_boundaries 为纯逻辑(可单测);
apply_pump 为 soundfile 薄包装。段切吸附复用 beat_aligner.snap_boundaries_to_beats。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from sound_track_agent.session import AccentPoint
from sound_track_agent.beat_aligner import snap_boundaries_to_beats


def build_pump_envelope(n_samples: int, sr: int, accents: list,
                        *, strength: float,
                        attack: float = 0.012, release: float = 0.35):
    """基线 1.0 的逐样本增益。每个卡点处下压到 (1 - strength*intensity)：
    attack 秒内 1.0→floor、release 秒内 floor→1.0。多卡点重叠取逐样本 min。
    """
    env = np.ones(int(n_samples), dtype=np.float32)
    if strength <= 0 or not accents or n_samples <= 0:
        return env
    a = max(1, int(round(attack * sr)))
    r = max(1, int(round(release * sr)))
    for ap in accents:
        depth = float(strength) * max(0.0, min(1.0, float(ap.intensity)))
        if depth <= 0:
            continue
        floor = 1.0 - depth
        idx = int(round(float(ap.t) * sr))
        a_lo = max(0, idx - a)
        if 0 <= idx < n_samples and idx > a_lo:               # attack 段
            ramp = np.linspace(1.0, floor, idx - a_lo, endpoint=False,
                               dtype=np.float32)
            env[a_lo:idx] = np.minimum(env[a_lo:idx], ramp)
        if 0 <= idx < n_samples:                              # 谷底
            env[idx] = min(env[idx], floor)
        r_hi = min(n_samples, idx + r + 1)
        if r_hi > idx + 1:                                    # release 段
            ramp = np.linspace(floor, 1.0, r_hi - (idx + 1), dtype=np.float32)
            env[idx + 1:r_hi] = np.minimum(env[idx + 1:r_hi], ramp)
    return env
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_accent_mixer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/accent_mixer.py tests/test_sound_track_agent/test_accent_mixer.py
git commit -m "feat(soundtrack): accent pump gain envelope (build_pump_envelope)"
```

---

## Task 2: `apply_pump`(soundfile 薄 I/O)

**Files:**
- Modify: `sound_track_agent/accent_mixer.py`
- Test: `tests/test_sound_track_agent/test_accent_mixer.py`

- [ ] **Step 1: 加失败测试**

```python
# 追加到 tests/test_sound_track_agent/test_accent_mixer.py
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_accent_mixer.py::test_apply_pump_attenuates_at_accent -v`
Expected: FAIL — `ImportError: cannot import name 'apply_pump'`

- [ ] **Step 3: 写实现(追加到 accent_mixer.py)**

```python
def apply_pump(bgm_in, bgm_out, accents: list, *, strength: float,
               attack: float = 0.012, release: float = 0.35) -> Path:
    """读 wav → 乘泵感包络 → 写出。返回输出路径。读/写失败抛 RuntimeError。"""
    import soundfile as sf
    try:
        data, sr = sf.read(str(bgm_in), always_2d=True)       # (n, ch)
    except Exception as e:
        raise RuntimeError(f"apply_pump 读取失败 {bgm_in}: {e}")
    env = build_pump_envelope(data.shape[0], sr, accents, strength=strength,
                              attack=attack, release=release)
    out = (data * env[:, None]).astype(data.dtype, copy=False)
    bgm_out = Path(bgm_out)
    bgm_out.parent.mkdir(parents=True, exist_ok=True)
    try:
        sf.write(str(bgm_out), out, sr)
    except Exception as e:
        raise RuntimeError(f"apply_pump 写出失败 {bgm_out}: {e}")
    return bgm_out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_accent_mixer.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/accent_mixer.py tests/test_sound_track_agent/test_accent_mixer.py
git commit -m "feat(soundtrack): apply_pump applies envelope to assembled BGM"
```

---

## Task 3: 段切目标时长 `snapped_boundaries` + `clip_targets`(纯逻辑,复用 beat_aligner)

**Files:**
- Modify: `sound_track_agent/accent_mixer.py`
- Test: `tests/test_sound_track_agent/test_accent_mixer.py`

- [ ] **Step 1: 加失败测试**

```python
# 追加到 tests/test_sound_track_agent/test_accent_mixer.py
from sound_track_agent.accent_mixer import snapped_boundaries, clip_targets


def test_snapped_boundaries_filters_small_and_snaps_near():
    segs = [2.0, 2.0, 2.0]                       # 自然内部接缝 [2.0, 4.0]
    accents = [AccentPoint(t=1.9, intensity=0.8),   # 大卡点,接缝 2.0 吸到 1.9
               AccentPoint(t=3.0, intensity=0.5)]   # 小卡点,被阈值过滤
    out = snapped_boundaries(segs, accents, big_threshold=0.7, window=0.5)
    assert out == [1.9, 4.0]                     # 4.0 最近大卡点 1.9 距 2.1>0.5 → 保留


def test_clip_targets_snaps_earlier_only():
    segs = [1.0, 1.0]
    accents = [AccentPoint(t=0.8, intensity=0.9)]   # 接缝 1.0 → 0.8(更早)
    assert clip_targets(segs, accents, big_threshold=0.7, window=0.6) == [0.8, None]


def test_clip_targets_never_extends():
    segs = [1.0, 1.0]
    accents = [AccentPoint(t=1.4, intensity=0.9)]   # 卡点在接缝之后 → trim-only 忽略
    assert clip_targets(segs, accents, big_threshold=0.7, window=0.6) == [None, None]


def test_clip_targets_ignores_below_threshold():
    segs = [1.0, 1.0]
    accents = [AccentPoint(t=0.8, intensity=0.5)]
    assert clip_targets(segs, accents, big_threshold=0.7, window=0.6) == [None, None]


def test_clip_targets_single_segment_is_noop():
    assert clip_targets([2.0], [AccentPoint(t=1.0, intensity=1.0)],
                        big_threshold=0.7, window=0.6) == [None]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_accent_mixer.py -k "snapped or clip_targets" -v`
Expected: FAIL — `ImportError: cannot import name 'snapped_boundaries'`

- [ ] **Step 3: 写实现(追加到 accent_mixer.py)**

```python
def snapped_boundaries(seg_durations: list, accents: list,
                       *, big_threshold: float, window: float) -> list:
    """各段时长 → 内部接缝(累加,去掉末段);把接缝吸附到 window 内最近的大卡点
    (intensity >= big_threshold)。复用 beat_aligner.snap_boundaries_to_beats。
    返回 len = 段数-1 的接缝时间(绝对秒)。"""
    bounds, acc = [], 0.0
    for d in seg_durations[:-1]:
        acc += float(d)
        bounds.append(acc)
    big = sorted(float(ap.t) for ap in accents
                 if float(ap.intensity) >= big_threshold)
    return snap_boundaries_to_beats(bounds, big, max_shift=window)


def clip_targets(seg_durations: list, accents: list,
                 *, big_threshold: float, window: float) -> list:
    """把吸附后的接缝换算成每段 clip 的目标时长(秒)。trim-only:接缝只允许
    比自然位置更早(裁短),更晚则忽略(保留自然 → None)。末段恒为 None(整段不裁)。
    返回 len = 段数 的列表,元素为 float(裁到该时长) 或 None(不裁)。"""
    n = len(seg_durations)
    if n <= 1:
        return [None] * n
    snapped = snapped_boundaries(seg_durations, accents,
                                 big_threshold=big_threshold, window=window)
    targets, prev, cum = [], 0.0, 0.0
    for i in range(n):
        if i == n - 1:
            targets.append(None)
            continue
        natural = cum + float(seg_durations[i])
        b = min(snapped[i], natural)              # trim-only:不许更晚
        b = max(b, prev + 0.05)                   # 防止 ≤0 / 越过前一接缝
        targets.append(None if abs(b - natural) < 1e-6 else round(b - prev, 6))
        prev, cum = b, natural
    return targets
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_accent_mixer.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/accent_mixer.py tests/test_sound_track_agent/test_accent_mixer.py
git commit -m "feat(soundtrack): trim-only segment-boundary snap to big accents (reuse beat_aligner)"
```

---

## Task 4: session 任务级字段 + 序列化

**Files:**
- Modify: `sound_track_agent/session.py:96-127`(`ScoringSession` dataclass + `to_dict` + `from_dict`)
- Test: `tests/test_sound_track_agent/test_session.py`

- [ ] **Step 1: 加失败测试**

```python
# 追加到 tests/test_sound_track_agent/test_session.py
from sound_track_agent.session import ScoringSession


def test_accent_mix_fields_default_and_roundtrip():
    s = ScoringSession(source_mp4="x", source_hash="h", global_style="g",
                       frame_rate=24.0)
    assert s.accent_mix_enabled is True
    assert abs(s.pump_strength - 0.6) < 1e-9
    d = s.to_dict()
    assert d["accent_mix_enabled"] is True and d["pump_strength"] == 0.6
    s2 = ScoringSession.from_dict(d)
    assert s2.accent_mix_enabled is True and s2.pump_strength == 0.6


def test_from_dict_missing_accent_mix_fields_uses_defaults():
    d = {"source_mp4": "x", "source_hash": "h", "global_style": "g",
         "frame_rate": 24.0, "segments": [], "accent_points": [], "output": None}
    s = ScoringSession.from_dict(d)
    assert s.accent_mix_enabled is True and abs(s.pump_strength - 0.6) < 1e-9
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_session.py -k accent_mix -v`
Expected: FAIL — `TypeError`/`AssertionError`(字段不存在)

- [ ] **Step 3: 改 `ScoringSession`**

在 `sound_track_agent/session.py` 的 `ScoringSession` dataclass 字段区(当前 `output: Optional[str] = None` 之后)加两行:

```python
    output: Optional[str] = None
    accent_mix_enabled: bool = True
    pump_strength: float = 0.6
```

在 `to_dict` 的返回 dict 里(`"output": self.output,` 之后)加:

```python
            "output": self.output,
            "accent_mix_enabled": self.accent_mix_enabled,
            "pump_strength": self.pump_strength,
```

在 `from_dict` 的 `cls(...)` 里(`output=d.get("output"),` 之后)加:

```python
            output=d.get("output"),
            accent_mix_enabled=bool(d.get("accent_mix_enabled", True)),
            pump_strength=float(d.get("pump_strength", 0.6)),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_session.py -v`
Expected: PASS(含原有用例 + 2 新增)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/session.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(soundtrack): persist per-task accent_mix_enabled + pump_strength on session"
```

---

## Task 5: `assemble_bgm` 支持按目标时长裁剪(trim-only)

**Files:**
- Modify: `sound_track_agent/bgm_assembler.py:8-46`
- Test: `tests/test_sound_track_agent/test_bgm_assembler.py`

- [ ] **Step 1: 加失败测试**

```python
# 追加到 tests/test_sound_track_agent/test_bgm_assembler.py
import numpy as np, soundfile as sf
from sound_track_agent.bgm_assembler import assemble_bgm


def _tone(p, freq, dur=1.0, sr=22050):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(str(p), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr)


def test_assemble_bgm_clip_durations_trims_first_clip(tmp_path):
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)
    out = tmp_path / "full.wav"
    assemble_bgm([b0, b1], out, crossfade=0.1, clip_durations=[0.4, None])
    info = sf.info(str(out))
    assert 1.1 < info.duration < 1.5      # 0.4 + 1.0 - 0.1 ≈ 1.3


def test_assemble_bgm_clip_durations_length_mismatch_raises(tmp_path):
    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    import pytest
    with pytest.raises(ValueError):
        assemble_bgm([b0], tmp_path / "o.wav", clip_durations=[0.4, None])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_bgm_assembler.py -k clip_durations -v`
Expected: FAIL — `TypeError: assemble_bgm() got an unexpected keyword argument 'clip_durations'`

- [ ] **Step 3: 改 `assemble_bgm` 签名 + 加 trim 预处理**

把 `sound_track_agent/bgm_assembler.py` 的函数签名与前段改成(其余 acrossfade 逻辑不变):

```python
def assemble_bgm(bgm_paths: list, out_path, *,
                 crossfade: float = 0.5,
                 clip_durations: list | None = None,
                 runner=subprocess.run) -> Path:
    """把分段 BGM 按顺序 crossfade 拼成整条。

    clip_durations(可选,长度需 == bgm_paths):元素为目标秒数则把对应 clip 先
    裁到该时长(trim-only:`-t` 比内容长则等于整段);为 None 不裁。裁剪失败降级用原片。
    """
    if not bgm_paths:
        raise ValueError("assemble_bgm 需要至少 1 段 BGM")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    paths = [str(p) for p in bgm_paths]

    if clip_durations is not None:
        if len(clip_durations) != len(paths):
            raise ValueError("clip_durations 长度需与 bgm_paths 一致")
        resolved = []
        for i, p in enumerate(paths):
            dur = clip_durations[i]
            if dur is None:
                resolved.append(p)
                continue
            tp = str(out_path.parent / f"_trim{i}.wav")
            r = runner(["ffmpeg", "-y", "-i", p, "-t", f"{float(dur):.3f}",
                        "-c:a", "pcm_s16le", tp], capture_output=True)
            resolved.append(tp if getattr(r, "returncode", 0) == 0
                            and Path(tp).exists() else p)
        paths = resolved

    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd += ["-i", p]
    # …(以下 1 段 / N 段 acrossfade 逻辑保持原样,基于 paths)…
```

> 注意:保留原文件后半段(`if len(paths) == 1: … else: …acrossfade…` 直到末尾)不变,只替换签名+开头到构造 `cmd` 之前的部分。

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_bgm_assembler.py -v`
Expected: PASS(原有 + 2 新增)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/bgm_assembler.py tests/test_sound_track_agent/test_bgm_assembler.py
git commit -m "feat(soundtrack): assemble_bgm trim-only clip_durations pre-pass"
```

---

## Task 6: `assemble_and_mix` 接入卡点路径(门控)

**Files:**
- Modify: `sound_track_agent/mixdown.py:1-54`
- Test: `tests/test_sound_track_agent/test_mixdown.py`

- [ ] **Step 1: 加失败测试**(沿用文件顶部已有的 `_make_video_with_audio` / `_tone` helper)

```python
# 追加到 tests/test_sound_track_agent/test_mixdown.py
from sound_track_agent.session import AccentPoint


def _two_seg_sess(v, b0, b1, *, enabled, accents):
    s = ScoringSession(
        source_mp4=str(v), source_hash="h", global_style="x", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=0)])
    s.accent_mix_enabled = enabled
    s.accent_points = list(accents)
    return s


def _fake_separate(audio_path, out_dir, **kw):
    return Path(audio_path), Path(audio_path)


def test_accent_path_calls_pump_when_enabled(tmp_path, monkeypatch):
    import sound_track_agent.mixdown as m
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)
    seen = {}

    def fake_pump(inp, outp, accents, **kw):
        seen["n"] = len(accents)
        import shutil; shutil.copy(str(inp), str(outp))
        return Path(outp)

    monkeypatch.setattr(m, "apply_pump", fake_pump)
    sess = _two_seg_sess(v, b0, b1, enabled=True,
                         accents=[AccentPoint(t=0.5, intensity=0.9)])
    out = m.assemble_and_mix(sess, v, tmp_path / "w", separate=_fake_separate)
    assert seen.get("n") == 1 and Path(out).exists()


def test_disabled_bypasses_pump(tmp_path, monkeypatch):
    import sound_track_agent.mixdown as m
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)

    def boom(*a, **k):
        raise AssertionError("关闭时不应调用 apply_pump")

    monkeypatch.setattr(m, "apply_pump", boom)
    sess = _two_seg_sess(v, b0, b1, enabled=False,
                         accents=[AccentPoint(t=0.5, intensity=0.9)])
    out = m.assemble_and_mix(sess, v, tmp_path / "w2", separate=_fake_separate)
    assert Path(out).exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_mixdown.py -k "accent_path or disabled" -v`
Expected: FAIL — `AttributeError: module 'sound_track_agent.mixdown' has no attribute 'apply_pump'`

- [ ] **Step 3: 改 `mixdown.py`**

在 import 区(`from sound_track_agent.audio_mixer import (...)` 之后)加:

```python
from sound_track_agent.accent_mixer import apply_pump, clip_targets
```

把 `assemble_and_mix` 整体替换为:

```python
def assemble_and_mix(sess: ScoringSession, video_path, work_dir, *,
                     crossfade: float = 0.5,
                     separate=separate_vocals,
                     target_lufs: float = -14.0,
                     big_threshold: float = 0.7,
                     snap_window: float = 0.6) -> str:
    """段 BGM 拼接 →(可选)段切对齐+泵感 → 分离对白 → ducking → 写回视频。

    当 sess.accent_mix_enabled 且有卡点时启用卡点路径;否则等同原逻辑(零回归)。
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    seg_bgms = [_chosen_bgm(s) for s in sess.segments]
    accents = list(getattr(sess, "accent_points", []) or [])
    use_accent = bool(getattr(sess, "accent_mix_enabled", True)) and bool(accents)

    if use_accent:
        targets = clip_targets([s.duration for s in sess.segments], accents,
                               big_threshold=big_threshold, window=snap_window)
        full_bgm = assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                crossfade=crossfade, clip_durations=targets)
        full_bgm = apply_pump(full_bgm, work_dir / "full_bgm_pumped.wav",
                              accents,
                              strength=float(getattr(sess, "pump_strength", 0.6)))
    else:
        full_bgm = assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                crossfade=crossfade)

    src_audio = extract_audio(video_path, work_dir / "src_audio.wav")
    vocals, _rest = separate(src_audio, work_dir / "sep")

    mixed = duck_and_mix(vocals, full_bgm, work_dir / "mixed.wav",
                         target_lufs=target_lufs)

    out_video = work_dir / (Path(video_path).stem + "_scored.mp4")
    replace_video_audio(video_path, mixed, out_video)
    return str(out_video)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_mixdown.py -v`
Expected: PASS(原有 end_to_end + 2 新增)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/mixdown.py tests/test_sound_track_agent/test_mixdown.py
git commit -m "feat(soundtrack): gate accent-aware (snap+pump) path in assemble_and_mix"
```

---

## Task 7: config 全局字段(大卡点阈值 / 吸附窗口)

**Files:**
- Modify: `drama_shot_master/config.py:77`(字段)、`:126`(update_settings dict)、`:259`(load_config 读取)
- Test: `tests/test_config_accent.py`(Create)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config_accent.py
import json
from drama_shot_master.config import Config


def test_accent_fields_default():
    c = Config()
    assert abs(c.accent_big_threshold - 0.7) < 1e-9
    assert abs(c.accent_snap_window - 0.6) < 1e-9


def test_accent_fields_persist(tmp_path):
    sp = tmp_path / "settings.json"
    c = Config(settings_path=sp)
    c.update_settings(accent_big_threshold=0.5, accent_snap_window=1.0)
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["accent_big_threshold"] == 0.5
    assert data["accent_snap_window"] == 1.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_config_accent.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'accent_big_threshold'`

- [ ] **Step 3: 改 `config.py`**

字段区 `soundtrack_crossfade: float = 0.5` 之后加:

```python
    soundtrack_crossfade: float = 0.5
    accent_big_threshold: float = 0.7
    accent_snap_window: float = 0.6
```

`update_settings` 的持久化 dict 里 `"soundtrack_crossfade": self.soundtrack_crossfade,` 之后加:

```python
                "soundtrack_crossfade": self.soundtrack_crossfade,
                "accent_big_threshold": self.accent_big_threshold,
                "accent_snap_window": self.accent_snap_window,
```

`load_config` 里 `cfg.soundtrack_crossfade = float(...)` 那个 if 块之后加:

```python
                if isinstance(data.get("accent_big_threshold"), (int, float)):
                    cfg.accent_big_threshold = float(data["accent_big_threshold"])
                if isinstance(data.get("accent_snap_window"), (int, float)):
                    cfg.accent_snap_window = float(data["accent_snap_window"])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_config_accent.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/config.py tests/test_config_accent.py
git commit -m "feat(soundtrack): add accent_big_threshold/accent_snap_window global config"
```

---

## Task 8: facade 把 cfg 阈值/窗口注入 mix_fn

**Files:**
- Modify: `sound_track_agent/facade.py:62-71`(`_build_real_stages` 里的 `mix_fn=partial(...)`)

> 说明:此为一行级 wiring,且 `_build_real_stages` 在 import 时依赖宿主(`RunningHubClient`),不在 agent 单测范围内孤立可测;正确性由"Task 6 的默认值兜底 + 现有 facade 测试仍通过"保证。无新增测试。

- [ ] **Step 1: 改 `_build_real_stages` 的 mix_fn**

把:

```python
        mix_fn=partial(assemble_and_mix, video_path=video_path,
                       work_dir=work_dir),
```

改为:

```python
        mix_fn=partial(assemble_and_mix, video_path=video_path,
                       work_dir=work_dir,
                       big_threshold=float(getattr(cfg, "accent_big_threshold", 0.7)),
                       snap_window=float(getattr(cfg, "accent_snap_window", 0.6))),
```

- [ ] **Step 2: 跑现有 facade 测试确认无回归**

Run: `$PY -m pytest tests/test_sound_track_agent/test_facade.py -v`
Expected: PASS(全部原有用例)

- [ ] **Step 3: 提交**

```bash
git add sound_track_agent/facade.py
git commit -m "feat(soundtrack): inject accent threshold/window from cfg into mix_fn"
```

---

## Task 9: 设置→配乐 加阈值/窗口两栏

**Files:**
- Modify: `drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py`
- Test: `tests/test_ui/test_soundtrack_settings_smoke.py`

- [ ] **Step 1: 加失败测试**

```python
# 改 tests/test_ui/test_soundtrack_settings_smoke.py 的 _Cfg 增加两个字段，并加新用例
# _Cfg 类体内补充：
#     accent_big_threshold = 0.7
#     accent_snap_window = 0.6
# 新增用例：

def test_dialog_loads_and_saves_accent_fields():
    _app()
    cfg = _Cfg()
    dlg = SoundtrackSettingsDialog(cfg)
    assert abs(dlg.big_thresh_spin.value() - 0.7) < 1e-6
    assert abs(dlg.snap_window_spin.value() - 0.6) < 1e-6
    dlg.big_thresh_spin.setValue(0.5)
    dlg.snap_window_spin.setValue(1.0)
    dlg.accept()
    assert abs(cfg.accent_big_threshold - 0.5) < 1e-6
    assert abs(cfg.accent_snap_window - 1.0) < 1e-6
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_settings_smoke.py -v`
Expected: FAIL — `AttributeError: 'SoundtrackSettingsDialog' object has no attribute 'big_thresh_spin'`

- [ ] **Step 3: 改 dialog**

在 `_build_ui` 的 `form.addRow("crossfade 时长", self.crossfade_spin)` 之后加:

```python
        self.big_thresh_spin = QDoubleSpinBox()
        self.big_thresh_spin.setRange(0.0, 1.0); self.big_thresh_spin.setSingleStep(0.05)
        self.big_thresh_spin.setDecimals(2)
        form.addRow("大卡点强度阈值", self.big_thresh_spin)

        self.snap_window_spin = QDoubleSpinBox()
        self.snap_window_spin.setRange(0.0, 3.0); self.snap_window_spin.setSingleStep(0.1)
        self.snap_window_spin.setDecimals(1); self.snap_window_spin.setSuffix(" s")
        form.addRow("段切吸附窗口", self.snap_window_spin)
```

在 `_load_from_cfg` 末尾加:

```python
        self.big_thresh_spin.setValue(
            float(getattr(self.cfg, "accent_big_threshold", 0.7)))
        self.snap_window_spin.setValue(
            float(getattr(self.cfg, "accent_snap_window", 0.6)))
```

在 `accept` 的 `update_settings(...)` 调用里补两个参数:

```python
        self.cfg.update_settings(
            soundtrack_workflow_id=self.workflow_edit.text().strip(),
            soundtrack_output_dir=self.out_edit.text().strip(),
            soundtrack_seeds_count=self.seeds_spin.value(),
            soundtrack_crossfade=self.crossfade_spin.value(),
            accent_big_threshold=self.big_thresh_spin.value(),
            accent_snap_window=self.snap_window_spin.value(),
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_settings_smoke.py -v`
Expected: PASS(原有 + 1 新增)

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py tests/test_ui/test_soundtrack_settings_smoke.py
git commit -m "feat(soundtrack): accent threshold/window fields in 配乐设置 dialog"
```

---

## Task 10: ③卡点页 开关 + 泵感强度滑块 + 大卡点更大菱形

**Files:**
- Modify: `drama_shot_master/ui/widgets/accent_editor_widget.py`
- Modify: `drama_shot_master/ui/windows/soundtrack_task_window.py:149`(构造 AccentEditorWidget 传阈值)
- Test: `tests/test_ui/test_accent_editor_smoke.py`

- [ ] **Step 1: 加失败测试**

```python
# 追加到 tests/test_ui/test_accent_editor_smoke.py
def test_mix_toggle_and_pump_slider_write_session():
    _app()
    sess = _sess()
    w = AccentEditorWidget(sess)
    seen = []
    w.accentsChanged.connect(lambda: seen.append(1))
    assert w.chk_mix.isChecked() is True            # 默认开
    w.chk_mix.setChecked(False)
    assert sess.accent_mix_enabled is False and seen
    w.pump_slider.setValue(30)
    assert abs(sess.pump_strength - 0.30) < 1e-6


def test_big_threshold_param_kept():
    _app()
    w = AccentEditorWidget(_sess(), big_threshold=0.4)
    assert w.timeline._big_threshold == 0.4
```

> `_sess()` 已在该测试文件中定义(段 + 卡点)。

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_accent_editor_smoke.py -k "mix_toggle or big_threshold" -v`
Expected: FAIL — `AttributeError: 'AccentEditorWidget' object has no attribute 'chk_mix'`

- [ ] **Step 3: 改 `accent_editor_widget.py`**

(a) `_AccentTimeline.__init__` 增加阈值参数并存字段:

```python
    def __init__(self, session, parent=None, *, big_threshold: float = 0.7):
        super().__init__(parent)
        self._session = session
        self._selected = -1
        self._big_threshold = big_threshold
        self.setMinimumHeight(96)
```

(b) `_AccentTimeline.paintEvent` 里画菱形那段,菱形半径按是否大卡点变化。把:

```python
            poly = QPolygonF([QPointF(x, my - 7), QPointF(x + 6, my),
                              QPointF(x, my + 7), QPointF(x - 6, my)])
```

改为:

```python
            rad = 9 if a.intensity >= self._big_threshold else 6
            poly = QPolygonF([QPointF(x, my - rad - 1), QPointF(x + rad, my),
                              QPointF(x, my + rad + 1), QPointF(x - rad, my)])
```

(c) `AccentEditorWidget.__init__` 增加 `big_threshold` 参数:

```python
    def __init__(self, session, parent=None, *, big_threshold: float = 0.7):
        super().__init__(parent)
        self._session = session
        self._worker = None
        self._big_threshold = big_threshold
        self._build_ui()
        self._refresh()
```

(d) `_build_ui` 里构造 timeline 处传入阈值:

```python
        self.timeline = _AccentTimeline(self._session,
                                        big_threshold=self._big_threshold)
```

(e) `_build_ui` 顶部工具行(`top` 这一 QHBoxLayout,在 `top.addWidget(self.btn_detect)` 之后、`root.addLayout(top)` 之前)插入开关+滑块。先在文件顶部 import 补 `QCheckBox, QSlider` 和 `Qt`:

```python
from PySide6.QtCore import Signal, QRectF, QPointF, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QDoubleSpinBox, QMessageBox, QCheckBox, QSlider,
)
```

然后在 `top` 行加控件(放在 `self.btn_detect` 之前,使开关/滑块在左、检测按钮在右):

```python
        self.chk_mix = QCheckBox("卡点混音")
        self.chk_mix.setChecked(bool(getattr(self._session, "accent_mix_enabled", True)))
        self.chk_mix.toggled.connect(self._on_mix_toggled)
        top.addWidget(self.chk_mix)
        top.addWidget(QLabel("泵感"))
        self.pump_slider = QSlider(Qt.Horizontal)
        self.pump_slider.setRange(0, 100)
        self.pump_slider.setFixedWidth(120)
        self.pump_slider.setValue(int(round(float(getattr(self._session, "pump_strength", 0.6)) * 100)))
        self.pump_slider.valueChanged.connect(self._on_pump_changed)
        top.addWidget(self.pump_slider)
```

(f) 加两个槽函数(放在 `_on_auto_detect` 附近):

```python
    def _on_mix_toggled(self, checked: bool):
        self._session.accent_mix_enabled = bool(checked)
        self.accentsChanged.emit()

    def _on_pump_changed(self, val: int):
        self._session.pump_strength = val / 100.0
        self.accentsChanged.emit()
```

> 复用既有 `accentsChanged` → 任务窗的 `_persist_session` 落盘通道,改动即存。

(g) 改 `drama_shot_master/ui/windows/soundtrack_task_window.py` 的 `_mount_session_tabs`,把:

```python
        self._accent = AccentEditorWidget(self._session)
```

改为:

```python
        self._accent = AccentEditorWidget(
            self._session,
            big_threshold=float(getattr(self.cfg, "accent_big_threshold", 0.7)))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_accent_editor_smoke.py -v`
Expected: PASS(原有 7 + 2 新增)

- [ ] **Step 5: 任务窗冒烟回归**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_window_smoke.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/widgets/accent_editor_widget.py drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_accent_editor_smoke.py
git commit -m "feat(soundtrack): ③卡点 mix toggle + pump slider + big-accent markers"
```

---

## Task 11: 依赖声明 + 全量回归

**Files:**
- Modify: `pyproject.toml`(dependencies 加 soundfile)

- [ ] **Step 1: 确认 soundfile 已被运行时依赖**

`accent_mixer.apply_pump` 运行期 import soundfile。把 `pyproject.toml` 的 `dependencies` 列表里(`"numpy>=1.24",` 附近)加一行(若尚无):

```toml
    "soundfile>=0.12",
```

> 仅当 dependencies 中尚未列出 soundfile 时才加。先 `grep -n soundfile pyproject.toml` 确认。

- [ ] **Step 2: 全量回归(sound_track_agent + 配乐相关 UI)**

```bash
$PY -m pytest tests/test_sound_track_agent -q
QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_accent_editor_smoke.py tests/test_ui/test_soundtrack_window_smoke.py tests/test_ui/test_soundtrack_settings_smoke.py tests/test_ui/test_soundtrack_panel_smoke.py -q
$PY -m pytest tests/test_config_accent.py -q
```
Expected: 全部 PASS。

> UI 测试逐文件单独跑过即可(同一进程跑全部 test_ui 退出时有已知的 C 扩展卸载 segfault,与本功能无关;逐文件 rc=0)。若需要可分文件运行。

- [ ] **Step 3: 提交**

```bash
git add pyproject.toml
git commit -m "build(soundtrack): declare soundfile dependency for accent pump"
```

---

## 手动验证(交付前,用户在真实 Windows 机器上)

代码层 offscreen 只能冒烟;真实听感需用户验证:
1. 打开一个配乐任务 → 跑到出片(②全部选定 + ①「停在」选「出片」)。
2. 关「卡点混音」出一版、开「卡点混音」+ 拖「泵感」出另一版,A/B 对比:开的那版应在动作爆点处有明显"泵"的呼吸感;大卡点处转场更贴。
3. 在 设置→配乐 调「大卡点强度阈值」「段切吸附窗口」,确认③卡点页大卡点菱形随阈值变大/变小、出片转场吸附行为变化。

---

## Self-Review

**1. Spec 覆盖:**
- §1 强调层泵感 → Task 1/2/6 ✅;§1 段切对齐 → Task 3/5/6 ✅;§1 门控 → Task 6 ✅;§1 方案2 不做 → 计划未实现 ✅(且复用了 beat_aligner,未删它,留作未来)。
- §2 trim-only 安全规则 → Task 3 `clip_targets`(min(b,natural)、末段 None)+ Task 5(`-t` 不拉长)✅。
- §3 三个函数 → Task 1(envelope)/2(apply_pump)/3(snapped_boundaries+clip_targets)✅;依赖 soundfile → Task 11 ✅;不需 librosa ✅。
- §4 mixdown 接入流程 → Task 6 ✅。
- §5 数据模型(session 2 字段)→ Task 4;全局 cfg 2 字段 → Task 7;facade 注入 → Task 8 ✅。
- §6 UI(开关+滑块+大卡点菱形)→ Task 10;设置两字段 → Task 9 ✅。
- §7 错误处理(apply_pump 抛、snap 降级、裁剪失败降级)→ Task 2/5/3 ✅。
- §8 测试 + 自包含 → 各 Task 测试 + Task 11 回归 ✅。

**2. 占位符扫描:** 无 TBD/TODO;每个改码步骤都给了完整代码或精确替换说明。Task 5 复用原文件后半段以"保持原样"说明(已指明边界),Task 8 为一行 wiring 已给完整 before/after。

**3. 类型一致性:** `apply_pump(bgm_in, bgm_out, accents, *, strength, ...)` 在 Task 2 定义、Task 6 调用一致;`clip_targets(seg_durations, accents, *, big_threshold, window)` 在 Task 3 定义、Task 6 调用一致;`snapped_boundaries` 同;session 字段 `accent_mix_enabled`/`pump_strength` 在 Task 4 定义、Task 6/10 使用一致;cfg `accent_big_threshold`/`accent_snap_window` 在 Task 7 定义、Task 8/9/10 使用一致;`_AccentTimeline._big_threshold` 在 Task 10 定义并被同任务测试断言一致。
