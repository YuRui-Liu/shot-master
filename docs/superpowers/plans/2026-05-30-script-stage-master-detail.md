# [2.剧本] 左右分栏（主从）布局 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「大纲（集列表）」与「剧集（选中集脚本）」在视觉与数据上分开——左右 `QSplitter`（左大纲/右剧集）+ 可折叠，且大纲流式文本改进左栏只读预览而非剧集编辑器。

**Architecture:** 单文件改造 `script_page.py`。`_build_ui` 由竖排改为 `QSplitter(Horizontal)`，左 `_build_outline_pane()`（大纲表 + 只读预览 + 一键全集），右 `_build_episode_pane()`（折叠钮 + 集标题 + 剧集编辑器）。新增布尔 `_outline_streaming`（流式去向开关）与 `_outline_collapsed`（折叠态）。所有既有控件保留同名属性，旧测试不破。

**Tech Stack:** PySide6（QSplitter/QWidget/QPlainTextEdit/QTableWidget），pytest（offscreen Qt）。

**Spec:** `docs/superpowers/specs/2026-05-30-script-stage-master-detail-design.md`

测试统一加环境前缀（文件首行已 `os.environ.setdefault("QT_QPA_PLATFORM","offscreen")`）。
运行单测用：`QT_QPA_PLATFORM=offscreen python -m pytest <path> -q -o addopts=''`

---

### Task 1: 布局改造为左右 QSplitter

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/script_page.py`（imports / `__init__` / `_build_ui` / 新增 `_build_outline_pane` / `_build_episode_pane` / `_toggle_outline_pane`）
- Test: `tests/test_ui/screenwriter/test_script_page.py`

- [ ] **Step 1: 失败测试** — 追加到 test_script_page.py 末尾

```python
def test_layout_has_splitter_and_hidden_preview(tmp_path):
    """左右分栏：splitter 存在、大纲预览默认隐藏、左右栏控件就位。"""
    _app()
    p = ScriptPage(_StubClient())
    assert p._splitter is not None
    assert p._outline_preview.isHidden()          # 默认隐藏
    assert p._outline_collapsed is False
    # 左栏含大纲表与一键全集，右栏含剧集编辑器与折叠钮
    assert p._collapse_btn.text() == "◀ 大纲"
    assert p._episode_title_lbl.text().startswith("剧集")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py::test_layout_has_splitter_and_hidden_preview -q -o addopts=''`
Expected: FAIL（`AttributeError: '_splitter'` 等）

- [ ] **Step 3: 改 imports** — 把 `QVBoxLayout, QHBoxLayout, ...` 那段补 `QSplitter, QWidget`

```python
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QSpinBox,
    QComboBox, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QWidget,
)
```

- [ ] **Step 4: `__init__` 加状态字段** — 在 `self._original_md: dict[str, str] = {}` 之后、`self._build_ui()` 之前插入

```python
        self._outline_streaming: bool = False         # True=大纲流式中（delta 进预览）
        self._outline_collapsed: bool = False          # 左栏是否折叠
        self._saved_sizes: list[int] = [320, 680]      # 折叠前的分栏宽度
```

- [ ] **Step 5: 重写 `_build_ui`** — 整体替换现有 `_build_ui` 方法体

```python
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        self._upstream_banner = _UpstreamBanner()
        root.addWidget(self._upstream_banner)
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(self._build_outline_pane())   # 左·大纲
        self._splitter.addWidget(self._build_episode_pane())   # 右·剧集
        self._splitter.setCollapsible(0, True)
        self._splitter.setCollapsible(1, False)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes(self._saved_sizes)
        root.addWidget(self._splitter, 1)
        root.addLayout(self._build_action_bar())

    def _build_outline_pane(self) -> QWidget:
        pane = QWidget()
        v = QVBoxLayout(pane)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(QLabel("大纲 · 集列表"))
        self._outline_table = QTableWidget(0, 4)
        self._outline_table.setHorizontalHeaderLabels(["集", "标题", "概要", "操作"])
        h = self._outline_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Interactive)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        self._outline_table.setColumnWidth(3, 92)
        self._outline_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._outline_table.setSelectionMode(QTableWidget.SingleSelection)
        self._outline_table.itemSelectionChanged.connect(self._on_outline_row_selected)
        v.addWidget(self._outline_table, 1)
        # 大纲流式只读预览（默认隐藏；流式时替换列表显示）
        self._outline_preview = QPlainTextEdit()
        self._outline_preview.setReadOnly(True)
        self._outline_preview.setPlaceholderText("大纲生成中…")
        self._outline_preview.hide()
        v.addWidget(self._outline_preview, 1)
        batch_bar = QHBoxLayout()
        self._batch_btn = QPushButton("一键全集 ▶")
        self._batch_btn.clicked.connect(self._on_batch_clicked)
        batch_bar.addWidget(self._batch_btn)
        self._batch_progress = QLabel("")
        batch_bar.addWidget(self._batch_progress)
        batch_bar.addStretch(1)
        v.addLayout(batch_bar)
        return pane

    def _build_episode_pane(self) -> QWidget:
        pane = QWidget()
        v = QVBoxLayout(pane)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        head = QHBoxLayout()
        self._collapse_btn = QPushButton("◀ 大纲")
        self._collapse_btn.setMaximumWidth(80)
        self._collapse_btn.clicked.connect(self._toggle_outline_pane)
        head.addWidget(self._collapse_btn)
        self._episode_title_lbl = QLabel("剧集 · 正文")
        head.addWidget(self._episode_title_lbl)
        head.addStretch(1)
        v.addLayout(head)
        self._episode_editor = QPlainTextEdit()
        self._episode_editor.setPlaceholderText("选中左侧某集后显示该集 md（或在此直接编写）")
        self._episode_editor.textChanged.connect(self._on_editor_changed)
        v.addWidget(self._episode_editor, 1)
        return pane

    def _toggle_outline_pane(self) -> None:
        """折叠/展开左栏（按显式状态驱动，不依赖 splitter 像素尺寸）。"""
        if not self._outline_collapsed:
            cur = self._splitter.sizes()
            if cur and cur[0] > 0:
                self._saved_sizes = cur
            self._splitter.setSizes([0, sum(cur) or sum(self._saved_sizes)])
            self._collapse_btn.setText("▶ 大纲")
            self._outline_collapsed = True
        else:
            left = self._saved_sizes[0] if self._saved_sizes[0] > 0 else 320
            self._splitter.setSizes([left, self._saved_sizes[1] or 680])
            self._collapse_btn.setText("◀ 大纲")
            self._outline_collapsed = False
