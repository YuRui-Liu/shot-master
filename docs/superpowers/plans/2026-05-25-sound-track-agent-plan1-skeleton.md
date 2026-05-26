# sound_track_agent Plan 1：核心骨架与纯逻辑 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭起 `sound_track_agent/` 包的确定性骨架——数据/持久化/续跑、provider 构造、段落聚合、prompt 模板、卡点对齐算法、编排框架（外部阶段用 stub）、CLI；全部可严格 TDD。

**Architecture:** 一条 6 阶段管线的"地基"。本 Plan 只实现不依赖外部库/模型实际行为的纯逻辑单元；shot_detector / emotion_tagger / music_generator / accent_detector / audio_mixer 这些接外部依赖的模块由后续 Plan 2-4 在验证库行为后实现。pipeline 用 Stage 协议 + stub 实现先跑通编排与 pause/resume，后续 Plan 把 stub 换成真实实现。

**Tech Stack:** Python 3.10+、dataclasses、pytest。复用宿主 `drama_shot_master.providers`（OpenAICompatProvider/ProviderConfig）。无新增第三方依赖（外部库在后续 Plan 引入）。

参考 spec：`docs/superpowers/specs/2026-05-25-sound-track-agent-design.md`

---

## 文件结构（本 Plan 涉及）

```
sound_track_agent/
  __init__.py          # 包标记
  session.py           # 数据结构 + 持久化 + 续跑 + hash 工具
  provider.py          # build_soundtrack_provider（参照 refine）
  segment_planner.py   # Shot 类型 + plan_segments 聚合
  prompt_composer.py   # compose_music_prompt 模板组装
  beat_aligner.py      # snap_boundaries_to_beats / align_accents 纯算法
  pipeline.py          # Stage 协议 + orchestrator + pause/resume（stub 阶段）
  cli.py               # argparse 入口 run/resume
tests/test_sound_track_agent/
  __init__.py
  test_session.py
  test_segment_planner.py
  test_provider.py
  test_prompt_composer.py
  test_beat_aligner.py
  test_pipeline.py
```

测试运行约定（本仓库）：从项目根用 `/usr/local/bin/pytest`。

---

## Task 1：session 数据结构 + 序列化

**Files:**
- Create: `sound_track_agent/__init__.py`
- Create: `sound_track_agent/session.py`
- Create: `tests/test_sound_track_agent/__init__.py`
- Test: `tests/test_sound_track_agent/test_session.py`

- [ ] **Step 1: 建包标记文件**

Create `sound_track_agent/__init__.py`（空文件）和 `tests/test_sound_track_agent/__init__.py`（空文件）。

- [ ] **Step 2: 写失败测试**

`tests/test_sound_track_agent/test_session.py`:

```python
from sound_track_agent.session import (
    EmotionTag, BGMCandidate, AccentPoint, SegmentScore, ScoringSession,
)


def test_segment_duration_computed():
    seg = SegmentScore(index=0, t_start=2.0, t_end=6.5)
    assert seg.duration == 4.5
    assert seg.status == "pending"
    assert seg.emotion is None
    assert seg.candidates == []


def test_session_roundtrip_to_dict_from_dict():
    sess = ScoringSession(
        source_mp4="/x/ep1.mp4", source_hash="abc123",
        global_style="末日废土冷色调", frame_rate=24.0,
        segments=[
            SegmentScore(
                index=0, t_start=0.0, t_end=8.0, shot_ids=[0, 1],
                emotion=EmotionTag(labels=["tense"], valence=-0.4,
                                   arousal=0.7, intensity=0.8),
                music_prompt="dark ambient, 90 BPM",
                candidates=[BGMCandidate(path="/x/c0.wav", seed=7,
                                         prompt="dark ambient, 90 BPM")],
                chosen_candidate=0, status="chosen",
            ),
        ],
        accent_points=[AccentPoint(t=5.2, intensity=0.9, confirmed=True)],
        output=None,
    )
    restored = ScoringSession.from_dict(sess.to_dict())
    assert restored == sess
```

