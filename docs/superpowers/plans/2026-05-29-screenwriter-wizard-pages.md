# 编剧 Wizard 4 阶段子面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `ScreenwriterPanel` 当前 4 个 `QLabel + QPlainTextEdit + 两按钮` 的占位子面板，重做为产品级 UI：左候选+右聊天（创意）/ 上参数+下编辑器（剧本）/ 全局头+表格+warnings（分镜）/ 左产物树+右预览（提示词），接 SSE 流、支持中止、重生确认、外部编辑兼容。

**Architecture:** 新增 `drama_shot_master/ui/widgets/screenwriter/` 目录放 4 个子面板和共用 `StreamWorker(QThread)`；每个子面板自治（hold `_state/_dirty`、自检上游、自处理 LLM 流），通过 3 个公共信号（`stageAdvanceRequested`/`projectStateChanged`/`statusMessage`）和 `try_release() -> bool` 切换护栏与 ScreenwriterPanel 通信；产物落盘是唯一真相源，UI 不维护双副本。

**Tech Stack:** PySide6 (QThread/QStackedWidget/QSplitter/QPlainTextEdit/QTableView/QTreeWidget)、既有 `ScreenwriterClient.stream_post`（小改：加 `params=` query 参数）、pytest + offscreen QApplication。

参考 spec：[`docs/superpowers/specs/2026-05-29-screenwriter-wizard-pages-design.md`](../specs/2026-05-29-screenwriter-wizard-pages-design.md)。

---

## 文件清单

**新增：**
```
drama_shot_master/ui/widgets/screenwriter/
├── __init__.py                  空，包标记
├── stream_worker.py             StreamWorker(QThread) + StreamSignals
├── base_stage_page.py           _BaseStagePage(QWidget)，3 公共信号 + try_release/set_project 抽象
├── ideate_page.py               IdeatePage
├── _ideate_candidate_card.py    单候选卡片
├── _ideate_message_bubble.py    单聊天气泡
├── script_page.py               ScriptPage
├── storyboard_page.py           StoryboardPage
├── _shots_table_model.py        QAbstractTableModel
├── _character_row.py            角色单行
├── _warnings_banner.py          自适应红条
├── prompts_page.py              PromptsPage
└── _product_tree.py             QTreeWidget 包装
```

**修改：**
```
drama_shot_master/agents/screenwriter_client.py   stream_post(..., params=)
drama_shot_master/ui/panels/screenwriter_panel.py 删 wizard 占位 + 装配 4 子面板 + dirty 切换护栏
```

**测试：**
```
tests/test_ui/screenwriter/
├── __init__.py
├── test_stream_worker.py
├── test_ideate_page.py
├── test_script_page.py
├── test_storyboard_page.py
├── test_prompts_page.py
└── test_screenwriter_panel_integration.py
```

---

## Task 1: 改造 ScreenwriterClient.stream_post 接受 params

**Files:**
- Modify: `drama_shot_master/agents/screenwriter_client.py`
- Test: `tests/test_screenwriter_agent/test_client_sse.py`（追加用例）

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_screenwriter_agent/test_client_sse.py`：

```python
def test_stream_post_accepts_params(monkeypatch):
    """stream_post 接受可选 params=dict，透传到 httpx.stream() 的 params 参数。"""
    from drama_shot_master.agents.screenwriter_client import ScreenwriterClient
    captured = {}

    class _FakeResp:
        def raise_for_status(self): pass
        def iter_lines(self): return iter([])
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class _FakeClient:
        def stream(self, method, url, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["params"] = params
            return _FakeResp()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    import drama_shot_master.agents.screenwriter_client as m
    monkeypatch.setattr(m, "httpx",
                        type("X", (), {"Client": lambda *a, **kw: _FakeClient()}))
    c = ScreenwriterClient("http://localhost:18430")
    list(c.stream_post("/foo", {"bar": 1}, params={"purge_downstream": "true"}))
    assert captured["params"] == {"purge_downstream": "true"}
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_client_sse.py::test_stream_post_accepts_params -q
```

Expected: FAIL（TypeError: stream_post() got an unexpected keyword argument 'params'）

- [ ] **Step 3: 改 stream_post**

在 `drama_shot_master/agents/screenwriter_client.py` 找到现 `stream_post`（约 54-60 行），替换为：

```python
    def stream_post(self, path: str, body: dict,
                    params: dict | None = None) -> Iterator[dict]:
        """POST + SSE 流；yield {event,data} dict。
        params: 可选 query 参数（如 {"purge_downstream":"true"}）。"""
        import httpx
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{self.base_url}{path}",
                          json=body, params=params or {}) as resp:
                resp.raise_for_status()
                yield from parse_sse_lines(resp.iter_lines())
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_client_sse.py -q
```

Expected: PASS（含原有 + 1 个新增）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/agents/screenwriter_client.py tests/test_screenwriter_agent/test_client_sse.py
git commit -m "feat(screenwriter): client.stream_post 加可选 params 参数（透传 query string）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 包骨架 + StreamWorker

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/__init__.py`（空）
- Create: `drama_shot_master/ui/widgets/screenwriter/stream_worker.py`
- Create: `tests/test_ui/screenwriter/__init__.py`（空）
- Create: `tests/test_ui/screenwriter/test_stream_worker.py`

- [ ] **Step 1: 建空 __init__**

```bash
mkdir -p drama_shot_master/ui/widgets/screenwriter tests/test_ui/screenwriter
: > drama_shot_master/ui/widgets/screenwriter/__init__.py
: > tests/test_ui/screenwriter/__init__.py
```

- [ ] **Step 2: 写失败测试**

`tests/test_ui/screenwriter/test_stream_worker.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def __init__(self, events):
        self._events = events

    def stream_post(self, path, body, params=None):
        for ev in self._events:
            yield ev


def _drain(worker, timeout_ms=2000):
    """跑 worker 到 finished_ok 或 failed，期间转 QEventLoop。"""
    loop = QEventLoop()
    worker.finished_ok.connect(loop.quit)
    worker.failed.connect(lambda _: loop.quit())
    QTimer.singleShot(timeout_ms, loop.quit)
    worker.start()
    loop.exec()
    worker.wait(500)


def test_emits_events_in_order():
    _app()
    events = [
        {"event": "status", "data": {"phase": "thinking"}},
        {"event": "delta",  "data": {"text": "hi"}},
        {"event": "done",   "data": {"saved": "/x"}},
    ]
    seen = []
    w = StreamWorker(_StubClient(events), "/foo", {"a": 1})
    w.event.connect(lambda name, data: seen.append((name, data)))
    finished = []
    w.finished_ok.connect(lambda: finished.append(True))
    _drain(w)
    assert seen == [("status", {"phase": "thinking"}),
                    ("delta",  {"text": "hi"}),
                    ("done",   {"saved": "/x"})]
    assert finished == [True]


def test_failed_signal_on_exception():
    _app()
    class _Boom:
        def stream_post(self, *a, **kw):
            raise RuntimeError("boom")
            yield  # noqa: unreachable - makes it a generator if needed
    errors = []
    w = StreamWorker(_Boom(), "/foo", {})
    w.failed.connect(errors.append)
    _drain(w)
    assert errors and "boom" in errors[0]


def test_stop_interrupts_iteration():
    _app()
    # 长流：100 个 event；调 stop 后应早退（实际能不能立即退取决于迭代器；
    # 这里用一个会检查 interruption 的 stub）
    def long_gen():
        for i in range(100):
            yield {"event": "delta", "data": {"text": str(i)}}

    class _Slow:
        def stream_post(self, *a, **kw):
            yield from long_gen()

    seen = []
    w = StreamWorker(_Slow(), "/foo", {})
    w.event.connect(lambda *a: seen.append(a))
    w.start()
    # 等到 worker 跑起来一点再 stop
    QTimer.singleShot(20, w.stop)
    w.wait(2000)
    # 至少触发过 stop（有的事件可能在 stop 前已 emit）；
    # 关键：worker 已退出 isFinished()
    assert w.isFinished()
```

- [ ] **Step 3: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_stream_worker.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 4: 实现 StreamWorker**

`drama_shot_master/ui/widgets/screenwriter/stream_worker.py`:

```python
"""SSE 流式 worker：阻塞迭代器 → Qt 信号流，避免堵 UI 线程。

设计参考：spec §2。单次用完即抛——每次生成新建 StreamWorker，
不复用，避免状态污染。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class StreamWorker(QThread):
    """SSE 流式 worker。"""
    event = Signal(str, dict)       # (event_name, data_dict)
    finished_ok = Signal()          # 流自然结束
    failed = Signal(str)            # 异常（网络/解析）

    def __init__(self, client, path: str, body: dict,
                 params: dict | None = None, parent=None):
        super().__init__(parent)
        self._client = client
        self._path = path
        self._body = body
        self._params = params or {}

    def run(self):
        try:
            for ev in self._client.stream_post(self._path, self._body,
                                                params=self._params):
                if self.isInterruptionRequested():
                    return
                self.event.emit(ev.get("event", ""), ev.get("data", {}))
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))

    def stop(self):
        """主线程槽里调；线程检测到 interruption flag 后退循环。"""
        self.requestInterruption()
```

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_stream_worker.py -q -p no:faulthandler
```

Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/__init__.py drama_shot_master/ui/widgets/screenwriter/stream_worker.py tests/test_ui/screenwriter/__init__.py tests/test_ui/screenwriter/test_stream_worker.py
git commit -m "feat(ui): StreamWorker(QThread) 包装 client.stream_post

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: _BaseStagePage 抽象

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py`

> 把 3 个公共信号 + `set_project`/`try_release` 抽象出来，4 个子面板继承它，避免散落各处。

- [ ] **Step 1: 创建文件**

`drama_shot_master/ui/widgets/screenwriter/base_stage_page.py`:

```python
"""_BaseStagePage：4 个 wizard 阶段子面板的公共基类。

提供 3 个跨阶段信号 + set_project/try_release 抽象接口。
具体 UI 在子类 _build_ui 里建。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class _BaseStagePage(QWidget):
    """所有 wizard 子面板（IdeatePage/ScriptPage/...）的基类。

    子类必须实现：
      - set_project(path: Path | None) → 切项目时调；None=置占位
      - try_release() → bool；dirty 时返 False 阻断切阶段/切项目
    """
    stageAdvanceRequested = Signal(int)     # 推进到第几个阶段（0..3）
    projectStateChanged = Signal()          # 产物变化 → master 列表状态点要刷
    statusMessage = Signal(str)             # toast 到主窗状态栏

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self._project_dir: Path | None = None

    def set_project(self, path: Path | None) -> None:
        raise NotImplementedError

    def try_release(self) -> bool:
        """默认无 dirty。子类有未保存编辑时 override 返 False 可阻断切换。"""
        return True
```

- [ ] **Step 2: Commit（无新测试——纯抽象基类，由 4 个子面板的测试间接覆盖）**

