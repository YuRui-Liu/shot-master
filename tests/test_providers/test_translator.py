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
