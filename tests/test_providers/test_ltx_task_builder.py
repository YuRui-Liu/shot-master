"""LTXDirectorSpec / LTXSegment / LTXTaskBuilder 单测。"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.providers.runninghub import (
    LTXSegment, LTXAudioSegment, LTXDirectorSpec,
    RunningHubInvalidSpec,
)


# ---------- Dataclass 基础行为 ----------

def test_ltx_segment_defaults():
    s = LTXSegment(local_prompt="p", length=24)
    assert s.local_prompt == "p"
    assert s.length == 24
    assert s.image_path is None
    assert s.segment_type == "image"
    assert s.guide_strength == 1.0
    assert s.seg_id == ""


def test_ltx_segment_is_frozen():
    s = LTXSegment(local_prompt="p", length=24)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.length = 48


def test_ltx_audio_segment_basic():
    a = LTXAudioSegment(audio_path=Path("/x.mp3"),
                          start_frame=0, length_frames=96)
    assert a.audio_path == Path("/x.mp3")
    assert a.start_frame == 0
    assert a.length_frames == 96


def test_ltx_director_spec_defaults():
    spec = LTXDirectorSpec()
    assert spec.global_prompt == ""
    assert spec.use_global_prompt is True
    assert spec.segments == ()
    assert spec.audio_segments == ()
    assert spec.use_custom_audio is False
    assert spec.display_mode == "seconds"
    assert spec.frame_rate == 24
    assert spec.resolution_preset == "1280x720 (16:9) (横屏)"
    assert spec.use_custom_resolution is False
    assert spec.custom_width == 1024
    assert spec.custom_height == 1024
    assert spec.noise_seed is None
    assert spec.filename_prefix == "spb_video"
    assert spec.output_dir == Path("./output")
    assert spec.epsilon == 0.5


def test_ltx_director_spec_is_frozen():
    spec = LTXDirectorSpec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.frame_rate = 30


def test_total_length_frames():
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=33),
        LTXSegment(local_prompt="b", length=33),
        LTXSegment(local_prompt="c", length=30),
    ))
    assert spec.total_length_frames() == 96


def test_total_length_seconds_uses_frame_rate():
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=96),),
        frame_rate=24,
    )
    assert spec.total_length_seconds() == 4.0


def test_unique_local_files_deduplicates_images():
    p1 = Path("/img1.png")
    p2 = Path("/img2.png")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=p1),
        LTXSegment(local_prompt="b", length=10, image_path=p1),  # 重复
        LTXSegment(local_prompt="c", length=10, image_path=p2),
        LTXSegment(local_prompt="d", length=10, image_path=None),  # 跳过
    ))
    assert spec.unique_local_files() == (p1, p2)


def test_unique_local_files_includes_audio_paths():
    img = Path("/img.png")
    aud = Path("/aud.mp3")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                         length_frames=10),),
    )
    assert set(spec.unique_local_files()) == {img, aud}


def test_unique_local_files_empty_when_all_text_segments():
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=None),
    ))
    assert spec.unique_local_files() == ()