```bash
git add drama_shot_master/ui/widgets/screenwriter/base_stage_page.py
git commit -m "feat(ui): _BaseStagePage 抽象基类（3 公共信号 + set_project/try_release）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: _ideate_candidate_card + _ideate_message_bubble 子控件

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/_ideate_candidate_card.py`
- Create: `drama_shot_master/ui/widgets/screenwriter/_ideate_message_bubble.py`

> 两个小 widget，无 SSE 无信号，是纯渲染组件。

- [ ] **Step 1: 创建候选卡片**

`drama_shot_master/ui/widgets/screenwriter/_ideate_candidate_card.py`:

```python
"""单个候选卡片：title + angle / summary / highlights 简略显示，点击可选定。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class _CandidateCard(QFrame):
    """候选卡片。点击 → emit clicked(id)。selected=True 时高亮边框。"""
    clicked = Signal(str)        # 候选 id

    def __init__(self, cand: dict, parent=None):
        super().__init__(parent)
        self._cid = cand.get("id", "")
        self._selected = False
        self.setObjectName("candidateCard")
        self.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4); v.setSpacing(2)

        title = QLabel(f"<b>{cand.get('title', '(无标题)')}</b>")
        title.setTextFormat(Qt.RichText)
        v.addWidget(title)

        for key, label in (("angle", "切入角度"),
                            ("summary", "摘要"),
                            ("highlights", "看点")):
            text = (cand.get(key) or "").strip()
            if text:
                lab = QLabel(f"<span style='color:#9aa0a6'>{label}：</span>{text}")
                lab.setTextFormat(Qt.RichText)
                lab.setWordWrap(True)
                v.addWidget(lab)

    def candidate_id(self) -> str:
        return self._cid

    def set_selected(self, sel: bool) -> None:
        self._selected = sel
        self.setProperty("selected", "true" if sel else "false")
        # 重新应用 QSS（属性变化触发）
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self._cid)
        super().mousePressEvent(ev)
```

- [ ] **Step 2: 创建消息气泡**

`drama_shot_master/ui/widgets/screenwriter/_ideate_message_bubble.py`:

```python
"""单条聊天气泡：role 标签 + content。流式时 append_text 追加。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class _MessageBubble(QFrame):
    """User/Assistant 消息气泡。"""

    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self._role = role
        self.setObjectName("msgBubble" + role.capitalize())
        self.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4); v.setSpacing(2)
        role_label = "你" if role == "user" else ("AI" if role == "assistant" else role)
        head = QLabel(f"<span style='color:#9aa0a6; font-size:9pt'>{role_label}</span>")
        head.setTextFormat(Qt.RichText)
        v.addWidget(head)
        self._body = QLabel(content)
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self._body)

    def append_text(self, chunk: str) -> None:
        """流式 delta 追加内容。"""
        self._body.setText(self._body.text() + chunk)

    def mark_aborted(self) -> None:
        self._body.setText(self._body.text() +
                            "  <span style='color:#9aa0a6'>(已中止)</span>")
        self._body.setTextFormat(Qt.RichText)
```

- [ ] **Step 3: Commit（这两个由 ideate_page 测试间接覆盖）**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_ideate_candidate_card.py drama_shot_master/ui/widgets/screenwriter/_ideate_message_bubble.py
git commit -m "feat(ui): _CandidateCard + _MessageBubble 创意子控件

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: IdeatePage

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/ideate_page.py`
- Test: `tests/test_ui/screenwriter/test_ideate_page.py`

> 左候选 + 右聊天；ContextForm 首次显、发完隐藏；候选本地选中再[选定·推进]。

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_ideate_page.py`:

