import pytest
from screenwriter_agent.core.schema_validator import validate_storyboard, ValidationWarn


def _good():
    return {
        "title": "demo",
        "aspectRatio": "9:16",
        "fps": 24,
        "totalDuration": 60,
        "globalStyle": "古风水墨",
        "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾披肩长发"}],
        "shots": [
            {"shotId": "S01", "description": "雨夜画面", "duration": 6,
             "stylePrompt": "古风水墨，雨夜松林，狐妖立于树下", "composition": "中景"},
        ],
    }


def test_valid_storyboard_passes():
    obj, warns = validate_storyboard(_good())
    assert obj is not None
    assert all(w.severity in ("info", "warning") for w in warns)


def test_missing_title_warning_filled():
    bad = _good(); del bad["title"]
    obj, warns = validate_storyboard(bad, fallback_title="from-script.md")
    assert obj is not None
    assert obj["title"] == "from-script.md"
    assert any("title" in w.path for w in warns)


def test_empty_shots_critical():
    bad = _good(); bad["shots"] = []
    with pytest.raises(Exception):
        validate_storyboard(bad)


def test_shot_missing_shotId_autofill():
    bad = _good(); del bad["shots"][0]["shotId"]
    obj, warns = validate_storyboard(bad)
    assert obj["shots"][0]["shotId"].startswith("S01")
    assert any("shotId" in w.path for w in warns)


def test_stylePrompt_must_be_long():
    bad = _good(); bad["shots"][0]["stylePrompt"] = "短"
    obj, warns = validate_storyboard(bad)
    assert any(w.severity in ("warning", "error") and "stylePrompt" in w.path for w in warns)
