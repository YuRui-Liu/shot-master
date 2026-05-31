"""翻译 facade：保留旧 translate_en_to_zh 签名；暴露新 translate / factory / 缓存控制。

配置来源：调用方传 cfg 则用 cfg 字段；不传则全走 os.environ。
config.py 启动时与 settings UI save_to() 都把字段同步到 os.environ，
让旧 translate_en_to_zh(text) 无参签名仍能找到当前 provider。

进程内 LRU(64) 缓存按 (provider_name, source, target, sha256(text)[:16]) 去重；
只缓存 ok=True 的结果，失败不进缓存。
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections import OrderedDict

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)

log = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────────────────

def translate_en_to_zh(text: str) -> str | None:
    """旧签名保留；委派到当前 provider，失败返回 None。

    cfg 由 os.environ 隐式提供（config.py 启动时回写）。
    新代码应改用 translate(text, source, target, cfg=...) 拿 TranslationResult。
    """
    result = translate(text, source="en", target="zh")
    return result.text if result.ok else None


def translate(text: str, source: str = "auto",
              target: str = "zh", cfg=None) -> TranslationResult:
    """统一翻译入口；走 LRU 缓存。

    cfg=None 时全从 os.environ 取（_CURRENT_TRANSLATOR / TENCENTCLOUD_*）。
    """
    provider = build_translation_provider(cfg)
    if provider is None:
        return TranslationResult.fail(TranslationError(
            code=TranslationErrorCode.AUTH_FAILED,
            message="no provider configured",
            hint="还没配翻译服务，去设置 → 翻译 选 provider 并填凭证",
            retryable=False, provider="none"))
    key = _cache_key(provider.name, source, target, text)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    result = provider.translate(text, source, target)
    if result.ok:
        _cache_set(key, result)
    return result


# ── Factory ────────────────────────────────────────────────────────────────

def build_translation_provider(cfg=None) -> TranslationProvider | None:
    """据 cfg.current_translator 或 os.environ['_CURRENT_TRANSLATOR'] 构造 provider；
    凭证不全返回 None。"""
    def _get(field: str, env_key: str, default: str = "") -> str:
        if cfg is not None:
            val = getattr(cfg, field, "") or ""
            if val:
                return val
        return os.environ.get(env_key, default)

    name = _get("current_translator", "_CURRENT_TRANSLATOR", "tencent").lower()
    if not name or name in ("none", "disabled"):
        return None
    if name == "tencent":
        sid = _get("tencent_translator_secret_id", "TENCENTCLOUD_SECRET_ID")
        skey = _get("tencent_translator_secret_key", "TENCENTCLOUD_SECRET_KEY")
        region = _get("tencent_translator_region",
                       "TENCENTCLOUD_REGION", "ap-beijing")
        if not sid or not skey:
            return None
        from drama_shot_master.providers.tencent_translator \
            import TencentTranslator
        project_id = 0
        if cfg is not None:
            project_id = int(
                getattr(cfg, "tencent_translator_project_id", 0) or 0)
        return TencentTranslator(
            sid, skey, region=region, project_id=project_id)
    if name == "deeplx":
        url = _get("deeplx_url", "DEEPLX_URL")
        if not url:
            return None
        from drama_shot_master.providers.deeplx_translator \
            import DeepLXTranslator
        return DeepLXTranslator(url)
    log.warning("Unknown translator provider: %s", name)
    return None


# ── LRU (thread-safe) ──────────────────────────────────────────────────────

_LRU_MAX = 64
_lru: "OrderedDict[tuple, TranslationResult]" = OrderedDict()
_lru_lock = threading.Lock()


def _cache_key(provider_name: str, source: str, target: str,
               text: str) -> tuple:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return (provider_name, source, target, digest)


def _cache_get(key: tuple) -> TranslationResult | None:
    with _lru_lock:
        if key in _lru:
            _lru.move_to_end(key)
            return _lru[key]
    return None


def _cache_set(key: tuple, value: TranslationResult) -> None:
    with _lru_lock:
        _lru[key] = value
        _lru.move_to_end(key)
        while len(_lru) > _LRU_MAX:
            _lru.popitem(last=False)


def clear_cache() -> None:
    """provider 切换 / settings 改了凭证 时主动清。"""
    with _lru_lock:
        _lru.clear()


def get_cache_stats() -> dict:
    """调试 / 测试用。"""
    with _lru_lock:
        return {"size": len(_lru), "max": _LRU_MAX}
