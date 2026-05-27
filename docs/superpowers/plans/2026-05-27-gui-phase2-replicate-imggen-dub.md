# Phase 2 replicate（图片+配音 主-详+浮出）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「图片生成」「配音」从「任务列表+双击开窗」改为窗内主-详+浮出独立窗，复用 Phase 2 视频已验证的 `TaskWorkspacePage`/`DetachedEditorWindow`；配乐不动（下个 plan）。

**Architecture:** 两管理面板加 `taskSelected`/`taskDeleted`（复用为 master）；AppShell 用 `_make_imggen_page`/`_make_dub_page` 注入各自 editor_factory/wire/payload/on_persist/title/尺寸，构造 `TaskWorkspacePage`；删旧开窗方法；退役两个 TaskWindow。编辑器(`ImgGenPanel`/`DubPanel`)、stores、config 零改动。

**Tech Stack:** PySide6 6.11、pytest 9（offscreen smoke）。

**Spec:** `docs/superpowers/specs/2026-05-27-gui-phase2-replicate-imggen-dub-design.md`

**排序原则（每次提交可用/绿）：** T1 纯加信号（不动开窗）；T2 加尺寸参数（默认不变）；T3 图片原子切换；T4 配音原子切换；T5 删旧窗。

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| Modify | `drama_shot_master/ui/panels/imggen_task_manager_panel.py` | T1 加 taskSelected/taskDeleted；T3 去开窗UI、_new选中、_del发taskDeleted |
| Modify | `drama_shot_master/ui/panels/dub_task_manager_panel.py` | 同上（T1/T4）|
| Modify | `drama_shot_master/ui/windows/detached_editor_window.py` | T2 加 `size` 参数 |
| Modify | `drama_shot_master/ui/pages/task_workspace_page.py` | T2 加 `detached_size` 参数并透传 pop_out |
| Modify | `drama_shot_master/ui/app_shell.py` | T3/T4 接入 page、删旧开窗方法、accessors/closeEvent/renamed |
| Delete | `drama_shot_master/ui/windows/imggen_task_window.py` / `dub_task_window.py` | T5 |
| Create | `tests/test_ui/test_imggen_dub_manager_selection_smoke.py` | T1 |
| Create | `tests/test_ui/test_imggen_workspace_smoke.py` / `test_dub_workspace_smoke.py` | T3/T4 |
| Modify | `tests/test_ui/test_detached_editor_window_smoke.py` / `test_task_workspace_page_smoke.py` | T2 |

---

## Task 1: 两管理面板加 taskSelected/taskDeleted（纯加）

**Files:**
- Modify: `drama_shot_master/ui/panels/imggen_task_manager_panel.py`
- Modify: `drama_shot_master/ui/panels/dub_task_manager_panel.py`
- Test: `tests/test_ui/test_imggen_dub_manager_selection_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_imggen_dub_manager_selection_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.config import load_config
from drama_shot_master.ui.state import AppState
from drama_shot_master.core.imggen_task_store import ImgGenTaskStore
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_imggen_selection_emits_and_loading_guard():
    _app()
    store = ImgGenTaskStore.from_list([])
    store.add("A", payload={}); store.add("B", payload={})
    p = ImgGenTaskManagerPanel(AppState(), load_config(), store, None, None, lambda: None)
    seen = []
    p.taskSelected.connect(seen.append)
    p.table.setCurrentCell(0, 0)
    assert seen and seen[-1].id == store.all()[0].id
    # refresh 期间 _loading 守卫：刷新不应再发选择
    seen.clear()
    p.refresh()
    assert seen == []
    # taskDeleted 信号存在
    assert hasattr(p, "taskDeleted")


def test_dub_selection_emits():
    _app()
    store = DubTaskStore.from_list([])
    store.add("A", mode="clone", payload={}); store.add("B", mode="clone", payload={})
    p = DubTaskManagerPanel(AppState(), load_config(), store, None, None, lambda: None)
    seen = []
    p.taskSelected.connect(seen.append)
    p.table.setCurrentCell(0, 0)
    assert seen and seen[-1].id == store.all()[0].id
    assert hasattr(p, "taskDeleted")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master && python -m pytest tests/test_ui/test_imggen_dub_manager_selection_smoke.py -q`
