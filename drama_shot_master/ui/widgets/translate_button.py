"""可复用的"译"按钮 + 弹窗。

用法：
    attach_translate_button(self.prompt_edit, parent=self)

按钮会在 text 为空时自动 disable；点击触发后台线程调
drama_shot_master.providers.translator.translate_en_to_zh，
完成后弹一个非模态 QDialog 显示原文和中译，失败时显示提示。

线程安全说明
------------
后台调用走项目通用的 FunctionWorker（QThread 子类），完成 / 失败信号的接收
方为 _TranslateController（QObject，parented 到 GUI 线程的 parent widget），
因此 Qt AutoConnection 会以 QueuedConnection 把信号路由回 GUI 线程，
_TranslateDialog 始终在 GUI 线程构造。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from drama_shot_master.providers.translator import translate_en_to_zh
from drama_shot_master.ui.worker import FunctionWorker


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


class _TranslateController(QObject):
    """QObject 控制器：固定在 GUI 线程，承接 worker 信号 → 弹窗。

    通过 ``parent=parent`` 与 GUI 上的 QWidget 形成 Qt 父子关系，因此
    本对象与槽方法都在 GUI 线程上；FunctionWorker 在另一线程发出的
    finished_with_result / failed 信号会以 QueuedConnection 派发回来。
    """

    def __init__(self, btn: QToolButton, text_widget: QPlainTextEdit,
                 parent: QWidget):
        super().__init__(parent)
        self._btn = btn
        self._text_widget = text_widget
        self._parent_widget = parent
        self._worker: Optional[FunctionWorker] = None
        self._source_text: str = ""

        text_widget.textChanged.connect(self._sync_enabled)
        btn.clicked.connect(self._on_clicked)
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        running = self._worker is not None
        text = self._text_widget.toPlainText().strip()
        self._btn.setEnabled(bool(text) and not running)

    def _on_clicked(self) -> None:
        if self._worker is not None:
            return  # 已在跑
        text = self._text_widget.toPlainText()
        if not text.strip():
            return
        self._source_text = text

        worker = FunctionWorker(translate_en_to_zh, text)
        worker.finished_with_result.connect(self._on_result)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_thread_done)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        self._sync_enabled()
        worker.start()

    def _on_result(self, result) -> None:
        # translate_en_to_zh 返回 str | None
        self._show_dialog(result if isinstance(result, str) else None)

    def _on_failed(self, _msg: str) -> None:
        # translate_en_to_zh 本身会吞异常返回 None，所以这里通常不会触发；
        # 但若 FunctionWorker 报错，仍走"失败"弹窗。
        self._show_dialog(None)

    def _show_dialog(self, translated: Optional[str]) -> None:
        dlg = _TranslateDialog(self._source_text, translated,
                               parent=self._parent_widget,
                               on_retry=self._on_clicked)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.show()

    def _on_thread_done(self) -> None:
        self._worker = None
        self._sync_enabled()


def attach_translate_button(text_widget: QPlainTextEdit,
                            parent: QWidget) -> QToolButton:
    """创建一个"译"按钮，挂到 parent，但与 text_widget 联动。

    返回 button，调用方负责把它 add 进自己的 layout。

    内部会创建一个 _TranslateController 作为 parent 的子 QObject，承接
    后台 worker 的信号；信号以 QueuedConnection 回到 GUI 线程，弹窗始终
    在 GUI 线程构造。
    """
    btn = QToolButton(parent)
    btn.setText("译")
    btn.setToolTip("调 DeepLX 翻译当前 prompt 为中文")
    btn.setFixedSize(28, 22)
    # 控制器 parented 到 parent → 与 parent 同生命周期，无需手动持有。
    _TranslateController(btn, text_widget, parent)
    return btn
