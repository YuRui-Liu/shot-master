# 配乐 Mix 阶段优化（真·卡点 + 复用对白轨）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `sound_track_agent` mix 阶段加上真·卡点（锚点式局部时间拉伸把音乐重拍精确对齐到大爆点）和对白轨复用（TTS 干轨替代 Demucs 盲分离）。

**Architecture:** 在现有聚焦模块内增量：`beat_aligner` 加 `align_beats_to_accents`（核心算法）；`accent_mixer.apply_pump` 加 `skip_indices` 跳过已对齐爆点；`audio_mixer` 加 `assemble_dialogue_track`（ffmpeg adelay+amix 装配定时对白轨）；`mixdown.assemble_and_mix` 编排新流水线（align→pump(skip)→dialogue OR Demucs→ducking）；`session.dialogue_segments` 持久化；`facade` 入参兼容、`build_accent_preview` 与 `assemble_and_mix` 共用同一 align+pump 流程。

**Tech Stack:** Python 3.10+、`librosa.effects.time_stretch`（已是 Phase 1 依赖）、`soundfile`、`numpy`、`ffmpeg`（adelay/amix/anullsrc）、`pytest`。**无新依赖**。

参考 spec：`docs/superpowers/specs/2026-05-28-soundtrack-mix-beat-sync-dialogue-design.md`

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `sound_track_agent/session.py` | + `DialogueSegment`、`ScoringSession.dialogue_segments` | 改 |
| `sound_track_agent/accent_mixer.py` | `apply_pump` / `build_pump_envelope` 加 `skip_indices` | 改 |
| `sound_track_agent/beat_aligner.py` | + `_plan_alignment`、`_chunks_from_plan`、`align_beats_to_accents` | 改 |
| `sound_track_agent/audio_mixer.py` | + `assemble_dialogue_track` | 改 |
| `sound_track_agent/mixdown.py` | `assemble_and_mix` 编排新流水线 | 改 |
| `sound_track_agent/facade.py` | `prepare_session`/`advance` 加 `dialogue_segments` 入参；`build_accent_preview` 同源 | 改 |
| `tests/test_sound_track_agent/test_*.py` | 单测扩展 | 改 |

实现顺序按依赖：data → 小工具（pump skip）→ 核心算法（align）→ 对白装配 → 编排 → facade 接线。

---

## Task 1: `session.py` — DialogueSegment + 持久化

**Files:**
- Modify: `sound_track_agent/session.py`
- Test: `tests/test_sound_track_agent/test_session.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_session.py`：

```python
from sound_track_agent.session import (
    ScoringSession, SegmentScore, DialogueSegment,
)


def test_dialogue_segment_roundtrip():
    d = DialogueSegment(audio_path="/x/a.flac", t_start=1.5, duration=3.0)
    back = DialogueSegment.from_dict(d.to_dict())
    assert back.audio_path == "/x/a.flac"
    assert back.t_start == 1.5
    assert back.duration == 3.0


def test_session_dialogue_segments_roundtrip(tmp_path):
    sess = ScoringSession(
        source_mp4="x.mp4", source_hash="h", global_style="s", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)],
        dialogue_segments=[
            DialogueSegment(audio_path="/x/d1.flac", t_start=0.0, duration=1.0),
            DialogueSegment(audio_path="/x/d2.flac", t_start=2.5, duration=0.8),
        ])
    p = tmp_path / "session.json"
    sess.save(p)
    back = ScoringSession.load(p)
    assert len(back.dialogue_segments) == 2
    assert back.dialogue_segments[0].audio_path == "/x/d1.flac"
    assert back.dialogue_segments[1].t_start == 2.5


def test_session_dialogue_segments_default_when_missing(tmp_path):
    """旧 session.json 缺字段时默认空列表（零回归）。"""
    p = tmp_path / "session.json"
    p.write_text(
        '{"source_mp4":"x","source_hash":"h","global_style":"s",'
        '"frame_rate":24.0,"segments":[],"accent_points":[]}',
        encoding="utf-8")
    back = ScoringSession.load(p)
    assert back.dialogue_segments == []
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q`
Expected: FAIL（无 `DialogueSegment` / 无 `dialogue_segments` 字段）

- [ ] **Step 3: 加 `DialogueSegment` dataclass**

在 `sound_track_agent/session.py` 中（与 `BGMCandidate`、`AccentPoint` 同级），添加：

```python
@dataclass
class DialogueSegment:
    """对白音频段：绝对路径 + 秒级定位。"""
    audio_path: str
    t_start: float
    duration: float

    def to_dict(self) -> dict:
        return {"audio_path": self.audio_path,
                "t_start": self.t_start, "duration": self.duration}

    @classmethod
    def from_dict(cls, d: dict) -> "DialogueSegment":
        return cls(audio_path=str(d["audio_path"]),
                   t_start=float(d["t_start"]),
                   duration=float(d["duration"]))
```

- [ ] **Step 4: 给 `ScoringSession` 加 `dialogue_segments` 字段**

在 `ScoringSession` 的 `pump_strength: float = 0.6` 之后加字段：

```python
    dialogue_segments: list = field(default_factory=list)
```

在 `ScoringSession.to_dict` 返回 dict 中加一项（与 `"pump_strength"` 同级）：

```python
            "dialogue_segments": [d.to_dict() for d in self.dialogue_segments],
```

