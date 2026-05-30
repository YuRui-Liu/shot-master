"""StoryboardOptions 支持时长范围 shot_duration_min / shot_duration_max。"""
from screenwriter_agent.models.requests import StoryboardOptions


def test_storyboard_options_duration_range_defaults():
    o = StoryboardOptions()
    assert o.shot_duration_min == 4.0
    assert o.shot_duration_max == 10.0


def test_storyboard_options_accepts_custom_range():
    o = StoryboardOptions(shot_duration_min=3.0, shot_duration_max=7.0)
    assert o.shot_duration_min == 3.0
    assert o.shot_duration_max == 7.0
