"""apply_directive_to_prompts：方向写入各段 music_prompt（纯模板，不联网）。"""
from sound_track_agent.session import (
    ScoringSession, SegmentScore, SoundtrackDirective, EmotionTag)
from sound_track_agent.facade import apply_directive_to_prompts


def _sess():
    return ScoringSession(source_mp4="/m.mp4", source_hash="h",
                          global_style="旧风格", frame_rate=24.0,
                          segments=[SegmentScore(0, 0.0, 5.0),
                                    SegmentScore(1, 5.0, 12.0)])


def test_global_directive_written_to_all_segments():
    s = _sess()
    s.directive = SoundtrackDirective(global_directive="史诗管弦")
    apply_directive_to_prompts(s)
    assert s.global_style == "史诗管弦"
    assert "史诗管弦" in s.segments[0].music_prompt
    assert "史诗管弦" in s.segments[1].music_prompt


def test_segment_directive_overrides_global():
    s = _sess()
    s.directive = SoundtrackDirective(global_directive="史诗管弦",
                                      segment_directives={1: "钢琴独奏"})
    apply_directive_to_prompts(s)
    assert "史诗管弦" in s.segments[0].music_prompt
    assert "钢琴独奏" in s.segments[1].music_prompt


def test_empty_directive_falls_back_to_global_style():
    s = _sess()
    s.directive = SoundtrackDirective()
    apply_directive_to_prompts(s)
    assert "旧风格" in s.segments[0].music_prompt


def test_does_not_touch_candidates():
    from sound_track_agent.session import BGMCandidate
    s = _sess()
    s.segments[0].candidates = [BGMCandidate(path="/a.mp3", seed=1, prompt="x")]
    s.segments[0].chosen_candidate = 0
    s.directive = SoundtrackDirective(global_directive="新")
    apply_directive_to_prompts(s)
    assert len(s.segments[0].candidates) == 1
    assert s.segments[0].chosen_candidate == 0
