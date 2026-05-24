"""TimelineModel 单测（纯数据，零 Qt 依赖）。"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from drama_shot_master.core.video_timeline_model import (
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


# ---------- 增删段 ----------

def test_add_image_segment_returns_id_and_appends(tmp_path):
    m = TimelineModel()
    img = tmp_path / "a.png"
    sid = m.add_image_segment(img, length_frames=30, local_prompt="P")
    assert isinstance(sid, str) and len(sid) >= 13
    assert len(m.segments) == 1
    assert m.segments[0].seg_id == sid
    assert m.segments[0].image_path == img
    assert m.segments[0].length_frames == 30
    assert m.segments[0].local_prompt == "P"
    assert m.segments[0].segment_type == "image"


def test_add_text_segment_returns_id_no_image_path():
    m = TimelineModel()
    sid = m.add_text_segment(length_frames=10, local_prompt="X")
    assert len(m.segments) == 1
    assert m.segments[0].segment_type == "text"
    assert m.segments[0].image_path is None
    assert m.segments[0].seg_id == sid


def test_add_audio_returns_id(tmp_path):
    m = TimelineModel()
    p = tmp_path / "b.mp3"
    aid = m.add_audio(p, start_frame=12, length_frames=48)
    assert isinstance(aid, str)
    assert m.audios[0].audio_id == aid
    assert m.audios[0].audio_path == p
    assert m.audios[0].start_frame == 12


def test_remove_segment_existing(tmp_path):
    m = TimelineModel()
    sid = m.add_image_segment(tmp_path / "a.png")
    assert m.remove_segment(sid) is True
    assert m.segments == []


def test_remove_segment_unknown_returns_false():
    m = TimelineModel()
    assert m.remove_segment("never-existed") is False


def test_remove_audio_existing(tmp_path):
    m = TimelineModel()
    aid = m.add_audio(tmp_path / "x.mp3")
    assert m.remove_audio(aid) is True
    assert m.audios == []


def test_reorder_segments_reorders(tmp_path):
    m = TimelineModel()
    a = m.add_image_segment(tmp_path / "a.png")
    b = m.add_image_segment(tmp_path / "b.png")
    c = m.add_image_segment(tmp_path / "c.png")
    m.reorder_segments([c, a, b])
    assert [s.seg_id for s in m.segments] == [c, a, b]


def test_reorder_segments_drops_unknown_ids(tmp_path):
    m = TimelineModel()
    a = m.add_image_segment(tmp_path / "a.png")
    m.reorder_segments(["bogus", a])
    assert [s.seg_id for s in m.segments] == [a]


def test_update_segment_replaces_fields(tmp_path):
    m = TimelineModel()
    sid = m.add_image_segment(tmp_path / "a.png", length_frames=24)
    m.update_segment(sid, length_frames=72, local_prompt="new")
    assert m.segments[0].length_frames == 72
    assert m.segments[0].local_prompt == "new"
    # 未改字段保留
    assert m.segments[0].guide_strength == 1.0


def test_update_segment_unknown_id_silent(tmp_path):
    m = TimelineModel()
    m.add_image_segment(tmp_path / "a.png")
    # 不应抛错
    m.update_segment("bogus", length_frames=99)


def test_update_audio_replaces_fields(tmp_path):
    m = TimelineModel()
    aid = m.add_audio(tmp_path / "a.mp3", start_frame=0, length_frames=10)
    m.update_audio(aid, length_frames=50)
    assert m.audios[0].length_frames == 50
    assert m.audios[0].start_frame == 0


# ---------- 图片池 ----------

def test_add_to_pool_deduplicates(tmp_path):
    m = TimelineModel()
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    assert m.add_to_pool([p1, p2, p1]) == 2  # p1 重复算 1 次
    assert m.pool == [p1, p2]
    # 再加重复路径
    assert m.add_to_pool([p1]) == 0
    assert m.pool == [p1, p2]


def test_clear_pool_empties(tmp_path):
    m = TimelineModel()
    m.add_to_pool([tmp_path / "a.png"])
    m.clear_pool()
    assert m.pool == []


def test_pool_usage_counts_segments(tmp_path):
    m = TimelineModel()
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    p3 = tmp_path / "c.png"
    m.add_to_pool([p1, p2, p3])
    m.add_image_segment(p1)
    m.add_image_segment(p1)
    m.add_image_segment(p2)
    # p3 未引用
    usage = m.pool_usage()
    assert usage == {p1: 2, p2: 1, p3: 0}


def test_pool_usage_empty_when_pool_empty():
    assert TimelineModel().pool_usage() == {}


# ---------- to_ltx_spec ----------

def test_to_ltx_spec_basic_field_mapping(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    m = TimelineModel(
        global_prompt="G", use_global_prompt=True,
        frame_rate=30, display_mode="frames",
        filename_prefix="myvid",
    )
    m.add_image_segment(img, length_frames=33, local_prompt="P1")
    out = tmp_path / "out"
    spec = m.to_ltx_spec(out)
    assert spec.global_prompt == "G"
    assert spec.use_global_prompt is True
    assert spec.frame_rate == 30
    assert spec.display_mode == "frames"
    assert spec.filename_prefix == "myvid"
    assert spec.output_dir == out
    assert len(spec.segments) == 1
    assert spec.segments[0].local_prompt == "P1"
    assert spec.segments[0].length == 33
    assert spec.segments[0].image_path == img


def test_to_ltx_spec_use_custom_audio_defaults_false(tmp_path):
    """use_custom_audio 默认 False，即使有 audios 也不自动推导为 True。"""
    img = tmp_path / "a.png"
    m = TimelineModel()
    m.add_image_segment(img)
    spec_no_audio = m.to_ltx_spec(tmp_path)
    assert spec_no_audio.use_custom_audio is False

    m.add_audio(tmp_path / "x.mp3")
    spec_with_audio = m.to_ltx_spec(tmp_path)
    # 新逻辑：use_custom_audio 是显式字段，不再从 audios 自动推导
    assert spec_with_audio.use_custom_audio is False


def test_to_ltx_spec_audio_segments_mapping(tmp_path):
    m = TimelineModel()
    m.add_image_segment(tmp_path / "a.png")
    m.add_audio(tmp_path / "x.mp3", start_frame=24, length_frames=72)
    spec = m.to_ltx_spec(tmp_path)
    assert len(spec.audio_segments) == 1
    assert spec.audio_segments[0].audio_path == tmp_path / "x.mp3"
    assert spec.audio_segments[0].start_frame == 24
    assert spec.audio_segments[0].length_frames == 72


def test_to_ltx_spec_custom_resolution_passed(tmp_path):
    m = TimelineModel(
        use_custom_resolution=True,
        custom_width=720, custom_height=1280,
    )
    m.add_image_segment(tmp_path / "a.png")
    spec = m.to_ltx_spec(tmp_path)
    assert spec.use_custom_resolution is True
    assert spec.custom_width == 720
    assert spec.custom_height == 1280


# ---------- 序列化 ----------

def test_to_dict_path_to_str(tmp_path):
    m = TimelineModel()
    p = tmp_path / "a.png"
    m.add_image_segment(p, length_frames=20, local_prompt="P")
    m.add_audio(tmp_path / "x.mp3", start_frame=5, length_frames=15)
    m.add_to_pool([tmp_path / "img1.png", tmp_path / "img2.png"])
    d = m.to_dict()
    assert isinstance(d["segments"][0]["image_path"], str)
    assert d["segments"][0]["image_path"] == str(p)
    assert d["segments"][0]["length_frames"] == 20
    assert d["audios"][0]["audio_path"] == str(tmp_path / "x.mp3")
    assert all(isinstance(p, str) for p in d["pool"])


def test_to_dict_text_segment_image_path_none(tmp_path):
    m = TimelineModel()
    m.add_text_segment(length_frames=10, local_prompt="text")
    d = m.to_dict()
    assert d["segments"][0]["image_path"] is None
    assert d["segments"][0]["segment_type"] == "text"


def test_round_trip_to_from_dict(tmp_path):
    m1 = TimelineModel(
        global_prompt="GP", use_global_prompt=True,
        frame_rate=30, display_mode="frames",
        resolution_preset="720x1280 (9:16) (竖屏)",
        use_custom_resolution=True,
        custom_width=720, custom_height=1280,
        filename_prefix="vid",
    )
    img = tmp_path / "img.png"
    sid = m1.add_image_segment(img, length_frames=42, local_prompt="seg")
    m1.add_text_segment(length_frames=8)
    m1.add_audio(tmp_path / "a.mp3", start_frame=10, length_frames=50)
    m1.add_to_pool([tmp_path / "p1.png"])

    m2 = TimelineModel.from_dict(m1.to_dict())
    assert len(m2.segments) == 2
    assert m2.segments[0].seg_id == sid
    assert m2.segments[0].image_path == img
    assert m2.segments[0].length_frames == 42
    assert m2.segments[1].segment_type == "text"
    assert len(m2.audios) == 1
    assert m2.audios[0].start_frame == 10
    assert m2.pool == [tmp_path / "p1.png"]
    assert m2.global_prompt == "GP"
    assert m2.frame_rate == 30
    assert m2.display_mode == "frames"
    assert m2.use_custom_resolution is True
    assert m2.custom_width == 720


def test_from_dict_empty_uses_defaults():
    m = TimelineModel.from_dict({})
    assert m.segments == []
    assert m.audios == []
    assert m.pool == []
    assert m.frame_rate == 24
    assert m.display_mode == "seconds"


def test_from_dict_missing_seg_id_generated():
    import re
    m = TimelineModel.from_dict({"segments": [
        {"segment_type": "image", "length_frames": 10,
         "image_path": "/x.png", "local_prompt": "p"},
    ]})
    assert len(m.segments) == 1
    assert re.match(r"^\d{13}[0-9a-f]{1,5}$", m.segments[0].seg_id)


def test_from_dict_skips_audio_without_path():
    m = TimelineModel.from_dict({"audios": [{"start_frame": 0}]})
    assert m.audios == []


# ---------- validate ----------

def test_validate_rejects_empty_segments():
    m = TimelineModel()
    ok, msg = m.validate()
    assert ok is False
    assert "至少需要 1 段" in msg


def test_validate_rejects_length_lt_1(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    m = TimelineModel()
    m.add_image_segment(img, length_frames=0)
    ok, msg = m.validate()
    assert ok is False
    assert "长度" in msg


def test_validate_rejects_image_segment_without_path(tmp_path):
    m = TimelineModel()
    # 用 update_segment 把已有段的 image_path 改成 None
    sid = m.add_image_segment(tmp_path / "a.png")
    m.update_segment(sid, image_path=None)
    ok, msg = m.validate()
    assert ok is False
    assert "图片" in msg


def test_validate_rejects_missing_image_file(tmp_path):
    m = TimelineModel()
    m.add_image_segment(tmp_path / "nonexistent.png")
    ok, msg = m.validate()
    assert ok is False
    assert "不存在" in msg


def test_validate_rejects_invalid_frame_rate(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for bad_fr in (0, 200):
        m = TimelineModel(frame_rate=bad_fr)
        m.add_image_segment(img)
        ok, msg = m.validate()
        assert ok is False
        assert "frame_rate" in msg or "帧率" in msg


def test_validate_rejects_missing_audio_file(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    m = TimelineModel()
    m.add_image_segment(img)
    m.add_audio(tmp_path / "no.mp3")
    ok, msg = m.validate()
    assert ok is False
    assert "音频" in msg


def test_validate_passes_text_segment_without_image(tmp_path):
    m = TimelineModel()
    m.add_text_segment(length_frames=10, local_prompt="p")
    ok, msg = m.validate()
    assert ok is True
    assert msg == ""


def test_validate_passes_complete_spec(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
    m = TimelineModel()
    m.add_image_segment(img, length_frames=24)
    m.add_audio(aud, start_frame=0, length_frames=24)
    ok, msg = m.validate()
    assert ok is True
    assert msg == ""


# ---------- F-1: epsilon + use_custom_audio ----------

def test_model_defaults_epsilon_and_use_custom_audio():
    m = TimelineModel()
    assert m.epsilon == 0.5
    assert m.use_custom_audio is False


def test_to_ltx_spec_uses_explicit_use_custom_audio_true(tmp_path):
    """显式 use_custom_audio=True 即使没有 audios 也应保留 True。"""
    img = tmp_path / "a.png"
    m = TimelineModel(use_custom_audio=True)
    m.add_image_segment(img)
    spec = m.to_ltx_spec(tmp_path)
    assert spec.use_custom_audio is True


def test_to_ltx_spec_uses_explicit_use_custom_audio_false(tmp_path):
    """显式 use_custom_audio=False 即使有 audios 也应保留 False。"""
    img = tmp_path / "a.png"
    m = TimelineModel(use_custom_audio=False)
    m.add_image_segment(img)
    m.add_audio(tmp_path / "x.mp3")
    spec = m.to_ltx_spec(tmp_path)
    assert spec.use_custom_audio is False


def test_to_ltx_spec_passes_epsilon(tmp_path):
    img = tmp_path / "a.png"
    m = TimelineModel(epsilon=0.75)
    m.add_image_segment(img)
    spec = m.to_ltx_spec(tmp_path)
    assert spec.epsilon == 0.75


def test_to_dict_includes_new_fields(tmp_path):
    m = TimelineModel(epsilon=0.3, use_custom_audio=True)
    m.add_image_segment(tmp_path / "a.png")
    d = m.to_dict()
    assert d["epsilon"] == 0.3
    assert d["use_custom_audio"] is True


def test_from_dict_restores_new_fields():
    m = TimelineModel.from_dict({
        "epsilon": 0.8, "use_custom_audio": True,
    })
    assert m.epsilon == 0.8
    assert m.use_custom_audio is True


def test_from_dict_missing_new_fields_uses_defaults():
    m = TimelineModel.from_dict({})
    assert m.epsilon == 0.5
    assert m.use_custom_audio is False


def test_validate_rejects_epsilon_out_of_range(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for bad in (-0.1, 1.5):
        m = TimelineModel(epsilon=bad)
        m.add_image_segment(img)
        ok, msg = m.validate()
        assert ok is False
        assert "epsilon" in msg


def test_validate_accepts_epsilon_boundaries(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for ok_v in (0.0, 1.0, 0.5):
        m = TimelineModel(epsilon=ok_v)
        m.add_image_segment(img)
        ok, msg = m.validate()
        assert ok is True, f"epsilon={ok_v} should pass; got msg={msg}"