- [ ] **Step 3: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_session.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'sound_track_agent.session'`）

- [ ] **Step 4: 实现 session.py 数据结构**

`sound_track_agent/session.py`:

```python
"""配乐会话数据结构 + 持久化 + 续跑。零外部依赖，可单测。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Status = Literal["pending", "tagged", "prompted", "generated", "chosen", "aligned"]


@dataclass
class EmotionTag:
    labels: list[str] = field(default_factory=list)
    valence: float = 0.0       # -1..1
    arousal: float = 0.0       # 0..1
    intensity: float = 0.5     # 0..1


@dataclass
class BGMCandidate:
    path: str
    seed: int
    prompt: str


@dataclass
class AccentPoint:
    t: float
    intensity: float
    confirmed: bool = False


@dataclass
class SegmentScore:
    index: int
    t_start: float
    t_end: float
    shot_ids: list[int] = field(default_factory=list)
    emotion: Optional[EmotionTag] = None
    music_prompt: str = ""
    candidates: list[BGMCandidate] = field(default_factory=list)
    chosen_candidate: Optional[int] = None
    status: Status = "pending"

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "shot_ids": list(self.shot_ids),
            "emotion": (vars(self.emotion) if self.emotion else None),
            "music_prompt": self.music_prompt,
            "candidates": [vars(c) for c in self.candidates],
            "chosen_candidate": self.chosen_candidate,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SegmentScore":
        emo = d.get("emotion")
        return cls(
            index=int(d["index"]),
            t_start=float(d["t_start"]),
            t_end=float(d["t_end"]),
            shot_ids=list(d.get("shot_ids", [])),
            emotion=(EmotionTag(**emo) if emo else None),
            music_prompt=d.get("music_prompt", ""),
            candidates=[BGMCandidate(**c) for c in d.get("candidates", [])],
            chosen_candidate=d.get("chosen_candidate"),
            status=d.get("status", "pending"),
        )


@dataclass
class ScoringSession:
    source_mp4: str
    source_hash: str
    global_style: str
    frame_rate: float
    segments: list[SegmentScore] = field(default_factory=list)
    accent_points: list[AccentPoint] = field(default_factory=list)
    output: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source_mp4": self.source_mp4,
            "source_hash": self.source_hash,
            "global_style": self.global_style,
            "frame_rate": self.frame_rate,
            "segments": [s.to_dict() for s in self.segments],
            "accent_points": [vars(a) for a in self.accent_points],
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScoringSession":
        return cls(
            source_mp4=d["source_mp4"],
            source_hash=d["source_hash"],
            global_style=d.get("global_style", ""),
            frame_rate=float(d.get("frame_rate", 24.0)),
            segments=[SegmentScore.from_dict(s) for s in d.get("segments", [])],
            accent_points=[AccentPoint(**a) for a in d.get("accent_points", [])],
            output=d.get("output"),
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_session.py -q`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add sound_track_agent/__init__.py sound_track_agent/session.py tests/test_sound_track_agent/__init__.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(sound_track_agent): session 数据结构 + 序列化"
```

---

## Task 2：session 持久化（save/load）+ 文件 hash

**Files:**
- Modify: `sound_track_agent/session.py`（追加 hash_file 函数 + save/load 方法）
- Test: `tests/test_sound_track_agent/test_session.py`（追加测试）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_sound_track_agent/test_session.py` 末尾追加：

```python
from pathlib import Path
from sound_track_agent.session import hash_file


def test_hash_file_stable(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello world")
    h1 = hash_file(f)
    h2 = hash_file(f)
    assert h1 == h2
    assert len(h1) == 16          # 取 sha256 前 16 hex
    f.write_bytes(b"different")
    assert hash_file(f) != h1


def test_session_save_load_roundtrip(tmp_path):
    sess = ScoringSession(
        source_mp4="/x/ep1.mp4", source_hash="abc123",
        global_style="冷色调", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)],
    )
    p = tmp_path / "session.json"
    sess.save(p)
    assert p.exists()
    loaded = ScoringSession.load(p)
    assert loaded == sess
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_session.py -q`
Expected: FAIL（`ImportError: cannot import name 'hash_file'`）

- [ ] **Step 3: 实现 hash_file + save/load**

在 `sound_track_agent/session.py` 顶部 import 区追加：

```python
import hashlib
import json
from pathlib import Path
```

文件末尾追加：

```python
def hash_file(path: Path, chunk: int = 1 << 20) -> str:
    """文件内容 sha256 前 16 hex，作缓存/会话键。"""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()[:16]
```

在 `ScoringSession` 类内追加方法：

```python
    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ScoringSession":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_session.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/session.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(sound_track_agent): session 持久化 + 文件 hash"
```

---

## Task 3：segment_planner 段落聚合

**Files:**
- Create: `sound_track_agent/segment_planner.py`
- Test: `tests/test_sound_track_agent/test_segment_planner.py`

**逻辑**：把 N 个镜头（Shot）按累计时长均衡聚合成 target（默认 4，clamp 3-5）个叙事段落，相邻镜头不跨段重排。每段 `shot_ids` 记录聚合了哪些镜头，`t_start/t_end` 取该段首尾镜头边界。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_segment_planner.py`:

```python
import pytest
from sound_track_agent.segment_planner import Shot, plan_segments


def _shots(durations, fps_gap=0.0):
    """按给定时长序列造连续镜头。"""
    shots, t = [], 0.0
    for i, d in enumerate(durations):
        shots.append(Shot(index=i, t_start=t, t_end=t + d))
        t += d
    return shots


def test_plan_segments_aggregates_to_target_count():
    shots = _shots([2, 2, 2, 2, 2, 2, 2, 2])   # 8 镜头，总 16s
    segs = plan_segments(shots, target=4)
    assert len(segs) == 4
    # 段覆盖完整时间轴、首尾衔接
    assert segs[0].t_start == 0.0
    assert segs[-1].t_end == 16.0
    for a, b in zip(segs, segs[1:]):
        assert a.t_end == b.t_start
    # 每个镜头恰好归入一段
    all_ids = [i for s in segs for i in s.shot_ids]
    assert sorted(all_ids) == list(range(8))


def test_plan_segments_clamps_when_few_shots():
    shots = _shots([3, 3])      # 只有 2 镜头，无法分 4 段
    segs = plan_segments(shots, target=4)
    assert len(segs) == 2       # 段数不超过镜头数
    assert all(s.status == "pending" for s in segs)


def test_plan_segments_index_sequential():
    shots = _shots([1, 1, 1, 1, 1, 1])
    segs = plan_segments(shots, target=3)
    assert [s.index for s in segs] == [0, 1, 2]


def test_plan_segments_empty_raises():
    with pytest.raises(ValueError):
        plan_segments([], target=4)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_segment_planner.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 segment_planner.py**

`sound_track_agent/segment_planner.py`:

```python
"""镜头切点 → 叙事段落聚合。纯逻辑，可单测。"""
from __future__ import annotations

from dataclasses import dataclass

from sound_track_agent.session import SegmentScore


@dataclass
class Shot:
    index: int
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


def plan_segments(shots: list[Shot], target: int = 4) -> list[SegmentScore]:
    """把相邻镜头按累计时长均衡聚合成 ~target 段（clamp 3-5、且不超过镜头数）。

    贪心：理想段长 = 总时长 / 段数；累加镜头，超过理想段长即断段。
    """
    if not shots:
        raise ValueError("plan_segments 需要至少 1 个镜头")
    n_seg = max(1, min(target, len(shots)))
    n_seg = min(n_seg, 5)
    total = sum(s.duration for s in shots)
    ideal = total / n_seg

    groups: list[list[Shot]] = []
    cur: list[Shot] = []
    cur_dur = 0.0
    for shot in shots:
        cur.append(shot)
        cur_dur += shot.duration
        # 已凑够一段，且剩余镜头还够铺满剩余段数 → 断段
        remaining_segs = n_seg - len(groups) - 1
        remaining_shots = len(shots) - sum(len(g) for g in groups) - len(cur)
        if (cur_dur >= ideal and remaining_segs >= 1
                and remaining_shots >= remaining_segs):
            groups.append(cur)
            cur, cur_dur = [], 0.0
    if cur:
        groups.append(cur)

    segs: list[SegmentScore] = []
    for i, g in enumerate(groups):
        segs.append(SegmentScore(
            index=i,
            t_start=g[0].t_start,
            t_end=g[-1].t_end,
            shot_ids=[s.index for s in g],
        ))
    return segs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_segment_planner.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/segment_planner.py tests/test_sound_track_agent/test_segment_planner.py
git commit -m "feat(sound_track_agent): 镜头→叙事段落聚合"
```

---

## Task 4：provider 构造（参照 refine）

**Files:**
- Create: `sound_track_agent/provider.py`
- Test: `tests/test_sound_track_agent/test_provider.py`

**逻辑**：参照 `drama_shot_master/core/prompt_refiner.py:build_refine_provider`，用 `OpenAICompatProvider(ProviderConfig(...))` 构造豆包 vision provider。默认模型 `doubao-seed-2-0-lite-260215`，超时 300s。配置取值优先级：`cfg.soundtrack_*` → `cfg.base_urls['doubao']` / `cfg.api_keys['doubao']` → 兜底默认。用 getattr 容错，不强制宿主 config 新增字段。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_provider.py`:

```python
from sound_track_agent.provider import (
    build_soundtrack_provider, DEFAULT_MODEL, REQUEST_TIMEOUT,
)


class _Cfg:
    """模拟宿主 Config 的最小子集。"""
    def __init__(self, **kw):
        self.api_keys = kw.get("api_keys", {})
        self.base_urls = kw.get("base_urls", {})
        for k, v in kw.items():
            if k not in ("api_keys", "base_urls"):
                setattr(self, k, v)


def test_default_model_is_doubao_lite():
    assert DEFAULT_MODEL == "doubao-seed-2-0-lite-260215"


def test_build_uses_doubao_creds_from_base_urls():
    cfg = _Cfg(api_keys={"doubao": "k-doubao"},
               base_urls={"doubao": "https://ark.example/api/v3"})
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-doubao"
    assert p.config.base_url == "https://ark.example/api/v3"
    assert p.config.model == DEFAULT_MODEL
    assert p.config.timeout == REQUEST_TIMEOUT


def test_soundtrack_overrides_take_priority():
    cfg = _Cfg(api_keys={"doubao": "k-doubao"},
               base_urls={"doubao": "https://ark.example/api/v3"},
               soundtrack_api_key="k-st",
               soundtrack_base_url="https://st.example/v1",
               soundtrack_model="doubao-custom")
    p = build_soundtrack_provider(cfg)
    assert p.config.api_key == "k-st"
    assert p.config.base_url == "https://st.example/v1"
    assert p.config.model == "doubao-custom"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_provider.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 provider.py**

`sound_track_agent/provider.py`:

```python
"""配乐 agent 的 vision provider 构造（参照 prompt_refiner.build_refine_provider）。

