# Phase 2（视频试点）主-详 + 浮出独立窗 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「视频生成」从「任务列表+双击开窗」改为窗内主-详（左列表/右内嵌缓存编辑器）+「⧉ 浮出独立窗」，支持窗内并行；图片/配音/配乐本期不动。

**Architecture:** 新增通用 `TaskWorkspacePage`（`QSplitter[manager | 详情头条+QStackedWidget缓存编辑器]`，注入 editor_factory/wire/payload/persist/title）与通用 `DetachedEditorWindow`（承载 reparent 出去的活编辑器，关窗收回）。`VideoTaskManagerPanel` 加 `taskSelected` 信号复用为 master。`AppShell` 把 `video_gen` 页换成 `TaskWorkspacePage`，复用现有 store 回调与 `VideoPanel`（零改动）。

**Tech Stack:** PySide6 6.11（QSplitter/QStackedWidget/QMainWindow reparent）、pytest 9（offscreen smoke）。

**Spec:** `docs/superpowers/specs/2026-05-27-gui-phase2-master-detail-design.md`

**排序原则（每次提交保持可用/绿）：** 先**纯加** `taskSelected`（不删旧开窗），再建独立组件（DetachedEditorWindow / TaskWorkspacePage，旁路存在、未接线），最后在 T4 **原子切换**（接入 page 的同时才移除旧开窗 UI/方法），T5 删 `VideoTaskWindow`。

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| Modify | `drama_shot_master/ui/panels/video_task_manager_panel.py` | 加 `taskSelected` 信号；T4 再去 打开按钮/双击开窗、cbs 可选、`_on_new` 选中新行 |
| Create | `drama_shot_master/ui/windows/detached_editor_window.py` | 通用 `DetachedEditorWindow`（承载 reparent 编辑器，关窗发 closed，不删 editor）|
| Create | `drama_shot_master/ui/pages/task_workspace_page.py` | 通用 `TaskWorkspacePage`（主-详+缓存编辑器+浮出/收回+flush_all）|
| Modify | `drama_shot_master/ui/app_shell.py` | T4：video_gen 换 page；删视频开窗方法；`_video_manager()`→page.manager；closeEvent 用 flush_all |
| Delete | `drama_shot_master/ui/windows/video_task_window.py` | T5：退役 |
| Create | `tests/test_ui/test_detached_editor_window_smoke.py` | T2 |
| Create | `tests/test_ui/test_task_workspace_page_smoke.py` | T3 |
| Modify | `tests/test_ui/test_app_shell_smoke.py` | T4：video_gen 是 TaskWorkspacePage |

---

## Task 1: VideoTaskManagerPanel 加 `taskSelected`（纯加）

**Files:**
- Modify: `drama_shot_master/ui/panels/video_task_manager_panel.py`
- Test: `tests/test_ui/test_video_manager_selection_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_video_manager_selection_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.config import load_config
from drama_shot_master.ui.state import AppState
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel


def _app():
    return QApplication.instance() or QApplication([])


def _panel():
    store = VideoTaskStore.from_list([])
    store.add("任务A", {}); store.add("任务B", {})
    return VideoTaskManagerPanel(AppState(), load_config(), store,
                                 None, None, lambda: None), store


def test_selecting_row_emits_task_selected():
    _app()
    panel, store = _panel()
    seen = []
    panel.taskSelected.connect(seen.append)
    panel.table.setCurrentCell(0, 0)
    assert seen and seen[-1].id == store.all()[0].id


def test_open_close_cb_optional_none_safe():
    _app()
    # open/close cb 传 None 不应在新建/删除时抛
    store = VideoTaskStore.from_list([])
    panel = VideoTaskManagerPanel(AppState(), load_config(), store,
                                  None, None, lambda: None)
    panel._on_new()             # None open cb 不抛
    assert len(store.all()) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master && python -m pytest tests/test_ui/test_video_manager_selection_smoke.py -q`
Expected: FAIL（无 `taskSelected`；或 `_on_new` 调 None open cb 抛 TypeError）

- [ ] **Step 3: 改 video_task_manager_panel.py（纯加，不删旧行为）**

