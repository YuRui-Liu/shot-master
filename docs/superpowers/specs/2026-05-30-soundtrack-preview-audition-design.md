# 配乐 出片前试听 + 工作目录打开 设计

> 日期：2026-05-30　分支：feat/sfx-phase4c
> 目标：让用户在**导出成片前**就能判断 BGM/SFX 是否合理（逐段试听 + 整体叠加播放），并能直接打开已有工作目录载入任务。

## 背景与动机

当前 SoundtrackEditor（Phase 4c DAW）选「配乐」胶囊只能播放 `session.output`（出片后的 scored mp4）。但用户需要在**出片前**判断 BGM 是否合理、要不要单段重生成——出片成本高，不能等出片才听。

现有可复用积木：
- `sound_track_agent.facade.build_accent_preview(session, work_dir, ...)` → 产出纯 BGM 预览轨 `preview_accent_bgm.wav`（含卡点对齐/泵感，**不需 demucs/视频混流**）
- `sound_track_agent.mixdown.assemble_sfx_track(sfx_shots, out_path)` → 收集 enabled+chosen 的 SFX，按 t_start 拼成单轨 wav；无可用 SFX 返回 None
- `VideoPreviewWidget`：封装单个 `QMediaPlayer+QAudioOutput`，已暴露 `set_source/seek/play/pause/duration/is_playing` + `positionChanged(float秒)` 信号
- BGM 候选 mp3 落在 `<work_dir>/cache/bgm/*.mp3`；SFX 候选落在 `<work_dir>/cache/sfx/*.mp3`

## 三个功能单元

### 功能 1a — Inspector 逐段候选 ▶ 试听

**目的**：段级判断"这一段的 BGM/SFX 候选好不好"，决定是否单段重生成。

- `BgmInspector` / `SfxInspector` 的每个候选 radio 行右侧加一个 ▶ 按钮。
- 点击 ▶ → 播放该候选音频文件（`seg.candidates[i].path` / `shot.candidates[i].path`），按钮变 ⏸。
- 再点 ⏸ → 停止，按钮变回 ▶。
- 点另一个候选的 ▶ 或切换 cue → 停止当前播放、复位所有按钮为 ▶。
- 每个 Inspector 实例自带一个 `QMediaPlayer+QAudioOutput`（懒建，headless 安全）。
- 文件不存在 → ▶ 按钮置灰 + tooltip "候选文件缺失"。

**接口**：Inspector 内部自洽，不新增对外信号（试听是本地行为，不改数据）。

### 功能 1b — 实时三轨叠加播放（视频原声 + BGM + SFX）

**目的**：出片前听"整体感觉"——视频原声 + 配乐 +（可选）音效叠在一起。

**新组件** `drama_shot_master/ui/widgets/overlay_audio.py`：

```
class OverlayMixer(QObject):
    """管理 N 条 audio-only 叠加轨（各自 QMediaPlayer+QAudioOutput），
    跟随一个主时钟（VideoPreviewWidget）播放。"""
    set_track(name: str, path: str | None)   # None=清空该轨
    set_enabled(name: str, on: bool)
    set_volume(name: str, vol: float)        # 0..1.5
    play()  /  pause()  /  stop()
    seek(t_sec: float)
    sync(t_sec: float)   # 主时钟回调：漂移 > _DRIFT_SEC(0.2) 才 setPosition 纠偏
```

- 轨名固定 `"bgm"` / `"sfx"`。
- 懒建 QMediaPlayer（headless 测试不碰音频后端）。

**VideoPreviewWidget 改动**（最小）：
- 新增信号 `playingChanged(bool)`，在内部 play/pause（含自带 ▶ 按钮与外部调用）状态变化时 emit。
- `positionChanged` 已存在，作为同步主时钟。

**SoundtrackEditor 接线**：
- 持有一个 `OverlayMixer`。
- `video_preview.positionChanged` → `mixer.sync(t)`
- `video_preview.playingChanged(on)` → `on ? mixer.play() : mixer.pause()`
- 用户 seek（overview/track playhead）→ 已经 `video_preview.seek`，position 变化经 positionChanged 传导；额外在 seek 后直接 `mixer.seek` 一次减少漂移。
- 播放模式胶囊映射：
  - **原声**：`mixer.set_enabled("bgm",False); set_enabled("sfx",False)`，video_preview 播原始 mp4（原声）。
  - **配乐**：确保 BGM 轨已构建并载入 → `set_enabled("bgm",True); set_enabled("sfx",False)`。
  - **完整混音**：BGM+SFX 轨均载入 → 两轨 enable。
- 视频源在所有模式下都用**原始 mp4**（保留画面+原声）；配乐/混音通过叠加轨实现，不再切换到 scored mp4。
  - 例外：若用户确有 scored mp4 且想看成片，仍可走原 `_scored_mp4()`——但本设计默认叠加预览，scored 播放保留给「预览成片」按钮（已存在）。
  - **取代上一轮行为**：上次修复让「配乐」→ `session.output`/`task["output"]`（scored mp4）。本设计改为「配乐」= 原始视频 + BGM 叠加轨，使**出片前**即可试听。`_resolve_video_source`/`_on_play_mode_changed` 相应重构；`_scored_mp4()` 保留供「预览成片」用。

