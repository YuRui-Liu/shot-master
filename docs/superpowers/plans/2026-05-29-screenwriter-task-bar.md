# 编剧任务栏化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `ScreenwriterPanel` 从单项目 wizard MVP 占位改造为「左任务栏 + 右 wizard」范式，支持多项目并发 SSE 生成，对齐 Dub/ImgGen/Soundtrack/Video 的 `TaskWorkspacePage` 模式。

**Architecture:** `QSplitter[ScreenwriterTaskManager | ScreenwriterWizardHost]`。子面板 worker 改为 `dict[Path, StreamWorker]` 按项目查表，切换不杀别项目 worker；`StreamWorker` 新增 `project_dir` 参数贯穿 signal 链。任务栏读 `Config.screenwriter_projects: list[str]` 持久化路径数组 + 即时扫文件推断 4 阶段状态点。

**Tech Stack:** PySide6 (QSplitter / QTableWidget / QStackedWidget / QThread)，pytest with offscreen Qt platform，自检 SSE worker dict 模式。

**Spec:** `docs/superpowers/specs/2026-05-29-screenwriter-task-bar-design.md`

---

## 文件结构

### 新建

| 文件 | 职责 |
|---|---|
| `drama_shot_master/ui/widgets/screenwriter/task_manager.py` | `ScreenwriterTaskManager` — 左侧任务列表 |
| `drama_shot_master/ui/widgets/screenwriter/wizard_host.py` | `ScreenwriterWizardHost` — stage stepper + 4-page stack |
| `drama_shot_master/ui/widgets/screenwriter/_upstream_banner.py` | `_UpstreamBanner` — 灰色「上游缺失」条 |
| `tests/test_ui/screenwriter/test_task_manager.py` | TaskManager 11 个测试 |
| `tests/test_ui/screenwriter/test_upstream_banner.py` | banner 单元测试 |
| `tests/test_ui/screenwriter/test_screenwriter_panel.py` | 装配 + 集成 4 测试 |

### 修改（破坏性）

| 文件 | 改动 |
|---|---|
| `drama_shot_master/ui/widgets/screenwriter/stream_worker.py` | 加 `project_dir` 字段，所有 signal 加 project_dir 参数 |
| `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py` | 加 worker dict 字段族 + `is_streaming` / `_active_worker` 等 |
| `drama_shot_master/ui/widgets/screenwriter/ideate_page.py` | caller 适配新 worker 签名 + SSE 多项目分流 |
| `drama_shot_master/ui/widgets/screenwriter/script_page.py` | caller 适配 + upstream banner |
| `drama_shot_master/ui/widgets/screenwriter/storyboard_page.py` | caller 适配 + upstream banner |
| `drama_shot_master/ui/panels/screenwriter_panel.py` | 整体重写，从 MVP 占位 → 任务栏化 |
| `drama_shot_master/config.py` | 加 `screenwriter_projects: list[str]` 字段 + 持久化 |
| 既有测试 5 个 | 适配新 StreamWorker 签名 |

---

## Task 1: Config.screenwriter_projects 字段

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_config.py`（如不存在则新建）

- [ ] **Step 1: 找现有 Config 测试位置**

```bash
ls tests/ | grep -i config
```

如无 `test_config.py`，新建：

`tests/test_config.py`：

```python
"""Config 字段持久化的最小回归测试。"""
import json
from pathlib import Path

from drama_shot_master.config import Config


def test_screenwriter_projects_default_empty():
    cfg = Config()
    assert cfg.screenwriter_projects == []


def test_screenwriter_projects_round_trips(tmp_path):
    settings_file = tmp_path / "settings.json"
    cfg = Config()
    cfg.settings_path = settings_file
    cfg.update_settings(screenwriter_projects=["/abs/path/a", "/abs/path/b"])
    # 落盘应包含字段
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert data["screenwriter_projects"] == ["/abs/path/a", "/abs/path/b"]
    # 重载
    cfg2 = Config.load(settings_file)
    assert cfg2.screenwriter_projects == ["/abs/path/a", "/abs/path/b"]
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_config.py -q -p no:faulthandler
```

Expected: FAIL with `AttributeError: 'Config' object has no attribute 'screenwriter_projects'` 或类似。

- [ ] **Step 3: 加字段到 dataclass**

修改 `drama_shot_master/config.py`，在 `screenwriter_stage_assignments` 字段下方加：

```python
# 编剧项目任务列表（绝对路径数组；与 screenwriter_project_root 区分——
# 后者只是「新建」按钮的默认 base，前者是任务栏里被纳管的项目）
screenwriter_projects: list[str] = field(default_factory=list)
```

- [ ] **Step 4: 加 save 落盘项**

在 `update_settings` 的 `data = {...}` 字典里（约 178 行附近，紧跟 `screenwriter_stage_assignments`）加：

```python
"screenwriter_projects": self.screenwriter_projects,
```

- [ ] **Step 5: 加 load 读取**

在 `Config.load` 里（约 274 行附近，`screenwriter_stage_assignments` 处理之后）加：

```python
if "screenwriter_projects" in data and isinstance(
        data["screenwriter_projects"], list):
    cfg.screenwriter_projects = [
        str(x) for x in data["screenwriter_projects"]
        if isinstance(x, str)
    ]
```

- [ ] **Step 6: 跑测试**

```bash
python -m pytest tests/test_config.py -q -p no:faulthandler
```

Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add drama_shot_master/config.py tests/test_config.py
git commit -m "feat(config): 加 screenwriter_projects 持久化字段（list[str] 绝对路径）

任务栏化所需的项目列表存储。与 screenwriter_project_root 区分：
后者是「新建」按钮的默认 base，前者是任务栏里被纳管的项目。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: StreamWorker 三参签名重构

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/stream_worker.py`
- Test: 新建 `tests/test_ui/screenwriter/test_stream_worker.py`（如不存在）

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_stream_worker.py`：

```python
"""StreamWorker 三参签名（含 project_dir）的回归测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def __init__(self, evs):
        self._evs = evs

    def stream_post(self, path, body, params=None):
        for ev in self._evs:
            yield ev


def test_event_signal_includes_project_dir():
    _app()
    captured = []
    w = StreamWorker(_StubClient([{"event": "delta", "data": {"text": "hi"}}]),
                     "/x", {}, params=None, project_dir="/tmp/projA")
    w.event.connect(lambda en, dd, pd: captured.append((en, dd, pd)))
    w.run()  # 同步跑（不调 start）
    assert captured == [("delta", {"text": "hi"}, "/tmp/projA")]


def test_finished_signal_carries_project_dir():
    _app()
    got = []
    w = StreamWorker(_StubClient([]), "/x", {}, params=None,
                     project_dir="/tmp/projB")
    w.finished_ok.connect(got.append)
    w.run()
    assert got == ["/tmp/projB"]


def test_failed_signal_carries_project_dir():
    _app()
    class _Bad:
        def stream_post(self, *a, **k):
            raise RuntimeError("boom")
    got = []
    w = StreamWorker(_Bad(), "/x", {}, params=None, project_dir="/tmp/projC")
    w.failed.connect(lambda msg, pd: got.append((msg, pd)))
    w.run()
    assert got == [("boom", "/tmp/projC")]


def test_project_dir_required_positional():
    _app()
    # 老签名（缺 project_dir）必须报错
    import pytest
    with pytest.raises(TypeError):
        StreamWorker(_StubClient([]), "/x", {}, params=None)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_stream_worker.py -q -p no:faulthandler
```

Expected: FAIL（旧 StreamWorker 不接受 `project_dir` 参数）。

- [ ] **Step 3: 重写 StreamWorker**

替换 `drama_shot_master/ui/widgets/screenwriter/stream_worker.py` 整文件为：

```python
"""SSE 流式 worker：阻塞迭代器 → Qt 信号流，避免堵 UI 线程。

每次生成新建 StreamWorker，不复用。worker 自带 project_dir 字段，
通过 signal 透传，让子面板按当前显示项目分流 UI 更新。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class StreamWorker(QThread):
    """SSE 流式 worker（每实例绑一个 project_dir）。"""
    event = Signal(str, dict, str)       # (event_name, data, project_dir_str)
    finished_ok = Signal(str)            # project_dir_str
    failed = Signal(str, str)            # (msg, project_dir_str)

    def __init__(self, client, path: str, body: dict,
                 params: dict | None, project_dir, parent=None):
        super().__init__(parent)
        self._client = client
        self._path = path
        self._body = body
        self._params = params or {}
        self._project_dir = str(project_dir)

    def run(self):
        try:
            for ev in self._client.stream_post(
                    self._path, self._body, params=self._params):
                if self.isInterruptionRequested():
                    return
                self.event.emit(
                    ev.get("event", ""), ev.get("data", {}),
                    self._project_dir)
            self.finished_ok.emit(self._project_dir)
        except Exception as e:
            self.failed.emit(str(e), self._project_dir)

    def stop(self):
        self.requestInterruption()

    @property
    def project_dir(self) -> str:
        return self._project_dir
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_stream_worker.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

