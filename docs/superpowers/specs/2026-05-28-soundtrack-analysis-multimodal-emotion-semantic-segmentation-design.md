# 配乐分析阶段优化（多帧情绪 + 情绪邻接分段）设计

> 日期：2026-05-28 ｜ 模块：`sound_track_agent/`（分析阶段）
> 来源：`sound_track_agent/优化升级调研.md` 的 Phase 3（特性 C 多帧 + D 情绪合并）
> 状态：设计已评审通过，待写实施计划

## 1. 背景与目标

分析阶段当前两大局限：

- **C 情绪标注信号弱**：`emotion_tagger.tag_emotion` 只抽段落**中点单帧**调 vision。一段可能跨多镜头、多情绪转折，单帧难以代表。
- **D 段落分法只看时长**：`segment_planner.plan_segments` 纯按累计时长贪心切 ~4 段，无视相邻镜头的情绪/语义相似度。换乐边界可能切在情绪连续处，反而把情绪突变并进同段。

**调研 P3 原本**包含「接入剧本台词文本」(C 子项) 与「按叙事/语义边界分段」(D 子项)，但项目侧 **`screenwriter_agent/` 尚为研究稿，无结构化 script 数据**。本期范围只做：

- **C 多帧情绪**：`emotion_tagger.tag_emotion_multi` 接受多帧（默认每 shot 的 start/mid/end 3 帧）同一 prompt 调用 vision；信号显著优于单帧。文本接入留待 host script_agent 落地。
- **D 情绪邻接合并**：新 pipeline stage `refine_segments` 重排——先 per-shot 多帧情绪 → 邻接距离合并相似段 → 替换 `session.segments`。后续 `tag_emotion` stage 因 emotion 已填自然跳过。

复用 Phase 1 已验证的「可选 stage 钩子 + 零回归回退」模式（`generate_all`）；新阶段同模式。

## 2. 范围

**本期内**：分析阶段 C+D；`session.segments_refined` 持久化；`Stages.refine_segments` 钩子；零回归回退。

**本期外**：C 接入台词文本（依赖 host script_agent，未来 Phase 4 候选）；D 按剧本场景切（同上）；refine 跨 session 缓存（YAGNI）；GUI 手动触发重排按钮（YAGNI）。

## 3. 架构与模块边界

沿用「纯逻辑 + 薄 IO + 注入」范式。**无新依赖**。

| 模块 | 增量 |
|---|---|
| `emotion_tagger.py` | + `tag_emotion_multi(provider, frame_paths: list[Path], global_style) -> EmotionTag` — 多帧同 prompt（复用 `_SYS`/`_USR_TMPL`/`_parse_emotion`） |
| `mixdown.py` | + `extract_frames_at(video_path, times: list[float], out_dir, *, runner) -> list[Path]` — 通用多时间点抽帧（ffmpeg `-ss t -frames:v 1`） |
| `segment_planner.py` | + `emotion_distance(a, b) -> float` 纯函数；+ `_avg_emotion(a, b, n_a, n_b) -> EmotionTag` 纯函数；+ `cluster_by_emotion(shots, emotions, *, max_segments, merge_threshold) -> list[SegmentScore]` |
| `refine.py`（**新文件**） | `refine_segments(session, *, video_path, work_dir, provider, global_style, max_segments, merge_threshold, detect=None, extract_frames=None, tag_fn=None) -> bool` — 编排器，全 I/O 注入 |
| `pipeline.py` | `STAGE_ORDER` 加 `refine_segments`；`Stages` 加可选字段；`run()` 加新 block |
| `stages_factory.py` | `build_stages` 加 `video_path`/`refine_max_segments`/`refine_merge_threshold`；装配 `refine_segments` 闭包 |
| `facade.py` | `_build_real_stages` 透 cfg + video_path；`_wrap_progress` 保留 `refine_segments`（吸取 Phase 1 教训） |
| `session.py` | + `segments_refined: bool = False` 字段 + 序列化 |

依赖方向：`refine → {segment_planner, emotion_tagger, mixdown, shot_detector, session}`；纯下行，无反向。

## 4. 数据结构变更

```python
# session.py
@dataclass
class ScoringSession:
    ...
    segments_refined: bool = False           # 新增；旧 json 缺 → False → 首次会触发
```

- `to_dict` 加 `"segments_refined": self.segments_refined`；`from_dict` 加 `segments_refined=bool(d.get("segments_refined", False))`。

