# Phase 2 配乐 主-详+浮出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把配乐从「任务列表 + 双击另开 `SoundtrackTaskWindow`」改为窗内主-详（左 `SoundtrackPanel` 列表 / 右内嵌 `SoundtrackEditor`）+「⧉ 浮出独立窗」，复用通用 `TaskWorkspacePage` + `DetachedEditorWindow`，收口 Phase 2 全部生成功能主-详化。

**Architecture:** 抽出 `SoundtrackEditor(QWidget)` 承载原窗的全部编辑器逻辑；dict 任务用薄 live-view（`_SoundtrackTaskView`，暴露 `.id/.name/.payload`）喂给通用页；`SoundtrackPanel` 改发 `taskSelected/taskDeleted/taskRenamed` 信号、去掉开窗；AppShell 用 try-import 兜底装配 `TaskWorkspacePage`；退役 `SoundtrackTaskWindow`。

**Tech Stack:** PySide6（QWidget/QTabWidget），pytest（headless `QT_QPA_PLATFORM=offscreen` smoke），`sound_track_agent.facade`（lazy import，不改）。

参考设计：[`docs/superpowers/specs/2026-05-27-gui-phase2-soundtrack-design.md`](../specs/2026-05-27-gui-phase2-soundtrack-design.md)。
镜像参照（已完成）：AppShell `_make_dub_page` / `_make_imggen_page`（`drama_shot_master/ui/app_shell.py:431-539`），通用页 `drama_shot_master/ui/pages/task_workspace_page.py`。

---

### Task 1: 抽出 `SoundtrackEditor(QWidget)`

把 `SoundtrackTaskWindow` 的全部编辑器逻辑搬进一个 QWidget；新增 `to_payload()`；删 `closed` 信号与 `closeEvent`。本任务**不删**旧窗（Task 4 删），保证中途套件常绿。

**Files:**
- Create: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_soundtrack_editor_smoke.py`
- Reference (copy from, do not edit): `drama_shot_master/ui/windows/soundtrack_task_window.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ui/test_soundtrack_editor_smoke.py`：

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    return type("C", (), {"soundtrack_workflow_id": "", "soundtrack_seeds_count": 2,
                          "soundtrack_output_dir": "", "video_output_dir": str(tmp_path),
                          "soundtrack_crossfade": 0.5, "accent_big_threshold": 0.7,
                          "accent_snap_window": 0.6})()


def _task():
    return {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
            "style": "末日废土", "output_dir": "", "status": "空闲", "output": ""}


def test_editor_is_qwidget_with_three_tabs(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    assert isinstance(ed, QWidget)
    assert ed.tabs.count() == 3
    assert ed.style_edit.toPlainText() == "末日废土"


def test_editor_has_no_closed_signal():
    # widget 不需要 closed 信号 / closeEvent；浮出由 DetachedEditorWindow 承载
    assert not hasattr(SoundtrackEditor, "closed")


def test_to_payload_reads_widgets(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    ed.mp4_edit.setText("/y/ep2.mp4")
    ed.style_edit.setPlainText("赛博霓虹")
    ed.out_edit.setText("/out/dir")
    p = ed.to_payload()
    assert p == {"mp4": "/y/ep2.mp4", "style": "赛博霓虹", "output_dir": "/out/dir"}


def test_output_base_falls_back(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    assert "soundtrack" in str(ed._resolve_output_base())


def test_export_guard_no_mp4_does_not_crash(tmp_path, monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    ed = SoundtrackEditor({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                          _cfg(tmp_path), tmp_path)
    monkeypatch.setattr(m.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(m.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    assert hasattr(ed, "btn_export")
    ed._on_export()        # 无 mp4 → 走校验提示并 return，不崩


def test_preview_button_toggles_with_output(tmp_path, monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    ed = SoundtrackEditor({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                          _cfg(tmp_path), tmp_path)
    assert ed.btn_preview.isEnabled() is False
    opened = []
    monkeypatch.setattr(m.QDesktopServices, "openUrl", lambda url: opened.append(url))
    fake = tmp_path / "clip_scored.mp4"; fake.write_bytes(b"x")
    ed._session = type("S", (), {"output": str(fake)})()
    ed._update_preview_enabled()
    assert ed.btn_preview.isEnabled() is True
    ed._on_preview()
    assert opened


def test_session_mount_does_not_crash(tmp_path, monkeypatch):
    # monkeypatch facade.load_session 返回空 session（segments/accent_points 空）
    # → _try_load_existing → _mount_session_tabs 构造 review/accent 不崩
    _app()
    import drama_shot_master.ui.widgets.soundtrack_editor as m
    stub = type("Sess", (), {"segments": [], "accent_points": [],
                             "source_mp4": "", "output": None})()
    monkeypatch.setattr(m, "_load_session_safe", lambda wd: stub, raising=False)
    # 直接验证 _mount_session_tabs 不崩（绕开 facade import 细节）
    ed = SoundtrackEditor(_task(), _cfg(tmp_path), tmp_path)
    ed._session = stub
    ed._mount_session_tabs()
    assert ed._review is not None and ed._accent is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui/test_soundtrack_editor_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'drama_shot_master.ui.widgets.soundtrack_editor'`

