# 配乐分析阶段优化（多帧情绪 + 情绪邻接分段）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `sound_track_agent` 分析阶段加上 C 多帧情绪（多图同 prompt）+ D 情绪邻接合并（agglomerative on adjacent pairs），通过新可选 pipeline stage `refine_segments` 重排 session.segments，让换乐边界贴合情绪转折。

**Architecture:** 复用 Phase 1 已验证的「可选 stage 钩子 + 零回归回退」模式（`generate_all`）。新 stage `refine_segments` 在 `tag_emotion` 之前；返回 `bool`（True=成功置 `session.segments_refined` 守续跑）；纯逻辑（emotion_distance / cluster_by_emotion）和薄 IO（extract_frames_at / tag_emotion_multi）分层；refine.py 编排器全 I/O 注入。失败降级返回 False，session 不动，pipeline 走原 segments（零回归）。

**Tech Stack:** Python 3.10+、`ffmpeg`（抽帧）、现有 OpenAI 兼容 vision provider（多图同 prompt 原生支持）、numpy/Path（无新增）、`pytest`。**无新依赖**。

参考 spec：`docs/superpowers/specs/2026-05-28-soundtrack-analysis-multimodal-emotion-semantic-segmentation-design.md`

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `sound_track_agent/session.py` | + `ScoringSession.segments_refined: bool` 字段 + 序列化 | 改 |
| `sound_track_agent/segment_planner.py` | + `emotion_distance` / `_avg_emotion` / `cluster_by_emotion` | 改 |
| `sound_track_agent/emotion_tagger.py` | + `tag_emotion_multi(provider, frame_paths, global_style)` | 改 |
| `sound_track_agent/mixdown.py` | + `extract_frames_at(video_path, times, out_dir, *, runner)` | 改 |
| `sound_track_agent/refine.py` | 编排器 `refine_segments(session, ...) -> bool`，全 I/O 注入 | 建 |
| `sound_track_agent/pipeline.py` | STAGE_ORDER 加 `refine_segments`；Stages 加可选字段；run() 加新 block | 改 |
| `sound_track_agent/stages_factory.py` | `build_stages` 加 `video_path` / `refine_*` kwargs；装配 `refine_segments` 闭包 | 改 |
| `sound_track_agent/facade.py` | `_build_real_stages` 透传；`_wrap_progress` 保留 `refine_segments`（关键防回归） | 改 |
| `tests/test_sound_track_agent/test_*.py` | 单测扩展 | 改 |

实现顺序按依赖：data → 纯逻辑（cluster）→ vision/I/O 小工具 → 编排器（refine）→ pipeline 钩子 → stages_factory 装配 → facade 接线。

---

## Task 1: `session.py` — `segments_refined` 字段

**Files:**
- Modify: `sound_track_agent/session.py`
- Test: `tests/test_sound_track_agent/test_session.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_session.py`：

```python
def test_segments_refined_default_false():
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    assert sess.segments_refined is False


def test_segments_refined_roundtrip(tmp_path):
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    sess.segments_refined = True
    p = tmp_path / "session.json"
    sess.save(p)
    assert ScoringSession.load(p).segments_refined is True


def test_segments_refined_default_when_missing(tmp_path):
    """旧 session.json 缺字段时默认 False（首次会触发 refine）。"""
    p = tmp_path / "session.json"
    p.write_text(
        '{"source_mp4":"x","source_hash":"h","global_style":"s",'
        '"frame_rate":24.0,"segments":[],"accent_points":[]}',
        encoding="utf-8")
    assert ScoringSession.load(p).segments_refined is False
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q`
Expected: FAIL（`ScoringSession` 无 `segments_refined` 字段）

- [ ] **Step 3: 给 `ScoringSession` 加 `segments_refined`**

在 `sound_track_agent/session.py` 中，在 `dialogue_segments: list[DialogueSegment] = field(default_factory=list)` 之后添加字段：

```python
    segments_refined: bool = False
```

在 `ScoringSession.to_dict` 返回 dict 中加一项（与 `"dialogue_segments"` 同级）：

```python
            "segments_refined": self.segments_refined,
```

在 `ScoringSession.from_dict` 的构造里加一行（与 `dialogue_segments=` 同级）：

```python
            segments_refined=bool(d.get("segments_refined", False)),
```

> 变量名按文件中实际的 from_dict 参数名（可能是 `d` 或 `data`）。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/session.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(soundtrack): + ScoringSession.segments_refined 持久化（Phase 3 守续跑）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `segment_planner.py` — 距离/平均/聚合（纯逻辑）

**Files:**
- Modify: `sound_track_agent/segment_planner.py`
- Test: `tests/test_sound_track_agent/test_segment_planner.py`

- [ ] **Step 1: 写失败测试（纯逻辑，多个边界）**

追加到 `tests/test_sound_track_agent/test_segment_planner.py`：