Expected: FAIL（无 taskSelected/taskDeleted）

- [ ] **Step 3: 改两个面板（同样的纯加改动；逐文件）**

对 `imggen_task_manager_panel.py` 与 `dub_task_manager_panel.py` 各做：

(a) 信号区（`taskRenamed = Signal(str, str)` 下方）加：
```python
    taskSelected = Signal(object)
    taskDeleted = Signal(str)
```
(b) `_build_ui` 中 `self.table.itemChanged.connect(self._on_item_changed)` 之后加：
```python
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
```
(c) 新增方法（`_selected_id` 附近）：
```python
    def _on_selection_changed(self):
        if self._loading:            # refresh 重建表期间不误发
            return
        tid = self._selected_id()
        if not tid:
            return
        t = self.store.get(tid)
        if t is not None:
            self.taskSelected.emit(t)
```
(d) `_del` 末尾（`self.refresh()` 之后）加 `self.taskDeleted.emit(tid)`：
- imggen `_del`：`if QMessageBox.question(...)==QMessageBox.Yes: self._close_cb(tid); self.store.remove(tid); self._persist(); self.refresh(); self.taskDeleted.emit(tid)`
- dub `_del`：同样在末尾追加 `self.taskDeleted.emit(tid)`。
（本任务**不**去开窗 UI、不动 cb 调用；纯加。）

- [ ] **Step 4: 跑测试确认通过 + 不回归**

Run: `python -m pytest tests/test_ui/test_imggen_dub_manager_selection_smoke.py tests/test_ui/test_app_shell_smoke.py -q`
Expected: PASS（判据 "N passed"；teardown exit-139 可接受）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/panels/imggen_task_manager_panel.py drama_shot_master/ui/panels/dub_task_manager_panel.py tests/test_ui/test_imggen_dub_manager_selection_smoke.py
git commit -m "feat(ui): imggen/dub 管理面板加 taskSelected/taskDeleted（主-详准备）"
```

---

## Task 2: DetachedEditorWindow + TaskWorkspacePage 尺寸参数

**Files:**
- Modify: `drama_shot_master/ui/windows/detached_editor_window.py`
- Modify: `drama_shot_master/ui/pages/task_workspace_page.py`
- Test: `tests/test_ui/test_detached_editor_window_smoke.py`, `tests/test_ui/test_task_workspace_page_smoke.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ui/test_detached_editor_window_smoke.py`：
```python
def test_size_param_applied():
    _app()
    win = DetachedEditorWindow(QWidget(), "T", "t1", size=(720, 780))
    assert win.width() == 720 and win.height() == 780
```
追加到 `tests/test_ui/test_task_workspace_page_smoke.py`：
```python
def test_detached_size_threaded_to_window():
    _app()
    page, mgr, made = _page()
    page._detached_size = (720, 780)      # 由构造注入，这里直接断言透传
    a = _Task("a", "A")
    mgr.taskSelected.emit(a)
    page.pop_out()
    win = page._detached["a"]
    assert (win.width(), win.height()) == (720, 780)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_detached_editor_window_smoke.py::test_size_param_applied tests/test_ui/test_task_workspace_page_smoke.py::test_detached_size_threaded_to_window -q`
Expected: FAIL（`size` / `_detached_size` 不支持）

- [ ] **Step 3a: 改 detached_editor_window.py `__init__`**

把签名与 resize 改为：
```python
    def __init__(self, editor, title: str, task_id: str, parent=None,
                 size: tuple[int, int] = (1100, 820)):
        super().__init__(parent)
        self._task_id = task_id
        self.setWindowTitle(title)
        self.resize(*size)
        self.setCentralWidget(editor)
        # reparent 后 Qt 会隐藏编辑器；显式 show 否则窗内空白
        editor.show()
