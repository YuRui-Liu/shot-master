# 多任务并行视频生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「视频生成」从单实例面板重构为任务管理列表 + 每任务一个独立顶级窗口，各窗自带提交 worker（并行），timeline 持久化、可重开重提。

**Architecture:** 新增 Qt-free `VideoTaskStore`（任务数据 + 列表 CRUD + 序列化）；`config` 加 `video_tasks` 字段并迁移旧单缓存；`VideoPanel` 参数化（接收外部 model + 3 个提交转发信号）；新增 `VideoTaskWindow`（顶级窗，窗口失活/关闭时持久化 timeline）+ `VideoTaskManagerPanel`（列表）；`main_window` 接线。

**Tech Stack:** Python stdlib（dataclasses/time/secrets）；PySide6（QMainWindow/QTableWidget/QEvent）；pytest。

**Spec:** [docs/superpowers/specs/2026-05-25-multi-video-tasks-design.md](../specs/2026-05-25-multi-video-tasks-design.md)

---

## File Structure

新增：
- `drama_shot_master/core/video_task_store.py` — `VideoTask` + `VideoTaskStore` + `_gen_task_id`
- `drama_shot_master/ui/windows/__init__.py`（空包）+ `drama_shot_master/ui/windows/video_task_window.py`
- `drama_shot_master/ui/panels/video_task_manager_panel.py`
- `tests/test_core/test_video_task_store.py`

修改：
- `drama_shot_master/config.py` — `video_tasks` 字段 + 落盘 + 迁移
- `drama_shot_master/ui/panels/video_panel.py` — 参数化 model + 3 提交信号；删 `_restore_model`/`save_cache`
- `drama_shot_master/ui/main_window.py` — stack 换 manager + 开窗/持久化/closeEvent
- `tests/test_config.py` — `video_tasks` round-trip + 迁移

---

## Task 1: VideoTaskStore（TDD）

**Files:**
- Create: `drama_shot_master/core/video_task_store.py`
- Create: `tests/test_core/test_video_task_store.py`

- [ ] **Step 1.1: 写失败测试**

Create `tests/test_core/test_video_task_store.py`:

```python
"""Tests for VideoTaskStore."""
from __future__ import annotations

from drama_shot_master.core.video_task_store import VideoTask, VideoTaskStore


def test_add_appends_with_id_and_timestamp():
    s = VideoTaskStore()
    t = s.add("任务 A", {"segments": []})
    assert t.id
    assert t.name == "任务 A"
    assert t.timeline == {"segments": []}
    assert t.updated_at > 0
    assert s.all() == [t]


def test_get_by_id():
    s = VideoTaskStore()
    t = s.add("A", {})
    assert s.get(t.id) is t
    assert s.get("nope") is None


def test_update_fields_refreshes_timestamp():
    s = VideoTaskStore()
    t = s.add("A", {})
    old_ts = t.updated_at
    t2 = s.get(t.id)
    object.__setattr__ if False else None  # noqa (placeholder removed below)
    s.update(t.id, name="B", timeline={"x": 1}, last_result="/o/v.mp4")
    g = s.get(t.id)
    assert g.name == "B"
    assert g.timeline == {"x": 1}
    assert g.last_result == "/o/v.mp4"
    assert g.updated_at >= old_ts


def test_remove():
    s = VideoTaskStore()
    t = s.add("A", {})
    s.remove(t.id)
    assert s.get(t.id) is None
    assert s.all() == []


def test_duplicate_is_deep_and_named():
    s = VideoTaskStore()
    t = s.add("A", {"segments": [{"seg_id": "x"}]})
    dup = s.duplicate(t.id)
    assert dup.id != t.id
    assert "副本" in dup.name
    # 深拷：改副本 timeline 不影响原
    dup.timeline["segments"].append({"seg_id": "y"})
    assert len(s.get(t.id).timeline["segments"]) == 1


def test_roundtrip_to_from_list():
    s = VideoTaskStore()
    s.add("A", {"a": 1})
    s.add("B", {"b": 2})
    data = s.to_list()
    s2 = VideoTaskStore.from_list(data)
    assert [t.name for t in s2.all()] == ["A", "B"]
    assert s2.all()[0].timeline == {"a": 1}


def test_from_list_tolerates_missing_optional_fields():
    s = VideoTaskStore.from_list([{"id": "1", "name": "A", "timeline": {}}])
    t = s.all()[0]
    assert t.last_result == ""
    assert t.updated_at == 0.0
```