```python
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def __init__(self):
        self.select_calls = []
    def ideate_select(self, project_dir, selected_id):
        self.select_calls.append((Path(project_dir), selected_id))
        return {"saved": str(Path(project_dir) / "idea.json"),
                "selected": {"id": selected_id}}


def test_set_project_none_shows_placeholder():
    _app()
    p = IdeatePage(_StubClient())
    p.set_project(None)
    # 占位状态：send button 禁用
    assert p._send_btn.isEnabled() is False


def test_loads_idea_json_renders_candidates(tmp_path):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [
            {"role": "user", "content": "出 2 个候选"},
            {"role": "assistant", "content": "候选 1..."},
        ],
        "candidates": [
            {"id": "c1", "title": "躺平农夫"},
            {"id": "c2", "title": "仙界 BUG"},
        ],
        "selected_id": "",
    }), encoding="utf-8")
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    # 2 张候选卡片渲染
    assert len(p._candidate_cards) == 2
    assert p._candidate_cards[0].candidate_id() == "c1"
    # 2 条消息气泡
    assert len(p._message_bubbles) == 2


def test_click_card_marks_local_only_not_calls_client(tmp_path):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [],
        "candidates": [{"id": "c1", "title": "t1"},
                       {"id": "c2", "title": "t2"}],
        "selected_id": "",
    }), encoding="utf-8")
    client = _StubClient()
    p = IdeatePage(client)
    p.set_project(tmp_path)
    p._on_card_clicked("c2")
    assert p._selected_id == "c2"
    assert client.select_calls == []   # 不立即调
    # 按钮文本变
    assert "c2" in p._select_btn.text() or "推进" in p._select_btn.text()


def test_select_button_persists_and_emits_advance(tmp_path):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [],
        "candidates": [{"id": "c1", "title": "t1"}],
        "selected_id": "",
    }), encoding="utf-8")
    client = _StubClient()
    p = IdeatePage(client)
    p.set_project(tmp_path)
    p._on_card_clicked("c1")
    emitted = []
    p.stageAdvanceRequested.connect(emitted.append)
    p._on_select_clicked()
    assert client.select_calls == [(tmp_path, "c1")]
    assert emitted == [1]    # 推进到第 1 个阶段（剧本）


def test_clear_chat_resets_messages_and_candidates(tmp_path, monkeypatch):
    _app()
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [{"role": "user", "content": "x"}],
        "candidates": [{"id": "c1", "title": "t1"}],
        "selected_id": "c1",
    }), encoding="utf-8")
    p = IdeatePage(_StubClient())
    p.set_project(tmp_path)
    # monkeypatch confirm dialog → 自动 Yes
    import drama_shot_master.ui.widgets.screenwriter.ideate_page as m
    monkeypatch.setattr(m.QMessageBox, "question",
                         staticmethod(lambda *a, **kw: m.QMessageBox.Yes))
    p._on_clear_chat_clicked()
    assert p._messages == []
    assert p._candidates == []
    assert p._selected_id == ""
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_ideate_page.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 IdeatePage**

`drama_shot_master/ui/widgets/screenwriter/ideate_page.py`:

```python
"""IdeatePage：创意阶段子面板。

左 _CandidatesPanel + 右 _ChatPanel；首次对话前显 ContextForm，发完隐藏。
候选卡片本地点选 → 按钮[选定·推进 →] → ideate_select + emit stageAdvanceRequested(1)。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QScrollArea, QSplitter, QLineEdit, QSpinBox, QFormLayout, QMessageBox,
    QFrame,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._ideate_candidate_card import _CandidateCard
from drama_shot_master.ui.widgets.screenwriter._ideate_message_bubble import _MessageBubble
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker


class IdeatePage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._messages: list[dict] = []
        self._candidates: list[dict] = []
        self._selected_id: str = ""
        self._context: dict = {}
        self._candidate_cards: list[_CandidateCard] = []
        self._message_bubbles: list[_MessageBubble] = []
        self._current_assistant_bubble: _MessageBubble | None = None
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_candidates_panel())
        splitter.addWidget(self._build_chat_panel())
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 500])
        root.addWidget(splitter)

    def _build_candidates_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(260)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self._candidates_label = QLabel("候选 (0)")
        v.addWidget(self._candidates_label)
        # 滚动卡片容器
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); self._candidates_layout = QVBoxLayout(inner)
        self._candidates_layout.setContentsMargins(2, 2, 2, 2)
        self._candidates_layout.setSpacing(4)
        self._candidates_layout.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        # 选定推进按钮
        self._select_btn = QPushButton("（先点一张候选）")
        self._select_btn.setEnabled(False)
        self._select_btn.clicked.connect(self._on_select_clicked)
        v.addWidget(self._select_btn)
        return w

    def _build_chat_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        # 顶 [清空对话]
        top = QHBoxLayout()
        top.addStretch(1)
        self._clear_btn = QPushButton("清空对话")
        self._clear_btn.clicked.connect(self._on_clear_chat_clicked)
        top.addWidget(self._clear_btn)
        v.addLayout(top)
        # 首轮 context form
        self._context_form = self._build_context_form()
        v.addWidget(self._context_form)
        # 聊天历史滚动
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); self._messages_layout = QVBoxLayout(inner)
        self._messages_layout.setContentsMargins(2, 2, 2, 2)
        self._messages_layout.setSpacing(4)
        self._messages_layout.addStretch(1)
        scroll.setWidget(inner)
        self._messages_scroll = scroll
        v.addWidget(scroll, 1)
        # 输入行
        input_row = QHBoxLayout()
        self._input = QPlainTextEdit(); self._input.setMaximumHeight(80)
        self._input.setPlaceholderText("输入追问…（已生成候选后用）")
        self._send_btn = QPushButton("发送")
        self._send_btn.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(self._send_btn)
        v.addLayout(input_row)
        return w

    def _build_context_form(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.StyledPanel)
        form = QFormLayout(f)
        form.setContentsMargins(6, 6, 6, 6)
        self._ctx_core_idea = QLineEdit()
        self._ctx_core_idea.setPlaceholderText("一句话主旨，如：守株待兔")
        self._ctx_genre = QLineEdit()
        self._ctx_genre.setPlaceholderText("题材标签，逗号分隔：古风, 寓言")
        self._ctx_duration = QSpinBox(); self._ctx_duration.setRange(15, 600)
        self._ctx_duration.setValue(60)
        self._ctx_visual = QLineEdit()
        self._ctx_visual.setPlaceholderText("视觉风格，如：水墨")
        self._ctx_extra = QLineEdit()
        self._ctx_extra.setPlaceholderText("额外约束（可空）")
        form.addRow("主旨", self._ctx_core_idea)
        form.addRow("题材", self._ctx_genre)
        form.addRow("时长(s)", self._ctx_duration)
        form.addRow("视觉风格", self._ctx_visual)
        form.addRow("额外约束", self._ctx_extra)
        self._gen_first_btn = QPushButton("生成 3 个候选")
        self._gen_first_btn.clicked.connect(self._on_first_gen_clicked)
        form.addRow("", self._gen_first_btn)
        return f

    # —— set_project / try_release ————

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        self._project_dir = path
        # 状态重置
        self._messages = []
        self._candidates = []
        self._selected_id = ""
        self._context = {}
        self._render_candidates()
        self._render_messages()
        if path is None:
            self._context_form.hide()
            self._send_btn.setEnabled(False)
            self._gen_first_btn.setEnabled(False)
            return
        self._send_btn.setEnabled(True)
        self._gen_first_btn.setEnabled(True)
        idea_path = path / "idea.json"
        if idea_path.is_file():
            try:
                idea = json.loads(idea_path.read_text(encoding="utf-8"))
                self._messages = list(idea.get("messages", []))
                self._candidates = list(idea.get("candidates", []))
                self._selected_id = idea.get("selected_id", "")
                self._context = dict(idea.get("input", {}))
            except Exception:
                pass
        self._render_candidates()
        self._render_messages()
        # context form 显示规则：从未对话过才显
        self._context_form.setVisible(not self._messages)

    def try_release(self) -> bool:
        # 创意阶段无 dirty 概念（每条 user 发都立刻产 idea.json）；总返 True
        return True

    # —— 渲染 ——

    def _render_candidates(self):
        # 清空旧卡
        for c in self._candidate_cards:
            c.deleteLater()
        self._candidate_cards = []
        # 加新卡（在 stretch 之前插）
        for cand in self._candidates:
            card = _CandidateCard(cand)
            card.clicked.connect(self._on_card_clicked)
            card.set_selected(cand.get("id") == self._selected_id)
            self._candidates_layout.insertWidget(
                self._candidates_layout.count() - 1, card)
            self._candidate_cards.append(card)
        self._candidates_label.setText(f"候选 ({len(self._candidates)})")
        # 按钮文本与可用性
        if self._selected_id:
            self._select_btn.setText(f"选定 {self._selected_id} · 推进 →")
            self._select_btn.setEnabled(True)
        else:
            self._select_btn.setText("（先点一张候选）")
            self._select_btn.setEnabled(False)

    def _render_messages(self):
        for b in self._message_bubbles:
            b.deleteLater()
        self._message_bubbles = []
        for m in self._messages:
            bub = _MessageBubble(m.get("role", "user"), m.get("content", ""))
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, bub)
            self._message_bubbles.append(bub)
        self._current_assistant_bubble = None

    # —— 用户交互 ——

    def _collect_context(self) -> dict:
        return {
            "core_idea": self._ctx_core_idea.text().strip(),
            "genre_tags": [t.strip() for t in
                           self._ctx_genre.text().split(",") if t.strip()],
            "format": "短剧",
            "tone_tags": [],
            "visual_style": self._ctx_visual.text().strip(),
            "candidate_count": 3,
            "duration_sec": int(self._ctx_duration.value()),
            "extra_constraints": self._ctx_extra.text().strip(),
        }

    def _on_first_gen_clicked(self):
        if self._project_dir is None:
            return
        self._context = self._collect_context()
        self._context_form.hide()
        self._send_user_text("生成候选（按上面 context）")

    def _on_send_clicked(self):
        text = self._input.toPlainText().strip()
        if not text or self._project_dir is None:
            return
        self._input.clear()
        self._send_user_text(text)

    def _send_user_text(self, text: str):
        # 追加 user message
        self._messages.append({"role": "user", "content": text})
        ub = _MessageBubble("user", text)
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, ub)
        self._message_bubbles.append(ub)
        # 起 assistant 流
        self._current_assistant_bubble = _MessageBubble("assistant", "")
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, self._current_assistant_bubble)
        self._message_bubbles.append(self._current_assistant_bubble)

        body = {
            "project_dir": str(self._project_dir),
            "context": self._context,
            "messages": list(self._messages),
            "auto_save_idea_json": True,
        }
        self._start_stream("/ideate/chat", body)

    def _on_card_clicked(self, cid: str):
        self._selected_id = cid
        for c in self._candidate_cards:
            c.set_selected(c.candidate_id() == cid)
        self._select_btn.setText(f"选定 {cid} · 推进 →")
        self._select_btn.setEnabled(True)

    def _on_select_clicked(self):
        if not self._selected_id or self._project_dir is None:
            return
        try:
            self._client.ideate_select(self._project_dir, self._selected_id)
        except Exception as e:
            QMessageBox.warning(self, "选定失败", str(e))
            return
        self.projectStateChanged.emit()
        self.stageAdvanceRequested.emit(1)

    def _on_clear_chat_clicked(self):
        if QMessageBox.question(
                self, "清空对话",
                "会清空对话历史和当前候选（不删除项目目录），继续？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._messages = []
        self._candidates = []
        self._selected_id = ""
        self._render_candidates()
        self._render_messages()
        self._context_form.show()

    # —— SSE 流 ——

    def _start_stream(self, path, body, params=None):
        self._state = "streaming"
        self._send_btn.setText("▣ 中止")
        self._send_btn.clicked.disconnect()
        self._send_btn.clicked.connect(self._stop_stream)
        self._worker = StreamWorker(self._client, path, body, params, parent=self)
        self._worker.event.connect(self._on_sse_event)
        self._worker.finished_ok.connect(self._on_stream_done)
        self._worker.failed.connect(self._on_stream_failed)
        self._worker.start()

    def _stop_stream(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._state = "idle"
        if self._current_assistant_bubble is not None:
            self._current_assistant_bubble.mark_aborted()
            self._current_assistant_bubble = None
        self._reset_send_button()

    def _on_sse_event(self, event_name: str, data: dict):
        if event_name == "delta":
            text = data.get("text", "")
            if text and self._current_assistant_bubble is not None:
                self._current_assistant_bubble.append_text(text)

    def _on_stream_done(self):
        self._state = "idle"
        self._reset_send_button()
        # 重读 idea.json（Agent 已落盘 + 解析候选）
        if self._project_dir is None:
            return
        idea_path = self._project_dir / "idea.json"
        if idea_path.is_file():
            try:
                idea = json.loads(idea_path.read_text(encoding="utf-8"))
                self._messages = list(idea.get("messages", []))
                self._candidates = list(idea.get("candidates", []))
                # 保留本地 selected_id 优先（用户在流式期间点过的）
                if not self._selected_id:
                    self._selected_id = idea.get("selected_id", "")
                self._render_candidates()
                self._render_messages()
                self.projectStateChanged.emit()
            except Exception:
                pass

    def _on_stream_failed(self, msg: str):
        self._state = "idle"
        self._reset_send_button()
        if self._current_assistant_bubble is not None:
            self._current_assistant_bubble.mark_aborted()
            self._current_assistant_bubble = None
        QMessageBox.warning(self, "生成失败",
                             f"创意阶段生成失败：{msg}\n请检查网络或 LLM 配置。")

    def _reset_send_button(self):
        self._send_btn.setText("发送")
        try:
            self._send_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._send_btn.clicked.connect(self._on_send_clicked)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_ideate_page.py -q -p no:faulthandler
```

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/ideate_page.py tests/test_ui/screenwriter/test_ideate_page.py
git commit -m "feat(ui): IdeatePage 创意阶段子面板（左候选 + 右聊天 + ContextForm）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: ScriptPage

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/script_page.py`
- Test: `tests/test_ui/screenwriter/test_script_page.py`

> 顶参数 + 中 QPlainTextEdit + 底操作；状态机 idle/streaming/done；重生确认 + purge_downstream；dirty 切换护栏。

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_script_page.py`:

```python
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def test_set_project_none_disables_buttons():
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False
    assert p._save_btn.isEnabled() is False
    assert p._advance_btn.isEnabled() is False


def test_loads_existing_script_md(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("# 剧本信息\n标题: 测试\n## 镜头 01\n画面: x\n",
                                       encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert "镜头 01" in p._editor.toPlainText()
    assert p._state == "done"
    assert p._advance_btn.isEnabled() is True


def test_idle_when_no_script(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._state == "idle"
    assert p._editor.toPlainText() == ""
    assert p._advance_btn.isEnabled() is False


def test_edit_then_save_button_enables(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("orig\n", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._save_btn.isEnabled() is False
    p._editor.setPlainText("edited\n")
    assert p._save_btn.isEnabled() is True


def test_save_writes_disk_and_clears_dirty(tmp_path):
    _app()
    (tmp_path / "剧本.md").write_text("orig\n", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._editor.setPlainText("edited content\n")
    p._on_save_clicked()
    assert (tmp_path / "剧本.md").read_text(encoding="utf-8") == "edited content\n"
    assert p._save_btn.isEnabled() is False


def test_try_release_blocks_when_dirty(tmp_path, monkeypatch):
    _app()
    (tmp_path / "剧本.md").write_text("orig\n", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._editor.setPlainText("edited\n")
    import drama_shot_master.ui.widgets.screenwriter.script_page as m
    monkeypatch.setattr(m.QMessageBox, "question",
                         staticmethod(lambda *a, **k: m.QMessageBox.Cancel))
    assert p.try_release() is False
    # 用户选 Discard：放行
    monkeypatch.setattr(m.QMessageBox, "question",
                         staticmethod(lambda *a, **k: m.QMessageBox.Discard))
    assert p.try_release() is True


def test_upstream_check_blocks_generate(tmp_path, monkeypatch):
    _app()
    # 没有 idea.json → 点生成应该弹 warning 而不发流
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    import drama_shot_master.ui.widgets.screenwriter.script_page as m
    called = []
    monkeypatch.setattr(m.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: called.append(True)))
    p._on_generate_clicked()
    assert called
    assert p._state == "idle"   # 没启流
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 ScriptPage**

`drama_shot_master/ui/widgets/screenwriter/script_page.py`:

```python
"""ScriptPage：剧本阶段子面板。

顶 _ParamBar + 中 QPlainTextEdit + 底 _ActionBar。
状态机 idle/streaming/done；磁盘是真相源；外部 mtime 检测；
重生确认 + purge_downstream；切阶段时 dirty 拦截。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QSpinBox,
    QComboBox, QMessageBox,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from screenwriter_agent.core.atomic_write import atomic_write_text


class ScriptPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._script_path: Path | None = None
        self._original_text: str = ""
        self._last_load_mtime: float = 0.0
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.addLayout(self._build_param_bar())
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("剧本.md 内容（生成或加载后显示在此）")
        self._editor.textChanged.connect(self._on_editor_changed)
        root.addWidget(self._editor, 1)
        root.addLayout(self._build_action_bar())

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("时长(s):"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(15, 600); self._duration_spin.setValue(60)
        bar.addWidget(self._duration_spin)
        bar.addWidget(QLabel("fps:"))
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(12, 60); self._fps_spin.setValue(24)
        bar.addWidget(self._fps_spin)
        bar.addWidget(QLabel("语言风格:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["口语化", "书面语", "古风"])
        bar.addWidget(self._lang_combo)
        bar.addStretch(1)
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        self._gen_btn = QPushButton("生成剧本")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止")
        self._stop_btn.clicked.connect(self._stop_stream)
        self._stop_btn.hide()
        bar.addWidget(self._stop_btn)
        return bar

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存修改")
        self._save_btn.clicked.connect(self._on_save_clicked)
        self._save_btn.setEnabled(False)
        bar.addWidget(self._save_btn)
        self._open_btn = QPushButton("📂 打开文件")
        self._open_btn.clicked.connect(self._on_open_file_clicked)
        bar.addWidget(self._open_btn)
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进到分镜 →")
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        self._advance_btn.setEnabled(False)
        bar.addWidget(self._advance_btn)
        return bar

    # —— set_project / try_release ——

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        self._project_dir = path
        if path is None:
            self._script_path = None
            self._editor.blockSignals(True)
            self._editor.clear()
            self._editor.blockSignals(False)
            self._original_text = ""
            self._state = "idle"
            for b in (self._gen_btn, self._save_btn, self._open_btn,
                       self._advance_btn):
                b.setEnabled(False)
            return
        self._script_path = path / "剧本.md"
        self._load_from_disk()
        self._gen_btn.setEnabled(True)
        self._open_btn.setEnabled(True)

    def _load_from_disk(self):
        text = ""
        if self._script_path is not None and self._script_path.is_file():
            try:
                text = self._script_path.read_text(encoding="utf-8")
                self._last_load_mtime = self._script_path.stat().st_mtime
            except OSError:
                text = ""
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self._original_text = text
        self._state = "done" if text else "idle"
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(self._state == "done")

    def try_release(self) -> bool:
        if not self._is_dirty():
            return True
        ans = QMessageBox.question(
            self, "剧本有未保存改动",
            "切换前是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            self._on_save_clicked()
            return True
        if ans == QMessageBox.Discard:
            self._editor.blockSignals(True)
            self._editor.setPlainText(self._original_text)
            self._editor.blockSignals(False)
            self._save_btn.setEnabled(False)
            return True
        return False    # Cancel

    def _is_dirty(self) -> bool:
        return self._editor.toPlainText() != self._original_text

    # —— 用户交互 ——

    def _on_editor_changed(self):
        self._save_btn.setEnabled(self._is_dirty())

    def _on_save_clicked(self):
        if self._script_path is None:
            return
        try:
            atomic_write_text(self._script_path, self._editor.toPlainText())
            self._original_text = self._editor.toPlainText()
            self._last_load_mtime = self._script_path.stat().st_mtime
            self._save_btn.setEnabled(False)
            self._state = "done"
            self._advance_btn.setEnabled(True)
            self.projectStateChanged.emit()
            self.statusMessage.emit("剧本.md 已保存")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_open_file_clicked(self):
        if self._script_path and self._script_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._script_path)))

    def _on_advance_clicked(self):
        if self._is_dirty() and not self.try_release():
            return
        self.stageAdvanceRequested.emit(2)

    def _on_generate_clicked(self):
        if self._project_dir is None:
            return
        # 上游检查
        idea_path = self._project_dir / "idea.json"
        if not idea_path.is_file():
            QMessageBox.warning(self, "上游缺失",
                                  "请先在「创意」阶段生成候选并选定一个。")
            return
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
        except Exception:
            QMessageBox.warning(self, "上游损坏", "idea.json 解析失败。")
            return
        if not idea.get("selected_id"):
            QMessageBox.warning(self, "未选定候选",
                                  "请先在「创意」阶段选定一个候选。")
            return
        # 重生确认
        params = None
        if self._state == "done":
            ans = QMessageBox.question(
                self, "重新生成",
                "重新生成会覆盖剧本.md，并删除下游 分镜.json + prompts/。继续？",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            params = {"purge_downstream": "true"}
        # 启流
        body = {
            "project_dir": str(self._project_dir),
            "options": {
                "length_preset": "完整版",
                "language_style": self._lang_combo.currentText(),
                "fps": self._fps_spin.value(),
                "duration_sec": self._duration_spin.value(),
            },
        }
        self._editor.blockSignals(True)
        self._editor.clear()
        self._editor.blockSignals(False)
        self._start_stream("/script", body, params)

    # —— SSE 流 ——

    def _start_stream(self, path, body, params=None):
        self._state = "streaming"
        self._gen_btn.hide(); self._stop_btn.show()
        self._stream_label.setText("● 流式 · 已 0 字")
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(False)
        self._worker = StreamWorker(self._client, path, body, params, parent=self)
        self._worker.event.connect(self._on_sse_event)
        self._worker.finished_ok.connect(self._on_stream_done)
        self._worker.failed.connect(self._on_stream_failed)
        self._worker.start()

    def _stop_stream(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._reset_stream_ui("idle")

    def _on_sse_event(self, event_name: str, data: dict):
        if event_name == "delta":
            text = data.get("text", "")
            if text:
                # 追加到编辑器末尾
                self._editor.blockSignals(True)
                self._editor.moveCursor(self._editor.textCursor().End)
                self._editor.insertPlainText(text)
                self._editor.blockSignals(False)
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._editor.toPlainText())} 字")

    def _on_stream_done(self):
        # 重读磁盘
        self._load_from_disk()
        self._reset_stream_ui("done")
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str):
        self._reset_stream_ui("idle")
        QMessageBox.warning(self, "生成失败",
                             f"剧本生成失败：{msg}\n请检查网络或 LLM 配置。")

    def _reset_stream_ui(self, state: str):
        self._state = state
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")
        self._save_btn.setEnabled(self._is_dirty())
        self._advance_btn.setEnabled(state == "done" and not self._is_dirty())
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -p no:faulthandler
```

Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py tests/test_ui/screenwriter/test_script_page.py
git commit -m "feat(ui): ScriptPage 剧本阶段子面板（参数+编辑器+SSE 流+dirty 拦截）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: _ShotsTableModel + _CharacterRow + _WarningsBanner 子控件

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/_shots_table_model.py`
- Create: `drama_shot_master/ui/widgets/screenwriter/_character_row.py`
- Create: `drama_shot_master/ui/widgets/screenwriter/_warnings_banner.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_storyboard_helpers.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._shots_table_model import _ShotsTableModel


def _app():
    return QApplication.instance() or QApplication([])


def test_table_model_basic_dimensions():
    _app()
    shots = [
        {"shotId": "S01", "duration": 6, "composition": "中景",
         "description": "雨夜", "stylePrompt": "古风水墨，雨夜松林"},
        {"shotId": "S02", "duration": 5, "composition": "近景",
         "description": "书生", "stylePrompt": "古风水墨，书生撑伞"},
    ]
    m = _ShotsTableModel()
    m.set_shots(shots)
    assert m.rowCount() == 2
    assert m.columnCount() == 5


def test_table_model_set_data_writes_back_and_emits():
    _app()
    shots = [{"shotId": "S01", "duration": 6, "composition": "中景",
              "description": "雨夜", "stylePrompt": "古风水墨"}]
    m = _ShotsTableModel()
    m.set_shots(shots)
    changes = []
    m.dataChanged.connect(lambda *a: changes.append(True))
    idx = m.index(0, 3)   # description 列
    ok = m.setData(idx, "改后描述", Qt.EditRole)
    assert ok
    assert shots[0]["description"] == "改后描述"
    assert changes
```

`tests/test_ui/screenwriter/test_warnings_banner.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._warnings_banner import _WarningsBanner


def _app():
    return QApplication.instance() or QApplication([])


def test_banner_hidden_when_no_warnings():
    _app()
    b = _WarningsBanner()
    b.set_warnings([])
    assert b.isVisible() is False


def test_banner_emits_path_on_click():
    _app()
    b = _WarningsBanner()
    b.set_warnings([
        {"path": "shots[1].stylePrompt", "issue": "过短", "severity": "warning"},
    ])
    got = []
    b.warningClicked.connect(got.append)
    # 模拟点击：直接 emit 内部（测试 helper）
    b._emit_click("shots[1].stylePrompt")
    assert got == ["shots[1].stylePrompt"]
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_storyboard_helpers.py tests/test_ui/screenwriter/test_warnings_banner.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 _ShotsTableModel**

`drama_shot_master/ui/widgets/screenwriter/_shots_table_model.py`:

```python
"""分镜 shots 列表的 QAbstractTableModel 包装。

列：ID | 时长(s) | 构图 | 描述 | stylePrompt。
setData 直接改 self._shots[i][key]——shots 是 storyboard_page._sb["shots"] 的引用，
所以外层 _sb 同步更新。"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


_COLS = (
    ("shotId",      "ID"),
    ("duration",    "时长(s)"),
    ("composition", "构图"),
    ("description", "描述"),
    ("stylePrompt", "stylePrompt"),
)


class _ShotsTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shots: list[dict] = []

    def set_shots(self, shots: list[dict]) -> None:
        self.beginResetModel()
        self._shots = shots
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._shots)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(_COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return _COLS[section][1] if 0 <= section < len(_COLS) else None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        key, _ = _COLS[index.column()]
        return str(self._shots[index.row()].get(key, ""))

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        key, _ = _COLS[index.column()]
        # duration 是数字
        if key == "duration":
            try:
                value = float(value)
            except (ValueError, TypeError):
                return False
        self._shots[index.row()][key] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True
```

- [ ] **Step 4: 实现 _CharacterRow**

`drama_shot_master/ui/widgets/screenwriter/_character_row.py`:

```python
"""单行角色：name QLineEdit + appearance QLineEdit + [×]。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton


class _CharacterRow(QWidget):
    changed = Signal()       # 任何字段改动
    removeClicked = Signal(int)   # 自己被点删除

    def __init__(self, idx: int, name: str = "", appearance: str = "", parent=None):
        super().__init__(parent)
        self._idx = idx
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("角色名")
        self.name_edit.setMaximumWidth(120)
        self.name_edit.textChanged.connect(self.changed)
        h.addWidget(self.name_edit)
        self.appearance_edit = QLineEdit(appearance)
        self.appearance_edit.setPlaceholderText("外貌（≥10 字）")
        self.appearance_edit.textChanged.connect(self.changed)
        h.addWidget(self.appearance_edit, 1)
        btn_del = QPushButton("×")
        btn_del.setMaximumWidth(28)
        btn_del.clicked.connect(lambda: self.removeClicked.emit(self._idx))
        h.addWidget(btn_del)

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.appearance_edit.text().strip()
```

- [ ] **Step 5: 实现 _WarningsBanner**

`drama_shot_master/ui/widgets/screenwriter/_warnings_banner.py`:

```python
"""自适应高度的 warnings 红条。点击单条 → emit warningClicked(path)。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel


_SEV_COLOR = {
    "info":     "#9aa0a6",
    "warning":  "#ffaa00",
    "error":    "#ff5c5c",
    "critical": "#ff3a3a",
}


class _WarningsBanner(QFrame):
    warningClicked = Signal(str)        # path 字段

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4); self._layout.setSpacing(2)
        self._items: list[QLabel] = []
        self.hide()

    def set_warnings(self, warns: list[dict]) -> None:
        # 清空
        for lab in self._items:
            lab.deleteLater()
        self._items = []
        if not warns:
            self.hide()
            return
        self.show()
        for w in warns[:10]:
            sev = w.get("severity", "warning")
            color = _SEV_COLOR.get(sev, "#9aa0a6")
            path = w.get("path", "")
            issue = w.get("issue", "")
            lab = QLabel(
                f"<a href='{path}' style='color:{color}; text-decoration:none'>"
                f"⚠ {path}</a> · <span style='color:#9aa0a6'>{issue}</span>")
            lab.setTextFormat(Qt.RichText)
            lab.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
            lab.linkActivated.connect(self._emit_click)
            self._layout.addWidget(lab)
            self._items.append(lab)

    def _emit_click(self, path: str):
        self.warningClicked.emit(path)
```

- [ ] **Step 6: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_storyboard_helpers.py tests/test_ui/screenwriter/test_warnings_banner.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_shots_table_model.py drama_shot_master/ui/widgets/screenwriter/_character_row.py drama_shot_master/ui/widgets/screenwriter/_warnings_banner.py tests/test_ui/screenwriter/test_storyboard_helpers.py tests/test_ui/screenwriter/test_warnings_banner.py
git commit -m "feat(ui): 分镜阶段子控件（_ShotsTableModel/_CharacterRow/_WarningsBanner）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: StoryboardPage

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/storyboard_page.py`
- Test: `tests/test_ui/screenwriter/test_storyboard_page.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_storyboard_page.py`:

```python
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.storyboard_page import StoryboardPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _sb_fixture():
    return {
        "title": "测试分镜",
        "aspectRatio": "9:16",
        "fps": 24,
        "totalDuration": 12,
        "globalStyle": "古风水墨",
        "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾披肩长发"}],
        "shots": [
            {"shotId": "S01", "description": "雨夜画面", "duration": 6,
             "composition": "中景",
             "stylePrompt": "古风水墨，雨夜松林，整体调性沉静"},
            {"shotId": "S02", "description": "书生撑伞", "duration": 6,
             "composition": "近景",
             "stylePrompt": "古风水墨，雨夜书生撑伞踱步"},
        ],
    }


def test_set_project_none_disables():
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_load_existing_storyboard_json(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._state == "done"
    assert p._shots_model.rowCount() == 2
    assert p._title_edit.text() == "测试分镜"
    assert p._global_style_edit.toPlainText() == "古风水墨"
    assert len(p._character_rows) == 1


def test_table_edit_marks_dirty(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._save_btn.isEnabled() is False
    p._shots_model.setData(p._shots_model.index(0, 3),
                            "改后画面",
                            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.EditRole)
    assert p._save_btn.isEnabled() is True


def test_save_writes_valid_json(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(
        json.dumps(_sb_fixture(), ensure_ascii=False), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    p._title_edit.setText("新标题")
    p._on_save_clicked()
    on_disk = json.loads((tmp_path / "分镜.json").read_text(encoding="utf-8"))
    assert on_disk["title"] == "新标题"
    assert p._save_btn.isEnabled() is False


def test_warnings_rendered_when_done_event_has_them(tmp_path):
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    # 模拟 done 事件携带 warnings
    p._on_sse_event("done", {
        "saved": str(tmp_path / "分镜.json"),
        "result": _sb_fixture(),
        "warnings": [
            {"path": "shots[1].stylePrompt", "issue": "过短",
             "severity": "warning"},
        ],
    })
    assert p._warnings_banner.isVisible()


def test_upstream_check_blocks_generate(tmp_path, monkeypatch):
    _app()
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)   # 没有 剧本.md
    import drama_shot_master.ui.widgets.screenwriter.storyboard_page as m
    called = []
    monkeypatch.setattr(m.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: called.append(True)))
    p._on_generate_clicked()
    assert called
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_storyboard_page.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 StoryboardPage**

`drama_shot_master/ui/widgets/screenwriter/storyboard_page.py`:

```python
"""StoryboardPage：分镜阶段子面板。

顶 _ParamBar + 全局头（标题/比例/时长/globalStyle/characters）+ 中表格 + 底 _WarningsBanner + ActionBar。
流式期间不解析、只显字数；done 时一次性解析 + 渲染表格。
重生确认 + purge_downstream；dirty 切换护栏。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QSpinBox,
    QComboBox, QPlainTextEdit, QMessageBox, QFrame, QTableView, QDoubleSpinBox,
    QDialog, QDialogButtonBox, QHeaderView,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._shots_table_model import _ShotsTableModel
from drama_shot_master.ui.widgets.screenwriter._character_row import _CharacterRow
from drama_shot_master.ui.widgets.screenwriter._warnings_banner import _WarningsBanner
from screenwriter_agent.core.atomic_write import atomic_write_text


class StoryboardPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._sb_path: Path | None = None
        self._sb: dict | None = None
        self._original_sb_json: str = ""
        self._last_load_mtime: float = 0.0
        self._warnings: list[dict] = []
        self._dirty: bool = False
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._buf: str = ""
        self._character_rows: list[_CharacterRow] = []
        self._shots_model = _ShotsTableModel()
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        root.addWidget(self._build_global_header())
        self._table = QTableView()
        self._table.setModel(self._shots_model)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)
        self._shots_model.dataChanged.connect(lambda *a: self._mark_dirty())
        root.addWidget(self._table, 1)
        self._warnings_banner = _WarningsBanner()
        self._warnings_banner.warningClicked.connect(self._on_warning_clicked)
        root.addWidget(self._warnings_banner)
        root.addLayout(self._build_action_bar())

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("比例:"))
        self._aspect_combo = QComboBox()
        self._aspect_combo.addItems(["9:16", "16:9", "1:1"])
        bar.addWidget(self._aspect_combo)
        bar.addWidget(QLabel("fps:"))
        self._fps_spin = QSpinBox(); self._fps_spin.setRange(12, 60)
        self._fps_spin.setValue(24)
        bar.addWidget(self._fps_spin)
        bar.addWidget(QLabel("默认时长:"))
        self._default_dur_spin = QDoubleSpinBox()
        self._default_dur_spin.setRange(0.5, 30.0); self._default_dur_spin.setValue(3.0)
        bar.addWidget(self._default_dur_spin)
        bar.addWidget(QLabel("密度:"))
        self._density_combo = QComboBox()
        self._density_combo.addItems(["稀疏", "常规", "紧凑"])
        self._density_combo.setCurrentText("常规")
        bar.addWidget(self._density_combo)
        bar.addStretch(1)
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        self._gen_btn = QPushButton("生成分镜")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止"); self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        return bar

    def _build_global_header(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(f)
        v.setContentsMargins(6, 4, 6, 4); v.setSpacing(4)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("标题:"))
        self._title_edit = QLineEdit()
        self._title_edit.textChanged.connect(lambda _: self._mark_dirty())
        row1.addWidget(self._title_edit, 1)
        row1.addWidget(QLabel("时长(s):"))
        self._total_duration_label = QLabel("0")
        row1.addWidget(self._total_duration_label)
        v.addLayout(row1)
        v.addWidget(QLabel("globalStyle:"))
        self._global_style_edit = QPlainTextEdit()
        self._global_style_edit.setMaximumHeight(50)
        self._global_style_edit.textChanged.connect(self._mark_dirty)
        v.addWidget(self._global_style_edit)
        # 角色区
        char_top = QHBoxLayout()
        char_top.addWidget(QLabel("角色:"))
        char_top.addStretch(1)
        btn_add = QPushButton("+ 加角色")
        btn_add.clicked.connect(self._on_add_character)
        char_top.addWidget(btn_add)
        v.addLayout(char_top)
        self._characters_layout = QVBoxLayout()
        v.addLayout(self._characters_layout)
        return f

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存修改")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_clicked)
        bar.addWidget(self._save_btn)
        self._view_json_btn = QPushButton("{ } 看原始 JSON")
        self._view_json_btn.clicked.connect(self._on_view_json_clicked)
        bar.addWidget(self._view_json_btn)
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进到提示词 →")
        self._advance_btn.setEnabled(False)
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        bar.addWidget(self._advance_btn)
        return bar

    # —— set_project / try_release ——

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        self._project_dir = path
        if path is None:
            self._sb_path = None
            self._sb = None
            self._set_sb_to_ui(None)
            self._state = "idle"
            for b in (self._gen_btn, self._save_btn, self._view_json_btn,
                       self._advance_btn):
                b.setEnabled(False)
            return
        self._sb_path = path / "分镜.json"
        self._load_from_disk()
        self._gen_btn.setEnabled(True)
        self._view_json_btn.setEnabled(self._sb is not None)

    def _load_from_disk(self):
        self._sb = None
        if self._sb_path and self._sb_path.is_file():
            try:
                self._sb = json.loads(self._sb_path.read_text(encoding="utf-8"))
                self._last_load_mtime = self._sb_path.stat().st_mtime
                self._original_sb_json = json.dumps(self._sb, ensure_ascii=False,
                                                     sort_keys=True)
            except Exception:
                self._sb = None
        self._set_sb_to_ui(self._sb)
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._state = "done" if self._sb else "idle"
        self._advance_btn.setEnabled(self._state == "done")

    def _set_sb_to_ui(self, sb: dict | None):
        # 清空角色行
        for r in self._character_rows:
            r.deleteLater()
        self._character_rows = []
        if sb is None:
            self._title_edit.blockSignals(True); self._title_edit.clear()
            self._title_edit.blockSignals(False)
            self._total_duration_label.setText("0")
            self._global_style_edit.blockSignals(True)
            self._global_style_edit.clear()
            self._global_style_edit.blockSignals(False)
            self._shots_model.set_shots([])
            self._warnings_banner.set_warnings([])
            return
        self._title_edit.blockSignals(True)
        self._title_edit.setText(sb.get("title", ""))
        self._title_edit.blockSignals(False)
        self._total_duration_label.setText(str(sb.get("totalDuration", 0)))
        self._global_style_edit.blockSignals(True)
        self._global_style_edit.setPlainText(sb.get("globalStyle", ""))
        self._global_style_edit.blockSignals(False)
        # characters
        for i, ch in enumerate(sb.get("characters", []) or []):
            row = _CharacterRow(i, ch.get("name", ""), ch.get("appearance", ""))
            row.changed.connect(self._mark_dirty)
            row.removeClicked.connect(self._on_remove_character)
            self._characters_layout.addWidget(row)
            self._character_rows.append(row)
        # shots 表（直接传引用，setData 写回原 dict）
        self._shots_model.set_shots(sb.get("shots", []) or [])
        self._warnings_banner.set_warnings(self._warnings)

    def try_release(self) -> bool:
        if not self._dirty:
            return True
        ans = QMessageBox.question(
            self, "分镜有未保存改动", "切换前是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            self._on_save_clicked()
            return True
        if ans == QMessageBox.Discard:
            self._load_from_disk()
            return True
        return False

    # —— UI 事件 ——

    def _mark_dirty(self):
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._advance_btn.setEnabled(False)

    def _on_add_character(self):
        if self._sb is None:
            self._sb = {"title": "", "globalStyle": "", "characters": [], "shots": []}
        self._sb.setdefault("characters", []).append({"name": "", "appearance": ""})
        idx = len(self._sb["characters"]) - 1
        row = _CharacterRow(idx, "", "")
        row.changed.connect(self._mark_dirty)
        row.removeClicked.connect(self._on_remove_character)
        self._characters_layout.addWidget(row)
        self._character_rows.append(row)
        self._mark_dirty()

    def _on_remove_character(self, idx: int):
        if self._sb is None:
            return
        chars = self._sb.get("characters", [])
        if 0 <= idx < len(chars):
            chars.pop(idx)
            # 重渲染（角色 idx 会变）
            self._set_sb_to_ui(self._sb)
            self._mark_dirty()

    def _on_save_clicked(self):
        if self._sb is None or self._sb_path is None:
            return
        # 把 UI 状态吸回 _sb
        self._sb["title"] = self._title_edit.text().strip()
        self._sb["globalStyle"] = self._global_style_edit.toPlainText().strip()
        self._sb["characters"] = [
            {"name": n, "appearance": a}
            for r in self._character_rows
            for (n, a) in [r.values()]
        ]
        # pydantic 二次校验
        try:
            from screenwriter_agent.models.storyboard_schema import Storyboard
            Storyboard.model_validate(self._sb)
        except Exception as e:
            QMessageBox.warning(self, "保存失败：数据无效", str(e))
            return
        try:
            atomic_write_text(
                self._sb_path,
                json.dumps(self._sb, ensure_ascii=False, indent=2))
            self._last_load_mtime = self._sb_path.stat().st_mtime
            self._original_sb_json = json.dumps(self._sb, ensure_ascii=False,
                                                 sort_keys=True)
            self._dirty = False
            self._save_btn.setEnabled(False)
            self._state = "done"
            self._advance_btn.setEnabled(True)
            self.projectStateChanged.emit()
            self.statusMessage.emit("分镜.json 已保存")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_view_json_clicked(self):
        if self._sb is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("分镜.json（只读）")
        dlg.resize(720, 600)
        v = QVBoxLayout(dlg)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(json.dumps(self._sb, ensure_ascii=False, indent=2))
        v.addWidget(viewer)
        bar = QHBoxLayout()
        btn_copy = QPushButton("复制到剪贴板")
        btn_copy.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(viewer.toPlainText()))
        bar.addWidget(btn_copy)
        btn_open = QPushButton("打开文件")
        btn_open.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._sb_path))))
        bar.addWidget(btn_open)
        bar.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bar.addWidget(bb)
        v.addLayout(bar)
        dlg.exec()

    def _on_advance_clicked(self):
        if self._dirty and not self.try_release():
            return
        self.stageAdvanceRequested.emit(3)

    def _on_warning_clicked(self, path: str):
        # 解析 shots[N].field → 高亮表格行 N
        import re
        m = re.match(r"shots\[(\d+)\]", path)
        if m:
            row = int(m.group(1))
            if 0 <= row < self._shots_model.rowCount():
                self._table.selectRow(row)

    # —— 生成 / SSE ——

    def _on_generate_clicked(self):
        if self._project_dir is None:
            return
        script_path = self._project_dir / "剧本.md"
        if not script_path.is_file():
            QMessageBox.warning(self, "上游缺失",
                                  "请先在「剧本」阶段生成剧本.md。")
            return
        params = None
        if self._state == "done":
            ans = QMessageBox.question(
                self, "重新生成",
                "重新生成会覆盖分镜.json，并删除下游 prompts/。继续？",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            params = {"purge_downstream": "true"}
        body = {
            "project_dir": str(self._project_dir),
            "options": {
                "aspect_ratio": self._aspect_combo.currentText(),
                "fps": self._fps_spin.value(),
                "shot_duration_default": self._default_dur_spin.value(),
                "density": self._density_combo.currentText(),
            },
        }
        self._buf = ""
        self._start_stream("/storyboard", body, params)

    def _start_stream(self, path, body, params=None):
        self._state = "streaming"
        self._gen_btn.hide(); self._stop_btn.show()
        self._stream_label.setText("● 流式 · 已 0 字")
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(False)
        self._worker = StreamWorker(self._client, path, body, params, parent=self)
        self._worker.event.connect(self._on_sse_event)
        self._worker.finished_ok.connect(self._on_stream_done_signal)
        self._worker.failed.connect(self._on_stream_failed)
        self._worker.start()

    def _stop_stream(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._state = "idle"
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")

    def _on_sse_event(self, event_name: str, data: dict):
        if event_name == "delta":
            text = data.get("text", "")
            self._buf += text
            self._stream_label.setText(f"● 流式 · 已 {len(self._buf)} 字")
        elif event_name == "status":
            phase = data.get("phase", "")
            if phase == "validating":
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._buf)} 字 · 修复中…")
        elif event_name == "done":
            # 直接消费 done 携带的 result + warnings
            sb = data.get("result")
            warns = data.get("warnings", [])
            saved = data.get("saved", "")
            if sb is not None:
                self._sb = sb
                self._warnings = warns or []
                self._original_sb_json = json.dumps(sb, ensure_ascii=False,
                                                     sort_keys=True)
                if saved:
                    try:
                        self._last_load_mtime = Path(saved).stat().st_mtime
                    except OSError:
                        pass
                self._set_sb_to_ui(sb)
                self._dirty = False
                self._save_btn.setEnabled(False)
                self._state = "done"
                self._advance_btn.setEnabled(True)
        elif event_name == "error":
            code = data.get("code", "")
            hint = data.get("hint") or data.get("message", "")
            details = data.get("details", {})
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

    def _on_stream_done_signal(self):
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str):
        self._stop_stream()
        QMessageBox.warning(self, "生成失败",
                             f"分镜生成失败：{msg}\n请检查网络或 LLM 配置。")
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_storyboard_page.py -q -p no:faulthandler
```

Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/storyboard_page.py tests/test_ui/screenwriter/test_storyboard_page.py
git commit -m "feat(ui): StoryboardPage 分镜阶段子面板（全局头+表格+warnings+SSE 修复链）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: _ProductTree 子控件

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/_product_tree.py`
- Test: `tests/test_ui/screenwriter/test_product_tree.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_product_tree.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._product_tree import _ProductTree


def _app():
    return QApplication.instance() or QApplication([])


def _sb_fixture():
    return {
        "title": "demo",
        "characters": [{"name": "狐妖"}, {"name": "书生"}],
        "shots": [{"shotId": f"S{i:02d}"} for i in range(1, 11)],   # 10 shots
    }


def test_build_from_sb_creates_expected_placeholders(tmp_path):
    _app()
    t = _ProductTree()
    t.build_from_sb(tmp_path / "prompts", _sb_fixture(),
                     grid_mode="9", include_character_refs=True)
    # 2 角色 + ceil(10/9)=2 网格 = 4 文件
    paths = list(t.tree_items.keys())
    assert len(paths) == 4
    char_dir = tmp_path / "prompts" / "角色参考图"
    grid_dir = tmp_path / "prompts" / "N宫格"
    assert (char_dir / "狐妖_ref.md") in paths
    assert (char_dir / "书生_ref.md") in paths
    assert (grid_dir / "S1.md") in paths
    assert (grid_dir / "S2.md") in paths


def test_status_dot_updates_when_file_exists(tmp_path):
    _app()
    (tmp_path / "prompts" / "角色参考图").mkdir(parents=True)
    (tmp_path / "prompts" / "角色参考图" / "狐妖_ref.md").write_text("x",
                                                                    encoding="utf-8")
    t = _ProductTree()
    t.build_from_sb(tmp_path / "prompts", _sb_fixture(),
                     grid_mode="9", include_character_refs=True)
    item = t.tree_items[tmp_path / "prompts" / "角色参考图" / "狐妖_ref.md"]
    assert "✓" in item.text(0)
    item2 = t.tree_items[tmp_path / "prompts" / "N宫格" / "S1.md"]
    assert "○" in item2.text(0)


def test_set_status_streaming():
    _app()
    t = _ProductTree()
    t.build_from_sb(Path("/tmp/nothing"), _sb_fixture(),
                     grid_mode="single", include_character_refs=False)
    # grid single：10 shots → 10 网格文件
    grid_dir = Path("/tmp/nothing") / "N宫格"
    p = grid_dir / "S1.md"
    assert p in t.tree_items
    t.set_status(p, "streaming")
    assert "●" in t.tree_items[p].text(0)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_product_tree.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 _ProductTree**

`drama_shot_master/ui/widgets/screenwriter/_product_tree.py`:

```python
"""产物树：按 _sb 推算预期文件 + 已落盘文件状态点。"""
from __future__ import annotations

from math import ceil
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


_STATUS_GLYPHS = {"missing": "○", "streaming": "●", "done": "✓"}
_STATUS_COLORS = {
    "missing":   "#9aa0a6",
    "streaming": "#4a9eff",
    "done":      "#4ec98f",
}


class _ProductTree(QTreeWidget):
    fileActivated = Signal(object)        # Path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree_items: dict[Path, QTreeWidgetItem] = {}

    def build_from_sb(self, prompts_dir: Path, sb: dict,
                      *, grid_mode: str,
                      include_character_refs: bool):
        """按分镜.json 推算预期文件，构建树 + 状态点。"""
        self.clear()
        self.tree_items = {}
        if include_character_refs:
            characters = sb.get("characters") or []
            char_group = QTreeWidgetItem(self,
                [f"📁 角色参考图 ({len(characters)})"])
            char_group.setExpanded(True)
            for ch in characters:
                name = ch.get("name", "")
                if not name:
                    continue
                p = prompts_dir / "角色参考图" / f"{name}_ref.md"
                status = "done" if p.is_file() else "missing"
                self._add_file_item(char_group, p, status)
        # 网格
        shots = sb.get("shots") or []
        grid_size = {"single": 1, "4": 4, "9": 9}.get(grid_mode, 9)
        n_groups = ceil(len(shots) / grid_size) if shots else 0
        grid_group = QTreeWidgetItem(self, [f"📁 N 宫格 ({n_groups})"])
        grid_group.setExpanded(True)
        for i in range(1, n_groups + 1):
            p = prompts_dir / "N宫格" / f"S{i}.md"
            status = "done" if p.is_file() else "missing"
            self._add_file_item(grid_group, p, status)

    def _add_file_item(self, parent: QTreeWidgetItem, path: Path, status: str):
        text = f"{_STATUS_GLYPHS[status]}  {path.name}"
        it = QTreeWidgetItem(parent, [text])
        it.setData(0, Qt.UserRole, str(path))
        self.tree_items[path] = it

    def set_status(self, path: Path, status: str) -> None:
        if path not in self.tree_items:
            return
        it = self.tree_items[path]
        glyph = _STATUS_GLYPHS.get(status, "○")
        it.setText(0, f"{glyph}  {path.name}")

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int):
        path_str = item.data(0, Qt.UserRole)
        if path_str:
            self.fileActivated.emit(Path(path_str))
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_product_tree.py -q -p no:faulthandler
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_product_tree.py tests/test_ui/screenwriter/test_product_tree.py
git commit -m "feat(ui): _ProductTree（按 _sb 推算文件 + 状态点 ✓/●/○）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: PromptsPage

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/prompts_page.py`
- Test: `tests/test_ui/screenwriter/test_prompts_page.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_prompts_page.py`:

```python
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.prompts_page import PromptsPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _sb_min():
    return {
        "title": "demo",
        "characters": [{"name": "狐妖"}],
        "shots": [{"shotId": "S01"}, {"shotId": "S02"}],
    }


