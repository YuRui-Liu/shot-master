"""LTXDirectorSpec / LTXSegment / LTXTaskBuilder 单测。"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import copy
import json

from drama_shot_master.providers.runninghub import LTXNodes, LTXTaskBuilder

from drama_shot_master.providers.runninghub import (
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


# ---------- Builder fixture ----------

@pytest.fixture
def template_path():
    """指向项目内置的真实模板。"""
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent.parent
         / "drama_shot_master" / "templates" / "ltx_director_v23.json")
    assert p.exists(), f"模板不存在: {p}"
    return p


@pytest.fixture
def builder(template_path):
    return LTXTaskBuilder(template_path)


# ---------- init ----------

def test_builder_init_loads_template(builder):
    assert LTXNodes.DIRECTOR in builder._template
    assert LTXNodes.SAVE_VIDEO in builder._template
    assert LTXNodes.NOISE in builder._template
    assert LTXNodes.RESOLUTION in builder._template


def test_builder_init_rejects_template_missing_director_node(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"99": {"class_type": "X"}}))
    with pytest.raises(RunningHubInvalidSpec) as exc_info:
        LTXTaskBuilder(bad)
    assert LTXNodes.DIRECTOR in str(exc_info.value)


def test_builder_init_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        LTXTaskBuilder(tmp_path / "absent.json")


# ---------- Director 参数计算（经 build_node_info_list）----------

def _basic_spec(img_path=None, length=33, n_segs=1):
    return LTXDirectorSpec(
        global_prompt="global",
        segments=tuple(
            LTXSegment(local_prompt=f"p{i}", length=length,
                        image_path=img_path)
            for i in range(n_segs)
        ),
        frame_rate=24,
    )


def _ninfo(builder, spec, uploaded):
    """build_node_info_list → {(nodeId, fieldName): fieldValue}。
    取代旧 inline 模式 wf[node]['inputs'][field] 的检查方式。"""
    items = builder.build_node_info_list(spec, uploaded)
    return {(it["nodeId"], it["fieldName"]): it["fieldValue"] for it in items}


def test_director_minimal_spec(builder, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    m = _ninfo(builder, spec, {img: "openapi/abc.png"})
    assert m[(LTXNodes.DIRECTOR, "global_prompt")] == "global"
    assert m[(LTXNodes.DIRECTOR, "frame_rate")] == 24


def test_build_node_info_list_does_not_mutate_template(builder, tmp_path):
    snapshot = copy.deepcopy(builder._template)
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    builder.build_node_info_list(spec, {img: "openapi/abc.png"})
    assert builder._template == snapshot


def test_timeline_data_json_structure(builder, tmp_path):
    img1 = tmp_path / "a.png"; img1.write_bytes(b"x")
    img2 = tmp_path / "b.png"; img2.write_bytes(b"y")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="p1", length=33, image_path=img1),
        LTXSegment(local_prompt="p2", length=33, image_path=img2),
        LTXSegment(local_prompt="p3", length=30, image_path=img1),  # 复用
    ))
    uploaded = {img1: "openapi/a.png", img2: "openapi/b.png"}
    m = _ninfo(builder, spec, uploaded)
    td = json.loads(m[(LTXNodes.DIRECTOR, "timeline_data")])
    assert len(td["segments"]) == 3
    assert td["segments"][0]["start"] == 0
    assert td["segments"][1]["start"] == 33
    assert td["segments"][2]["start"] == 66
    assert td["segments"][0]["length"] == 33
    assert td["segments"][0]["prompt"] == "p1"
    assert td["segments"][0]["type"] == "image"
    assert td["segments"][0]["imageFile"] == "a.png"
    assert "filename=a.png" in td["segments"][0]["imageB64"]
    assert td["audioSegments"] == []


def test_local_prompts_joined_with_pipe_and_spaces(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img),
        LTXSegment(local_prompt="b", length=10, image_path=img),
        LTXSegment(local_prompt="c", length=10, image_path=img),
    ))
    m = _ninfo(builder, spec, {img: "openapi/a.png"})
    assert m[(LTXNodes.DIRECTOR, "local_prompts")] == "a | b | c"


def test_segment_lengths_csv(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=33, image_path=img),
        LTXSegment(local_prompt="b", length=33, image_path=img),
        LTXSegment(local_prompt="c", length=30, image_path=img),
    ))
    m = _ninfo(builder, spec, {img: "openapi/a.png"})
    assert m[(LTXNodes.DIRECTOR, "segment_lengths")] == "33,33,30"


def test_guide_strength_two_decimals(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img,
                    guide_strength=1.0),
        LTXSegment(local_prompt="b", length=10, image_path=img,
                    guide_strength=0.75),
    ))
    m = _ninfo(builder, spec, {img: "openapi/a.png"})
    assert m[(LTXNodes.DIRECTOR, "guide_strength")] == "1.00,0.75"


def test_global_prompt_blanked_when_disabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        global_prompt="should-be-blanked",
        use_global_prompt=False,
        segments=(LTXSegment(local_prompt="p", length=10, image_path=img),),
    )
    m = _ninfo(builder, spec, {img: "openapi/a.png"})
    assert m[(LTXNodes.DIRECTOR, "global_prompt")] == ""


def test_duration_frames_and_seconds_consistent(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=96, image_path=img),),
        frame_rate=24,
    )
    m = _ninfo(builder, spec, {img: "openapi/a.png"})
    assert m[(LTXNodes.DIRECTOR, "duration_frames")] == 96
    assert m[(LTXNodes.DIRECTOR, "duration_seconds")] == 4.0


def test_audio_empty_when_disabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"; aud.write_bytes(b"a")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=False,
    )
    m = _ninfo(builder, spec, {img: "openapi/a.png", aud: "openapi/x.mp3"})
    td = json.loads(m[(LTXNodes.DIRECTOR, "timeline_data")])
    assert td["audioSegments"] == []
    assert m[(LTXNodes.DIRECTOR, "use_custom_audio")] is False


def test_audio_present_when_enabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"; aud.write_bytes(b"a")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=True,
    )
    m = _ninfo(builder, spec, {img: "openapi/a.png", aud: "openapi/x.mp3"})
    td = json.loads(m[(LTXNodes.DIRECTOR, "timeline_data")])
    assert len(td["audioSegments"]) == 1
    assert td["audioSegments"][0]["audioFile"] == "x.mp3"


def test_seg_id_generated_when_blank(builder, tmp_path):
    import re
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img, seg_id=""),
    ))
    m = _ninfo(builder, spec, {img: "openapi/a.png"})
    td = json.loads(m[(LTXNodes.DIRECTOR, "timeline_data")])
    generated_id = td["segments"][0]["id"]
    assert re.match(r"^\d{13}[0-9a-f]{1,5}$", generated_id), generated_id


def test_seg_id_preserved_when_provided(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img,
                    seg_id="custom-abc"),
    ))
    m = _ninfo(builder, spec, {img: "openapi/a.png"})
    td = json.loads(m[(LTXNodes.DIRECTOR, "timeline_data")])
    assert td["segments"][0]["id"] == "custom-abc"


# ---------- build_node_info_list ----------

def test_nodeinfolist_includes_all_director_fields(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    field_names = {it["fieldName"] for it in items
                    if it["nodeId"] == LTXNodes.DIRECTOR}
    expected = {"global_prompt", "duration_frames", "duration_seconds",
                "timeline_data", "local_prompts", "segment_lengths",
                "use_custom_audio", "frame_rate", "display_mode",
                "guide_strength", "epsilon"}
    assert expected.issubset(field_names)


def test_nodeinfolist_excludes_non_whitelisted_director_fields(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    director_fields = {it["fieldName"] for it in items
                        if it["nodeId"] == LTXNodes.DIRECTOR}
    forbidden = {"model", "clip", "audio_vae", "custom_width",
                  "custom_height", "timeline_ui", "resize_method",
                  "divisible_by", "img_compression"}
    assert not director_fields & forbidden


def test_nodeinfolist_includes_filename_prefix_104(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    spec = dataclasses.replace(spec, filename_prefix="myvid")
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    matching = [it for it in items
                if it["nodeId"] == LTXNodes.SAVE_VIDEO
                and it["fieldName"] == "filename_prefix"]
    assert len(matching) == 1
    assert matching[0]["fieldValue"] == "myvid"


def test_nodeinfolist_noise_seed_only_when_set(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec_none = _basic_spec(img_path=img)
    items_none = builder.build_node_info_list(spec_none, {img: "openapi/a.png"})
    assert not any(it["nodeId"] == LTXNodes.NOISE for it in items_none)

    spec_seed = dataclasses.replace(spec_none, noise_seed=42)
    items_seed = builder.build_node_info_list(spec_seed, {img: "openapi/a.png"})
    seed_items = [it for it in items_seed if it["nodeId"] == LTXNodes.NOISE]
    assert len(seed_items) == 1
    assert seed_items[0]["fieldName"] == "noise_seed"
    assert seed_items[0]["fieldValue"] == 42


def test_nodeinfolist_resolution_preset_when_not_custom(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    res_items = [it for it in items if it["nodeId"] == LTXNodes.RESOLUTION]
    assert len(res_items) == 1
    assert res_items[0]["fieldName"] == "resolution"
    assert res_items[0]["fieldValue"] == "1280x720 (16:9) (横屏)"


def test_nodeinfolist_custom_resolution_three_fields(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        use_custom_resolution=True,
        custom_width=1024, custom_height=768,
    )
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    res_items = {it["fieldName"]: it["fieldValue"]
                  for it in items if it["nodeId"] == LTXNodes.RESOLUTION}
    assert res_items == {"use_custom_resolution": True,
                          "custom_width": 1024, "custom_height": 768}


# ---------- 完整 _validate ----------

def test_validate_rejects_empty_segments(builder):
    spec = LTXDirectorSpec(segments=())
    with pytest.raises(RunningHubInvalidSpec, match="至少需要 1 段"):
        builder.build_node_info_list(spec, {})


def test_validate_rejects_segment_length_lt_1(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=0, image_path=img),
    ))
    with pytest.raises(RunningHubInvalidSpec, match="length"):
        builder.build_node_info_list(spec, {img: "openapi/a.png"})


def test_validate_rejects_missing_uploaded_image(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    with pytest.raises(RunningHubInvalidSpec, match="未在 uploaded_files"):
        builder.build_node_info_list(spec, {})


def test_validate_rejects_guide_strength_out_of_range(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for bad in (-0.1, 1.5):
        spec = LTXDirectorSpec(segments=(
            LTXSegment(local_prompt="a", length=10, image_path=img,
                        guide_strength=bad),
        ))
        with pytest.raises(RunningHubInvalidSpec, match="guide_strength"):
            builder.build_node_info_list(spec, {img: "openapi/a.png"})


def test_validate_rejects_invalid_frame_rate(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for bad in (0, 200):
        spec = LTXDirectorSpec(
            segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
            frame_rate=bad,
        )
        with pytest.raises(RunningHubInvalidSpec, match="frame_rate"):
            builder.build_node_info_list(spec, {img: "openapi/a.png"})


def test_validate_rejects_missing_audio_upload(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=True,
    )
    with pytest.raises(RunningHubInvalidSpec, match="音频段"):
        builder.build_node_info_list(spec, {img: "openapi/a.png"})


def test_validate_passes_text_segment_without_upload(builder):
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=None),
    ))
    # 不应抛错（text 段不要求 image_path）
    builder.build_node_info_list(spec, {})


# ---------- 音频路由约束 ----------

def test_nodeinfolist_never_overrides_audio_link(builder, tmp_path):
    """RunningHub nodeInfoList 只能覆盖 widget 参数；CreateVideo.audio 是
    节点间连线(link)，覆盖它会被服务端拒为 code=404 NOT_FOUND。
    因此 nodeInfoList 绝不能把 audio 放进去——无论 use_custom_audio 取值。
    原生音频路由需在 RunningHub 平台上改工作流本身。"""
    CREATE_VIDEO = "17"
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for use_custom in (False, True):
        kwargs = dict(
            segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
            use_custom_audio=use_custom,
        )
        files = {img: "openapi/a.png"}
        if use_custom:
            aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
            kwargs["audio_segments"] = (
                LTXAudioSegment(audio_path=aud, start_frame=0, length_frames=10),)
            files[aud] = "openapi/a.mp3"
        items = builder.build_node_info_list(LTXDirectorSpec(**kwargs), files)
        audio_items = [it for it in items
                       if it["nodeId"] == CREATE_VIDEO
                       and it["fieldName"] == "audio"]
        assert audio_items == [], (
            f"use_custom_audio={use_custom}: nodeInfoList 不应覆盖 audio 连线")
