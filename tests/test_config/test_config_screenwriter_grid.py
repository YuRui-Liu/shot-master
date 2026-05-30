"""prompts_default_grid 配置字段（分镜默认宫格）。"""
from drama_shot_master.config import load_config


def test_default_is_four(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.prompts_default_grid == "4"


def test_roundtrip(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(prompts_default_grid="9")
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.prompts_default_grid == "9"