在类信号区加：
```python
    taskSelected = Signal(object)    # 选中的 VideoTask（主-详用）
```
在 `_build_ui` 末尾（`self.btn_del.clicked.connect(self._on_del)` 之后）加选择信号转发：
```python
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
```
新增方法：
```python
    def _on_selection_changed(self):
        tid = self._selected_task_id()
        if not tid:
            return
        t = self.store.get(tid)
        if t is not None:
            self.taskSelected.emit(t)

    def task_for_row(self):
        """当前选中行对应的 task（无选中返回 None）。"""
        tid = self._selected_task_id()
        return self.store.get(tid) if tid else None
```
把 `_open_window_cb`/`_close_window_cb` 调用改为 None 安全（最小改动，保留双击开窗行为）：
- `_on_new` 末尾 `self._open_window_cb(t)` → `if self._open_window_cb: self._open_window_cb(t)`
- `_on_open`/`_on_double_clicked` 内 `self._open_window_cb(t)` → 同样加 `if self._open_window_cb:`
- `_on_del` 内 `self._close_window_cb(tid)` → `if self._close_window_cb: self._close_window_cb(tid)`

（本任务**不**删 打开按钮/双击；只加 `taskSelected` 与 None 安全。AppShell 仍照常用。）

- [ ] **Step 4: 跑测试确认通过 + 不回归**

Run: `python -m pytest tests/test_ui/test_video_manager_selection_smoke.py tests/test_ui/test_app_shell_smoke.py -q`
Expected: PASS（判据 "N passed"；teardown exit-139 可接受）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/panels/video_task_manager_panel.py tests/test_ui/test_video_manager_selection_smoke.py
git commit -m "feat(ui): VideoTaskManagerPanel 加 taskSelected 信号 + cb 可选（主-详准备）"
```

---

## Task 2: 通用 `DetachedEditorWindow`

承载被 reparent 出去的活编辑器；关窗发 `closed(task_id)`，**绝不删除 editor**（由 page 收回）。

**Files:**
- Create: `drama_shot_master/ui/windows/detached_editor_window.py`
- Test: `tests/test_ui/test_detached_editor_window_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_detached_editor_window_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget
from drama_shot_master.ui.windows.detached_editor_window import DetachedEditorWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_hosts_editor_and_emits_closed_without_deleting_editor():
    _app()
    ed = QWidget()
    win = DetachedEditorWindow(ed, "视频任务 · A", "t1")
    assert win.centralWidget() is ed
    seen = []
    win.closed.connect(seen.append)
    win.close()
    assert seen == ["t1"]
    # editor 仍存活（未被窗销毁）——可被重新 setParent
    ed.setParent(None)
    assert ed is not None


def test_set_title():
    _app()
    win = DetachedEditorWindow(QWidget(), "视频任务 · A", "t1")
    win.set_title("视频任务 · B")
    assert "B" in win.windowTitle()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_detached_editor_window_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 建 `drama_shot_master/ui/windows/detached_editor_window.py`**

```python
"""DetachedEditorWindow：通用「浮出」窗，承载从主-详详情区 reparent 出来的活编辑器。

只负责承载与转发关闭事件；编辑器的状态/结果/脏信号由 TaskWorkspacePage 统一接线，
故本窗不接任何编辑器信号。关窗时**不删除** editor（page 在 closed 槽里把它收回）。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.ui.theme import apply_window_icon, apply_dark_titlebar


class DetachedEditorWindow(QMainWindow):
    closed = Signal(str)              # task_id

    def __init__(self, editor, title: str, task_id: str, parent=None):
        super().__init__(parent)
        self._task_id = task_id
        self.setWindowTitle(title)
        self.resize(1100, 820)
        self.setCentralWidget(editor)

    @property
    def task_id(self) -> str:
        return self._task_id

    def set_title(self, title: str) -> None:
        self.setWindowTitle(title)

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_themed", False):
            self._themed = True
            apply_window_icon(self)
            apply_dark_titlebar(self)

    def closeEvent(self, e):
        # 不删 editor：先发信号让 page 把 editor reparent 收回，再正常关闭。
        self.closed.emit(self._task_id)
        super().closeEvent(e)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/test_detached_editor_window_smoke.py -q`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/windows/detached_editor_window.py tests/test_ui/test_detached_editor_window_smoke.py
