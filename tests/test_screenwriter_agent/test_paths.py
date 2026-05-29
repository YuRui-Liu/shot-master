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
