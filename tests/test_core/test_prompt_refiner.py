"""Tests for drama_shot_master.core.prompt_refiner."""
from __future__ import annotations

from pathlib import Path

import pytest

from drama_shot_master.core.prompt_refiner import (
    build_refine_request, parse_refine_response, RefineParseError,
)
from drama_shot_master.core.video_timeline_model import TimelineModel


def _model_2img_1text() -> TimelineModel:
    m = TimelineModel(global_prompt="cinematic noir style")
    m.add_image_segment(Path("/fake/a.png"), length_frames=36, local_prompt="a")
    m.add_image_segment(Path("/fake/b.png"), length_frames=24, local_prompt="b")
    m.add_text_segment(length_frames=12, local_prompt="t")
    return m


def test_build_request_collects_only_image_paths():
    req = build_refine_request(_model_2img_1text())
    assert req.images == [Path("/fake/a.png"), Path("/fake/b.png")]


def test_build_request_seg_ids_cover_all_in_order():
    m = _model_2img_1text()
    req = build_refine_request(m)
    assert req.seg_ids == [s.seg_id for s in m.segments]
    assert len(req.seg_ids) == 3


def test_build_request_message_has_global_and_all_segments():
    req = build_refine_request(_model_2img_1text())
    assert "cinematic noir style" in req.user_message
    assert "[seg 0]" in req.user_message
    assert "[seg 1]" in req.user_message
    assert "[seg 2]" in req.user_message
    assert "attached_image=#0" in req.user_message
    assert "attached_image=#1" in req.user_message


def test_parse_valid_json_maps_indices_to_seg_ids():
    raw = ('{"global_prompt": "G", "segments": ['
           '{"index": 0, "local_prompt": "A"}, '
           '{"index": 1, "local_prompt": "B"}]}')
    res = parse_refine_response(raw, ["s0", "s1"])
    assert res.global_prompt == "G"
    assert res.segment_locals == [("s0", "A"), ("s1", "B")]
    assert res.warnings == []


def test_parse_strips_code_fence():
    raw = '```json\n{"global_prompt": "G", "segments": []}\n```'
    res = parse_refine_response(raw, ["s0"])
    assert res.global_prompt == "G"
    assert res.segment_locals == []


def test_parse_missing_global_is_none():
    raw = '{"segments": [{"index": 0, "local_prompt": "A"}]}'
    res = parse_refine_response(raw, ["s0"])
    assert res.global_prompt is None
    assert res.segment_locals == [("s0", "A")]


def test_parse_index_out_of_range_skipped_with_warning():
    raw = '{"segments": [{"index": 99, "local_prompt": "X"}]}'
    res = parse_refine_response(raw, ["s0"])
    assert res.segment_locals == []
    assert res.warnings  # non-empty


def test_parse_bad_json_raises():
    with pytest.raises(RefineParseError):
        parse_refine_response("not json at all", ["s0"])


def test_parse_blank_global_treated_as_none():
    raw = '{"global_prompt": "   ", "segments": []}'
    res = parse_refine_response(raw, [])
    assert res.global_prompt is None
