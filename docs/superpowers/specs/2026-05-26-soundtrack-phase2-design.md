# 配乐功能第二期 · 设计（试听选优 + 卡点 + 缓存 + 设置 + 输出路径）

> 日期：2026-05-26
> 前置：第一期骨架已端到端跑通（用户实测能生成候选 BGM）。本期在任务窗内补半自动交互，并加两个用户需求（输出路径可设、设置菜单加配乐项）。

---

## 1. 本期范围（已确认）

| 项 | 内容 |
|---|---|
| 试听选优 | 任务窗内每段播放候选 BGM（QMediaPlayer）→ 选定 → 不满意重生成某段 |
| 卡点编辑 | 时间轴可视化增删/微调 accent_points（第一版简化交互：按钮增删 + 数值微调，纯拖拽后续打磨） |
| 输出路径（需求1） | 全局默认（设置里）+ 单任务可覆盖 |
| 设置菜单（需求2） | 顶部[设置]新增[配乐…]对话框，放 WorkflowID 等不常改项，释放面板注意力 |
| 缓存/续跑（问题3） | 打开任务读已存 session + 幂等不重生成 + 重生成某段入口 |

**不在本期**：纯拖拽卡点精修（第一版用按钮+数值）。

## 2. 架构：任务窗页签 + 组件拆分（方案 A）

```
SoundtrackTaskWindow (QTabWidget)        ← 改造：单页 → 3 页签 + 共享 ScoringSession
├─ ① 配置+生成   现有表单（精简）+ 段落预览 + 进度 + 出片
├─ ② 试听选优   SegmentReviewWidget（新文件）
└─ ③ 卡点       AccentEditorWidget（新文件）

drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py   ← 新（需求2）
drama_shot_master/config.py                                  ← 加 4 个 soundtrack_* 字段
drama_shot_master/ui/main_window.py                          ← [设置]菜单加[配乐…]入口
sound_track_agent/facade.py                                  ← 加 set_chosen / regenerate_segment / load_session
```

**可拆性不变**：新增的是宿主侧 widget/dialog/config 字段（删配乐功能时一并删）+ facade 少量辅助函数（agent 内、仍不 import 宿主）。GUI→agent 仍只经 facade。

## 3. 组件设计

### 3.1 SegmentReviewWidget（②试听选优，新文件 `ui/widgets/segment_review_widget.py`）

- 输入：`ScoringSession`。每段渲染一张卡片：段序号/时间/情绪标签 + 候选按钮（每候选一个，选中高亮）+ 内嵌 `QMediaPlayer`+`QAudioOutput` 播放进度条 + 「↻ 重生成」按钮。
- 选中候选 → 调 `facade.set_chosen(session, seg_idx, cand_idx)` 写 `SegmentScore.chosen_candidate`。
- 「重生成」→ 发信号给任务窗 → 任务窗用 worker 跑 `facade.regenerate_segment`（对该段重跑生成，新 seed），完成刷新该卡片。
- 信号：`chosenChanged()`（任一段选定变化 → 任务窗重算"是否全选定/可出片"）、`regenerateRequested(int seg_idx)`。
- 全部段 `chosen_candidate is not None` 才允许出片；未选定段卡片标橙色。
- 单一播放器实例：切段/切候选时 `stop()` 旧的再播新的（避免多路并发）。

### 3.2 AccentEditorWidget（③卡点，新文件 `ui/widgets/accent_editor_widget.py`）

- 输入：`ScoringSession`（用 segments 画段落带做参照，accent_points 画爆点）。
- 自绘 `QGraphicsView`（复用 timeline_widget 的深色画布套路）或简化为带刻度的自绘 widget：刻度尺 + 段落带（只读）+ 爆点行（菱形标记）。
- 交互（第一版务实）：点击选中爆点 → `−0.1s/+0.1s` 按钮微调或数值框直填；「🗑删除」；「+ 在播放头/指定时间新增」。拖拽微调作为增强、非第一版必需。
- 编辑写回 `session.accent_points`（confirmed=True），落盘。
- 信号：`accentsChanged()` → 任务窗标记 session 脏、落盘。

### 3.3 SoundtrackSettingsDialog（需求2，新文件 `ui/dialogs/soundtrack_settings_dialog.py`）

沿用 `runninghub_settings_dialog` 的 QFormLayout + OK/Cancel + `cfg.update_settings(...)` 模式。字段：

| UI 字段 | config 字段 | 默认 |
|---|---|---|
| ACE-Step Workflow ID | `soundtrack_workflow_id` | `2059090557116440578` |
| 默认输出目录（浏览） | `soundtrack_output_dir` | `""`（空=用 video_output_dir/soundtrack） |
| 默认候选数 | `soundtrack_seeds_count` | `2` |
| crossfade 时长(秒) | `soundtrack_crossfade` | `0.5` |

挂载：main_window `_build_ui` 的[设置]菜单加 `QAction("配乐…")` → `_open_soundtrack_settings`。

### 3.4 任务窗①页精简

