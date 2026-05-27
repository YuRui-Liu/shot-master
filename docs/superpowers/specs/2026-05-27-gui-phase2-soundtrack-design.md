# Phase 2 配乐改主-详+浮出 设计（SoundtrackEditor 抽取）

- 日期：2026-05-27
- 关系：Phase 2 主-详的最后一块。复用通用 `TaskWorkspacePage` + `DetachedEditorWindow`
  （见 [`2026-05-27-gui-phase2-master-detail-design.md`](2026-05-27-gui-phase2-master-detail-design.md)）。
  视频/图片/配音已完成；本期收口配乐。
- 配乐是特殊例：编辑器逻辑长在 321 行 `SoundtrackTaskWindow` 里、任务是 `cfg.soundtrack_tasks` 的 dict（无 *TaskStore）、
  依赖可能缺失（try-import 兜底）、session 落盘到磁盘。

---

## 1. 目标与约束

把配乐从「任务列表 + 双击另开 `SoundtrackTaskWindow`」改为窗内主-详（左 `SoundtrackPanel` 列表 / 右内嵌 `SoundtrackEditor`）+「⧉ 浮出独立窗」，复用通用组件。

**已确认决策：**
1. **抽出 `SoundtrackEditor(QWidget)`**：把 `SoundtrackTaskWindow` 的全部编辑器逻辑搬进一个 QWidget；**退役 `SoundtrackTaskWindow`**（浮出由通用 `DetachedEditorWindow` 承载）。
2. **薄 live-view 包装**：dict 任务用一个轻量视图对象（`.id/.name/.payload` 指向原 dict）暴露给通用页；**`TaskWorkspacePage` 零改动**。
3. **持久化映射**：`to_payload()`={mp4,style,output_dir}；session.json 仍由编辑器自动落盘。

**不变**：`sound_track_agent.facade` / session 模型 / `SegmentReviewWidget` / `AccentEditorWidget` / 其它三个生成功能 / config 结构。

## 2. 组件

### 2.1 `SoundtrackEditor(QWidget)`（新）
位置 `drama_shot_master/ui/widgets/soundtrack_editor.py`。从 `SoundtrackTaskWindow` 抽取：
- ctor `(task: dict, cfg, work_root, parent=None)`：存 `self._task=task`（活 dict）、`self.cfg`、`self._work_root=Path(work_root)`；`self._worker/_session/_review/_accent=None`；`_build_ui()` + `_try_load_existing()`。
- `_build_ui`：把窗的 `self.setCentralWidget(self.tabs)` 改为 `root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.addWidget(self.tabs)`。tabs 三页（① 配置+生成 / ② 试听选优 / ③ 卡点）构造逻辑原样。
- **原样搬入**（self 由窗实例改为编辑器实例，方法体不变）：`task_id`(property)、`_work_dir`、`_resolve_output_base`、`_build_config_tab`、`_try_load_existing`、`_mount_session_tabs`、`_persist_session`、`_on_chosen_changed`、`_worker_busy`、`_browse_mp4`、`_browse_out`、`_post_progress`、`_on_start`、`_on_export`、`_run_pipeline`、`_on_regenerate`、`_post_seg_preview`、`_on_done`、`_on_regen_done`、`_on_failed`、`_update_preview_enabled`、`_on_preview`、`_open_output_dir`。
- 信号：保留 `statusChanged = Signal(str, str)`（(task_id,status)）、`resultReady = Signal(str, str)`（(task_id,output)）；**删 `closed` 信号**与 `closeEvent`（widget 不需要）。
- 新增 `to_payload(self) -> dict`：`return {"mp4": self.mp4_edit.text().strip(), "style": self.style_edit.toPlainText().strip(), "output_dir": self.out_edit.text().strip()}`。供页在切换/浮出/flush 时保存用户对这三项的编辑（不必跑 pipeline）。
- 注意：`_run_pipeline` 里原有 `self._task["mp4"/"style"/"output_dir"]=...` 的就地写仍保留（_task 是活 dict）；`to_payload` 是页持久化的读取面，二者并存无害。

