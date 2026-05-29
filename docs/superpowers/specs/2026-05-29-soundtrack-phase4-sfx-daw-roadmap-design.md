# Phase 4 SFX + DAW 多轨编辑器 路线图 & Phase 4a 详细设计

**日期**：2026-05-29
**作者**：sound_track_agent 维护者
**状态**：设计稿，待用户确认

---

## §0 Phase 4 路线图（5-7 周总）

> 目标终态：**自动配乐 + 自动配音效双管齐下的 DAW 多轨编辑器**，体感对标 ACE Studio 的"项目级多 stem 管理"与 Submagic/CapCut 的"自动检测 + 用户精细调整"。

### §0.1 三阶段渐进

| 阶段 | 时长 | 后端 | UI | 可交付状态 |
|------|------|------|-----|-----------|
| **Phase 4a** | 2 周 | ✅ SFX 完整后端管道（检测 → 生成 → 混音） | ⚠️ 临时用 P1 卡片 Tab（与 BGM tab 同构，最小 UI） | 用户可让系统**自动**给视频加 SFX，听、改 prompt、重生成、出最终视频 |
| **Phase 4b** | 1 周 | 零新增（复用 4a） | ➕ SoundtrackEditor 顶部加只读 mini-timeline 概览（视频/BGM/SFX/对白 4 轨） | 用户可一眼看全片各 stem 分布，点击跳到对应 tab 的卡片 |
| **Phase 4c** | 3-4 周 | 零新增（复用 4a） | 🔁 主区从 tab+卡片**完全切换**为 DAW 多轨时间轴 + Inspector + 撤销栈 | 体验对齐 Premiere/CapCut SFX 模式：cue 可拖、双击编辑、撤销重做、键盘快捷键 |

### §0.2 每阶段独立 spec + plan

本文档**只覆盖 Phase 4a 的详细设计**。Phase 4b/4c 在 4a 落地、跑通真实视频后，单独 brainstorm + spec，以便届时根据 4a 真实使用反馈调整。

### §0.3 总路线图里程碑验收

| 里程碑 | 验收条件 |
|--------|----------|
| **4a 完成** | 拿一段 30s 短剧视频，点 [🎬 一键生成]：自动检测镜头 → LLM 推荐 SFX → 提交 RunningHub 生成 → 混音回视频；UI 卡片列表里能改任意 cue 的 prompt/duration/音量/启用、重生成、试听；最终 mp4 里能听到 SFX 与 BGM 共存且 SFX 出现时 BGM 自动 -6dB |
| **4b 完成** | mini-timeline 上能正确显示 4 条 stem，点击 BGM/SFX cue 跳到对应 tab 卡片，点击视频缩略图触发底部播放器 seek |
| **4c 完成** | 主区是多轨时间轴；拖动 BGM/SFX cue 边界改时长、整体平移；双击 cue 在 inspector 改 prompt；右键 cue 菜单含 split/duplicate/delete；Ctrl-Z/Y 撤销重做覆盖所有命令；keyboard mapping 至少 4 个核心快捷键（space=播放、R=重生选区、Del=删除、Ctrl-Z/Y） |

---

## §1 Phase 4a 详细设计

### §1.1 包结构（在 `sound_track_agent/` 内加 sfx 子包）

```
sound_track_agent/
├── sfx/                          # NEW: SFX 子包
│   ├── __init__.py
│   ├── event_planner.py          # LLM 看 shot 多帧 → SFXShot.{prompt_short, needs_sfx, duration_hint}
│   ├── prompt_composer.py        # SFXShot → RunningHub workflow node_info_list（薄）
│   ├── generator.py              # 单 job 完整生命周期：cache → create_task → wait → download → store
│   ├── batch_generator.py        # SFX 批量并发（与 BGM batch_generator 同结构，但 cache namespace="sfx"）
│   ├── facade.py                 # 公开 API: plan_sfx_session / generate_sfx_all / regenerate_sfx_one / set_sfx_chosen / load_sfx_session
│   └── session.py                # SFXShot / SFXCandidate / SFXSession dataclasses + 持久化
│
├── audio_cache.py                # RENAMED from bgm_cache.py: 加 namespace 参数 ("bgm" / "sfx")
├── batch_generator.py            # CHANGED: 抽 _run_job/_execute 成可复用辅助（保持 BGM API 不变）
├── mixdown.py                    # CHANGED: 加 assemble_sfx_track + sidechain ducking
└── facade.py                     # CHANGED: 加 SFX 入口转发
```

