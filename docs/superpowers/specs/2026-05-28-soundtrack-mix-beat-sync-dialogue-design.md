# 配乐 Mix 阶段优化（真·卡点 + 复用对白轨）设计

> 日期：2026-05-28 ｜ 模块：`sound_track_agent/`（mix 阶段）
> 来源：`sound_track_agent/优化升级调研.md` 的 Phase 2（特性 A + B）
> 状态：设计已评审通过，待写实施计划

## 1. 背景与目标

混音阶段当前两大痛点：

- **「卡点」名不副实**：`beat_aligner.extract_beats/align_accents` 已实现/单测但**生产链路零调用**；实际「卡点」只做两件事——段缝吸附到大爆点（`clip_targets`）+ 爆点处音量下压（`apply_pump` 泵感）。**音乐自身的重拍从不参与对齐**，爆点落在哪个音符随机；泵感本质是音量塌陷而非节奏命中，与项目核心「anti-PPT」诉求相悖。

- **Demucs 在做无用功**：项目本身是 AI 配音工具，`providers/tts_submit.py` 已逐句下载干净 TTS 配音（落 `cfg.dub_output_dir/dub/dub_<ts>.flac`），`VideoTask.timeline["audios"]` 也已记录每段对白的时间定位。但 `audio_mixer.separate_vocals` 仍用 ~300MB 的 Demucs 模型从成片**盲分离**对白——等于把自己合成的干净对白再花算力分离一遍。

本期目标（仅 mix 阶段，不动生成/分析）：

- **A — 真·卡点**：接入 `extract_beats`；为每个大爆点找最近重拍 + 局部时间拉伸（±10% 上限），让音乐下拍**毫秒级**落在爆点；成功对齐的爆点不再走音量下压（泵感降级处理未对齐者）。
- **B — 复用对白轨**：facade 接收 `dialogue_segments` 列表（带时间定位），内部装配成连续对白 wav 后直接 ducking；现有 Demucs 路径保留为缺省回退（零回归）。

## 2. 范围

**本期内**：`sound_track_agent` mix 阶段（A+B）+ session 持久化 + facade 入参 + 预览路径同步。

**本期外**（后续 phase）：Phase 3 C 多模态情绪 / D 语义分段；调用方侧（GUI）从 `VideoTask.timeline["audios"]` 派生 `dialogue_segments` 的具体接线由相应 GUI 设计承接。

## 3. 架构与模块边界

沿用「纯逻辑 + 薄 IO + 依赖注入」范式。**无新文件、无新依赖**（librosa 已是 Phase 1 依赖；`librosa.effects.time_stretch` 直接可用）。所有改动以**模块内增量**形式分布到现有聚焦模块：

| 模块 | 增量 |
|---|---|
| `beat_aligner.py` | + `align_beats_to_accents(bgm_path, accents, *, max_stretch=0.10, big_threshold=0.7) → (stretched_path, aligned_indices: set[int])` |
| `accent_mixer.py` | `apply_pump` / `build_pump_envelope` 加 `skip_indices: set[int] = frozenset()` 入参 |
| `audio_mixer.py` | + `assemble_dialogue_track(segments, total_duration, out_path) → Path` |
| `mixdown.py` | `assemble_and_mix` 编排：assemble_bgm → align_beats → apply_pump(skip) → assemble_dialogue OR separate_vocals → duck_and_mix |
| `session.py` | + `DialogueSegment` dataclass、`ScoringSession.dialogue_segments` 字段 |
| `facade.py` | `prepare_session`/`advance` 加可选 `dialogue_segments` 入参；`build_accent_preview` 同步走 align+pump 流程 |

**依赖方向**：`mixdown → {bgm_assembler, beat_aligner, accent_mixer, audio_mixer, session}`；新增公开 API 不反向依赖编排层。

## 4. 数据结构变更

```python
# session.py
@dataclass
class DialogueSegment:
    audio_path: str           # 绝对路径（同 source_mp4 处理）
    t_start: float            # 秒
    duration: float           # 秒

    def to_dict(self) -> dict:
        return {"audio_path": self.audio_path,
                "t_start": self.t_start, "duration": self.duration}

    @classmethod
    def from_dict(cls, d: dict) -> "DialogueSegment":
        return cls(audio_path=str(d["audio_path"]),
                   t_start=float(d["t_start"]),
                   duration=float(d["duration"]))


@dataclass
class ScoringSession:
    ...
    dialogue_segments: list[DialogueSegment] = field(default_factory=list)
```

- `to_dict/from_dict` 同步加字段；旧 `session.json` 缺 `dialogue_segments` 时默认空列表 → 走 Demucs 回退（**零回归**）。
- caller 侧（GUI）从 `VideoTask.timeline["audios"]` 派生：`t_start = start_frame/fps`、`duration = length_frames/fps`，`audio_path` 原样。

