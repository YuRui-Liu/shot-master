"""Tests for translator.py facade: build_translation_provider + translate."""
from __future__ import annotations

import types
from unittest.mock import patch

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationErrorCode, TranslationResult,
)


def _cfg(**kwargs):
    """Build a minimal cfg-like object."""
    defaults = dict(
        current_translator="",
        tencent_translator_secret_id="",
        tencent_translator_secret_key="",
        tencent_translator_region="ap-beijing",
        tencent_translator_project_id=0,
        deeplx_url="",
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_build_returns_tencent_when_creds_present(stub_tmt_client):
    from drama_shot_master.providers.translator import build_translation_provider
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    cfg = _cfg(current_translator="tencent",
               tencent_translator_secret_id="sid",
               tencent_translator_secret_key="skey")
    p = build_translation_provider(cfg)
    assert isinstance(p, TencentTranslator)


def test_build_returns_none_when_tencent_creds_missing():
    from drama_shot_master.providers.translator import build_translation_provider
    cfg = _cfg(current_translator="tencent",
               tencent_translator_secret_id="",
               tencent_translator_secret_key="")
    assert build_translation_provider(cfg) is None


def test_build_returns_deeplx_when_url_set():
    from drama_shot_master.providers.translator import build_translation_provider
    from drama_shot_master.providers.deeplx_translator import DeepLXTranslator
    cfg = _cfg(current_translator="deeplx",
               deeplx_url="http://example/translate")
    p = build_translation_provider(cfg)
    assert isinstance(p, DeepLXTranslator)


def test_build_returns_none_when_deeplx_url_missing():
    from drama_shot_master.providers.translator import build_translation_provider
    cfg = _cfg(current_translator="deeplx", deeplx_url="")
    assert build_translation_provider(cfg) is None


def test_build_returns_none_for_unknown_provider():
    from drama_shot_master.providers.translator import build_translation_provider
    cfg = _cfg(current_translator="bogus_xyz",
               tencent_translator_secret_id="x",
               tencent_translator_secret_key="y")
    assert build_translation_provider(cfg) is None


def test_build_uses_env_when_cfg_field_empty(monkeypatch, stub_tmt_client):
    from drama_shot_master.providers.translator import build_translation_provider
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    monkeypatch.setenv("_CURRENT_TRANSLATOR", "tencent")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "env-sid")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "env-skey")
    p = build_translation_provider(cfg=None)
    assert isinstance(p, TencentTranslator)


def test_translate_returns_fail_when_no_provider_configured():
    from drama_shot_master.providers.translator import translate
    cfg = _cfg()  # All empty
    r = translate("hello", "en", "zh", cfg=cfg)
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.AUTH_FAILED
    assert "设置" in r.error.hint


def test_translate_en_to_zh_returns_str_on_success(stub_tmt_client):
    from drama_shot_master.providers.translator import (
        translate_en_to_zh, clear_cache,
    )
    clear_cache()
    stub_tmt_client.TextTranslate = lambda self, req: type("R", (), {
        "TargetText": "你好", "UsedAmount": 5})()
    import os
    os.environ["_CURRENT_TRANSLATOR"] = "tencent"
    os.environ["TENCENTCLOUD_SECRET_ID"] = "sid"
    os.environ["TENCENTCLOUD_SECRET_KEY"] = "skey"
    try:
        assert translate_en_to_zh("hello") == "你好"
    finally:
        os.environ.pop("_CURRENT_TRANSLATOR", None)
        os.environ.pop("TENCENTCLOUD_SECRET_ID", None)
        os.environ.pop("TENCENTCLOUD_SECRET_KEY", None)


def test_translate_en_to_zh_returns_none_when_no_provider(monkeypatch):
    from drama_shot_master.providers.translator import translate_en_to_zh
    monkeypatch.delenv("_CURRENT_TRANSLATOR", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_ID", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_KEY", raising=False)
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    assert translate_en_to_zh("hello") is None
