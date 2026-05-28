from sound_track_agent import bgm_cache


def test_cache_key_deterministic_and_seed_sensitive():
    k1 = bgm_cache.cache_key("wf", "tags", 120, 15.0, 1)
    k2 = bgm_cache.cache_key("wf", "tags", 120, 15.0, 1)
    k3 = bgm_cache.cache_key("wf", "tags", 120, 15.0, 2)
    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 16


def test_cache_key_duration_precision_stable():
    # 15.0 与 15.0004 在 .3f 下不同；15.0 与 15.0001 相同
    assert bgm_cache.cache_key("wf", "t", 120, 15.0, 1) == \
           bgm_cache.cache_key("wf", "t", 120, 15.0001, 1)


def test_lookup_miss_then_store_then_hit(tmp_path):
    cache_dir = tmp_path / "cache"
    key = bgm_cache.cache_key("wf", "t", 120, 15.0, 1)
    assert bgm_cache.lookup(cache_dir, key) is None
    src = tmp_path / "dl.mp3"
    src.write_bytes(b"AUDIO")
    dest = bgm_cache.store(cache_dir, key, src)
    assert dest.exists() and dest.read_bytes() == b"AUDIO"
    assert not src.exists()                      # store 是移动语义
    assert bgm_cache.lookup(cache_dir, key) == dest
