# 框选生成交互设计 — 子项目 #3d

> 日期：2026-05-31　分支：main
> #3「框选→生成→叠加多子轨」第 4 块（收官）。地基：3a OverlaySession / 3b MixStreamEngine / 3c 动态轨渲染。
> 交互已 `docs/explorer/3d-framing-generate-interaction-confirm.html` 可视化确认（推荐流程 + 4 决策全取推荐默认）。

## 背景与定位

把前三块串成完整用户闭环：在时间轴**框选区间** + prompt → **异步生成** 一个 BGM/SFX 音频片段 → 落进 `OverlaySession`（3c 渲染、3b 播放）。生成走 RunningHub，**异步 10–120s**，故「生成中/失败」态与不阻塞 UI 是核心。

## 已锁定决策

- **框选 = 时间轴 Shift+拖拽**：复用现有 rubber band。`soundtrack_editor.py` 的 `_on_rubber_band(rect, mod)` stub 实装：`_x_to_t(rect.left/right)` → `[t_start, t_end]`（`QRect.normalized()` 已保证 left≤right）。
- **生成对话框** `GenerateOverlayDialog`：BGM/SFX 二选一切换 + prompt 多行 + 时长只读（=框选长度）+ 生成/取消。
- **prompt = LLM 预填可改**：打开对话框时**异步**请求一次 LLM 建议（基于框选区间内对白字幕 + 段落 `global_style`/emotion 上下文），预填进输入框，用户可改。LLM 不可用/超时/未配置 → 输入框留空（降级不崩，不挡手动输入）。
- **时长 = 自动 = t_end − t_start**：BGM 直接用；SFX clamp 到管线约束 1–15s（超出给提示）。
- **异步生成 + lane 占位块**：点「生成」后**立刻** `OverlaySession.add` 一个 `status="generating"` 的占位 segment（audio_path 空）→ 渲染为脉冲斜纹占位块；后台 worker 轮询 RunningHub。成功 → 填 `audio_path` + `status="generated"`；失败 → `status="failed"`（红块可重试）。**UI 全程不阻塞，可多条并行生成**。
- **OverlaySegment 加 `status` 字段**（3a 小扩展）：`Literal["pending","generating","generated","failed"]`，默认 `"generated"`（旧 overlay.json 迁移兼容）；`to_dict`/`from_dict` 同步。
- **生成后端复用**：BGM=`music_generator.generate_bgm(tags=用户prompt, bpm=默认, duration)` 取单结果（用户 prompt 直接当 tags，无需 emotion 反推）；SFX=`sfx.generator.generate_sfx(prompt, duration, seed, out_path)`。缓存复用 `audio_cache`（`work_dir/cache/{bgm,sfx}/`）。**不打分、单结果无候选**（符合 3a）。
- **落库刷新链**：`add`(占位) → 生成完成填 `audio_path`/`status` → `save_overlay` → `mix_engine.set_segments`（自动 skip 空 audio_path 占位）→ 3c `_refresh_overlay_view`。正在播放则新片段即时叠加出声。
- **seg_id**：`f"ov_{kind}_{ms}{hex4}"`（毫秒戳 + 短随机，与项目 `_gen_task_id` 风格一致）。
- **解耦**：与 4 固定轨的生成（`generate_sfx_all` 等）互不影响；overlay 生成独立路径。

## 组件

### 1. OverlaySegment.status（`sound_track_agent/overlay_session.py` 改）

```python
status: str = "generated"   # pending|generating|generated|failed
# to_dict 增 "status"；from_dict: d.get("status", "generated")（旧数据兼容）
```

- `add(...)` 增可选 `status="generated"`（占位时传 `"generating"`）。

### 2. GenerateOverlayDialog（`drama_shot_master/ui/dialogs/generate_overlay_dialog.py`）