- [ ] **Step 3: Create the editor by extracting from the window**

Create `drama_shot_master/ui/widgets/soundtrack_editor.py`. Strategy: copy `soundtrack_task_window.py` verbatim, then apply exactly these changes:

1. **Imports** — drop `QMainWindow`; the rest of the imports stay. Final import block:

```python
"""SoundtrackEditor：单集配乐编辑器（QWidget，3 页签）。

从退役的 SoundtrackTaskWindow 抽取：① 配置+生成 ② 试听选优 ③ 卡点。
浮出由通用 DetachedEditorWindow 承载，故本类不带 closed/closeEvent。
输出路径：任务 output_dir → cfg.soundtrack_output_dir → cfg.video_output_dir/soundtrack。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QComboBox, QProgressBar, QTabWidget,
    QFileDialog, QMessageBox,
)

from drama_shot_master.ui.worker import FunctionWorker
from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
from drama_shot_master.ui.widgets.accent_editor_widget import AccentEditorWidget

_STAGES = ["tag_emotion", "compose_prompt", "generate", "align", "mix"]
_STAGE_LABELS = {"tag_emotion": "切段+情绪", "compose_prompt": "prompt",
                 "generate": "生成(选优点)", "align": "对齐", "mix": "出片"}
```

2. **Class decl + signals + `__init__`** — base class `QWidget`; drop `closed` signal; drop `setWindowTitle`/`resize`:

```python
class SoundtrackEditor(QWidget):
    statusChanged = Signal(str, str)
    resultReady = Signal(str, str)

    def __init__(self, task: dict, cfg, work_root, parent=None):
        super().__init__(parent)
        self._task = task
        self.cfg = cfg
        self._work_root = Path(work_root)
        self._worker = None
        self._session = None
        self._review = None
        self._accent = None
        self._build_ui()
        self._try_load_existing()
```

3. **`_build_ui`** — replace `self.setCentralWidget(self.tabs)` with a zero-margin root layout:

```python
    def _build_ui(self):
        self.tabs = QTabWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_config_tab(), "① 配置+生成")
        self._review_holder = QWidget(); QVBoxLayout(self._review_holder)
        self.tabs.addTab(self._review_holder, "② 试听选优")
        self._accent_holder = QWidget(); QVBoxLayout(self._accent_holder)
        self.tabs.addTab(self._accent_holder, "③ 卡点")
```

4. **Copy verbatim** (these methods are unchanged — `self` now is the editor widget, which is legal as `QMessageBox`/`QFileDialog` parent) from `soundtrack_task_window.py`:
   `task_id` (property), `_work_dir`, `_resolve_output_base`, `_build_config_tab`, `_try_load_existing`, `_mount_session_tabs`, `_persist_session`, `_on_chosen_changed`, `_worker_busy`, `_browse_mp4`, `_browse_out`, `_post_progress`, `_on_start`, `_on_export`, `_run_pipeline`, `_on_regenerate`, `_post_seg_preview`, `_on_done`, `_on_regen_done`, `_on_failed`, `_update_preview_enabled`, `_on_preview`, `_open_output_dir`.

