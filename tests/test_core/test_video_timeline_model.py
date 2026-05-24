"""TimelineModel 单测（纯数据，零 Qt 依赖）。"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.core.video_timeline_model import (
    TimelineSegment, TimelineAudio, TimelineModel,
)


# ---------- dataclass 基础 ----------

def test_timeline_segment_defaults_image():
    s = TimelineSegment(
        seg_id="abc", segment_type="image", length_frames=24,
        image_path=Path("/x.png"),
    )
    assert s.seg_id == "abc"
    assert s.segment_type == "image"
    assert s.length_frames == 24
    assert s.local_prompt == ""
    assert s.image_path == Path("/x.png")
    assert s.guide_strength == 1.0


def test_timeline_segment_defaults_text():
    s = TimelineSegment(seg_id="t1", segment_type="text", length_frames=12)
    assert s.image_path is None
    assert s.guide_strength == 1.0


def test_timeline_segment_is_frozen():
    s = TimelineSegment(seg_id="abc", segment_type="image", length_frames=24)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.length_frames = 48


def test_timeline_audio_basic():
    a = TimelineAudio(
        audio_id="aud1", audio_path=Path("/bgm.mp3"),
        start_frame=0, length_frames=96,
    )
    assert a.audio_id == "aud1"
    assert a.audio_path == Path("/bgm.mp3")
    assert a.start_frame == 0
    assert a.length_frames == 96


def test_timeline_audio_is_frozen():
    a = TimelineAudio(audio_id="x", audio_path=Path("/a.mp3"),
                       start_frame=0, length_frames=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.start_frame = 10


def test_timeline_model_defaults():
    m = TimelineModel()
    assert m.segments == []
    assert m.audios == []
    assert m.pool == []
    assert m.global_prompt == ""
    assert m.use_global_prompt is True
    assert m.frame_rate == 24
    assert m.display_mode == "seconds"
    assert m.resolution_preset == "1280x720 (16:9) (横屏)"
    assert m.use_custom_resolution is False
    assert m.custom_width == 1024
    assert m.custom_height == 1024
    assert m.filename_prefix == "spb_video"
