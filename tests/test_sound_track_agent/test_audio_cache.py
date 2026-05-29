"""audio_cache (改名 from bgm_cache): BGM 键签名不变 + 新增 sfx_cache_key。"""
from sound_track_agent.audio_cache import (
    cache_key, sfx_cache_key, cache_path, lookup, store,
)


def test_bgm_cache_key_signature_unchanged():
    """旧 BGM key 签名/hash 不变（保证现有 cache 文件继续命中）。"""
    k1 = cache_key("wf-x", "tags", 120, 30.0, 42)
    k2 = cache_key("wf-x", "tags", 120, 30.0, 42)
    assert k1 == k2
    assert isinstance(k1, str) and len(k1) >= 16


def test_sfx_cache_key_returns_string():
    k = sfx_cache_key("wf-sfx", "门吱呀", 3.0, 1)
    assert isinstance(k, str) and len(k) >= 16


def test_sfx_cache_key_different_inputs_different_keys():
    a = sfx_cache_key("wf", "p1", 3.0, 1)
    b = sfx_cache_key("wf", "p2", 3.0, 1)
    c = sfx_cache_key("wf", "p1", 4.0, 1)
    d = sfx_cache_key("wf", "p1", 3.0, 2)
    assert len({a, b, c, d}) == 4


def test_sfx_and_bgm_keys_dont_collide():
    """同 workflow_id + 同 seed + 共 'tags=门吱呀' / 'prompt=门吱呀' 不能撞键。"""
    bgm = cache_key("wf", "门吱呀", 120, 3.0, 1)
    sfx = sfx_cache_key("wf", "门吱呀", 3.0, 1)
    assert bgm != sfx


def test_lookup_store_unchanged(tmp_path):
    src = tmp_path / "a.mp3"; src.write_bytes(b"audio")
    dst = store(tmp_path, "k1", src)
    assert dst.exists()
    assert lookup(tmp_path, "k1") == dst
    assert lookup(tmp_path, "missing") is None