**复用现有模块**（零或微改）：
- `shot_detector.detect_shots` —— 复用，输出 `List[Shot]` 喂给 sfx event_planner
- `emotion_tagger` 的视觉 LLM provider —— 复用，但 system prompt 切换为 SFX 检测专用
- `bgm_cache` → 改名为 `audio_cache` + 加 `namespace: Literal["bgm","sfx"]` 参数（缓存键加前缀）
- `batch_generator._run_job/_execute` 抽公共，BGM/SFX 各自包装
- `mixdown._duck_and_mix` —— 复用其 ducking 实现，新增 SFX 轨作为第二条触发源
- `audio_mixer.assemble_dialogue_track` 的 `adelay + amix` 拼接模式 —— 直接复制为 `assemble_sfx_track`

### §1.2 数据结构

`sound_track_agent/sfx/session.py`：

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


@dataclass
class SFXCandidate:
    """单次 RunningHub 提交的 stable_audio_3 输出。"""
    path: str                                # 绝对路径，cache/sfx/<hash>.mp3
    seed: int
    prompt: str                              # 最终提交给 workflow 的短描述（含 Length: Xs 后缀）
    score: Optional[float] = None            # MVP 不打分，留字段


@dataclass
class SFXShot:
    """与 shot_detector 输出的镜头一一对应。"""
    shot_index: int                          # 0-based，与 shot_detector 输出对齐
    t_start: float                           # 镜头起始秒
    t_end: float                             # 镜头结束秒
    representative_frame: str = ""           # 缩略图（中段那一帧的路径）
    prompt_short: str = ""                   # 用户/LLM 给的短描述
    duration: float = 0.0                    # 默认 = t_end - t_start，可被用户编辑（1-15s）
    candidates: list[SFXCandidate] = field(default_factory=list)
    chosen_candidate: Optional[int] = None   # 选定的 candidate index
    status: Literal["pending", "planned", "generated", "skipped"] = "pending"
    next_seed: int = 1                       # 下次 regenerate 起始 seed
    volume: float = 1.0                      # 0.0-1.5，单条 SFX 输出音量
    enabled: bool = True                     # mix 阶段是否纳入

    @property
    def shot_duration(self) -> float:
        return self.t_end - self.t_start


@dataclass
class SFXSession:
    """SFX 编辑会话；与 BGM ScoringSession 平级、独立持久化。"""
    source_mp4: str
    source_hash: str
    frame_rate: float
    shots: list[SFXShot] = field(default_factory=list)
    sfx_planned: bool = False                # event_planner 是否已跑过

    def save(self, path: Path) -> None:
        """JSON 序列化到 <work_dir>/sfx_session.json"""
        import json
        from dataclasses import asdict
        Path(path).write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Optional["SFXSession"]:
        """损坏 / 不存在返回 None；调用方据此决定是否新建"""
        import json
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            shots = [SFXShot(
                **{k: v for k, v in s.items() if k != "candidates"},
                candidates=[SFXCandidate(**c) for c in s.get("candidates", [])])
                for s in data.pop("shots", [])]
            return cls(**data, shots=shots)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, TypeError, KeyError):
            return None
```

### §1.3 数据流（5 阶段）

```
[1] shot_detect   sound_track_agent.shot_detector.detect_shots(mp4, threshold=0.3)
                  → List[Shot{t_start, t_end, frame_path}]
                  写入: SFXSession.shots[i].t_start/t_end/representative_frame
                  状态: SFXShot.status = "pending"

[2] event_plan    sfx.event_planner.plan_events(session, provider, frames_per_shot=3)
                  对每个 status=pending 的 SFXShot:
                      - 抽 frames_per_shot 帧（首/中/末，复用 refine._times_for_shot 思路）
                      - 调 emotion_tagger 的多帧 LLM 接口（system prompt 切 SFX 模式）
                      - 期望 LLM 返回 JSON: {"needs_sfx": bool, "prompt_short": str, "duration_hint": float}
                      - needs_sfx=false 或 prompt_short 空 → 状态置 "skipped"
                      - 否则写 prompt_short + duration（clamp 到 [1, 15]）+ 状态 "planned"
                  写入: SFXSession.sfx_planned = True

[3] generate      sfx.batch_generator.generate_all(session, client, workflow_id, cache_dir, ...)
                  对每个 status=planned 的 SFXShot:
                      - cache_key = hash(workflow_id, "sfx", prompt_short, duration, seed)
                      - 命中 cache: 直接拿 path 入候选
                      - miss: RunningHub create_task with node_info_list（见 §1.4）
                      - 下载到 cache/sfx/<hash>.mp3
                  写入: SFXShot.candidates += [SFXCandidate(...)]
                       SFXShot.chosen_candidate = 0（默认选第一个）
                       SFXShot.status = "generated"
                       SFXShot.next_seed += seeds_count