(Remove the stray `object.__setattr__ if False else None` line — it was a typo guard; delete it when pasting.)

- [ ] **Step 1.2: 运行测试，确认失败**

Run: `pytest tests/test_core/test_video_task_store.py -v` (or `python3.10 -m pytest`)
Expected: ImportError (module missing).

- [ ] **Step 1.3: 实现 video_task_store.py**

Create `drama_shot_master/core/video_task_store.py`:

```python
"""视频生成任务的数据模型 + 列表存储。

Qt-free，可单测。调用方（main_window）负责把 to_list() 落盘到 settings.json。
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from secrets import token_hex
from typing import Optional


def _gen_task_id() -> str:
    """13 位毫秒戳 + 5 位 hex 随机，与 timeline 内 id 风格一致。"""
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


@dataclass
class VideoTask:
    id: str
    name: str
    timeline: dict
    updated_at: float = 0.0
    last_result: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "timeline": self.timeline,
            "updated_at": self.updated_at, "last_result": self.last_result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VideoTask":
        return cls(
            id=str(d.get("id") or _gen_task_id()),
            name=str(d.get("name") or "未命名任务"),
            timeline=d.get("timeline") or {},
            updated_at=float(d.get("updated_at") or 0.0),
            last_result=str(d.get("last_result") or ""),
        )


class VideoTaskStore:
    """内存维护任务列表。"""

    def __init__(self, tasks: Optional[list[VideoTask]] = None):
        self._tasks: list[VideoTask] = list(tasks or [])

    def all(self) -> list[VideoTask]:
        return list(self._tasks)

    def get(self, task_id: str) -> Optional[VideoTask]:
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, timeline: dict) -> VideoTask:
        t = VideoTask(id=_gen_task_id(), name=name,
                      timeline=copy.deepcopy(timeline), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id: str, *, name: Optional[str] = None,
               timeline: Optional[dict] = None,
               last_result: Optional[str] = None) -> None:
        t = self.get(task_id)
        if t is None:
            return
        if name is not None:
            t.name = name
        if timeline is not None:
            t.timeline = copy.deepcopy(timeline)
        if last_result is not None:
            t.last_result = last_result
        t.updated_at = time.time()

    def remove(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def duplicate(self, task_id: str) -> Optional[VideoTask]:
        src = self.get(task_id)
        if src is None:
            return None
        return self.add(f"{src.name} 副本", copy.deepcopy(src.timeline))

    def to_list(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks]

    @classmethod
    def from_list(cls, data: list[dict]) -> "VideoTaskStore":
        return cls([VideoTask.from_dict(d) for d in (data or [])])
```

- [ ] **Step 1.4: 运行测试，确认通过**

Run: `pytest tests/test_core/test_video_task_store.py -v`
Expected: 7 PASS.

- [ ] **Step 1.5: 全量回归**

Run: `pytest -q`
Expected: 0 failures。

- [ ] **Step 1.6: 提交**

```bash
git add drama_shot_master/core/video_task_store.py tests/test_core/test_video_task_store.py
git commit -m "feat(video-tasks): add VideoTaskStore (task model + list CRUD)

Qt-free VideoTask dataclass + VideoTaskStore (add/get/update/remove/
duplicate with deep-copied timelines + to_list/from_list round-trip).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 1)
- Working dir `/mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master`, branch `feat/video-panel`. Tree clean.
- `timeline` is a `TimelineModel.to_dict()` dict; store treats it opaquely (deep-copies on add/duplicate/update so callers can't alias).

---

## Task 2: config video_tasks 字段 + 迁移（TDD）

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 2.1: 写失败测试**

Append to `tests/test_config.py`:

```python
def test_video_tasks_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(video_tasks=[
        {"id": "1", "name": "T1", "timeline": {"global_prompt": "g"},
         "updated_at": 123.0, "last_result": "/o/v.mp4"}])
    cfg2 = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg2.video_tasks[0]["name"] == "T1"
    assert cfg2.video_tasks[0]["timeline"] == {"global_prompt": "g"}