```python
class GenerateOverlayDialog(QDialog):
    """框选生成对话框。返回 (kind, prompt) 或 None(取消)。"""
    def __init__(self, t_start, t_end, *, suggest_fn=None, parent=None): ...
    # BGM/SFX 切换(QButtonGroup) + prompt QPlainTextEdit + 时长只读 label + 生成/取消
    # 构造后异步调 suggest_fn(kind, t_start, t_end) → 预填 prompt（QThreadPool/QTimer，不阻塞 exec）
    def result_value(self) -> tuple[str, str] | None
```

### 3. overlay prompt 建议（`sound_track_agent/overlay_prompt.py`）

```python
def suggest_overlay_prompt(kind, t_start, t_end, *, work_dir, cfg, dialogue_text="") -> str:
    """用现有 LLM provider 给一句生成提示词建议。
    输入：kind、区间内对白字幕、global_style。失败/未配置 → 返回 ""（降级）。"""
```

- 复用现有 LLM 平台配置（参考 translator/screenwriter 的 provider 取法）；纯文本进出，全可 mock 单测。

### 4. overlay 单片段生成（`sound_track_agent/overlay_gen.py`）

```python
def generate_overlay_clip(kind, prompt, duration, *, work_dir, cfg, client=None) -> Path:
    """BGM: generate_bgm(tags=prompt, bpm=默认, duration) 取首结果；
    SFX: generate_sfx(prompt, clamp(duration,1,15), seed, out_path)。
    复用 audio_cache 缓存。返回音频文件 Path。异常上抛由 worker 捕获。"""
```

### 5. 异步生成 worker（`drama_shot_master/ui/widgets/daw/overlay_gen_worker.py`）

```python
class OverlayGenWorker(QObject):
    finished = Signal(str, str)   # seg_id, audio_path
    failed   = Signal(str, str)   # seg_id, error
    # 在 QThread/QThreadPool 跑 generate_overlay_clip；只发信号，不碰 UI/session。
```

- 编辑器持有 worker 引用防 GC；信号在主线程槽里改 session + 刷新。

### 6. DawTrackView 片段按 status 上色（扩展 3c 渲染）

- 3c 已画 overlay 片段块；本块按 `seg.status` 区分：`generating`→脉冲斜纹占位 + "⟳ 生成中…"；`failed`→红斜纹 + "✕ 失败"；`generated`→正常斜纹色块。
- 失败块点击 → 选中 + Inspector 显「重试」（或复用 overlaySegmentClicked + inspector 按 status 显重试按钮）。

### 7. SoundtrackEditor 接线（`soundtrack_editor.py`）

- `_on_rubber_band(rect, mod)` 实装：算 `[t_start,t_end]` → 弹 `GenerateOverlayDialog`（传 `suggest_fn=partial(suggest_overlay_prompt, work_dir=..., cfg=...)`）→ 取消则 return。
- 接受 → `seg_id=_gen_overlay_id(kind)`；`_overlay_session.add(kind, t_start, t_end, prompt, seg_id=seg_id, status="generating")` → `save_overlay` → `_refresh_overlay_view`（占位即现）。
- 起 `OverlayGenWorker(seg_id, kind, prompt, duration)`；`finished(seg_id, path)` 槽：`seg=get(seg_id)`；`seg.audio_path=path; seg.status="generated"` → `save_overlay` → `mix_engine.set_segments` → `_refresh_overlay_view`。`failed(seg_id, err)` 槽：`seg.status="failed"` → 保存 + 刷新 + 日志。
- 重试：从 failed segment 复用 prompt/区间重起 worker（status→generating）。

## 错误处理 / 降级

- LLM 建议失败/超时/未配置 → 空 prompt，用户手填，不崩。
- 生成失败（网络/RunningHub 错/超时）→ `status="failed"`，红块可重试，不影响其它片段与固定轨。
- 生成中关闭/切项目 → 占位 segment 已落盘（`status="generating"`）；下次载入按 `generating` 当作可重试（或载入时降级为 `failed`）。
- `seg_id` 在回调时已被删 → `get` 返回 None → 丢弃结果，不崩。
- SFX 时长越界 → clamp + 提示。

