import json
from pathlib import Path
import pytest
from app.config import Config, load_config


def test_load_config_from_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEFAULT_PROVIDER=anthropic\n"
        "DEFAULT_MODEL=claude-opus-4\n"
        "GEMINI_API_KEY=g-key\n"
        "OPENAI_API_KEY=o-key\n"
        "OPENAI_BASE_URL=https://x.example/v1\n"
        "HOST=0.0.0.0\n"
        "PORT=9000\n"
    )
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.default_provider == "anthropic"
    assert cfg.default_model == "claude-opus-4"
    assert cfg.api_keys["gemini"] == "g-key"
    assert cfg.api_keys["openai"] == "o-key"
    assert cfg.base_urls["openai"] == "https://x.example/v1"
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9000


def test_settings_json_overrides_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\n")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "current_provider": "anthropic",
        "current_model": "claude-opus-4",
    }))
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.current_provider == "anthropic"
    assert cfg.current_model == "claude-opus-4"
    # default_* still from .env
    assert cfg.default_provider == "gemini"


def test_save_settings_persists_changes(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=gemini\n")
    settings_file = tmp_path / "settings.json"
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(current_provider="anthropic", current_model="claude-opus-4")
    assert settings_file.exists()
    data = json.loads(settings_file.read_text())
    assert data["current_provider"] == "anthropic"
    assert data["current_model"] == "claude-opus-4"


def test_missing_env_uses_defaults(tmp_path):
    cfg = load_config(env_path=tmp_path / "nonexistent.env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.default_provider == "doubao"
    assert cfg.default_model.startswith("doubao-")
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 7866


def test_last_dirs_default_none(tmp_path):
    cfg = load_config(env_path=tmp_path / "no.env",
                      settings_path=tmp_path / "s.json")
    assert cfg.last_input_dir is None
    assert cfg.last_output_dir is None


def test_last_dirs_loaded_from_settings(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    import json as _j
    sj.write_text(_j.dumps({
        "current_provider": "doubao",
        "current_model": "doubao-seed-2-0-pro-260215",
        "last_input_dir": "/data/imgs",
        "last_output_dir": "/data/out",
    }))
    cfg = load_config(env_path=env_file, settings_path=sj)
    assert cfg.last_input_dir == "/data/imgs"
    assert cfg.last_output_dir == "/data/out"


def test_update_settings_persists_last_dirs(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env_file, settings_path=sj)
    cfg.update_settings(last_input_dir="/x/in", last_output_dir="/x/out")
    import json as _j
    data = _j.loads(sj.read_text())
    assert data["last_input_dir"] == "/x/in"
    assert data["last_output_dir"] == "/x/out"
    cfg2 = load_config(env_path=env_file, settings_path=sj)
    assert cfg2.last_input_dir == "/x/in"
    assert cfg2.last_output_dir == "/x/out"


def test_config_default_comfyui_url(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.comfyui_url == "http://127.0.0.1:8188"


def test_config_default_split_resample_defaults(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    d = cfg.split_resample_defaults
    assert d["enabled"] is False
    assert d["aspect_w"] == 1 and d["aspect_h"] == 1
    assert d["long_edge"] == 2048
    assert d["algorithm"] == "lanczos"
    assert d["ai_model"] == ""


def test_config_loads_comfyui_url_from_settings(tmp_path):
    sp = tmp_path / "settings.json"
    sp.write_text('{"comfyui_url": "http://other:1234"}', encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.comfyui_url == "http://other:1234"


def test_config_loads_split_resample_defaults_from_settings(tmp_path):
    sp = tmp_path / "settings.json"
    sp.write_text(
        '{"split_resample_defaults": {"enabled": true, "long_edge": 1024, '
        '"aspect_w": 16, "aspect_h": 9, "algorithm": "ai", '
        '"ai_model": "x.pth"}}',
        encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.split_resample_defaults["enabled"] is True
    assert cfg.split_resample_defaults["long_edge"] == 1024
    assert cfg.split_resample_defaults["ai_model"] == "x.pth"


def test_config_update_settings_persists_comfyui_and_resample(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(
        comfyui_url="http://x:9999",
        split_resample_defaults={
            "enabled": True, "aspect_w": 1, "aspect_h": 1,
            "long_edge": 2048, "algorithm": "lanczos", "ai_model": ""})
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["comfyui_url"] == "http://x:9999"
    assert data["split_resample_defaults"]["enabled"] is True