在 `ScoringSession.from_dict` 的构造里加一行（与 `pump_strength=` 同级）：

```python
            dialogue_segments=[DialogueSegment.from_dict(d)
                               for d in data.get("dialogue_segments", [])],
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/session.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(soundtrack): + DialogueSegment 与 session.dialogue_segments 持久化

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `accent_mixer.py` — pump 跳过对齐爆点

**Files:**
- Modify: `sound_track_agent/accent_mixer.py`
- Test: `tests/test_sound_track_agent/test_accent_mixer.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_accent_mixer.py`：

```python
import numpy as np

from sound_track_agent.accent_mixer import build_pump_envelope
from sound_track_agent.session import AccentPoint


def test_build_pump_envelope_skip_indices_no_dip():
    sr = 22050
    n = sr * 4
    accents = [AccentPoint(t=1.0, intensity=0.9),
               AccentPoint(t=2.0, intensity=0.9),
               AccentPoint(t=3.0, intensity=0.9)]
    # 跳过第 1 个（index=1, t=2.0）
    env = build_pump_envelope(n, sr, accents, strength=0.6,
                              skip_indices=frozenset({1}))
    # t=1.0 与 t=3.0 处应有下压；t=2.0 处不应有
    i0 = int(1.0 * sr); i1 = int(2.0 * sr); i2 = int(3.0 * sr)
    assert env[i0] < 0.6                # 命中下压
    assert env[i1] == 1.0               # 跳过，基线
    assert env[i2] < 0.6                # 命中下压


def test_build_pump_envelope_skip_empty_unchanged():
    """skip_indices 缺省 frozenset() 时行为与旧版一致。"""
    sr = 22050; n = sr * 2
    a = [AccentPoint(t=1.0, intensity=0.9)]
    env_default = build_pump_envelope(n, sr, a, strength=0.6)
    env_empty = build_pump_envelope(n, sr, a, strength=0.6,
                                    skip_indices=frozenset())
    assert np.array_equal(env_default, env_empty)
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_accent_mixer.py -q`
Expected: FAIL（`build_pump_envelope` 不接受 `skip_indices` 关键字）

- [ ] **Step 3: 给 `build_pump_envelope` 加 `skip_indices`**

打开 `sound_track_agent/accent_mixer.py`。把 `build_pump_envelope` 的签名与循环替换为：

```python
def build_pump_envelope(n_samples: int, sr: int, accents: list[AccentPoint],
                        *, strength: float,
                        attack: float = 0.012, release: float = 0.35,
                        skip_indices: frozenset = frozenset()):
    """基线 1.0 的逐样本增益。每个卡点处下压到 (1 - strength*intensity)：
    attack 秒内 1.0→floor、release 秒内 floor→1.0。多卡点重叠取逐样本 min。

    skip_indices 中的爆点下标不下压（已被重拍精准命中，无需再削音量）。
    """
    n = int(n_samples)
    env = np.ones(max(0, n), dtype=np.float32)
    if strength <= 0 or not accents or n <= 0:
        return env
    a = max(1, int(round(attack * sr)))
    r = max(1, int(round(release * sr)))
    for i, ap in enumerate(accents):
        if i in skip_indices:
            continue
        depth = float(strength) * max(0.0, min(1.0, float(ap.intensity)))
        if depth <= 0:
            continue
        floor = 1.0 - depth
        idx = int(round(float(ap.t) * sr))
        if idx < 0 or idx >= n:
            continue
        a_lo = max(0, idx - a)
        if idx > a_lo:                                        # attack 段
            ramp = np.linspace(1.0, floor, idx - a_lo, endpoint=False,
                               dtype=np.float32)
            env[a_lo:idx] = np.minimum(env[a_lo:idx], ramp)
        env[idx] = min(env[idx], floor)                       # 谷底
        r_hi = min(n, idx + r + 1)
        if r_hi > idx + 1:                                    # release 段
            ramp = np.linspace(floor, 1.0, r_hi - (idx + 1), dtype=np.float32)
            env[idx + 1:r_hi] = np.minimum(env[idx + 1:r_hi], ramp)
    return env
```

- [ ] **Step 4: 给 `apply_pump` 也加 `skip_indices`**

替换 `apply_pump` 函数为：

```python
def apply_pump(bgm_in, bgm_out, accents: list, *, strength: float,
               attack: float = 0.012, release: float = 0.35,
               skip_indices: frozenset = frozenset()) -> Path:
    """读 wav → 乘泵感包络 → 写出。返回输出路径。读/写失败抛 RuntimeError。"""
    import soundfile as sf
    try:
        data, sr = sf.read(str(bgm_in), always_2d=True)       # (n, ch)
    except Exception as e:
        raise RuntimeError(f"apply_pump 读取失败 {bgm_in}: {e}")
    env = build_pump_envelope(data.shape[0], sr, accents, strength=strength,
                              attack=attack, release=release,
                              skip_indices=skip_indices)
    out = (data * env[:, None]).astype(data.dtype, copy=False)
    bgm_out = Path(bgm_out)
    bgm_out.parent.mkdir(parents=True, exist_ok=True)
    try:
        sf.write(str(bgm_out), out, sr)
    except Exception as e:
        raise RuntimeError(f"apply_pump 写出失败 {bgm_out}: {e}")
    return bgm_out
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_accent_mixer.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/accent_mixer.py tests/test_sound_track_agent/test_accent_mixer.py
git commit -m "feat(soundtrack): apply_pump/build_pump_envelope 加 skip_indices 跳过对齐爆点

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `beat_aligner.py` — 锚点式局部时间拉伸