def test_migrate_old_cache_to_one_task(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(_json.dumps({
        "video_timeline_cache": {"global_prompt": "OLD", "segments": []},
    }))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert len(cfg.video_tasks) == 1
    assert cfg.video_tasks[0]["name"] == "默认任务"
    assert cfg.video_tasks[0]["timeline"] == {"global_prompt": "OLD", "segments": []}


def test_no_migration_when_tasks_exist(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(_json.dumps({
        "video_timeline_cache": {"global_prompt": "OLD"},
        "video_tasks": [{"id": "1", "name": "Keep", "timeline": {}}],
    }))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert len(cfg.video_tasks) == 1
    assert cfg.video_tasks[0]["name"] == "Keep"
```

- [ ] **Step 2.2: 运行测试，确认失败**

Run: `pytest tests/test_config.py -v -k "video_tasks or migrate or no_migration"`
Expected: FAIL（字段不存在 / 未迁移）。

- [ ] **Step 2.3: 加字段 + import**

Edit `drama_shot_master/config.py`.

(a) Near the top, after `import os` (added in a prior feature), add:
```python
import time
from drama_shot_master.core.video_task_store import _gen_task_id
```

(b) In the `Config` dataclass, after `video_timeline_cache: dict = field(default_factory=dict)`, add:
```python
    video_tasks: list = field(default_factory=list)
```

(c) In `update_settings`, add to the persisted `data` dict (before the closing brace):
```python
                "video_tasks": self.video_tasks,
```

- [ ] **Step 2.4: load_config 读取 + 迁移**

Edit `drama_shot_master/config.py`. In `load_config`, inside the settings.json `if isinstance(data, dict):` block, after the `video_timeline_cache` read (the existing block that sets `cfg.video_timeline_cache`), add:
```python
                if "video_tasks" in data and isinstance(data["video_tasks"], list):
                    cfg.video_tasks = data["video_tasks"]
```

Then, immediately before the os.environ sync / `return cfg` at the end of `load_config`, add the migration:
```python
    if not cfg.video_tasks and cfg.video_timeline_cache:
        cfg.video_tasks = [{
            "id": _gen_task_id(),
            "name": "默认任务",
            "timeline": cfg.video_timeline_cache,
            "updated_at": time.time(),
            "last_result": "",
        }]
```
(Place it before the `if cfg.deeplx_url: os.environ[...]` line so both run before return.)

- [ ] **Step 2.5: 运行测试，确认通过**

Run: `pytest tests/test_config.py -v`
Expected: all PASS.

- [ ] **Step 2.6: 全量回归 + 提交**

Run: `pytest -q` → 0 failures。

```bash
git add drama_shot_master/config.py tests/test_config.py
git commit -m "feat(video-tasks): persist video_tasks + migrate old single cache

Config gains a video_tasks list (persisted); load_config reads it and,
when absent, migrates the legacy video_timeline_cache into one 默认任务.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 2)
- `config.py` already `import json` / `import os`. `_gen_task_id` comes from Task 1's store (no circular import: store doesn't import config).
- The old `video_timeline_cache` field/read stays (migration reads it once).

---

## Task 3: VideoPanel 参数化 + 提交转发信号

**Files:**
- Modify: `drama_shot_master/ui/panels/video_panel.py`

- [ ] **Step 3.1: 加 3 个提交信号到类**

Edit `drama_shot_master/ui/panels/video_panel.py`. The `VideoPanel(BasePanel)` class has a docstring then `def __init__`. Insert signal declarations right after the docstring, before `def __init__`:
```python
    submitStarted = Signal()
    submitDone = Signal(str)     # mp4 path
    submitFailed = Signal(str)   # error message
```
Ensure `Signal` is imported. The file imports from `PySide6.QtCore`; confirm `Signal` is in that import — if the current import is `from PySide6.QtCore import Qt, QTimer, QUrl`, change it to `from PySide6.QtCore import Qt, QTimer, QUrl, Signal`.