默认豆包 doubao-seed-2-0-lite-260215（便宜），OpenAI 兼容接口。
情绪/prompt 的实际调用走 VisionProvider.generate(images, system_prompt, user_supplement)。
"""
from __future__ import annotations

DEFAULT_MODEL = "doubao-seed-2-0-lite-260215"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
REQUEST_TIMEOUT = 300.0      # 多图 + 长输出，放宽超时（同 refine）


def build_soundtrack_provider(cfg):
    """用配乐专属/豆包配置构造 vision provider。

    取值优先级：cfg.soundtrack_* → cfg.base_urls/api_keys['doubao'] → 默认。
    """
    from drama_shot_master.providers.openai_compat import OpenAICompatProvider
    from drama_shot_master.providers.base import ProviderConfig

    api_key = (getattr(cfg, "soundtrack_api_key", "")
               or getattr(cfg, "api_keys", {}).get("doubao", ""))
    base_url = (getattr(cfg, "soundtrack_base_url", "")
                or getattr(cfg, "base_urls", {}).get("doubao", "")
                or DEFAULT_BASE_URL)
    model = getattr(cfg, "soundtrack_model", "") or DEFAULT_MODEL

    return OpenAICompatProvider(ProviderConfig(
        api_key=api_key or "x",
        base_url=base_url,
        model=model,
        timeout=REQUEST_TIMEOUT,
    ))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_provider.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/provider.py tests/test_sound_track_agent/test_provider.py
git commit -m "feat(sound_track_agent): 豆包 vision provider 构造（参照 refine）"
```

---

## Task 5：prompt_composer 音乐 prompt 模板

**Files:**
- Create: `sound_track_agent/prompt_composer.py`
- Test: `tests/test_sound_track_agent/test_prompt_composer.py`

**逻辑**：把「总风格 + 段落 EmotionTag + 时长」确定性地组装成 ACE-Step BGM-only prompt 文本。本 Task 只做模板组装（纯函数）；可选的"豆包润色"留到后续 Plan，不在此。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_prompt_composer.py`:

```python
from sound_track_agent.session import EmotionTag
from sound_track_agent.prompt_composer import compose_music_prompt


def test_compose_includes_core_fields():
    emo = EmotionTag(labels=["tense", "suspense"], valence=-0.5,
                     arousal=0.8, intensity=0.9)
    out = compose_music_prompt(
        global_style="末日废土，冷色调低饱和", emotion=emo, duration=8.5)
    assert "[BGM-only]" in out
    assert "末日废土，冷色调低饱和" in out
    assert "tense" in out and "suspense" in out
    assert "8.5s" in out
    # 对白友好硬约束必须在
    assert "no vocal" in out
    assert "dialogue-friendly" in out


def test_compose_high_arousal_implies_faster_tempo_hint():
    fast = compose_music_prompt(
        "x", EmotionTag(labels=["epic"], arousal=0.9), 10.0)
    slow = compose_music_prompt(
        "x", EmotionTag(labels=["calm"], arousal=0.1), 10.0)
    assert "BPM" in fast and "BPM" in slow
    # 高 arousal 的 BPM 下界应高于低 arousal
    assert "110-140 BPM" in fast
    assert "60-80 BPM" in slow


def test_compose_no_emotion_falls_back_to_neutral():
    out = compose_music_prompt("古风", emotion=None, duration=5.0)
    assert "古风" in out
    assert "5.0s" in out
    assert "no vocal" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_prompt_composer.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 prompt_composer.py**

`sound_track_agent/prompt_composer.py`:

```python
"""总风格 + 段落情绪 + 时长 → ACE-Step BGM-only prompt。纯模板，可单测。"""
from __future__ import annotations

from typing import Optional

from sound_track_agent.session import EmotionTag


def _tempo_hint(arousal: float) -> str:
    """情绪唤起度 → BPM 区间提示。"""
    if arousal >= 0.66:
        return "110-140 BPM"
    if arousal >= 0.33:
        return "85-110 BPM"
    return "60-80 BPM"


def compose_music_prompt(global_style: str,
                         emotion: Optional[EmotionTag],
                         duration: float) -> str:
    """组装一段 BGM-only 的 ACE-Step prompt。

    确定性：相同输入永远得到相同文本（便于缓存与测试）。
    """
    labels = emotion.labels if emotion else []
    arousal = emotion.arousal if emotion else 0.3
    mood = ", ".join(labels) if labels else "neutral, restrained"
    lines = [
        "[BGM-only]",
        f"Overall style: {global_style}",
        f"Mood: {mood}",
        f"Tempo: {_tempo_hint(arousal)}",
        f"Length: {duration:.1f}s",
        "Mix: dialogue-friendly, leave headroom for speech, no vocal, no lyrics",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_prompt_composer.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/prompt_composer.py tests/test_sound_track_agent/test_prompt_composer.py
git commit -m "feat(sound_track_agent): ACE-Step BGM-only prompt 模板"
```

---

## Task 6：beat_aligner 卡点对齐算法

**Files:**
- Create: `sound_track_agent/beat_aligner.py`
- Test: `tests/test_sound_track_agent/test_beat_aligner.py`

**逻辑**：两个纯函数。`snap_boundaries_to_beats`：把段落边界吸附到最近的音乐 beat（超出 max_shift 则不吸附，保留原值）。`align_accents`：把爆点时间戳匹配到容差内最近的 beat，返回匹配对（无匹配则跳过）。都喂 mock 时间戳，无外部依赖。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_beat_aligner.py`:

```python
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
    boundaries = [2.0]               # 距最近 beat 2.0s，超过 max_shift
    out = snap_boundaries_to_beats(boundaries, beats, max_shift=0.3)
    assert out == [2.0]              # 不吸附，保留原值


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
    accents = [1.0]                  # 距最近 beat 1.0s > tolerance
    out = align_accents(accents, beats, tolerance=0.1)
    assert out == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_beat_aligner.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 beat_aligner.py**

`sound_track_agent/beat_aligner.py`:

```python
"""卡点对齐纯算法：段落边界吸附 beat、爆点匹配 beat。可单测。"""
from __future__ import annotations


def _nearest(value: float, candidates: list[float]) -> float:
    return min(candidates, key=lambda c: abs(c - value))


def snap_boundaries_to_beats(boundaries: list[float],
                             beats: list[float],
                             max_shift: float = 0.3) -> list[float]:
    """把每个段落边界吸附到最近 beat；偏移超过 max_shift 则保留原值。

    beats 为空时原样返回。
    """
    if not beats:
        return list(boundaries)
    out: list[float] = []
    for b in boundaries:
        nb = _nearest(b, beats)
        out.append(nb if abs(nb - b) <= max_shift else b)
    return out


def align_accents(accents: list[float],
                  beats: list[float],
                  tolerance: float = 0.1) -> list[tuple[float, float]]:
    """把爆点匹配到容差内最近 beat，返回 (accent_t, beat_t) 对；无匹配则跳过。"""
    if not beats:
        return []
    pairs: list[tuple[float, float]] = []
    for a in accents:
        nb = _nearest(a, beats)
        if abs(nb - a) <= tolerance:
            pairs.append((a, nb))
    return pairs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_beat_aligner.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/beat_aligner.py tests/test_sound_track_agent/test_beat_aligner.py
git commit -m "feat(sound_track_agent): 卡点对齐纯算法（边界吸附 + 爆点匹配）"
```

---

## Task 7：pipeline 编排框架 + pause/resume（stub 阶段）

**Files:**
- Create: `sound_track_agent/pipeline.py`
- Test: `tests/test_sound_track_agent/test_pipeline.py`

**逻辑**：定义阶段接口与编排器。编排器按 [tag_emotion → compose_prompt → generate → align → mix] 推进，每个确认点把 session 落盘并可在该点停下（`run(..., stop_after=...)`），再次调用 `run` 时从 session 现状继续。本 Task 用注入的 stub 阶段函数验证编排/续跑，不接真实外部实现。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_pipeline.py`:

```python
from pathlib import Path
from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate,
)
from sound_track_agent.pipeline import Stages, run


def _base_session():
    return ScoringSession(
        source_mp4="/x/ep1.mp4", source_hash="h1",
        global_style="冷色调", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0),
                  SegmentScore(index=1, t_start=4.0, t_end=8.0)],
    )


def _stub_stages():
    return Stages(
        tag_emotion=lambda seg, sess: EmotionTag(labels=["calm"], arousal=0.2),
        compose_prompt=lambda seg, sess: f"prompt-{seg.index}",
        generate=lambda seg, sess: [
            BGMCandidate(path=f"/x/{seg.index}.wav", seed=1,
                         prompt=seg.music_prompt)],
        align=lambda sess: None,
        mix=lambda sess: "/x/out.mp4",
    )


def test_run_advances_all_segments_to_generated(tmp_path):
    sess = _base_session()
    sp = tmp_path / "session.json"
    run(sess, _stub_stages(), session_path=sp, stop_after="generate")
    assert all(s.status == "generated" for s in sess.segments)
    assert all(s.emotion is not None for s in sess.segments)
    assert all(s.music_prompt == f"prompt-{s.index}" for s in sess.segments)
    assert all(len(s.candidates) == 1 for s in sess.segments)
    assert sp.exists()                      # 落盘


def test_run_stop_after_tag_does_not_generate(tmp_path):
    sess = _base_session()
    run(sess, _stub_stages(), session_path=tmp_path / "s.json",
        stop_after="tag_emotion")
    assert all(s.status == "tagged" for s in sess.segments)
    assert all(s.music_prompt == "" for s in sess.segments)


def test_run_resumes_from_persisted_state(tmp_path):
    sess = _base_session()
    sp = tmp_path / "s.json"
    run(sess, _stub_stages(), session_path=sp, stop_after="tag_emotion")
    # 重新从盘加载，继续到出片
    reloaded = ScoringSession.load(sp)
    out = run(reloaded, _stub_stages(), session_path=sp, stop_after="mix")
    assert out == "/x/out.mp4"
    assert reloaded.output == "/x/out.mp4"
    assert all(s.status == "aligned" for s in reloaded.segments)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_pipeline.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 pipeline.py**

`sound_track_agent/pipeline.py`:

```python
"""配乐管线编排器 + pause/resume。各阶段以可注入函数提供（便于 stub/测试）。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate,
)

