# DeepLX Prompt 中文预览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 video panel 的 `local_prompt` 和 `global_prompt` 两处可编辑字段加一个"译"按钮，点击调公共 DeepLX 接口弹窗显示中译，失败静默回退。

**Architecture:** 新增一个无 Qt 依赖的纯函数翻译模块（stdlib urllib），加一个 PyQt 按钮工具函数把它接到 `QPlainTextEdit` 上。两个现有 widget 各加一行 attach 调用。

**Tech Stack:** Python stdlib (`urllib.request`, `json`, `socket`, `os`, `logging`)、PySide6 (`QToolButton`, `QDialog`, `QThread`, `Signal`)、pytest (`unittest.mock.patch`)。

**Spec:** [docs/superpowers/specs/2026-05-24-deeplx-prompt-preview-design.md](../specs/2026-05-24-deeplx-prompt-preview-design.md)

---

## File Structure

新增文件：
- `drama_shot_master/providers/translator.py` — 纯函数 `translate_en_to_zh(text, *, timeout=3.0) -> str | None`，读 `os.environ["DEEPLX_URL"]`，任何异常返回 None。
- `drama_shot_master/ui/widgets/translate_button.py` — `attach_translate_button(text_widget, parent) -> QToolButton`，挂按钮 + 后台线程 + 弹窗。
- `tests/test_providers/test_translator.py` — 单测 translator 的成功/超时/HTTP错误/坏JSON/缺字段/无env 六条路径。

修改文件：
- `drama_shot_master/ui/widgets/segment_editor.py` — 第 42 行 `root.addWidget(QLabel("Prompt"))` 改为带按钮的水平 layout。
- `drama_shot_master/ui/widgets/video_global_form.py` — 第 53 行 `root.addWidget(QLabel("Global prompt"))` 改为带按钮的水平 layout。
- `.env.example` — 追加 `DEEPLX_URL=https://api.deeplx.org/translate`。

---

## Task 1: translator 模块（TDD）

**Files:**
- Create: `drama_shot_master/providers/translator.py`
- Test: `tests/test_providers/test_translator.py`

- [ ] **Step 1.1: 写失败测试**

Create `tests/test_providers/test_translator.py`:

```python
"""Tests for drama_shot_master.providers.translator."""
from __future__ import annotations

import io
import json
import socket
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from drama_shot_master.providers.translator import translate_en_to_zh


def _fake_response(body: bytes):
    """Build a fake urlopen() context manager returning given bytes."""
    class _FakeResp:
        def __enter__(self_inner):
            return io.BytesIO(body)
        def __exit__(self_inner, *exc):
            return False
    return _FakeResp()


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("DEEPLX_URL", "https://example.test/translate")


def test_success_returns_translated_text():
    body = json.dumps({"code": 200, "data": "你好"}).encode("utf-8")
    with patch("drama_shot_master.providers.translator.urlopen",
               return_value=_fake_response(body)):
        assert translate_en_to_zh("hello") == "你好"


def test_empty_text_returns_none_without_request():
    with patch("drama_shot_master.providers.translator.urlopen") as m:
        assert translate_en_to_zh("") is None
        assert translate_en_to_zh("   ") is None
        m.assert_not_called()


def test_no_env_url_returns_none(monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    assert translate_en_to_zh("hello") is None


def test_timeout_returns_none():
    with patch("drama_shot_master.providers.translator.urlopen",
               side_effect=socket.timeout("timed out")):
        assert translate_en_to_zh("hello") is None


def test_http_error_returns_none():
    err = HTTPError("u", 500, "boom", {}, None)
    with patch("drama_shot_master.providers.translator.urlopen",
               side_effect=err):
        assert translate_en_to_zh("hello") is None


def test_bad_json_returns_none():
    with patch("drama_shot_master.providers.translator.urlopen",
               return_value=_fake_response(b"not json")):
        assert translate_en_to_zh("hello") is None


def test_missing_data_field_returns_none():
    body = json.dumps({"code": 500, "msg": "err"}).encode("utf-8")
    with patch("drama_shot_master.providers.translator.urlopen",
               return_value=_fake_response(body)):
        assert translate_en_to_zh("hello") is None


def test_non_string_data_returns_none():
    body = json.dumps({"code": 200, "data": 12345}).encode("utf-8")
    with patch("drama_shot_master.providers.translator.urlopen",
               return_value=_fake_response(body)):
        assert translate_en_to_zh("hello") is None
```

