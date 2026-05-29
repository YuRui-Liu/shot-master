"""Offscreen smoke for translate button + _TranslateDialog."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationResult,
)
from drama_shot_master.ui.widgets.translate_button import (
    _TranslateDialog, attach_translate_button,
)


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    a = QApplication.instance() or QApplication([])
    yield a


def _fail(code, retryable=False, hint="hint", provider="tencent",
          message="m"):
    return TranslationResult.fail(TranslationError(
        code=code, message=message, hint=hint, retryable=retryable,
        provider=provider))


def test_button_disabled_when_text_empty(app):
    parent = QWidget()
    edit = QPlainTextEdit(parent)
    btn = attach_translate_button(edit, parent)
    assert btn.isEnabled() is False


def test_button_enabled_when_text_present(app):
    parent = QWidget()
    edit = QPlainTextEdit(parent)
    btn = attach_translate_button(edit, parent)
    edit.setPlainText("hello")
    assert btn.isEnabled() is True


def test_success_dialog_has_copy_button(app):
    result = TranslationResult.success("你好", "tencent", 5)
    dlg = _TranslateDialog("hello", result, parent=None)
    btn_texts = _all_button_texts(dlg)
    assert "复制译文" in btn_texts
    assert "关闭" in btn_texts


def test_auth_failed_dialog_offers_settings_button_when_callback_provided(app):
    called = []
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.AUTH_FAILED),
        parent=None,
        on_open_settings=lambda: called.append(True))
    assert "去设置" in _all_button_texts(dlg)


def test_auth_failed_no_settings_button_when_callback_missing(app):
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.AUTH_FAILED),
        parent=None, on_open_settings=None)
    assert "去设置" not in _all_button_texts(dlg)


def test_quota_exhausted_offers_console_button(app):
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.QUOTA_EXHAUSTED),
        parent=None)
    assert "打开腾讯控制台" in _all_button_texts(dlg)


def test_rate_limited_retry_button_starts_disabled(app):
    from PySide6.QtWidgets import QPushButton
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.RATE_LIMITED, retryable=True),
        parent=None, on_retry=lambda: None)
    retry_btn = next(
        (b for b in dlg.findChildren(QPushButton) if "重试" in b.text()), None)
    assert retry_btn is not None
    assert retry_btn.isEnabled() is False
    # Countdown text: "重试 (5s)" initially; (4s) acceptable if first tick fired
    assert "(5s)" in retry_btn.text() or "(4s)" in retry_btn.text()


def test_network_retryable_shows_immediate_retry(app):
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.NETWORK, retryable=True),
        parent=None, on_retry=lambda: None)
    from PySide6.QtWidgets import QPushButton
    retry_btn = next(
        (b for b in dlg.findChildren(QPushButton) if "重试" in b.text()), None)
    assert retry_btn is not None
    assert retry_btn.isEnabled() is True


def _all_button_texts(dlg):
    from PySide6.QtWidgets import QPushButton
    return [b.text() for b in dlg.findChildren(QPushButton)]
