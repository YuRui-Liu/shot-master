"""FE _paths.py 集级 helper 镜像 agent。"""
from pathlib import Path

from drama_shot_master.ui.widgets.screenwriter._paths import (
    script_index_path_in, script_episode_read_path_in,
    storyboard_episode_read_path_in, episode_prompts_dir_in,
    is_valid_episode_id_fe,
)


def test_is_valid_episode_id_fe():
    assert is_valid_episode_id_fe("E1")
    assert not is_valid_episode_id_fe("e1")
    assert not is_valid_episode_id_fe("E0")


def test_script_index_path_in(tmp_path):
    assert script_index_path_in(tmp_path).name == "剧本.json"


def test_script_episode_read_falls_back(tmp_path):
    (tmp_path / "剧本.md").write_text("x", encoding="utf-8")
    p = script_episode_read_path_in(tmp_path, "E1")
    assert p is not None and p.name == "剧本.md"


def test_storyboard_episode_read_prefers_new(tmp_path):
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "分镜.json").write_text("{}", encoding="utf-8")
    assert storyboard_episode_read_path_in(tmp_path, "E1").name == "分镜_E1.json"


def test_episode_prompts_dir_in(tmp_path):
    assert episode_prompts_dir_in(tmp_path, "E1") == tmp_path / "prompts" / "E1"
