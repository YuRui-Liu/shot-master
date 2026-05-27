# Phase 2：生成类功能改窗内主-详 + 浮出独立窗 设计

- 日期：2026-05-27
- 关系：原 UX spec [`2026-05-27-gui-shell-redesign-design.md`](2026-05-27-gui-shell-redesign-design.md) §4.3b 的落地；
  建立在原生 PySide6 外壳之上（`AppShell(QMainWindow)`，已去 qfluentwidgets，见
  [`…-stock-pyside6-design.md`](2026-05-27-gui-shell-stock-pyside6-design.md)）。
- 本期为**视频试点**：仅「视频生成」改为主-详+浮出；图片/配音/配乐保持现状（双击开窗），待后续 replicate plan。

---

## 1. 目标与约束

把生成类功能从「任务列表 + 双击另开独立窗」改为「窗内主-详（左任务列表 / 右内嵌编辑器）+
「⧉ 浮出独立窗」按钮」。三条已确认决策：

1. **每任务缓存一个编辑器**：详情区是 `QStackedWidget`，每个任务首次选中时懒建编辑器并缓存；
   切任务不丢未存编辑；提交在编辑器自带后台线程跑，编辑器不可见也照跑 →
   **窗内即可并行出视频/图/音**，不依赖开窗。
2. **浮出 = reparent 活编辑器进窗**：同一编辑器实例移入独立窗，状态/进度零丢失、无双份；
   详情区显示占位；关窗时编辑器收回详情区。单一数据源。
3. **视频试点先行**：仅视频生成切换；其余三功能不变；reparent 机制验证后再复制。

**不变**：所有功能算法/provider/数据模型/stores/config 持久化；图片/配音/配乐本期行为不变。

## 2. 组件

### 2.1 `TaskWorkspacePage(QWidget)`（新，通用，可复用）
`drama_shot_master/ui/pages/task_workspace_page.py`。结构：`QSplitter(Horizontal)[ master | detail ]`。

- **master（左）**：注入的 `*TaskManagerPanel`（复用现有，新增 `taskSelected(object)` 信号 —— 见 §2.2）。
- **detail（右）**：上为**详情头条**（`QHBoxLayout`：任务名 + 状态 + **「⧉ 浮出独立窗」按钮**，按钮属 page、点了调 `pop_out(current_task)`），
  下为 `QStackedWidget`，index 0 为占位页 `_PlaceholderPanel`（文案：未选时「选择左侧任务以编辑」，
  浮出时「该任务已在独立窗编辑」）。其余为缓存的编辑器。编辑器自身的「生成/提交」等按钮仍在编辑器内，不动。
- 构造参数（注入点，使其与具体功能解耦）：
  - `manager`：master 面板实例。
  - `editor_factory(task) -> QWidget`：按任务建编辑器（视频=`VideoPanel(state, cfg, TimelineModel.from_dict(task.timeline))`）。
  - `wire_editor(editor, task) -> None`：把该编辑器的状态/结果/脏信号接到宿主回调（见 §3）。
  - `title_for(task) -> str`：浮出窗标题（如 `f"视频任务 · {task.name}"`）。
- 状态：`self._editors: dict[str, QWidget]`（task_id→editor）、`self._detached: dict[str, DetachedEditorWindow]`。
- 行为：
  - `_on_task_selected(task)`：若 task 已浮出 → 详情区切占位；否则 `_ensure_editor(task)` 后切到该编辑器。
  - `_ensure_editor(task)`：缓存命中直接返回；否则 `editor_factory` 建、`wire_editor` 接线、`addWidget` 入栈、存入 `_editors`。
  - `pop_out(task)`：把 `_editors[task]` 从栈中 `removeWidget` 后放进新建 `DetachedEditorWindow`，详情区切占位，记入 `_detached`；窗 `closed`→`_dock_back(task)`。
  - `_dock_back(task)`：编辑器 `addWidget` 回栈，若当前选中即该任务则切回显示，移除 `_detached` 记录。
  - `current_task()`/`selected_task` 由 master 维护。

### 2.2 `VideoTaskManagerPanel` 改动（master 复用）
- 新增信号 `taskSelected = Signal(object)`（发选中的 `VideoTask`），在表格 `currentItemChanged`/行选中时发。
- 把原「双击 → open_window_cb」语义改为「单击选中 → taskSelected」。浮出按钮**不在 master**，在 page 详情头条（§2.1）。
- 保留 新建/复制/删除/重命名 与 `taskRenamed`、`set_task_status`/`clear_task_status`/`refresh`。
- 试点期 `open_window_cb`/`close_window_cb` 构造参数不再需要（开窗逻辑移入 page）：移除这两个参数，或传 `None` 占位。**取移除**：面板只负责任务列表与 `taskSelected`，更纯粹。

### 2.3 `DetachedEditorWindow(QMainWindow)`（新，通用）
`drama_shot_master/ui/windows/detached_editor_window.py`。取代试点中 `VideoTaskWindow` 的「宿主+转发」职责（转发已移到 page 的 `wire_editor`，故此窗只需承载）：
- 构造：`DetachedEditorWindow(editor, title, task_id)`；`setCentralWidget(editor)`；`setWindowTitle(title)`；`resize(1100, 820)`。
- 信号：`closed = Signal(str)`（task_id）。`closeEvent` 发 `closed` 后 `super().closeEvent()`（不销毁 editor —— page 会 reparent 回收）。
- `showEvent`：`apply_window_icon(self)` + `apply_dark_titlebar(self)`（与 AppShell 一致）。
- `set_title(name)`：改名同步。
- **关键**：关窗不删 editor。Qt 中 `setCentralWidget(None)` 或 page `addWidget(editor)` 会把 editor reparent 走；为防关窗连带删 editor，dock_back 须在 window 真正析构前把 editor 取出（在 `closed` 槽里先 `editor.setParent(None)`/`addWidget`）。

