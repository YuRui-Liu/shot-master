import json
from pathlib import Path
import pytest
from drama_shot_master.config import Config, load_config


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


# ---------- RunningHub 字段持久化 ----------

def test_config_default_runninghub_fields(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.runninghub_api_key == ""
    assert cfg.runninghub_workflow_id == ""
    assert cfg.runninghub_base_url == "https://www.runninghub.cn"
    assert cfg.runninghub_template_path == ""
    assert cfg.video_output_dir == ""


def test_config_loads_runninghub_api_key_from_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RUNNINGHUB_API_KEY=k-from-env\n", encoding="utf-8")
    cfg = load_config(env_path=env_file,
                       settings_path=tmp_path / "settings.json")
    assert cfg.runninghub_api_key == "k-from-env"


def test_config_loads_runninghub_base_url_from_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RUNNINGHUB_BASE_URL=https://other.x\n",
                          encoding="utf-8")
    cfg = load_config(env_path=env_file,
                       settings_path=tmp_path / "settings.json")
    assert cfg.runninghub_base_url == "https://other.x"


def test_config_settings_overrides_env_for_runninghub_api_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RUNNINGHUB_API_KEY=from-env\n", encoding="utf-8")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        '{"runninghub_api_key": "from-settings"}', encoding="utf-8")
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.runninghub_api_key == "from-settings"


def test_config_settings_loads_all_runninghub_fields(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        '{"runninghub_workflow_id": "wf-1",'
        ' "runninghub_template_path": "/x/tpl.json",'
        ' "video_output_dir": "/x/out"}',
        encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=settings_file)
    assert cfg.runninghub_workflow_id == "wf-1"
    assert cfg.runninghub_template_path == "/x/tpl.json"
    assert cfg.video_output_dir == "/x/out"


