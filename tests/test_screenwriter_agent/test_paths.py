"""创意.json/idea.json 路径兼容 helper 测试。"""
from screenwriter_agent.core.paths import (
    IDEA_FILE_NAME, IDEA_LEGACY_NAME,
    idea_exists, idea_read_path, idea_write_path,
)


def test_idea_write_path_uses_chinese_name(tmp_path):
    assert idea_write_path(tmp_path).name == IDEA_FILE_NAME


def test_idea_read_prefers_new_name(tmp_path):
    (tmp_path / IDEA_FILE_NAME).write_text("{}", encoding="utf-8")
    (tmp_path / IDEA_LEGACY_NAME).write_text("{}", encoding="utf-8")
    assert idea_read_path(tmp_path).name == IDEA_FILE_NAME


def test_idea_read_falls_back_to_legacy(tmp_path):
    (tmp_path / IDEA_LEGACY_NAME).write_text("{}", encoding="utf-8")
    assert idea_read_path(tmp_path).name == IDEA_LEGACY_NAME


def test_idea_read_none_when_missing(tmp_path):
    assert idea_read_path(tmp_path) is None
    assert idea_exists(tmp_path) is False


def test_idea_exists_true_for_either_name(tmp_path):
    (tmp_path / IDEA_LEGACY_NAME).write_text("{}", encoding="utf-8")
    assert idea_exists(tmp_path) is True


import re
from screenwriter_agent.core.paths import (
    script_index_path, script_episode_path, script_episode_read_path,
    storyboard_episode_path, storyboard_episode_read_path,
    episode_prompts_dir, is_valid_episode_id,
)


def test_is_valid_episode_id_accepts_E_plus_digits():
    assert is_valid_episode_id("E1")
    assert is_valid_episode_id("E20")
    assert not is_valid_episode_id("e1")
    assert not is_valid_episode_id("E0")    # 1-based
    assert not is_valid_episode_id("EE")
    assert not is_valid_episode_id("E1.5")


def test_script_index_path_returns_chinese_name(tmp_path):
    assert script_index_path(tmp_path).name == "剧本.json"


def test_script_episode_path_returns_E_suffix(tmp_path):
    assert script_episode_path(tmp_path, "E1").name == "剧本_E1.md"
    assert script_episode_path(tmp_path, "E13").name == "剧本_E13.md"


def test_script_episode_read_falls_back_to_legacy_script_md(tmp_path):
    # 旧项目：只有 剧本.md
    (tmp_path / "剧本.md").write_text("# old", encoding="utf-8")
    p = script_episode_read_path(tmp_path, "E1")
    assert p is not None and p.name == "剧本.md"


def test_script_episode_read_prefers_new_name(tmp_path):
    (tmp_path / "剧本_E1.md").write_text("# new", encoding="utf-8")
    (tmp_path / "剧本.md").write_text("# legacy", encoding="utf-8")
    p = script_episode_read_path(tmp_path, "E1")
    assert p.name == "剧本_E1.md"


def test_script_episode_read_none_when_missing(tmp_path):
    assert script_episode_read_path(tmp_path, "E1") is None


def test_storyboard_episode_path(tmp_path):
    assert storyboard_episode_path(tmp_path, "E2").name == "分镜_E2.json"


def test_storyboard_episode_read_falls_back_to_legacy(tmp_path):
    (tmp_path / "分镜.json").write_text("{}", encoding="utf-8")
    assert storyboard_episode_read_path(tmp_path, "E1").name == "分镜.json"


def test_episode_prompts_dir(tmp_path):
    assert episode_prompts_dir(tmp_path, "E1") == tmp_path / "prompts" / "E1"