## 3. 信号接线与持久化（page 统一负责）
`wire_editor(editor, task)` 把编辑器信号接到宿主已有的 store 回调（**复用 AppShell 现成方法，不改其逻辑**）：
- 视频：`editor.submitStarted → status「生成中」`、`editor.submitDone → result(mp4)`、`editor.submitFailed → status「失败」`、
  以及 timeline 脏 → `timelineDirty(task_id, model.to_dict())`。这些目前在 `VideoTaskWindow.__init__` 里做，
  现整体搬进 `wire_editor`（一处接线，inline/popped 都有效）。
- 宿主（AppShell）侧的 `_on_task_status/_on_task_result/_on_task_dirty/_persist_tasks` **保持不变**，
  由 page 在构造时以回调注入（page 不直接 import AppShell）。
- 落盘时机：编辑器 dirty 即触发 store.update + persist（与现状一致）；关闭软件时 AppShell `closeEvent`
  仍对「打开中的任务」落盘 —— 改为对 page 持有的所有 `_editors` 落盘（page 暴露
  `flush_all()` 供 AppShell 调）。

## 4. AppShell 接入（试点）
- `_build_pages` 中 `video_gen` 的构造从 `VideoTaskManagerPanel(...)`（直接作页）改为
  `TaskWorkspacePage(manager=VideoTaskManagerPanel(...), editor_factory=…, wire_editor=…, title_for=…)`。
- AppShell 原 `_open_task_window/_close_task_window/_on_task_window_closed/_open_task_windows` 等视频开窗逻辑：
  试点期由 page 内部 `pop_out`/`_dock_back`/`_detached` 取代；AppShell 删除这些视频专用开窗方法（dub/imggen/soundtrack 的同类方法**保留不动**）。
- `_video_manager()` 仍需可达（用于 `set_task_status` 等）：改为返回 `page.manager`。
- AppShell `closeEvent` 里视频部分：调 `video_page.flush_all()` 代替遍历 `_open_task_windows`。
- `_wire` 中视频 `taskRenamed` 连接：改连 `page.manager.taskRenamed`，浮出窗存在时同步标题（page 处理）。

## 5. 复用与处置一览

| 现有 | 处置 |
|------|------|
| `VideoTaskManagerPanel` | 复用为 master；加 `taskSelected` 信号；移除 open/close 窗回调参数；浮出按钮归 page |
| `VideoPanel`（编辑器） | **完全不变**，被 `editor_factory` 建，inline/popped 共用一实例 |
| `VideoTaskWindow` | **试点期退役**（职责拆入 page + DetachedEditorWindow）；删除其文件与对应 smoke 测试或改测 page |
| `DubTaskWindow`/`ImgGenTaskWindow`/`SoundtrackTaskWindow` + 其 manager | **本期不动**，仍双击开窗 |
| AppShell 视频开窗方法 | 退役（dub/imggen/soundtrack 的保留） |
| stores/core/config | 零改动 |

## 6. 测试（headless，沿用 offscreen smoke 惯例）
新 `tests/test_ui/test_task_workspace_page_smoke.py`：
- 选中任务 → 详情区显示该任务编辑器（`page._editors` 含其 id；stack 当前为该编辑器）。
- 选中第二个任务 → 两个编辑器都在 `_editors`（并行：均存活）。
- `pop_out(task)` → 编辑器进入一个 `DetachedEditorWindow`、详情区切占位、`_detached` 含其 id。
- 关闭该窗（emit closed / close()）→ 编辑器回到 stack、`_detached` 不含其 id。
- 脏信号：编辑器发 dirty → 注入的回调被调用（用 spy 回调验证 inline 与 popped 两态都触发）。
- `flush_all()` 调用不抛、对所有缓存编辑器执行落盘回调。
AppShell smoke 补充：`video_gen` 页是 `TaskWorkspacePage`；`_video_manager()` 返回其 manager。
其余既有测试保持绿。`grep -r qfluentwidgets` 仍为空。

## 7. 风险
- **reparent 生命周期**：关窗时必须先把 editor 从窗取出再让窗析构，否则 editor 被连带删除。
  实现：`DetachedEditorWindow.closed` 槽里 page 立即 `editor.setParent(None)` 再 `stack.addWidget(editor)`；
  `DetachedEditorWindow` 自身不持有 editor 所有权语义（不在 closeEvent 删 editor）。headless 测试覆盖此路径。
- **后台线程与可见性**：提交线程在 `VideoPanel` 内部，独立于 parent；切页/浮出不影响。需确认
  `VideoPanel` 的提交不依赖 `isVisible()`（读 VideoPanel 确认；若依赖，记为风险并在 plan 处理）。
- **master 选择信号**：现 `VideoTaskManagerPanel` 触发方式（双击 vs 选中）需读代码确认后接 `taskSelected`。
- **AppShell 视频开窗方法删除**：确认 dub/imggen/soundtrack 的同名前缀方法不被误删（它们独立保留）。

## 8. 非目标（YAGNI）
- 不动图片/配音/配乐（本期）；它们的主-详化是后续 replicate plan。
- 不做浮出窗的位置记忆/多详情分屏/拖拽停靠。
- 不改编辑器内部 UI。

## 9. 后续（各自 plan）
- replicate-1：图片生成 + 配音改 `TaskWorkspacePage`（结构同视频，机械复制 factory/wire）。
- replicate-2：配乐改造（`SoundtrackPanel` try-import 与 321 行窗的特殊性单独处理）。
- 之后回到原 UX 路线 Phase 3（统一设置页+浅色）/Phase 4（全局任务中心）/Phase 5（精修+折叠动画）。