**Files:**
- Modify: `sound_track_agent/beat_aligner.py`
- Test: `tests/test_sound_track_agent/test_beat_aligner.py`

- [ ] **Step 1: 写失败测试（纯逻辑 + 集成）**

追加到 `tests/test_sound_track_agent/test_beat_aligner.py`：

```python
import numpy as np

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
    """beats=[1.8] accent t=2.0 → factor=2.0/1.8≈1.111 在 ±10% 边界，可对齐。"""
    aligned = _plan_alignment([1.8], [_ap(2.0)], max_stretch=0.12,
                              big_threshold=0.7)
    assert aligned == [(0, 2.0, 1.8)]


def test_plan_alignment_rejects_factor_beyond_stretch():
    """beats=[1.5] accent t=2.0 → factor=2.0/1.5≈1.333 超 ±10% 跳过。"""
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
    # accent1 t=2.0 ← beat 1.9（factor=2.0/1.9≈1.053）
    # accent2 t=4.0 ← beat 3.8（factor=(4-2)/(3.8-1.9)=2.0/1.9≈1.053）
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
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_beat_aligner.py -q`
Expected: FAIL（`_plan_alignment` / `_chunks_from_plan` / `align_beats_to_accents` 不存在）

- [ ] **Step 3: 实现 `_plan_alignment` + `_chunks_from_plan`（纯逻辑）**

在 `sound_track_agent/beat_aligner.py` 末尾追加：

```python
def _plan_alignment(beats: list[float], accents: list,
                    max_stretch: float, big_threshold: float):
    """纯逻辑：选哪些 big-accent 能局部拉伸对齐到 beat。

    Returns: list of (accent_idx, accent_t, beat_t) 按时间升序。
    """
    big = sorted([(i, float(a.t)) for i, a in enumerate(accents)
                  if float(a.intensity) >= big_threshold],
                 key=lambda x: x[1])
    aligned = []
    used = set()
    prev_t, prev_b = 0.0, 0.0
    for (i, t) in big:
        candidates = [b for b in beats
                      if b <= t and b not in used and b > prev_b]
        if not candidates:
            continue
        b = max(candidates)
        if (b - prev_b) <= 0:
            continue
        if (t - prev_t) <= 0:
            continue
        factor = (b - prev_b) / (t - prev_t)        # rate for time_stretch
        if abs(factor - 1.0) > max_stretch:
            continue
        aligned.append((i, t, b))
        used.add(b)
        prev_t, prev_b = t, b
    return aligned


def _chunks_from_plan(aligned, total_dur: float):
    """纯逻辑：对齐计划 → 拉伸 chunks。

    Returns list of (kind, src_start, src_end, target_dur):
    - "stretch" 段：源音频 [src_start, src_end] 拉/压到 target_dur 秒
    - "tail" 段：末段原速保留
    """
    chunks = []
    prev_t, prev_b = 0.0, 0.0
    for (_, t, b) in aligned:
        chunks.append(("stretch", prev_b, b, t - prev_t))
        prev_t, prev_b = t, b
    chunks.append(("tail", prev_b, float(total_dur),
                   float(total_dur) - prev_t))
    return chunks
```

- [ ] **Step 4: 实现 `align_beats_to_accents`（注入式 I/O）**

在 `sound_track_agent/beat_aligner.py` 末尾追加：

