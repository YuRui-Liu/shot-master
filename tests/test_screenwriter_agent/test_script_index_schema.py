import pytest
from pydantic import ValidationError

from screenwriter_agent.models.script_index_schema import (
    EpisodeEntry, ScriptIndex,
)


def test_episode_entry_id_must_match_pattern():
    EpisodeEntry(id="E1", title="t", summary="s")
    with pytest.raises(ValidationError):
        EpisodeEntry(id="e1", title="t", summary="s")
    with pytest.raises(ValidationError):
        EpisodeEntry(id="E0", title="t", summary="s")
    with pytest.raises(ValidationError):
        EpisodeEntry(id="", title="t", summary="s")


def test_script_index_basic():
    si = ScriptIndex(
        title="测试",
        episode_count=2,
        episodes=[
            EpisodeEntry(id="E1", title="a", summary="aa"),
            EpisodeEntry(id="E2", title="b", summary="bb"),
        ],
    )
    assert si.episode_count == 2
    assert len(si.episodes) == 2


def test_script_index_count_bounds():
    with pytest.raises(ValidationError):
        ScriptIndex(episode_count=0, episodes=[])
    with pytest.raises(ValidationError):
        ScriptIndex(episode_count=21, episodes=[])


def test_script_index_episodes_length_matches_count_loose():
    """spec 不强制 episodes 长度等于 episode_count——大纲生成中可能 partial 写入。
    校验只查 schema 类型，不做长度等于校验。"""
    si = ScriptIndex(
        title="x", episode_count=3,
        episodes=[EpisodeEntry(id="E1", title="a", summary="aa")],
    )
    assert si.episode_count == 3
    assert len(si.episodes) == 1


def test_script_index_round_trips_json():
    import json
    src = {
        "title": "x",
        "episode_count": 1,
        "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": "a", "summary": "aa"}],
        "input": {"core_idea": "守株待兔"},
        "updated_at": "2026-05-29T00:00:00",
    }
    si = ScriptIndex.model_validate(src)
    again = json.loads(si.model_dump_json())
    assert again["episodes"][0]["id"] == "E1"
    assert again["input"]["core_idea"] == "守株待兔"