注：T5/T6/T8 的既有测试现在会 fail——T2 通过后 caller 还没改，留给 T5/T6/T7 修复。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/stream_worker.py tests/test_ui/screenwriter/test_stream_worker.py
git commit -m "refactor(ui): StreamWorker 加 project_dir 字段并贯穿 signal

破坏性改动：构造函数从 (client, path, body, params=None) 改为
(client, path, body, params, project_dir)；event/finished_ok/failed 三个
signal 末尾追加 project_dir 字符串。子面板将按当前 _project_dir 分流 UI 更新，
后台 worker 不被切换打断。caller 适配在后续 T5/T6/T7 中。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: _BaseStagePage worker dict 字段族

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py`
- Test: 新建 `tests/test_ui/screenwriter/test_base_stage_page.py`（如已有，append）

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_base_stage_page.py`：

```python
"""_BaseStagePage worker dict 化的最小契约测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage


def _app():
    return QApplication.instance() or QApplication([])


class _Sub(_BaseStagePage):
    """最小可实例化子类。"""
    def set_project(self, path):
        self._project_dir = path


class _FakeWorker:
    def __init__(self, running=True):
        self._running = running
    def isRunning(self):
        return self._running


def test_default_fields_initialized():
    _app()
    s = _Sub(client=None)
    assert s._workers == {}
    assert s._buf_by_project == {}
    assert s._state_by_project == {}
    assert s._error_by_project == {}
    assert s._project_dir is None


def test_is_streaming_false_when_no_worker(tmp_path):
    _app()
    s = _Sub(client=None)
    assert s.is_streaming(tmp_path) is False


def test_is_streaming_true_when_worker_running(tmp_path):
    _app()
    s = _Sub(client=None)
    s._workers[tmp_path] = _FakeWorker(running=True)
    assert s.is_streaming(tmp_path) is True


def test_is_streaming_false_when_worker_stopped(tmp_path):
    _app()
    s = _Sub(client=None)
    s._workers[tmp_path] = _FakeWorker(running=False)
    assert s.is_streaming(tmp_path) is False


def test_active_worker_returns_current_projects_worker(tmp_path):
    _app()
    s = _Sub(client=None)
    s._project_dir = tmp_path
    w = _FakeWorker(running=True)
    s._workers[tmp_path] = w
    assert s._active_worker() is w


def test_active_worker_returns_none_when_no_current_project():
    _app()
    s = _Sub(client=None)
    assert s._active_worker() is None


def test_on_project_switched_default_noop(tmp_path):
    _app()
    s = _Sub(client=None)
    # 默认实现不应抛
    s._on_project_switched(None, tmp_path)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_base_stage_page.py -q -p no:faulthandler
```

Expected: FAIL（字段 / 方法都不存在）。

- [ ] **Step 3: 重写 _BaseStagePage**

替换 `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py` 整文件为：

```python
"""_BaseStagePage：4 个 wizard 阶段子面板的公共基类。

提供 3 个跨阶段信号 + worker dict 字段族 + 工具方法。
具体 UI 在子类 _build_ui 里建。

Worker dict 模式（spec §4.1）：所有 SSE worker 按 project_dir 索引，
切换项目不停别项目的 worker，UI 只显示当前 _project_dir 对应的状态。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class _BaseStagePage(QWidget):
    """所有 wizard 子面板（IdeatePage/ScriptPage/...）的基类。"""
    stageAdvanceRequested = Signal(int)     # 推进到第几个阶段（0..3）
    projectStateChanged = Signal()          # 产物变化 → master 列表状态点要刷
    statusMessage = Signal(str)             # toast 到主窗状态栏

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._project_dir: Path | None = None
        # 多项目并发支持：worker / 缓冲 / 状态 / 错误 按 project_dir 索引
        self._workers: dict[Path, object] = {}        # value: StreamWorker
        self._buf_by_project: dict[Path, str] = {}
        self._state_by_project: dict[Path, str] = {}  # idle/streaming/done/error
        self._error_by_project: dict[Path, str] = {}

    # —— 抽象 ——

    def set_project(self, path: Path | None) -> None:
        raise NotImplementedError

    def try_release(self) -> bool:
        """默认无 dirty。子类有未保存编辑时 override 返 False 可阻断切换。"""
        return True

    # —— 通用工具（给 TaskManager / 子类用）——

    def is_streaming(self, project_dir: Path) -> bool:
        w = self._workers.get(project_dir)
        return bool(w and w.isRunning())

    def _active_worker(self):
        if self._project_dir is None:
            return None
        return self._workers.get(self._project_dir)

    def _on_project_switched(self, old: Path | None, new: Path | None) -> None:
        """切换 hook。默认 no-op，子类可 override。"""
        pass
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_base_stage_page.py -q -p no:faulthandler
```

Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/base_stage_page.py tests/test_ui/screenwriter/test_base_stage_page.py
git commit -m "refactor(ui): _BaseStagePage 加 worker dict 字段族（is_streaming/_active_worker）

字段：_workers / _buf_by_project / _state_by_project / _error_by_project
方法：is_streaming(p) 给 TaskManager 用、_active_worker() 取当前显示项目 worker、
     _on_project_switched(old, new) 给子类 hook（默认 no-op）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: _UpstreamBanner 共享 widget

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/_upstream_banner.py`
- Test: `tests/test_ui/screenwriter/test_upstream_banner.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_upstream_banner.py`：

```python
"""_UpstreamBanner 单元测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner


def _app():
    return QApplication.instance() or QApplication([])


def test_banner_hidden_initially():
    _app()
    b = _UpstreamBanner()
    assert b.isHidden() is True


def test_show_missing_sets_text_and_visible():
    _app()
    b = _UpstreamBanner()
    b.show_missing(stage_name="剧本", expected_file="剧本.md")
    assert not b.isHidden()
    assert "剧本" in b.text()
    assert "剧本.md" in b.text()


def test_hide_after_show():
    _app()
    b = _UpstreamBanner()
    b.show_missing(stage_name="分镜", expected_file="分镜.json")
    b.hide_banner()
    assert b.isHidden() is True


def test_text_method_returns_label_text():
    _app()
    b = _UpstreamBanner()
    b.show_missing(stage_name="提示词", expected_file="prompts/")
    # text() 应返非空
    assert len(b.text()) > 0
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_upstream_banner.py -q -p no:faulthandler
```

Expected: FAIL（ModuleNotFoundError）。

- [ ] **Step 3: 实现 _UpstreamBanner**

`drama_shot_master/ui/widgets/screenwriter/_upstream_banner.py`：

```python
"""灰色「上游缺失」条。

