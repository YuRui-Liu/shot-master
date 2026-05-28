# 配乐生成阶段优化（并行 + 缓存 + 候选打分）设计

> 日期：2026-05-28 ｜ 模块：`sound_track_agent/`（生成阶段）
> 来源：`sound_track_agent/优化升级调研.md` 的 Phase 1（特性 F + G + E）
> 状态：设计已评审通过，待写实施计划

## 1. 背景与目标

配乐智能体当前生成阶段全串行：`pipeline.run` 逐段调 `stages.generate`，`music_generator.generate_bgm` 内再逐 seed `create_task → 轮询(≤600s) → download`。约 5 段 × 2 seed ≈ 10 次顺序 RunningHub 往返，墙钟≈求和。另外：

- `regenerate_segment` 复用固定 seeds `1..N`，而 ACE-Step 近似按 seed 确定 → 实际拿不到新候选。
- `source_hash` 已算但未用于缓存，续跑/重生成重复计费。
- 候选无打分，`_chosen_bgm` 未选时默认 seed-0（无质量信号）。

本期目标（仅生成阶段，不动混音/分析）：

- **F**：(段×seed) 任务级并发，封顶并发数，大幅压缩出片墙钟时间。
- **G**：按内容寻址缓存生成结果，续跑/重生成免重复计费。
- **E**：候选自动打分排序并默认选最优（可人工覆盖）。

## 2. 范围

**本期内**：`sound_track_agent` 生成阶段（F+G+E）、`regenerate_segment` 改造、相关数据结构与配置。

**本期外**（后续 phase）：A 真·卡点 / B 复用对白轨（混音阶段）；C 多模态情绪 / D 语义分段（分析阶段）。「节拍-爆点匹配」打分留待 Phase 2（届时才有 accents）。

## 3. 架构与模块边界

沿用本仓「纯逻辑 + 薄 IO + 依赖注入」范式。采用「`Stages` 增可选 `generate_all` 钩子 + 逐段 `generate` 回退」方案，保住可注入/可测试结构。

**新增 3 模块**：

| 模块 | 职责 | 依赖 |
|---|---|---|
| `bgm_cache.py` (G) | 纯逻辑 + 薄 IO。`cache_key(...)`、`lookup(cache_dir,key)`、`store(cache_dir,key,src)`。内容寻址落 `work_dir/cache/bgm/<key>.mp3` | `hashlib`、`pathlib` |
| `scorer.py` (E) | 候选打分。核心数学纯函数（numpy 数组）；`score_candidate(path)→CandidateScore`、`rank`、`pick_best` | `soundfile`、`numpy`、`librosa`(可选) |
| `batch_generator.py` (F) | 编排：收集任务 → 查缓存 → 批量提交 → 并发轮询下载 → 写缓存 → 打分 → 回填。`generate_all(session)`、`generate_one(session, seg_index)` | `bgm_cache`、`scorer`、`music_generator`、注入 `client` |

**改动现有模块**：

- `pipeline.py`：`Stages` 加可选字段 `generate_all`；`run()` generate 阶段优先调它，缺省回退逐段 `generate`。
- `stages_factory.py` / `facade.py`：真实链路注入 `generate_all`（携 `client`/`cache_dir`/`max_concurrency`/`score_fn`/`compose`）；`regenerate_segment` 改用 `batch_generator.generate_one`（新种子）。
- `session.py`：`BGMCandidate` 加 `score`/`subscores`；`SegmentScore` 加 `next_seed`。
- `music_generator.py`：保留 `generate_bgm`（逐段回退路径 + 共享节点常量 `_node_info`/`NODE_*`），不删，零回归。

**依赖方向**：`batch_generator → {bgm_cache, scorer, music_generator, session}`；`scorer`/`bgm_cache` 不反向依赖编排层；`pipeline`/`facade` 不直接碰并发细节。

## 4. 数据结构变更

```python
# session.py
@dataclass
class BGMCandidate:
    path: str; seed: int; prompt: str
    score: float | None = None                       # 总分（None=未打分）
    subscores: dict = field(default_factory=dict)    # {health, headroom, beat}

@dataclass
class SegmentScore:
    ...
    next_seed: int = 1                                # 下次生成起始 seed 游标
```

- `to_dict/from_dict` 同步加字段；旧 `session.json` 缺字段走默认（`BGMCandidate(**c)` 兼容，新字段均有默认）。
- 种子语义：每段生成用 `[next_seed … next_seed+count-1]`，生成后 `next_seed += count`（无论成败）。初次 `next_seed=1`（与现状 `range(1,count+1)` 一致）；regenerate 自然取全新种子。

```python
# pipeline.py
@dataclass
class Stages:
    tag_emotion: ...; compose_prompt: ...; generate: ...; align: ...; mix: ...
    generate_all: Optional[Callable[[ScoringSession], None]] = None   # 新增、可选、置末

# run() generate 阶段：
if stages.generate_all is not None:
    stages.generate_all(sess)        # 自行回填 candidates/score/chosen/next_seed
else:
    for seg in prompted: seg.candidates = stages.generate(seg, sess); ...
# 之后：仅给「已有候选」的 prompted 段置 status="generated"（0 候选段留 prompted 待续跑）
_save(sess, session_path)
```

## 5. F · 批量并发生成（`generate_all`）

数据流（一次处理所有 `prompted` 段）：

