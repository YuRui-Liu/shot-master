# 漫剧后期配乐智能体 sound_track_agent · 设计

> 日期：2026-05-25
> 形态：drama-shot-master 项目内的相对独立 agent 包 `sound_track_agent/`
> 目标场景：漫剧/短剧 1–2min 剧集成片的后期自动配乐

---

## 1. 目标与背景

当前痛点：漫剧配乐**太慢**，集中在两处——**找曲/选曲 + 风格不统一**、**卡点/转场同步**。

本 agent 面向**成片 MP4 后期配乐**：输入一集已拼接好的成片（对白已压在混合音轨里），半自动产出配乐成片。核心策略是**从成片恢复时间结构 + 已知总风格锁基调 + 分段生成 BGM + 爆点半自动卡点 + 人声分离避让对白**。

落地为 `sound_track_agent/` 独立包：自带 CLI 管线可单独/批量运行，同时暴露 API 允许被 drama-shot-master 导演台调用、复用其支持（`providers/factory` 的 gemini provider、RunningHub client、config）。

## 2. 需求与边界（已确认）

| 维度 | 结论 |
|---|---|
| 载体 | 独立包 `sound_track_agent/`，CLI + API；可被导演台调用并复用其 provider/config |
| 输入 | 成片 MP4（多段拼接，对白已混入音轨），1–2min/集，剧集（批量是潜在刚需） |
| 元数据 | **总风格已知**；精确分段**对不上成片** → 需从 MP4 恢复时间结构 |
| 音频 | 对白与原声混在一条轨 → 需 Demucs 人声分离 + sidechain ducking + loudnorm |
| 自动化 | 半自动：关键节点（情绪 / prompt / 候选 BGM / 卡点）人工确认 |
| 交互 | 先 CLI + 候选导出回填；API 设计成可被 GUI 调用，导演台壳后续再加 |
| 技术栈 | 务实混合：切分/分离/混音本地开源 + 情绪理解/prompt 走豆包 `doubao-seed-2-0-lite-260215`（参照 refine 机制）+ BGM 用 ACE-Step |
| 方案 | 方案 A 完整版：分段生成 + 段落转场对齐 + 爆点帧级半自动卡点 |
| 商用 | 全链路 MIT/Apache 开源 + 自有 API；ACE-Step（MIT）可商用 |

## 3. 非目标（YAGNI）

明确**不做**（理由见调研：重、不稳、或与本场景不符）：

- ❌ V2M 端到端"看视频直接生成音乐"（VidMuse/MuVi/V2Meow：未开源训练、10–30s、CC-BY-NC）
- ❌ 重型 MLLM 视频理解（总风格已知，gemini 只需补**粗情绪**，不需从零理解剧情）
- ❌ CLAP 曲库检索（本场景是**生成**不是找曲）
- ❌ 多 agent 反思/自动打分编排（半自动人工确认已覆盖质量把关）
- ❌ 全自动直出（用户明确要关键节点人工确认）

## 4. 架构

### 4.1 组件划分（单一职责，独立可测）

| 模块 | 职责 | 依赖 |
|---|---|---|
| `shot_detector` | MP4 → 镜头切点列表 | PySceneDetect（TransNetV2 可选增强） |
| `segment_planner` | 镜头切点 → 聚合成 3–5 个**叙事段落**（铺垫/冲突/高潮/收尾） | 纯逻辑（时长 + 相邻相似度规则） |
| `emotion_tagger` | 段落代表帧 → 情绪标签（valence/arousal + 离散标签） | 豆包 `doubao-seed-2-0-lite-260215`（vision，参照 refine 的独立 provider 配置） |
| `prompt_composer` | 总风格 + 段落情绪 + 时长 → ACE-Step 音乐 prompt | 同上豆包模型 + 模板 |
| `music_generator` | prompt → BGM-only 音频（每段多候选） | ACE-Step（本地 / ComfyUI 节点） |
| `accent_detector` | 光流峰值 → 爆点候选时间戳 | OpenCV 光流 + librosa |
| `beat_aligner` | 段落边界/音乐重音 ↔ 转场/爆点对齐（time-stretch 微调） | librosa + pyrubberband |
| `audio_mixer` | Demucs 分离对白 → ducking → loudnorm → 合成出片 | Demucs + FFmpeg |
| `session` | 贯穿全程的 `ScoringSession` 状态对象，可持久化 | 纯数据 |
| `pipeline` | 编排器：串各阶段，在关键节点暂停等人工确认 | 以上全部 |
| `cli` / `api` | 命令行入口 + 可被导演台调用的接口 | pipeline |

