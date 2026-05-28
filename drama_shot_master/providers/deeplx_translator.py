"""DeepLX 翻译 provider（自部署或公共 DeepLX 实例）。

从原 drama_shot_master/providers/translator.py 拆出来，逻辑基本不变；
区别是返回 TranslationResult 而非 str | None，并把 HTTP/网络错误映射为
统一 TranslationError code。
"""
from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)

log = logging.getLogger(__name__)

# DeepLX 的 target_lang 用大写短码
_DEEPLX_TARGET_MAP = {"zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO"}

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "drama-shot-master/translator",
}


class DeepLXTranslator(TranslationProvider):
    name = "deeplx"

    def __init__(self, url: str, timeout: float = 3.0):
        if not url or not url.strip():
            raise ValueError("DeepLX URL 为空")
        self._url = url.strip()
        self._timeout = float(timeout)

    def translate(self, text: str, source: str = "auto",
                  target: str = "zh") -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message="empty text", hint="输入是空的",
                retryable=False, provider=self.name))
        tgt = _DEEPLX_TARGET_MAP.get(target)
        if tgt is None:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.LANGUAGE_UNSUPPORTED,
                message=f"target {target} unsupported",
                hint=f"DeepLX 不支持 {target}",
                retryable=False, provider=self.name))

        payload = json.dumps({"text": text, "source_lang": "auto",
                              "target_lang": tgt}).encode("utf-8")
        req = Request(self._url, data=payload, method="POST",
                      headers=_HEADERS)
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except HTTPError as e:
            err = self._map_http_error(e)
            self._log_error(err)
            return TranslationResult.fail(err)
        except (URLError, OSError) as e:
            err = TranslationError(
                code=TranslationErrorCode.NETWORK,
                message=str(e),
                hint=f"连不上 DeepLX（{self._url}），检查网络/部署",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            err = TranslationError(
                code=TranslationErrorCode.UNKNOWN,
                message="bad JSON",
                hint="DeepLX 返回非 JSON",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        data = obj.get("data") if isinstance(obj, dict) else None
        if not isinstance(data, str) or not data:
            err = TranslationError(
                code=TranslationErrorCode.UNKNOWN,
                message=f"missing data in {obj!r}",
                hint="DeepLX 返回格式异常",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        log.info("translate ok: deeplx auto→%s, %d chars", target, len(text))
        return TranslationResult.success(
            text=data, provider=self.name, used_chars=len(text))

    def health_check(self) -> tuple[bool, str]:
        return bool(self._url), self._url or "URL 未配置"

    def _map_http_error(self, e: HTTPError) -> TranslationError:
        if e.code in (401, 403):
            return TranslationError(
                code=TranslationErrorCode.AUTH_FAILED,
                message=f"HTTP {e.code}",
                hint="DeepLX 拒绝访问，检查 URL 或鉴权",
                retryable=False, provider=self.name)
        if e.code == 429:
            return TranslationError(
                code=TranslationErrorCode.RATE_LIMITED,
                message="HTTP 429",
                hint="DeepLX 频控触顶，稍等再试",
                retryable=True, provider=self.name)
        return TranslationError(
            code=TranslationErrorCode.UNKNOWN,
            message=f"HTTP {e.code}",
            hint=f"DeepLX 返回 HTTP {e.code}",
            retryable=True, provider=self.name)

    def _log_error(self, err: TranslationError) -> None:
        level = logging.WARNING if err.retryable else logging.ERROR
        log.log(level, "deeplx %s: %s", err.code, err.message)