### 2.2 `_SoundtrackTaskView`（薄 live-view）
放在 `soundtrack_panel.py` 顶部（或同模块小类）。
```python
class _SoundtrackTaskView:
    """把 cfg.soundtrack_tasks 的 dict 暴露成 .id/.name/.payload（活引用），
    供通用 TaskWorkspacePage（按属性访问）消费。"""
    def __init__(self, d: dict):
        self._d = d
    @property
    def id(self): return self._d.get("id", "")
    @property
    def name(self): return self._d.get("name", "")
    @property
    def payload(self): return self._d
```
每次选中/新建时新建一个 view 包住当前 dict；`.id` 为字符串，缓存/浮出/同名比较均按 id 字符串，故每次新建 view 不影响 `TaskWorkspacePage` 的按 id 缓存。

### 2.3 `SoundtrackPanel` 改造
现状：ctor `(state, cfg, open_window_cb, persist_cb)`（2 cb，无 store，无 taskRenamed），`_tasks()` 读 `cfg.soundtrack_tasks`，refresh 用 `blockSignals`，`_selected()` 返回 dict。
改动：
1. 信号加 `taskSelected = Signal(object)`、`taskDeleted = Signal(str)`、`taskRenamed = Signal(str, str)`（它当前没有 taskRenamed）。
2. `_build_ui`：删「打开」按钮(`self.btn_open`)及其 connect 与 `_on_open` 方法；删 `itemDoubleClicked.connect(self._on_double_clicked)` 与 `_on_double_clicked`（col-0 内联改名由 itemChanged 处理，保留）；连 `self.table.itemSelectionChanged.connect(self._on_selection_changed)`。
3. 新增 `_on_selection_changed`：refresh 用 blockSignals 已天然防误发；实现：
   ```python
   def _on_selection_changed(self):
       d = self._selected()
       if d is not None:
           self.taskSelected.emit(_SoundtrackTaskView(d))
   ```
4. `_on_item_changed`（rename）末尾在 `_persist_cb()` 之后加 `self.taskRenamed.emit(tid, new_name)`。
5. `_on_new`：建 dict + persist + refresh 后改为选中新行（不再 `_open_window_cb`）：用 `_select_task(task["id"])`（按 id 在 col-0 找行 setCurrentCell(r,0)→触发 taskSelected）。
6. `_on_del`：删 dict + persist + refresh 后加 `self.taskDeleted.emit(tid)`。
7. ctor 形参保留 `open_window_cb`（AppShell 传 None；不再调用）。`persist_cb` 仍用。

### 2.4 退役 `SoundtrackTaskWindow`
删除 `drama_shot_master/ui/windows/soundtrack_task_window.py`，清引用（AppShell `_open_soundtrack_window` 等删除）。

## 3. AppShell 接入（try-import 兜底）

- `_build_pages`：`"soundtrack": self._make_soundtrack_page`（替换 `_try_make_soundtrack_panel`）。删 `self._soundtrack_windows`（若在 __init__/build_pages 初始化）。
- `_make_soundtrack_page`：
  ```python
  def _make_soundtrack_page(self):
      try:
          from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
          from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
          from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
      except Exception as e:
          import logging
          logging.getLogger(__name__).warning("配乐面板不可用，已跳过: %s", e)
          from PySide6.QtWidgets import QWidget
          return QWidget()
      from pathlib import Path
      work_root = Path(getattr(self.cfg, "video_output_dir", "") or ".") / "soundtrack"
      manager = SoundtrackPanel(self.state, self.cfg, None, self._persist_soundtrack)

      def editor_factory(view):
          return SoundtrackEditor(view.payload, self.cfg, work_root)

      def wire_editor(editor, view):
          editor.statusChanged.connect(self._on_soundtrack_status)   # (task_id,status)
          editor.resultReady.connect(self._on_soundtrack_result)     # (task_id,output)

      page = TaskWorkspacePage(
          manager=manager,
          editor_factory=editor_factory,
          wire_editor=wire_editor,
          payload_of=lambda ed: ed.to_payload(),
          on_persist=self._on_soundtrack_dirty,
          title_for=lambda view: f"配乐 · {view.name}",
      )
      manager.taskRenamed.connect(self._on_soundtrack_renamed)
      manager.taskDeleted.connect(page.discard_editor)
      return page
  ```
- `_soundtrack_panel()`：`p = self.pages.get("soundtrack"); return getattr(p, "manager", None)`（兜底裸 QWidget 时返回 None；现有 `_on_soundtrack_status/_result` 已对 `_soundtrack_panel()` 做 `hasattr(p,"refresh")` 守卫，需改为对 manager 守卫——见下）。
- 新增 `_on_soundtrack_dirty(self, task_id, payload)`：
  ```python
  for t in getattr(self.cfg, "soundtrack_tasks", []):
      if t.get("id") == task_id:
          t.update(payload)    # mp4/style/output_dir
          break
  self._persist_soundtrack()
  ```