```
（`editor.show()` 那行已存在，保留；仅把 `resize(1100,820)` 改为 `resize(*size)` 并加 `size` 参数。）

- [ ] **Step 3b: 改 task_workspace_page.py**

构造函数加 `detached_size` 参数（放在 `title_for` 之后、`parent` 之前）：
```python
    def __init__(self, manager, editor_factory, wire_editor, payload_of,
                 on_persist, title_for, detached_size=(1100, 820), parent=None):
        ...
        self._title_for = title_for
        self._detached_size = detached_size
        ...
```
`pop_out` 中创建窗时透传尺寸：
```python
        win = DetachedEditorWindow(ed, self._title_for(t), t.id, size=self._detached_size)
```

- [ ] **Step 4: 跑测试确认通过（含既有不回归）**

Run: `python -m pytest tests/test_ui/test_detached_editor_window_smoke.py tests/test_ui/test_task_workspace_page_smoke.py -q`
Expected: PASS（既有 + 2 新）。`_make_video_page` 不传 detached_size → 默认 (1100,820)，视频不受影响。

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/windows/detached_editor_window.py drama_shot_master/ui/pages/task_workspace_page.py tests/test_ui/test_detached_editor_window_smoke.py tests/test_ui/test_task_workspace_page_smoke.py
git commit -m "feat(ui): DetachedEditorWindow/TaskWorkspacePage 支持浮出窗尺寸参数（默认 1100x820）"
```

---

## Task 3: 图片生成接入 TaskWorkspacePage（原子切换）

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Modify: `drama_shot_master/ui/panels/imggen_task_manager_panel.py`
- Test: `tests/test_ui/test_imggen_workspace_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_imggen_workspace_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_imggen_page_is_task_workspace():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
    w = AppShell()
    page = w.pages["imggen"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, ImgGenTaskManagerPanel)
    assert w._imggen_manager() is page.manager


def test_imggen_select_creates_editor_inline():
    _app()
    from drama_shot_master.ui.panels.imggen_panel import ImgGenPanel
    w = AppShell()
    page = w.pages["imggen"]; m = page.manager
    if not m.store.all():
        m.store.add("T1", payload={}); m.refresh()
    t = m.store.all()[0]
    m.taskSelected.emit(t)
    assert isinstance(page._editors[t.id], ImgGenPanel)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_imggen_workspace_smoke.py -q`
Expected: FAIL（imggen 页仍是裸 manager）

- [ ] **Step 3: 改 imggen 管理面板（去开窗 UI；_new 选中；_del 去 close_cb）**

`imggen_task_manager_panel.py`：
- `_build_ui` 的按钮 bar 元组里删掉 `("打开", self._open)`；删除 `_open` 方法。
- 删除 `self.table.doubleClicked.connect(self._on_double)`；删除 `_on_double` 方法（col-0 内联改名走表 DoubleClicked 编辑触发，保留不受影响）。
- `_new`：把末尾 `self._persist(); self.refresh(); self._open_cb(t)` 改为：
```python
        self._persist(); self.refresh(); self._select_task(t.id)
```
  并新增：
```python
    def _select_task(self, task_id):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.data(Qt.UserRole) == task_id:
                self.table.setCurrentCell(r, 0)
                break
```
- `_del`：删掉 `self._close_cb(tid)` 调用（保留 `self.store.remove(tid); self._persist(); self.refresh(); self.taskDeleted.emit(tid)`）。
- 构造形参 `open_window_cb, close_window_cb` 保留（AppShell 传 None，不再调用）。

- [ ] **Step 4: 改 app_shell.py（imggen 段）**