git commit -m "feat(ui): 通用 DetachedEditorWindow（承载浮出编辑器，关窗收回不删）"
```

---

## Task 3: 通用 `TaskWorkspacePage`

主-详 + 每任务缓存编辑器 + 浮出/收回 + flush_all。用注入的工厂/回调与具体功能解耦；本任务用轻量 stub 测通用机制（不依赖 VideoPanel）。

**Files:**
- Create: `drama_shot_master/ui/pages/task_workspace_page.py`
- Test: `tests/test_ui/test_task_workspace_page_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_task_workspace_page_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget
from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
from drama_shot_master.ui.windows.detached_editor_window import DetachedEditorWindow


def _app():
    return QApplication.instance() or QApplication([])


class _Task:
    def __init__(self, tid, name): self.id = tid; self.name = name


class _FakeManager(QWidget):
    taskSelected = Signal(object)


class _FakeEditor(QWidget):
    def __init__(self): super().__init__(); self.payload = {"v": 1}


def _page(persist_spy=None):
    mgr = _FakeManager()
    made = {}
    def factory(task):
        ed = _FakeEditor(); made[task.id] = ed; return ed
    page = TaskWorkspacePage(
        manager=mgr,
        editor_factory=factory,
        wire_editor=lambda ed, task: None,
        payload_of=lambda ed: ed.payload,
        on_persist=(persist_spy or (lambda tid, p: None)),
        title_for=lambda task: f"视频任务 · {task.name}",
    )
    return page, mgr, made


def test_select_shows_cached_editor():
    _app()
    page, mgr, made = _page()
    a, b = _Task("a", "A"), _Task("b", "B")
    mgr.taskSelected.emit(a)
    assert page._editors["a"] is made["a"]
    assert page.stack.currentWidget() is made["a"]
    mgr.taskSelected.emit(b)
    # 两个编辑器都缓存（并行）
    assert set(page._editors) == {"a", "b"}
    assert page.stack.currentWidget() is made["b"]
    # 再选回 a：复用同一实例（不重建）
    mgr.taskSelected.emit(a)
    assert page.stack.currentWidget() is made["a"]
    assert page._editors["a"] is made["a"]


def test_pop_out_reparents_and_dock_back_returns():
    _app()
    page, mgr, made = _page()
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    page.pop_out()                       # 浮出当前选中
    win = page._detached["a"]
    assert isinstance(win, DetachedEditorWindow)
    assert win.centralWidget() is made["a"]
    assert page.stack.currentWidget() is page._placeholder    # 详情区占位
    win.close()                          # 关窗 → 收回
    assert "a" not in page._detached
    assert made["a"] in [page.stack.widget(i) for i in range(page.stack.count())]


def test_select_detached_task_shows_placeholder():
    _app()
    page, mgr, made = _page()
    a, b = _Task("a", "A"), _Task("b", "B")
    mgr.taskSelected.emit(a); page.pop_out()
    mgr.taskSelected.emit(b)
    mgr.taskSelected.emit(a)             # a 已浮出
    assert page.stack.currentWidget() is page._placeholder