[4] UI 修正       SoundtrackEditor 的 SFX tab (P1 卡片列表)
                  - 改 prompt_short → 触发 regenerate_sfx_one（清候选 + status="planned" + 重生）
                  - 改 duration → 同上
                  - 调音量 → 仅改 SFXShot.volume，不重生
                  - 勾掉 enabled → mix 跳过
                  - 试听某候选 → 直接 QMediaPlayer 加载（复用 SegmentReviewWidget 模式）
                  - 切换 chosen_candidate → 写 SFXShot.chosen_candidate

[5] mix           mixdown.assemble_and_mix(...) 内部追加：
                  - 收集所有 enabled 且 chosen_candidate is not None 的 SFXShot
                  - assemble_sfx_track(shots, work_dir / "sfx_track.wav"):
                      对每条 SFX，按 t_start 计算 adelay (ms)，
                      合到 sfx_track.wav（复用 audio_mixer.assemble_dialogue_track 的 adelay+amix）
                  - duck_with_sfx(mixed.wav, sfx_track.wav, out.wav):
                      用 ffmpeg sidechaincompress，触发源 = sfx_track，被压源 = mixed（含 BGM）
                      ratio=4, threshold=0.05, makeup=2  → 听感 SFX 出现时 BGM 短暂 -6dB
                  - replace_video_audio(mp4, out.wav, out_mp4)