```python
# pipeline.py
STAGE_ORDER = ["refine_segments", "tag_emotion", "compose_prompt",
               "generate", "align", "mix"]

@dataclass
class Stages:
    tag_emotion: ...; compose_prompt: ...; generate: ...; align: ...; mix: ...
    generate_all: Optional[Callable[[ScoringSession], None]] = None
    refine_segments: Optional[Callable[[ScoringSession], bool]] = None  # 新增
```

> `refine_segments` 返回 `bool`：True=成功重排，pipeline 据此置持久化 flag；False=失败/跳过，flag 不置（可续跑重试）。与 `generate_all` 的 `None`-return 语义不同。

## 5. C · 多帧情绪（`extract_frames_at` + `tag_emotion_multi`）

**抽帧策略**（per shot，由 `refine.refine_segments` 编排）：

```
mid = (shot.t_start + shot.t_end) / 2
if shot.duration < 0.1s:               # 极短 shot
    times = [mid]
else:
    times = [shot.t_start + 0.05, mid, shot.t_end - 0.05]
```

**`mixdown.extract_frames_at`**：

```python
def extract_frames_at(video_path, times: list[float], out_dir,
                      *, runner=subprocess.run) -> list[Path]:
    """对每个时间点 ffmpeg -ss t -frames:v 1 抽帧。失败抛 RuntimeError。"""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(times):
        p = out_dir / f"f{i}_{t:.3f}.png"
        cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video_path),
               "-frames:v", "1", str(p)]
        r = runner(cmd, capture_output=True)
        if getattr(r, "returncode", 0) != 0 or not p.exists():
            raise RuntimeError(f"ffmpeg 抽帧失败 @ {t:.3f}s")
        paths.append(p)
    return paths
```

**`emotion_tagger.tag_emotion_multi`**：

```python
def tag_emotion_multi(provider, frame_paths: list[Path],
                      global_style: str) -> EmotionTag:
    """多帧同 prompt 测情绪。复用现有 _SYS / _USR_TMPL；
    provider.generate 原生接受 image list。解析失败降级 _NEUTRAL，不抛。"""
    if not frame_paths:
        return _NEUTRAL
    raw = provider.generate(list(frame_paths), _SYS,
                            _USR_TMPL.format(style=global_style))
    return _parse_emotion(raw)
```

**成本**：典型 1 分钟 AI 剧 ~5 shots × 3 frames = 15 image-tokens／集（今天 ~4）。约 4×，doubao-seed-lite 单集数分钱级。`session.segments_refined` 持久化后续跑零额外成本。

## 6. D · 情绪邻接聚合（`cluster_by_emotion`）

**距离度量**（纯函数）：

```python
def emotion_distance(a: EmotionTag, b: EmotionTag) -> float:
    """欧氏距离 on (valence_norm, arousal, intensity)。值域 [0, sqrt(3)] ≈ [0, 1.732]。
    valence ∈[-1,1] 先映射到 [0,1] 与 arousal/intensity 同尺度。"""
    av = (a.valence + 1.0) / 2.0
    bv = (b.valence + 1.0) / 2.0
    d2 = ((av - bv) ** 2
          + (a.arousal - b.arousal) ** 2
          + (a.intensity - b.intensity) ** 2)
    return d2 ** 0.5
```

**邻接聚合**（agglomerative，单链接，**只允许相邻合并**保连续性）：

```python
def cluster_by_emotion(shots, emotions, *,
                       max_segments: int = 5,
                       merge_threshold: float = 0.25) -> list[SegmentScore]:
    """每 shot 起为 1 cluster，反复合并相邻距离最小的对，停止条件：
       len(clusters) ≤ max_segments AND min_adjacent_gap ≥ merge_threshold。
       max_segments 硬上限，merge_threshold 软上限（不够"相邻还有相似的"也得合）。"""
    if not shots: raise ValueError("cluster_by_emotion 需要至少 1 个镜头")
    if len(shots) != len(emotions): raise ValueError("shots/emotions 长度不一致")

    clusters = [[i] for i in range(len(shots))]
    cluster_emo = list(emotions)

    while len(clusters) > 1:
        gaps = [emotion_distance(cluster_emo[i], cluster_emo[i+1])
                for i in range(len(clusters) - 1)]
        min_gap = min(gaps)
        if len(clusters) <= max_segments and min_gap >= merge_threshold:
            break
        k = gaps.index(min_gap)
        n_a, n_b = len(clusters[k]), len(clusters[k+1])
        merged_shots = clusters[k] + clusters[k+1]
        merged_emo = _avg_emotion(cluster_emo[k], cluster_emo[k+1], n_a, n_b)
        clusters = clusters[:k] + [merged_shots] + clusters[k+2:]
        cluster_emo = cluster_emo[:k] + [merged_emo] + cluster_emo[k+2:]

    out = []
    for i, shot_ids in enumerate(clusters):
        first, last = shots[shot_ids[0]], shots[shot_ids[-1]]
        out.append(SegmentScore(
            index=i, t_start=first.t_start, t_end=last.t_end,
            shot_ids=shot_ids, emotion=cluster_emo[i], status="tagged"))
    return out


def _avg_emotion(a, b, n_a, n_b) -> EmotionTag:
    """按 shot 数加权平均三维数值；labels 取并集去重排序。"""
    total = n_a + n_b
    return EmotionTag(
        labels=sorted(set(a.labels) | set(b.labels)),
        valence=(a.valence * n_a + b.valence * n_b) / total,
        arousal=(a.arousal * n_a + b.arousal * n_b) / total,
        intensity=(a.intensity * n_a + b.intensity * n_b) / total,
    )
```