def test_flush_all_persists_every_editor():
    _app()
    calls = []
    page, mgr, made = _page(persist_spy=lambda tid, p: calls.append((tid, p)))
    mgr.taskSelected.emit(_Task("a", "A"))
    mgr.taskSelected.emit(_Task("b", "B"))
    page.flush_all()
    assert {tid for tid, _ in calls} == {"a", "b"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_task_workspace_page_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 建 `drama_shot_master/ui/pages/task_workspace_page.py`**

```python
"""TaskWorkspacePage：生成类功能的窗内主-详页。

左 master（注入的 *TaskManagerPanel，发 taskSelected(task)）；
右详情 = 头条（任务名 + 「⧉ 浮出独立窗」）+ QStackedWidget（index0 占位，其余每任务缓存的编辑器）。
- 每任务首次选中懒建编辑器并缓存；切任务不丢未存编辑；提交后台线程跑 → 窗内并行。
- 浮出 = 把活编辑器 reparent 进 DetachedEditorWindow；关窗收回；单一数据源。
与具体功能解耦：editor_factory/wire_editor/payload_of/on_persist/title_for 注入。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget,
)
from PySide6.QtCore import Qt

from drama_shot_master.ui.windows.detached_editor_window import DetachedEditorWindow


class TaskWorkspacePage(QWidget):
    def __init__(self, manager, editor_factory, wire_editor, payload_of,
                 on_persist, title_for, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._editor_factory = editor_factory
        self._wire_editor = wire_editor
        self._payload_of = payload_of
        self._on_persist = on_persist
        self._title_for = title_for

        self._editors: dict[str, QWidget] = {}
        self._detached: dict[str, DetachedEditorWindow] = {}
        self._current_task = None          # 当前选中的 task 对象

        self._build_ui()
        self.manager.taskSelected.connect(self._on_task_selected)

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.manager)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 6, 8, 8)
        head = QHBoxLayout()
        self.lbl_task = QLabel("未选择任务")
        self.lbl_task.setObjectName("detailTaskName")
        self.btn_popout = QPushButton("⧉ 浮出独立窗")
        self.btn_popout.setEnabled(False)
        self.btn_popout.clicked.connect(self.pop_out)
        head.addWidget(self.lbl_task, 1)
        head.addWidget(self.btn_popout)
        rv.addLayout(head)

        self.stack = QStackedWidget()
        self._placeholder = QLabel("选择左侧任务以编辑")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setObjectName("detailPlaceholder")
        self.stack.addWidget(self._placeholder)
        rv.addWidget(self.stack, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

    # ---------- selection ----------
    def _on_task_selected(self, task):
        # 切走前先持久化上一个（非浮出）编辑器
        self._persist_current()
        self._current_task = task
        tid = task.id
        self.lbl_task.setText(getattr(task, "name", tid))
        if tid in self._detached:
            self.stack.setCurrentWidget(self._placeholder)
            self.btn_popout.setEnabled(False)
            return
        ed = self._ensure_editor(task)
        self.stack.setCurrentWidget(ed)
        self.btn_popout.setEnabled(True)

    def _ensure_editor(self, task):
        tid = task.id
        ed = self._editors.get(tid)
        if ed is None:
            ed = self._editor_factory(task)
            self._wire_editor(ed, task)
            self.stack.addWidget(ed)
            self._editors[tid] = ed
        return ed

    def _persist_current(self):
        t = self._current_task
        if t is None:
            return
        ed = self._editors.get(t.id)
        if ed is not None and t.id not in self._detached:
            self._on_persist(t.id, self._payload_of(ed))

    # ---------- pop out / dock ----------
    def pop_out(self):
        t = self._current_task
        if t is None or t.id in self._detached:
            return
        ed = self._editors.get(t.id)
        if ed is None:
            return
        self._persist_current()
        ed.setParent(None)                          # 脱离 stack
        win = DetachedEditorWindow(ed, self._title_for(t), t.id)
        win.closed.connect(self._dock_back)
        self._detached[t.id] = win
        self.stack.setCurrentWidget(self._placeholder)
        self.btn_popout.setEnabled(False)
        win.show()

    def _dock_back(self, task_id: str):
        win = self._detached.pop(task_id, None)
        ed = self._editors.get(task_id)
        if ed is not None:
            ed.setParent(None)                      # 先脱离窗，避免随窗销毁
            self.stack.addWidget(ed)
            if self._current_task is not None and self._current_task.id == task_id:
                self.stack.setCurrentWidget(ed)
                self.btn_popout.setEnabled(True)
        if win is not None:
            win.deleteLater()

    # ---------- lifecycle ----------
    def flush_all(self):
        for tid, ed in self._editors.items():
            self._on_persist(tid, self._payload_of(ed))

    def discard_editor(self, task_id: str):
        """任务被删时清理其缓存编辑器与浮出窗。"""
        win = self._detached.pop(task_id, None)
        if win is not None:
            win.close()
        ed = self._editors.pop(task_id, None)
        if ed is not None:
            self.stack.removeWidget(ed)
            ed.deleteLater()
```

- [ ] **Step 4: 跑测试确认通过（4 条）**

Run: `python -m pytest tests/test_ui/test_task_workspace_page_smoke.py -q`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/pages/task_workspace_page.py tests/test_ui/test_task_workspace_page_smoke.py
git commit -m "feat(ui): 通用 TaskWorkspacePage（主-详+缓存编辑器+浮出/收回+flush_all）"
```

---

## Task 4: AppShell 接入 video_gen（原子切换）

把 video_gen 页从裸 manager 换成 `TaskWorkspacePage`；同时移除旧开窗 UI/方法（替换与移除同处发生，无功能空窗期）。

> **前置确认（并行前提）：** 视频提交须独立于编辑器可见性才能「窗内并行」。开工前 grep 确认 `VideoPanel` 的提交不因隐藏而停：`grep -nE "isVisible|setVisible|showEvent|hideEvent" drama_shot_master/ui/panels/video_panel.py`。预期：提交逻辑（QThread/worker + submitStarted/Done/Failed）不读 `isVisible()`（旧 `VideoTaskWindow.closeEvent` 注释已确认 worker 关窗后仍在后台跑、只更新隐藏控件）。若发现提交依赖可见性，停下报告，改为在 plan 增加去耦步骤。

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Modify: `drama_shot_master/ui/panels/video_task_manager_panel.py`（去 打开按钮/双击开窗）
- Test: `tests/test_ui/test_app_shell_smoke.py`

- [ ] **Step 1: 写/改失败测试（追加到 test_app_shell_smoke.py）**

```python
def test_video_page_is_task_workspace():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    w = AppShell()
    page = w.pages["video_gen"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, VideoTaskManagerPanel)


def test_video_manager_accessor_returns_page_manager():
    _app()
    w = AppShell()
    assert w._video_manager() is w.pages["video_gen"].manager


def test_video_select_creates_editor_inline():
    _app()
    w = AppShell()
    page = w.pages["video_gen"]
    mgr = page.manager
    if not mgr.store.all():
        mgr.store.add("T1", {})
        mgr.refresh()
    t = mgr.store.all()[0]
    mgr.taskSelected.emit(t)
    from drama_shot_master.ui.panels.video_panel import VideoPanel
    assert isinstance(page._editors[t.id], VideoPanel)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_app_shell_smoke.py -q`
Expected: FAIL（video_gen 仍是裸 manager / 无 `w._video_manager().store` 经 page）

- [ ] **Step 3: 改 video_task_manager_panel.py —— 去开窗 UI（现由 page 提供选择/浮出）**

- 删 `self.btn_open = QPushButton("打开")` 及其加入 bar、`self.btn_open.clicked.connect(self._on_open)`；删 `_on_open` 方法。
- 删 `self.table.itemDoubleClicked.connect(self._on_double_clicked)` 与 `_on_double_clicked` 方法。
- `_on_new`：去掉末尾 `if self._open_window_cb: self._open_window_cb(t)`，改为新建后选中新行（触发 `taskSelected`）：
```python
    def _on_new(self):
        n = len(self.store.all()) + 1
        t = self.store.add(f"任务 {n}", TimelineModel().to_dict())
        self._persist_cb()
        self.refresh()
        self._select_task(t.id)

    def _select_task(self, task_id: str):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.data(Qt.UserRole) == task_id:
                self.table.setCurrentCell(r, 0)
                break
```
- `_on_del`：去掉 `if self._close_window_cb: self._close_window_cb(tid)`（改由 page 监听删除；见 Step 4 page 接 `discard_editor`）。保留其余删除逻辑。
- 构造签名保留 `open_window_cb, close_window_cb` 形参（AppShell 传 None），保持兼容；它们此后不再被调用。

- [ ] **Step 4: 改 app_shell.py —— 构造 page + 删旧开窗方法**

(a) `_build_pages` 里 video_gen 构造改为：
```python
            "video_gen": self._make_video_page,
```
并新增 `_make_video_page`（放在 `_make_imggen_panel` 等近旁）：
```python
    def _make_video_page(self):
        from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
        from drama_shot_master.ui.panels.video_panel import VideoPanel
        from drama_shot_master.core.video_timeline_model import TimelineModel

        manager = VideoTaskManagerPanel(
            self.state, self.cfg, self.video_store, None, None, self._persist_tasks)

        def editor_factory(task):
            return VideoPanel(self.state, self.cfg,
                              TimelineModel.from_dict(task.timeline))

        def wire_editor(editor, task):
            tid = task.id
            editor.submitStarted.connect(lambda: self._on_task_status(tid, "生成中"))
            editor.submitDone.connect(
                lambda mp4: (self._on_task_status(tid, "完成"),
                             self._on_task_result(tid, mp4)))
            editor.submitFailed.connect(lambda e: self._on_task_status(tid, "失败"))

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.model.to_dict(),
            on_persist=self._on_task_dirty,
            title_for=lambda task: f"视频任务 · {task.name}",
        )
        # 任务删除 → 清理缓存编辑器
        manager.taskRenamed.connect(self._on_task_renamed)
        return page