```

- [ ] **Step 6: 删除旧 `_build_ui` 里残留的注释/控件构建**（确认旧 `_build_ui` 整体被 Step 5 替换，无重复 `_outline_table`/`_episode_editor` 构建）

- [ ] **Step 7: 跑新测试 + 全量旧测试**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -o addopts=''`
Expected: PASS（新 test_layout_* 过 + 既有 12 项全过）

- [ ] **Step 8: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py tests/test_ui/screenwriter/test_script_page.py
git commit -m "refactor(script-page): 左右 QSplitter 分栏 + 大纲只读预览骨架"
```

---

### Task 2: 大纲流式 delta 改进左栏预览（根治数据混淆）

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/script_page.py`（`_on_sse_event` 的 `delta` 分支）
- Test: `tests/test_ui/screenwriter/test_script_page.py`

- [ ] **Step 1: 失败测试**

```python
def test_outline_delta_goes_to_preview_not_editor(tmp_path):
    """大纲流式时 delta 进 _outline_preview，剧集编辑器保持空。"""
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_streaming = True
    p._on_sse_event("delta", {"text": '{"episodes":['}, str(tmp_path))
    assert '{"episodes":[' in p._outline_preview.toPlainText()
    assert p._episode_editor.toPlainText() == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py::test_outline_delta_goes_to_preview_not_editor -q -o addopts=''`
Expected: FAIL（大纲文本误入 `_episode_editor` → preview 为空）

- [ ] **Step 3: 改 `_on_sse_event` 的 delta 分支** — 整体替换现有 `if event_name == "delta":` 块

```python
        if event_name == "delta":
            text = data.get("text", "")
            if not (text and proj == self._project_dir):
                pass
            elif self._outline_streaming:
                # 大纲流式 → 进左栏只读预览，绝不进剧集编辑器
                self._outline_preview.moveCursor(QTextCursor.End)
                self._outline_preview.insertPlainText(text)
            elif ep_id == self._current_episode:
                self._episode_editor.blockSignals(True)
                self._episode_editor.moveCursor(QTextCursor.End)
                self._episode_editor.insertPlainText(text)
                self._episode_editor.blockSignals(False)
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._episode_editor.toPlainText())} 字")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -o addopts=''`
Expected: PASS（全绿）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py tests/test_ui/screenwriter/test_script_page.py
git commit -m "fix(script-page): 大纲流式 delta 进左栏预览，不再灌剧集编辑器"
```

---

### Task 3: 大纲流式进入/退出视图切换（start/done/error/stop）

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/script_page.py`（`_start_outline_stream` / `_on_sse_event` done+error / `_stop_stream`）
- Test: `tests/test_ui/screenwriter/test_script_page.py`

- [ ] **Step 1: 失败测试**

```python
def test_outline_done_restores_list_view(tmp_path):
    """大纲 done(saved=剧本.json) 后：预览隐藏、列表显示并渲染、标志复位。"""
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "T", "episode_count": 2, "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": "a", "summary": "s"},
                     {"id": "E2", "title": "b", "summary": "s2"}],
    }, ensure_ascii=False), encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    # 进入大纲流式态
    p._outline_streaming = True
    p._outline_table.hide()
    p._outline_preview.show()
    p._on_sse_event("done", {"saved": str(tmp_path / "剧本.json")}, str(tmp_path))
    assert p._outline_streaming is False
    assert p._outline_preview.isHidden()
    assert not p._outline_table.isHidden()
    assert p._outline_table.rowCount() == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py::test_outline_done_restores_list_view -q -o addopts=''`
