"""Tests for translation_base ABC + dataclasses."""
from __future__ import annotations

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)


def test_result_success_factory():
    r = TranslationResult.success("你好", "tencent", used_chars=5)
    assert r.ok is True
    assert r.text == "你好"
    assert r.error is None
    assert r.provider == "tencent"
    assert r.used_chars == 5


def test_result_fail_factory_propagates_provider():
    err = TranslationError(
        code=TranslationErrorCode.AUTH_FAILED,
        message="bad cred", hint="去设置",
        retryable=False, provider="deeplx")
    r = TranslationResult.fail(err)
    assert r.ok is False
    assert r.text is None
    assert r.error is err
    assert r.provider == "deeplx"
    assert r.used_chars == 0


def test_error_codes_are_unique_strings():
    codes = {
        TranslationErrorCode.AUTH_FAILED,
        TranslationErrorCode.QUOTA_EXHAUSTED,
        TranslationErrorCode.SERVICE_DISABLED,
        TranslationErrorCode.RATE_LIMITED,
        TranslationErrorCode.INVALID_INPUT,
        TranslationErrorCode.LANGUAGE_UNSUPPORTED,
        TranslationErrorCode.NETWORK,
        TranslationErrorCode.UNKNOWN,
    }
    assert len(codes) == 8
    assert all(isinstance(c, str) and c == c.upper() for c in codes)


def test_result_is_frozen():
    r = TranslationResult.success("hi", "x")
    with pytest.raises((AttributeError, Exception)):
        r.ok = False  # type: ignore[misc]


def test_error_is_frozen():
    err = TranslationError(
        code="X", message="m", hint="h", retryable=True, provider="p")
    with pytest.raises((AttributeError, Exception)):
        err.code = "Y"  # type: ignore[misc]


def test_subclass_must_implement_translate_and_health_check():
    class Incomplete(TranslationProvider):
        name = "incomplete"
    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]