```python
def align_beats_to_accents(bgm_path, accents: list, *,
                           max_stretch: float = 0.10,
                           big_threshold: float = 0.7,
                           out_path=None,
                           extractor=None, stretcher=None,
                           reader=None, writer=None):
    """把音乐重拍局部拉伸到大爆点；返回 (out_path, aligned_indices)。

    注入点（缺省用 librosa + soundfile）：
      - extractor(path) -> list[float]    默认 extract_beats
      - reader(path)    -> (np.ndarray, sr)   默认 soundfile.read(always_2d=True)
      - writer(path, samples, sr) -> None  默认 soundfile.write
      - stretcher(y, rate) -> y_new        默认 librosa.effects.time_stretch

    失败降级（librosa 不可用 / beats 空 / 任意异常）→ 返回 (bgm_path, frozenset())。
    """
    from pathlib import Path
    try:
        import numpy as np

        if extractor is None:
            extractor = extract_beats
        beats = list(extractor(bgm_path) or [])
        if not beats:
            return Path(bgm_path), frozenset()

        if reader is None:
            import soundfile as sf
            reader = lambda p: sf.read(str(p), always_2d=True)
        if writer is None:
            import soundfile as sf
            writer = lambda p, d, s: sf.write(str(p), d, s)
        if stretcher is None:
            import librosa
            stretcher = lambda y, rate: librosa.effects.time_stretch(y, rate=rate)

        data, sr = reader(bgm_path)
        if data is None or sr is None or data.shape[0] == 0:
            return Path(bgm_path), frozenset()
        total_dur = data.shape[0] / float(sr)

        plan = _plan_alignment(beats, accents, max_stretch, big_threshold)
        if not plan:
            return Path(bgm_path), frozenset()

        chunks = _chunks_from_plan(plan, total_dur)
        out_path = Path(out_path) if out_path else Path(bgm_path).with_suffix(
            ".aligned.wav")

        pieces = []
        for kind, src_start, src_end, target in chunks:
            s = max(0, int(round(src_start * sr)))
            e = min(data.shape[0], int(round(src_end * sr)))
            seg = data[s:e]
            if seg.shape[0] == 0:
                continue
            if kind == "stretch" and target > 0:
                rate = (src_end - src_start) / target
                if seg.ndim == 1 or seg.shape[1] == 1:
                    mono = seg.reshape(-1).astype("float64", copy=False)
                    out = stretcher(mono, rate=rate)
                    seg = out.reshape(-1, 1) if data.ndim == 2 else out
                else:
                    chans = [stretcher(np.ascontiguousarray(seg[:, c]).astype(
                        "float64", copy=False), rate=rate)
                        for c in range(seg.shape[1])]
                    L = min(len(c) for c in chans)
                    seg = np.stack([c[:L] for c in chans], axis=1)
            pieces.append(seg)

        result = np.concatenate(pieces, axis=0)
        writer(out_path, result.astype(data.dtype, copy=False), sr)
        return out_path, frozenset(idx for (idx, _, _) in plan)
    except Exception:
        return Path(bgm_path), frozenset()
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_beat_aligner.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/beat_aligner.py tests/test_sound_track_agent/test_beat_aligner.py
git commit -m "feat(soundtrack): beat_aligner 加锚点式局部时间拉伸（真·卡点核心）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `audio_mixer.py` — 对白轨装配

**Files:**
- Modify: `sound_track_agent/audio_mixer.py`
- Test: `tests/test_sound_track_agent/test_audio_mixer.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_audio_mixer.py`：

```python
from sound_track_agent.audio_mixer import assemble_dialogue_track
from sound_track_agent.session import DialogueSegment


class _FakeResult:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stderr = b""


def test_assemble_dialogue_track_empty_uses_silence_only(tmp_path):
    """空段列表 → 只生成静音底轨。"""
    captured = {}
    def runner(cmd, capture_output=False):
        captured["cmd"] = cmd
        (tmp_path / "out.wav").write_bytes(b"WAV")
        return _FakeResult(returncode=0)
    out = assemble_dialogue_track(
        [], total_duration=5.0, out_path=tmp_path / "out.wav", runner=runner)
    cmd = captured["cmd"]
    assert "anullsrc=channel_layout=stereo:sample_rate=44100" in " ".join(cmd)
    assert "-filter_complex" not in cmd                # 单输入路径
    assert out == tmp_path / "out.wav"


def test_assemble_dialogue_track_segments_adelay_and_amix(tmp_path):
    captured = {}
    def runner(cmd, capture_output=False):
        captured["cmd"] = cmd
        (tmp_path / "out.wav").write_bytes(b"WAV")
        return _FakeResult(returncode=0)
    segs = [DialogueSegment(audio_path="/x/a.flac", t_start=1.5, duration=1.0),
            DialogueSegment(audio_path="/x/b.flac", t_start=3.0, duration=0.8)]
    assemble_dialogue_track(segs, total_duration=5.0,
                            out_path=tmp_path / "out.wav", runner=runner)
    cmd = " ".join(captured["cmd"])
    assert "-i /x/a.flac" in cmd
    assert "-i /x/b.flac" in cmd
    assert "adelay=1500:all=1" in cmd                  # 1.5s → 1500ms
    assert "adelay=3000:all=1" in cmd
    assert "amix=inputs=3:duration=first:normalize=0" in cmd