5. **Append `to_payload`** (new):

```python
    def to_payload(self) -> dict:
        return {"mp4": self.mp4_edit.text().strip(),
                "style": self.style_edit.toPlainText().strip(),
                "output_dir": self.out_edit.text().strip()}
```

6. **Drop** `closeEvent` entirely (do not copy it).

> Note: `_run_pipeline` 内原有 `self._task["mp4"/"style"/"output_dir"] = ...` 就地写保留（`_task` 是活 dict）；`to_payload` 是页持久化的读取面，二者并存无害。`_try_load_existing` 内仍 `from sound_track_agent import facade`（lazy）。`test_session_mount_does_not_crash` 直接调 `_mount_session_tabs`，不依赖 `_load_session_safe`，故无需新增该函数。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui/test_soundtrack_editor_smoke.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py tests/test_ui/test_soundtrack_editor_smoke.py
git commit -m "feat(ui): 抽出 SoundtrackEditor(QWidget) + to_payload，供配乐主-详复用"
```

---

### Task 2: `SoundtrackPanel` 改主-详（信号化 + 去开窗）

加 `taskSelected/taskDeleted/taskRenamed` 信号；删「打开」按钮与双击开窗；选中即发 `taskSelected`；新建/删除发对应信号。ctor 形参 `open_window_cb` 保留（AppShell 后续传 None，不再调用）。

**Files:**
- Modify: `drama_shot_master/ui/panels/soundtrack_panel.py`
- Test: `tests/test_ui/test_soundtrack_panel_smoke.py` (rewrite the open-window cases)

- [ ] **Step 1: Update the test to the new contract**

Rewrite `tests/test_ui/test_soundtrack_panel_smoke.py` fully:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import (
    SoundtrackPanel, _SoundtrackTaskView)


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tasks):
    return type("C", (), {"soundtrack_tasks": tasks})()


def test_panel_constructs_and_lists_tasks():
    _app()
    panel = SoundtrackPanel(
        state=None,
        cfg=_cfg([{"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
                   "style": "冷色调", "status": "空闲", "output": ""}]),
        open_window_cb=None, persist_cb=lambda: None)
    assert panel.table.rowCount() == 1
    assert panel.select_mode() == "none"
    ok, _why = panel.validate()
    assert ok is False


def test_selection_emits_task_view():
    _app()
    panel = SoundtrackPanel(
        state=None,
        cfg=_cfg([{"id": "t1", "name": "EP01", "mp4": "", "style": "",
                   "status": "空闲", "output": ""}]),
        open_window_cb=None, persist_cb=lambda: None)
    seen = []
    panel.taskSelected.connect(seen.append)
    panel.table.setCurrentCell(0, 0)
    assert len(seen) == 1
    v = seen[0]
    assert isinstance(v, _SoundtrackTaskView)
    assert v.id == "t1" and v.name == "EP01"


def test_new_appends_and_selects_new_row():
    _app()
    cfg = _cfg([])
    persisted = []
    panel = SoundtrackPanel(state=None, cfg=cfg, open_window_cb=None,
                            persist_cb=lambda: persisted.append(1))
    seen = []
    panel.taskSelected.connect(seen.append)
    panel._on_new()
    assert len(cfg.soundtrack_tasks) == 1
    assert persisted                       # 落盘被调用
    assert seen and seen[-1].id == cfg.soundtrack_tasks[0]["id"]   # 新行被选中


def test_rename_via_name_column_emits_renamed():
    _app()
    cfg = _cfg([{"id": "t1", "name": "旧名", "mp4": "", "style": "",
                 "status": "空闲", "output": ""}])
    persisted, renamed = [], []
    panel = SoundtrackPanel(state=None, cfg=cfg, open_window_cb=None,
                            persist_cb=lambda: persisted.append(1))
    panel.taskRenamed.connect(lambda tid, name: renamed.append((tid, name)))
    panel.table.item(0, 0).setText("新名字")        # 触发 itemChanged
    assert cfg.soundtrack_tasks[0]["name"] == "新名字"
    assert persisted
    assert renamed == [("t1", "新名字")]


def test_del_emits_task_deleted(monkeypatch):
    _app()
    import drama_shot_master.ui.panels.soundtrack_panel as m
    cfg = _cfg([{"id": "t1", "name": "n", "mp4": "", "style": "",
                 "status": "空闲", "output": ""}])
    panel = SoundtrackPanel(state=None, cfg=cfg, open_window_cb=None,
                            persist_cb=lambda: None)
    deleted = []
    panel.taskDeleted.connect(deleted.append)
    panel.table.setCurrentCell(0, 0)
    monkeypatch.setattr(m.QMessageBox, "question",
                        staticmethod(lambda *a, **k: m.QMessageBox.Yes))
    panel._on_del()
    assert cfg.soundtrack_tasks == []
    assert deleted == ["t1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui/test_soundtrack_panel_smoke.py -q`