Expected: FAIL（`_outline_streaming` 仍 True / 预览未隐藏）

- [ ] **Step 3: `_start_outline_stream` 进入预览视图** — 在该方法体内 `self._stream_label.setText("● 生成大纲…")` 之前插入

```python
        self._outline_streaming = True
        if self._outline_collapsed:                # 折叠态生成大纲 → 自动展开
            self._toggle_outline_pane()
        self._outline_table.hide()
        self._outline_preview.clear()
        self._outline_preview.show()
```

- [ ] **Step 4: done 分支退出预览视图** — 把现有 `if saved and saved.endswith("剧本.json"):` 块替换为

```python
                if saved and saved.endswith("剧本.json"):
                    self._outline_streaming = False
                    self._outline_preview.hide()
                    self._outline_table.show()
                    self._load_index()
```

- [ ] **Step 5: error 分支复位 + `_stop_stream` 复位** — error 分支替换为

```python
        elif event_name == "error":
            if proj == self._project_dir:
                if self._outline_streaming:
                    self._outline_streaming = False
                    self._outline_preview.hide()
                    self._outline_table.show()
                QMessageBox.warning(self, "生成失败",
                                     data.get("hint") or data.get("message", ""))
                self._exit_streaming_view()
            self.projectStateChanged.emit()
```

并在 `_stop_stream` 的 `self._exit_streaming_view()` 之前插入：

```python
        if self._outline_streaming:
            self._outline_streaming = False
            self._outline_preview.hide()
            self._outline_table.show()
```

- [ ] **Step 6: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -o addopts=''`
Expected: PASS（全绿，含旧测试）

- [ ] **Step 7: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py tests/test_ui/screenwriter/test_script_page.py
git commit -m "feat(script-page): 大纲流式进/出预览视图切换（start/done/error/stop）"
```

---

### Task 4: 左栏折叠切换

**Files:**
- Modify: 无（`_toggle_outline_pane` 已在 Task 1 实现）
- Test: `tests/test_ui/screenwriter/test_script_page.py`

- [ ] **Step 1: 失败测试**（先验证：Task 1 已实现，此测试应直接过——若 Task 1 未含逻辑则失败）

```python
def test_collapse_toggle_hides_left_pane(tmp_path):
    """折叠钮按显式状态切换：折叠→宽度0/文案▶；展开→文案◀。"""
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._splitter.setSizes([300, 700])
    p._toggle_outline_pane()
    assert p._outline_collapsed is True
    assert p._collapse_btn.text() == "▶ 大纲"
    assert p._splitter.sizes()[0] == 0
    p._toggle_outline_pane()
    assert p._outline_collapsed is False
    assert p._collapse_btn.text() == "◀ 大纲"
```

- [ ] **Step 2: 跑测试**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py::test_collapse_toggle_hides_left_pane -q -o addopts=''`
Expected: PASS（逻辑在 Task 1）。若 FAIL，回查 `_toggle_outline_pane`。

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui/screenwriter/test_script_page.py
git commit -m "test(script-page): 左栏折叠切换回归"
```

---

### Task 5: 选集更新右栏标题

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/script_page.py`（`_on_outline_row_selected` 末尾）
- Test: `tests/test_ui/screenwriter/test_script_page.py`

- [ ] **Step 1: 失败测试**

```python
def test_episode_select_updates_right_editor_and_title(tmp_path):
    """选第 2 行：current_episode=E2、右栏编辑器载入 E2、标题含 E2。"""
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "T", "episode_count": 2, "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": "a", "summary": "s"},
                     {"id": "E2", "title": "b", "summary": "s2"}],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "剧本_E2.md").write_text("E2 正文", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_table.selectRow(1)
    assert p._current_episode == "E2"
    assert "E2 正文" in p._episode_editor.toPlainText()
    assert "E2" in p._episode_title_lbl.text()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py::test_episode_select_updates_right_editor_and_title -q -o addopts=''`
Expected: FAIL（标题仍为「剧集 · 正文」）

- [ ] **Step 3: `_on_outline_row_selected` 末尾更新标题** — 在该方法把 md 写入 `_episode_editor` 之后补一行（方法末尾）

```python
        self._episode_title_lbl.setText(f"剧集 · {ep_id} 正文")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -o addopts=''`
Expected: PASS（全绿）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py tests/test_ui/screenwriter/test_script_page.py
git commit -m "feat(script-page): 选集更新右栏剧集标题"
```

---

## 收尾验证

- [ ] 全量 script_page 测试：`QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -o addopts=''` → 全绿（旧 12 + 新 5）。
- [ ] 旁邻阶段页冒烟：`QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/screenwriter/test_storyboard_page.py tests/test_ui/screenwriter/test_prompts_page.py -q -o addopts=''` → 全绿。