```python
from sound_track_agent.segment_planner import (
    Shot, emotion_distance, _avg_emotion, cluster_by_emotion,
)
from sound_track_agent.session import EmotionTag


def _et(v=0.0, a=0.3, i=0.5, labels=None):
    return EmotionTag(labels=list(labels or []), valence=v, arousal=a, intensity=i)


# ===== emotion_distance（纯）=====

def test_emotion_distance_zero_when_equal():
    e = _et(0.0, 0.5, 0.5)
    assert emotion_distance(e, e) == 0.0


def test_emotion_distance_valence_single_dim():
    # valence -1 vs 1 → val_norm 0 vs 1 → distance 1.0（其它两维相等）
    a = _et(v=-1.0, a=0.3, i=0.5)
    b = _et(v=1.0, a=0.3, i=0.5)
    assert abs(emotion_distance(a, b) - 1.0) < 1e-9


def test_emotion_distance_arousal_single_dim():
    a = _et(v=0.0, a=0.0, i=0.5)
    b = _et(v=0.0, a=0.5, i=0.5)
    assert abs(emotion_distance(a, b) - 0.5) < 1e-9


def test_emotion_distance_opposite_max():
    # (val=-1, ar=1, int=1) vs (val=1, ar=0, int=0) → 三维各差 1 → sqrt(3)
    a = _et(v=-1.0, a=1.0, i=1.0)
    b = _et(v=1.0, a=0.0, i=0.0)
    assert abs(emotion_distance(a, b) - (3 ** 0.5)) < 1e-9


# ===== _avg_emotion（纯）=====

def test_avg_emotion_weighted_by_count():
    # n_a=2 with v=1; n_b=1 with v=0 → val=(2*1+1*0)/3=0.667
    a = _et(v=1.0, a=0.3, i=0.5)
    b = _et(v=0.0, a=0.6, i=0.7)
    out = _avg_emotion(a, b, n_a=2, n_b=1)
    assert abs(out.valence - 2.0/3.0) < 1e-9
    assert abs(out.arousal - (0.3*2 + 0.6) / 3) < 1e-9
    assert abs(out.intensity - (0.5*2 + 0.7) / 3) < 1e-9


def test_avg_emotion_labels_union_sorted():
    a = _et(labels=["tense", "sad"])
    b = _et(labels=["tense", "calm"])
    out = _avg_emotion(a, b, n_a=1, n_b=1)
    assert out.labels == ["calm", "sad", "tense"]      # 排序去重


# ===== cluster_by_emotion（纯）=====

def _shot(idx, dur=1.0):
    return Shot(index=idx, t_start=float(idx), t_end=float(idx) + dur)


def test_cluster_one_shot_one_segment():
    shots = [_shot(0)]
    emotions = [_et()]
    segs = cluster_by_emotion(shots, emotions, max_segments=5, merge_threshold=0.25)
    assert len(segs) == 1
    assert segs[0].shot_ids == [0]
    assert segs[0].status == "tagged"
    assert segs[0].emotion is not None


def test_cluster_all_identical_merges_to_max_segments():
    """全相同情绪 + 6 shots + max=5 → 合并到 5 段（最小邻距离为 0，先合）。"""
    shots = [_shot(i) for i in range(6)]
    emotions = [_et(v=0.0, a=0.3, i=0.5) for _ in range(6)]
    segs = cluster_by_emotion(shots, emotions, max_segments=5, merge_threshold=0.25)
    assert len(segs) == 5


def test_cluster_all_different_returns_min_of_shots_and_max():
    """3 shots 情绪两两距离都 > merge_threshold，max=5 → 仍 3 段。"""
    shots = [_shot(i) for i in range(3)]
    emotions = [_et(v=-1.0), _et(v=0.0), _et(v=1.0)]
    segs = cluster_by_emotion(shots, emotions, max_segments=5, merge_threshold=0.25)
    assert len(segs) == 3


def test_cluster_merges_most_similar_neighbor():
    """3 shots：[相同, 相同, 不同]，max=2 → 前两段合并。"""
    shots = [_shot(i) for i in range(3)]
    same = _et(v=0.0, a=0.3, i=0.5)
    diff = _et(v=1.0, a=0.9, i=0.9)
    segs = cluster_by_emotion(shots, [same, same, diff], max_segments=2, merge_threshold=0.25)
    assert len(segs) == 2
    assert segs[0].shot_ids == [0, 1]
    assert segs[1].shot_ids == [2]


def test_cluster_max_segments_one_forces_full_merge():
    shots = [_shot(i) for i in range(4)]
    emotions = [_et(v=v) for v in [-1.0, 0.0, 0.5, 1.0]]
    segs = cluster_by_emotion(shots, emotions, max_segments=1, merge_threshold=0.25)
    assert len(segs) == 1
    assert segs[0].shot_ids == [0, 1, 2, 3]


def test_cluster_threshold_zero_only_obeys_max():
    """merge_threshold=0 + max_segments=3 with 5 shots → 恰好 3 段。"""
    shots = [_shot(i) for i in range(5)]
    emotions = [_et(v=v) for v in [-1.0, -0.5, 0.0, 0.5, 1.0]]
    segs = cluster_by_emotion(shots, emotions, max_segments=3, merge_threshold=0.0)
    assert len(segs) == 3


def test_cluster_raises_on_empty_shots():
    import pytest
    with pytest.raises(ValueError):
        cluster_by_emotion([], [], max_segments=5, merge_threshold=0.25)
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_segment_planner.py -q`
Expected: FAIL（三个新函数不存在）

