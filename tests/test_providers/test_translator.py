"""Backward-compatibility sentinels for the legacy translate_en_to_zh(text) API.

This file used to host all DeepLX tests; those moved to test_deeplx_translator.py.
What's kept here proves the public no-arg signature still works as the rest of
the codebase expects.
"""
from __future__ import annotations

import os

import pytest

from drama_shot_master.providers.translator import (
    clear_cache, translate_en_to_zh,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("_CURRENT_TRANSLATOR", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_ID", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_KEY", raising=False)
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    clear_cache()
    yield
    clear_cache()


def test_empty_text_returns_none_without_provider():
    assert translate_en_to_zh("") is None
    assert translate_en_to_zh("   ") is None


def test_no_provider_configured_returns_none():
    assert translate_en_to_zh("hello") is None


def test_signature_is_str_to_optional_str():
    """Type stability check: signature shape preserved for legacy callers."""
    import inspect
    sig = inspect.signature(translate_en_to_zh)
    params = list(sig.parameters)
    assert params == ["text"]
