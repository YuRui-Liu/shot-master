# 配乐生成阶段优化（并行 + 缓存 + 候选打分）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `sound_track_agent` 生成阶段加上 (段×seed) 任务级并发、内容寻址缓存、候选自动打分，并让 `regenerate_segment` 用新种子产出真正不同的候选。

**Architecture:** 在 `pipeline.Stages` 上加一个**可选** `generate_all` 钩子；真实链路注入一个批量生成器（并发提交/轮询/下载 + 查缓存 + 打分 + 回填），缺省回退到现有逐段 `generate`（零回归）。新增 3 个聚焦模块：`bgm_cache`（纯）、`scorer`（纯 + 薄读音频）、`batch_generator`（编排 + 并发）。

**Tech Stack:** Python 3.10+、`concurrent.futures.ThreadPoolExecutor`、`numpy`/`soundfile`/`librosa`（打分）、`hashlib`（缓存键）、`pytest`。复用 `drama_shot_master.providers.runninghub.RunningHubClient`（注入，不在模块顶层 import 宿主）。

参考 spec：`docs/superpowers/specs/2026-05-28-soundtrack-gen-parallel-cache-scoring-design.md`

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `sound_track_agent/session.py` | 数据结构：`BGMCandidate.score/subscores`、`SegmentScore.next_seed` | 改 |
| `sound_track_agent/bgm_cache.py` | 内容寻址缓存：`cache_key`/`cache_path`/`lookup`/`store` | 建 |
| `sound_track_agent/scorer.py` | 候选打分：`health/headroom/beat` → `CandidateScore`、`score_candidate`、`pick_best` | 建 |
| `sound_track_agent/batch_generator.py` | 批量并发生成编排：`generate_all`、`generate_one` | 建 |
| `sound_track_agent/pipeline.py` | `Stages.generate_all` 可选字段 + `run()` generate 阶段钩子 | 改 |
| `sound_track_agent/stages_factory.py` | 真实链路装配 `generate_all` | 改 |
| `sound_track_agent/facade.py` | 注入并发/打分配置；`regenerate_segment` 走 `generate_one` | 改 |
| `tests/test_sound_track_agent/test_*.py` | 各模块单测 | 建/改 |

实现顺序按依赖：数据结构 → 纯模块（cache/scorer）→ pipeline 钩子 → 批量生成器 → 装配（stages_factory/facade）。

---

## Task 1: session.py 数据结构扩展

**Files:**
- Modify: `sound_track_agent/session.py`
- Test: `tests/test_sound_track_agent/test_session.py`

- [ ] **Step 1: 写失败测试（新字段往返 + 旧 json 兼容）**

追加到 `tests/test_sound_track_agent/test_session.py`：

```python
from sound_track_agent.session import (
    ScoringSession, SegmentScore, BGMCandidate,
)


def test_bgm_candidate_score_fields_roundtrip():
    c = BGMCandidate(path="a.mp3", seed=3, prompt="p",
                     score=0.8, subscores={"health": 0.9, "headroom": 0.7, "beat": 0.5})
    d = c.to_dict()
    assert d["score"] == 0.8 and d["subscores"]["health"] == 0.9
    c2 = BGMCandidate(**d)
    assert c2.score == 0.8 and c2.subscores == {"health": 0.9, "headroom": 0.7, "beat": 0.5}


def test_bgm_candidate_defaults_when_missing():
    c = BGMCandidate(path="a.mp3", seed=1, prompt="p")
    assert c.score is None and c.subscores == {}


def test_segment_next_seed_roundtrip_and_default():
    seg = SegmentScore(index=0, t_start=0.0, t_end=2.0, next_seed=5)
    assert seg.to_dict()["next_seed"] == 5
    # 旧 json 缺字段 → 默认 1
    d = seg.to_dict(); del d["next_seed"]
    assert SegmentScore.from_dict(d).next_seed == 1


def test_session_roundtrip_preserves_new_fields(tmp_path):
    sess = ScoringSession(source_mp4="x.mp4", source_hash="h",
                          global_style="s", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                                                 next_seed=7,
                                                 candidates=[BGMCandidate(
                                                     path="b.mp3", seed=7, prompt="p",
                                                     score=0.6, subscores={"health": 1.0})])])
    p = tmp_path / "session.json"
    sess.save(p)
    back = ScoringSession.load(p)
    assert back.segments[0].next_seed == 7
    assert back.segments[0].candidates[0].score == 0.6
    assert back.segments[0].candidates[0].subscores == {"health": 1.0}
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q`
Expected: FAIL（`BGMCandidate` 无 `score` 参数 / `SegmentScore` 无 `next_seed`）

- [ ] **Step 3: 改 `BGMCandidate`**

`sound_track_agent/session.py` 中替换 `BGMCandidate` 定义：

```python
@dataclass
class BGMCandidate:
    path: str
    seed: int
    prompt: str
    score: float | None = None
    subscores: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"path": self.path, "seed": self.seed, "prompt": self.prompt,
                "score": self.score, "subscores": dict(self.subscores)}
```

- [ ] **Step 4: 改 `SegmentScore`（加 `next_seed` 字段 + 序列化）**

在 `SegmentScore` 的 `volume: float = 1.0` 之后加字段：

```python
    next_seed: int = 1
```

在 `SegmentScore.to_dict` 返回 dict 里加一项（与 `"volume"` 同级）：

```python
            "next_seed": self.next_seed,
```

在 `SegmentScore.from_dict` 的构造里加一行（与 `volume=` 同级）：