- [ ] **Step 3.2: 构造改为接收 model**

Edit `drama_shot_master/ui/panels/video_panel.py`. Current:
```python
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self.model = self._restore_model()
```
Change to:
```python
    def __init__(self, state: AppState, cfg: Config,
                 model: Optional[TimelineModel] = None, parent=None):
        super().__init__(state, cfg, parent)
        self.model = model if model is not None else TimelineModel()
```

- [ ] **Step 3.3: emit 提交信号**

Edit `drama_shot_master/ui/panels/video_panel.py`.

(a) In `_on_submit`, the worker is started with `self._worker.start()`. Right after that line, add:
```python
        self.submitStarted.emit()
```

(b) In `_on_submit_done`, current:
```python
    def _on_submit_done(self, mp4_path):
        self.video_status_bar.set_done(Path(mp4_path))
        self.statusMessage.emit(f"视频已保存：{mp4_path}")
```
Add at the end:
```python
        self.submitDone.emit(str(mp4_path))
```

(c) In `_on_submit_failed`, current:
```python
    def _on_submit_failed(self, err_msg: str):
        self.video_status_bar.set_failed(err_msg)
```
Add at the end:
```python
        self.submitFailed.emit(err_msg)
```

- [ ] **Step 3.4: 删除 save_cache + _restore_model**

Edit `drama_shot_master/ui/panels/video_panel.py`. Delete the entire `# ---------- 缓存 ----------` section: both `save_cache` and `_restore_model` methods (the last ~18 lines of the class). They are no longer used (persistence moves to the window).

- [ ] **Step 3.5: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.panels.video_panel import VideoPanel; print('ok')"
```
Expected: `ok`（或 ast 回退）。

- [ ] **Step 3.6: 全量回归**

Run: `pytest -q`
Expected: 0 failures。

> Note: `main_window.py` still does `VideoPanel(self.state, self.cfg)` (no model) — that's fine now (model defaults to empty TimelineModel). It will be replaced by the manager in Task 6. The in-stack video panel is transiently empty between Task 3 and Task 6; tests don't construct it, so the suite stays green.

- [ ] **Step 3.7: 提交**

```bash
git add drama_shot_master/ui/panels/video_panel.py
git commit -m "refactor(video-panel): accept external model + emit submit signals

VideoPanel takes an optional TimelineModel (no longer restores/saves the
single cache) and emits submitStarted/submitDone/submitFailed so a hosting
window can forward status. Drops _restore_model/save_cache.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 3)
- `Optional` and `TimelineModel` are already imported in video_panel.py.
- Do NOT touch the submit logic beyond adding the 3 `emit` lines.

---

## Task 4: VideoTaskWindow

**Files:**
- Create: `drama_shot_master/ui/windows/__init__.py` (empty)
- Create: `drama_shot_master/ui/windows/video_task_window.py`

- [ ] **Step 4.1: 创建 windows 包**

Create `drama_shot_master/ui/windows/__init__.py` with a single line:
```python
"""顶级窗口（非主窗）。"""
```

- [ ] **Step 4.2: 实现 video_task_window.py**

Create `drama_shot_master/ui/windows/video_task_window.py`:

```python
"""VideoTaskWindow：单个视频生成任务的独立顶级窗口。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.config import Config
from drama_shot_master.core.video_timeline_model import TimelineModel
from drama_shot_master.core.video_task_store import VideoTask
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.panels.video_panel import VideoPanel


class VideoTaskWindow(QMainWindow):
    """内嵌一个 VideoPanel 编辑器；提交独立、并行。"""

    statusChanged = Signal(str, str)     # (task_id, status_text)
    resultReady = Signal(str, str)       # (task_id, mp4_path)
    timelineDirty = Signal(str, dict)    # (task_id, timeline_dict)
    closed = Signal(str)                 # (task_id) 关窗后

    def __init__(self, task: VideoTask, state: AppState, cfg: Config,
                 parent=None):
        super().__init__(parent)
        self._task_id = task.id
        self.model = TimelineModel.from_dict(task.timeline)
        self.editor = VideoPanel(state, cfg, self.model)
        self.setCentralWidget(self.editor)
        self.setWindowTitle(f"视频任务 · {task.name}")
        self.resize(1100, 820)

        self.editor.submitStarted.connect(
            lambda: self.statusChanged.emit(self._task_id, "生成中"))
        self.editor.submitDone.connect(self._on_done)
        self.editor.submitFailed.connect(
            lambda e: self.statusChanged.emit(self._task_id, "失败"))

    @property
    def task_id(self) -> str:
        return self._task_id

    def set_title_name(self, name: str) -> None:
        self.setWindowTitle(f"视频任务 · {name}")

    def _persist(self) -> None:
        self.timelineDirty.emit(self._task_id, self.model.to_dict())

    def _on_done(self, mp4: str) -> None:
        self.statusChanged.emit(self._task_id, "完成")
        self.resultReady.emit(self._task_id, mp4)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowDeactivate:
            self._persist()
        super().changeEvent(event)

    def closeEvent(self, event):
        # 停本地轮询（云端可能仍跑）；断开提交转发避免 use-after-free
        try:
            self.editor._cancel_flag["v"] = True
            self.editor.submitStarted.disconnect()
            self.editor.submitDone.disconnect()
            self.editor.submitFailed.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._persist()
        self.closed.emit(self._task_id)
        super().closeEvent(event)
```

- [ ] **Step 4.3: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.windows.video_task_window import VideoTaskWindow; print('ok')"
```
Expected: `ok`（或 ast 回退，如实报告）。

- [ ] **Step 4.4: 提交**

```bash
git add drama_shot_master/ui/windows/__init__.py drama_shot_master/ui/windows/video_task_window.py
git commit -m "feat(video-tasks): add VideoTaskWindow (per-task top-level window)

Hosts a VideoPanel editor, forwards submit status as statusChanged/
resultReady, and persists the timeline (timelineDirty) on WindowDeactivate
and close. On close it stops the local poll and disconnects submit signals.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 4)
- Tasks 1+3 landed: `VideoTask` exists; `VideoPanel(state, cfg, model)` + submit signals exist.
- `editor._cancel_flag` is `{"v": bool}` (the existing cancel mechanism); setting `["v"]=True` ends the poll loop in the running worker.
- Disconnecting all slots of a signal with no args disconnects every connection; guarded by try/except for the case where nothing is connected.

---

## Task 5: VideoTaskManagerPanel

**Files:**
- Create: `drama_shot_master/ui/panels/video_task_manager_panel.py`

- [ ] **Step 5.1: 实现 video_task_manager_panel.py**

Create `drama_shot_master/ui/panels/video_task_manager_panel.py`:

```python
"""VideoTaskManagerPanel：视频生成任务列表（替换原 VideoPanel 在 stack 中的位置）。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView,
)

from drama_shot_master.config import Config
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.core.video_timeline_model import TimelineModel
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState


class VideoTaskManagerPanel(BasePanel):
    """任务列表 + 新建/打开/复制/删除。开窗与持久化由回调交给 main_window。"""

    def __init__(self, state: AppState, cfg: Config,
                 store: VideoTaskStore,
                 open_window_cb, close_window_cb, persist_cb,
                 parent=None):
        super().__init__(state, cfg, parent)
        self.store = store
        self._open_window_cb = open_window_cb     # open_window_cb(task)
        self._close_window_cb = close_window_cb   # close_window_cb(task_id)
        self._persist_cb = persist_cb             # persist_cb()
        self._live_status: dict[str, str] = {}    # task_id → 运行态文本
        self._build_ui()
        self.refresh()

    # ---------- BasePanel ----------
    def select_mode(self) -> str:
        return "none"

    def validate(self) -> tuple[bool, str]:
        return False, "请用列表内按钮管理任务"

    def execute(self):
        raise NotImplementedError("manager uses list buttons")

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_new = QPushButton("+ 新建任务")
        self.btn_open = QPushButton("打开")
        self.btn_dup = QPushButton("复制")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_dup, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "上次结果", "更新时间"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        root.addWidget(self.table, 1)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_dup.clicked.connect(self._on_dup)
        self.btn_del.clicked.connect(self._on_del)

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for t in self.store.all():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(t.name)
            name_item.setData(Qt.UserRole, t.id)
            self.table.setItem(r, 0, name_item)
            status = self._live_status.get(t.id, "空闲")
            self.table.setItem(r, 1, self._readonly(status))
            res = Path(t.last_result).name if t.last_result else "—"
            self.table.setItem(r, 2, self._readonly(res))
            ts = (time.strftime("%m-%d %H:%M", time.localtime(t.updated_at))
                  if t.updated_at else "—")
            self.table.setItem(r, 3, self._readonly(ts))
        self.table.blockSignals(False)

    @staticmethod
    def _readonly(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    def _selected_task_id(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else ""

    # ---------- public ----------
    def set_task_status(self, task_id: str, status: str):
        self._live_status[task_id] = status
        self.refresh()

    def clear_task_status(self, task_id: str):
        self._live_status.pop(task_id, None)
        self.refresh()

    # ---------- slots ----------
    def _on_new(self):
        n = len(self.store.all()) + 1
        t = self.store.add(f"任务 {n}", TimelineModel().to_dict())
        self._persist_cb()
        self.refresh()
        self._open_window_cb(t)

    def _on_open(self):
        tid = self._selected_task_id()
        if not tid:
            QMessageBox.information(self, "打开", "请先选一个任务")
            return
        t = self.store.get(tid)
        if t:
            self._open_window_cb(t)

    def _on_double_clicked(self, item):
        if item.column() == 0:
            return   # 名称列双击 = 进入编辑（重命名），不开窗
        tid = self._selected_task_id()
        t = self.store.get(tid) if tid else None
        if t:
            self._open_window_cb(t)

    def _on_dup(self):
        tid = self._selected_task_id()
        if not tid:
            return
        if self.store.duplicate(tid):
            self._persist_cb()
            self.refresh()

    def _on_del(self):
        tid = self._selected_task_id()
        if not tid:
            return
        if QMessageBox.question(
                self, "删除任务", "确定删除该任务？不可恢复。",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._close_window_cb(tid)      # 若窗开着先关
        self.store.remove(tid)
        self._live_status.pop(tid, None)
        self._persist_cb()
        self.refresh()

    def _on_item_changed(self, item):
        if item.column() != 0:
            return
        tid = item.data(Qt.UserRole)
        new_name = item.text().strip()
        if tid and new_name:
            self.store.update(tid, name=new_name)
            self._persist_cb()
```

- [ ] **Step 5.2: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel; print('ok')"
```
Expected: `ok`（或 ast 回退）。

- [ ] **Step 5.3: 提交**

```bash
git add drama_shot_master/ui/panels/video_task_manager_panel.py
git commit -m "feat(video-tasks): add VideoTaskManagerPanel (task list)

Table of tasks (name/status/last-result/updated) with 新建/打开/复制/删除 and
inline rename. Window open/close/persist are injected callbacks owned by
main_window. set_task_status/clear_task_status update live status.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 5)
- BasePanel signature is `(state, cfg, parent=None)`; this panel adds store + 3 callbacks before parent.
- The manager never opens windows itself — it calls `open_window_cb(task)` / `close_window_cb(task_id)` and persists via `persist_cb()`. main_window (Task 6) wires these.
- `TimelineModel().to_dict()` gives an empty-timeline dict for a fresh task.

---

## Task 6: main_window 接线

**Files:**
- Modify: `drama_shot_master/ui/main_window.py`

- [ ] **Step 6.1: imports**

Edit `drama_shot_master/ui/main_window.py`. Replace:
```python
from drama_shot_master.ui.panels.video_panel import VideoPanel
```
with:
```python
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
from drama_shot_master.ui.windows.video_task_window import VideoTaskWindow
```