Expected: FAIL — `ImportError: cannot import name '_SoundtrackTaskView'` (and missing signals).

- [ ] **Step 3: Refactor the panel**

In `drama_shot_master/ui/panels/soundtrack_panel.py`:

(a) Add `Signal` import and the live-view class near the top (after the existing imports, before `SoundtrackPanel`):

```python
from PySide6.QtCore import Qt, Signal
```

```python
class _SoundtrackTaskView:
    """把 cfg.soundtrack_tasks 的 dict 暴露成 .id/.name/.payload（活引用），
    供通用 TaskWorkspacePage（按属性访问）消费。"""

    def __init__(self, d: dict):
        self._d = d

    @property
    def id(self):
        return self._d.get("id", "")

    @property
    def name(self):
        return self._d.get("name", "")

    @property
    def payload(self):
        return self._d
```

(b) Declare signals on the class (right under `class SoundtrackPanel(BasePanel):` docstring):

```python
    taskSelected = Signal(object)
    taskDeleted = Signal(str)
    taskRenamed = Signal(str, str)
```

(c) In `_build_ui`, delete the `self.btn_open` button, its `addWidget`, its `clicked.connect`, and the `itemDoubleClicked` wiring; add a selection handler. Replace the button-bar + table-wiring block:

```python
        bar = QHBoxLayout()
        self.btn_new = QPushButton("+ 新建配乐任务")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "成片 MP4", "状态", "输出"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self.table, 1)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_del.clicked.connect(self._on_del)
```

(d) Delete `_on_open` and `_on_double_clicked` entirely. Add `_on_selection_changed` and `_select_task`:

```python
    def _on_selection_changed(self):
        d = self._selected()
        if d is not None:
            self.taskSelected.emit(_SoundtrackTaskView(d))

    def _select_task(self, tid: str):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.data(Qt.UserRole) == tid:
                self.table.setCurrentCell(r, 0)
                return
```

(e) Rewrite `_on_new` to select the new row instead of opening a window:

```python
    def _on_new(self):
        n = len(self._tasks()) + 1
        task = {"id": _gen_id(), "name": f"配乐任务 {n}", "mp4": "",
                "style": "", "workflow_id": "", "status": "空闲", "output": ""}
        self._tasks().append(task)
        self._persist_cb()
        self.refresh()
        self._select_task(task["id"])
```

(f) In `_on_item_changed`, emit `taskRenamed` after persist (append at the end of the method, inside the matched-id path is fine — emit once after persist):

```python
    def _on_item_changed(self, item):
        if item.column() != 0:
            return
        tid = item.data(Qt.UserRole)
        new_name = item.text().strip()
        if not tid or not new_name:
            return
        for t in self._tasks():
            if t.get("id") == tid:
                t["name"] = new_name
                break
        self._persist_cb()
        self.taskRenamed.emit(tid, new_name)
```

(g) In `_on_del`, emit `taskDeleted` after refresh:

```python
    def _on_del(self):
        t = self._selected()
        if not t:
            return
        if QMessageBox.question(self, "删除", "确定删除该配乐任务？",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        tid = t.get("id")
        self._tasks().remove(t)
        self._persist_cb()
        self.refresh()
        self.taskDeleted.emit(tid)
```