**默认参数**：`max_segments=5`（与现 `plan_segments` cap 一致），`merge_threshold=0.25`（直觉：valence 单维差 0.5 ≈ 距离 0.25 触发停合并；3 维总差 ≥ 0.25 才算"够不同"）。均可经 cfg 覆盖（§配置）。

**边界**：1 shot → 1 段；max_segments=1 → 全合一段；全相同情绪 → 合到 max_segments；merge_threshold=0 → 只看 max_segments。

## 7. `refine.py` 编排器

```python
"""refine_segments: per-shot 多帧情绪 → 邻接聚合 → 替换 session.segments。

供 pipeline.Stages.refine_segments 注入。纯编排，全 I/O 注入。失败降级返回 False。
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
_MIN_MULTIFRAME_DUR = 0.1


def refine_segments(session: ScoringSession, *, video_path, work_dir,
                    provider, global_style: str,
                    max_segments: int = 5,
                    merge_threshold: float = 0.25,
                    detect: Optional[Callable] = None,
                    extract_frames: Optional[Callable] = None,
                    tag_fn: Optional[Callable] = None) -> bool:
    """1. 重检镜头 2. per-shot 抽 3 帧 + 测情绪 3. 邻接聚合 4. 替换 segments。
    返回 True=成功；False=失败/跳过（不动 session，pipeline 不置 flag，下次可重试）。
    安全护栏：session 已有任意候选 → 返回 False、不替换。
    """
    try:
        if any(getattr(s, "candidates", None) for s in session.segments):
            log.info("refine_segments 跳过：session 已有候选段")
            return False

        detect = detect or detect_shots
        extract_frames = extract_frames or extract_frames_at
        if tag_fn is None:
            tag_fn = lambda paths: tag_emotion_multi(provider, paths, global_style)
        work_dir = Path(work_dir)

        shots = detect(video_path)
        if not shots:
            log.warning("refine_segments: 未检出镜头，保留原 segments")
            return False

        emotions = []
        for i, shot in enumerate(shots):
            mid = (shot.t_start + shot.t_end) / 2.0
            if shot.duration < _MIN_MULTIFRAME_DUR:
                times = [mid]
            else:
                times = [shot.t_start + 0.05, mid, shot.t_end - 0.05]
            shot_dir = work_dir / f"shot{i}"
            frame_paths = extract_frames(video_path, times, shot_dir)
            emotions.append(tag_fn(frame_paths))

        new_segs = cluster_by_emotion(shots, emotions,
                                      max_segments=max_segments,
                                      merge_threshold=merge_threshold)
        session.segments = new_segs
        return True
    except Exception:
        log.warning("refine_segments 降级，保留原始分段", exc_info=True)
        return False
```

**为什么顺序循环、不并发**：典型 5-8 shots × 1-3s 单 vision 调用 = 总 ~10-25s，对一次性预处理可接受；并发增加复杂度，doubao 单账户并发也有限。`session.segments_refined` 守住续跑后，首次成本可接受。**YAGNI**。

## 8. 接线（pipeline / stages_factory / facade）

### `pipeline.run()` 在最前加新 block

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

`tag_emotion` stage 已有 `if seg.status == "pending"` 守门——refine 置 `"tagged"` 的天然跳过，零额外改动。

### `stages_factory.build_stages` 加 3 个 kwarg