- [ ] **Step 1.2: 运行测试，确认全部失败**

Run: `pytest tests/test_providers/test_translator.py -v`
Expected: 8 个 `ModuleNotFoundError: No module named 'drama_shot_master.providers.translator'`。

- [ ] **Step 1.3: 实现 translator.py**

Create `drama_shot_master/providers/translator.py`:

```python
"""DeepLX 翻译客户端：英文 prompt → 中文预览。

设计原则：
- 任何异常（网络、JSON、缺字段）都返回 None，调用方负责回退。
- 不抛错、不打 stacktrace，只 logging.info/warning。
- 无 Qt 依赖，可单测、可在 CLI 中复用。
"""
from __future__ import annotations

import json
import logging
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_logger = logging.getLogger(__name__)

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "drama-shot-master/translator",
}


def translate_en_to_zh(text: str, *, timeout: float = 3.0) -> str | None:
    """POST 文本到 DEEPLX_URL，返回中译；任何失败返回 None。

    成功响应形如：{"code": 200, "data": "...", ...}
    """
    if not text or not text.strip():
        return None

    url = os.environ.get("DEEPLX_URL", "").strip()
    if not url:
        _logger.warning("DEEPLX_URL not set; skip translation")
        return None

    payload = json.dumps({
        "text": text,
        "source_lang": "auto",
        "target_lang": "ZH",
    }).encode("utf-8")

    req = Request(url, data=payload, headers=_HEADERS, method="POST")

    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (HTTPError, URLError, socket.timeout, OSError) as exc:
        _logger.info("DeepLX request failed: %s", exc)
        return None

    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _logger.info("DeepLX bad response body: %s", exc)
        return None

    data = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(data, str) or not data:
        _logger.info("DeepLX missing/invalid data field: %r", obj)
        return None
    return data
```

- [ ] **Step 1.4: 运行测试，确认全部通过**

Run: `pytest tests/test_providers/test_translator.py -v`
Expected: 8 个测试全部 PASS。

- [ ] **Step 1.5: 提交**