> Keep `__init__`, `select_mode`, `validate`, `execute`, `_tasks`, `_ro`, `_status_item`, `refresh`, `_selected` unchanged. `self._open_window_cb` is still stored but no longer called.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui/test_soundtrack_panel_smoke.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/soundtrack_panel.py tests/test_ui/test_soundtrack_panel_smoke.py
git commit -m "feat(ui): SoundtrackPanel 主-详化（taskSelected/Deleted/Renamed，去开窗）"
```

---

### Task 3: AppShell 接入 `TaskWorkspacePage`（try-import 兜底）

把配乐页从 `_try_make_soundtrack_panel`（裸面板）换成 `_make_soundtrack_page`（通用主-详页），并迁移 status/result/rename/dirty 回调；删旧开窗回调；closeEvent 收尾 flush。

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Test: `tests/test_ui/test_soundtrack_workspace_smoke.py` (new)

- [ ] **Step 1: Write the failing test**

`tests/test_ui/test_soundtrack_workspace_smoke.py`：

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_soundtrack_page_is_task_workspace():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
    w = AppShell()
    page = w.pages["soundtrack"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, SoundtrackPanel)
    assert w._soundtrack_panel() is page.manager


def test_soundtrack_select_creates_editor_inline():
    _app()
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    w = AppShell()
    page = w.pages["soundtrack"]; m = page.manager
    tasks = m.cfg.soundtrack_tasks
    if not tasks:
        m._on_new()
    else:
        m._select_task(tasks[0]["id"])
    tid = m.cfg.soundtrack_tasks[0]["id"]
    assert isinstance(page._editors[tid], SoundtrackEditor)


def test_soundtrack_dirty_writes_back_to_cfg():
    _app()
    w = AppShell()
    if not w.cfg.soundtrack_tasks:
        w.cfg.soundtrack_tasks.append(
            {"id": "tz", "name": "Z", "mp4": "", "style": "", "status": "空闲", "output": ""})
    tid = w.cfg.soundtrack_tasks[0]["id"]
    w._on_soundtrack_dirty(tid, {"mp4": "/a.mp4", "style": "暗黑", "output_dir": "/o"})
    t = next(t for t in w.cfg.soundtrack_tasks if t["id"] == tid)
    assert t["mp4"] == "/a.mp4" and t["style"] == "暗黑" and t["output_dir"] == "/o"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui/test_soundtrack_workspace_smoke.py -q`
Expected: FAIL — `page` is a `SoundtrackPanel`/`QWidget`, not `TaskWorkspacePage`; `_on_soundtrack_dirty` missing.

- [ ] **Step 3: Rewire AppShell**

In `drama_shot_master/ui/app_shell.py`:

(a) In `_build_pages`, change the builder entry:

```python
            "soundtrack": self._make_soundtrack_page,
```

(b) Replace the whole「配乐 tab helpers」block (`_try_make_soundtrack_panel` … `_on_soundtrack_result`, i.e. `app_shell.py:362-425`) with:

```python
    def _make_soundtrack_page(self):
        """try-import 兜底装配配乐主-详页；agent/控件缺失则返回占位空面板。"""
        try:
            from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
            from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
            from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("配乐面板不可用，已跳过: %s", e)
            from PySide6.QtWidgets import QWidget
            return QWidget()
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

    def _persist_soundtrack(self):
        try:
            self.cfg.update_settings(soundtrack_tasks=self.cfg.soundtrack_tasks)
        except Exception:
            pass

    def _soundtrack_panel(self):
        """返回 manager（SoundtrackPanel）；兜底裸 QWidget 时返回 None。"""
        p = self.pages.get("soundtrack")
        return getattr(p, "manager", None)

    def _on_soundtrack_dirty(self, task_id: str, payload: dict):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t.update(payload)        # mp4/style/output_dir
                break
        self._persist_soundtrack()

    def _on_soundtrack_renamed(self, task_id: str, name: str):
        page = self.pages.get("soundtrack")
        if page is not None and hasattr(page, "update_task_name"):
            page.update_task_name(task_id, name)

    def _on_soundtrack_status(self, task_id: str, status: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["status"] = status
        m = self._soundtrack_panel()
        if m is not None and hasattr(m, "refresh"):
            m.refresh()

    def _on_soundtrack_result(self, task_id: str, output: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["output"] = output
        self._persist_soundtrack()
        m = self._soundtrack_panel()
        if m is not None and hasattr(m, "refresh"):
            m.refresh()
```

