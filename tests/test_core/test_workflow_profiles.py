"""Tests for workflow_profiles."""
from __future__ import annotations

from drama_shot_master.core import workflow_profiles as wp


def test_two_builtin_profiles():
    assert set(wp.PROFILES) == {"director", "director_v3"}


def test_director_profile_node_ids():
    p = wp.PROFILES["director"]
    assert (p.director_node, p.save_video_node, p.noise_node,
            p.resolution_node, p.audio_switch_node) == ("4", "32", "23", "34", None)
    assert p.extras_yaml is None


def test_v3_profile_node_ids():
    p = wp.PROFILES["director_v3"]
    assert (p.director_node, p.save_video_node, p.noise_node,
            p.resolution_node, p.audio_switch_node) == ("672", "683", "654", None, "687")
    assert p.extras_yaml == "ltx_v3_extras.yaml"


def test_get_profile_fallback():
    assert wp.get_profile("nope").key == wp.DEFAULT_PROFILE_KEY


def test_template_path_points_into_templates():
    p = wp.template_path_for(wp.PROFILES["director"])
    assert p.name == "ltx_director_v23.json"
    assert p.parent.name == "templates"


def test_parse_preset_wh():
    assert wp.parse_preset_wh("1280x720 (16:9) (横屏)") == (1280, 720)
    assert wp.parse_preset_wh("720x1280 (9:16) (竖屏)") == (720, 1280)
    assert wp.parse_preset_wh("1024x1024 (1:1)") == (1024, 1024)
    assert wp.parse_preset_wh("自定义...") is None


def test_load_extras_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(wp, "extras_path_for", lambda prof: tmp_path / "nope.yaml")
    assert wp.load_extras(wp.PROFILES["director_v3"]) == []


def test_load_extras_reads_overrides(monkeypatch, tmp_path):
    y = tmp_path / "x.yaml"
    y.write_text("overrides:\n  - {node: '687', field: switch, value: true}\n"
                 "  - {node: '695', field: lora_01, value: a.safetensors}\n",
                 encoding="utf-8")
    monkeypatch.setattr(wp, "extras_path_for", lambda prof: y)
    out = wp.load_extras(wp.PROFILES["director_v3"])
    assert out == [
        {"node": "687", "field": "switch", "value": True},
        {"node": "695", "field": "lora_01", "value": "a.safetensors"},
    ]


def test_load_extras_for_profile_without_yaml():
    assert wp.load_extras(wp.PROFILES["director"]) == []


# ── 音频 profile ────────────────────────────────────────────────────

def test_audio_profiles_count():
    """四个音频 workflow profile 全部注册。"""
    assert set(wp.AUDIO_PROFILES) == {"tts_design", "tts_clone", "bgm", "sfx"}


def test_tts_design_key_nodes():
    p = wp.AUDIO_PROFILES["tts_design"]
    assert p.key == "tts_design"
    assert p.name == "音色设计"
    assert p.template_filename == "Qwen3 TTS 音色设计_api.json"
    assert p.key_nodes["text"] == "14"
    assert p.key_nodes["audio_style"] == "15"
    assert p.key_nodes["voice_design"] == "22"
    assert p.key_nodes["model_loader"] == "23"
    assert p.key_nodes["save_audio"] == "18"


def test_tts_clone_key_nodes():
    p = wp.AUDIO_PROFILES["tts_clone"]
    assert p.key == "tts_clone"
    assert p.name == "声音克隆"
    assert p.template_filename == "TTS2 情感声音克隆_input_switch_api.json"
    assert p.key_nodes["text"] == "4"
    assert p.key_nodes["speaker_audio"] == "10"
    assert p.key_nodes["emo_text"] == "16"
    assert p.key_nodes["emo_audio"] == "19"
    assert p.key_nodes["emo_vector"] == "21"
    assert p.key_nodes["emotion_selector"] == "103"
    assert p.key_nodes["run_node"] == "1"
    assert p.key_nodes["save_audio"] == "5"
    assert "情感模式" in p.notes


def test_bgm_key_nodes():
    p = wp.AUDIO_PROFILES["bgm"]
    assert p.key == "bgm"
    assert p.name == "配BGM (ACE-Step)"
    assert p.template_filename == "Ace-Step1.5X 配乐_api.json"
    assert p.key_nodes["tags_prompt"] == "94"
    assert p.key_nodes["bpm"] == "203"
    assert p.key_nodes["duration"] == "205"
    assert p.key_nodes["seed"] == "109"
    assert p.key_nodes["save_audio"] == "107"


def test_sfx_key_nodes():
    p = wp.AUDIO_PROFILES["sfx"]
    assert p.key == "sfx"
    assert p.name == "配SFX (Stable Audio)"
    assert p.template_filename == "Stable audio 3纯音乐-音效-VFX-One-Shot音频_api.json"
    assert p.key_nodes["user_prompt"] == "92"
    assert p.key_nodes["duration"] == "98"
    assert p.key_nodes["enable_reprompt"] == "97"
    assert p.key_nodes["mode_selector"] == "108"
    assert p.key_nodes["save_audio_mp3"] == "78"
    assert p.key_nodes["save_audio_flac"] == "102"
    # SFX notes 提示 LLM 改写 + mode_selector 存疑
    assert "LLM" in p.notes
    assert "存疑" in p.notes


def test_get_audio_profile():
    assert wp.get_audio_profile("tts_design") is wp.AUDIO_PROFILES["tts_design"]
    assert wp.get_audio_profile("nope") is None
    assert wp.get_audio_profile("bgm") is wp.AUDIO_PROFILES["bgm"]


def test_audio_template_path_exists():
    """所有音频模板 JSON 文件在 comfyui_workflow/ 下必须存在。"""
    for key, prof in wp.AUDIO_PROFILES.items():
        p = wp.audio_template_path_for(prof)
        assert p.exists(), f"{key}: 模板缺失 {p}"
        assert p.suffix == ".json", f"{key}: 模板非 .json"


def test_video_profiles_unchanged():
    """确保原有视频 profile 的 node ID 不受音频 profile 新增影响。"""
    assert set(wp.PROFILES) == {"director", "director_v3"}
    p = wp.PROFILES["director"]
    assert p.director_node == "4"
    assert p.save_video_node == "32"
    p3 = wp.PROFILES["director_v3"]
    assert p3.director_node == "672"
    assert p3.save_video_node == "683"