# 阶段顺序：到达 stop_after 指定阶段后停止（含该阶段）
STAGE_ORDER = ["tag_emotion", "compose_prompt", "generate", "align", "mix"]


@dataclass
class Stages:
    """各阶段实现的注入点。Plan 2-4 用真实实现替换 stub。"""
    tag_emotion: Callable[[SegmentScore, ScoringSession], EmotionTag]
    compose_prompt: Callable[[SegmentScore, ScoringSession], str]
    generate: Callable[[SegmentScore, ScoringSession], list[BGMCandidate]]
    align: Callable[[ScoringSession], None]
    mix: Callable[[ScoringSession], str]


def _save(sess: ScoringSession, path: Optional[Path]) -> None:
    if path is not None:
        sess.save(path)


def run(sess: ScoringSession,
        stages: Stages,
        session_path: Optional[Path] = None,
        stop_after: str = "mix") -> Optional[str]:
    """按阶段推进 session；到 stop_after 阶段后停止。

    每阶段后落盘，支持中断/续跑（已完成阶段幂等跳过）。
    返回出片路径（若推进到 mix），否则 None。
    """
    if stop_after not in STAGE_ORDER:
        raise ValueError(f"未知 stop_after: {stop_after}")
    limit = STAGE_ORDER.index(stop_after)

    # tag_emotion
    if limit >= STAGE_ORDER.index("tag_emotion"):
        for seg in sess.segments:
            if seg.status == "pending":
                seg.emotion = stages.tag_emotion(seg, sess)
                seg.status = "tagged"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("tag_emotion"):
            return None

    # compose_prompt
    if limit >= STAGE_ORDER.index("compose_prompt"):
        for seg in sess.segments:
            if seg.status == "tagged":
                seg.music_prompt = stages.compose_prompt(seg, sess)
                seg.status = "prompted"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("compose_prompt"):
            return None

    # generate
    if limit >= STAGE_ORDER.index("generate"):
        for seg in sess.segments:
            if seg.status == "prompted":
                seg.candidates = stages.generate(seg, sess)
                seg.status = "generated"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("generate"):
            return None

    # align（整轨级，标记各段 aligned）
    if limit >= STAGE_ORDER.index("align"):
        stages.align(sess)
        for seg in sess.segments:
            if seg.status in ("generated", "chosen"):
                seg.status = "aligned"
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("align"):
            return None

    # mix
    out = stages.mix(sess)
    sess.output = out
    _save(sess, session_path)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_pipeline.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/pipeline.py tests/test_sound_track_agent/test_pipeline.py