子面板在 set_project 之后自检上游产物缺失时显示；
位置统一在子面板的参数栏下、主编辑器上。
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class _UpstreamBanner(QFrame):
    """显示「上游缺失：请先在『阶段名』生成或手动放入 文件名」。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #3a3a2a; border: 1px solid #5a5a3a; }"
            "QLabel { color: #c0c0a0; padding: 6px; }")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("")
        h.addWidget(self._label)
        self.hide()

    def show_missing(self, stage_name: str, expected_file: str) -> None:
        self._label.setText(
            f"⚠ 上游缺失：请先在「{stage_name}」阶段生成，"
            f"或手动放入 {expected_file}")
        self.show()

    def hide_banner(self) -> None:
        self.hide()

    def text(self) -> str:
        return self._label.text()
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_upstream_banner.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_upstream_banner.py tests/test_ui/screenwriter/test_upstream_banner.py
git commit -m "feat(ui): _UpstreamBanner 共享 widget（灰色「上游缺失」条）

ScriptPage/StoryboardPage/PromptsPage 在 set_project 自检上游产物缺失
时调用 show_missing(stage_name, expected_file) 显示提示。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: IdeatePage caller 适配（新 worker 签名 + dict 化）

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/ideate_page.py`
- Modify: `tests/test_ui/screenwriter/test_ideate_page.py`（适配新签名 + 加多项目并发回归）

- [ ] **Step 1: 跑现有测试看哪里挂**

```bash
python -m pytest tests/test_ui/screenwriter/test_ideate_page.py -q -p no:faulthandler
```

Expected: 部分 fail（StreamWorker 调用缺 project_dir）。记下挂的测试名。

- [ ] **Step 2: 改 _start_stream 调用 + signal connect**

打开 `drama_shot_master/ui/widgets/screenwriter/ideate_page.py`，找到 `_start_stream`（创建 StreamWorker 的地方），替换为：

```python
def _start_stream(self, path, body, params=None):
    if self._project_dir is None:
        return
    self._state_by_project[self._project_dir] = "streaming"
    self._buf_by_project.setdefault(self._project_dir, "")
    self._enter_streaming_view()
    worker = StreamWorker(self._client, path, body, params,
                           project_dir=self._project_dir, parent=self)
    self._workers[self._project_dir] = worker
    worker.event.connect(self._on_sse_event)
    worker.finished_ok.connect(self._on_stream_done_signal)
    worker.failed.connect(self._on_stream_failed)
    worker.start()
```

注：`_enter_streaming_view` 替换原来 `self._gen_btn.hide(); self._stop_btn.show(); ...` 那段 UI 状态切换（提取为新方法以便复用）。

- [ ] **Step 3: 改 _on_sse_event 签名 + 分流**

替换 `_on_sse_event(self, event_name, data)` 为：

```python
def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    # 累 buffer（不论是否当前显示）
    if event_name == "delta":
        text = data.get("text", "")
        self._buf_by_project[proj] = self._buf_by_project.get(proj, "") + text
    elif event_name == "done":
        self._state_by_project[proj] = "done"
        # ideate 阶段把 done 的 candidates 落盘——保留原逻辑，加 proj 参数
        self._handle_done_for_project(proj, data)
    elif event_name == "error":
        self._error_by_project[proj] = data.get("hint") or data.get("message", "")
        self._state_by_project[proj] = "error"

    # 只有当前显示项目才动 UI
    if proj != self._project_dir:
        # 后台项目状态变了，通知 TaskManager 刷新行
        if event_name in ("done", "error"):
            self.projectStateChanged.emit()
        return

    # 当前显示项目的 UI 更新——把原 _on_sse_event 里直接动 UI 的部分搬过来
    self._render_sse_for_current(event_name, data)
```

`_handle_done_for_project(proj, data)` 是新方法，把原 `_on_sse_event("done", ...)` 里**仅依赖文件写入**的逻辑搬过来：

```python
def _handle_done_for_project(self, proj: Path, data: dict):
    # 把原 done 分支里"写文件"部分迁移到这里。例如 ideate 落盘：
    cands = data.get("candidates") or []
    if cands:
        from drama_shot_master.screenwriter_agent.core.atomic_write import atomic_write_text
        import json
        out = proj / "创意.json"
        atomic_write_text(out, json.dumps(
            {"candidates": cands, "selected": data.get("selected_id", "")},
            ensure_ascii=False, indent=2))
```

`_render_sse_for_current(event_name, data)` 是新方法，把 UI 更新部分（如往气泡 append_text、显示 candidates）搬过来。原 IdeatePage `_on_sse_event` 里直接动 `self._bubbles[...]` / `self._cand_list` 的语句全部搬到这里。

- [ ] **Step 4: 改 _on_stream_done_signal / _on_stream_failed 签名**

```python
def _on_stream_done_signal(self, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    # worker 完成清理
    if proj in self._workers:
        self._workers[proj] = None
    if proj == self._project_dir:
        self._exit_streaming_view()
    self.projectStateChanged.emit()


def _on_stream_failed(self, msg: str, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    self._error_by_project[proj] = msg
    self._state_by_project[proj] = "error"
    if proj in self._workers:
        self._workers[proj] = None
    if proj == self._project_dir:
        # 前台失败 → 立即弹
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "生成失败",
                              f"创意生成失败：{msg}\n请检查网络或 LLM 配置。")
        self._exit_streaming_view()
    self.projectStateChanged.emit()
```

- [ ] **Step 5: 改 set_project 接管 streaming view**

在 `set_project` 末尾（成功 load 之后）加：

```python
# 如果该项目有 active worker → UI 接管显示
if path in self._workers and self._workers[path] and self._workers[path].isRunning():
    self._enter_streaming_view()
    # replay buffer 到 UI（如 IdeatePage 用 _MessageBubble，可能不易 replay；
    # 简化做法：只显示「该项目正在后台生成，已收 N 字」label）
    n = len(self._buf_by_project.get(path, ""))
    self._stream_label.setText(f"● 流式 · 已 {n} 字（后台跑）")
else:
    self._exit_streaming_view()
self._on_project_switched(old=None, new=path)
```

注：IdeatePage 的 `_stream_label` 已在 T5 实现里。如果 `_enter_streaming_view` / `_exit_streaming_view` 不存在，从原 `_start_stream` / `_stop_stream` 里拆出来。

- [ ] **Step 6: 在测试里加多项目并发回归**

在 `tests/test_ui/screenwriter/test_ideate_page.py` 末尾加：

```python
def test_two_projects_workers_kept_concurrently(tmp_path):
    _app()
    p = IdeatePage(_StubClient())
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    # 模拟两个 worker（不 start，只挂在 dict 上）
    class _FakeWorker:
        def isRunning(self): return True
    p._workers[pA] = _FakeWorker()
    p._workers[pB] = _FakeWorker()
    p.set_project(pA)
    assert p.is_streaming(pA) is True
    assert p.is_streaming(pB) is True   # 切换不杀 B


def test_sse_event_for_inactive_project_emits_state_change(tmp_path):
    _app()
    p = IdeatePage(_StubClient())
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    p.set_project(pA)
    flips = []
    p.projectStateChanged.connect(lambda: flips.append(True))
    # B 项目的 done 事件应触发 state change（让 TaskManager 刷新行）
    p._on_sse_event("done", {"result": {}, "saved": ""}, str(pB))
    assert len(flips) >= 1
```

注：若已存在的测试断言 `_on_sse_event("delta", {...})` 两参，把第三参补成 `str(p._project_dir)` 或 fixture path。

- [ ] **Step 7: 跑全部 IdeatePage 测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_ideate_page.py -q -p no:faulthandler
```

Expected: PASS (≥7 passed，5 旧 + 2 新)

- [ ] **Step 8: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/ideate_page.py tests/test_ui/screenwriter/test_ideate_page.py
git commit -m "refactor(ui): IdeatePage 适配 worker dict + 三参 StreamWorker

- _start_stream 把 worker 存到 _workers[project_dir]
- _on_sse_event 收 (event, data, project_dir_str)，按 proj 累 buffer
  和落盘，UI 仅在 proj==当前显示项目时更新
- _on_stream_done_signal / _on_stream_failed 签名加 project_dir 参数
- set_project 检测 _workers[path].isRunning() 接管 streaming view
- 加 2 个测试覆盖多项目并发场景

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: ScriptPage caller 适配 + 上游 banner

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/script_page.py`
- Modify: `tests/test_ui/screenwriter/test_script_page.py`

- [ ] **Step 1: 写新失败测试**

在 `tests/test_ui/screenwriter/test_script_page.py` 末尾加：

```python
def test_upstream_missing_shows_banner_and_disables_gen(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)   # 无 创意.json
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False


def test_upstream_present_hides_banner(tmp_path):
    _app()
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._upstream_banner.isHidden()


def test_sse_event_signature_accepts_project_dir(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    # 不应抛
    p._on_sse_event("delta", {"text": "x"}, str(tmp_path))
    assert "x" in p._editor.toPlainText()


def test_sse_delta_for_inactive_project_does_not_touch_editor(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    p.set_project(pA)
    before = p._editor.toPlainText()
    p._on_sse_event("delta", {"text": "ignore"}, str(pB))
    assert p._editor.toPlainText() == before
    # 但 B 的 buffer 应有内容
    assert "ignore" in p._buf_by_project.get(pB, "")
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -p no:faulthandler
```

Expected: 4 新测试 fail；既有 SSE-signature 测试也可能 fail（旧两参 handler）。

- [ ] **Step 3: 改 ScriptPage 加 upstream banner**

在 `script_page.py` 的 `_build_ui` 里，紧跟参数栏之后加 banner：

```python
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
...

def _build_ui(self):
    root = QVBoxLayout(self)
    root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
    root.addLayout(self._build_param_bar())
    self._upstream_banner = _UpstreamBanner()
    root.addWidget(self._upstream_banner)
    # ... 既有 editor + action bar
```

- [ ] **Step 4: 改 set_project 自检上游**

```python
def set_project(self, path):
    if self._project_dir and not self.try_release():
        return
    old = self._project_dir
    self._project_dir = path
    if path is None:
        self._upstream_banner.hide_banner()
        self._gen_btn.setEnabled(False)
        # ... 既有 None 分支
        return
    # 自检上游
    upstream = path / "创意.json"
    if not upstream.is_file():
        self._upstream_banner.show_missing(
            stage_name="创意", expected_file="创意.json")
        self._gen_btn.setEnabled(False)
    else:
        self._upstream_banner.hide_banner()
        self._gen_btn.setEnabled(True)
    # 加载本阶段产物（剧本.md）— 既有逻辑
    self._load_from_disk()
    # 检查 active worker
    if path in self._workers and self._workers[path] and self._workers[path].isRunning():
        self._enter_streaming_view()
    else:
        self._exit_streaming_view()
    self._on_project_switched(old, path)
```

- [ ] **Step 5: 改 _on_sse_event 三参 + 分流**

替换 `_on_sse_event`：

```python
def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    if event_name == "delta":
        text = data.get("text", "")
        self._buf_by_project[proj] = self._buf_by_project.get(proj, "") + text
    elif event_name == "done":
        self._handle_done_for_project(proj, data)
        self._state_by_project[proj] = "done"
    elif event_name == "error":
        self._error_by_project[proj] = data.get("hint") or data.get("message", "")
        self._state_by_project[proj] = "error"

    if proj != self._project_dir:
        if event_name in ("done", "error"):
            self.projectStateChanged.emit()
        return

    # 当前显示项目 → 更新 UI（保留原 ScriptPage 的 delta append 逻辑）
    if event_name == "delta":
        from PySide6.QtGui import QTextCursor
        self._editor.moveCursor(QTextCursor.End)
        self._editor.insertPlainText(data.get("text", ""))
    elif event_name == "done":
        self._exit_streaming_view()
        # 落盘后切到 done 视图（既有逻辑）
    elif event_name == "error":
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "剧本生成失败",
                             self._error_by_project.get(proj, ""))
        self._exit_streaming_view()
```

`_handle_done_for_project(proj, data)`：抽出原 done 分支的落盘代码（写 `剧本.md` 到 `proj`，不再依赖 `self._project_dir`）。

- [ ] **Step 6: 改 _start_stream + signal hookup**

```python
def _start_stream(self, path, body, params=None):
    if self._project_dir is None:
        return
    self._state_by_project[self._project_dir] = "streaming"
    self._buf_by_project.setdefault(self._project_dir, "")
    self._enter_streaming_view()
    worker = StreamWorker(self._client, path, body, params,
                           project_dir=self._project_dir, parent=self)
    self._workers[self._project_dir] = worker
    worker.event.connect(self._on_sse_event)
    worker.finished_ok.connect(self._on_stream_done_signal)
    worker.failed.connect(self._on_stream_failed)
    worker.start()


def _on_stream_done_signal(self, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    if proj in self._workers:
        self._workers[proj] = None
    if proj == self._project_dir:
        self._exit_streaming_view()
    self.projectStateChanged.emit()


def _on_stream_failed(self, msg: str, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    self._error_by_project[proj] = msg
    self._state_by_project[proj] = "error"
    if proj in self._workers:
        self._workers[proj] = None
    if proj == self._project_dir:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "生成失败", f"剧本生成失败：{msg}")
        self._exit_streaming_view()
    self.projectStateChanged.emit()
```

`_enter_streaming_view` / `_exit_streaming_view`：分别隐藏/显示「生成」按钮、显示/隐藏「中止」按钮、更新 `_stream_label`。把原 `_start_stream` 的 UI 部分搬过来。

- [ ] **Step 7: 跑全部 ScriptPage 测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -p no:faulthandler
```

Expected: PASS (≥12 passed，8 旧 + 4 新)

- [ ] **Step 8: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py tests/test_ui/screenwriter/test_script_page.py
git commit -m "refactor(ui): ScriptPage 适配 worker dict + 加 _UpstreamBanner

- _on_sse_event 收 (event, data, project_dir_str)，按 proj 累 buffer 和落盘
- _start_stream 把 worker 存到 _workers[project_dir]
- set_project 自检 创意.json 缺失 → banner + disable 生成
- 4 个新测试覆盖 banner + 多项目并发

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: StoryboardPage caller 适配 + 上游 banner

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/storyboard_page.py`
- Modify: `tests/test_ui/screenwriter/test_storyboard_page.py`

- [ ] **Step 1: 写新失败测试**

在 `tests/test_ui/screenwriter/test_storyboard_page.py` 末尾加：

```python
def test_upstream_missing_shows_banner_and_disables_gen(tmp_path):
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)   # 无 剧本.md
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False


def test_upstream_present_hides_banner(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("# 测试", encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._upstream_banner.isHidden()


def test_sse_event_for_inactive_project_does_not_touch_table(tmp_path):
    _app()
    p = StoryboardPage(_StubClient())
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    p.set_project(pA)
    rows_before = p._shots_model.rowCount()
    p._on_sse_event("done", {
        "saved": str(pB / "分镜.json"),
        "result": {
            "title": "B 标题", "globalStyle": "x",
            "characters": [], "shots": [{"shotId": "S01", "duration": 1,
                                          "composition": "中", "description": "d",
                                          "stylePrompt": "p"}],
        },
        "warnings": [],
    }, str(pB))
    # 当前显示 A，表格不应变
    assert p._shots_model.rowCount() == rows_before
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_storyboard_page.py -q -p no:faulthandler
```

Expected: 3 新 + 既有 SSE 测试 fail。

- [ ] **Step 3: 改 _build_ui 加 banner**

在 `storyboard_page.py` 的 `_build_ui` 里，紧跟参数栏之后插入：

```python
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
...

def _build_ui(self):
    root = QVBoxLayout(self)
    root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
    root.addLayout(self._build_param_bar())
    self._upstream_banner = _UpstreamBanner()
    root.addWidget(self._upstream_banner)
    root.addWidget(self._build_global_header())
    # ... 既有 table + warnings + action bar
```

- [ ] **Step 4: 改 set_project 自检上游**

修改 `set_project` 末尾（在 `self._sb_path = path / "分镜.json"; self._load_from_disk()` 之前加自检；或重组顺序）：

```python
def set_project(self, path):
    if self._project_dir and not self.try_release():
        return
    old = self._project_dir
    self._project_dir = path
    if path is None:
        self._upstream_banner.hide_banner()
        self._sb_path = None
        self._sb = None
        self._set_sb_to_ui(None)
        self._state = "idle"
        for b in (self._gen_btn, self._save_btn, self._view_json_btn,
                   self._advance_btn):
            b.setEnabled(False)
        return
    upstream = path / "剧本.md"
    if not upstream.is_file():
        self._upstream_banner.show_missing(
            stage_name="剧本", expected_file="剧本.md")
        self._gen_btn.setEnabled(False)
    else:
        self._upstream_banner.hide_banner()
        self._gen_btn.setEnabled(True)
    self._sb_path = path / "分镜.json"
    self._load_from_disk()
    self._view_json_btn.setEnabled(self._sb is not None)
    # 检查 active worker
    if path in self._workers and self._workers[path] and self._workers[path].isRunning():
        # 表格暂保留磁盘加载结果；status label 标记
        self._stream_label.setText(
            f"● 流式 · 已 {len(self._buf_by_project.get(path, ''))} 字（后台跑）")
    else:
        self._stream_label.setText("")
    self._on_project_switched(old, path)
```

- [ ] **Step 5: 改 _on_sse_event 三参 + 分流**

替换 `_on_sse_event`：

```python
def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    if event_name == "delta":
        self._buf_by_project[proj] = self._buf_by_project.get(proj, "") + data.get("text", "")
    elif event_name == "status":
        pass   # 不缓存 phase
    elif event_name == "done":
        # 落盘已由 agent 端做；这里只解析 result + warnings
        sb = data.get("result")
        warns = data.get("warnings", [])
        if sb is not None and proj == self._project_dir:
            # 前台：更新表格
            self._sb = sb
            self._warnings = warns or []
            self._set_sb_to_ui(sb)
            self._dirty = False
            self._save_btn.setEnabled(False)
            self._state = "done"
            self._advance_btn.setEnabled(True)
        elif sb is not None:
            # 后台：仅记 state，让 TaskManager 刷新
            self._state_by_project[proj] = "done"
        self.projectStateChanged.emit()
    elif event_name == "error":
        self._error_by_project[proj] = data.get("hint") or data.get("message", "")
        self._state_by_project[proj] = "error"
        self.projectStateChanged.emit()

    if proj != self._project_dir:
        return

    if event_name == "delta":
        self._stream_label.setText(
            f"● 流式 · 已 {len(self._buf_by_project.get(proj, ''))} 字")
    elif event_name == "status":
        phase = data.get("phase", "")
        if phase == "validating":
            self._stream_label.setText(
                f"● 流式 · 已 {len(self._buf_by_project.get(proj, ''))} 字 · 修复中…")
    elif event_name == "error":
        code = data.get("code", "")
        hint = self._error_by_project.get(proj, "")
        details = data.get("details", {})
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QMessageBox
        if code == "JSON_REPAIR_FAILED":
            raw_path = details.get("raw_output_path", "")
            ans = QMessageBox.warning(
                self, "JSON 修复失败",
                f"{hint}\n\nraw 文件: {raw_path}",
                QMessageBox.Open | QMessageBox.Close)
            if ans == QMessageBox.Open and raw_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(raw_path))
        else:
            QMessageBox.warning(self, "分镜生成失败", hint or code)
        self._stop_stream()
```

- [ ] **Step 6: 改 _start_stream + done/failed signal handlers**

```python
def _start_stream(self, path, body, params=None):
    if self._project_dir is None:
        return
    self._state_by_project[self._project_dir] = "streaming"
    self._buf_by_project.setdefault(self._project_dir, "")
    self._state = "streaming"
    self._gen_btn.hide(); self._stop_btn.show()
    self._stream_label.setText("● 流式 · 已 0 字")
    self._save_btn.setEnabled(False)
    self._advance_btn.setEnabled(False)
    worker = StreamWorker(self._client, path, body, params,
                           project_dir=self._project_dir, parent=self)
    self._workers[self._project_dir] = worker
    worker.event.connect(self._on_sse_event)
    worker.finished_ok.connect(self._on_stream_done_signal)
    worker.failed.connect(self._on_stream_failed)
    worker.start()


def _on_stream_done_signal(self, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    if proj in self._workers:
        self._workers[proj] = None
    if proj == self._project_dir:
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")
    self.projectStateChanged.emit()


def _on_stream_failed(self, msg: str, project_dir_str: str):
    from pathlib import Path
    proj = Path(project_dir_str)
    self._error_by_project[proj] = msg
    self._state_by_project[proj] = "error"
    if proj in self._workers:
        self._workers[proj] = None
    if proj == self._project_dir:
        self._stop_stream()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "生成失败",
                             f"分镜生成失败：{msg}\n请检查网络或 LLM 配置。")
    self.projectStateChanged.emit()
```

- [ ] **Step 7: 跑全部 StoryboardPage 测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_storyboard_page.py -q -p no:faulthandler
```

Expected: PASS (≥9 passed，6 旧 + 3 新)

- [ ] **Step 8: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/storyboard_page.py tests/test_ui/screenwriter/test_storyboard_page.py
git commit -m "refactor(ui): StoryboardPage 适配 worker dict + 加 _UpstreamBanner

- 同 ScriptPage：SSE handler 三参化、按 proj 分流 UI 更新、worker 存 dict
- set_project 自检 剧本.md 缺失 → banner + disable 生成
- 3 个新测试覆盖 banner + 后台 done 不动表格

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: ScreenwriterTaskManager 左侧任务栏

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/task_manager.py`
- Create: `tests/test_ui/screenwriter/test_task_manager.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_task_manager.py`：

```python
"""ScreenwriterTaskManager 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QFileDialog, QMessageBox

