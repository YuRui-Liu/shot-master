"""Tencent translator 字段读写 + 迁移逻辑测试。"""
from drama_shot_master.config import load_config


def test_save_load_tencent_translator_fields(tmp_path, monkeypatch):
    for k in ("_CURRENT_TRANSLATOR", "TENCENTCLOUD_SECRET_ID",
              "TENCENTCLOUD_SECRET_KEY", "TENCENTCLOUD_REGION", "DEEPLX_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    cfg.update_settings(
        current_translator="tencent",
        tencent_translator_secret_id="sid-x",
        tencent_translator_secret_key="skey-y",
        tencent_translator_region="ap-shanghai",
        tencent_translator_project_id=42,
    )
    cfg2 = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg2.current_translator == "tencent"
    assert cfg2.tencent_translator_secret_id == "sid-x"
    assert cfg2.tencent_translator_secret_key == "skey-y"
    assert cfg2.tencent_translator_region == "ap-shanghai"
    assert cfg2.tencent_translator_project_id == 42


def test_tencent_env_overlay_fills_missing_secret_id(tmp_path, monkeypatch):
    for k in ("_CURRENT_TRANSLATOR", "TENCENTCLOUD_SECRET_ID",
              "TENCENTCLOUD_SECRET_KEY", "TENCENTCLOUD_REGION", "DEEPLX_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "env-sid")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "env-skey")
    monkeypatch.setenv("TENCENTCLOUD_REGION", "ap-guangzhou")
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.tencent_translator_secret_id == "env-sid"
    assert cfg.tencent_translator_secret_key == "env-skey"
    assert cfg.tencent_translator_region == "ap-guangzhou"


def test_post_load_migrate_keeps_deeplx_when_only_deeplx_configured(
        tmp_path, monkeypatch):
    """旧用户仅配过 deeplx_url → current_translator 自动设为 deeplx。"""
    import json
    for k in ("_CURRENT_TRANSLATOR", "TENCENTCLOUD_SECRET_ID",
              "TENCENTCLOUD_SECRET_KEY", "TENCENTCLOUD_REGION", "DEEPLX_URL"):
        monkeypatch.delenv(k, raising=False)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "deeplx_url": "http://localhost:1188/translate",
    }), encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=settings_path)
    assert cfg.current_translator == "deeplx"
    assert cfg.deeplx_url == "http://localhost:1188/translate"


def test_post_load_migrate_defaults_to_tencent_when_empty(tmp_path, monkeypatch):
    for k in ("_CURRENT_TRANSLATOR", "TENCENTCLOUD_SECRET_ID",
              "TENCENTCLOUD_SECRET_KEY", "TENCENTCLOUD_REGION", "DEEPLX_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.current_translator == "tencent"