```python
            next_seed=int(d.get("next_seed", 1)),
```

> 说明：`ScoringSession.from_dict` 里 `candidates=[BGMCandidate(**c) ...]` 无需改——新字段都有默认，旧 json 缺 `score/subscores` 时走默认，新 json 含这两键时 `**c` 正常传入。

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/session.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(soundtrack): BGMCandidate 加 score/subscores、SegmentScore 加 next_seed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: bgm_cache.py 内容寻址缓存

**Files:**
- Create: `sound_track_agent/bgm_cache.py`
- Test: `tests/test_sound_track_agent/test_bgm_cache.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_sound_track_agent/test_bgm_cache.py`：

```python
from sound_track_agent import bgm_cache


def test_cache_key_deterministic_and_seed_sensitive():
    k1 = bgm_cache.cache_key("wf", "tags", 120, 15.0, 1)
    k2 = bgm_cache.cache_key("wf", "tags", 120, 15.0, 1)
    k3 = bgm_cache.cache_key("wf", "tags", 120, 15.0, 2)
    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 16


def test_cache_key_duration_precision_stable():
    # 15.0 与 15.0004 在 .3f 下不同；15.0 与 15.0001 相同
    assert bgm_cache.cache_key("wf", "t", 120, 15.0, 1) == \
           bgm_cache.cache_key("wf", "t", 120, 15.0001, 1)


def test_lookup_miss_then_store_then_hit(tmp_path):
    cache_dir = tmp_path / "cache"
    key = bgm_cache.cache_key("wf", "t", 120, 15.0, 1)
    assert bgm_cache.lookup(cache_dir, key) is None
    src = tmp_path / "dl.mp3"
    src.write_bytes(b"AUDIO")
    dest = bgm_cache.store(cache_dir, key, src)
    assert dest.exists() and dest.read_bytes() == b"AUDIO"
    assert not src.exists()                      # store 是移动语义
    assert bgm_cache.lookup(cache_dir, key) == dest
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_bgm_cache.py -q`
Expected: FAIL（`No module named ... bgm_cache`）

- [ ] **Step 3: 实现 `bgm_cache.py`**

新建 `sound_track_agent/bgm_cache.py`：