from drama_shot_master.ui.widgets.screenwriter.task_manager import ScreenwriterTaskManager


def _app():
    return QApplication.instance() or QApplication([])


class _StubCfg:
    """模拟 Config：只持 screenwriter_projects + project_root + update_settings。"""
    def __init__(self, projects=None, root=""):
        self.screenwriter_projects = list(projects or [])
        self.screenwriter_project_root = root
        self._saved = {}

    def update_settings(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._saved.update(kw)


def test_refresh_empty_list_shows_no_rows():
    _app()
    tm = ScreenwriterTaskManager(_StubCfg())
    assert tm._table.rowCount() == 0


def test_refresh_renders_status_dots_from_files(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    (pA / "创意.json").write_text("{}", encoding="utf-8")
    (pA / "剧本.md").write_text("# X", encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    assert tm._table.rowCount() == 1
    # 状态点列含 ✓✓○○
    dots = tm._table.item(0, 1).text() if tm._table.item(0, 1) else \
           tm._table.cellWidget(0, 1).text()
    assert "✓" in dots
    assert "○" in dots


def test_refresh_prunes_missing_dirs(tmp_path):
    _app()
    cfg = _StubCfg(projects=[str(tmp_path / "nonexistent")])
    tm = ScreenwriterTaskManager(cfg)
    # 列表里不应有该路径
    assert cfg.screenwriter_projects == []


def test_new_creates_subdir_under_root(tmp_path, monkeypatch):
    _app()
    cfg = _StubCfg(root=str(tmp_path))
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QInputDialog, "getText",
                          staticmethod(lambda *a, **k: ("项目1", True)))
    tm._on_new_clicked()
    assert (tmp_path / "项目1").is_dir()
    assert str(tmp_path / "项目1") in cfg.screenwriter_projects


def test_new_same_name_warns(tmp_path, monkeypatch):
    _app()
    (tmp_path / "A").mkdir()
    cfg = _StubCfg(projects=[str(tmp_path / "A")], root=str(tmp_path))
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QInputDialog, "getText",
                          staticmethod(lambda *a, **k: ("A", True)))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                          staticmethod(lambda *a, **k: warned.append(True)))
    tm._on_new_clicked()
    assert warned