def test_config_update_settings_persists_runninghub_fields(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(
        runninghub_api_key="new-key",
        video_output_dir="/x/v",
    )
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["runninghub_api_key"] == "new-key"
    assert data["video_output_dir"] == "/x/v"


# ---------- 老 settings.json GBK 编码兼容 ----------

def test_load_config_falls_back_to_locale_on_non_utf8_settings(tmp_path):
    """Windows 上历史 settings.json 可能是 GBK 编码（含中文路径/值）。
    UTF-8 严格读失败时应回退 locale 默认读取，不应抛 UnicodeDecodeError。"""
    sp = tmp_path / "settings.json"
    # 用 GBK 编码写入含中文字符的合法 JSON
    payload = '{"runninghub_workflow_id": "测试工作流-中文"}'
    sp.write_bytes(payload.encode("gbk"))
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    # 在 GBK locale 系统（Win cp936）上能读出来；在 UTF-8 locale 系统上
    # locale fallback 会失败但被外层 except 吞掉，cfg 走默认空串。
    # 两种情况都不应抛 UnicodeDecodeError。
    assert cfg.runninghub_workflow_id in ("测试工作流-中文", "")


def test_load_config_swallows_unicode_decode_error_completely(tmp_path):
    """彻底乱码的 settings.json 应该被静默忽略，不抛错。"""
    sp = tmp_path / "settings.json"
    sp.write_bytes(b"\xff\xfe\xbb\xbb\xaa not valid in any encoding")
    # 不应抛 UnicodeDecodeError；应该走默认值
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.runninghub_api_key == ""    # 默认空值


def test_update_settings_writes_utf8(tmp_path):
    """update_settings 落盘应该用 UTF-8（保证下次读取一致）。"""
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(runninghub_workflow_id="中文工作流名")
    raw = sp.read_bytes()
    # 必须能用 utf-8 解码；不应被 ensure_ascii 转义
    text = raw.decode("utf-8")
    assert "中文工作流名" in text


# ---------- video_timeline_cache ----------

def test_config_default_video_timeline_cache(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.video_timeline_cache == {}


def test_config_loads_video_timeline_cache(tmp_path):
    sp = tmp_path / "settings.json"
    sp.write_text(
        '{"video_timeline_cache": {"frame_rate": 30, "segments": []}}',
        encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.video_timeline_cache == {"frame_rate": 30, "segments": []}


def test_config_update_settings_persists_video_timeline_cache(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(
        video_timeline_cache={"frame_rate": 30, "filename_prefix": "v1"})
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["video_timeline_cache"]["frame_rate"] == 30
    assert data["video_timeline_cache"]["filename_prefix"] == "v1"


def test_config_loads_invalid_video_timeline_cache_falls_back(tmp_path):
    sp = tmp_path / "settings.json"
    # value 是 list 而非 dict —— 应被静默忽略走默认
    sp.write_text('{"video_timeline_cache": ["bad"]}', encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.video_timeline_cache == {}


# ---------- F-1: last_active_function ----------

def test_config_default_last_active_function(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.last_active_function == "inference"


def test_config_loads_last_active_function_from_settings(tmp_path):
    sp = tmp_path / "settings.json"
    sp.write_text(
        '{"last_active_function": "video_gen"}', encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.last_active_function == "video_gen"


def test_config_update_settings_persists_last_active_function(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(last_active_function="video_gen")
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["last_active_function"] == "video_gen"


# ---------- 翻译 + refine provider 字段 ----------

def test_save_load_refine_and_deeplx_fields(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(
        deeplx_url="http://localhost:1188/translate",
        refine_base_url="http://localhost:11434/v1",
        refine_api_key="k",
        refine_model="qwen2.5-vl",
        refine_provider_preset="ollama",
        refine_meta_prompt_path="/custom/meta.md",
    )
    cfg2 = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg2.deeplx_url == "http://localhost:1188/translate"
    assert cfg2.refine_base_url == "http://localhost:11434/v1"
    assert cfg2.refine_api_key == "k"
    assert cfg2.refine_model == "qwen2.5-vl"
    assert cfg2.refine_provider_preset == "ollama"
    assert cfg2.refine_meta_prompt_path == "/custom/meta.md"


def test_deeplx_url_env_fallback_syncs_os_environ(tmp_path, monkeypatch):
    import os
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPLX_URL=http://env.example/translate\n")
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.deeplx_url == "http://env.example/translate"
    assert os.environ.get("DEEPLX_URL") == "http://env.example/translate"


def test_missing_new_fields_default_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"current_provider": "gemini"}))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.refine_base_url == ""
    assert cfg.refine_model == ""
    assert cfg.refine_provider_preset == "ollama"
    assert cfg.deeplx_url == ""


# ---------- video_tasks（多任务）+ 老缓存迁移 ----------

def test_video_tasks_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(video_tasks=[
        {"id": "1", "name": "T1", "timeline": {"global_prompt": "g"},
         "updated_at": 123.0, "last_result": "/o/v.mp4"}])
    cfg2 = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg2.video_tasks[0]["name"] == "T1"
    assert cfg2.video_tasks[0]["timeline"] == {"global_prompt": "g"}


def test_migrate_old_cache_to_one_task(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(_json.dumps({
        "video_timeline_cache": {"global_prompt": "OLD", "segments": []},
    }))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert len(cfg.video_tasks) == 1
    assert cfg.video_tasks[0]["name"] == "默认任务"
    assert cfg.video_tasks[0]["timeline"] == {"global_prompt": "OLD", "segments": []}


def test_no_migration_when_tasks_exist(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(_json.dumps({
        "video_timeline_cache": {"global_prompt": "OLD"},
        "video_tasks": [{"id": "1", "name": "Keep", "timeline": {}}],
    }))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert len(cfg.video_tasks) == 1
    assert cfg.video_tasks[0]["name"] == "Keep"


def test_workflow_ids_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(workflow_ids={"director": "A", "director_v3": "B"})
    cfg2 = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg2.workflow_ids == {"director": "A", "director_v3": "B"}


def test_migrate_old_workflow_id(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(_json.dumps({"runninghub_workflow_id": "OLD"}))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.workflow_ids.get("director") == "OLD"


# ---------- soundtrack_tasks ----------

def test_config_default_soundtrack_tasks_empty(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.soundtrack_tasks == []


def test_config_soundtrack_tasks_roundtrip(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(soundtrack_tasks=[{"id": "t1", "name": "EP01",
                                           "mp4": "/x/ep1.mp4", "style": "冷色调"}])
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["soundtrack_tasks"][0]["name"] == "EP01"
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.soundtrack_tasks[0]["mp4"] == "/x/ep1.mp4"


# ---------- soundtrack settings (workflow_id, output_dir, seeds_count, crossfade) ----------

def test_config_default_soundtrack_settings(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.soundtrack_workflow_id == "2059090557116440578"
    assert cfg.soundtrack_output_dir == ""
    assert cfg.soundtrack_seeds_count == 2
    assert cfg.soundtrack_crossfade == 0.5


def test_config_soundtrack_settings_roundtrip(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(soundtrack_workflow_id="wf-x",
                        soundtrack_output_dir="/x/out",
                        soundtrack_seeds_count=3,
                        soundtrack_crossfade=0.8)
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.soundtrack_workflow_id == "wf-x"
    assert cfg2.soundtrack_output_dir == "/x/out"
    assert cfg2.soundtrack_seeds_count == 3
    assert cfg2.soundtrack_crossfade == 0.8


# ── Tencent translator fields & migration ─────────────────────────────────

def test_save_load_tencent_translator_fields(tmp_path, monkeypatch):
    from drama_shot_master.config import load_config
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
    from drama_shot_master.config import load_config
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
    from drama_shot_master.config import load_config
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=settings_path)
    assert cfg.current_translator == "deeplx"
    assert cfg.deeplx_url == "http://localhost:1188/translate"


def test_post_load_migrate_defaults_to_tencent_when_empty(tmp_path, monkeypatch):
    from drama_shot_master.config import load_config
    for k in ("_CURRENT_TRANSLATOR", "TENCENTCLOUD_SECRET_ID",
              "TENCENTCLOUD_SECRET_KEY", "TENCENTCLOUD_REGION", "DEEPLX_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.current_translator == "tencent"