```python
"""BGM 生成结果缓存：内容寻址，按 work_dir 作用域。纯逻辑 + 薄文件 IO，可单测。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def cache_key(workflow_id: str, tags: str, bpm: int,
              duration: float, seed: int) -> str:
    """对决定输出的输入算 sha256 前 16 hex。duration 定精度避免浮点 repr 漂移。"""
    raw = f"{workflow_id}|{tags}|{int(bpm)}|{float(duration):.3f}|{int(seed)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_path(cache_dir, key: str) -> Path:
    return Path(cache_dir) / f"{key}.mp3"


def lookup(cache_dir, key: str):
    """命中返回缓存路径，未命中返回 None。"""
    p = cache_path(cache_dir, key)
    return p if p.exists() else None


def store(cache_dir, key: str, src) -> Path:
    """把 src 移入缓存（同盘 rename，原子），返回缓存路径。"""
    dest = cache_path(cache_dir, key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Path(src).replace(dest)
    return dest
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_bgm_cache.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/bgm_cache.py tests/test_sound_track_agent/test_bgm_cache.py
git commit -m "feat(soundtrack): 新增 bgm_cache 内容寻址缓存

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: scorer.py 候选打分

**Files:**
- Create: `sound_track_agent/scorer.py`
- Test: `tests/test_sound_track_agent/test_scorer.py`

- [ ] **Step 1: 写失败测试（纯函数 + pick_best）**

新建 `tests/test_sound_track_agent/test_scorer.py`：

```python
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
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_scorer.py -q`
Expected: FAIL（`No module named ... scorer`）

- [ ] **Step 3: 实现 `scorer.py`**

新建 `sound_track_agent/scorer.py`：

```python
"""候选 BGM 打分：health / headroom / beat → 总分。核心数学纯函数，可单测。

score_candidate 薄读音频（soundfile）；beat 用 librosa（缺失则降级中性）。
读取失败由调用方降级为 None。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_WEIGHTS = {"health": 0.5, "headroom": 0.3, "beat": 0.2}


@dataclass
class CandidateScore:
    total: float
    health: float
    headroom: float
    beat: float


def health_score(samples: np.ndarray, sr: int, expected_dur: float) -> float:
    """[0,1]。惩罚削波 / 近静音 / 过短 / NaN。samples 单声道 float[-1,1]。"""
    if samples.size == 0 or not np.all(np.isfinite(samples)):
        return 0.0
    clip_frac = float(np.mean(np.abs(samples) >= 0.999))
    rms = float(np.sqrt(np.mean(samples ** 2)))
    dur = samples.size / sr if sr else 0.0
    score = 1.0
    score -= min(1.0, clip_frac * 10.0)                 # 10% 削波即清零该项
    if rms < 0.01:                                      # 近静音
        score -= 0.8
    if expected_dur > 0 and dur < expected_dur * 0.5:   # 远短于期望
        score -= 0.5
    return max(0.0, min(1.0, score))


def headroom_score(samples: np.ndarray, sr: int) -> float:
    """[0,1]。语音频段(300-3400Hz)能量占比越低分越高（给人声让路）。"""
    if samples.size == 0 or sr <= 0:
        return 0.5
    spec = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, 1.0 / sr)
    total = float(np.sum(spec ** 2)) + 1e-9
    band = (freqs >= 300) & (freqs <= 3400)
    ratio = float(np.sum(spec[band] ** 2)) / total
    return max(0.0, min(1.0, 1.0 - ratio))


def beat_score(path) -> float:
    """[0,1]。librosa onset 自相关清晰度；不可用/异常 → 中性 0.5。"""
    try:
        import librosa
        y, sr = librosa.load(str(path), sr=None, mono=True)
        if y is None or len(y) == 0:
            return 0.5
        onset = librosa.onset.onset_strength(y=y, sr=sr)
        if onset.size == 0:
            return 0.5
        ac = librosa.autocorrelate(onset)
        if ac.size < 2 or ac[0] <= 0:
            return 0.5
        return max(0.0, min(1.0, float(np.max(ac[1:]) / ac[0])))
    except Exception:
        return 0.5


def score_candidate(path, *, expected_dur: float = 0.0,
                    weights: dict | None = None) -> CandidateScore:
    """读音频 → 三项 → 加权总分。读失败抛异常（调用方降级为 None）。"""
    import soundfile as sf
    weights = weights or DEFAULT_WEIGHTS
    data, sr = sf.read(str(path), always_2d=True)
    mono = data.mean(axis=1).astype("float64")
    h = health_score(mono, sr, expected_dur)
    hr = headroom_score(mono, sr)
    b = beat_score(path)
    total = (weights["health"] * h + weights["headroom"] * hr
             + weights["beat"] * b)
    return CandidateScore(total=total, health=h, headroom=hr, beat=b)


def pick_best(candidates) -> int:
    """返回 score 最高候选的下标；全 None → 0。candidates 为 BGMCandidate 列表。"""
    best, best_i, seen = -1.0, 0, False
    for i, c in enumerate(candidates):
        s = getattr(c, "score", None)
        if s is not None:
            seen = True
            if s > best:
                best, best_i = s, i
    return best_i if seen else 0
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_scorer.py -q`
Expected: PASS

> 注：测试只用 `health_score`/`headroom_score`/`pick_best`（纯 numpy），不触发 `score_candidate`/`beat_score`（需 soundfile/librosa），故 CI 无音频依赖也能跑。

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/scorer.py tests/test_sound_track_agent/test_scorer.py
git commit -m "feat(soundtrack): 新增 scorer 候选打分（health/headroom/beat）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: pipeline.py 加 `generate_all` 钩子

**Files:**
- Modify: `sound_track_agent/pipeline.py`
- Test: `tests/test_sound_track_agent/test_pipeline.py`

- [ ] **Step 1: 写失败测试（钩子路径 + 回退路径 + 0 候选留 prompted）**

追加到 `tests/test_sound_track_agent/test_pipeline.py`：

```python
from sound_track_agent.pipeline import Stages, run as run_pipeline
from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate,
)


def _prompted_session(n=2):
    segs = [SegmentScore(index=i, t_start=float(i), t_end=float(i) + 1.0,
                         status="prompted") for i in range(n)]
    return ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=segs)


def _base_stage_fns():
    return dict(
        tag_emotion=lambda seg, s: EmotionTag(),
        compose_prompt=lambda seg, s: "p",
        generate=lambda seg, s: [BGMCandidate(path="g.mp3", seed=1, prompt="p")],
        align=lambda s: None,
        mix=lambda s: "out.mp4",
    )


def test_generate_all_hook_used_when_present():
    sess = _prompted_session(2)
    calls = {"all": 0, "per_seg": 0}

    def gen_all(s):
        calls["all"] += 1
        for seg in s.segments:
            seg.candidates = [BGMCandidate(path=f"seg{seg.index}.mp3", seed=seg.next_seed,
                                           prompt="p", score=0.5)]
            seg.chosen_candidate = 0

    def per_seg(seg, s):
        calls["per_seg"] += 1
        return []

    fns = _base_stage_fns(); fns["generate"] = per_seg
    stages = Stages(generate_all=gen_all, **fns)
    run_pipeline(sess, stages, stop_after="generate")
    assert calls["all"] == 1 and calls["per_seg"] == 0
    assert all(seg.status == "generated" for seg in sess.segments)
    assert all(seg.candidates for seg in sess.segments)


def test_generate_all_zero_candidates_stays_prompted():
    sess = _prompted_session(2)

    def gen_all(s):
        s.segments[0].candidates = [BGMCandidate(path="a.mp3", seed=1, prompt="p")]
        # 段1 全失败：不填候选
    stages = Stages(generate_all=gen_all, **_base_stage_fns())
    run_pipeline(sess, stages, stop_after="generate")
    assert sess.segments[0].status == "generated"
    assert sess.segments[1].status == "prompted"     # 0 候选留待续跑


def test_fallback_per_segment_when_no_hook():
    sess = _prompted_session(2)
    stages = Stages(**_base_stage_fns())             # generate_all 缺省 None
    run_pipeline(sess, stages, stop_after="generate")
    assert all(seg.status == "generated" for seg in sess.segments)
    assert all(seg.candidates for seg in sess.segments)
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_pipeline.py -q`
Expected: FAIL（`Stages` 无 `generate_all` 关键字）

- [ ] **Step 3: 给 `Stages` 加可选字段**

`sound_track_agent/pipeline.py` 顶部 import 加 `Optional`：

```python
from typing import Callable, Optional
```

在 `Stages` dataclass 末尾（`mix` 之后）加字段：

```python
    generate_all: Optional[Callable[[ScoringSession], None]] = None
```

- [ ] **Step 4: 改 `run()` 的 generate 阶段**

把 `run()` 里 generate 阶段那段（`if limit >= STAGE_ORDER.index("generate"):` 整块）替换为：

```python
    if limit >= STAGE_ORDER.index("generate"):
        prompted = [s for s in sess.segments if s.status == "prompted"]
        if stages.generate_all is not None:
            stages.generate_all(sess)
            for seg in prompted:
                if seg.candidates:                 # 0 候选段留 prompted 待续跑
                    seg.status = "generated"
        else:
            for seg in sess.segments:
                if seg.status == "prompted":
                    seg.candidates = stages.generate(seg, sess)
                    seg.status = "generated"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("generate"):
            return None
```

- [ ] **Step 5: 运行，确认通过（含原有用例）**

Run: `python -m pytest tests/test_sound_track_agent/test_pipeline.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/pipeline.py tests/test_sound_track_agent/test_pipeline.py
git commit -m "feat(soundtrack): pipeline 加可选 generate_all 钩子（缺省回退逐段）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: batch_generator.py 批量并发生成

**Files:**
- Create: `sound_track_agent/batch_generator.py`
- Test: `tests/test_sound_track_agent/test_batch_generator.py`

- [ ] **Step 1: 写失败测试（注入 fake client，覆盖缓存命中/并发上限/失败隔离/游标/打分/全失败）**

新建 `tests/test_sound_track_agent/test_batch_generator.py`：

```python
import threading

from sound_track_agent import batch_generator, bgm_cache
from sound_track_agent.scorer import CandidateScore
from sound_track_agent.session import ScoringSession, SegmentScore


class FakeClient:
    """记录调用 + 可指定失败 seed + 跟踪并发峰值。"""

    def __init__(self, fail_seeds=()):
        self.fail_seeds = set(fail_seeds)
        self.created = []
        self._lock = threading.Lock()
        self._live = 0
        self.peak = 0
        # task_id -> seed（从 node_info_list 的 NODE_SEED 取）
        self._task_seed = {}

    def create_task(self, *, workflow_id, node_info_list=None):
        seed = next(n["fieldValue"] for n in node_info_list if n["nodeId"] == "109")
        with self._lock:
            self.created.append(seed)
            tid = f"t{len(self.created)}"
            self._task_seed[tid] = seed
            self._live += 1
            self.peak = max(self.peak, self._live)
        return tid

    def query_task(self, task_id):
        seed = self._task_seed[task_id]
        if seed in self.fail_seeds:
            return {"status": "FAILED", "errorMessage": "boom"}
        return {"status": "SUCCESS", "results": [{"url": f"http://x/{seed}.mp3"}]}

    def download_file(self, url, dest):
        from pathlib import Path
        dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"AUDIO-" + url.encode())
        # 模拟下载占时，便于并发峰值观测
        import time
        time.sleep(0.02)
        with self._lock:
            self._live -= 1
        return dest


def _compose(seg):
    # 按段区分 tags，避免不同段（同时长）撞同一 cache_key 而误命中
    return (f"tags{seg.index}", 120, seg.duration)


def _fake_score(path, expected_dur=0.0):
    # 缓存文件名是 hash，不含 seed，故返回常量分即可（pick_best 的 argmax 由 scorer 单测覆盖）
    return CandidateScore(total=0.5, health=1.0, headroom=0.5, beat=0.5)


def _session(n=2):
    segs = [SegmentScore(index=i, t_start=float(i), t_end=float(i) + 1.0,
                         status="prompted") for i in range(n)]
    return ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=segs)


def test_generate_all_fills_candidates_scores_chosen_and_advances_seed(tmp_path):
    sess = _session(2)
    client = FakeClient()
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    for seg in sess.segments:
        assert len(seg.candidates) == 2
        assert all(c.score is not None for c in seg.candidates)
        assert seg.chosen_candidate is not None
        assert seg.next_seed == 3                       # 1 -> +2
    assert sorted(client.created) == [1, 1, 2, 2]       # 两段各 seed 1,2


def test_generate_all_uses_cache_skips_create(tmp_path):
    sess = _session(1)
    cache_dir = tmp_path / "cache"
    # 预置段0 seed1、seed2 的缓存
    for seed in (1, 2):
        key = bgm_cache.cache_key("wf", "tags0", 120, sess.segments[0].duration, seed)
        src = tmp_path / f"pre{seed}.mp3"; src.write_bytes(b"CACHED")
        bgm_cache.store(cache_dir, key, src)
    client = FakeClient()
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=cache_dir,
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    assert client.created == []                          # 全命中，零提交
    assert len(sess.segments[0].candidates) == 2


def test_concurrency_cap_respected(tmp_path):
    sess = _session(3)                                   # 3 段 × 2 seed = 6 job
    client = FakeClient()
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=2, poll_interval=0, sleep=lambda *_: None)
    assert client.peak <= 2


def test_failure_isolation_keeps_other_candidates(tmp_path):
    sess = _session(1)
    client = FakeClient(fail_seeds={1})                  # seed1 失败，seed2 成功
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    seg = sess.segments[0]
    assert len(seg.candidates) == 1 and seg.candidates[0].seed == 2
    assert seg.next_seed == 3                            # 仍推进


def test_total_failure_leaves_no_candidates(tmp_path):
    sess = _session(1)
    client = FakeClient(fail_seeds={1, 2})
    batch_generator.generate_all(
        sess, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    assert sess.segments[0].candidates == []
    assert sess.segments[0].next_seed == 3


def test_generate_one_replaces_with_fresh_seeds(tmp_path):
    sess = _session(1)
    seg = sess.segments[0]
    seg.next_seed = 5
    client = FakeClient()
    batch_generator.generate_one(
        sess, 0, client=client, workflow_id="wf", cache_dir=tmp_path / "cache",
        compose=_compose, score_fn=_fake_score, seeds_count=2,
        max_concurrency=4, poll_interval=0, sleep=lambda *_: None)
    assert sorted(client.created) == [5, 6]              # 用新种子
    assert seg.next_seed == 7
    assert seg.status == "generated"
    assert len(seg.candidates) == 2 and seg.chosen_candidate is not None
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_batch_generator.py -q`
Expected: FAIL（`No module named ... batch_generator`）

- [ ] **Step 3: 实现 `batch_generator.py`**

新建 `sound_track_agent/batch_generator.py`：

```python
"""批量并发生成 BGM：收集 (段,seed) 任务 → 查缓存 → 并发提交/轮询/下载 →
写缓存 → 打分 → 回填候选/chosen → 推进 next_seed。