def test_open_adds_external_dir(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg()
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                          staticmethod(lambda *a, **k: str(pA)))
    tm._on_open_clicked()
    assert str(pA) in cfg.screenwriter_projects


def test_open_duplicate_warns(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                          staticmethod(lambda *a, **k: str(pA)))
    info = []
    monkeypatch.setattr(QMessageBox, "information",
                          staticmethod(lambda *a, **k: info.append(True)))
    tm._on_open_clicked()
    assert info


def test_delete_list_only_keeps_dir(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm._table.selectRow(0)
    # mock QMessageBox：点「仅从列表移除」
    class _Box:
        def __init__(self, *a, **k):
            self._btns = {}
        def setWindowTitle(self, _): pass
        def setText(self, _): pass
        def addButton(self, label, role=None):
            b = object()
            self._btns[id(b)] = label
            return b
        def exec(self): self._clicked = list(self._btns.keys())[0]
        def clickedButton(self): return next(
            k for k, v in self._btns.items() if v == "仅从列表移除")
    monkeypatch.setattr("drama_shot_master.ui.widgets.screenwriter.task_manager.QMessageBox",
                         _Box)
    # 用 closure 让 _on_delete_clicked 内部的 QMessageBox 引用上面的 mock
    # 由于代码里用 `box = QMessageBox(...)` + `box.clickedButton()`，mock 类即可
    tm._on_delete_clicked()
    assert str(pA) not in cfg.screenwriter_projects
    assert pA.is_dir()  # 目录保留


def test_delete_purge_removes_dir(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    (pA / "file.txt").write_text("x", encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm.set_active_worker_query(lambda p: False)
    tm._table.selectRow(0)
    class _Box:
        def __init__(self, *a, **k): pass
        def setWindowTitle(self, _): pass
        def setText(self, _): pass
        def addButton(self, label, role=None):
            self._label = label
            return label
        def exec(self): pass
        def clickedButton(self): return "连同目录删除"
    monkeypatch.setattr("drama_shot_master.ui.widgets.screenwriter.task_manager.QMessageBox",
                         _Box)
    tm._on_delete_clicked()
    assert str(pA) not in cfg.screenwriter_projects
    assert not pA.is_dir()


def test_delete_blocked_when_worker_active(tmp_path, monkeypatch):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm.set_active_worker_query(lambda p: True)
    tm._table.selectRow(0)
    class _Box:
        def __init__(self, *a, **k): pass
        def setWindowTitle(self, _): pass
        def setText(self, _): pass
        def addButton(self, label, role=None): return label
        def exec(self): pass
        def clickedButton(self): return "连同目录删除"
    monkeypatch.setattr("drama_shot_master.ui.widgets.screenwriter.task_manager.QMessageBox",
                         _Box)
    warned = []
    # 拒绝时的 warning 属于 QMessageBox.warning 静态调用——也 mock
    _Box.warning = staticmethod(lambda *a, **k: warned.append(True))
    tm._on_delete_clicked()
    assert pA.is_dir()
    assert str(pA) in cfg.screenwriter_projects   # 没被删
    assert warned


def test_task_selected_emits_path(tmp_path):
    _app()
    pA = tmp_path / "X"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    got = []
    tm.taskSelected.connect(got.append)
    tm._table.selectRow(0)
    tm._on_selection_changed()
    assert got == [pA]
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_task_manager.py -q -p no:faulthandler
```

Expected: FAIL（ModuleNotFoundError）。

- [ ] **Step 3: 实现 ScreenwriterTaskManager**

`drama_shot_master/ui/widgets/screenwriter/task_manager.py`：

```python
"""ScreenwriterTaskManager：编剧面板左侧任务列表。

与 Dub/ImgGen 范式一致：QTableWidget 4 列（名称/状态点/当前阶段/更新时间）
+ 工具栏 [新建/打开/删除]。多项目并发支持，状态点即时扫文件推断。

持久化：cfg.screenwriter_projects: list[str]（绝对路径）。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QInputDialog, QFileDialog, QMessageBox,
    QLabel,
)


_STAGE_FILES = (
    ("创意", "创意.json"),
    ("剧本", "剧本.md"),
    ("分镜", "分镜.json"),
    ("提示词", "prompts"),     # 目录非空
)


class ScreenwriterTaskManager(QWidget):
    """编剧任务列表（左侧栏）。"""
    taskSelected = Signal(object)         # Path | None
    projectAdded = Signal(object)         # Path
    projectRemoved = Signal(object)       # Path

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._projects: list[Path] = [
            Path(p) for p in (cfg.screenwriter_projects or [])]
        # 询问外部「某项目当前是否有 worker 在跑」的回调（由 ScreenwriterPanel 注入）
        self._active_worker_query = lambda p: False
        self._build_ui()
        self.refresh()
        # 30s 定时刷
        self._timer = QTimer(self)
        self._timer.setInterval(30000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def set_active_worker_query(self, fn) -> None:
        self._active_worker_query = fn

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)
        # 工具栏
        bar = QHBoxLayout()
        bar.setSpacing(4)
        btn_new = QPushButton("+ 新建")
        btn_new.clicked.connect(self._on_new_clicked)
        bar.addWidget(btn_new)
        btn_open = QPushButton("📂 打开")
        btn_open.clicked.connect(self._on_open_clicked)
        bar.addWidget(btn_open)
        btn_del = QPushButton("🗑 删除")
        btn_del.clicked.connect(self._on_delete_clicked)
        bar.addWidget(btn_del)
        bar.addStretch(1)
        v.addLayout(bar)
        # 表格
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["名称", "状态", "当前阶段", "更新"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.setColumnWidth(1, 60)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.viewport().installEventFilter(self)
        v.addWidget(self._table, 1)
        # 状态注脚
        self._footer = QLabel("")
        self._footer.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        v.addWidget(self._footer)

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if obj is self._table.viewport() and ev.type() == QEvent.Resize:
            self._fit_name_col()
        return super().eventFilter(obj, ev)

    def _fit_name_col(self) -> None:
        vw = self._table.viewport().width()
        used = self._table.columnWidth(1) + self._table.columnWidth(2) \
               + self._table.columnWidth(3)
        self._table.setColumnWidth(0, max(100, vw - used))

    # —— 数据 ——

    def refresh(self) -> None:
        # 1) 剪枝：清掉已不存在的目录
        valid: list[Path] = []
        for p in self._projects:
            if p.is_dir():
                valid.append(p)
        if len(valid) != len(self._projects):
            self._projects = valid
            self._save()
        # 2) 重绘表格
        self._table.setRowCount(0)
        for p in self._projects:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(p.name))
            dots, current_stage = self._compute_status(p)
            self._table.setItem(row, 1, QTableWidgetItem(dots))
            self._table.setItem(row, 2, QTableWidgetItem(current_stage))
            mtime = self._dir_mtime(p)
            self._table.setItem(row, 3, QTableWidgetItem(mtime))
        self._footer.setText(f"{len(self._projects)} 个项目")
        self._fit_name_col()

    def _compute_status(self, p: Path) -> tuple[str, str]:
        dots = []
        last_done_idx = -1
        for i, (_, fname) in enumerate(_STAGE_FILES):
            target = p / fname
            done = target.is_file() if not fname.endswith("/") and "/" not in fname else False
            if fname == "prompts":
                done = target.is_dir() and any(target.iterdir())
            else:
                done = target.is_file()
            if done:
                dots.append("✓")
                last_done_idx = i
            else:
                dots.append("○")
        # streaming 覆盖
        if self._active_worker_query(p):
            return "".join(dots), "生成中"
        # 当前阶段
        if last_done_idx == len(_STAGE_FILES) - 1:
            return "".join(dots), "已完成"
        next_idx = last_done_idx + 1
        next_stage = _STAGE_FILES[next_idx][0]
        return "".join(dots), f"待 {next_stage}"

    def _dir_mtime(self, p: Path) -> str:
        try:
            ts = p.stat().st_mtime
        except OSError:
            return ""
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M")

    # —— 工具栏 actions ——

    def _on_new_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, "新建编剧项目", "项目名：")
        if not ok or not name.strip():
            return
        base = Path(self._cfg.screenwriter_project_root
                    or Path.home() / "drama-projects")
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "失败", f"创建 base 目录失败：{e}")
            return
        new_dir = base / name.strip()
        if new_dir.exists():
            QMessageBox.warning(self, "同名", f"{new_dir} 已存在")
            return
        try:
            new_dir.mkdir(parents=True)
        except OSError as e:
            QMessageBox.warning(self, "失败", str(e)); return
        self._add_project(new_dir)

    def _on_open_clicked(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择项目目录")
        if not d:
            return
        p = Path(d)
        if p in self._projects:
            QMessageBox.information(self, "已在列表",
                                       f"{p} 已经在任务列表里")
            return
        self._add_project(p)

    def _on_delete_clicked(self) -> None:
        p = self._selected_project()
        if p is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除项目")
        box.setText(f"确认删除「{p.name}」？")
        btn_listonly = box.addButton("仅从列表移除", QMessageBox.AcceptRole)
        btn_purge = box.addButton("连同目录删除", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_listonly or clicked == "仅从列表移除":
            self._remove_from_list(p)
            return
        if clicked is btn_purge or clicked == "连同目录删除":
            if self._active_worker_query(p):
                QMessageBox.warning(self, "项目仍在生成",
                                       "请先停止当前阶段")
                return
            try:
                shutil.rmtree(p)
            except OSError as e:
                QMessageBox.warning(self, "删除失败", str(e)); return
            self._remove_from_list(p)

    def _selected_project(self) -> Path | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._projects):
            return self._projects[idx]
        return None

    def _add_project(self, p: Path) -> None:
        if p in self._projects:
            return
        self._projects.append(p)
        self._save()
        self.refresh()
        self.projectAdded.emit(p)

    def _remove_from_list(self, p: Path) -> None:
        if p in self._projects:
            self._projects.remove(p)
            self._save()
            self.refresh()
            self.projectRemoved.emit(p)

    def _save(self) -> None:
        self._cfg.update_settings(
            screenwriter_projects=[str(p) for p in self._projects])

    def _on_selection_changed(self) -> None:
        p = self._selected_project()
        self.taskSelected.emit(p)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_task_manager.py -q -p no:faulthandler
```

Expected: PASS (11 passed)

注：mock QMessageBox 的策略可能需要微调以适配实际实现。若 `clicked is btn_*` 比较不成立（因为 mock 返字符串），代码已加 `or clicked == "..."` 兜底。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/task_manager.py tests/test_ui/screenwriter/test_task_manager.py
git commit -m "feat(ui): ScreenwriterTaskManager 左侧任务栏（4 列 + 工具栏 + 30s 定时刷）

- 4 列：名称（伸缩，min 100）/ 状态点（✓○）/ 当前阶段 / 更新时间
- 工具栏：[新建/打开/删除]，删除弹三项 dialog（仅移除/连目录/取消）
- 持久化 cfg.screenwriter_projects: list[str]，refresh 时自动剪枝失效路径
- set_active_worker_query 注入外部回调，让状态点能反映 worker 状态
- 11 测试覆盖核心路径

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: ScreenwriterWizardHost 右侧 wizard host

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/wizard_host.py`
- Test: `tests/test_ui/screenwriter/test_wizard_host.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_wizard_host.py`：

```python
"""ScreenwriterWizardHost 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QLabel

from drama_shot_master.ui.widgets.screenwriter.wizard_host import ScreenwriterWizardHost


def _app():
    return QApplication.instance() or QApplication([])


def test_host_builds_with_4_pages():
    _app()
    pages = [QLabel(f"P{i}") for i in range(4)]
    host = ScreenwriterWizardHost(pages, stage_names=["创意", "剧本", "分镜", "提示词"])
    assert host._stack.count() == 4


def test_stage_button_switches_stack():
    _app()
    pages = [QLabel(f"P{i}") for i in range(4)]
    host = ScreenwriterWizardHost(pages, stage_names=["创意", "剧本", "分镜", "提示词"])
    host.set_stage(2)
    assert host._stack.currentIndex() == 2


def test_invalid_stage_index_clamped():
    _app()
    pages = [QLabel(f"P{i}") for i in range(4)]
    host = ScreenwriterWizardHost(pages, stage_names=["a", "b", "c", "d"])
    host.set_stage(99)
    assert host._stack.currentIndex() in (3, 0)   # 不崩
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_wizard_host.py -q -p no:faulthandler
```

Expected: FAIL（ModuleNotFoundError）。

- [ ] **Step 3: 实现 ScreenwriterWizardHost**

`drama_shot_master/ui/widgets/screenwriter/wizard_host.py`：

```python
"""ScreenwriterWizardHost：编剧面板右侧 wizard host。

顶部 stage stepper（4 按钮）+ QStackedWidget（4 子面板）。
stage 按钮无条件切换（spec issue #4），上游缺失由子面板自己显示 banner。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
)


class ScreenwriterWizardHost(QWidget):
    """右侧 wizard host。"""
    stageChanged = Signal(int)

    def __init__(self, pages: list[QWidget], stage_names: list[str], parent=None):
        super().__init__(parent)
        assert len(pages) == len(stage_names) == 4
        self._pages = pages
        self._buttons: list[QPushButton] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)
        # Stage stepper
        bar = QHBoxLayout()
        bar.setSpacing(2)
        for i, name in enumerate(stage_names):
            btn = QPushButton(f"{i + 1}. {name}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, idx=i: self.set_stage(idx))
            bar.addWidget(btn)
            self._buttons.append(btn)
        bar.addStretch(1)
        v.addLayout(bar)
        # Stack
        self._stack = QStackedWidget()
        for pg in pages:
            self._stack.addWidget(pg)
        v.addWidget(self._stack, 1)
        self.set_stage(0)

    def set_stage(self, idx: int) -> None:
        n = self._stack.count()
        if idx < 0:
            idx = 0
        if idx >= n:
            idx = n - 1
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._buttons):
            b.setChecked(i == idx)
        self.stageChanged.emit(idx)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_wizard_host.py -q -p no:faulthandler
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/wizard_host.py tests/test_ui/screenwriter/test_wizard_host.py
git commit -m "feat(ui): ScreenwriterWizardHost（stage stepper + 4 子面板 stack）

无条件切换，上游缺失由子面板自己显示 banner（spec issue #4）。
索引越界 clamped 到 [0, n-1] 不崩。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: ScreenwriterPanel 整体重写（任务栏化装配）

**Files:**
- Modify: `drama_shot_master/ui/panels/screenwriter_panel.py`（完全重写）
- Create: `tests/test_ui/screenwriter/test_screenwriter_panel.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_screenwriter_panel.py`：

```python
"""ScreenwriterPanel 装配的端到端测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel


def _app():
    return QApplication.instance() or QApplication([])


class _StubCfg:
    def __init__(self, projects=None, root=""):
        self.screenwriter_projects = list(projects or [])
        self.screenwriter_project_root = root
        self.screenwriter_agent_port = 18999
        self.screenwriter_stage_assignments = {}
        self.screenwriter_llm_api_key = ""
        self.screenwriter_llm_base_url = ""
        self.llm_providers = {}
        self._saved = {}

    def update_settings(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._saved.update(kw)


def test_panel_builds_with_splitter_and_4_pages():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    assert panel._task_manager is not None
    assert panel._wizard_host is not None
    assert panel._wizard_host._stack.count() == 4


def test_task_selection_propagates_to_all_pages(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)
    # 模拟用户选第 0 行
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    # 4 个 page 的 _project_dir 都应是 pA
    for i in range(4):
        page = panel._wizard_host._stack.widget(i)
        # PromptsPage placeholder 可能是 QLabel，没有 _project_dir
        if hasattr(page, "_project_dir"):
            assert page._project_dir == pA


def test_stage_stepper_unconditional_switch():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    panel._wizard_host.set_stage(2)
    assert panel._wizard_host._stack.currentIndex() == 2
    panel._wizard_host.set_stage(0)
    assert panel._wizard_host._stack.currentIndex() == 0


def test_dirty_page_blocks_task_switch(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    panel = ScreenwriterPanel(cfg)
    # 先选 A
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    # 注入：让所有 page 的 try_release 返 False
    for i in range(4):
        page = panel._wizard_host._stack.widget(i)
        if hasattr(page, "try_release"):
            page.try_release = lambda: False  # type: ignore
    # 试着切到 B
    panel._task_manager._table.selectRow(1)
    panel._task_manager._on_selection_changed()
    # 各 page 的 _project_dir 仍是 pA（切换被拒）
    for i in range(4):
        page = panel._wizard_host._stack.widget(i)
        if hasattr(page, "_project_dir"):
            assert page._project_dir == pA


def test_active_worker_query_aggregates_across_pages(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)
    # 默认无 worker → False
    assert panel._any_page_streaming(pA) is False
    # 给 IdeatePage 注入 mock
    page = panel._wizard_host._stack.widget(0)
    class _W:
        def isRunning(self): return True
    page._workers[pA] = _W()
    assert panel._any_page_streaming(pA) is True
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py -q -p no:faulthandler
```

Expected: FAIL（ImportError 或类不存在某属性）。

- [ ] **Step 3: 重写 ScreenwriterPanel**

替换 `drama_shot_master/ui/panels/screenwriter_panel.py` 整文件为：

```python
"""ScreenwriterPanel：编剧面板（任务栏化）。

左 ScreenwriterTaskManager + 右 ScreenwriterWizardHost。
4 个子面板单例：IdeatePage / ScriptPage / StoryboardPage / PromptsPage（placeholder）。
切换任务 → 全 page 统一 try_release + set_project；任一拒 → 回滚。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QSplitter, QLabel,
)

from drama_shot_master.agents.screenwriter_client import ScreenwriterClient
from drama_shot_master.ui.widgets.screenwriter.task_manager import ScreenwriterTaskManager
from drama_shot_master.ui.widgets.screenwriter.wizard_host import ScreenwriterWizardHost
from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage
from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage
from drama_shot_master.ui.widgets.screenwriter.storyboard_page import StoryboardPage


_STAGE_NAMES = ["创意", "剧本", "分镜", "提示词"]


class _PromptsPlaceholder(QWidget):
    """提示词阶段占位（待 PromptsPage 实现后替换）。"""
    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._project_dir = None
        self._workers = {}
        from PySide6.QtWidgets import QVBoxLayout
        v = QVBoxLayout(self)
        v.addWidget(QLabel("提示词阶段（PromptsPage 待实现，占位）"))

    def set_project(self, path):
        self._project_dir = path

    def try_release(self) -> bool:
        return True

    def is_streaming(self, p) -> bool:
        return False


class ScreenwriterPanel(QWidget):
    """编剧面板入口（任务栏化）。"""
    statusMessage = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._client = ScreenwriterClient(
            base_url=f"http://127.0.0.1:{cfg.screenwriter_agent_port}")
        self._last_selected: Path | None = None
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        # 左
        self._task_manager = ScreenwriterTaskManager(self._cfg)
        self._task_manager.setMaximumWidth(300)
        self._task_manager.setMinimumWidth(220)
        splitter.addWidget(self._task_manager)
        # 右
        ideate = IdeatePage(self._client)
        script = ScriptPage(self._client)
        storyboard = StoryboardPage(self._client)
        prompts = _PromptsPlaceholder(self._client)
        self._pages = [ideate, script, storyboard, prompts]
        self._wizard_host = ScreenwriterWizardHost(
            self._pages, stage_names=_STAGE_NAMES)
        splitter.addWidget(self._wizard_host)
        splitter.setSizes([280, 900])
        h.addWidget(splitter)

    def _wire_signals(self) -> None:
        self._task_manager.taskSelected.connect(self._on_task_selected)
        self._task_manager.set_active_worker_query(self._any_page_streaming)
        for pg in self._pages:
            if hasattr(pg, "projectStateChanged"):
                pg.projectStateChanged.connect(self._task_manager.refresh)
            if hasattr(pg, "statusMessage"):
                pg.statusMessage.connect(self.statusMessage)
            if hasattr(pg, "stageAdvanceRequested"):
                pg.stageAdvanceRequested.connect(self._wizard_host.set_stage)

    def _on_task_selected(self, path: Path | None) -> None:
        # 统一切换：先全员 try_release，全 OK 才推进
        for pg in self._pages:
            if hasattr(pg, "try_release") and not pg.try_release():
                # 回滚 task manager 选择
                self._restore_selection()
                return
        for pg in self._pages:
            if hasattr(pg, "set_project"):
                pg.set_project(path)
        self._last_selected = path

    def _restore_selection(self) -> None:
        """try_release 拒绝时，把表格选择还原到 _last_selected。"""
        tm = self._task_manager
        if self._last_selected is None:
            tm._table.clearSelection()
            return
        for row in range(tm._table.rowCount()):
            item = tm._table.item(row, 0)
            if item and item.text() == self._last_selected.name:
                # blockSignals 防止 _on_selection_changed 再触发一遍
                tm._table.blockSignals(True)
                tm._table.selectRow(row)
                tm._table.blockSignals(False)
                return

    def _any_page_streaming(self, project_dir: Path) -> bool:
        for pg in self._pages:
            if hasattr(pg, "is_streaming") and pg.is_streaming(project_dir):
                return True
        return False
```

- [ ] **Step 4: 跑全部 ScreenwriterPanel 测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py -q -p no:faulthandler
```

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/screenwriter_panel.py tests/test_ui/screenwriter/test_screenwriter_panel.py
git commit -m "feat(ui): ScreenwriterPanel 任务栏化（QSplitter[TaskManager | WizardHost]）

- 左 ScreenwriterTaskManager（max 300）
- 右 ScreenwriterWizardHost（4 子面板）
- taskSelected → 全员 try_release，全 OK 才统一 set_project；任一拒 → 回滚
- projectStateChanged 联动 TaskManager 刷新
- set_active_worker_query 注入聚合查询：任一 page 的 _workers[p] 在跑就 True
- PromptsPage 暂用 _PromptsPlaceholder（T74/T75 完成后替换）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: 集成验收（全套件 + 多项目并发集成）

**Files:**
- Append: `tests/test_ui/screenwriter/test_screenwriter_panel.py`

- [ ] **Step 1: 加多项目并发集成测试**

在 `test_screenwriter_panel.py` 末尾追加：

```python
def test_two_projects_streaming_concurrently_keeps_both_workers(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    panel = ScreenwriterPanel(cfg)

    ideate = panel._pages[0]  # IdeatePage
    storyboard = panel._pages[2]  # StoryboardPage

    class _W:
        def __init__(self): self._running = True
        def isRunning(self): return self._running
        def stop(self): self._running = False

    # 在 IdeatePage 给 A 灌 worker
    wA = _W()
    ideate._workers[pA] = wA
    # 在 StoryboardPage 给 B 灌 worker
    wB = _W()
    storyboard._workers[pB] = wB

    # 选 A
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    # A 的 worker 显示在 IdeatePage
    assert ideate._project_dir == pA
    assert ideate._active_worker() is wA

    # 切到 B
    panel._task_manager._table.selectRow(1)
    panel._task_manager._on_selection_changed()
    # A 的 worker 没死
    assert wA.isRunning() is True
    # B 的 worker 仍在 StoryboardPage
    assert wB.isRunning() is True
    # 当前显示 B
    assert ideate._project_dir == pB
    assert storyboard._project_dir == pB


def test_external_dir_removal_prunes_on_refresh(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    panel = ScreenwriterPanel(cfg)
    # 外部删 A
    import shutil
    shutil.rmtree(pA)
    panel._task_manager.refresh()
    assert str(pA) not in cfg.screenwriter_projects
    assert str(pB) in cfg.screenwriter_projects
```

- [ ] **Step 2: 跑增量测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py -q -p no:faulthandler
```

Expected: PASS (7 passed total，5 旧 + 2 新)

- [ ] **Step 3: 跑全 screenwriter 套件回归**

```bash
python -m pytest tests/test_ui/screenwriter/ -q -p no:faulthandler
```

Expected: PASS — 累计预期：
- test_base_stage_page.py: 7
- test_stream_worker.py: 4
- test_upstream_banner.py: 4
- test_ideate_page.py: 7（5 旧 + 2 新）
- test_script_page.py: 12（8 旧 + 4 新）
- test_storyboard_page.py: 9（6 旧 + 3 新）
- test_task_manager.py: 11
- test_wizard_host.py: 3
- test_screenwriter_panel.py: 7
- 其他旧测试（test_ideate_candidate_card.py / test_ideate_message_bubble.py / test_storyboard_helpers.py / test_warnings_banner.py）：~10

**总计预期 ≥74 passed**

- [ ] **Step 4: 跑全 Config 测试**

```bash
python -m pytest tests/test_config.py -q -p no:faulthandler
```

Expected: PASS (2 passed)

- [ ] **Step 5: 检查工作树状态**

```bash
git status --short
```

Expected：除 3 个原有未提交文件外，无新增未跟踪改动。

- [ ] **Step 6: Commit 验收**

```bash
git add tests/test_ui/screenwriter/test_screenwriter_panel.py
git commit -m "test(ui): 编剧任务栏化集成验收（多项目并发 + 外部删剪枝）

覆盖 spec §10 验收条目 #8（两项目同时跑 worker）+ §6.4（外部删自动剪枝）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 验收清单（与 spec §10 对照）

完成 T1-T11 后，对照 spec §10 逐条手测：

1. ✅ `tests/test_ui/screenwriter/` 全套件全绿 — Task 11 Step 3 验
2. ☐ 应用启动 → 编剧面板加载 → 左侧任务栏可见且空（首次） — 手动启动 `python -m drama_shot_master.app` 验
3. ☐ 「+ 新建」可建项目目录，列表立即刷新 — 手测
4. ☐ 「打开」可纳入外部目录 — 手测
5. ☐ 「删除」可选「仅移除」或「连目录删」 — 手测
6. ☐ 选中任务 → 右侧 wizard 切到该项目的 4 阶段 stack — 手测
7. ☐ stage stepper 可点切换任意阶段（无上游产物 → 子面板自己显示「上游缺失」banner） — 手测
8. ☐ 启动项目 A 的剧本流式生成，切到项目 B 点分镜流式生成 → 两个 worker 同时跑、两行状态点都显示 ● — 手测（需 agent 启动 + LLM 配置）
9. ☐ 切回项目 A → 剧本编辑器接管显示（buffer 已通过 _stream_label 展示，编辑器接管由 5.5 测试覆盖） — 手测
10. ☐ 项目 A 流式中点删除 → 弹三项 dialog，「连目录删」被拒绝并提示 — 手测

☐ 项目是手测项；CI 仅保证自动化部分。

---

## 与现有 wizard plan（2026-05-29-screenwriter-wizard-pages.md）的关系

| 旧 plan task | 状态 |
|---|---|
| T1 client.stream_post params | ✅ 不动 |
| T2 StreamWorker | **被本 plan T2 覆盖**（破坏性重构） |
| T3 _BaseStagePage | **被本 plan T3 覆盖**（加字段族） |
| T4 创意子控件 | ✅ 不动 |
| T5 IdeatePage | **被本 plan T5 覆盖**（caller 适配） |
| T6 ScriptPage | **被本 plan T6 覆盖**（+ upstream banner） |
| T7 分镜子控件 | ✅ 不动 |
| T8 StoryboardPage | **被本 plan T7 覆盖**（+ upstream banner） |
| T9 _ProductTree | 仍待做（独立 task #74） |
| T10 PromptsPage | 仍待做（独立 task #75）。完成后替换 `_PromptsPlaceholder` |
| T11 装配 | **被本 plan T10 完全替代** |
| T12 全套件验收 | **被本 plan T11 替代** |

T9/T10（_ProductTree + PromptsPage）独立于本 plan，可在本 plan 完成后或并行做。完成后需要在 `ScreenwriterPanel._build_ui` 里把 `_PromptsPlaceholder` 替换为 `PromptsPage(self._client)` 并加测试。