## 测试策略

**OverlaySegment.status（纯单测）**
- `add(..., status="generating")` → seg.status 对；`to_dict` 含 status；`from_dict` 缺 status → "generated"（迁移）；round-trip。

**suggest_overlay_prompt（mock LLM）**
- mock provider 返回文本 → 透传；provider 抛/未配置 → 返回 ""。

**generate_overlay_clip（mock client）**
- mock RunningHub client：BGM 路径走 generate_bgm（注入假 client/缓存）→ 返回 Path；SFX 走 generate_sfx；duration clamp 验证；异常上抛。

**GenerateOverlayDialog（smoke）**
- 构造（t_start/t_end）→ 时长 label 正确；切 SFX → kind 变；suggest_fn 返回值预填进 prompt（用同步 stub）；接受 → result_value 返回 (kind, prompt)；取消 → None。

**OverlayGenWorker（mock 生成函数）**
- 注入假 `generate_overlay_clip`（直接返回 Path）→ finished(seg_id, path) 发；注入抛异常 → failed(seg_id, err) 发。（不依赖真线程：可直接调 run，或 QSignalSpy + QThreadPool.waitForDone。）

**DawTrackView status 上色（smoke）**
- set_overlay 含 generating/failed/generated 三态 → 不崩；（可断言内部按 status 取色的纯函数 `_overlay_block_style(status)`）。

**editor 接线（smoke，mock 重组件）**
- `_on_rubber_band` → 弹对话框（mock dialog 返回 (kind,prompt)）→ `add` 占位（status=generating）+ `save_overlay` 被调 + worker 起（mock）。
- worker.finished 槽 → seg.audio_path/status 更新 + `mix_engine.set_segments` 被调 + 刷新。
- worker.failed 槽 → seg.status="failed" + 刷新。
- 取消对话框 → 不 add、不起 worker。

## 文件清单

```
新增:
  drama_shot_master/ui/dialogs/generate_overlay_dialog.py
  drama_shot_master/ui/widgets/daw/overlay_gen_worker.py
  sound_track_agent/overlay_gen.py
  sound_track_agent/overlay_prompt.py
  tests/test_sound_track_agent/test_overlay_gen.py
  tests/test_sound_track_agent/test_overlay_prompt.py
  tests/test_ui/dialogs/test_generate_overlay_dialog_smoke.py
  tests/test_ui/daw/test_overlay_gen_worker.py
  tests/test_ui/test_soundtrack_overlay_framing_wiring.py
改:
  sound_track_agent/overlay_session.py        # + status 字段 + 迁移
  drama_shot_master/ui/widgets/daw/daw_track_view.py   # overlay 片段按 status 上色（扩展 3c）
  drama_shot_master/ui/widgets/soundtrack_editor.py    # _on_rubber_band 实装 + worker 接线
  tests/test_sound_track_agent/test_overlay_session.py # + status round-trip/迁移
```

## 范围

- ✅ 框选 → 对话框（LLM 预填）→ 异步生成（lane 占位/失败重试）→ 落库渲染播放。
- ✅ OverlaySegment.status + 迁移；BGM/SFX 单片段生成复用现有管线 + 缓存。
- ❌ 多 seed 候选选优、生成打分、片段拖拽/缩放编辑（仍非本期）、固定轨生成逻辑改动。
- 依赖 3c 落地（占位/状态渲染 + `_refresh_overlay_view`）。

## 依赖说明

3d 实现须在 3c（动态轨渲染）合并后开始：占位块/失败块复用 3c 的 overlay 片段绘制并按 status 扩展；刷新走 3c 的 `_refresh_overlay_view`。3c 若有方法命名微调，本 spec 接线处随之对齐。