- 移除常驻 Workflow ID / 候选数输入框（挪进设置对话框，从 cfg 读默认）。
- 保留：成片 MP4（浏览）、总风格（多行）、**本任务输出目录**（可选，覆盖全局默认）、"停在"单选、开始/进度/打开目录。

## 4. facade 新增辅助（agent 内，不 import 宿主）

```python
def load_session(work_dir) -> ScoringSession | None:
    """work_dir/session.json 存在则加载，否则 None（供打开任务续跑/缓存）。"""

def set_chosen(session, seg_index: int, cand_index: int) -> None:
    """写 SegmentScore.chosen_candidate；越界抛 ValueError。"""

def regenerate_segment(session, seg_index, work_dir, *, cfg, workflow_id,
                       seeds_count=2, stages=None) -> ScoringSession:
    """对单段重跑 generate（新 seed 区间），替换该段 candidates、清 chosen。
    stages 可注入（测试 fake）。其它段不动。"""
```

`advance` 增强：第一步先 `load_session(work_dir)`，存在则以它为基础推进（续跑）；幂等由 pipeline 现有 status 机制保证。

## 5. 输出路径解析（需求1）

任务窗出片时，work_dir/输出目录解析优先级：
```
任务自带 output_dir（①页填了） → cfg.soundtrack_output_dir（设置全局默认）
  → cfg.video_output_dir/soundtrack（兜底）
```
解析逻辑放任务窗（宿主侧，读 cfg）；facade 仍只接收最终 work_dir 参数。

## 6. 缓存/续跑（问题3）

- **打开任务**：`_open_soundtrack_window` → 任务窗构造时 `facade.load_session(work_dir)`，存在则各页按 session 现状填充（段落/候选/选定/爆点），状态置"可续跑"。
- **不重生成**：`advance` 幂等跳过已完成段（pipeline status 机制，已有）。
- **重生成某段**：②页「↻」→ `regenerate_segment`（只动该段）。
- **缓存键**：`source_hash`（MP4 内容 hash，已有）作 work_dir 名的一部分，天然隔离不同成片。

## 7. 错误处理 / 线程

- 所有长任务（生成/重生成/出片）走 `FunctionWorker`，进度经 `QTimer.singleShot(0,...)` 回主线程（沿用第一期）。
- QMediaPlayer 仅播放本地文件，错误（文件缺失）弹提示不崩。
- 设置/路径缺失：facade 调用抛异常 → worker failed → 任务窗弹错。

## 8. 测试策略

- **facade 新函数**（`test_facade.py` 追加）：`load_session`（存在/不存在）、`set_chosen`（写入/越界）、`regenerate_segment`（注入 fake stages，验证只动目标段 + 清 chosen）。mock 重型。
- **config**（`test_config.py` 追加）：4 个 soundtrack_* 字段默认值 + roundtrip。
- **UI widgets**（offscreen 冒烟，用 conda python `/root/miniconda3/envs/UniRig/bin/python`）：SegmentReviewWidget 按 session 渲染段卡片数、选定写 chosen；AccentEditorWidget 按 accent_points 渲染、删除/微调改 session；SoundtrackSettingsDialog 构造+读写 cfg；任务窗 3 页签构造。
- QMediaPlayer 真实播放不自动测（WSL 无音频后端，靠用户真机）。

## 9. 实现时定（不阻塞）

- AccentEditorWidget 自绘 vs QGraphicsView：实现时按 timeline_widget 现状择简。
- 播放头概念是否需要（"在播放头新增"）：第一版可先用"在指定数值新增"，播放头增强可选。
- regenerate_segment 的 seed 取值（避免与已有候选重复）：用递增/随机，实现时定。

## 10. 改动清单（本期）

| 文件 | 改动 |
|---|---|
| `sound_track_agent/facade.py` | 加 load_session/set_chosen/regenerate_segment + advance 续跑 |
| `drama_shot_master/config.py` | 加 4 个 soundtrack_* 字段 |
| `drama_shot_master/ui/widgets/segment_review_widget.py` | 新（②试听选优） |
| `drama_shot_master/ui/widgets/accent_editor_widget.py` | 新（③卡点） |
| `drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py` | 新（需求2） |
| `drama_shot_master/ui/windows/soundtrack_task_window.py` | 改：单页→3 页签 + 精简①页 + 输出路径解析 + 续跑加载 |
| `drama_shot_master/ui/main_window.py` | [设置]菜单加[配乐…] |
| tests：test_facade / test_config / test_ui 多个 | 新增/追加 |

## 11. 一句话总结

任务窗改 3 页签（配置生成 / 试听选优 / 卡点）；②页 QMediaPlayer 试听每段候选并选定、可单段重生成；③页时间轴可视化增删微调爆点；WorkflowID 等挪进新增的[设置]→[配乐]对话框、输出路径全局默认+单任务覆盖；打开任务读已存 session 续跑、幂等不重生成。facade 加 load_session/set_chosen/regenerate_segment，仍只通过 facade 与 GUI 交互、可拆边界不变。