- [ ] **Step 6.2: 建 store + 开窗注册表（在 __init__）**

Edit `drama_shot_master/ui/main_window.py`. In `MainWindow.__init__`, after `self.state = AppState()`, add:
```python
        self.video_store = VideoTaskStore.from_list(self.cfg.video_tasks)
        self._open_task_windows: dict[str, VideoTaskWindow] = {}
```

- [ ] **Step 6.3: stack 用 manager 替换 VideoPanel**

Edit `drama_shot_master/ui/main_window.py`. In `_build_ui`, the panels list currently ends with `VideoPanel(self.state, self.cfg),`. Replace that entry:
```python
            VideoTaskManagerPanel(
                self.state, self.cfg, self.video_store,
                self._open_task_window, self._close_task_window,
                self._persist_tasks),
```

- [ ] **Step 6.4: 加开窗/关窗/持久化方法**

Edit `drama_shot_master/ui/main_window.py`. Add these methods to `MainWindow` (e.g. after `_open_refine_settings`):

```python
    def _video_manager(self):
        # stack 中最后一个 panel 即任务管理面板
        return self.panels[-1]

    def _persist_tasks(self):
        try:
            self.cfg.update_settings(video_tasks=self.video_store.to_list())
        except Exception:
            pass

    def _open_task_window(self, task):
        existing = self._open_task_windows.get(task.id)
        if existing is not None:
            existing.raise_(); existing.activateWindow()
            return
        win = VideoTaskWindow(task, self.state, self.cfg)
        win.timelineDirty.connect(self._on_task_dirty)
        win.statusChanged.connect(self._on_task_status)
        win.resultReady.connect(self._on_task_result)
        win.closed.connect(self._on_task_window_closed)
        self._open_task_windows[task.id] = win
        win.show()

    def _close_task_window(self, task_id: str):
        win = self._open_task_windows.get(task_id)
        if win is not None:
            win.close()

    def _on_task_dirty(self, task_id: str, timeline: dict):
        self.video_store.update(task_id, timeline=timeline)
        self._persist_tasks()

    def _on_task_status(self, task_id: str, status: str):
        self._video_manager().set_task_status(task_id, status)

    def _on_task_result(self, task_id: str, mp4: str):
        self.video_store.update(task_id, last_result=mp4)
        self._persist_tasks()
        self._video_manager().refresh()

    def _on_task_window_closed(self, task_id: str):
        self._open_task_windows.pop(task_id, None)
        self._video_manager().clear_task_status(task_id)
        self._video_manager().refresh()
```

- [ ] **Step 6.5: closeEvent 保存所有窗 + 移除旧 VideoPanel 分支**

Edit `drama_shot_master/ui/main_window.py`. Current `closeEvent`:
```python
    def closeEvent(self, e):
        # 保存视频面板缓存（VideoPanel 自己处理）
        for w in self.panels:
            if isinstance(w, VideoPanel):
                w.save_cache()
                break
        # 持久化当前活跃 panel
        try:
            self.cfg.update_settings(
                last_active_function=self.state.active_function or "inference")
        except Exception:
            pass
        super().closeEvent(e)
```
Replace with:
```python
    def closeEvent(self, e):
        # 让每个打开的任务窗口存一次 timeline，再整体落盘
        for win in list(self._open_task_windows.values()):
            try:
                self.video_store.update(win.task_id, timeline=win.model.to_dict())
            except Exception:
                pass
        self._persist_tasks()
        # 持久化当前活跃 panel
        try:
            self.cfg.update_settings(
                last_active_function=self.state.active_function or "inference")
        except Exception:
            pass
        super().closeEvent(e)
```
(This removes the `isinstance(w, VideoPanel)` branch; `VideoPanel` is no longer imported here.)

- [ ] **Step 6.6: 烟测导入 + 全量回归**

Run:
```bash
python -c "from drama_shot_master.ui.main_window import MainWindow; print('ok')"
```
Expected: `ok`（或 ast 回退）。

Run: `pytest -q`
Expected: 0 failures。

- [ ] **Step 6.7: 提交**