def test_assemble_dialogue_track_ffmpeg_failure_raises(tmp_path):
    def runner(cmd, capture_output=False):
        return _FakeResult(returncode=1)
    import pytest
    with pytest.raises(RuntimeError, match="ffmpeg"):
        assemble_dialogue_track([], total_duration=2.0,
                                out_path=tmp_path / "out.wav", runner=runner)
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_audio_mixer.py -q`
Expected: FAIL（`assemble_dialogue_track` 不存在）

- [ ] **Step 3: 实现 `assemble_dialogue_track`**

在 `sound_track_agent/audio_mixer.py` 末尾追加：

```python
def assemble_dialogue_track(segments, total_duration: float, out_path,
                            *, runner=subprocess.run) -> Path:
    """把 [(audio_path, t_start, duration), ...] 装配成 total_duration 秒
    的连续对白 wav（静音底轨 + 各段 adelay 定位 + amix）。

    空段列表 → 仅静音底轨。ffmpeg 失败抛 RuntimeError。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dur_str = f"{float(total_duration):.3f}"

    if not segments:
        cmd = ["ffmpeg", "-y",
               "-f", "lavfi", "-t", dur_str,
               "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
               "-c:a", "pcm_s16le", str(out_path)]
        result = runner(cmd, capture_output=True)
        if getattr(result, "returncode", 0) != 0:
            err = getattr(result, "stderr", b"")
            msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) \
                else str(err)[-400:]
            raise RuntimeError(f"ffmpeg 静音底轨失败: {msg}")
        if not out_path.exists():
            raise FileNotFoundError(f"ffmpeg 未产出 {out_path}")
        return out_path

    cmd = ["ffmpeg", "-y",
           "-f", "lavfi", "-t", dur_str,
           "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    for seg in segments:
        cmd += ["-i", str(seg.audio_path)]

    parts = []
    for i, seg in enumerate(segments):
        delay_ms = int(round(float(seg.t_start) * 1000))
        parts.append(f"[{i+1}:a]adelay={delay_ms}:all=1[a{i+1}]")
    n = len(segments)
    amix_input = "[0:a]" + "".join(f"[a{i+1}]" for i in range(n))
    amix = f"{amix_input}amix=inputs={n+1}:duration=first:normalize=0[out]"
    filter_complex = ";".join(parts + [amix])

    cmd += ["-filter_complex", filter_complex, "-map", "[out]",
            "-t", dur_str, "-c:a", "pcm_s16le", str(out_path)]

    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) \
            else str(err)[-400:]
        raise RuntimeError(f"ffmpeg 对白装配失败: {msg}")
    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg 未产出 {out_path}")
    return out_path
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_audio_mixer.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/audio_mixer.py tests/test_sound_track_agent/test_audio_mixer.py
git commit -m "feat(soundtrack): audio_mixer 加 assemble_dialogue_track（adelay+amix 装配定时对白轨）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `mixdown.py` — 新编排（align→pump(skip)→dialogue OR Demucs）

**Files:**
- Modify: `sound_track_agent/mixdown.py`
- Test: `tests/test_sound_track_agent/test_mixdown.py`

- [ ] **Step 1: 写失败测试（编排：dialogue 路径跳过 Demucs；空时回退 Demucs；aligned 透传）**

追加到 `tests/test_sound_track_agent/test_mixdown.py`：

```python
from pathlib import Path

from sound_track_agent.mixdown import assemble_and_mix
from sound_track_agent.session import (
    ScoringSession, SegmentScore, BGMCandidate, AccentPoint, DialogueSegment,
)


def _sess_with_bgm(tmp_path, dialogue_segments=None, accents=None):
    bgm = tmp_path / "seg0.mp3"; bgm.write_bytes(b"BGM")
    sess = ScoringSession(
        source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
        global_style="s", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                  candidates=[BGMCandidate(path=str(bgm), seed=1, prompt="t")],
                  chosen_candidate=0)],
        accent_points=accents or [],
        dialogue_segments=dialogue_segments or [])
    return sess


def test_assemble_and_mix_uses_dialogue_track_skips_demucs(tmp_path):
    (tmp_path / "ep.mp4").write_bytes(b"FAKE")
    calls = {"separate": 0, "dialogue": 0, "duck": 0, "replace": 0}

    def fake_separate(*a, **k):
        calls["separate"] += 1
        return tmp_path / "v.wav", tmp_path / "n.wav"

    def fake_assemble_dialogue(segs, total_duration, out_path, **k):
        calls["dialogue"] += 1
        p = Path(out_path); p.write_bytes(b"DIA"); return p

    def fake_assemble_bgm(paths, out, **k):
        Path(out).write_bytes(b"BGM"); return Path(out)

    def fake_duck(v, b, o, **k):
        calls["duck"] += 1; Path(o).write_bytes(b"MX"); return Path(o)

    def fake_replace(vid, aud, out, **k):
        calls["replace"] += 1; Path(out).write_bytes(b"VID"); return Path(out)

    def fake_extract_audio(v, o, **k):
        Path(o).write_bytes(b"A"); return Path(o)

    def fake_duration(v): return 4.0

    sess = _sess_with_bgm(tmp_path, dialogue_segments=[
        DialogueSegment(audio_path="/x/a.flac", t_start=1.0, duration=1.0)])
    out = assemble_and_mix(
        sess, tmp_path / "ep.mp4", tmp_path / "w",
        separate=fake_separate,
        assemble_dialogue=fake_assemble_dialogue,
        assemble_bgm_fn=fake_assemble_bgm,
        extract_audio_fn=fake_extract_audio,
        duck_and_mix_fn=fake_duck,
        replace_video_audio_fn=fake_replace,
        duration_of=fake_duration)
    assert calls["separate"] == 0                  # 不调 Demucs
    assert calls["dialogue"] == 1
    assert calls["duck"] == 1
    assert calls["replace"] == 1
    assert Path(out).exists()


def test_assemble_and_mix_falls_back_to_demucs_when_no_dialogue(tmp_path):
    (tmp_path / "ep.mp4").write_bytes(b"FAKE")
    calls = {"separate": 0, "dialogue": 0}

    def fake_separate(*a, **k):
        calls["separate"] += 1
        return tmp_path / "v.wav", tmp_path / "n.wav"

    def fake_assemble_dialogue(*a, **k):
        calls["dialogue"] += 1
        return tmp_path / "d.wav"

    sess = _sess_with_bgm(tmp_path, dialogue_segments=[])
    assemble_and_mix(
        sess, tmp_path / "ep.mp4", tmp_path / "w",
        separate=fake_separate,
        assemble_dialogue=fake_assemble_dialogue,
        assemble_bgm_fn=lambda p, o, **k: (Path(o).write_bytes(b"B"), Path(o))[1],
        extract_audio_fn=lambda v, o, **k: (Path(o).write_bytes(b"A"), Path(o))[1],
        duck_and_mix_fn=lambda v, b, o, **k: (Path(o).write_bytes(b"M"), Path(o))[1],
        replace_video_audio_fn=lambda v, a, o, **k: (Path(o).write_bytes(b"V"), Path(o))[1],
        duration_of=lambda v: 4.0)
    assert calls["separate"] == 1                  # 走 Demucs 回退
    assert calls["dialogue"] == 0


def test_assemble_and_mix_passes_aligned_indices_to_pump(tmp_path):
    """align 返回的 aligned_set 透传给 apply_pump 的 skip_indices。"""
    (tmp_path / "ep.mp4").write_bytes(b"FAKE")
    captured = {}

    def fake_align(bgm, accents, **k):
        # 模拟：第 0 号 accent 已对齐
        return Path(bgm), frozenset({0})

    def fake_apply_pump(bgm_in, bgm_out, accents, **k):
        captured["skip_indices"] = k.get("skip_indices")
        Path(bgm_out).write_bytes(b"P"); return Path(bgm_out)

    sess = _sess_with_bgm(tmp_path, accents=[AccentPoint(t=1.0, intensity=0.9)],
                          dialogue_segments=[DialogueSegment(
                              audio_path="/x/a.flac", t_start=0.0, duration=1.0)])
    assemble_and_mix(
        sess, tmp_path / "ep.mp4", tmp_path / "w",
        align_beats=fake_align, apply_pump_fn=fake_apply_pump,
        separate=lambda *a, **k: (tmp_path / "v.wav", tmp_path / "n.wav"),
        assemble_dialogue=lambda s, t, o, **k: (Path(o).write_bytes(b"D"), Path(o))[1],
        assemble_bgm_fn=lambda p, o, **k: (Path(o).write_bytes(b"B"), Path(o))[1],
        extract_audio_fn=lambda v, o, **k: (Path(o).write_bytes(b"A"), Path(o))[1],
        duck_and_mix_fn=lambda v, b, o, **k: (Path(o).write_bytes(b"M"), Path(o))[1],
        replace_video_audio_fn=lambda v, a, o, **k: (Path(o).write_bytes(b"V"), Path(o))[1],
        duration_of=lambda v: 4.0)
    assert captured["skip_indices"] == frozenset({0})
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_mixdown.py -q`
Expected: FAIL（`assemble_and_mix` 不接受 `dialogue`/`align_beats`/`assemble_dialogue`/`duration_of` 等关键字）

- [ ] **Step 3: 重写 `assemble_and_mix`**

替换 `sound_track_agent/mixdown.py` 中的 `assemble_and_mix` 函数为：

```python
def assemble_and_mix(sess: ScoringSession, video_path, work_dir, *,
                     crossfade: float = 0.5,
                     target_lufs: float = -14.0,
                     big_threshold: float = 0.7,
                     snap_window: float = 0.6,
                     max_stretch: float = 0.10,
                     separate=separate_vocals,
                     assemble_dialogue=None,
                     align_beats=None,
                     apply_pump_fn=None,
                     assemble_bgm_fn=None,
                     extract_audio_fn=None,
                     duck_and_mix_fn=None,
                     replace_video_audio_fn=None,
                     duration_of=None) -> str:
    """段 BGM 拼接 → 卡点对齐+泵感（跳过对齐爆点） → 装对白轨(或 Demucs) →
    ducking → 写回视频。所有 I/O 可注入（测试用）。"""
    from sound_track_agent.audio_mixer import (
        assemble_dialogue_track as _default_dialogue,
        extract_audio as _default_extract_audio,
        duck_and_mix as _default_duck,
        replace_video_audio as _default_replace,
    )
    from sound_track_agent.bgm_assembler import assemble_bgm as _default_assemble_bgm
    from sound_track_agent.accent_mixer import (
        clip_targets, apply_pump as _default_apply_pump,
    )
    from sound_track_agent.beat_aligner import (
        align_beats_to_accents as _default_align,
    )
    from sound_track_agent.accent_detector import (
        _video_duration_seconds as _default_duration,
    )

    assemble_dialogue = assemble_dialogue or _default_dialogue
    align_beats = align_beats or _default_align
    apply_pump_fn = apply_pump_fn or _default_apply_pump
    assemble_bgm_fn = assemble_bgm_fn or _default_assemble_bgm
    extract_audio_fn = extract_audio_fn or _default_extract_audio
    duck_and_mix_fn = duck_and_mix_fn or _default_duck
    replace_video_audio_fn = replace_video_audio_fn or _default_replace
    duration_of = duration_of or _default_duration

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    seg_bgms = [_chosen_bgm(s) for s in sess.segments]
    accents = list(getattr(sess, "accent_points", []) or [])
    use_accent = bool(getattr(sess, "accent_mix_enabled", True)) and bool(accents)
    gains = [float(getattr(s, "volume", 1.0)) for s in sess.segments]

    if use_accent:
        targets = clip_targets([s.duration for s in sess.segments], accents,
                               big_threshold=big_threshold, window=snap_window,
                               min_clip=crossfade)
        raw_bgm = assemble_bgm_fn(seg_bgms, work_dir / "full_bgm.wav",
                                  crossfade=crossfade, clip_durations=targets,
                                  clip_gains=gains)
        stretched, aligned = align_beats(
            raw_bgm, accents, max_stretch=max_stretch,
            big_threshold=big_threshold,
            out_path=work_dir / "full_bgm_aligned.wav")
        full_bgm = apply_pump_fn(stretched, work_dir / "full_bgm_pumped.wav",
                                 accents,
                                 strength=float(getattr(sess, "pump_strength", 0.6)),
                                 skip_indices=aligned)
    else:
        full_bgm = assemble_bgm_fn(seg_bgms, work_dir / "full_bgm.wav",
                                   crossfade=crossfade, clip_gains=gains)

    if sess.dialogue_segments:
        total_dur = float(duration_of(video_path))
        vocals = assemble_dialogue(
            sess.dialogue_segments, total_duration=total_dur,
            out_path=work_dir / "dialogue_track.wav")
    else:
        src_audio = extract_audio_fn(video_path, work_dir / "src_audio.wav")
        vocals, _rest = separate(src_audio, work_dir / "sep")

    mixed = duck_and_mix_fn(vocals, full_bgm, work_dir / "mixed.wav",
                            target_lufs=target_lufs)

    out_video = work_dir / (Path(video_path).stem + "_scored.mp4")
    replace_video_audio_fn(video_path, mixed, out_video)
    return str(out_video)
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_mixdown.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 5: 跑整套配乐 agent 测试，确认零回归**

Run: `python -m pytest tests/test_sound_track_agent/ -q`
Expected: PASS（全绿）

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/mixdown.py tests/test_sound_track_agent/test_mixdown.py
git commit -m "feat(soundtrack): mixdown 编排 align→pump(skip)→dialogue OR Demucs 新流水线

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `facade.py` — `dialogue_segments` 入参 + 预览路径同步

**Files:**
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_facade.py`：

```python
def test_prepare_session_accepts_and_persists_dialogue_segments(tmp_path):
    from sound_track_agent.facade import prepare_session
    from sound_track_agent.segment_planner import Shot
    from sound_track_agent.session import DialogueSegment
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"f")
    segs = [DialogueSegment(audio_path="/x/a.flac", t_start=0.0, duration=1.0),
            DialogueSegment(audio_path="/x/b.flac", t_start=2.0, duration=1.0)]
    sess = prepare_session(mp4, "末日", tmp_path / "w",
                           dialogue_segments=segs,
                           detect=lambda p: [Shot(0, 0.0, 3.0)])
    assert len(sess.dialogue_segments) == 2
    assert sess.dialogue_segments[1].audio_path == "/x/b.flac"


def test_advance_overrides_dialogue_segments_when_provided(tmp_path):
    """advance 传 dialogue_segments 非空时覆盖 session；空/None 不动。"""
    from sound_track_agent.facade import advance
    from sound_track_agent.pipeline import Stages
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, EmotionTag, BGMCandidate, DialogueSegment,
    )
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="s", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)],
        dialogue_segments=[DialogueSegment(
            audio_path="/old.flac", t_start=0.0, duration=1.0)])
    fake = Stages(
        tag_emotion=lambda seg, s: EmotionTag(labels=["x"]),
        compose_prompt=lambda seg, s: "p",
        generate=lambda seg, s: [BGMCandidate(path="/b.wav", seed=1, prompt="t")],
        align=lambda s: None, mix=lambda s: "/out.mp4")
    new_segs = [DialogueSegment(audio_path="/new.flac", t_start=0.5, duration=2.0)]
    advance(sess, tmp_path / "w", cfg=object(), workflow_id="wf",
            stop_after="mix", stages=fake, dialogue_segments=new_segs)
    assert sess.dialogue_segments[0].audio_path == "/new.flac"


def test_build_accent_preview_invokes_align_with_pump_skip(tmp_path, monkeypatch):
    """预览路径与 mix 路径共用 align+pump 流程：monkeypatch align 返回固定
    aligned set，断言 align 被调用且预览 wav 正常产出。"""
    import numpy as np, soundfile as sf
    from pathlib import Path
    from sound_track_agent import facade
    import sound_track_agent.beat_aligner as ba
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate, AccentPoint)

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550)
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="g", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=0)],
        accent_points=[AccentPoint(t=0.5, intensity=0.9)])

    align_called = {"flag": False}

    def fake_align(bgm, accents, *, max_stretch, big_threshold, out_path):
        align_called["flag"] = True
        return Path(bgm), frozenset({0})

    monkeypatch.setattr(ba, "align_beats_to_accents", fake_align)
    out = facade.build_accent_preview(sess, tmp_path / "w", crossfade=0.1)
    assert Path(out).exists() and Path(out).stat().st_size > 0
    assert align_called["flag"] is True
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: FAIL（`prepare_session` 不接受 `dialogue_segments`、`advance` 不接受同参）

- [ ] **Step 3: 改 `prepare_session` 接收 `dialogue_segments`**

打开 `sound_track_agent/facade.py`。把 `prepare_session` 替换为：

```python
def prepare_session(mp4, style: str, work_dir, *,
                    dialogue_segments=None,
                    detect: Callable = detect_shots) -> ScoringSession:
    """MP4 → 切镜头 → 段落聚合 → 新建 ScoringSession。

    dialogue_segments 非 None 时落入 session.dialogue_segments（与 accent_points 同样持久化）。
    """
    mp4 = Path(mp4)
    shots = detect(mp4)
    segments = plan_segments(shots)
    return ScoringSession(
        source_mp4=str(mp4),
        source_hash=hash_file(mp4),
        global_style=style,
        frame_rate=_read_fps(mp4),
        segments=segments,
        dialogue_segments=list(dialogue_segments or []),
    )
```

- [ ] **Step 4: 改 `advance` 接收 `dialogue_segments` 覆盖**

打开 `sound_track_agent/facade.py`，把 `advance` 函数签名加 `dialogue_segments` 入参，并在 `work_dir.mkdir(...)` 之后插入覆盖逻辑：

```python
def advance(session: ScoringSession, work_dir, *, cfg, workflow_id: str,
            seeds_count: int = 2, stop_after: str = "mix",
            on_progress: Optional[Callable[[str], None]] = None,
            stages: Optional[Stages] = None,
            dialogue_segments=None) -> ScoringSession:
    """从 session 当前状态推进到 stop_after（可重复调用=续跑）。

    stages 可注入（测试用 fake）；dialogue_segments 非空时覆盖 session 字段。
    """
    if stop_after not in STAGE_ORDER:
        raise ValueError(f"未知 stop_after: {stop_after}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if dialogue_segments:
        session.dialogue_segments = list(dialogue_segments)
    real = stages or _build_real_stages(
        cfg, workflow_id, work_dir, session.global_style,
        seeds_count, session.source_mp4)
    real = _wrap_progress(real, on_progress)
    _pipeline_run(session, real,
                  session_path=work_dir / "session.json",
                  stop_after=stop_after)
    return session
```

- [ ] **Step 5: 改 `build_accent_preview` 同源走 align+pump**

打开 `sound_track_agent/facade.py`，把 `build_accent_preview` 的 accent 分支替换为：

```python
    if bool(getattr(session, "accent_mix_enabled", True)) and accents:
        targets = clip_targets([s.duration for s in session.segments], accents,
                               big_threshold=big_threshold, window=snap_window,
                               min_clip=crossfade)
        raw = assemble_bgm(seg_bgms, work_dir / "_preview_raw.wav",
                           crossfade=crossfade, clip_durations=targets,
                           clip_gains=gains)
        from sound_track_agent.beat_aligner import align_beats_to_accents
        stretched, aligned = align_beats_to_accents(
            raw, accents,
            max_stretch=max_stretch,
            big_threshold=big_threshold,
            out_path=work_dir / "_preview_aligned.wav")
        out = apply_pump(stretched, out, accents,
                         strength=float(getattr(session, "pump_strength", 0.6)),
                         skip_indices=aligned)
    else:
        out = assemble_bgm(seg_bgms, out, crossfade=crossfade, clip_gains=gains)
    return str(out)
```

并把 `build_accent_preview` 的签名加上 `max_stretch` 入参（与 `crossfade`/`big_threshold`/`snap_window` 同级，默认 `0.10`）：

```python
def build_accent_preview(session: ScoringSession, work_dir, *,
                         crossfade: float = 0.5,
                         big_threshold: float = 0.7,
                         snap_window: float = 0.6,
                         max_stretch: float = 0.10) -> str:
```

- [ ] **Step 6: 把 `max_stretch` 透传进 `_build_real_stages` 的 mix_fn**

在 `_build_real_stages` 的 `partial(assemble_and_mix, ...)` 调用里追加 `max_stretch` 配置项（与 `big_threshold`/`snap_window` 同级，从 cfg 读取，默认 0.10）：

```python
        mix_fn=partial(assemble_and_mix, video_path=video_path,
                       work_dir=work_dir,
                       big_threshold=float(getattr(cfg, "accent_big_threshold", 0.7)),
                       snap_window=float(getattr(cfg, "accent_snap_window", 0.6)),
                       max_stretch=float(getattr(cfg, "accent_max_stretch", 0.10))),
```

- [ ] **Step 7: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 8: 跑整套配乐 agent 测试 + UI 冒烟，零回归**

Run: `python -m pytest tests/test_sound_track_agent tests/test_ui/test_segment_review_smoke.py tests/test_ui/test_accent_editor_smoke.py -q`
Expected: PASS（全绿）

- [ ] **Step 9: 提交**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(soundtrack): facade prepare_session/advance 接收 dialogue_segments；build_accent_preview 同源走 align+pump

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 收尾验证（全部任务完成后）

- [ ] **回归全测**

Run: `python -m pytest tests/test_sound_track_agent/ -q`
Expected: PASS

- [ ] **对照验收标准（spec §11）逐条确认**

1. 大爆点 + 节拍存在 → `aligned_indices` 非空 → `test_align_writes_stretched_with_injected_fakes` + `_plan_alignment` 多个边界用例。
2. `apply_pump(skip_indices=aligned)` 在跳过位置零下压 → `test_build_pump_envelope_skip_indices_no_dip`。
3. 提供 `dialogue_segments` → Demucs `separate` 调用计数 = 0 → `test_assemble_and_mix_uses_dialogue_track_skips_demucs`。
4. 缺 `dialogue_segments` → Demucs 路径正常 → `test_assemble_and_mix_falls_back_to_demucs_when_no_dialogue`。
5. session 往返 `dialogue_segments`（含旧 json 默认 []）→ `test_session_dialogue_segments_*`。
6. 预览与正片共用 align+pump → `test_build_accent_preview_invokes_align_with_pump_skip` + `test_assemble_and_mix_passes_aligned_indices_to_pump`。