1. **收集任务**：每段 `compose_acestep_inputs(style, emotion, dur)` → `(tags,bpm,dur)`；seeds=`[next_seed … +count-1]`；展开 job `{seg_index, seed, tags, bpm, dur}`。
2. **查缓存**：每 job 算 `cache_key`，命中 → 以缓存文件为候选，**不提交**。
3. **并发执行未命中**：`ThreadPoolExecutor(max_workers=cap)`，每 worker 跑完整生命周期 `create_task → 轮询 → download → cache.store`。轮询沿用 `LTXTaskHandle` 风格：瞬时网络错连续 3 次才判失败。
4. **失败隔离**：`as_completed` 收集；单 job 失败（FAILED/超时/网络）记录并丢弃该 seed 候选，不连累其余。
5. **回填 + 打分**：每段成功候选按 seed 排序填入 `seg.candidates` → `scorer` 打分 → `pick_best` 写 `chosen_candidate`；`next_seed += count`。
6. **并发模型理由**：RunningHub 有账户级并发配额；一次性全 create 超配额者只在服务端排队，徒增取消/失败处理复杂度。封顶 `cap` 的 worker 池在配额内取得等价或更优墙钟收益，且天然不超配额。
7. **进度**：每完成一 job 回调 `on_progress("生成 BGM 段X (k/total)…")`。

`generate_one(session, seg_index)`：单段版，供 regenerate 复用（同上 2-5，只处理一段）。

## 6. G · 缓存（`bgm_cache.py`）

- `cache_key = sha256(f"{workflow_id}|{tags}|{bpm}|{duration:.3f}|{seed}").hexdigest()[:16]`（`duration` 定精度，避免浮点 repr 漂移）。
- 内容寻址落 `work_dir/cache/bgm/<key>.mp3`；**候选 `path` 直接指向缓存文件**（单一真相、不重复存储）；下载直接写入缓存目录；命中零下载、零 `create_task`。
- 作用域**按 work_dir**（续跑/regenerate 同集复用）；跨集不追求。
- 失效：内容寻址，输入变 key 变，无显式失效。

## 7. E · 打分（`scorer.py`）

`score_candidate(path) -> CandidateScore(total, health, headroom, beat)`：

- **health** ∈[0,1]：惩罚削波（|x|≥0.999 占比）、近静音（RMS 过低）、过短（< 期望时长×0.5）、NaN/inf。作软门——health 极低压到排序底部。
- **headroom** ∈[0,1]：语音频段（~300–3400Hz）能量占比，越低分越高（给人声让路）。自包含，不依赖对白轨。
- **beat** ∈[0,1]：librosa onset/节拍强度，衡量「有清晰稳定节拍」。librosa 不可用 → 中性 0.5。
- **total** = 加权和，默认权重 `{health:0.5, headroom:0.3, beat:0.2}`（可配 `soundtrack_score_weights`）。`rank`/`pick_best` → 写 `chosen_candidate`。
- **降级**：soundfile/读取失败 → 该候选 `score=None`；排序中 None 视为中性，退回 seed 顺序、chosen 默认 0，不中断。

## 8. `regenerate_segment` 改造

- 改用 `batch_generator.generate_one(session, seg_index, ...)`：取该段 `next_seed` 窗口的**全新种子** → 清空旧候选 → 生成 → 打分 → `pick_best` 写 `chosen` → `next_seed += count` → 落盘。
- 新种子 → 新 cache_key → 必然 miss → 真出新音乐（符合「换候选」语义）。

## 9. 错误 / 续跑语义

- **单段部分失败**（≥1 候选）：照常 `status="generated"`，打分用现有候选。
- **单段全失败**（0 候选）：保持 `prompted`，`generate_all` **不抛异常**，正常返回让 `pipeline.run` 落盘，保住其它段进度。
- **续跑**：再次 `advance(stop_after="generate")` 只重跑仍 `prompted` 的失败段（已成功段幂等跳过），用推进后新种子重试 → 只补失败、不重复计费。
- 失败段经 `on_progress` 告警 + session 状态暴露给 UI；带未完成段强推到 mix，`_chosen_bgm` 仍对空候选段报错（需先补 generate），属预期。

## 10. 配置项（cfg，`getattr` 读，全可缺省）

| 字段 | 默认 | 用途 |
|---|---|---|
| `soundtrack_max_concurrency` | `3` | 并发上限（RunningHub 配额保守） |
| `soundtrack_score_weights` | `{health:.5, headroom:.3, beat:.2}` | 打分权重 |
| `seeds_count`（沿用参数） | `2` | 每段候选数 |

## 11. 测试策略（TDD，注入 fake，不碰真 RunningHub/网络）

- `bgm_cache`：key 确定性/稳定性、命中跳过、store 往返。纯。
- `scorer`：合成信号（削波方波/静音/纯正弦/节拍+噪声）断言子项排序、`pick_best`、降级（None）。
- `batch_generator`：注入 fake client（create/query/download 确定性）+ fake sleep + fake score_fn，断言——缓存命中跳过 create、并发不超 cap、失败隔离、`next_seed` 推进、候选回填+打分+chosen、全失败段留 `prompted`。
- `pipeline`：`generate_all` 钩子路径与逐段回退路径均正确；回退零回归。
- `facade`：`_build_real_stages` 接上 `generate_all`；`regenerate_segment` 用新种子（next_seed 推进、候选替换）。
- `session`：新字段往返；缺字段旧 json 走默认。

## 12. 验收标准

1. 多段多 seed 生成并发执行，墙钟显著低于串行；并发数不超 `soundtrack_max_concurrency`。
2. 续跑/regenerate 命中缓存时不再 `create_task`（可由 fake client 调用计数断言）。
3. regenerate 产出与上一轮不同的候选（新种子）。
4. 生成后 `chosen_candidate` 指向打分最优候选；坏生成（削波/静音）不被选为默认。
5. 单段失败不影响其它段；失败段续跑可补齐。
6. 逐段回退路径与现有测试全绿（零回归）。
