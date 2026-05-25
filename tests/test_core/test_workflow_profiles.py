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