```
(b) `_video_manager()` 改为返回 page.manager：
```python
    def _video_manager(self):
        return self.pages["video_gen"].manager
```
(c) 删除这些视频专用开窗方法（dub/imggen/soundtrack 同名前缀方法**保留**）：`_open_task_window`、`_close_task_window`、`_on_task_window_closed`；以及 `__init__`/`_build_pages` 里的 `self._open_task_windows = {}`。保留 `_on_task_status`/`_on_task_result`/`_on_task_dirty`/`_persist_tasks`/`_on_task_renamed`（page/wire 仍用）。
(d) `_wire` 里 `self._video_manager().taskRenamed.connect(self._on_task_renamed)` —— 现已在 `_make_video_page` 内连接，故从 `_wire` 删除这一行（避免重复连接）。同时确保 `_wire` 中对 video page 的 `statusMessage` 连接走 `page.manager`（manager 是 BasePanel，有 statusMessage；若 `_wire` 按 `self.pages.values()` 遍历连接 statusMessage，TaskWorkspacePage 不是 BasePanel、无 statusMessage —— 用 `hasattr` 守卫已覆盖；确认遍历对 page 用 `getattr(page,'manager',page)` 或跳过非 BasePanel。**实现：** `_wire` 里把「每页 statusMessage」连接改为：对 TaskWorkspacePage 连其 `.manager.statusMessage`，其余页若 `hasattr(page,'statusMessage')` 连之）。
(e) `_on_task_renamed`：原按 `_open_task_windows` 找窗同步标题；改为同步 page 的浮出窗标题：
```python
    def _on_task_renamed(self, task_id: str, name: str):
        page = self.pages.get("video_gen")
        win = getattr(page, "_detached", {}).get(task_id) if page else None
        if win is not None:
            win.set_title(f"视频任务 · {name}")