- [ ] **Step 3: 实现三个函数**

在 `sound_track_agent/segment_planner.py` 顶部加 import：

```python
from sound_track_agent.session import EmotionTag, SegmentScore
```

（如已部分存在则补全。）

在文件末尾追加：

```python
def emotion_distance(a: EmotionTag, b: EmotionTag) -> float:
    """欧氏距离 on (valence_norm, arousal, intensity)。

    valence ∈[-1,1] 先映射到 [0,1] 与另两维同尺度。值域 [0, sqrt(3)]。
    """
    av = (a.valence + 1.0) / 2.0
    bv = (b.valence + 1.0) / 2.0
    d2 = ((av - bv) ** 2
          + (a.arousal - b.arousal) ** 2
          + (a.intensity - b.intensity) ** 2)
    return d2 ** 0.5


def _avg_emotion(a: EmotionTag, b: EmotionTag, n_a: int, n_b: int) -> EmotionTag:
    """按 shot 数加权平均三维数值；labels 取并集去重排序。"""
    total = n_a + n_b
    return EmotionTag(
        labels=sorted(set(a.labels) | set(b.labels)),
        valence=(a.valence * n_a + b.valence * n_b) / total,
        arousal=(a.arousal * n_a + b.arousal * n_b) / total,
        intensity=(a.intensity * n_a + b.intensity * n_b) / total,
    )


def cluster_by_emotion(shots: list[Shot], emotions: list[EmotionTag], *,
                       max_segments: int = 5,
                       merge_threshold: float = 0.25) -> list[SegmentScore]:
    """邻接 agglomerative 聚合。每 shot 起为 1 cluster，重复合并相邻距离最小的对：

    停止条件：len(clusters) ≤ max_segments AND min_adjacent_gap ≥ merge_threshold。

    返回 list[SegmentScore]，每段 emotion 已填、status="tagged"。"""
    if not shots:
        raise ValueError("cluster_by_emotion 需要至少 1 个镜头")
    if len(shots) != len(emotions):
        raise ValueError("shots/emotions 长度不一致")

    clusters: list[list[int]] = [[i] for i in range(len(shots))]
    cluster_emo: list[EmotionTag] = list(emotions)

    while len(clusters) > 1:
        gaps = [emotion_distance(cluster_emo[i], cluster_emo[i + 1])
                for i in range(len(clusters) - 1)]
        min_gap = min(gaps)
        if len(clusters) <= max_segments and min_gap >= merge_threshold:
            break
        k = gaps.index(min_gap)
        n_a, n_b = len(clusters[k]), len(clusters[k + 1])
        merged_shots = clusters[k] + clusters[k + 1]
        merged_emo = _avg_emotion(cluster_emo[k], cluster_emo[k + 1], n_a, n_b)
        clusters = clusters[:k] + [merged_shots] + clusters[k + 2:]
        cluster_emo = cluster_emo[:k] + [merged_emo] + cluster_emo[k + 2:]

    out: list[SegmentScore] = []
    for i, shot_ids in enumerate(clusters):
        first = shots[shot_ids[0]]
        last = shots[shot_ids[-1]]
        out.append(SegmentScore(
            index=i, t_start=first.t_start, t_end=last.t_end,
            shot_ids=list(shot_ids),
            emotion=cluster_emo[i],
            status="tagged",
        ))
    return out
```

- [ ] **Step 4: 运行，确认通过（含原有用例）**

Run: `python -m pytest tests/test_sound_track_agent/test_segment_planner.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/segment_planner.py tests/test_sound_track_agent/test_segment_planner.py
git commit -m "feat(soundtrack): segment_planner 加 emotion_distance/_avg_emotion/cluster_by_emotion（D 情绪邻接合并核心）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `emotion_tagger.py` — 多帧情绪

**Files:**
- Modify: `sound_track_agent/emotion_tagger.py`
- Test: `tests/test_sound_track_agent/test_emotion_tagger.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_emotion_tagger.py`：

```python
from pathlib import Path
from unittest.mock import MagicMock

from sound_track_agent.emotion_tagger import tag_emotion_multi


def test_tag_emotion_multi_passes_image_list_to_provider():
    """多帧调用应把 list[Path] 完整传给 provider.generate。"""
    prov = MagicMock()
    prov.generate.return_value = (
        '{"labels":["tense","focused"],"valence":-0.3,"arousal":0.7,"intensity":0.6}')
    paths = [Path("/a.png"), Path("/b.png"), Path("/c.png")]
    emo = tag_emotion_multi(prov, paths, "末日废土")
    args, _kwargs = prov.generate.call_args
    images_arg = args[0]
    assert list(images_arg) == paths                          # 完整传入
    assert "末日废土" in args[2]                              # 风格融入 user prompt
    assert emo.labels == ["tense", "focused"]
    assert emo.valence == -0.3