- 新增 `_on_soundtrack_renamed(self, task_id, name)`：`self.pages["soundtrack"].update_task_name(task_id, name)`（兜底时 pages["soundtrack"] 无 update_task_name → 守卫 hasattr）。
- 调整 `_on_soundtrack_status`/`_on_soundtrack_result`：现读 `self._soundtrack_panel()` 并 `hasattr(p,"refresh")`。改为取 manager：`m = self._soundtrack_panel(); if m is not None and hasattr(m,"refresh"): m.refresh()`（其余更新 cfg dict + persist 不变）。
- 删除 `_open_soundtrack_window`、`_on_soundtrack_window_closed`、`_soundtrack_windows`。
- `_wire`：statusMessage 循环对 TaskWorkspacePage 走 `page.manager.statusMessage`——但兜底 QWidget 无 manager 且非 BasePanel，`getattr(page,"manager",page)` + `hasattr(...,"statusMessage")` 已守卫（视频期实现），确认无碍。
- `closeEvent`：配乐当前可能**没有**落盘块（session 自动落盘、窗关时不持久 task dict）。实施时先核对 closeEvent 是否有配乐相关遍历（如 `_soundtrack_windows`）；有则替换、无则**新增**一段：`sp = self.pages.get("soundtrack"); if sp is not None and hasattr(sp, "flush_all"): sp.flush_all()`（保存缓存编辑器里未跑 pipeline 的 mp4/style/output_dir 编辑；兜底裸 QWidget 无 flush_all → 守卫跳过）。

## 4. 测试（headless offscreen smoke）
- 新 `tests/test_ui/test_soundtrack_editor_smoke.py`：`SoundtrackEditor(task_dict, cfg, work_root)` 构造不崩；`tabs.count()==3`；`style_edit` 初值=task["style"]；`to_payload()` 返回含 mp4/style/output_dir 三键且值取自 widgets；无 session 时不挂、有 session（monkeypatch facade.load_session 返回桩）时 `_mount_session_tabs` 不崩。迁移 `test_soundtrack_window_smoke.py` 里适用的断言（导出按钮存在、预览禁用→启用、输出路径回退）到 editor，删除针对窗的用例。
- 新 `tests/test_ui/test_soundtrack_workspace_smoke.py`：AppShell `pages["soundtrack"]` 是 `TaskWorkspacePage`（依赖可用时）且 `manager` 是 `SoundtrackPanel`；选中任务建 `SoundtrackEditor`；manager 发 taskSelected/taskDeleted/taskRenamed。
- SoundtrackPanel 单测：taskSelected 发 view（.id/.name 正确）；`_new` 后选中新行。
- 兜底：monkeypatch 让 import 抛错，`_make_soundtrack_page` 返回 QWidget 不崩（可选，若 headless 难做则跳过并记录）。
- 验收：`grep -r qfluentwidgets` 为空；`python -m pytest tests/` 全绿；四个生成页：imggen/dub/video/soundtrack 均 `TaskWorkspacePage`（soundtrack 依赖可用时）。

## 5. 非目标 / 风险
- 不改 facade/session/子控件；不改其它三功能。
- **抽取风险**：`SoundtrackTaskWindow` 内 `self.xxx` 引用众多（mp4_edit/style_edit/out_edit/stop_combo/seg_preview/btn_*/progress/tabs/_review_holder/_accent_holder/_review/_accent/_session/_worker），搬入编辑器后 `self` 即编辑器，逐一核对无遗漏；`QMessageBox`/`QFileDialog` 的 `self` 父窗变为编辑器 widget（合法）。
- **session 落盘路径**：`_work_dir`/`_resolve_output_base` 依赖 `self._task`(dict) + `self.cfg`，搬入后不变。
- **try-import 兜底**：真实环境依赖齐全时走正常路径；兜底分支用 monkeypatch 模拟。
- 迁移后 `test_soundtrack_window_smoke.py` 删除或重写为 editor 版，避免悬空 import。

## 6. 后续
- 配乐完成后，Phase 2 全部生成功能主-详化收口。
- 再后：原 UX 路线 Phase 3（统一设置页+浅色）/ Phase 4（全局任务中心抽屉）/ Phase 5（精修：侧栏折叠动画、图片面板「重命名」按钮统一等）。
