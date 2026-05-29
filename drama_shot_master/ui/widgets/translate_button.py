"""可复用的"译"按钮 + 弹窗（升级到结构化错误）。

用法：
    attach_translate_button(self.prompt_edit, parent=self,
                            on_open_settings=lambda: …)

按钮在 text 为空时自动 disable；点击触发后台线程调
drama_shot_master.providers.translator.translate(text, "en", "zh")，
完成后弹一个非模态 QDialog。

成功：上半原文、下半译文 + 复制按钮。
失败：原文 + error.hint + 按 error.code 给的差异化按钮：
  - AUTH_FAILED → 去设置
  - QUOTA_EXHAUSTED / SERVICE_DISABLED → 打开腾讯控制台
  - RATE_LIMITED → 重试（5s 倒计时后启用）
  - retryable=True → 重试（即时）
  - 其它 → 仅关闭
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from drama_shot_master.providers.translation_base import (
    TranslationErrorCode, TranslationResult,
)
from drama_shot_master.providers.translator import translate
from drama_shot_master.ui.worker import FunctionWorker

_TENCENT_CONSOLE = "https://console.cloud.tencent.com/tmt"


class _TranslateDialog(QDialog):
    """非模态弹窗：原文 + 译文/错误 + 按 error.code 分发按钮。"""

    def __init__(self, source: str, result: TranslationResult,
                 parent: Optional[QWidget] = None,
                 on_retry: Optional[Callable[[], None]] = None,
                 on_open_settings: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 中译预览")
        self.setMinimumSize(420, 320)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setSpacing(6)

        root.addWidget(QLabel("原文"))
        src_edit = QPlainTextEdit(source)
        src_edit.setReadOnly(True)
        root.addWidget(src_edit, 1)

        if result.ok:
            root.addWidget(QLabel(
                f"中译 · {result.provider} · {result.used_chars} 字符"))
            dst = QPlainTextEdit(result.text or "")
            dst.setReadOnly(True)
            root.addWidget(dst, 1)
            root.addLayout(self._build_success_buttons(result.text or ""))
        else:
            err = result.error
            assert err is not None
            root.addWidget(QLabel(f"失败 · {err.provider} · {err.code}"))
            dst = QPlainTextEdit(f"{err.hint}\n\n详情：{err.message}")
            dst.setReadOnly(True)
            root.addWidget(dst, 1)
            root.addLayout(self._build_error_buttons(
                err, on_retry, on_open_settings))

    def _build_success_buttons(self, translated: str) -> QHBoxLayout:
        row = QHBoxLayout()
        copy_btn = QPushButton("复制译文")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(translated))
        row.addWidget(copy_btn)
        row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        return row

    def _build_error_buttons(self, err, on_retry, on_open_settings):
        row = QHBoxLayout()
        # Differentiated action button (by code)
        if (err.code == TranslationErrorCode.AUTH_FAILED
                and on_open_settings is not None):
            btn = QPushButton("去设置")
            btn.clicked.connect(lambda: (self.close(), on_open_settings()))
            row.addWidget(btn)
        elif err.code in (TranslationErrorCode.QUOTA_EXHAUSTED,
                          TranslationErrorCode.SERVICE_DISABLED):
            btn = QPushButton("打开腾讯控制台")
            btn.clicked.connect(self._open_tencent_console)
            row.addWidget(btn)

        # Retry button (if retryable + callback provided)
        if err.retryable and on_retry is not None:
            self._retry_btn = QPushButton("重试")
            self._retry_btn.clicked.connect(
                lambda: (self.close(), on_retry()))
            if err.code == TranslationErrorCode.RATE_LIMITED:
                self._start_countdown(self._retry_btn, 5)
            row.addWidget(self._retry_btn)

        row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        return row

    def _start_countdown(self, btn: QPushButton, seconds: int) -> None:
        """RATE_LIMITED 时给重试按钮 N 秒 disable 倒计时。"""
        self._countdown_remaining = int(seconds)
        original_text = btn.text()
        btn.setEnabled(False)
        btn.setText(f"{original_text} ({self._countdown_remaining}s)")
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        def _tick():
            self._countdown_remaining -= 1
            if self._countdown_remaining <= 0:
                btn.setEnabled(True)
                btn.setText(original_text)
                self._countdown_timer.stop()
            else:
                btn.setText(f"{original_text} ({self._countdown_remaining}s)")
        self._countdown_timer.timeout.connect(_tick)
        self._countdown_timer.start()

    @staticmethod
    def _open_tencent_console() -> None:
        QDesktopServices.openUrl(QUrl(_TENCENT_CONSOLE))


class _TranslateController(QObject):
    """承接 FunctionWorker 信号 → 弹 _TranslateDialog（始终在 GUI 线程）。"""

    def __init__(self, btn: QToolButton, text_widget: QPlainTextEdit,
                 parent: QWidget,
                 on_open_settings: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self._btn = btn
        self._text_widget = text_widget
        self._parent_widget = parent
        self._on_open_settings = on_open_settings
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
            return
        text = self._text_widget.toPlainText()
        if not text.strip():
            return
        self._source_text = text

        worker = FunctionWorker(translate, text, "en", "zh")
        worker.finished_with_result.connect(self._on_result)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_thread_done)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        self._sync_enabled()
        worker.start()

    def _on_result(self, result) -> None:
        # Always TranslationResult now (success or fail)
        self._show_dialog(result if isinstance(result, TranslationResult)
                          else self._synthetic_fail("unexpected result"))

    def _on_worker_failed(self, msg: str) -> None:
        self._show_dialog(self._synthetic_fail(msg))

    def _synthetic_fail(self, msg: str) -> TranslationResult:
        from drama_shot_master.providers.translation_base import (
            TranslationError,
        )
        return TranslationResult.fail(TranslationError(
            code=TranslationErrorCode.UNKNOWN,
            message=msg,
            hint="后台任务异常，重试或重启软件",
            retryable=True, provider="none"))

    def _show_dialog(self, result: TranslationResult) -> None:
        dlg = _TranslateDialog(
            self._source_text, result,
            parent=self._parent_widget,
            on_retry=self._on_clicked,
            on_open_settings=self._on_open_settings)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.show()

    def _on_thread_done(self) -> None:
        self._worker = None
        self._sync_enabled()


def attach_translate_button(
        text_widget: QPlainTextEdit, parent: QWidget,
        on_open_settings: Optional[Callable[[], None]] = None
) -> QToolButton:
    """创建一个"译"按钮，挂到 parent，但与 text_widget 联动。

    on_open_settings：被点击"去设置"时调（用于路由打开设置对话框 + 滚到翻译 section）；
    传 None 则弹窗不显示该按钮（柔性降级）。
    """
    btn = QToolButton(parent)
    btn.setText("译")
    btn.setToolTip("翻译当前 prompt 为中文")
    btn.setFixedSize(28, 22)
    _TranslateController(btn, text_widget, parent, on_open_settings)
    return btn