def test_set_project_none_disables_gen():
    _app()
    p = PromptsPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_loads_sb_builds_tree(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    # 1 角色 + ceil(2/9)=1 网格 = 2 文件占位
    assert len(p._tree.tree_items) == 2


def test_partial_event_updates_tree_dot(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    char_dir = tmp_path / "prompts" / "角色参考图"
    char_dir.mkdir(parents=True)
    (char_dir / "狐妖_ref.md").write_text("done content", encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    p._on_sse_event("partial", {
        "saved": str(char_dir / "狐妖_ref.md"),
        "kind": "character_ref",
    })
    item = p._tree.tree_items[char_dir / "狐妖_ref.md"]
    assert "✓" in item.text(0)


def test_upstream_check_blocks_generate(tmp_path, monkeypatch):
    _app()
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)        # 没 分镜.json
    import drama_shot_master.ui.widgets.screenwriter.prompts_page as m
    called = []
    monkeypatch.setattr(m.QMessageBox, "warning",
                         staticmethod(lambda *a, **k: called.append(True)))
    p._on_generate_clicked()
    assert called
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_prompts_page.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 PromptsPage**

`drama_shot_master/ui/widgets/screenwriter/prompts_page.py`:

```python
"""PromptsPage：提示词阶段子面板。

顶 _ParamBar + 主区 QSplitter（左 _ProductTree + 右 _Preview）。
partial 事件 → 树状态点变 ✓；落盘后右侧预览自动刷新。
重生 = 清空 prompts/ + purge_downstream（虽然没下游了，但 Agent 不报错）。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QPlainTextEdit,
    QComboBox, QCheckBox, QMessageBox, QWidget,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._product_tree import _ProductTree
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from screenwriter_agent.core.atomic_write import atomic_write_text


class PromptsPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._prompts_dir: Path | None = None
        self._sb: dict | None = None
        self._current_file: Path | None = None
        self._original_text: str = ""
        self._last_load_mtime: float = 0.0
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 540])
        root.addWidget(splitter, 1)

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("grid:"))
        self._grid_combo = QComboBox()
        self._grid_combo.addItems(["single", "4", "9"])
        self._grid_combo.setCurrentText("9")
        self._grid_combo.currentTextChanged.connect(self._rebuild_tree)
        bar.addWidget(self._grid_combo)
        self._char_refs_chk = QCheckBox("角色参考")
        self._char_refs_chk.setChecked(True)
        self._char_refs_chk.toggled.connect(self._rebuild_tree)
        bar.addWidget(self._char_refs_chk)
        self._quality_chk = QCheckBox("画质增强")
        self._quality_chk.setChecked(True)
        bar.addWidget(self._quality_chk)
        bar.addStretch(1)
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        self._gen_btn = QPushButton("生成提示词")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止"); self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        return bar

    def _build_left(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        self._tree = _ProductTree()
        self._tree.fileActivated.connect(self._on_file_activated)
        v.addWidget(self._tree, 1)
        btn = QPushButton("📂 打开 prompts/")
        btn.clicked.connect(self._on_open_prompts_dir)
        v.addWidget(btn)
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        self._preview_label = QLabel("预览：（点左侧文件）")
        v.addWidget(self._preview_label)
        self._editor = QPlainTextEdit()
        self._editor.textChanged.connect(self._on_editor_changed)
        v.addWidget(self._editor, 1)
        bar = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_clicked)
        bar.addWidget(self._save_btn)
        bar.addStretch(1)
        self._complete_btn = QPushButton("完成 ✓")
        self._complete_btn.clicked.connect(self._on_complete_clicked)
        bar.addWidget(self._complete_btn)
        v.addLayout(bar)
        return w

    # —— set_project / try_release ——

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        self._project_dir = path
        if path is None:
            self._prompts_dir = None
            self._sb = None
            self._current_file = None
            self._tree.clear()
            self._tree.tree_items = {}
            self._editor.blockSignals(True); self._editor.clear()
            self._editor.blockSignals(False)
            self._original_text = ""
            for b in (self._gen_btn, self._save_btn, self._complete_btn):
                b.setEnabled(False)
            return
        self._prompts_dir = path / "prompts"
        # 读 _sb
        sb_path = path / "分镜.json"
        if sb_path.is_file():
            try:
                self._sb = json.loads(sb_path.read_text(encoding="utf-8"))
            except Exception:
                self._sb = None
        else:
            self._sb = None
        self._rebuild_tree()
        self._gen_btn.setEnabled(True)
        self._complete_btn.setEnabled(True)
        self._editor.blockSignals(True); self._editor.clear()
        self._editor.blockSignals(False)
        self._current_file = None
        self._original_text = ""
        self._preview_label.setText("预览：（点左侧文件）")

    def try_release(self) -> bool:
        if not self._is_dirty():
            return True
        ans = QMessageBox.question(
            self, "提示词文件有未保存改动",
            "切换前是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            self._on_save_clicked()
            return True
        if ans == QMessageBox.Discard:
            return True
        return False

    def _is_dirty(self) -> bool:
        return (self._current_file is not None
                and self._editor.toPlainText() != self._original_text)

    # —— 树/预览 ——

    def _rebuild_tree(self, *_):
        if self._prompts_dir is None or self._sb is None:
            self._tree.clear()
            self._tree.tree_items = {}
            return
        self._tree.build_from_sb(
            self._prompts_dir, self._sb,
            grid_mode=self._grid_combo.currentText(),
            include_character_refs=self._char_refs_chk.isChecked())

    def _on_file_activated(self, path):
        if self._is_dirty() and not self.try_release():
            return
        if not path.is_file():
            self._preview_label.setText(f"预览：{path.name}（未生成）")
            self._editor.blockSignals(True); self._editor.clear()
            self._editor.blockSignals(False)
            self._current_file = None
            self._original_text = ""
            self._save_btn.setEnabled(False)
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "打开失败", str(e))
            return
        self._current_file = path
        self._original_text = text
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        try:
            self._last_load_mtime = path.stat().st_mtime
        except OSError:
            pass
        self._preview_label.setText(f"预览：{path.name}")
        self._save_btn.setEnabled(False)

    def _on_editor_changed(self):
        self._save_btn.setEnabled(self._is_dirty())

    def _on_save_clicked(self):
        if self._current_file is None:
            return
        try:
            atomic_write_text(self._current_file, self._editor.toPlainText())
            self._original_text = self._editor.toPlainText()
            self._last_load_mtime = self._current_file.stat().st_mtime
            self._save_btn.setEnabled(False)
            self.statusMessage.emit(f"{self._current_file.name} 已保存")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_open_prompts_dir(self):
        if self._prompts_dir and self._prompts_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._prompts_dir)))

    def _on_complete_clicked(self):
        # 不切阶段；只发完成信号
        self.statusMessage.emit("项目已完成 ✓")
        self.projectStateChanged.emit()

    # —— 生成 / SSE ——

    def _on_generate_clicked(self):
        if self._project_dir is None or self._sb is None:
            QMessageBox.warning(self, "上游缺失",
                                  "请先在「分镜」阶段生成分镜.json。")
            return
        # 重生确认
        params = None
        if self._prompts_dir and self._prompts_dir.exists() and \
                any(self._prompts_dir.iterdir()):
            ans = QMessageBox.question(
                self, "重新生成",
                "重新生成会清空 prompts/。继续？",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            params = {"purge_downstream": "true"}
            shutil.rmtree(self._prompts_dir, ignore_errors=True)
        body = {
            "project_dir": str(self._project_dir),
            "options": {
                "grid_mode": self._grid_combo.currentText(),
                "include_character_refs": self._char_refs_chk.isChecked(),
                "style_extra": "",
                "negative_preset": "标准 SDXL",
                "quality_boost": self._quality_chk.isChecked(),
            },
        }
        self._rebuild_tree()       # 现 prompts/ 已清空，树全 ○
        self._start_stream("/prompts", body, params)

    def _start_stream(self, path, body, params=None):
        self._state = "streaming"
        self._gen_btn.hide(); self._stop_btn.show()
        self._stream_label.setText("● 流式 · 准备中…")
        self._worker = StreamWorker(self._client, path, body, params, parent=self)
        self._worker.event.connect(self._on_sse_event)
        self._worker.finished_ok.connect(self._on_stream_done)
        self._worker.failed.connect(self._on_stream_failed)
        self._worker.start()

    def _stop_stream(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._state = "idle"
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")

    def _on_sse_event(self, event_name: str, data: dict):
        if event_name == "partial":
            saved = data.get("saved", "")
            kind = data.get("kind", "")
            if saved:
                p = Path(saved)
                self._tree.set_status(p, "done")
                self._stream_label.setText(f"● 已生成 {p.name}（{kind}）")
                # 如果当前打开的就是这个文件，刷新预览
                if self._current_file == p and not self._is_dirty():
                    self._on_file_activated(p)

    def _on_stream_done(self):
        self._state = "done"
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")
        self.projectStateChanged.emit()
        self.statusMessage.emit("提示词全部已生成 ✓")

    def _on_stream_failed(self, msg: str):
        self._stop_stream()
        QMessageBox.warning(self, "生成失败",
                             f"提示词生成失败：{msg}\n请检查网络或 LLM 配置。")
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_prompts_page.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/prompts_page.py tests/test_ui/screenwriter/test_prompts_page.py
git commit -m "feat(ui): PromptsPage 提示词阶段子面板（产物树+预览+partial 事件驱动）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: ScreenwriterPanel 改造 — 装配 4 子面板

**Files:**
- Modify: `drama_shot_master/ui/panels/screenwriter_panel.py`
- Test: `tests/test_ui/screenwriter/test_screenwriter_panel_integration.py`

> 删 wizard 占位（145-167 行）；装配 4 真实子面板；删 `_on_generate_stage`/`_on_open_output`；`_switch_stage` 加 dirty 拦截；`_on_row_selected` 给 4 个子面板 set_project。

- [ ] **Step 1: 写失败测试**

`tests/test_ui/screenwriter/test_screenwriter_panel_integration.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel
from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage
from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage
from drama_shot_master.ui.widgets.screenwriter.storyboard_page import StoryboardPage
from drama_shot_master.ui.widgets.screenwriter.prompts_page import PromptsPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    def scan_project(self, path):
        return {"status": "empty", "recommended_next": "ideate", "stages": {}}


def _cfg(tmp_path):
    return type("C", (), {"screenwriter_project_root": str(tmp_path),
                          "screenwriter_models": {}})()


def test_wizard_has_4_real_pages(tmp_path):
    _app()
    p = ScreenwriterPanel(cfg=_cfg(tmp_path), client=_StubClient(), lifecycle=None)
    assert p.wizard.count() == 4
    assert isinstance(p.wizard.widget(0), IdeatePage)
    assert isinstance(p.wizard.widget(1), ScriptPage)
    assert isinstance(p.wizard.widget(2), StoryboardPage)
    assert isinstance(p.wizard.widget(3), PromptsPage)


def test_no_stale_methods_remain(tmp_path):
    _app()
    p = ScreenwriterPanel(cfg=_cfg(tmp_path), client=_StubClient(), lifecycle=None)
    assert not hasattr(p, "_on_generate_stage")
    assert not hasattr(p, "_on_open_output")
    assert not hasattr(p, "_stage_edits")


def test_switch_stage_triggers_try_release(tmp_path, monkeypatch):
    """切阶段前要调当前页 try_release；返 False 则不切。"""
    _app()
    p = ScreenwriterPanel(cfg=_cfg(tmp_path), client=_StubClient(), lifecycle=None)
    # 让当前页（IdeatePage idx 0）的 try_release 强制返 False
    p.wizard.widget(0).try_release = lambda: False
    p._switch_stage(1)
    assert p.wizard.currentIndex() == 0   # 没切走
    p.wizard.widget(0).try_release = lambda: True
    p._switch_stage(1)
    assert p.wizard.currentIndex() == 1


def test_stage_advance_signal_switches(tmp_path):
    _app()
    p = ScreenwriterPanel(cfg=_cfg(tmp_path), client=_StubClient(), lifecycle=None)
    # IdeatePage emit stageAdvanceRequested(1) → 切到 1
    p.wizard.widget(0).stageAdvanceRequested.emit(1)
    assert p.wizard.currentIndex() == 1
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel_integration.py -q -p no:faulthandler
```

Expected: FAIL (现 wizard 装的是占位 QWidget；_stage_edits/_on_generate_stage 还在)

- [ ] **Step 3: 改 screenwriter_panel.py**

**3a) 文件顶部 import 区，删除占位用的 QPlainTextEdit、QInputDialog、QLabel(只 QLabel 在阶段标签头还用，留着) — 实际上简化做法是不删 import，多余无害。但要新增：**

打开 `drama_shot_master/ui/panels/screenwriter_panel.py`，在文件顶部既有 import 块（about line 13-19）之后追加：

```python
from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage
from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage
from drama_shot_master.ui.widgets.screenwriter.storyboard_page import StoryboardPage
from drama_shot_master.ui.widgets.screenwriter.prompts_page import PromptsPage
```

**3b) 删 wizard 占位段。**找到 `_build_detail` 方法内"# Wizard 区（4 阶段子面板）" 开始那段（约 142-166 行）：

```python
        # Wizard 区（4 阶段子面板）；记录每页 widget 以便绑定按钮
        self.wizard = QStackedWidget()
        self._stage_edits: list[QPlainTextEdit] = []
        for stage_idx, name in enumerate(_STAGE_NAMES):
            ...大段占位代码...
            self.wizard.addWidget(page)
        v.addWidget(self.wizard, 1)
        self.stage_btns[0].setChecked(True)
        return w
```

整体替换为：

```python
        # Wizard 区（4 阶段真实子面板）
        self.wizard = QStackedWidget()
        self._stage_pages = [
            IdeatePage(self._client, self),
            ScriptPage(self._client, self),
            StoryboardPage(self._client, self),
            PromptsPage(self._client, self),
        ]
        for sp in self._stage_pages:
            self.wizard.addWidget(sp)
            sp.stageAdvanceRequested.connect(self._switch_stage)
            sp.projectStateChanged.connect(self.refresh)
            sp.statusMessage.connect(self.statusMessage)
        v.addWidget(self.wizard, 1)
        self.stage_btns[0].setChecked(True)
        return w
```

**3c) 删 `_on_generate_stage` 和 `_on_open_output` 方法**（约 323-360 行，整段删）。

**3d) 改 `_on_row_selected` 让 4 个子面板都收到 set_project：**

找到 `_on_row_selected` 方法（搜索 `def _on_row_selected(self):`）。原版结构：
```python
    def _on_row_selected(self):
        r = self.table.currentRow()
        if r < 0: return
        name = self.table.item(r, 0).text()
        self._current_project = self._project_root() / name
        self.lbl_project.setText(name)
        idx = 0
        if self._client is not None:
            try:
                st = self._client.scan_project(self._current_project)
                idx = {"ideate": 0, "script": 1, "storyboard": 2, "prompts": 3}\
                       .get(st.get("recommended_next", "ideate"), 0)
            except Exception: pass
        self._switch_stage(idx)
```

在 `self.lbl_project.setText(name)` 之后、`idx = 0` 之前插入：

```python
        # 给所有 4 个子面板传当前项目（None=占位）
        for sp in self._stage_pages:
            sp.set_project(self._current_project)
```

**3e) 改 `_switch_stage` 加 dirty 拦截：**

找到现 `_switch_stage`:

```python
    def _switch_stage(self, idx: int):
        if not 0 <= idx < len(self.stage_btns): return
        self.wizard.setCurrentIndex(idx)
        btn = self.stage_btns[idx]
        if not btn.isChecked():
            btn.setChecked(True)
```

替换为：

```python
    def _switch_stage(self, idx: int):
        if not 0 <= idx < len(self.stage_btns):
            return
        # 切之前问当前页是否允许释放（dirty 拦截）
        cur = self.wizard.currentWidget()
        if cur is not None and hasattr(cur, "try_release"):
            if not cur.try_release():
                return
        self.wizard.setCurrentIndex(idx)
        btn = self.stage_btns[idx]
        if not btn.isChecked():
            btn.setChecked(True)
```

**3f) 给 ScreenwriterPanel 加 `statusMessage` 信号声明**（如已有则跳过）。搜索 `class ScreenwriterPanel(BasePanel):`，确认 `statusMessage = Signal(str)` 已存在（既有代码已有）。

**3g) 改 `_on_del`**，删项目时同步给子面板 set_project(None) 以释放当前项目引用。找到 `_on_del` 方法尾部：

```python
        shutil.rmtree(self._project_root() / name, ignore_errors=True)
        self._current_project = None
        self.lbl_project.setText("未选择项目")
        self.refresh()
```

之前一行加：
```python
        # 让 4 子面板放弃当前项目
        for sp in self._stage_pages:
            sp.set_project(None)
```

变成：
```python
        # 让 4 子面板放弃当前项目
        for sp in self._stage_pages:
            sp.set_project(None)
        shutil.rmtree(self._project_root() / name, ignore_errors=True)
        ...
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel_integration.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

也跑既有面板 smoke 防止回归：

```bash
python -m pytest tests/test_ui/test_screenwriter_panel_smoke.py -q -p no:faulthandler
```

Expected: PASS（既有 2 个 + 不回归）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/screenwriter_panel.py tests/test_ui/screenwriter/test_screenwriter_panel_integration.py
git commit -m "refactor(ui): ScreenwriterPanel 装配 4 真实子面板（删 wizard 占位 + dirty 拦截）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: 全套件验收

- [ ] **Step 1: 跑 screenwriter 全套件**

```bash
for f in test_stream_worker test_ideate_page test_script_page test_storyboard_helpers test_warnings_banner test_storyboard_page test_product_tree test_prompts_page test_screenwriter_panel_integration; do
  out=$(timeout 30 python -m pytest tests/test_ui/screenwriter/$f.py -q -p no:faulthandler 2>&1 | grep -E "passed|failed" | tail -1)
  echo "$f: $out"
done
```

Expected: 每个文件 `N passed in <1s`，0 failed

- [ ] **Step 2: 跑既有面板 + Agent 套件不回归**

```bash
python -m pytest tests/test_ui/test_screenwriter_panel_smoke.py tests/test_screenwriter_agent/ -q -p no:faulthandler 2>&1 | tail -3
```

Expected: 全 PASS，0 failed

- [ ] **Step 3: 手动 smoke**（可选——若环境允许真启 Agent + 真 LLM key）

```bash
# 启主软件
python -m drama_shot_master.main &
APP_PID=$!
sleep 5
# 检查日志看是否报错
tail -20 ~/.drama_shot_master/logs/screenwriter_agent.log
kill $APP_PID
```

- [ ] **Step 4: 验收 commit**

```bash
git commit --allow-empty -m "test(ui): 编剧 Wizard 4 子面板 + StreamWorker 验收（全套件绿）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec 覆盖：**
- spec §1 总体架构 → Task 11
- spec §2 StreamWorker → Task 2
- spec §3 IdeatePage → Tasks 4-5
- spec §4 ScriptPage → Task 6
- spec §5 StoryboardPage → Tasks 7-8
- spec §6 PromptsPage → Tasks 9-10
- spec §7 ScreenwriterPanel 改造 → Task 11
- spec §8.1 错误处理 → 散落各 page（spec 列的 6 项里：网络错误/上游缺失/磁盘 IO/done 时 error 事件 → IdeatePage._on_stream_failed/ScriptPage 上游检查/_on_save_clicked OSError 处理/StoryboardPage._on_sse_event(error) — 已 cover；Agent 未就绪/外部修改冲突在 plan 中显式延后到 Task 11 验收阶段手动检查或留作后续增量，本期 plan 不强迫每个面板单独写测试）
- spec §8.2 测试 → 每个子面板都有专属测试文件
- spec §8.4 显式延后 → 不在本期实施

**Placeholder 扫描：**
- 无 TBD/TODO/"similar to"。
- Task 12 Step 3 "手动 smoke (可选)" 写明前置条件、Optional 标记，可接受。
- Task 7/8 中 _StubClient 是测试 fixture，不是产品代码 placeholder。

**类型一致性：**
- `_BaseStagePage` 三信号（stageAdvanceRequested/projectStateChanged/statusMessage）在 Task 3 定义、Tasks 5/6/8/10 emit、Task 11 connect 一致 ✓
- `set_project(path: Path | None)` / `try_release() -> bool` 在 Task 3 抽象、4 个子面板实现一致 ✓
- StreamWorker 接口（event/finished_ok/failed/stop()）在 Task 2 定义、4 子面板用法一致 ✓
- `_ProductTree.set_status(path, status)` 在 Task 9 定义、Task 10 PromptsPage._on_sse_event(partial) 调用一致 ✓
- `atomic_write_text` 从 `screenwriter_agent.core.atomic_write` import，在 Tasks 6/8/10 用法一致 ✓
- `_ShotsTableModel.set_shots(list[dict])` 在 Task 7 定义、Task 8 StoryboardPage._set_sb_to_ui 使用一致 ✓
- `stream_post(path, body, params=)` 在 Task 1 定义、Task 2 StreamWorker 使用一致 ✓