```python
# facade.py
def prepare_session(mp4, style, work_dir, *, dialogue_segments=None,
                    detect=detect_shots) -> ScoringSession:
    """新建 session；dialogue_segments 直接落入 session.dialogue_segments。"""

def advance(session, work_dir, *, cfg, workflow_id, seeds_count=2,
            stop_after="mix", on_progress=None, stages=None,
            dialogue_segments=None) -> ScoringSession:
    """若非空则覆盖 session.dialogue_segments（用户可后续追加/替换），否则不动。"""
```

签名向后兼容（默认 None / 不动 session）。

## 5. A · 锚点式拉伸算法（`align_beats_to_accents`）

**输入**：BGM wav 路径、`accents: list[AccentPoint]`、`max_stretch`（默认 `0.10`，因子限在 `[0.9, 1.1]`）、`big_threshold`（沿用 `0.7`）。

**算法**（伪码）：

```
beats = extract_beats(bgm_path)                                  # librosa.beat_track
total_dur = duration_of(bgm_path)                                # soundfile: n_samples / sr
big_accents = sorted((i, a.t) for i, a in enumerate(accents)
                     if a.intensity >= big_threshold)

aligned = []   # list of (accent_idx, accent_t, music_beat_t)
used_beats = set()
for (i, t) in big_accents:
    candidates = [b for b in beats if b <= t and b not in used_beats]
    if not candidates: continue
    b = max(candidates)                                          # 最近的前向 beat
    prev_t = aligned[-1][1] if aligned else 0.0
    prev_b = aligned[-1][2] if aligned else 0.0
    if (b - prev_b) <= 0: continue                               # 防退化
    factor = (t - prev_t) / (b - prev_b)
    if abs(factor - 1.0) <= max_stretch:
        aligned.append((i, t, b)); used_beats.add(b)
    # 否则跳过——该爆点交还原泵感处理

# 计划局部拉伸：把每段 [prev_b, cur_b] → 目标长度 (cur_t - prev_t)
chunks = []
prev_t, prev_b = 0.0, 0.0
for (_, t, b) in aligned:
    chunks.append(("stretch", prev_b, b, t - prev_t))            # 拉伸段
    prev_t, prev_b = t, b
chunks.append(("tail", prev_b, total_dur, total_dur - prev_t))    # 末段原速

# 用 librosa.effects.time_stretch 逐段做：读 src → stretch → 拼接 → 写 stretched_path
return stretched_path, set(idx for (idx, _, _) in aligned)
```

**关键决策**：

- **只向前找 beat**（`b ≤ t`）—— 简化拉伸方向（永远把过去的音乐拉到当前爆点），避免「未来 beat 反向压缩」的边界。
- **±10% 拉伸上限**：超过则放弃该爆点，交泵感兜底；librosa 相位 vocoder 在小因子下伪影不可闻。
- **逐段拼接**而非整曲拉伸：保证未对齐区域原速、原相位，只在「上一锚点 → 当前爆点」之间微调。
- **末段不拉伸**：保留原曲尾感。
- **立体声**：mono 直接拉；stereo 按 channel 分别同 factor 拉伸后合回，保持相位锁同。
- **失败降级**：librosa 不可用 / 拉伸抛异常 → 返回 `(原 bgm_path, frozenset())`，全部交给泵感（=今天的行为，零回归）。

**返回值** `aligned_indices` 是「这些爆点的音乐重拍已对准」的下标集合，下游 `apply_pump(skip_indices=...)` 据此跳过对应位置的音量下压。

## 6. B · 对白装配 + Demucs 回退（`assemble_dialogue_track`）

**接口**：`assemble_dialogue_track(segments: list[DialogueSegment], total_duration: float, out_path: Path, *, runner=subprocess.run) → Path`

**ffmpeg 命令骨架**：

```
ffmpeg -y \
  -f lavfi -t {total_duration} -i anullsrc=channel_layout=stereo:sample_rate=44100 \
  -i seg1.flac -i seg2.flac ... \
  -filter_complex "
    [1:a]adelay={t1_ms}:all=1[a1];
    [2:a]adelay={t2_ms}:all=1[a2];
    ...
    [0:a][a1][a2]...amix=inputs={N+1}:duration=first:normalize=0[out]
  " \
  -map [out] -t {total_duration} -c:a pcm_s16le out_path.wav
```

- 静音底轨保证总时长精确（首尾空白填白）。
- `adelay` 单位 ms；`all=1` 避免立体声错位。
- `amix normalize=0` 防止自动均化把音量莫名拉低；重叠（罕见）由 amix 自然叠加。
- 格式无关：ffmpeg 自动解码 flac/wav/mp3。
- 失败：`runner.returncode != 0` → `RuntimeError`（与 audio_mixer 其它函数一致）。

**`mixdown.assemble_and_mix` 分支**：

