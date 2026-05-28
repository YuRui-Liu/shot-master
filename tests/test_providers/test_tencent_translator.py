"""Tests for TencentTranslator."""
from __future__ import annotations

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationErrorCode,
)


def _make_translator(stub_tmt_client, **kwargs):
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    defaults = dict(secret_id="fake_id", secret_key="fake_key",
                    region="ap-beijing", project_id=0)
    defaults.update(kwargs)
    return TencentTranslator(**defaults)


def _fake_response(target_text="你好", used_amount=5,
                   source="en", target="zh", request_id="fake-req"):
    """Build a TextTranslateResponse-shaped object."""
    return type("R", (), {
        "TargetText": target_text, "UsedAmount": used_amount,
        "Source": source, "Target": target, "RequestId": request_id})()


def _raise(exc):
    """Return a method that raises the given exception."""
    def _method(self, req):
        raise exc
    return _method


def test_init_rejects_empty_secret_id(stub_tmt_client):
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    with pytest.raises(ValueError, match="凭证"):
        TencentTranslator(secret_id="", secret_key="x")


def test_translate_success(stub_tmt_client):
    stub_tmt_client.TextTranslate = lambda self, req: _fake_response("你好", 5)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.ok is True
    assert r.text == "你好"
    assert r.used_chars == 5
    assert r.provider == "tencent"


def test_translate_empty_text_returns_invalid_input(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    r = t.translate("", "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.INVALID_INPUT
    assert r.error.retryable is False


def test_translate_oversize_text_returns_invalid_input(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    text = "a" * 6001  # 6001 UTF-8 bytes (ASCII), exceeds 6000-byte limit
    r = t.translate(text, "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.INVALID_INPUT
    assert "6000" in r.error.hint


def test_translate_unsupported_target_returns_language_unsupported(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "xx")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.LANGUAGE_UNSUPPORTED


def test_translate_auth_failure_signature_failure(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="AuthFailure.SignatureFailure",
        message="credentials invalid", requestId="r1")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.AUTH_FAILED
    assert r.error.retryable is False


def test_translate_auth_failure_signature_expire_also_maps(stub_tmt_client):
    """Prefix match: any AuthFailure.* → AUTH_FAILED."""
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="AuthFailure.SignatureExpire",
        message="signature expired", requestId="r2")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.AUTH_FAILED


def test_translate_no_free_amount_maps_to_quota(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="FailedOperation.NoFreeAmount",
        message="quota exhausted", requestId="r3")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.QUOTA_EXHAUSTED


def test_translate_service_isolate_maps_to_service_disabled(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="FailedOperation.ServiceIsolate",
        message="service disabled", requestId="r4")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.SERVICE_DISABLED


def test_translate_rate_limit_is_retryable(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="RequestLimitExceeded",
        message="qps limit", requestId="r5")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.RATE_LIMITED
    assert r.error.retryable is True


def test_translate_invalid_parameter_maps_to_invalid_input(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="InvalidParameter.SomeField",
        message="bad field", requestId="r6")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.INVALID_INPUT


def test_translate_unknown_code_is_retryable(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="SomethingNew.WeDoNotKnow",
        message="???", requestId="r7")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN
    assert r.error.retryable is True


def test_translate_network_error_maps_to_network(stub_tmt_client):
    stub_tmt_client.TextTranslate = _raise(OSError("connection refused"))
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.NETWORK
    assert r.error.retryable is True


def test_health_check_with_credentials(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    ok, _msg = t.health_check()
    assert ok is True