(a) `_build_pages`：`"imggen": self._make_imggen_panel` → `"imggen": self._make_imggen_page`。删除 `self._open_imggen_windows = {}`（在 `__init__`/`_build_pages` 中，line ~59）。
(b) 用 `_make_imggen_page` 替换 `_make_imggen_panel`：
```python
    def _make_imggen_page(self):
        from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
        from drama_shot_master.ui.panels.imggen_panel import ImgGenPanel

        manager = ImgGenTaskManagerPanel(
            self.state, self.cfg, self.imggen_store, None, None, self._persist_imggen_tasks)

        def editor_factory(task):
            return ImgGenPanel(self.cfg, payload=task.payload)

        def wire_editor(editor, task):
            tid = task.id
            editor.statusChanged.connect(lambda s: self._on_imggen_status(tid, s))
            editor.resultReady.connect(lambda p: self._on_imggen_result(tid, p))
            editor.dirty.connect(lambda: self._on_imggen_dirty(tid, editor.to_payload()))

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.to_payload(),
            on_persist=self._on_imggen_dirty,
            title_for=lambda task: f"图片生成 · {task.name}",
            detached_size=(720, 780),
        )
        manager.taskRenamed.connect(self._on_imggen_renamed)
        manager.taskDeleted.connect(page.discard_editor)
        return page
```
(c) `_imggen_manager` → `return self.pages["imggen"].manager`。
(d) 删除 `_open_imggen_window`、`_close_imggen_window`、`_on_imggen_window_closed`。**保留** `_on_imggen_status/_on_imggen_result/_on_imggen_dirty/_persist_imggen_tasks/_on_imggen_renamed`。
(e) `_on_imggen_renamed` 改为：
```python
    def _on_imggen_renamed(self, task_id: str, name: str):
        self.pages["imggen"].update_task_name(task_id, name)
```
(f) `_wire`：删除 `self._imggen_manager().taskRenamed.connect(self._on_imggen_renamed)` 那行（现已在 `_make_imggen_page` 内连接，避免重复）。
(g) `closeEvent`：把 imggen 段（`for win in list(self._open_imggen_windows.values()): self.imggen_store.update(win.task_id, payload=win.panel.to_payload())` + `self._persist_imggen_tasks()`）替换为：
```python
        ip = self.pages.get("imggen")
        if ip is not None and hasattr(ip, "flush_all"):
            ip.flush_all()
```

切换确认：`grep -nE "_open_imggen_window|_close_imggen_window|_on_imggen_window_closed|_open_imggen_windows|ImgGenTaskWindow" drama_shot_master/ui/app_shell.py` → 空。

- [ ] **Step 5: 跑测试**

Run: `python -m pytest tests/test_ui/test_imggen_workspace_smoke.py tests/test_ui/test_app_shell_smoke.py tests/test_ui/test_imggen_dub_manager_selection_smoke.py -q`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/app_shell.py drama_shot_master/ui/panels/imggen_task_manager_panel.py tests/test_ui/test_imggen_workspace_smoke.py
git commit -m "feat(ui): 图片生成接入 TaskWorkspacePage（主-详+浮出 720x780），移除旧开窗"
```

---

## Task 4: 配音接入 TaskWorkspacePage（原子切换）

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Modify: `drama_shot_master/ui/panels/dub_task_manager_panel.py`
- Test: `tests/test_ui/test_dub_workspace_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_dub_workspace_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_dub_page_is_task_workspace():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
    w = AppShell()
    page = w.pages["dubbing"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, DubTaskManagerPanel)
    assert w._dub_manager() is page.manager