**预览轨构建 + 缓存（功能 1b 核心）**：
- 选「配乐/混音」时，若对应预览轨未构建或**内容指纹变化**，后台 `FunctionWorker` 跑：
  - BGM：`facade.build_accent_preview(session, work_dir)` → `preview_accent_bgm.wav`
  - SFX：`mixdown.assemble_sfx_track(sfx_session.shots, work_dir/"sfx_track.wav")`（None=无 SFX，禁用该轨）
- **缓存指纹** `_preview_fingerprint()`：对影响产物的字段做 hash——
  - BGM：各段 `chosen_candidate`、`volume`、`accent_points`、`accent_mix_enabled`、`pump_strength`
  - SFX：各 shot 的 `enabled`、`chosen_candidate`、`volume`、chosen 候选 path
  - 指纹未变 + 产物文件存在 → 跳过重建，直接载入。
- 构建期间播放模式按钮短暂禁用 + progress_label 提示"正在生成配乐预览…"。

### 功能 2 — 配乐面板「打开」工作目录

**目的**：直接打开已有工作目录载入任务（顺带修正"output_dir 改动导致工作目录错位"）。

- `SoundtrackPanel` 在「新建/删除」按钮旁加「打开」按钮。
- 点击 → `QFileDialog.getExistingDirectory` 选含 `session.json` 的目录 `D`。
- 校验：`D/session.json` 不存在 → `QMessageBox.warning("不是有效的配乐工作目录")`，不创建。
- 反推任务字段：
  - `id = D.name`（如 `17797915850335bf1e`）
  - `output_dir = str(D.parent)`
  - `name = D.parent.name`（如 `02_女剑客归山`）
  - `mp4 = session["source_mp4"]`、`style = session.get("global_style","")`、`output = session.get("output","") or ""`
- 关键不变式：`_work_dir() = output_dir / id = D.parent / D.name = D` —— 正好载入选中目录。
- 同 `id` 已在 `cfg.soundtrack_tasks` → 不重复添加，直接选中。
- 追加任务 → `_persist_cb()` → `refresh()` → `_select_task(id)` → `icon_rail_updated.emit()`。

## 数据流

```
[1a] Inspector ▶  →  本地 QMediaPlayer 播 candidate mp3（不改数据）

[1b] 胶囊模式切换 ──→ (指纹变?) ──→ FunctionWorker: build_accent_preview / assemble_sfx_track
                                          │
                                          ▼
                                   OverlayMixer.set_track(bgm/sfx, wav)
     VideoPreviewWidget(主时钟) ──positionChanged──→ OverlayMixer.sync(t)
                              └──playingChanged──→ OverlayMixer.play/pause

[2]  打开按钮 → 选目录 → 读 session.json → 反推 task dict → cfg.soundtrack_tasks → refresh/select
```

## 错误处理

- 1a：候选文件缺失 → ▶ 置灰；播放后端异常 → 静默忽略（不崩）。
- 1b：build_accent_preview / assemble_sfx_track 抛错 → progress_label 显示"配乐预览生成失败：…"，该轨禁用，视频原声照常播。
- 1b：QMediaPlayer 在 headless（offscreen）下懒建，测试只验证状态机不碰真实音频。
- 2：目录无 session.json / session.json 解析失败 → warning，不创建任务。

## 测试策略

- **1a**：`BgmInspector`/`SfxInspector` 构造后每候选有 ▶；点击 ▶ 触发播放调用（mock QMediaPlayer 或验证内部 state 切 ⏸）；切候选复位。
- **1b**：
  - `OverlayMixer` 单测：set_track/enable/volume/play/pause/sync 状态机（不实例化真实音频后端，或用 offscreen 懒建守卫）。
  - `_preview_fingerprint` 纯函数单测：字段变化 → 指纹变；不变 → 指纹同。
  - `VideoPreviewWidget.playingChanged` 在 play/pause 时 emit。
  - 编辑器接线 smoke：切模式 → mixer enable 正确；指纹未变不重建。
- **2**：`SoundtrackPanel.open_work_dir(path)`（抽成可测方法）：合法目录 → 追加正确 task dict；缺 session → 不追加 + 返回 False；重复 id → 不重复。

## 不做（YAGNI）

- 不做采样级精确同步（方案 A 接受 <200ms 漂移）。
- 不做实时 ducking（叠加轨各自定音量；精确 ducking 留给正式出片）。
- 不做多候选并排试听（一次播一个）。
- 「打开」不递归扫描父目录（用户明确选工作目录这一层）。

## 文件清单

```
新增:
  drama_shot_master/ui/widgets/overlay_audio.py          # OverlayMixer
  tests/test_ui/test_overlay_audio.py
  tests/test_ui/test_inspector_audition.py
  tests/test_ui/test_soundtrack_open_dir.py

改:
  drama_shot_master/ui/widgets/daw/inspector/bgm_inspector.py   # 候选 ▶
  drama_shot_master/ui/widgets/daw/inspector/sfx_inspector.py   # 候选 ▶
  drama_shot_master/ui/widgets/video_preview_widget.py          # playingChanged 信号
  drama_shot_master/ui/widgets/soundtrack_editor.py             # OverlayMixer 接线 + 指纹缓存 + 模式映射
  drama_shot_master/ui/panels/soundtrack_panel.py               # 打开按钮 + open_work_dir()
  tests/test_ui/test_soundtrack_play_mode.py                    # 适配叠加模式
```