```bash
git add drama_shot_master/ui/main_window.py
git commit -m "feat(video-tasks): wire task manager + per-task windows into main_window

The 视频生成 slot is now VideoTaskManagerPanel; main_window owns the
VideoTaskStore, the open-window registry, dirty/status/result persistence,
and saves all open windows on close.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 6)
- Tasks 1–5 landed. `panels[-1]` is the manager (it's the 5th/last panel in the stack list).
- `_on_func_changed` already special-cases `video_gen` (hides thumb/preview/exec) — the manager panel fits that (no preview/exec needed).
- The manager's status updates come from window signals; closing a window clears its live status back to 空闲.

---

## Task 7: 手测清单（end-of-feature）

**Files:** 无代码变更。

- [ ] **Step 7.1: 交回用户手测清单**（spec §7.3）

1. 启动 → 「视频生成」显示任务列表（旧缓存已迁成"默认任务"）。
2. 新建任务 → 弹独立窗口；拖图、写 prompt；列表出现该任务。
3. 再新建 → 第二个独立窗口；两窗并存。
4. 两窗各点提交 → 两 worker 并行；两窗状态栏各自进度；列表两行显"生成中"。
5. 一个完成 → 该窗显示结果、列表该行"完成 + mp4 名"。
6. 关一个窗 → 列表该行回"空闲"；重开 → 轨道/prompt 原样恢复，可再提交。
7. 复制任务 → 新行、timeline 克隆、独立可改。
8. 删除任务（含其窗开着）→ 窗关、行消失。
9. 列表双击名称列改名 → 列表更新（已开窗标题下次打开更新）。
10. 重启 app → 任务列表与各 timeline 持久化恢复。

报告：全过 DONE；任一异常 DONE_WITH_CONCERNS + 具体步。

---

## Self-Review 记录

- **Spec coverage:**
  - §4.1 store → Task 1
  - §4.2 config 字段 + 迁移 → Task 2
  - §4.3 VideoPanel 参数化 + 3 信号 → Task 3
  - §4.4 VideoTaskWindow（持久化 on deactivate/close + 状态转发 + 停轮询） → Task 4
  - §4.5 manager 列表（新建/打开/复制/删除/重命名/状态） → Task 5
  - §4.6 main_window 接线（store/开窗注册/持久化/closeEvent） → Task 6
  - §5 数据流 → Task 4+5+6 合成
  - §6 生命周期（删除关窗/重复打开聚焦/进行中关窗/迁移/use-after-free） → Task 4（closeEvent 断信号）+ Task 5（删除调 close_window_cb）+ Task 6（重复打开聚焦）+ Task 2（迁移）
  - §7.1 store 测试 → Task 1；§7.2 config 测试 → Task 2；§7.3 手测 → Task 7
- **Placeholder scan:** 无 TBD/"similar to"。Task 1.1 测试里那行 `object.__setattr__ if False else None` 是显式标注要删除的占位，已在文中明确指示删除。
- **Type consistency:**
  - `VideoTaskStore.add(name, timeline)->VideoTask` / `update(id,*,name,timeline,last_result)` / `duplicate(id)->VideoTask|None` / `to_list/from_list`（Task 1）→ Task 5/6 调用一致。
  - `VideoPanel(state, cfg, model=None, parent)` + `submitStarted/submitDone(str)/submitFailed(str)`（Task 3）→ Task 4 内嵌 + 连接一致。
  - `VideoTaskWindow(task, state, cfg)` + 信号 `statusChanged(str,str)/resultReady(str,str)/timelineDirty(str,dict)/closed(str)` + `task_id`/`model`/`set_title_name`（Task 4）→ Task 6 连接 + closeEvent 用 `win.task_id`/`win.model` 一致。
  - manager `(state,cfg,store,open_window_cb,close_window_cb,persist_cb)` + `set_task_status/clear_task_status/refresh`（Task 5）→ Task 6 构造 + 调用一致。
  - `cfg.video_tasks`（Task 2）→ Task 6 `VideoTaskStore.from_list(cfg.video_tasks)` 一致。