def test_tag_emotion_multi_empty_returns_neutral():
    """空帧列表 → _NEUTRAL，不调 provider。"""
    prov = MagicMock()
    emo = tag_emotion_multi(prov, [], "any")
    prov.generate.assert_not_called()
    assert emo.labels == []
    assert emo.valence == 0.0


def test_tag_emotion_multi_parse_failure_degrades_to_neutral():
    """模型返非 JSON → 降级 _NEUTRAL。"""
    prov = MagicMock()
    prov.generate.return_value = "not a json"
    emo = tag_emotion_multi(prov, [Path("/a.png")], "x")
    assert emo.labels == []
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_emotion_tagger.py -q`
Expected: FAIL（`tag_emotion_multi` 不存在）

- [ ] **Step 3: 实现 `tag_emotion_multi`**

在 `sound_track_agent/emotion_tagger.py` 末尾追加：

```python
def tag_emotion_multi(provider, frame_paths: list[Path],
                      global_style: str) -> EmotionTag:
    """多帧同 prompt 测情绪。复用 _SYS/_USR_TMPL/_parse_emotion；
    provider.generate 原生接受 image list。

    空列表 → _NEUTRAL（不调 provider）。
    解析失败 → _NEUTRAL（不抛）。
    """
    if not frame_paths:
        return _NEUTRAL
    raw = provider.generate(list(frame_paths), _SYS,
                            _USR_TMPL.format(style=global_style))
    return _parse_emotion(raw)
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_emotion_tagger.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/emotion_tagger.py tests/test_sound_track_agent/test_emotion_tagger.py
git commit -m "feat(soundtrack): emotion_tagger 加 tag_emotion_multi（C 多帧情绪）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `mixdown.py` — 多时间点抽帧

**Files:**
- Modify: `sound_track_agent/mixdown.py`
- Test: `tests/test_sound_track_agent/test_mixdown.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_mixdown.py`：

```python
from sound_track_agent.mixdown import extract_frames_at


class _FakeResult:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stderr = b""


def test_extract_frames_at_one_command_per_time(tmp_path):
    """每个时间点一条 ffmpeg cmd，命令含 -ss <t> 与 -frames:v 1。"""
    captured = []
    def runner(cmd, capture_output=False):
        captured.append(list(cmd))
        # ffmpeg "成功"：写出对应 png
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"PNG")
        return _FakeResult(returncode=0)

    from pathlib import Path
    times = [0.5, 1.2, 2.0]
    paths = extract_frames_at(tmp_path / "ep.mp4", times,
                              tmp_path / "out", runner=runner)
    assert len(paths) == 3 == len(captured)
    for i, t in enumerate(times):
        joined = " ".join(captured[i])
        assert f"-ss {t:.3f}" in joined
        assert "-frames:v 1" in joined


def test_extract_frames_at_ffmpeg_failure_raises(tmp_path):
    def runner(cmd, capture_output=False):
        return _FakeResult(returncode=1)
    import pytest
    with pytest.raises(RuntimeError, match="ffmpeg"):
        extract_frames_at(tmp_path / "ep.mp4", [1.0],
                          tmp_path / "out", runner=runner)


def test_extract_frames_at_creates_out_dir(tmp_path):
    def runner(cmd, capture_output=False):
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"PNG")
        return _FakeResult(returncode=0)
    from pathlib import Path
    out_dir = tmp_path / "nested" / "deep"
    extract_frames_at(tmp_path / "ep.mp4", [0.5], out_dir, runner=runner)
    assert out_dir.exists()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_mixdown.py -q`
Expected: FAIL（`extract_frames_at` 不存在）

- [ ] **Step 3: 实现 `extract_frames_at`**

在 `sound_track_agent/mixdown.py` 末尾追加：

```python
def extract_frames_at(video_path, times: list[float], out_dir, *,
                      runner=subprocess.run) -> list[Path]:
    """对每个时间点 ffmpeg -ss t -frames:v 1 抽帧。

    返回 list[Path] 与 times 一一对应。任一帧抽帧失败抛 RuntimeError。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, t in enumerate(times):
        p = out_dir / f"f{i}_{float(t):.3f}.png"
        cmd = ["ffmpeg", "-y", "-ss", f"{float(t):.3f}", "-i", str(video_path),
               "-frames:v", "1", str(p)]
        result = runner(cmd, capture_output=True)
        if getattr(result, "returncode", 0) != 0 or not p.exists():
            raise RuntimeError(f"ffmpeg 抽帧失败 @ {float(t):.3f}s")
        paths.append(p)
    return paths
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_mixdown.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/mixdown.py tests/test_sound_track_agent/test_mixdown.py
git commit -m "feat(soundtrack): mixdown 加 extract_frames_at（per-shot 多时间点抽帧）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `refine.py` — 编排器

**Files:**
- Create: `sound_track_agent/refine.py`
- Test: `tests/test_sound_track_agent/test_refine.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_sound_track_agent/test_refine.py`：

```python
from pathlib import Path

