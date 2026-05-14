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