供 pipeline.Stages.generate_all 注入。纯编排，外部依赖（client/compose/
score_fn/sleep）全部注入，便于单测。失败按 job 隔离、不抛（保住部分进度）。
"""
from __future__ import annotations

import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent import bgm_cache, music_generator, scorer
from sound_track_agent.session import ScoringSession, BGMCandidate


@dataclass
class _Job:
    seg_index: int
    seed: int
    tags: str
    bpm: int
    duration: float


def _run_job(job: _Job, *, client, workflow_id, cache_dir,
             timeout, poll_interval, sleep):
    """单 job 完整生命周期：查缓存→(miss)create/poll/download/store。返回 (job, Path)。"""
    key = bgm_cache.cache_key(workflow_id, job.tags, job.bpm, job.duration, job.seed)
    hit = bgm_cache.lookup(cache_dir, key)
    if hit is not None:
        return job, hit
    task_id = client.create_task(
        workflow_id=workflow_id,
        node_info_list=music_generator._node_info(
            job.tags, job.bpm, job.duration, job.seed))
    url = music_generator._wait_success(
        client, task_id, timeout=timeout, poll_interval=poll_interval, sleep=sleep)
    tmp = Path(cache_dir) / f"_dl_{key}.mp3"
    client.download_file(url, tmp)
    return job, bgm_cache.store(cache_dir, key, tmp)


def _execute(jobs, *, client, workflow_id, cache_dir, max_concurrency,
             timeout, poll_interval, sleep, on_progress):
    """并发跑 jobs，返回成功的 (job, Path) 列表；失败经 on_progress 告警并跳过。"""
    out, total, done = [], len(jobs), 0
    if not jobs:
        return out
    with ThreadPoolExecutor(max_workers=max(1, int(max_concurrency))) as ex:
        futs = {ex.submit(_run_job, j, client=client, workflow_id=workflow_id,
                          cache_dir=cache_dir, timeout=timeout,
                          poll_interval=poll_interval, sleep=sleep): j for j in jobs}
        for fut in as_completed(futs):
            j = futs[fut]
            done += 1
            try:
                out.append(fut.result())
            except Exception as e:                     # 失败隔离
                if on_progress:
                    on_progress(f"段{j.seg_index} seed{j.seed} 生成失败：{e}")
            if on_progress:
                on_progress(f"生成 BGM ({done}/{total})…")
    return out


def _score_and_pick(seg, cands, score_fn) -> None:
    """对候选打分写 score/subscores，pick_best 写 seg.chosen_candidate。"""
    for c in cands:
        try:
            cs = score_fn(c.path, expected_dur=seg.duration)
        except Exception:
            cs = None
        if cs is not None:
            c.score = cs.total
            c.subscores = {"health": cs.health, "headroom": cs.headroom,
                           "beat": cs.beat}
        else:
            c.score = None
    seg.chosen_candidate = scorer.pick_best(cands)


def _jobs_for_segment(seg, compose, seeds_count) -> list[_Job]:
    tags, bpm, dur = compose(seg)
    return [_Job(seg.index, seg.next_seed + k, tags, bpm, dur)
            for k in range(seeds_count)]


def generate_all(session: ScoringSession, *, client, workflow_id: str, cache_dir,
                 compose: Callable, score_fn: Callable,
                 seeds_count: int = 2, max_concurrency: int = 3,
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep: Optional[Callable] = None,
                 on_progress: Optional[Callable[[str], None]] = None) -> None:
    """处理所有 prompted 段：并发生成→缓存→打分→回填→推进 next_seed。不抛。"""
    sleep = sleep or _time.sleep
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    segs = [s for s in session.segments if s.status == "prompted"]
    if not segs:
        return
    jobs = [j for seg in segs for j in _jobs_for_segment(seg, compose, seeds_count)]
    successes = _execute(jobs, client=client, workflow_id=workflow_id,
                         cache_dir=cache_dir, max_concurrency=max_concurrency,
                         timeout=timeout, poll_interval=poll_interval,
                         sleep=sleep, on_progress=on_progress)
    by_index = {s.index: [] for s in segs}
    for job, path in successes:
        by_index[job.seg_index].append(
            BGMCandidate(path=str(path), seed=job.seed, prompt=job.tags))
    for seg in segs:
        seg.next_seed += seeds_count                   # 无论成败都推进
        cands = sorted(by_index[seg.index], key=lambda c: c.seed)
        if not cands:
            continue                                   # 0 候选留 prompted
        _score_and_pick(seg, cands, score_fn)
        seg.candidates = cands


def generate_one(session: ScoringSession, seg_index: int, *, client,
                 workflow_id: str, cache_dir, compose: Callable, score_fn: Callable,
                 seeds_count: int = 2, max_concurrency: int = 3,
                 timeout: float = 600.0, poll_interval: float = 5.0,
                 sleep: Optional[Callable] = None,
                 on_progress: Optional[Callable[[str], None]] = None) -> ScoringSession:
    """单段重生成：新种子、清旧候选、生成、打分、pick、推进 next_seed。"""
    sleep = sleep or _time.sleep
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    seg = session.segments[seg_index]
    seg.candidates = []
    seg.chosen_candidate = None
    jobs = _jobs_for_segment(seg, compose, seeds_count)
    successes = _execute(jobs, client=client, workflow_id=workflow_id,
                         cache_dir=cache_dir, max_concurrency=max_concurrency,
                         timeout=timeout, poll_interval=poll_interval,
                         sleep=sleep, on_progress=on_progress)
    seg.next_seed += seeds_count
    cands = sorted((BGMCandidate(path=str(p), seed=j.seed, prompt=j.tags)
                    for j, p in successes), key=lambda c: c.seed)
    if cands:
        _score_and_pick(seg, cands, score_fn)
        seg.candidates = cands
        seg.status = "generated"
    return session
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_batch_generator.py -q`
Expected: PASS（6 个用例全绿）

> 若 `test_concurrency_cap_respected` 偶发因调度过快导致 peak 观测不到 2，确认 `FakeClient.download_file` 中的 `time.sleep(0.02)` 仍在——它制造重叠窗口。该断言是 `<= 2`，不依赖一定达到 2。

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/batch_generator.py tests/test_sound_track_agent/test_batch_generator.py
git commit -m "feat(soundtrack): 新增 batch_generator 批量并发生成（缓存+打分+失败隔离）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: stages_factory.py 装配 `generate_all`

**Files:**
- Modify: `sound_track_agent/stages_factory.py`
- Test: `tests/test_sound_track_agent/test_stages_factory.py`

- [ ] **Step 1: 写失败测试（build_stages 产出带 generate_all 的 Stages，且能驱动 batch）**

追加到 `tests/test_sound_track_agent/test_stages_factory.py`：

```python
from sound_track_agent.stages_factory import build_stages
from sound_track_agent.scorer import CandidateScore
from sound_track_agent.session import ScoringSession, SegmentScore


def test_build_stages_wires_generate_all(tmp_path):
    # 复用 test_batch_generator 的 FakeClient 思路：内联一个最小 fake
    import threading

    class FakeClient:
        def __init__(self):
            self.created = []
            self._lock = threading.Lock()

        def create_task(self, *, workflow_id, node_info_list=None):
            seed = next(n["fieldValue"] for n in node_info_list if n["nodeId"] == "109")
            with self._lock:
                self.created.append(seed)
            return f"t{seed}"

        def query_task(self, task_id):
            return {"status": "SUCCESS", "results": [{"url": "http://x/a.mp3"}]}

        def download_file(self, url, dest):
            from pathlib import Path
            dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"A")
            return dest

    client = FakeClient()
    stages = build_stages(
        provider=None, client=client, workflow_id="wf", work_dir=tmp_path,
        global_style="style", seeds=[1, 2],
        frame_provider=lambda seg: tmp_path / "f.png",
        score_fn=lambda p, expected_dur=0.0: CandidateScore(0.5, 1.0, 0.5, 0.5),
        max_concurrency=2)
    assert stages.generate_all is not None

    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="style",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0,
                                                 status="prompted")])
    stages.generate_all(sess)
    assert sorted(client.created) == [1, 2]
    assert len(sess.segments[0].candidates) == 2
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_stages_factory.py -q`
Expected: FAIL（`build_stages` 不接受 `score_fn`/`max_concurrency`，或 `generate_all` 为 None）

- [ ] **Step 3: 改 `build_stages`**

`sound_track_agent/stages_factory.py` 顶部 import 加：

```python
from sound_track_agent import emotion_tagger, prompt_composer, music_generator
from sound_track_agent import batch_generator, scorer
```

把 `build_stages` 函数签名改为（加 `max_concurrency`、`score_fn`、`seeds_count` 推导）：

```python
def build_stages(*, provider, client, workflow_id: str,
                 work_dir, global_style: str, seeds: list,
                 frame_provider: Callable[[SegmentScore], Path],
                 mix_fn: Optional[Callable[[ScoringSession], str]] = None,
                 align_fn: Optional[Callable[[ScoringSession], None]] = None,
                 max_concurrency: int = 3,
                 score_fn: Optional[Callable] = None,
                 ) -> Stages:
```

在函数体内（`work_dir = Path(work_dir)` 之后）加一个共享的 `compose` 闭包，并把原 `generate` 改成复用它：

```python
    work_dir = Path(work_dir)
    seeds_count = len(list(seeds))
    _score = score_fn or scorer.score_candidate
    cache_dir = work_dir / "cache" / "bgm"

    def compose(seg: SegmentScore):
        return prompt_composer.compose_acestep_inputs(
            global_style, seg.emotion, seg.duration)
```

把原 `compose_prompt` 与 `generate` 两个闭包替换为复用 `compose`：

```python
    def compose_prompt(seg: SegmentScore, sess: ScoringSession) -> str:
        tags, _bpm, _dur = compose(seg)
        return tags

    def generate(seg: SegmentScore, sess: ScoringSession):
        tags, bpm, dur = compose(seg)
        seg_dir = work_dir / f"seg{seg.index}"
        return music_generator.generate_bgm(
            client, workflow_id, tags=tags, bpm=bpm, duration=dur,
            out_dir=seg_dir, seeds=list(seeds))

    def generate_all(sess: ScoringSession) -> None:
        batch_generator.generate_all(
            sess, client=client, workflow_id=workflow_id, cache_dir=cache_dir,
            compose=compose, score_fn=_score, seeds_count=seeds_count,
            max_concurrency=max_concurrency)
```

最后把 `return Stages(...)` 改为带上 `generate_all`：

```python
    return Stages(
        tag_emotion=tag_emotion,
        compose_prompt=compose_prompt,
        generate=generate,
        align=align_fn or _noop_align,
        mix=mix_fn or _unconfigured_mix,
        generate_all=generate_all,
    )
```

> `tag_emotion`、`_noop_align`、`_unconfigured_mix` 三个闭包保持原样不动。

- [ ] **Step 4: 运行，确认通过（含原有用例）**

Run: `python -m pytest tests/test_sound_track_agent/test_stages_factory.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/stages_factory.py tests/test_sound_track_agent/test_stages_factory.py
git commit -m "feat(soundtrack): stages_factory 装配 generate_all（并发+缓存+打分）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: facade.py 注入配置 + regenerate 走新种子

**Files:**
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

- [ ] **Step 1: 替换旧 regenerate 测试 + 写新失败测试（注入 client/新种子 + progress 保留 generate_all）**

先**删除** `tests/test_sound_track_agent/test_facade.py` 中两个用旧 `stages=` API 的用例
`test_regenerate_segment_replaces_only_target`、`test_regenerate_segment_out_of_range_raises`
（约 line 118-153 的两段函数；上方 `from sound_track_agent.facade import regenerate_segment` 行可保留）。
然后追加下列用例：

```python
import threading

from sound_track_agent import facade
from sound_track_agent.pipeline import Stages
from sound_track_agent.scorer import CandidateScore
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate


class _Cfg:
    runninghub_api_key = "k"
    runninghub_base_url = "https://example.test"
    soundtrack_max_concurrency = 2
    soundtrack_score_weights = None


class _FakeClient:
    def __init__(self):
        self.created = []
        self._lock = threading.Lock()

    def create_task(self, *, workflow_id, node_info_list=None):
        seed = next(n["fieldValue"] for n in node_info_list if n["nodeId"] == "109")
        with self._lock:
            self.created.append(seed)
        return f"t{seed}"

    def query_task(self, task_id):
        return {"status": "SUCCESS", "results": [{"url": "http://x/a.mp3"}]}

    def download_file(self, url, dest):
        from pathlib import Path
        dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"A")
        return dest


def _one_seg_session():
    return ScoringSession(
        source_mp4="x", source_hash="h", global_style="style", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0, next_seed=3,
                               status="generated")])


def test_regenerate_uses_injected_client_and_fresh_seeds(tmp_path):
    sess = _one_seg_session()
    client = _FakeClient()
    facade.regenerate_segment(
        sess, 0, tmp_path, cfg=_Cfg(), workflow_id="wf", seeds_count=2,
        client=client,
        score_fn=lambda p, expected_dur=0.0: CandidateScore(0.5, 1.0, 0.5, 0.5))
    seg = sess.segments[0]
    assert sorted(client.created) == [3, 4]          # 用 next_seed 起的新种子
    assert seg.next_seed == 5
    assert len(seg.candidates) == 2 and seg.chosen_candidate is not None
    assert (tmp_path / "session.json").exists()       # 落盘


def test_regenerate_seg_index_out_of_range_raises(tmp_path):
    import pytest
    sess = _one_seg_session()
    with pytest.raises(ValueError):
        facade.regenerate_segment(sess, 5, tmp_path, cfg=_Cfg(),
                                  workflow_id="wf", client=_FakeClient())


def test_advance_preserves_generate_all_under_progress(tmp_path):
    # progress 包装（on_progress 非 None）后，generate_all 钩子不能丢，否则回退到逐段
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0,
                                                 status="prompted")])
    calls = {"all": 0}

    def gen_all(s):
        calls["all"] += 1
        s.segments[0].candidates = [BGMCandidate(path="a.mp3", seed=1, prompt="p")]
        s.segments[0].chosen_candidate = 0

    stages = Stages(
        tag_emotion=lambda seg, s: None,
        compose_prompt=lambda seg, s: "p",
        generate=lambda seg, s: (_ for _ in ()).throw(AssertionError("不应走逐段")),
        align=lambda s: None, mix=lambda s: "out.mp4",
        generate_all=gen_all)
    facade.advance(sess, tmp_path / "w", cfg=object(), workflow_id="wf",
                   stop_after="generate", stages=stages, on_progress=lambda m: None)
    assert calls["all"] == 1
    assert sess.segments[0].status == "generated"
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: FAIL（`regenerate_segment` 不接受 `client`/`score_fn`；且 `_wrap_progress` 丢掉 `generate_all` → progress 用例走逐段触发 AssertionError）

- [ ] **Step 3: 改 `_wrap_progress` 保留（并包装）`generate_all`**

`sound_track_agent/facade.py` 的 `_wrap_progress` 里，把末尾 `return Stages(...)` 补上 `generate_all`（其余不动）：

```python
    return Stages(
        tag_emotion=wrap(stages.tag_emotion, "情绪分析"),
        compose_prompt=wrap(stages.compose_prompt, "生成 prompt"),
        generate=wrap(stages.generate, "生成 BGM"),
        align=wrap_whole(stages.align, "对齐卡点"),
        mix=wrap_whole(stages.mix, "混音出片"),
        generate_all=(wrap_whole(stages.generate_all, "生成 BGM")
                      if stages.generate_all is not None else None),
    )
```

- [ ] **Step 4: 改 `_build_real_stages` 透传并发上限 + 打分权重**

`sound_track_agent/facade.py` 的 `_build_real_stages` 里，把 `build_stages(...)` 调用补上两个参数（其余参数不动）：

```python
    from sound_track_agent import scorer
    weights = getattr(cfg, "soundtrack_score_weights", None)
    score_fn = (None if not weights else
                (lambda p, expected_dur=0.0:
                 scorer.score_candidate(p, expected_dur=expected_dur, weights=weights)))
    return build_stages(
        provider=provider, client=client, workflow_id=workflow_id,
        work_dir=work_dir, global_style=global_style,
        seeds=list(range(1, seeds_count + 1)),
        frame_provider=lambda seg: extract_segment_frame(
            video_path, seg, frames_dir / f"seg{seg.index}.png"),
        align_fn=_make_align_fn(video_path),
        mix_fn=partial(assemble_and_mix, video_path=video_path,
                       work_dir=work_dir,
                       big_threshold=float(getattr(cfg, "accent_big_threshold", 0.7)),
                       snap_window=float(getattr(cfg, "accent_snap_window", 0.6))),
        max_concurrency=int(getattr(cfg, "soundtrack_max_concurrency", 3)),
        score_fn=score_fn,
    )
```

- [ ] **Step 5: 重写 `regenerate_segment` 走 `batch_generator.generate_one`**

把 `sound_track_agent/facade.py` 的 `regenerate_segment` 整个函数替换为：

```python
def regenerate_segment(session: ScoringSession, seg_index: int, work_dir, *,
                       cfg, workflow_id: str, seeds_count: int = 2,
                       client=None, score_fn=None) -> ScoringSession:
    """对单段重跑 generate（用新种子换候选、清选定），不动其它段。落盘并返回。

    client/score_fn 可注入（测试用 fake）；为 None 时内部组装真实依赖。
    """
    if not (0 <= seg_index < len(session.segments)):
        raise ValueError(f"seg_index 越界: {seg_index}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    from sound_track_agent import batch_generator, scorer
    from sound_track_agent.prompt_composer import compose_acestep_inputs

    if client is None:
        from drama_shot_master.providers.runninghub import RunningHubClient
        client = RunningHubClient(
            getattr(cfg, "runninghub_api_key", ""),
            base_url=getattr(cfg, "runninghub_base_url",
                             "https://www.runninghub.cn"))
    if score_fn is None:
        weights = getattr(cfg, "soundtrack_score_weights", None)
        score_fn = (lambda p, expected_dur=0.0:
                    scorer.score_candidate(p, expected_dur=expected_dur,
                                           weights=weights))

    global_style = session.global_style

    def compose(seg):
        return compose_acestep_inputs(global_style, seg.emotion, seg.duration)

    batch_generator.generate_one(
        session, seg_index, client=client, workflow_id=workflow_id,
        cache_dir=work_dir / "cache" / "bgm", compose=compose, score_fn=score_fn,
        seeds_count=seeds_count,
        max_concurrency=int(getattr(cfg, "soundtrack_max_concurrency", 3)))
    session.save(work_dir / "session.json")
    return session
```

> 旧 `regenerate_segment` 的 `stages` 参数被移除；当前调用方
> `drama_shot_master/ui/widgets/soundtrack_editor.py:259` 未传 `stages`，兼容。

- [ ] **Step 6: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: PASS

- [ ] **Step 7: 跑整个配乐 agent 测试 + UI 冒烟，确认零回归**

Run: `python -m pytest tests/test_sound_track_agent tests/test_ui/test_segment_review_smoke.py tests/test_ui/test_accent_editor_smoke.py -q`
Expected: PASS（全绿）

- [ ] **Step 8: 提交**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(soundtrack): facade 注入并发/打分配置，regenerate 走 generate_one 新种子

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 收尾验证（全部任务完成后）

- [ ] **回归全测**

Run: `python -m pytest tests/test_sound_track_agent -q`
Expected: PASS

- [ ] **对照验收标准（spec §12）逐条确认**

1. 并发执行、不超 `soundtrack_max_concurrency` → `test_concurrency_cap_respected`。
2. 缓存命中不再 `create_task` → `test_generate_all_uses_cache_skips_create`。
3. regenerate 产出新种子候选 → `test_generate_one_replaces_with_fresh_seeds` / `test_regenerate_uses_injected_client_and_fresh_seeds`。
4. `chosen_candidate` 指向打分最优、坏生成不被选 → `scorer` 用例 + `test_generate_all_fills_...`。
5. 单段失败不连累其它、失败段续跑可补 → `test_failure_isolation_*` / `test_total_failure_*` + pipeline `test_generate_all_zero_candidates_stays_prompted`。
6. 逐段回退零回归 → `test_fallback_per_segment_when_no_hook` + 原有用例全绿。
```