```
(f) `closeEvent` 视频段：把遍历 `self._open_task_windows` 落盘改为：
```python
        vp = self.pages.get("video_gen")
        if vp is not None and hasattr(vp, "flush_all"):
            vp.flush_all()
```
（删除原 `for win in list(self._open_task_windows.values()): self.video_store.update(win.task_id, timeline=win.model.to_dict())` 段。）
(g) 任务删除清理编辑器：在 `_make_video_page` 里把 manager 的删除与 page.discard_editor 关联 —— `VideoTaskManagerPanel._on_del` 已不调 close_cb。新增：manager 删除后需通知 page。最简：给 manager 加一个 `taskDeleted = Signal(str)`（在 `_on_del` 成功后 `self.taskDeleted.emit(tid)`），在 `_make_video_page` 内 `manager.taskDeleted.connect(page.discard_editor)`。**本步包含**给 manager 加 `taskDeleted` 信号并在 `_on_del` 末尾 emit。

- [ ] **Step 5: 跑全部 UI 测试**

Run: `python -m pytest tests/test_ui/test_app_shell_smoke.py tests/test_ui/test_task_workspace_page_smoke.py tests/test_ui/test_video_manager_selection_smoke.py -q`
Expected: PASS（新 3 条 + 既有全绿）。若 `test_video_manager_selection_smoke` 因删 `_on_double_clicked` 失败，更新该测试（去掉双击相关断言；它原只测 taskSelected + None 安全，不涉双击，应仍绿）。

- [ ] **Step 6: 真机冒烟（有显示环境）**

Run: `python -m drama_shot_master.main`
Expected: 视频生成页左列表/右编辑器；选任务即内嵌编辑；新建即选中；「⧉ 浮出独立窗」弹独立窗、关窗收回；可同时跑多个任务生成。

- [ ] **Step 7: 提交**

```bash
git add drama_shot_master/ui/app_shell.py drama_shot_master/ui/panels/video_task_manager_panel.py tests/test_ui/test_app_shell_smoke.py
git commit -m "feat(ui): video_gen 接入 TaskWorkspacePage（窗内主-详+浮出），移除旧开窗逻辑"
```

---

## Task 5: 退役 VideoTaskWindow + 收尾

**Files:**
- Delete: `drama_shot_master/ui/windows/video_task_window.py`
- (可能) Delete/改: 引用它的旧测试

- [ ] **Step 1: 确认无引用**

Run: `cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master && grep -rn "video_task_window\|VideoTaskWindow" drama_shot_master/ tests/`
Expected: 仅可能命中测试或注释。若 `drama_shot_master/` 生产代码仍引用（除注释），停下报告。

- [ ] **Step 2: 删文件 + 清理引用**

```bash
git rm drama_shot_master/ui/windows/video_task_window.py
```
若 Step 1 命中某测试文件 import 了 `VideoTaskWindow`，删除该测试或移除相关用例（视具体文件而定；多数情况无专门测试）。

- [ ] **Step 3: 全量回归 + 零 GPL 复核**

Run:
```
grep -rn "import qfluentwidgets\|from qfluentwidgets" drama_shot_master/ tests/ && echo "!!!" || echo "CLEAN: zero qfluentwidgets"
for f in tests/test_ui/*.py; do echo "== $f =="; python -m pytest "$f" -q 2>&1 | tail -2; done
python -m pytest tests/ -q --ignore=tests/test_ui 2>&1 | tail -3
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.ui.app_shell import AppShell; w=AppShell(); w.show(); a.processEvents(); print('LIVE OK', len(w.pages))"
```
Expected: `CLEAN: zero qfluentwidgets`；每 UI 文件 "N passed"（teardown exit-139 后置可接受）；非 UI 全绿；`LIVE OK 7`。

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore(ui): 退役 VideoTaskWindow（职责并入 TaskWorkspacePage + DetachedEditorWindow）"
```

---

## 验收清单（对应 spec §1/§6）
- [ ] video_gen 页是 `TaskWorkspacePage`：左列表选中即内嵌编辑；新建即选中。
- [ ] 每任务缓存独立编辑器，切任务不丢编辑；可同时跑多个生成（窗内并行）。
- [ ] 「⧉ 浮出独立窗」reparent 活编辑器进 `DetachedEditorWindow`；关窗收回；详情区占位切换正确。
- [ ] 状态/结果经 `wire_editor` 进现有 store 回调；脏/落盘经 `on_persist`/`flush_all` 不丢。
- [ ] 删除任务清理其缓存编辑器与浮出窗（`discard_editor`）。
- [ ] 图片/配音/配乐行为不变（仍双击开窗）。
- [ ] `python -m pytest tests/` 全绿；`grep qfluentwidgets` 仍为空。

## 后续（各自 plan）
- replicate-1：图片生成 + 配音改 `TaskWorkspacePage`（factory=ImgGenPanel/DubPanel，payload_of=`lambda ed: ed.to_payload()`，wire 用各自 statusChanged/resultReady/dirty；退役 ImgGen/Dub TaskWindow）。
- replicate-2：配乐改造（SoundtrackPanel try-import 与 321 行窗特殊处理）。
- 之后 Phase 3（统一设置页+浅色）/ Phase 4（全局任务中心）/ Phase 5（精修 + 侧栏折叠动画）。