from sound_track_agent.refine import refine_segments
from sound_track_agent.segment_planner import Shot
from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate,
)


def _session(tmp_path, *, candidates=None):
    seg = SegmentScore(index=0, t_start=0.0, t_end=2.0)
    if candidates is not None:
        seg.candidates = list(candidates)
    return ScoringSession(
        source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
        global_style="末日", frame_rate=24.0, segments=[seg])


def test_refine_replaces_segments_with_emotion_filled(tmp_path):
    sess = _session(tmp_path)
    # 注入：3 shots，前两个相似（合并），第三个不同
    fake_shots = [Shot(0, 0.0, 1.0), Shot(1, 1.0, 2.0), Shot(2, 2.0, 3.0)]
    emos = [
        EmotionTag(labels=["calm"], valence=0.0, arousal=0.2, intensity=0.4),
        EmotionTag(labels=["calm"], valence=0.0, arousal=0.2, intensity=0.4),
        EmotionTag(labels=["tense"], valence=-0.5, arousal=0.9, intensity=0.8),
    ]
    call_log = {"detect": 0, "extract": 0, "tag": 0}

    def fake_detect(v):
        call_log["detect"] += 1
        return fake_shots

    def fake_extract(v, times, out_dir):
        call_log["extract"] += 1
        # 返回伪 path 列表（refine 不会真打开文件）
        return [Path(out_dir) / f"f{i}.png" for i in range(len(times))]

    def fake_tag(frame_paths):
        # 把每次调用的次数当作 shot 索引
        i = call_log["tag"]
        call_log["tag"] += 1
        return emos[i]

    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="末日",
        max_segments=5, merge_threshold=0.25,
        detect=fake_detect, extract_frames=fake_extract, tag_fn=fake_tag)
    assert ok is True
    # 合并后应为 2 段：[shot0,shot1] 与 [shot2]
    assert len(sess.segments) == 2
    assert sess.segments[0].shot_ids == [0, 1]
    assert sess.segments[1].shot_ids == [2]
    assert all(s.emotion is not None for s in sess.segments)
    assert all(s.status == "tagged" for s in sess.segments)
    # 每 shot 都抽了一次帧 + 测了一次情绪
    assert call_log["detect"] == 1
    assert call_log["extract"] == 3
    assert call_log["tag"] == 3


def test_refine_safety_gate_when_session_has_candidates(tmp_path):
    """已有候选段 → 返回 False、不替换。"""
    sess = _session(tmp_path,
                    candidates=[BGMCandidate(path="/b.mp3", seed=1, prompt="t")])
    original_segs = list(sess.segments)
    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="末日",
        detect=lambda v: [Shot(0, 0.0, 1.0)],
        extract_frames=lambda *a, **k: [Path("/x.png")],
        tag_fn=lambda paths: EmotionTag())
    assert ok is False
    assert sess.segments == original_segs


def test_refine_no_shots_returns_false(tmp_path):
    sess = _session(tmp_path)
    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="x",
        detect=lambda v: [],
        extract_frames=lambda *a, **k: [],
        tag_fn=lambda paths: EmotionTag())
    assert ok is False


def test_refine_degrades_on_detect_exception(tmp_path):
    sess = _session(tmp_path)
    original_segs = list(sess.segments)
    def boom(v): raise RuntimeError("PySceneDetect down")
    ok = refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="x",
        detect=boom,
        extract_frames=lambda *a, **k: [],
        tag_fn=lambda paths: EmotionTag())
    assert ok is False
    assert sess.segments == original_segs