```bash
git add drama_shot_master/providers/translator.py tests/test_providers/test_translator.py
git commit -m "feat(translator): add DeepLX client for prompt zh preview

- Pure stdlib (urllib), no Qt dependency
- Returns None on any failure (network/HTTP/JSON/missing field)
- Reads DEEPLX_URL from env; empty/missing → None

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: translate_button widget

**Files:**
- Create: `drama_shot_master/ui/widgets/translate_button.py`

PyQt UI 不做自动化测试（成本高于收益），按 spec §7.2 的手测清单验证。

- [ ] **Step 2.1: 实现 translate_button.py**

Create `drama_shot_master/ui/widgets/translate_button.py`:

```python
"""可复用的"译"按钮 + 弹窗。

用法：
    attach_translate_button(self.prompt_edit, parent=self)

按钮会在 text 为空时自动 disable；点击触发后台线程调
drama_shot_master.providers.translator.translate_en_to_zh，
完成后弹一个非模态 QDialog 显示原文和中译，失败时显示提示。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from drama_shot_master.providers.translator import translate_en_to_zh


class _TranslateWorker(QObject):
    """后台线程包装，避免阻塞 UI。"""

    finished = Signal(str, object)  # (source_text, translated_or_None)

    def __init__(self, text: str):
        super().__init__()
        self._text = text

    def run(self) -> None:
        result = translate_en_to_zh(self._text)
        self.finished.emit(self._text, result)


class _TranslateDialog(QDialog):
    """非模态弹窗：上半原文、下半译文（或失败提示）。

    失败时显示"重试"按钮；点击后关闭当前弹窗并通过 on_retry
    回调让外层按钮重新发起请求。
    """

    def __init__(self, source: str, translated: Optional[str],
                 parent: Optional[QWidget] = None,
                 on_retry=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 中译预览")
        self.setMinimumSize(420, 320)
        self.setWindowFlag(Qt.WindowType.Window, True)  # 非模态独立窗

        root = QVBoxLayout(self)
        root.setSpacing(6)

        root.addWidget(QLabel("原文"))
        src = QPlainTextEdit(source)
        src.setReadOnly(True)
        root.addWidget(src, 1)

        if translated:
            root.addWidget(QLabel("中译"))
            dst = QPlainTextEdit(translated)
        else:
            url = os.environ.get("DEEPLX_URL", "").strip()
            tip = (f"翻译服务暂不可用。\nDEEPLX_URL={url or '(未配置)'}\n"
                   "请检查网络，或在 .env 中改为可用的 DeepLX 实例。")
            root.addWidget(QLabel("失败"))
            dst = QPlainTextEdit(tip)
        dst.setReadOnly(True)
        root.addWidget(dst, 1)

        btn_row = QHBoxLayout()
        if translated:
            copy_btn = QPushButton("复制译文")
            copy_btn.clicked.connect(
                lambda: QGuiApplication.clipboard().setText(translated))
            btn_row.addWidget(copy_btn)
        elif on_retry is not None:
            retry_btn = QPushButton("重试")

            def _do_retry():
                self.close()
                on_retry()
            retry_btn.clicked.connect(_do_retry)
            btn_row.addWidget(retry_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)


def attach_translate_button(text_widget: QPlainTextEdit,
                            parent: QWidget) -> QToolButton:
    """创建一个"译"按钮，挂到 parent，但与 text_widget 联动。

    返回 button，调用方负责把它 add 进自己的 layout。
    """
    btn = QToolButton(parent)
    btn.setText("译")
    btn.setToolTip("调 DeepLX 翻译当前 prompt 为中文")
    btn.setFixedSize(28, 22)

    # 内部状态：当前正在跑的 thread / worker，避免并发点击
    state: dict = {"thread": None, "worker": None, "dialog": None}

    def _sync_enabled() -> None:
        running = state["thread"] is not None
        text = text_widget.toPlainText().strip()
        btn.setEnabled(bool(text) and not running)

    def _on_clicked() -> None:
        text = text_widget.toPlainText()
        if not text.strip():
            return
        if state["thread"] is not None:
            return  # 已在跑

        thread = QThread(parent)
        worker = _TranslateWorker(text)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def _on_finished(source: str, result):
            dlg = _TranslateDialog(source, result, parent=parent,
                                   on_retry=_on_clicked)
            dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dlg.show()
            state["dialog"] = dlg
            thread.quit()

        worker.finished.connect(_on_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _on_thread_done():
            state["thread"] = None
            state["worker"] = None
            _sync_enabled()

        thread.finished.connect(_on_thread_done)

        state["thread"] = thread
        state["worker"] = worker
        _sync_enabled()
        thread.start()

    btn.clicked.connect(_on_clicked)
    text_widget.textChanged.connect(_sync_enabled)
    _sync_enabled()
    return btn
```

- [ ] **Step 2.2: 烟测 — 模块可导入**

Run: `python -c "from drama_shot_master.ui.widgets.translate_button import attach_translate_button; print('ok')"`
Expected: 输出 `ok`，无异常。

- [ ] **Step 2.3: 提交**

```bash
git add drama_shot_master/ui/widgets/translate_button.py
git commit -m "feat(ui): add attach_translate_button() helper

QToolButton + QThread + non-modal QDialog. Disables itself when
the bound text is empty. Failure shows a helpful message with the
current DEEPLX_URL value.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 接入 SegmentEditor

**Files:**
- Modify: `drama_shot_master/ui/widgets/segment_editor.py:14-17, 42`

- [ ] **Step 3.1: 修改 segment_editor.py 的 imports**

Edit `drama_shot_master/ui/widgets/segment_editor.py` line 14-17.

Old:
```python
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox,
    QDoubleSpinBox, QStackedWidget, QWidget,
)

from drama_shot_master.core.video_timeline_model import TimelineSegment
```

New:
```python
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox,
    QDoubleSpinBox, QStackedWidget, QWidget,
)

from drama_shot_master.core.video_timeline_model import TimelineSegment
from drama_shot_master.ui.widgets.translate_button import attach_translate_button
```

- [ ] **Step 3.2: 修改 prompt 标签行**

Edit `drama_shot_master/ui/widgets/segment_editor.py` line 41-42.

Old:
```python
        # Prompt label + multi-line edit
        root.addWidget(QLabel("Prompt"))
        self.prompt_edit = QPlainTextEdit()
```

New:
```python
        # Prompt label + 译按钮 + multi-line edit
        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("Prompt"))
        prompt_row.addStretch(1)
        self.prompt_edit = QPlainTextEdit()
        prompt_row.addWidget(attach_translate_button(self.prompt_edit, self))
        root.addLayout(prompt_row)
```

注意：`self.prompt_edit` 实例化必须在 `attach_translate_button` 之前，所以这里把它从原 line 43 提前到 layout 之前。下一步把原 line 43 删掉。

- [ ] **Step 3.3: 删除原来的 prompt_edit 实例化与 addWidget**

Edit `drama_shot_master/ui/widgets/segment_editor.py`. 删除原 line 43-46 中已被上一步替代的内容。

Old (原 43-46，注意此时 line 号已偏移）:
```python
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setPlaceholderText("本段 prompt（仅作用于此段）")
        root.addWidget(self.prompt_edit)
```

New:
```python
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setPlaceholderText("本段 prompt（仅作用于此段）")
        root.addWidget(self.prompt_edit)
```

- [ ] **Step 3.4: 烟测 — 模块可导入**

Run: `python -c "from drama_shot_master.ui.widgets.segment_editor import SegmentEditor; print('ok')"`
Expected: 输出 `ok`，无异常。

- [ ] **Step 3.5: 跑现有的 segment_editor 测试（如有）确保未回归**

Run: `pytest tests/ -k segment -v` (no-op if no matches)
Expected: 没有新增失败。

- [ ] **Step 3.6: 提交**

```bash
git add drama_shot_master/ui/widgets/segment_editor.py
git commit -m "feat(segment-editor): attach DeepLX translate button to prompt

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 接入 VideoGlobalForm

**Files:**
- Modify: `drama_shot_master/ui/widgets/video_global_form.py:5-9, 11-12, 53-57`

- [ ] **Step 4.1: 修改 imports**

Edit `drama_shot_master/ui/widgets/video_global_form.py` line 11.

Old:
```python
from drama_shot_master.core.video_timeline_model import TimelineModel
```

New:
```python
from drama_shot_master.core.video_timeline_model import TimelineModel
from drama_shot_master.ui.widgets.translate_button import attach_translate_button
```

- [ ] **Step 4.2: 修改 Global prompt 标签行**

Edit `drama_shot_master/ui/widgets/video_global_form.py` line 52-57.

Old:
```python
        # ---------- Row 2: Global prompt 多行 ----------
        root.addWidget(QLabel("Global prompt"))
        self.global_prompt_edit = QPlainTextEdit()
        self.global_prompt_edit.setMaximumHeight(60)
        self.global_prompt_edit.setPlaceholderText("全片统一风格/角色描述…")
        root.addWidget(self.global_prompt_edit)
```

New:
```python
        # ---------- Row 2: Global prompt 多行 ----------
        self.global_prompt_edit = QPlainTextEdit()
        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("Global prompt"))
        prompt_row.addStretch(1)
        prompt_row.addWidget(
            attach_translate_button(self.global_prompt_edit, self))
        root.addLayout(prompt_row)
        self.global_prompt_edit.setMaximumHeight(60)
        self.global_prompt_edit.setPlaceholderText("全片统一风格/角色描述…")
        root.addWidget(self.global_prompt_edit)
```

- [ ] **Step 4.3: 烟测 — 模块可导入**

Run: `python -c "from drama_shot_master.ui.widgets.video_global_form import VideoGlobalForm; print('ok')"`
Expected: 输出 `ok`，无异常。

- [ ] **Step 4.4: 跑现有的 video_global_form 相关测试（如有）**

Run: `pytest tests/ -k global -v` (no-op if no matches)
Expected: 没有新增失败。

- [ ] **Step 4.5: 提交**

```bash
git add drama_shot_master/ui/widgets/video_global_form.py
git commit -m "feat(video-global-form): attach DeepLX translate button to global prompt

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: .env.example 与全量回归

**Files:**
- Modify: `.env.example`

- [ ] **Step 5.1: 追加 DEEPLX_URL 到 .env.example**

Edit `.env.example`. 在文件末尾追加：

```
# === DeepLX（用于 prompt 中文预览。完全免费，无密钥）===
# 公共实例可能不稳定，可改为自部署 http://localhost:1188/translate
DEEPLX_URL=https://api.deeplx.org/translate
```

- [ ] **Step 5.2: 全量测试回归**

Run: `pytest -q`
Expected: 所有原有测试 PASS + Task 1 新加的 8 个 translator 测试 PASS，无回归。

- [ ] **Step 5.3: 手测清单**

把以下用例在本地跑一遍：

1. 启动应用，打开视频面板。
2. 在 SegmentEditor 的 Prompt 框输入 `a cat walks on a beach` → 点"译"按钮 → 应弹窗显示中文翻译，"复制译文"能复制到剪贴板。
3. 清空 Prompt 框 → "译"按钮应变灰。
4. 在 VideoGlobalForm 的 Global prompt 同样测一次。
5. 关掉网络（或临时把 `.env` 里 `DEEPLX_URL` 改成 `http://127.0.0.1:1/translate`）重启 → 点"译"应弹"翻译服务暂不可用"。
6. 同时打开两个译窗（一段一全局），互不干扰，关闭其中一个不影响另一个。

- [ ] **Step 5.4: 提交**

```bash
git add .env.example
git commit -m "docs(env): document DEEPLX_URL for prompt zh preview

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review 记录

- **Spec coverage:**
  - §3.1 模块拆分 → Task 1（translator）+ Task 2（button widget）+ Task 5（.env.example）
  - §3.2 边界 → translator 无 Qt 依赖（Task 1）；button 是粘合层（Task 2）
  - §4.1 translator 签名 → Task 1 实现
  - §4.2 button + dialog → Task 2 实现（复制 / 关闭 / 失败提示，重试按钮按 YAGNI 不实现，spec §9 已允许"不重试"）
  - §4.3 配置 → Task 5
  - §4.4 两处挂接点 → Task 3 + Task 4
  - §5 数据流 → Task 2 实现
  - §6 错误处理 → Task 1（translator 全部异常路径已覆盖测试）+ Task 2（dialog 失败分支）
  - §7.1 单测 → Task 1.1 覆盖（含额外的 non-string data 测试）
  - §7.2 手测清单 → Task 5.3
- **Placeholder scan:** 无 TBD / TODO / "similar to" / "handle edge cases" 等占位。
- **Type consistency:** `translate_en_to_zh(text, *, timeout) -> str | None`；button 中 `_TranslateWorker.finished` 信号签名 `(source_text, translated_or_None)`；`_TranslateDialog(source, translated, parent)`。所有调用点一致。
- **重试按钮：** Spec §4.2 要求失败态显示重试，Task 2 已实现 — 失败 dialog 显示"重试"按钮，点击关闭当前 dialog 并重新调 `_on_clicked` 发起请求。