### 4.2 数据流

```
成片 MP4
 → shot_detector      → ShotList（切点时间戳）
 → segment_planner    → SegmentPlan（3–5 叙事段，各带 start/end/时长）
 → emotion_tagger     → [EmotionTag × N]            [人工可改]
 → prompt_composer    → [MusicPrompt × N]           [人工可改]
 → music_generator    → [BGMCandidate × N × k]      [人工选优/重生成]
 → accent_detector    → AccentPoints（爆点候选）     [人工增删/微调]
 → beat_aligner       → AlignedTrack（对齐后整轨）
 → audio_mixer        → MixedVideo（配乐成片）
        ↑________ ScoringSession 全程记录、可持久化、可单段重跑 ________↑
```

## 5. 关键数据结构：ScoringSession

支撑"半自动不返工"的核心。每阶段产物落盘（JSON 元数据 + 音频/帧文件），可中断后从任意阶段继续，或只重跑某一段。

```
ScoringSession
  source_mp4: Path
  source_hash: str                  # 缓存键
  global_style: str                 # 已知总风格
  frame_rate: float
  segments: [
    SegmentScore {
      index, t_start, t_end, duration
      shot_ids: [...]               # 聚合自哪些镜头
      emotion: EmotionTag           # {valence, arousal, labels[]}  [可改]
      music_prompt: str             # ACE-Step prompt              [可改]
      candidates: [BGMCandidate{path, seed, prompt}]   # 多候选
      chosen_candidate: idx | None  # 人工选优                      [可改]
      status: pending|tagged|prompted|generated|chosen|aligned
    }, ...
  ]
  accent_points: [{t, intensity, confirmed: bool}]    # 爆点          [可改]
  output: Path | None
```

持久化路径：`<work_dir>/<source_hash>/session.json` + 同目录音频/帧产物。

## 6. 半自动交互

**4 个人工确认点**（每个都可"接受默认 / 修改 / 重跑"）：

1. **情绪标签**（emotion_tagger 后）：豆包给的每段标签可改
2. **音乐 prompt**（prompt_composer 后）：可改文本
3. **候选 BGM 选优**（music_generator 后）：每段 2–4 候选，听后选一；全不满意 → 改 prompt 重生成
4. **卡点**（accent_detector 后）：爆点候选时间戳可增删/微调

**交互实现（先 CLI + 回填）**：
- agent 跑到确认点暂停，把候选音频 / 情绪 / prompt **导出到工作目录**
- 用户用外部播放器听候选音频，在 CLI 提示 / 回填文件里写选择与修改
- `pipeline` 读回填后继续

**API 设计**：每个确认点暴露为 `pause → 返回待确认数据 → 接收人工输入 → resume` 的接口，使未来导演台 GUI 壳可直接驱动同一管线。

## 7. 音频链与质量风险

```
成片混轨 → Demucs 分离 → vocals(对白，保留) + accompaniment(原声/旧BGM，丢弃)
新 BGM(AlignedTrack) + vocals →
  FFmpeg sidechaincompress(BGM 跟随 vocals 自动 ducking)
  → amix → loudnorm(I=-14:TP=-1:LRA=11) → 封装出片
```

**风险（设计正视，不静默劣化）**：
1. Demucs 从"对白+原BGM+音效"混轨分离人声会有**残留/损耗**——成片音质下限取决于此。检测到分离质量低时**告警 + 保留原混轨供人工裁决**。
2. ACE-Step 分段 crossfade 拼接处可能有衔接感——用重叠淡入淡出 + 段落边界落在转场处缓解。
3. 爆点帧级卡点是最不稳的一环——即便半自动，也以"给候选 + 人工确认"为准，不强行自动吸附。

## 8. 错误处理 / 降级 / 缓存

- 每阶段产物落盘 → 任意阶段失败可单独重跑，不影响已完成段
- 豆包情绪识别失败/超时 → 降级用"总风格默认情绪"，不阻断
- ACE-Step 生成失败 → 重试；连续失败 → 标记该段待人工处理
- Demucs 分离质量低 → 告警 + 保留原混轨，不静默劣化
- 缓存：MP4 内容 hash 作键，镜头切分/情绪/已选 BGM 分层缓存，改一段不冲掉全部