git commit -m "feat(sound_track_agent): 管线编排框架 + pause/resume（stub 阶段）"
```

---

## Task 8：CLI 骨架

**Files:**
- Create: `sound_track_agent/cli.py`
- Test: `tests/test_sound_track_agent/test_cli.py`

**逻辑**：argparse 入口，两个子命令 `run`（新建会话：给 MP4 + 总风格 + 工作目录）和 `resume`（从已存会话续跑）。本 Task 只验证参数解析正确（`build_parser`），真实管线接线（接 shot_detector 等）留后续 Plan——所以 `main` 暂时只解析 + 打印计划动作，不调真实外部阶段。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_cli.py`:

```python
from sound_track_agent.cli import build_parser


def test_run_subcommand_parses():
    p = build_parser()
    ns = p.parse_args(["run", "ep1.mp4", "--style", "冷色调末日",
                       "--work-dir", "out", "--stop-after", "generate"])
    assert ns.command == "run"
    assert ns.mp4 == "ep1.mp4"
    assert ns.style == "冷色调末日"
    assert ns.work_dir == "out"
    assert ns.stop_after == "generate"


def test_resume_subcommand_parses():
    p = build_parser()
    ns = p.parse_args(["resume", "out/h1/session.json", "--stop-after", "mix"])
    assert ns.command == "resume"
    assert ns.session == "out/h1/session.json"
    assert ns.stop_after == "mix"


def test_run_stop_after_defaults_to_mix():
    p = build_parser()
    ns = p.parse_args(["run", "ep1.mp4", "--style", "x"])
    assert ns.stop_after == "mix"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_cli.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 cli.py**

`sound_track_agent/cli.py`:

```python
"""配乐 agent 命令行入口。

run   : 新建会话并推进（接线 shot_detector 等留后续 Plan）
resume: 从已存 session.json 续跑
"""
from __future__ import annotations

