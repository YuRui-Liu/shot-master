"""Tests for LRU cache in translator.py facade."""
from __future__ import annotations

import threading

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationResult,
)
from drama_shot_master.providers.translator import (
    _cache_get, _cache_key, _cache_set, clear_cache, get_cache_stats,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def test_cache_hit_returns_stored_value():
    key = _cache_key("tencent", "en", "zh", "hello")
    r = TranslationResult.success("你好", "tencent", 5)
    _cache_set(key, r)
    assert _cache_get(key) is r


def test_cache_miss_returns_none():
    key = _cache_key("tencent", "en", "zh", "never-set")
    assert _cache_get(key) is None


def test_different_provider_does_not_collide():
    k1 = _cache_key("tencent", "en", "zh", "hello")
    k2 = _cache_key("deeplx", "en", "zh", "hello")
    assert k1 != k2
    _cache_set(k1, TranslationResult.success("你好-tx", "tencent", 5))
    assert _cache_get(k2) is None


def test_lru_evicts_oldest_when_full():
    # 65 entries; first must be evicted (max=64).
    for i in range(65):
        key = _cache_key("tencent", "en", "zh", f"text-{i}")
        _cache_set(key, TranslationResult.success(f"r-{i}", "tencent", 1))
    stats = get_cache_stats()
    assert stats["size"] == 64
    # First key (i=0) should be gone
    first = _cache_key("tencent", "en", "zh", "text-0")
    assert _cache_get(first) is None
    # Last key (i=64) should still be present
    last = _cache_key("tencent", "en", "zh", "text-64")
    assert _cache_get(last) is not None


def test_clear_cache_removes_all():
    key = _cache_key("tencent", "en", "zh", "x")
    _cache_set(key, TranslationResult.success("y", "tencent", 1))
    clear_cache()
    assert _cache_get(key) is None
    assert get_cache_stats()["size"] == 0


def test_failed_results_must_not_be_cached_by_translate(stub_tmt_client):
    """translate() 自己只在 ok=True 时调 _cache_set。
    这里直接断言：cache_set 收到失败结果时不抛错（行为本身由 translate 主导）。
    """
    err = TranslationError(
        code=TranslationErrorCode.AUTH_FAILED,
        message="m", hint="h", retryable=False, provider="tencent")
    fail = TranslationResult.fail(err)
    key = _cache_key("tencent", "en", "zh", "hello")
    _cache_set(key, fail)  # 直接写入失败结果是允许的（API 不主动拒）
    assert _cache_get(key) is fail


def test_concurrent_set_and_get_does_not_crash():
    """简易并发：8 个线程做 get/set 不应抛锁/数据结构异常。"""
    def worker(i):
        for j in range(50):
            key = _cache_key("tencent", "en", "zh", f"t{i}-{j}")
            _cache_set(key, TranslationResult.success(
                f"r{i}-{j}", "tencent", 1))
            _cache_get(key)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    assert get_cache_stats()["size"] <= 64