## 9. 测试策略

沿用项目现有 mock 风格（参考 `tests/test_providers/test_runninghub_*`）：

- **纯逻辑单元直接测**：`segment_planner`（聚合规则）、`prompt_composer`（模板）、`beat_aligner`（对齐算法，喂 mock 时间戳）、`session`（持久化/续跑/单段重跑）
- **外部依赖全 mock**：豆包 / ACE-Step(RunningHub) / Demucs
- **音视频 IO** 用极小样例片段

## 10. 技术栈

| 环节 | 选型 | License |
|---|---|---|
| 镜头切分 | PySceneDetect（默认）/ TransNetV2（可选） | MIT / 宽松 |
| 情绪理解 | 豆包 `doubao-seed-2-0-lite-260215`（OpenAICompatProvider，参照 refine） | 自有 API |
| prompt 转译 | 同上豆包模型 + 模板 | 自有 API |
| BGM 生成 | ACE-Step v1.5（BGM-only），**RunningHub 远程**，复用 `providers/runninghub` client | 模型 MIT / 平台 |
| 爆点检测 | OpenCV 光流 + librosa | BSD/ISC |
| 节奏对齐 | librosa + pyrubberband | ISC/GPL→以 CLI 调用 rubberband |
| 人声分离 | Demucs | MIT |
| 混音 | FFmpeg（loudnorm + sidechaincompress） | LGPL/GPL |

## 11. 实现时定（不阻塞设计）

- ACE-Step：**RunningHub 远程**（WorkflowID `2059090557116440578`，复用 runninghub client，同 LTX 模式，零本地显存）。`music_generator` 注入的 nodeInfoList 字段（均为 widget，覆盖合法）：
  - node94 `TextEncodeAceStepAudio1.5.tags` ← 风格/情绪标签文本（逗号分隔 + `[Intro]/[main theme]/[fade out]` 结构标记）
  - node203 `Int.value` ← BPM（每分钟节拍数）
  - node205 `Float.value` ← 时长秒（同时驱动 latent 98 与 tags 94 的 duration）
  - node109 `PrimitiveInt.value` ← seed（多候选用不同 seed）
  - node107 `SaveAudioMP3.filename_prefix` ← 输出命名（可选）
  - **设计影响**：BPM/时长是独立数值节点（不靠 tags 文字），故 `prompt_composer` 需从"单一多行文本"改为输出 **(tags, bpm, duration) 三元组**；Plan 1 的 `compose_music_prompt` 在 Plan 3 据此调整。
- 镜头切分是否上 TransNetV2（PySceneDetect 不够准时再加）
- 情绪标签的具体 schema（valence/arousal 连续值 vs 离散标签集，先离散 + 强度）
- ✅ **已验证 `doubao-seed-2-0-lite-260215` 支持图像输入**（实测分镜图返回准确情绪 JSON：labels/valence/arousal + 画面描述，真看懂内容）。无需回退两步走。

## 12. 与 drama-shot-master 的集成点

- `emotion_tagger` 经 `OpenAICompatProvider` 调用豆包 `doubao-seed-2-0-lite-260215`（vision）。**实测：有效 key 在 `refine_api_key`（settings.json），`.env DOUBAO_API_KEY` 为空**。故 `build_soundtrack_provider` 取值优先级须为 `soundtrack_*` → **`refine_*`** → `api_keys['doubao']` → 默认（Plan 1 的 provider.py 缺 refine 回退，Plan 3 修正）。openai SDK 已装入 `/usr/bin/python3`。
- `music_generator` 走 RunningHub（已定），复用现有 `providers/runninghub` client：create_task(ACE-Step workflowId + nodeInfoList 注入 prompt) → 轮询 → 下载 BGM wav，同 LTX 模式
- 复用宿主 `config`（API key、路径策略）；豆包凭据可复用 `.env` 里的 `DOUBAO_API_KEY/DOUBAO_BASE_URL`
- 后续导演台可加一个"配乐"面板/任务，通过 §6 的 pause/resume API 驱动本 agent

## 13. 一句话总结

成片 MP4 → 镜头切分恢复时间结构 → 聚合 3–5 叙事段 → 豆包补段落情绪 → 总风格锁基调经 RunningHub ACE-Step 生成分段 BGM → 段落边界对齐转场 + 爆点半自动卡点 → Demucs 分离对白后 ducking 混音出片；全程半自动、关键节点人工确认、可单段重跑。