def test_dub_select_creates_editor_inline():
    _app()
    from drama_shot_master.ui.panels.dub_panel import DubPanel
    w = AppShell()
    page = w.pages["dubbing"]; m = page.manager
    if not m.store.all():
        m.store.add("T1", mode="clone", payload={}); m.refresh()
    t = m.store.all()[0]
    m.taskSelected.emit(t)
    assert isinstance(page._editors[t.id], DubPanel)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_dub_workspace_smoke.py -q`
Expected: FAIL（dub 页仍是裸 manager）

- [ ] **Step 3: 改 dub 管理面板（去开窗 UI；_new 选中；_del 去 close_cb）**

`dub_task_manager_panel.py`（注意 dub 无 `_rename` 按钮、表 5 列）：
- `_build_ui` 按钮 bar 元组删 `("打开", self._open)`；删 `_open` 方法。
- 删 `self.table.doubleClicked.connect(self._on_double)`；删 `_on_double` 方法。
- `_new`：把 `self._persist(); self.refresh(); self._open_cb(t)` 改为 `self._persist(); self.refresh(); self._select_task(t.id)`；新增 `_select_task`（同 imggen）：
```python
    def _select_task(self, task_id):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.data(Qt.UserRole) == task_id:
                self.table.setCurrentCell(r, 0)
                break
```
- `_del`：删 `self._close_cb(tid)` 调用（保留 remove/persist/refresh/taskDeleted.emit）。
- 构造形参保留（AppShell 传 None）。

- [ ] **Step 4: 改 app_shell.py（dub 段）**

(a) `_build_pages`：`"dubbing": self._make_dub_panel` → `"dubbing": self._make_dub_page`。删 `self._open_dub_windows = {}`（line ~58）。
(b) 用 `_make_dub_page` 替换 `_make_dub_panel`：
```python
    def _make_dub_page(self):
        from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
        from drama_shot_master.ui.panels.dub_panel import DubPanel

        manager = DubTaskManagerPanel(
            self.state, self.cfg, self.dub_store, None, None, self._persist_dub_tasks)

        def editor_factory(task):
            return DubPanel(self.cfg, payload=task.payload)

        def wire_editor(editor, task):
            tid = task.id
            editor.statusChanged.connect(lambda s: self._on_dub_status(tid, s))
            editor.resultReady.connect(lambda p: self._on_dub_result(tid, p))
            editor.dirty.connect(lambda: self._on_dub_dirty(tid, editor.to_payload()))

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.to_payload(),
            on_persist=self._on_dub_dirty,
            title_for=lambda task: f"配音 · {task.name}",
        )
        manager.taskRenamed.connect(self._on_dub_renamed)
        manager.taskDeleted.connect(page.discard_editor)
        return page
```
（dub 浮出窗用默认 1100×820，不传 detached_size。）
(c) `_dub_manager` → `return self.pages["dubbing"].manager`。
(d) 删除 `_open_dub_window`、`_close_dub_window`、`_on_dub_window_closed`。**保留** `_on_dub_status/_on_dub_result/_on_dub_dirty/_persist_dub_tasks/_on_dub_renamed`。注意 `_on_dub_dirty(task_id, payload)` 内部已含 `mode=` 推导，签名 `(task_id, payload)` 与 page 的 `on_persist(tid, payload)` 一致，不改其逻辑。
(e) `_on_dub_renamed` 改为：
```python
    def _on_dub_renamed(self, task_id: str, name: str):
        self.pages["dubbing"].update_task_name(task_id, name)
```
(f) `_wire`：删除 `self._dub_manager().taskRenamed.connect(self._on_dub_renamed)` 那行（现已在 `_make_dub_page` 内连接）。
(g) `closeEvent`：把 dub 段替换为：
```python
        dp = self.pages.get("dubbing")
        if dp is not None and hasattr(dp, "flush_all"):
            dp.flush_all()
```

切换确认：`grep -nE "_open_dub_window|_close_dub_window|_on_dub_window_closed|_open_dub_windows|DubTaskWindow" drama_shot_master/ui/app_shell.py` → 空。

- [ ] **Step 5: 跑测试**

Run: `python -m pytest tests/test_ui/test_dub_workspace_smoke.py tests/test_ui/test_app_shell_smoke.py -q`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/app_shell.py drama_shot_master/ui/panels/dub_task_manager_panel.py tests/test_ui/test_dub_workspace_smoke.py
git commit -m "feat(ui): 配音接入 TaskWorkspacePage（主-详+浮出），移除旧开窗"
```