> This deletes `_try_make_soundtrack_panel`, `_open_soundtrack_window`, `_on_soundtrack_window_closed`, and the `self._soundtrack_windows` dict (no longer referenced anywhere).

(c) In `closeEvent` (`app_shell.py:552`), add a soundtrack flush+persist block after the imggen block and before「持久化当前活跃 panel」:

```python
        # 让配乐页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        sp = self.pages.get("soundtrack")
        if sp is not None and hasattr(sp, "flush_all"):
            sp.flush_all()
        self._persist_soundtrack()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui/test_soundtrack_workspace_smoke.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/app_shell.py tests/test_ui/test_soundtrack_workspace_smoke.py
git commit -m "feat(ui): 配乐接入 TaskWorkspacePage（主-详+浮出），移除旧开窗回调"
```

---

### Task 4: 退役 `SoundtrackTaskWindow`

删旧窗与其 smoke 测试；确认无悬空引用。

**Files:**
- Delete: `drama_shot_master/ui/windows/soundtrack_task_window.py`
- Delete: `tests/test_ui/test_soundtrack_window_smoke.py`

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "soundtrack_task_window\|SoundtrackTaskWindow" drama_shot_master/ tests/`
Expected: only matches inside the two files about to be deleted. If any other file references them, stop and fix that reference first.

- [ ] **Step 2: Delete the window and its test**

```bash
git rm drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_soundtrack_window_smoke.py
```

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all tests green (count = prior 576 − 5 deleted window-smoke + 7 editor + (5−3 net panel) + 3 workspace; exact number not load-bearing, the requirement is **0 failures**).

- [ ] **Step 4: Verify acceptance criteria from the spec**

Run: `grep -rn qfluentwidgets drama_shot_master/ tests/`
Expected: empty (no GPL dep — see [[feedback_no_gpl_deps]]).

Run: `python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; QApplication([]); from drama_shot_master.ui.app_shell import AppShell; from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage as P; w=AppShell(); print({k: isinstance(w.pages[k], P) for k in ('imggen','dubbing','video_gen','soundtrack')})"`
Expected: `{'imggen': True, 'dubbing': True, 'video_gen': True, 'soundtrack': True}` — 四个生成功能均已主-详化。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(ui): 退役 SoundtrackTaskWindow（职责并入 SoundtrackEditor + TaskWorkspacePage）"
```

---

## Self-Review Notes

- **Spec coverage:** §2.1 SoundtrackEditor → Task 1; §2.2 `_SoundtrackTaskView` → Task 2 (3a); §2.3 SoundtrackPanel 改造 7 点 → Task 2 (3b–3g, ctor 保留 open_window_cb); §2.4 退役窗 → Task 4; §3 AppShell 接入（含 `_soundtrack_panel` 改返 manager、status/result 守卫、closeEvent flush、删旧开窗）→ Task 3; §4 测试（editor/workspace/panel/兜底/验收）→ Tasks 1–4 (兜底分支由 try-import 结构覆盖；headless 难造 import 失败，依赖 grep+全绿验收，符合 §4 "若 headless 难做则跳过并记录")。
- **Type consistency:** view 暴露 `.id/.name/.payload`；`editor_factory(view)` 用 `view.payload`，`title_for(view)` 用 `view.name`；editor 信号 `statusChanged(str,str)`/`resultReady(str,str)` 与 AppShell 槽签名一致；`payload_of=lambda ed: ed.to_payload()` 返回 `{mp4,style,output_dir}` 与 `_on_soundtrack_dirty` 的 `t.update(payload)` 对齐。
- **Green between tasks:** Task 1 不删旧窗；Task 2 同改面板与其测试、ctor 兼容旧 AppShell 调用；Task 3 切页后旧窗已无引用；Task 4 删窗+窗测试。
- **No placeholders:** 抽取类的不变方法以「逐一列名 + verbatim copy from 源文件」指明，非 TODO/“类似上文”。
