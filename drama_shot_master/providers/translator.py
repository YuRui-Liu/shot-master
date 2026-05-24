"""DeepLX 翻译客户端：英文 prompt → 中文预览。

设计原则：
- 任何异常（网络、JSON、缺字段）都返回 None，调用方负责回退。
- 不抛错、不打 stacktrace，只 logging.info/warning。
- 无 Qt 依赖，可单测、可在 CLI 中复用。
"""
from __future__ import annotations

import json
import logging
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_logger = logging.getLogger(__name__)

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "drama-shot-master/translator",
}


def translate_en_to_zh(text: str, *, timeout: float = 3.0) -> str | None:
    """POST 文本到 DEEPLX_URL，返回中译；任何失败返回 None。

    成功响应形如：{"code": 200, "data": "...", ...}
    """
    if not text or not text.strip():
        return None

    url = os.environ.get("DEEPLX_URL", "").strip()
    if not url:
        _logger.warning("DEEPLX_URL not set; skip translation")
        return None

    payload = json.dumps({
        "text": text,
        "source_lang": "auto",
        "target_lang": "ZH",
    }).encode("utf-8")

    req = Request(url, data=payload, headers=_HEADERS, method="POST")

    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (HTTPError, URLError, socket.timeout, OSError) as exc:
        _logger.info("DeepLX request failed: %s", exc)
        return None

    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _logger.info("DeepLX bad response body: %s", exc)
        return None

    data = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(data, str) or not data:
        _logger.info("DeepLX missing/invalid data field: %r", obj)
        return None
    return data