```

### §1.4 RunningHub Stable Audio 3 workflow 节点参数

Workflow ID: `2060218796413112321`
JSON 模板: `comfyui_workflow/Stable audio 3纯音乐-音效-VFX-One-Shot音频_api.json`

`sfx/prompt_composer.py` 输出的 `node_info_list`（每条提交都设这 4 个节点）：

| 节点 ID | class_type | fieldName | fieldValue | 说明 |
|---------|------------|-----------|------------|------|
| `92` | `PrimitiveStringMultiline` | `value` | `prompt_short` (str) | 用户/LLM 给的短描述，如 "门吱呀开启，脚步进屋" |
| `98` | `PrimitiveFloat` | `value` | `duration` (float) | 目标音频长度，秒；范围 1-15 |
| `108` | `easy anythingIndexSwitch` | `index` | `2` (int, 固定) | 选 SFX 模式（其它：0=Music, 1=Instrument, 3=One-shot） |
| `84` | `KSampler` | `seed` | `seed` (int) | 决定生成随机性 |

**可选**（MVP 不动）：
- 节点 `97 PrimitiveBoolean.Enable_Reprompt = True` —— 让 qwen3.5-4B 自动扩写短描述为详细 prompt（默认 True 即可，避免短剧用户写不出 stable_audio 期望的 dense prompt）

### §1.5 UI 层（Phase 4a：P1 卡片 Tab）

**SoundtrackEditor 新增 SFX tab**（在现有 配置/BGM tab 之后）：

```
┌── SFX tab ─────────────────────────────────────────────┐
│ ┌── 顶部工具栏 ──────────────────────────────────────┐ │
│ │ [🎬 检测 SFX 时机]  [🔊 生成全部]  [↻ 重检测]    │ │
│ │ 状态: 已检测 12 镜 / 已生成 8 镜                  │ │
│ └────────────────────────────────────────────────────┘ │
│ ┌── 滚动卡片列表（每镜一卡） ────────────────────────┐ │
│ │ ┌── 镜 0  [00:00.0 - 00:03.5]  ✅ generated ─────┐│ │
│ │ │ [🖼缩略图] [启用 ☑] [音量 ━●━]               ││ │
│ │ │ 短描述: [门吱呀开启，脚步进屋_________________]│ │
│ │ │ 时长: [3.5s ▲▼]  种子: 1                       ││ │
│ │ │ 候选: [▶ 1] [▶ 2]  ←现在选 #1                  ││ │
│ │ │ [↻ 重生成]                                     ││ │
│ │ └────────────────────────────────────────────────┘│ │
│ │ ┌── 镜 1  [00:03.5 - 00:05.0]  ⏭️ skipped ─────┐│ │
│ │ │ LLM 判定: 该镜静态对话无音效需求               ││ │
│ │ │ [手动启用 SFX]                                 ││ │
│ │ └────────────────────────────────────────────────┘│ │
│ │ ┌── 镜 2  ...                                    ││ │
│ └────────────────────────────────────────────────────┘ │
│ ┌── 底部共享试听 seek bar（复用 SegmentReviewWidget）┐│
│ │ [▶/⏸] ━━●━━━━━━━━━━━ 00:01.2 / 00:03.5            ││
│ └─────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────┘
```

**新增 UI 模块**：
- `drama_shot_master/ui/widgets/sfx_review_widget.py` —— 与 SegmentReviewWidget 同结构的 SFX 卡片列表 widget
- `drama_shot_master/ui/widgets/soundtrack_editor.py` 内 `_build_sfx_tab()` 方法 + 集成 SFX 流水线触发按钮

### §1.6 配置项（Config 新字段）

```python
# drama_shot_master/config.py 追加
sfx_workflow_id: str = "2060218796413112321"
sfx_plan_frames_per_shot: int = 3                      # event_planner 抽帧数（1/3/5）
sfx_max_concurrency: int = 3                           # 并发 stable_audio_3 任务数
sfx_default_volume: float = 0.8                        # SFX 默认音量（BGM 默认 1.0，SFX 略低让对白更突出）
sfx_ducking_db: float = -6.0                           # SFX 触发时 BGM 衰减分贝
sfx_seeds_count: int = 1                               # 单镜默认候选数（1=最快，2-3=多选）
sfx_default_enabled: bool = True                       # 新检测出的镜头默认 enabled
```

**SoundtrackSection 新增控件**（与 Sprint 0 6 控件并列）：
- `sfx_workflow_id` QLineEdit
- `sfx_plan_frames_per_shot` QComboBox [1,3,5]
- `sfx_max_concurrency` QSpinBox 1-10
- `sfx_default_volume` QDoubleSpinBox 0.0-1.5
- `sfx_ducking_db` QDoubleSpinBox -20.0-0.0
- `sfx_seeds_count` QSpinBox 1-5

所有字段走 `cfg.update_settings` 持久化到 settings.json。

### §1.7 错误处理

| 错误源 | 影响 | 处理 |
|--------|------|------|
| LLM event_plan 返回非 JSON / 解析失败 | 单镜停在 `pending` | try/except + log + UI 显示"⚠️ 该镜检测失败"，用户可手填 prompt |
| LLM `needs_sfx=true` 但 prompt_short 为空 | 模型不确定 | 当作 `skipped`，不阻塞 |
| RunningHub 提交超时 / 5xx | 单镜 0 候选 | 复用 batch_generator 失败隔离 (`_execute on_progress` + 跳过)；UI 显示重试按钮 |
| 生成 mp3 与请求 duration 偏差 > 50% | 候选异常但保留 | log warn；UI 候选按钮加 ⚠️ 标记 |
| `sfx_session.json` 损坏 | 加载失败 | `load_sfx_session` 返回 None；写 `.bak` 备份后新建空 session |
| 全部镜头 enabled=false | sfx_track.wav 空 | mix 跳过 SFX 步骤，直接出 BGM+dialogue mixed.wav |
| dialogue 派生失败（video_tasks 无匹配） | 不影响 SFX 流程 | mini-timeline 对白轨灰（Phase 4b 才出现） |

### §1.8 测试策略

| 测试文件 | 数量 | 覆盖 |
|----------|------|------|
| `tests/test_sound_track_agent/test_sfx_session.py` | 4-5 | SFXSession round-trip 持久化、损坏文件返回 None、空 candidates 加载 |
| `tests/test_sound_track_agent/test_sfx_event_planner.py` | 5-6 | JSON 解析 / needs_sfx=false 跳过 / 空 prompt 跳过 / duration clamp / LLM 异常 |
| `tests/test_sound_track_agent/test_sfx_prompt_composer.py` | 4-5 | node_info_list 4 字段映射正确 / duration 浮点保真 / SFX 模式 index=2 固定 |
| `tests/test_sound_track_agent/test_sfx_generator.py` | 4-5 | _node_info 正确 / wait_success 超时 / 下载存盘 (mock RunningHubClient) |
| `tests/test_sound_track_agent/test_sfx_batch_generator.py` | 4-5 | 缓存命中 / 失败隔离 / next_seed 推进 / chosen_candidate 默认 0 |
| `tests/test_sound_track_agent/test_sfx_facade.py` | 4-5 | plan_sfx_session / generate_sfx_all / regenerate_sfx_one / set_sfx_chosen e2e (fake client) |
| `tests/test_sound_track_agent/test_audio_cache.py` | 3-4 | BGM/SFX 同 prompt+seed 不冲突 / 旧 BGM 缓存键兼容（namespace 默认 "bgm"） |
| `tests/test_sound_track_agent/test_mixdown_sfx.py` | 4-5 | assemble_sfx_track adelay+amix 时序 / sidechain ducking ffmpeg 命令正确 / 空 SFX 跳过 |
| `tests/test_config/` 追加 | 2-3 | 6 个 sfx_* 字段持久化 round-trip |
| `tests/test_ui/test_sfx_review_widget_smoke.py` | 4-5 | 控件存在 / 重生成信号 / 选定候选写 chosen / 音量滑条 |
| `tests/test_ui/test_soundtrack_editor_sfx_tab_smoke.py` | 3-4 | SFX tab 存在 / 切换不崩 / SFX session 派生 / pipeline 触发 |
| `tests/test_ui/test_soundtrack_section_sfx_smoke.py` | 2-3 | 6 个 sfx cfg 控件 load_from/save_to 往返 |

**总估计 ~45-55 新用例**，工程量同 Phase 2 量级。

---

## §2 Phase 4a 验收标准

1. **后端 e2e**：拿一段 30s 短剧 mp4，调 `facade.plan_sfx_session(mp4, work_dir)` → `facade.generate_sfx_all(session, work_dir)` → `mixdown.assemble_and_mix(..., sfx_session=session)` → 输出新 mp4。新 mp4 含 SFX，听感无明显冲突，BGM 在 SFX 出现时刻短暂衰减。
2. **UI 可用**：在 SoundtrackEditor 新增 SFX tab；点 [🎬 检测 SFX 时机] 触发后端 plan_sfx；卡片列表显示每镜 prompt + 时长 + 启用开关 + 音量 + 候选 + 重生按钮；改 prompt 后 ↻ 重生成正常出新候选；切候选写 chosen_candidate；试听按钮播 mp3。
3. **session 持久化**：关闭再开 SoundtrackEditor，SFX tab 状态完全恢复。
4. **配置项可用**：设置→配乐 6 个 sfx_* 控件可改、写盘、reload 生效。
5. **测试**：~45 新用例全绿；现有 BGM 测试零回归（特别注意 bgm_cache → audio_cache 改名后旧 cache 仍能命中）。
6. **commits**：每个 task 单独 commit 在分支 `feat/sfx-phase4a`，最后整合到主干。

---

## §App A：Stable Audio 3 workflow 4 模式开关

`easy anythingIndexSwitch (节点 108) .index` 切换：

| index | 模式 | 用途 | 我们用吗 |
|-------|------|------|---------|
| 0 | Music | 整曲 BGM (60-300s) | ❌（BGM 走 ACE-Step） |
| 1 | Instrument | 单乐器 loop/stem (6-180s) | ❌（MVP 不需要） |
| **2** | **SFX** | **音效 / ambience (1-15s)** | ✅ **Phase 4a 主用** |
| 3 | One-shot | 单击鼓点等 (1-11s) | ❌（Phase 4c 可能用） |

每个模式有独立的 LLM system prompt（嵌在 workflow 节点 94 的 json_string），SFX 模式 system prompt 已写好（约 3KB），包含 length 规则（1-3s impact / 3-6s 动作 / 6-15s ambience）和大量示例。**我们不动它，让 workflow 内置 qwen3.5-4B 自动 reprompt。**

## §App B：与 BGM 智能体的关键差异

| 维度 | BGM (sound_track_agent 现状) | SFX (Phase 4a 新增) |
|------|---|---|
| 粒度 | segment（30s 聚合段） | shot（1-6s 镜头） |
| 模型 | ACE-Step 1.5X (RunningHub) | Stable Audio 3 medium (RunningHub) |
| Workflow ID | `2059090557116440578` | `2060218796413112321` |
| LLM 检测 | emotion_tagger 多帧情绪标签（5 维 VAD） | SFX event planner（短描述 + duration_hint） |
| 默认候选数 | 2 | 1 |
| Cache 子目录 | `cache/bgm/` | `cache/sfx/` |
| 持久化 | `session.json` (ScoringSession) | `sfx_session.json` (SFXSession) |
| 默认音量 | 1.0 | 0.8（让对白更突出） |
| Mix 接入点 | 主轨叠加 + accent ducking 卡点 | sidechain triggered ducking（SFX 触发 BGM -6dB） |
| 重生重置 | clear candidates + status=planned | 同 |
| UI | BGM tab (SegmentReviewWidget) | SFX tab (SfxReviewWidget，同构) |
