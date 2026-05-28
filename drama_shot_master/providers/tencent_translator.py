"""Tencent Cloud Machine Translation (TMT) provider。

通过官方 tencentcloud-sdk-python-tmt 调 TextTranslate 接口。
SDK 自己处理 TC3-HMAC-SHA256 v3 签名 / 重试 / endpoint resolution。
我们只负责：参数校验 + SDK 异常 → TranslationError 映射 + 网络异常兜底。
"""
from __future__ import annotations

import logging

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception \
    import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.tmt.v20180321 import models, tmt_client

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)

log = logging.getLogger(__name__)

# 腾讯支持的 target 语种（含 source "auto" 已隐含）
_TENCENT_LANGS = {
    "zh", "zh-TW", "en", "ja", "ko", "fr", "es", "it", "de",
    "tr", "ru", "pt", "vi", "id", "th", "ms", "ar", "hi",
}

# 统一码 → 腾讯码（基本一致；显式表加防御性）
_LANG_MAP = {"auto": "auto", "zh": "zh", "en": "en",
             "ja": "ja", "ko": "ko"}


class TencentTranslator(TranslationProvider):
    name = "tencent"

    def __init__(self, secret_id: str, secret_key: str,
                 region: str = "ap-beijing", project_id: int = 0,
                 timeout: float = 10.0):
        if not secret_id or not secret_key:
            raise ValueError("Tencent 凭证不完整")
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile(reqTimeout=int(timeout))
        client_profile = ClientProfile(httpProfile=http_profile)
        self._client = tmt_client.TmtClient(cred, region, client_profile)
        self._project_id = int(project_id or 0)

    def translate(self, text: str, source: str = "auto",
                  target: str = "zh") -> TranslationResult:
        # 1. 入参校验
        if not text or not text.strip():
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message="empty text",
                hint="输入是空的，没什么可翻译的",
                retryable=False, provider=self.name))
        byte_len = len(text.encode("utf-8"))
        if byte_len > 6000:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message=f"text length {byte_len} > 6000 bytes",
                hint="腾讯单次最多 6000 字符（UTF-8 字节），文本太长，分段后再试",
                retryable=False, provider=self.name))
        src = _LANG_MAP.get(source, source)
        tgt = _LANG_MAP.get(target, target)
        if tgt not in _TENCENT_LANGS:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.LANGUAGE_UNSUPPORTED,
                message=f"target {target} not supported",
                hint=f"腾讯翻译不支持目标语种 {target}",
                retryable=False, provider=self.name))

        # 2. 调 SDK
        req = models.TextTranslateRequest()
        req.SourceText = text
        req.Source = src
        req.Target = tgt
        req.ProjectId = self._project_id
        try:
            resp = self._client.TextTranslate(req)
        except TencentCloudSDKException as e:
            err = _map_tencent_error(e)
            self._log_error(err)
            return TranslationResult.fail(err)
        except (OSError, ConnectionError, TimeoutError) as e:
            err = TranslationError(
                code=TranslationErrorCode.NETWORK,
                message=str(e),
                hint="网络问题连不上腾讯，检查网络/代理后重试",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        # 3. 包结果
        used = getattr(resp, "UsedAmount", None)
        used = int(used) if used is not None else len(text)
        log.info("translate ok: tencent %s→%s, %d chars", src, tgt, used)
        return TranslationResult.success(
            text=resp.TargetText, provider=self.name, used_chars=used)

    def health_check(self) -> tuple[bool, str]:
        # 不发请求（避免无谓计费），仅校验凭证字段
        cred = self._client._credential  # noqa: SLF001 — SDK 暴露的内部属性
        if not getattr(cred, "secretId", "") or not getattr(cred, "secretKey", ""):
            return False, "凭证为空"
        return True, "凭证已配置"

    def _log_error(self, err: TranslationError) -> None:
        level = logging.WARNING if err.retryable else logging.ERROR
        log.log(level, "tencent %s: %s", err.code, err.message)


def _map_tencent_error(e: TencentCloudSDKException) -> TranslationError:
    """把腾讯 SDK 异常 code 映射为统一 TranslationError。
    code 详见 https://cloud.tencent.com/document/api/551/15619 错误码段。"""
    code = (getattr(e, "code", "") or "").strip()
    msg = getattr(e, "message", "") or ""
    if code.startswith("AuthFailure"):
        return TranslationError(
            code=TranslationErrorCode.AUTH_FAILED,
            message=f"{code}: {msg}",
            hint="腾讯凭证错误，去设置里检查 SecretId/SecretKey/Region",
            retryable=False, provider="tencent")
    if code in {"FailedOperation.NoFreeAmount",
                "FailedOperation.UserNotRegistered"}:
        return TranslationError(
            code=TranslationErrorCode.QUOTA_EXHAUSTED,
            message=f"{code}: {msg}",
            hint="腾讯翻译额度用完了，去控制台充值或开通付费服务",
            retryable=False, provider="tencent")
    if code == "FailedOperation.ServiceIsolate":
        return TranslationError(
            code=TranslationErrorCode.SERVICE_DISABLED,
            message=f"{code}: {msg}",
            hint="腾讯账号下 TMT 服务未开通或已停用，去控制台开通",
            retryable=False, provider="tencent")
    if code.startswith("RequestLimitExceeded"):
        return TranslationError(
            code=TranslationErrorCode.RATE_LIMITED,
            message=f"{code}: {msg}",
            hint="请求太快了（5 QPS 上限），稍等几秒再试",
            retryable=True, provider="tencent")
    if (code.startswith("InvalidParameter")
            or code.startswith("UnsupportedOperation")):
        return TranslationError(
            code=TranslationErrorCode.INVALID_INPUT,
            message=f"{code}: {msg}",
            hint=f"腾讯说参数有问题：{msg}",
            retryable=False, provider="tencent")
    return TranslationError(
        code=TranslationErrorCode.UNKNOWN,
        message=f"{code}: {msg}",
        hint=f"腾讯返回未知错误：{code}，详情查日志",
        retryable=True, provider="tencent")
