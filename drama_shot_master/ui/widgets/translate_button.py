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
