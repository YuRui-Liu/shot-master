"""Tests for DeepLXTranslator."""
from __future__ import annotations

import io
import json
import socket
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from drama_shot_master.providers.deeplx_translator import DeepLXTranslator
from drama_shot_master.providers.translation_base import TranslationErrorCode


_URL = "https://example.test/translate"


def _fake_response(body: bytes):
    class _FakeResp:
        def __enter__(self_inner):
            return io.BytesIO(body)
        def __exit__(self_inner, *exc):
            return False
    return _FakeResp()


def _http_error(code: int):
    return HTTPError(_URL, code, f"http {code}", {}, None)


def test_init_rejects_empty_url():
    with pytest.raises(ValueError):
        DeepLXTranslator(url="")


def test_translate_success_returns_text():
    t = DeepLXTranslator(url=_URL)
    body = json.dumps({"code": 200, "data": "你好"}).encode("utf-8")
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               return_value=_fake_response(body)):
        r = t.translate("hello", "en", "zh")
    assert r.ok is True
    assert r.text == "你好"
    assert r.used_chars == len("hello")
    assert r.provider == "deeplx"


def test_empty_text_returns_invalid_input():
    t = DeepLXTranslator(url=_URL)
    r = t.translate("", "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.INVALID_INPUT


def test_unsupported_target_returns_language_unsupported():
    t = DeepLXTranslator(url=_URL)
    r = t.translate("hello", "en", "xy")
    assert r.error.code == TranslationErrorCode.LANGUAGE_UNSUPPORTED


def test_http_401_maps_to_auth_failed():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=_http_error(401)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.AUTH_FAILED
    assert r.error.retryable is False


def test_http_429_maps_to_rate_limited():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=_http_error(429)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.RATE_LIMITED
    assert r.error.retryable is True


def test_http_500_maps_to_unknown_retryable():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=_http_error(500)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN
    assert r.error.retryable is True


def test_url_error_maps_to_network():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=URLError("connection refused")):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.NETWORK
    assert r.error.retryable is True


def test_socket_timeout_maps_to_network():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=socket.timeout("timed out")):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.NETWORK


def test_non_json_response_maps_to_unknown():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               return_value=_fake_response(b"not json at all")):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN


def test_empty_data_field_maps_to_unknown():
    t = DeepLXTranslator(url=_URL)
    body = json.dumps({"code": 200, "data": ""}).encode("utf-8")
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               return_value=_fake_response(body)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN


def test_health_check_returns_true_when_url_set():
    t = DeepLXTranslator(url=_URL)
    ok, _ = t.health_check()
    assert ok is True