```python
def build_stages(*, ...,
                 video_path=None,                            # 新
                 refine_max_segments: int = 5,                # 新
                 refine_merge_threshold: float = 0.25,        # 新
                 ) -> Stages:
    def refine_segments_fn(sess):
        from sound_track_agent import refine
        return refine.refine_segments(
            sess, video_path=video_path, work_dir=work_dir,
            provider=provider, global_style=global_style,
            max_segments=refine_max_segments,
            merge_threshold=refine_merge_threshold)

    return Stages(
        ...,
        refine_segments=(refine_segments_fn if video_path is not None else None),
    )
```

`video_path is None` 时不装配 refine（向后兼容现有 test_stages_factory 用例）。

### `facade._build_real_stages` 透传

```python
return build_stages(
    ...,
    video_path=video_path,
    refine_max_segments=int(getattr(cfg, "refine_max_segments", 5)),
    refine_merge_threshold=float(getattr(cfg, "refine_merge_threshold", 0.25)),
)
```

### `facade._wrap_progress` 保留 refine_segments（**关键防回归**）

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

> 吸取 Phase 1 教训：可选 stage 必须在 `_wrap_progress` 显式 forward，否则 `on_progress` 非空时被默默丢掉。

### facade.advance / prepare_session / build_accent_preview
**无签名变更**。refine_segments 是内部链路扩展，对外契约不变。

## 9. 错误处理 / 续跑

| 失败点 | 行为 |
|---|---|
| `refine_segments` 内任何异常 | 返回 False，`segments_refined` 不置；下次 advance 重试 |
| `detect(video_path)` 返空 | 返回 False（保留原 segments） |
| `extract_frames_at` ffmpeg 失败 | 返回 False |
| `tag_emotion_multi` provider 失败 | 函数内已捕获、降级 `_NEUTRAL`，不抛；refine 继续，受影响 shot 用中性情绪聚合 |
| **安全护栏**：session 已有候选 | refine 返回 False、不替换，避免打散已生成 BGM |

**续跑**：`segments_refined=True` → 跳过 refine；False → 重试。首次成功后落盘到 session.json。

## 10. 配置项（cfg `getattr` 读，全可缺省）

| 字段 | 默认 | 用途 |
|---|---|---|
| `refine_max_segments` | `5` | D 段数硬上限（与现 plan_segments cap 一致） |
| `refine_merge_threshold` | `0.25` | D 邻接合并距离阈值（越小→段数越多） |

## 11. 测试策略（TDD，全注入 fake，无真 vision/ffmpeg）

- `segment_planner.emotion_distance`（纯）：同情绪=0；valence/arousal/intensity 各单维差；对立情绪 ≈ √3。
- `segment_planner._avg_emotion`（纯）：加权三维平均；labels 并集去重排序。
- `segment_planner.cluster_by_emotion`（纯，多个边界）：1 shot / 全相同 / 全不同（远超阈值）/ max_segments=3 优先合并最相似邻对 / max_segments=1 强制全合并 / merge_threshold=0 只看段数上限。
- `emotion_tagger.tag_emotion_multi`：mock provider，断言 generate 收到 image list + prompt 模板正确；空列表 → `_NEUTRAL`。
- `mixdown.extract_frames_at`（注入 runner）：断言每个时间点 ffmpeg cmd `-ss t -frames:v 1`；ffmpeg 失败 → RuntimeError。
- `refine.refine_segments`（注入 detect/extract_frames/tag_fn）：
  - 正常：segments 被替换、emotion 填、`status="tagged"`、返回 True；
  - 安全护栏：已有候选 → 返回 False、不替换；
  - 无 shots：返回 False；
  - 任一注入抛 → 返回 False，session 不动。
- `pipeline.run` 新 refine_segments stage：注入 fake refine 返回 True → `segments_refined=True` 置；返回 False → 不置；`segments_refined=True` 时跳过；`stop_after="refine_segments"` 提前返回。
- `stages_factory.build_stages`：传 `video_path` → 产 refine_segments；不传 → None（向后兼容）。
- `facade._wrap_progress`：refine_segments 在 progress 包装后**仍存在**（关键防回归）。

## 12. 验收标准

1. refine_segments stage 注入后，advance 自动跑（首次）+ session.`segments_refined` 持久化（True）。
2. 续跑跳过 refine（`segments_refined==True`）。
3. `cluster_by_emotion` 相邻相似 shots 合并；总段数 ≤ `max_segments`；非相邻不跨段。
4. `tag_emotion` stage 检测 emotion 已填 → 跳过（refine 已置 `status="tagged"`）。
5. refine 内部失败 → 返回 False、session 不动、可续跑重试。
6. `_wrap_progress` 保留 refine_segments hook（progress 包装下不丢，关键防回归）。
7. 安全护栏：session 已有候选时 refine 返回 False、不替换。