import argparse

from sound_track_agent.pipeline import STAGE_ORDER


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sound_track_agent",
        description="漫剧成片后期配乐 agent")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="对成片 MP4 新建配乐会话并推进")
    pr.add_argument("mp4", help="成片 MP4 路径")
    pr.add_argument("--style", required=True, help="全剧总风格描述")
    pr.add_argument("--work-dir", default="sound_track_out",
                    help="工作目录（会话与产物落盘处）")
    pr.add_argument("--stop-after", choices=STAGE_ORDER, default="mix",
                    help="推进到该阶段后停止（半自动确认点）")

    ps = sub.add_parser("resume", help="从已存 session.json 续跑")
    ps.add_argument("session", help="session.json 路径")
    ps.add_argument("--stop-after", choices=STAGE_ORDER, default="mix")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # 真实管线接线（shot_detector → segment_planner → 真实 Stages）留 Plan 2-4。
    # 此处先回显将执行的动作，保证 CLI 可运行、可测。
    print(f"[sound_track_agent] command={args.command} "
          f"stop_after={args.stop_after}")
    if args.command == "run":
        print(f"  mp4={args.mp4} style={args.style!r} work_dir={args.work_dir}")
    else:
        print(f"  session={args.session}")
    print("  （管线接线见 Plan 2-4，当前为骨架）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/test_cli.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 跑全 Plan 测试 + commit**

Run: `/usr/local/bin/pytest tests/test_sound_track_agent/ -q`
Expected: PASS（全部，约 25 项）

```bash
git add sound_track_agent/cli.py tests/test_sound_track_agent/test_cli.py
git commit -m "feat(sound_track_agent): CLI 骨架（run/resume 参数解析）"
```

---

## 后续 Plan 预告（不在本 Plan）

- **Plan 2 视频分析**：`shot_detector`（PySceneDetect）、`accent_detector`（OpenCV 光流 + librosa）。先写库行为探针，再 TDD。
- **Plan 3 理解+生成**：`emotion_tagger`（豆包 `generate` 调用 + 解析）、`prompt_composer` 豆包润色（可选）、`music_generator`（ACE-Step 本地/ComfyUI）。
- **Plan 4 对齐+混音**：`beat_aligner` 接 librosa 取真实 beat + pyrubberband time-stretch、`audio_mixer`（Demucs 分离 + FFmpeg sidechain ducking + loudnorm）。
- **集成**：把 `pipeline.Stages` 的 stub 换成真实实现；CLI `main` 接线；导演台 GUI 壳通过 pause/resume API 驱动。