def test_refine_short_shot_uses_single_mid_frame(tmp_path):
    """shot 时长 < 0.1s → 只抽 mid 一帧。"""
    sess = _session(tmp_path)
    captured_times = []
    def fake_extract(v, times, out_dir):
        captured_times.append(list(times))
        return [Path(out_dir) / f"f{i}.png" for i in range(len(times))]
    refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="x",
        detect=lambda v: [Shot(0, 1.000, 1.050)],     # duration 0.05 < 0.1
        extract_frames=fake_extract,
        tag_fn=lambda paths: EmotionTag())
    assert len(captured_times) == 1
    assert len(captured_times[0]) == 1                 # 单帧
    # 该帧时间应为 mid
    assert abs(captured_times[0][0] - 1.025) < 1e-6
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_refine.py -q`
Expected: FAIL（`refine` 模块不存在）

- [ ] **Step 3: 实现 `refine.py`**

新建 `sound_track_agent/refine.py`：

```python
"""refine_segments: per-shot 多帧情绪 → 邻接聚合 → 替换 session.segments。

供 pipeline.Stages.refine_segments 注入。纯编排，全 I/O 注入。
失败降级返回 False，session 不动，pipeline 据此不置 segments_refined（可续跑重试）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.session import ScoringSession
from sound_track_agent.shot_detector import detect_shots
from sound_track_agent.segment_planner import cluster_by_emotion
from sound_track_agent.emotion_tagger import tag_emotion_multi
from sound_track_agent.mixdown import extract_frames_at

log = logging.getLogger(__name__)

# 极短 shot 阈值（秒）：duration < 此值时退化为单帧 mid
_MIN_MULTIFRAME_DUR = 0.1


def refine_segments(session: ScoringSession, *, video_path, work_dir,
                    provider, global_style: str,
                    max_segments: int = 5,
                    merge_threshold: float = 0.25,
                    detect: Optional[Callable] = None,
                    extract_frames: Optional[Callable] = None,
                    tag_fn: Optional[Callable] = None) -> bool:
    """1. 重检镜头 2. per-shot 抽 3 帧（极短 shot 退化单帧） 3. 测情绪
       4. 邻接聚合 5. 替换 session.segments。

    返回 True=成功重排（pipeline 据此置 segments_refined）；
    False=失败/跳过（不动 session，pipeline 不置 flag，下次续跑可重试）。

    安全护栏：session 已有任意候选 → 返回 False、不替换。

    所有 I/O 可注入；缺省走真实实现（shot_detector / mixdown / emotion_tagger）。
    """
    try:
        # 安全护栏：已有候选 → 不动（防止重排打散已生成 BGM）
        if any(getattr(s, "candidates", None) for s in session.segments):
            log.info("refine_segments 跳过：session 已有候选段")
            return False

        detect = detect or detect_shots
        extract_frames = extract_frames or extract_frames_at
        if tag_fn is None:
            tag_fn = lambda paths: tag_emotion_multi(provider, paths, global_style)
        work_dir = Path(work_dir)

        # 1. 重检镜头
        shots = detect(video_path)
        if not shots:
            log.warning("refine_segments: 未检出镜头，保留原 segments")
            return False

        # 2-3. per-shot 抽帧 + 测情绪
        emotions = []
        for i, shot in enumerate(shots):
            mid = (shot.t_start + shot.t_end) / 2.0
            duration = shot.t_end - shot.t_start
            if duration < _MIN_MULTIFRAME_DUR:
                times = [mid]
            else:
                times = [shot.t_start + 0.05, mid, shot.t_end - 0.05]
            shot_dir = work_dir / f"shot{i}"
            frame_paths = extract_frames(video_path, times, shot_dir)
            emotions.append(tag_fn(frame_paths))

        # 4. 邻接聚合
        new_segs = cluster_by_emotion(shots, emotions,
                                      max_segments=max_segments,
                                      merge_threshold=merge_threshold)

        # 5. 替换
        session.segments = new_segs
        return True
    except Exception:
        log.warning("refine_segments 降级，保留原始分段", exc_info=True)
        return False
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_refine.py -q`
Expected: PASS（5 个用例）

- [ ] **Step 5: 跑整套配乐 agent 测试，零回归**

Run: `python -m pytest tests/test_sound_track_agent/ -q`
Expected: PASS（全绿）

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/refine.py tests/test_sound_track_agent/test_refine.py
git commit -m "feat(soundtrack): 新增 refine 编排器（per-shot 多帧情绪 + 邻接合并）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `pipeline.py` — STAGE_ORDER + Stages.refine_segments + run() 新 block

**Files:**
- Modify: `sound_track_agent/pipeline.py`
- Test: `tests/test_sound_track_agent/test_pipeline.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_pipeline.py`：

```python
def test_refine_segments_stage_runs_on_first_advance():
    """注入的 refine_segments 返回 True → segments_refined=True。"""
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    calls = {"refine": 0}

    def fake_refine(s):
        calls["refine"] += 1
        return True

    fns = _base_stage_fns()
    stages = Stages(refine_segments=fake_refine, **fns)
    run_pipeline(sess, stages, stop_after="refine_segments")
    assert calls["refine"] == 1
    assert sess.segments_refined is True


def test_refine_segments_skipped_when_already_refined():
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    sess.segments_refined = True
    calls = {"refine": 0}
    fns = _base_stage_fns()
    stages = Stages(refine_segments=lambda s: (calls.__setitem__("refine", calls["refine"] + 1), True)[1],
                    **fns)
    run_pipeline(sess, stages, stop_after="refine_segments")
    assert calls["refine"] == 0                        # 已重排，跳过


def test_refine_failure_does_not_set_flag():
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    fns = _base_stage_fns()
    stages = Stages(refine_segments=lambda s: False, **fns)
    run_pipeline(sess, stages, stop_after="refine_segments")
    assert sess.segments_refined is False              # 失败不置


def test_refine_segments_default_none_no_op():
    """缺省 refine_segments=None → 现有流水线零回归。"""
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                                                 status="prompted")])
    fns = _base_stage_fns()
    stages = Stages(**fns)                             # 不设 refine_segments
    run_pipeline(sess, stages, stop_after="generate")
    # tag_emotion / compose_prompt / generate 仍然正常推进
    assert sess.segments[0].status == "generated"
```

> 注：`_base_stage_fns` 和 `run_pipeline` 应已在 test_pipeline.py 中（Phase 1 加的）。如缺，按上文同名定义补回（不在本任务范围）。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_pipeline.py -q`
Expected: FAIL（`Stages` 无 `refine_segments` 字段 / STAGE_ORDER 不含 `refine_segments`）

- [ ] **Step 3: 改 `STAGE_ORDER` + `Stages` + `run()`**

在 `sound_track_agent/pipeline.py`：

**3.1** 把 `STAGE_ORDER` 改为：

```python
STAGE_ORDER = ["refine_segments", "tag_emotion", "compose_prompt",
               "generate", "align", "mix"]
```

**3.2** 在 `Stages` dataclass 加可选字段（与 `generate_all` 同级）：

```python
    refine_segments: Optional[Callable[[ScoringSession], bool]] = None
```

**3.3** 在 `run()` 函数体最前面（首个 `if limit >= STAGE_ORDER.index("tag_emotion"):` 之前）插入新 block：

```python
    if limit >= STAGE_ORDER.index("refine_segments"):
        if (stages.refine_segments is not None
                and not getattr(sess, "segments_refined", False)):
            ok = stages.refine_segments(sess)
            if ok:
                sess.segments_refined = True
        _save(sess, session_path)
        if limit == STAGE_ORDER.index("refine_segments"):
            return None
```

- [ ] **Step 4: 运行，确认通过（含原有用例）**

Run: `python -m pytest tests/test_sound_track_agent/test_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/pipeline.py tests/test_sound_track_agent/test_pipeline.py
git commit -m "feat(soundtrack): pipeline 加可选 refine_segments stage（与 generate_all 同模式）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `stages_factory.py` — 装配 refine_segments

**Files:**
- Modify: `sound_track_agent/stages_factory.py`
- Test: `tests/test_sound_track_agent/test_stages_factory.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sound_track_agent/test_stages_factory.py`：

```python
def test_build_stages_wires_refine_segments_when_video_path_set(tmp_path):
    stages = build_stages(
        provider=None, client=None, workflow_id="wf", work_dir=tmp_path,
        global_style="末日", seeds=[1],
        frame_provider=lambda seg: tmp_path / "f.png",
        video_path=tmp_path / "ep.mp4",
        refine_max_segments=3, refine_merge_threshold=0.3)
    assert stages.refine_segments is not None


def test_build_stages_no_refine_when_video_path_none(tmp_path):
    """video_path=None 时不装配 refine（向后兼容老用例）。"""
    stages = build_stages(
        provider=None, client=None, workflow_id="wf", work_dir=tmp_path,
        global_style="末日", seeds=[1],
        frame_provider=lambda seg: tmp_path / "f.png")
    assert stages.refine_segments is None
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_stages_factory.py -q`
Expected: FAIL（`build_stages` 不接受 `video_path`/`refine_*` 关键字 / 无 `refine_segments` 字段）

- [ ] **Step 3: 改 `build_stages`**

在 `sound_track_agent/stages_factory.py`：

**3.1** 把 `build_stages` 签名加 3 个 kwarg（与 Phase 1/2 同模式，全可选）：

```python
def build_stages(*, provider, client, workflow_id: str,
                 work_dir, global_style: str, seeds: list,
                 frame_provider: Callable[[SegmentScore], Path],
                 mix_fn: Optional[Callable[[ScoringSession], str]] = None,
                 align_fn: Optional[Callable[[ScoringSession], None]] = None,
                 max_concurrency: int = 3,
                 score_fn: Optional[Callable] = None,
                 video_path=None,                            # 新
                 refine_max_segments: int = 5,                # 新
                 refine_merge_threshold: float = 0.25,        # 新
                 ) -> Stages:
```

**3.2** 在函数体内（其它闭包定义附近）加 `refine_segments` 闭包：

```python
    def refine_segments_fn(sess):
        from sound_track_agent import refine
        return refine.refine_segments(
            sess, video_path=video_path, work_dir=work_dir,
            provider=provider, global_style=global_style,
            max_segments=refine_max_segments,
            merge_threshold=refine_merge_threshold)
```

**3.3** 在 `return Stages(...)` 里加 `refine_segments`：

```python
    return Stages(
        tag_emotion=tag_emotion,
        compose_prompt=compose_prompt,
        generate=generate,
        align=align_fn or _noop_align,
        mix=mix_fn or _unconfigured_mix,
        generate_all=generate_all,
        refine_segments=(refine_segments_fn if video_path is not None else None),
    )
```

- [ ] **Step 4: 运行，确认通过（含原有用例）**

Run: `python -m pytest tests/test_sound_track_agent/test_stages_factory.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/stages_factory.py tests/test_sound_track_agent/test_stages_factory.py
git commit -m "feat(soundtrack): stages_factory 装配 refine_segments（注入 video_path 时启用）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `facade.py` — _build_real_stages 透传 + _wrap_progress 保留

**Files:**
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

- [ ] **Step 1: 写失败测试（关键：progress 包装后 refine 不丢，与 Phase 1 generate_all bug 同类）**

追加到 `tests/test_sound_track_agent/test_facade.py`：

```python
def test_advance_preserves_refine_segments_under_progress(tmp_path):
    """progress 包装（on_progress 非 None）后，refine_segments 钩子不能丢。"""
    from sound_track_agent import facade
    from sound_track_agent.pipeline import Stages
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, EmotionTag, BGMCandidate)

    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    calls = {"refine": 0}

    def refine_fn(s):
        calls["refine"] += 1
        return True

    stages = Stages(
        tag_emotion=lambda seg, s: EmotionTag(),
        compose_prompt=lambda seg, s: "p",
        generate=lambda seg, s: [BGMCandidate(path="/b.wav", seed=1, prompt="t")],
        align=lambda s: None, mix=lambda s: "/out.mp4",
        refine_segments=refine_fn)
    facade.advance(sess, tmp_path / "w", cfg=object(), workflow_id="wf",
                   stop_after="refine_segments", stages=stages,
                   on_progress=lambda m: None)
    assert calls["refine"] == 1                # progress 包装后仍触发 refine
    assert sess.segments_refined is True
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: FAIL（`_wrap_progress` 丢掉 `refine_segments` → progress 用例 calls["refine"]==0）

- [ ] **Step 3: 改 `_wrap_progress` 保留 refine_segments**

在 `sound_track_agent/facade.py` 的 `_wrap_progress` 末尾，把 `return Stages(...)` 加上 `refine_segments=`（其余字段保持现状）：

```python
    return Stages(
        tag_emotion=wrap(stages.tag_emotion, "情绪分析"),
        compose_prompt=wrap(stages.compose_prompt, "生成 prompt"),
        generate=wrap(stages.generate, "生成 BGM"),
        align=wrap_whole(stages.align, "对齐卡点"),
        mix=wrap_whole(stages.mix, "混音出片"),
        generate_all=(wrap_whole(stages.generate_all, "批量生成 BGM")
                      if stages.generate_all is not None else None),
        refine_segments=(wrap_whole(stages.refine_segments, "精排段落")
                         if stages.refine_segments is not None else None),
    )
```

- [ ] **Step 4: 改 `_build_real_stages` 透传 cfg 配置**

在 `sound_track_agent/facade.py` 的 `_build_real_stages` 末尾 `build_stages(...)` 调用里加 3 个 kwarg（`video_path` / `refine_max_segments` / `refine_merge_threshold`），其它参数保持现状：

```python
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
                       snap_window=float(getattr(cfg, "accent_snap_window", 0.6)),
                       max_stretch=float(getattr(cfg, "accent_max_stretch", 0.10))),
        max_concurrency=int(getattr(cfg, "soundtrack_max_concurrency", 3)),
        score_fn=score_fn,
        video_path=video_path,                                                    # 新
        refine_max_segments=int(getattr(cfg, "refine_max_segments", 5)),          # 新
        refine_merge_threshold=float(getattr(cfg, "refine_merge_threshold", 0.25)),  # 新
    )
```

> Phase 2 已加 `max_stretch=...`；本任务再追加 `video_path/refine_*` 三行。

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 跑整套配乐 agent + UI smoke，零回归**

Run: `python -m pytest tests/test_sound_track_agent tests/test_ui/test_segment_review_smoke.py tests/test_ui/test_accent_editor_smoke.py -q`
Expected: PASS（全绿）

- [ ] **Step 7: 提交**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(soundtrack): facade _wrap_progress 保留 refine_segments + _build_real_stages 透 cfg

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 收尾验证（全部任务完成后）

- [ ] **回归全测**

Run: `python -m pytest tests/test_sound_track_agent/ -q`
Expected: PASS

- [ ] **对照验收标准（spec §12）逐条确认**

1. refine_segments stage 注入后，advance 自动跑（首次）+ session.segments_refined 持久化 → `test_refine_segments_stage_runs_on_first_advance` + `test_advance_preserves_refine_segments_under_progress`
2. 续跑 skip refine（`segments_refined==True`）→ `test_refine_segments_skipped_when_already_refined`
3. cluster_by_emotion 相邻相似 shots 合并；总段数 ≤ max_segments → `test_cluster_*`
4. tag_emotion stage 检测 emotion 已填 → 跳过（refine 已置 status="tagged"）→ `test_refine_segments_default_none_no_op`（隐含）+ refine 用例
5. refine 内部失败 → 返回 False、session 不动、可续跑重试 → `test_refine_failure_does_not_set_flag` + `test_refine_degrades_on_detect_exception` + `test_refine_no_shots_returns_false`
6. _wrap_progress 保留 refine_segments hook → `test_advance_preserves_refine_segments_under_progress`
7. 安全护栏：session 已有候选时 refine 返回 False、不替换 → `test_refine_safety_gate_when_session_has_candidates`