---

## Task 5: 退役 ImgGen/Dub TaskWindow + 收尾验收

**Files:**
- Delete: `drama_shot_master/ui/windows/imggen_task_window.py`, `drama_shot_master/ui/windows/dub_task_window.py`

- [ ] **Step 1: 确认无生产引用**

Run: `cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master && grep -rn "imggen_task_window\|ImgGenTaskWindow\|dub_task_window\|DubTaskWindow" drama_shot_master/ tests/`
Expected: 仅命中两文件自身（及可能的旧测试）。若 `drama_shot_master/` 其它生产代码引用，停下报告。

- [ ] **Step 2: 删除（仅这两个文件；用精确路径，勿用 git add -A）**

```bash
git rm drama_shot_master/ui/windows/imggen_task_window.py drama_shot_master/ui/windows/dub_task_window.py
```
若 Step 1 命中某测试 import 了它们，删除该测试或相关用例并 `git add` 那个测试文件（仅该文件）。

- [ ] **Step 3: 最终验收**

Run（判据为各 "N passed" 行；teardown exit-139 后置可接受；真 FAIL/ERROR 则停下报告，勿提交）：
```
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
echo "== qfluentwidgets imports（应为空）=="
grep -rn "import qfluentwidgets\|from qfluentwidgets" drama_shot_master/ tests/ && echo "!!!" || echo "CLEAN"
echo "== 每文件 UI 测试 =="
for f in tests/test_ui/*.py; do echo "== $f =="; python -m pytest "$f" -q 2>&1 | tail -1; done
echo "== 非 UI 全量 =="
python -m pytest tests/ -q --ignore=tests/test_ui 2>&1 | tail -3
echo "== 入口构造 + 三个生成页类型 =="
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.ui.app_shell import AppShell; from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage as T; w=AppShell(); w.show(); a.processEvents(); print('imggen', isinstance(w.pages['imggen'],T), 'dubbing', isinstance(w.pages['dubbing'],T), 'soundtrack-unchanged', not isinstance(w.pages['soundtrack'],T)); print('LIVE OK', len(w.pages))"
```
Expected: `CLEAN`；每 UI 文件 "N passed"；非 UI 全绿；`imggen True dubbing True soundtrack-unchanged True`；`LIVE OK 7`。

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/ui/windows/imggen_task_window.py drama_shot_master/ui/windows/dub_task_window.py
git commit -m "chore(ui): 退役 ImgGen/Dub TaskWindow（职责并入 TaskWorkspacePage + DetachedEditorWindow）"
```

---

## 验收清单（对应 spec §1/§8）
- [ ] imggen/dubbing 页是 `TaskWorkspacePage`：选中即内嵌编辑；新建即选中；图片浮出窗 720×780、配音 1100×820。
- [ ] 浮出/收回/删除清理 与视频一致（复用通用机制 + reparent-show 防空白）。
- [ ] 状态/结果/dirty 经 wire_editor 进现有 store 回调；落盘经 on_persist/flush_all 不丢。
- [ ] **soundtrack 行为不变**（仍双击开窗）。
- [ ] `python -m pytest tests/` 全绿；`grep qfluentwidgets` 仍为空。

## 后续
- 下一个 plan：**配乐** —— 抽 `SoundtrackEditor(QWidget)` from `SoundtrackTaskWindow`(321行) + 适配 `cfg.soundtrack_tasks` dict 模型 + try-import 兜底 → 接入 `TaskWorkspacePage`。
- 再后：原 UX 路线 Phase 3（统一设置页+浅色）/ Phase 4（全局任务中心）/ Phase 5（精修+侧栏折叠动画）。
