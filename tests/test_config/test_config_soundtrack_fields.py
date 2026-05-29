"""验证 Sprint 0 新增的 6 个 cfg 字段默认值 + 持久化往返。"""
import json
from pathlib import Path

from drama_shot_master.config import Config, load_config


def test_new_fields_default_values():
    cfg = Config()
    assert cfg.refine_frames_per_shot == 3
    assert cfg.refine_max_segments == 5
    assert cfg.refine_merge_threshold == 0.25
    assert cfg.accent_max_stretch == 0.10
    assert cfg.soundtrack_max_concurrency == 3
    assert cfg.soundtrack_score_weights == {
        "health": 0.5, "headroom": 0.3, "beat": 0.2}


def test_load_config_returns_defaults_when_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=settings_path)
    assert cfg.refine_frames_per_shot == 3
    assert cfg.soundtrack_score_weights["health"] == 0.5


def test_load_config_reads_persisted_values(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "refine_frames_per_shot": 5,
        "refine_max_segments": 7,
        "refine_merge_threshold": 0.40,
        "accent_max_stretch": 0.15,
        "soundtrack_max_concurrency": 6,
        "soundtrack_score_weights": {"health": 0.6, "headroom": 0.2, "beat": 0.2},
    }), encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=settings_path)
    assert cfg.refine_frames_per_shot == 5
    assert cfg.refine_max_segments == 7
    assert cfg.refine_merge_threshold == 0.40
    assert cfg.accent_max_stretch == 0.15
    assert cfg.soundtrack_max_concurrency == 6
    assert cfg.soundtrack_score_weights == {"health": 0.6, "headroom": 0.2, "beat": 0.2}


def test_new_fields_update_settings_roundtrip(tmp_path):
    """完整往返：update_settings 写盘 → load_config 读盘 → 字段保留。"""
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(
        refine_frames_per_shot=5,
        refine_merge_threshold=0.40,
        soundtrack_score_weights={"health": 0.6, "headroom": 0.2, "beat": 0.2},
    )
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.refine_frames_per_shot == 5
    assert abs(cfg2.refine_merge_threshold - 0.40) < 1e-9
    assert cfg2.soundtrack_score_weights == {"health": 0.6, "headroom": 0.2, "beat": 0.2}