```python
if sess.dialogue_segments:
    vocals = assemble_dialogue_track(
        sess.dialogue_segments,
        total_duration=_video_duration(video_path),
        out_path=work_dir / "dialogue_track.wav")
else:
    src_audio = extract_audio(video_path, work_dir / "src_audio.wav")
    vocals, _rest = separate(src_audio, work_dir / "sep")    # Demucs 回退
```

> 装配失败**不**回退 Demucs——用户已显式提供 dialogue，回退会掩盖问题（缺文件 / 格式坏 / 路径漂移）。直接 raise，调用方修复后续跑。

## 7. 泵感跳过对齐爆点 + 预览同步

**`accent_mixer.apply_pump` / `build_pump_envelope`** 加 `skip_indices: set[int] = frozenset()` 入参：

```python
def build_pump_envelope(n_samples, sr, accents, *, strength,
                        attack=0.012, release=0.35,
                        skip_indices: set[int] = frozenset()):
    env = np.ones(...)
    for i, ap in enumerate(accents):
        if i in skip_indices:
            continue          # 该爆点已被重拍命中，不下压
        # 其余逻辑不变
    return env
```

**`facade.build_accent_preview`** 与 `mixdown.assemble_and_mix` 共用同一流程：

```python
if sess.accent_mix_enabled and accents:
    targets = clip_targets(...)
    raw = assemble_bgm(..., clip_durations=targets, ...)
    stretched, aligned = align_beats_to_accents(
        raw, accents,
        max_stretch=float(getattr(cfg, "accent_max_stretch", 0.10)))
    out = apply_pump(stretched, out, accents,
                     strength=float(sess.pump_strength),
                     skip_indices=aligned)
else:
    out = assemble_bgm(...)
```

单一可信源：试听到的卡点效果与最终出片一致。

## 8. 错误处理 / 续跑语义

| 失败点 | 行为 |
|---|---|
| `align_beats_to_accents`：librosa 不可用 / beats 空 / time_stretch 异常 | 返回 `(原 bgm_path, frozenset())`；下游全交泵感（=今天） |
| `assemble_dialogue_track`：ffmpeg 失败 / 文件缺失 | raise `RuntimeError`，不静默回退 Demucs |
| 拉伸因子超 ±10% | 跳过该爆点（aligned_set 不含它），落到泵感分支 |
| `dialogue_segments` 路径在持久化后被移动 | ffmpeg 报错 → `RuntimeError`；session 字段保留以便 GUI 提示重新指定 |

**续跑**：`dialogue_segments` 持久化到 `session.json`；再次 `advance(stop_after="mix")` 直接读 session 字段，不需重供。

## 9. 配置项（cfg，`getattr` 读，全可缺省）

| 字段 | 默认 | 用途 |
|---|---|---|
| `accent_max_stretch` | `0.10` | A 拉伸因子上限（±10%） |
| `accent_big_threshold` | `0.7`（沿用） | 大爆点阈值（同 clip_targets） |
| `accent_snap_window` | `0.6`（沿用） | 段切吸附窗（同 clip_targets） |

## 10. 测试策略（TDD，注入 fake，不碰真 ffmpeg / Demucs / librosa）

- `beat_aligner.align_beats_to_accents`（注入 `_extract_beats`/`_time_stretch` fake）：
  - 边界：无大爆点 → `(input, ∅)`；无 beats → `(input, ∅)`；全部对齐；全部超 ±10% → `(input, ∅)`；混合（部分对齐）；
  - chunk planning 正确性（哪些 accent 入 aligned，对应 factor 是否在阈值内）；
  - 立体声分通道一致性（拉伸因子相同）。
- `accent_mixer.build_pump_envelope` `skip_indices`：合成 envelope，断言被跳过位置无下压。
- `audio_mixer.assemble_dialogue_track`（注入 `runner=fake`）：
  - 边界：空段列表 → 仅静音底轨；单段；多段；重叠段；
  - 断言 ffmpeg 命令含正确 `adelay={t_ms}:all=1` 与 `amix=inputs=N+1`。
- `mixdown.assemble_and_mix`（注入 fake separate / fake align / fake assemble_dialogue）：
  - dialogue_segments 非空 → separate 不被调用；
  - dialogue_segments 空 → 仍调 separate（零回归）；
  - aligned_set 透传到 apply_pump。
- `session`：DialogueSegment 往返；缺字段默认空列表。
- `facade.build_accent_preview`：注入 fake，断言走 align+pump 同一路径。

## 11. 验收标准

1. 大爆点 + 节拍存在 → `aligned_indices` 非空（合成测试）。
2. `apply_pump(skip_indices=aligned)` 在跳过位置零下压（包络断言）。
3. 提供 `dialogue_segments` → Demucs `separate` 调用计数 = 0。
4. 缺 `dialogue_segments` → Demucs 路径正常（零回归）。
5. session 往返 `dialogue_segments` 字段（含旧 json 缺字段降级）。
6. `build_accent_preview` 与 `assemble_and_mix` 共用同一 align+pump 流程（统一测试驱动）。
