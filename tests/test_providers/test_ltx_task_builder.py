"""LTXDirectorSpec / LTXSegment / LTXTaskBuilder 单测。"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import copy
import json

from app.providers.runninghub import LTXNodes, LTXTaskBuilder

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


# ---------- Builder fixture ----------

@pytest.fixture
def template_path():
    """指向项目内置的真实模板。"""
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent.parent
         / "app" / "templates" / "ltx_director_v23.json")
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


# ---------- build_inline_workflow ----------

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


def test_inline_workflow_minimal_spec(builder, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    uploaded = {img: "openapi/abc.png"}
    wf = builder.build_inline_workflow(spec, uploaded)
    assert LTXNodes.DIRECTOR in wf
    inputs = wf[LTXNodes.DIRECTOR]["inputs"]
    assert inputs["global_prompt"] == "global"
    assert inputs["frame_rate"] == 24


def test_inline_workflow_does_not_mutate_template(builder, tmp_path):
    snapshot = copy.deepcopy(builder._template)
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    builder.build_inline_workflow(spec, {img: "openapi/abc.png"})
    assert builder._template == snapshot


def test_inline_workflow_other_nodes_unchanged(builder, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    wf = builder.build_inline_workflow(spec, {img: "openapi/abc.png"})
    # 节点 80 / 113 / 140（LoRA loaders）必须保持模板默认
    for nid in ("80", "113", "140"):
        assert wf[nid] == builder._template[nid]


def test_inline_timeline_data_json_structure(builder, tmp_path):
    img1 = tmp_path / "a.png"; img1.write_bytes(b"x")
    img2 = tmp_path / "b.png"; img2.write_bytes(b"y")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="p1", length=33, image_path=img1),
        LTXSegment(local_prompt="p2", length=33, image_path=img2),
        LTXSegment(local_prompt="p3", length=30, image_path=img1),  # 复用
    ))
    uploaded = {img1: "openapi/a.png", img2: "openapi/b.png"}
    wf = builder.build_inline_workflow(spec, uploaded)
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
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


def test_inline_local_prompts_joined_with_pipe_and_spaces(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img),
        LTXSegment(local_prompt="b", length=10, image_path=img),
        LTXSegment(local_prompt="c", length=10, image_path=img),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["local_prompts"] == "a | b | c"


def test_inline_segment_lengths_csv(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=33, image_path=img),
        LTXSegment(local_prompt="b", length=33, image_path=img),
        LTXSegment(local_prompt="c", length=30, image_path=img),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["segment_lengths"] == "33,33,30"


def test_inline_guide_strength_two_decimals(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img,
                    guide_strength=1.0),
        LTXSegment(local_prompt="b", length=10, image_path=img,
                    guide_strength=0.75),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["guide_strength"] == "1.00,0.75"


def test_inline_global_prompt_blanked_when_disabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        global_prompt="should-be-blanked",
        use_global_prompt=False,
        segments=(LTXSegment(local_prompt="p", length=10, image_path=img),),
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["global_prompt"] == ""


def test_inline_duration_frames_and_seconds_consistent(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=96, image_path=img),),
        frame_rate=24,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    inputs = wf[LTXNodes.DIRECTOR]["inputs"]
    assert inputs["duration_frames"] == 96
    assert inputs["duration_seconds"] == 4.0


def test_inline_audio_empty_when_disabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"; aud.write_bytes(b"a")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=False,
    )
    wf = builder.build_inline_workflow(
        spec, {img: "openapi/a.png", aud: "openapi/x.mp3"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    assert td["audioSegments"] == []
    assert wf[LTXNodes.DIRECTOR]["inputs"]["use_custom_audio"] is False


def test_inline_audio_present_when_enabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"; aud.write_bytes(b"a")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=True,
    )
    wf = builder.build_inline_workflow(
        spec, {img: "openapi/a.png", aud: "openapi/x.mp3"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    assert len(td["audioSegments"]) == 1
    assert td["audioSegments"][0]["audioFile"] == "x.mp3"


def test_inline_filename_prefix_node_104(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        filename_prefix="myvid",
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.SAVE_VIDEO]["inputs"]["filename_prefix"] == "myvid"


def test_inline_noise_seed_none_preserves_template(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    original_seed = builder._template[LTXNodes.NOISE]["inputs"]["noise_seed"]
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        noise_seed=None,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.NOISE]["inputs"]["noise_seed"] == original_seed


def test_inline_noise_seed_overrides_template(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        noise_seed=42,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.NOISE]["inputs"]["noise_seed"] == 42


def test_inline_resolution_preset_applied(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        resolution_preset="720x1280 (9:16) (竖屏)",
        use_custom_resolution=False,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    inputs = wf[LTXNodes.RESOLUTION]["inputs"]
    assert inputs["use_custom_resolution"] is False
    assert inputs["resolution"] == "720x1280 (9:16) (竖屏)"


def test_inline_custom_resolution_applied(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        use_custom_resolution=True,
        custom_width=1024, custom_height=768,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    inputs = wf[LTXNodes.RESOLUTION]["inputs"]
    assert inputs["use_custom_resolution"] is True
    assert inputs["custom_width"] == 1024
    assert inputs["custom_height"] == 768


def test_seg_id_generated_when_blank(builder, tmp_path):
    import re
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img, seg_id=""),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    generated_id = td["segments"][0]["id"]
    assert re.match(r"^\d{13}[0-9a-f]{1,5}$", generated_id), generated_id


def test_seg_id_preserved_when_provided(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img,
                    seg_id="custom-abc"),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    assert td["segments"][0]["id"] == "custom-abc"
