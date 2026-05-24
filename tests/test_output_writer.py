import json
from pathlib import Path
from drama_shot_master.core.result_parser import ParsedResult
from drama_shot_master.core.output_writer import write_outputs, resolve_output_dir


def _make_result() -> ParsedResult:
    r = ParsedResult(raw="raw text")
    r.global_prompt = "GP"
    r.timeline_data = '{"segments": []}'
    r.local_prompts = "LP"
    r.segment_lengths = [96, 96]
    r.max_frames = 192
    r.frame_indices = [0, 96, -1, -1, -1]
    r.strengths = [1.0, 1.0, 0.0, 0.0, 0.0]
    r.epsilon = 0.1
    r.notes = "n1"
    return r


def test_write_outputs_creates_md_and_json(tmp_path):
    result = _make_result()
    md_path, json_path = write_outputs(
        result=result,
        output_dir=tmp_path,
        base_name="EP01_S03",
        template_id="four_frame",
        provider="gemini",
        model="gemini-2.5-pro",
    )
    assert md_path.exists()
    assert json_path.exists()
    md = md_path.read_text(encoding="utf-8")
    assert "GP" in md
    assert "EP01_S03" in md
    assert "four_frame" in md
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["global_prompt"] == "GP"
    assert data["max_frames"] == 192
    assert data["frame_indices"] == [0, 96, -1, -1, -1]
    assert data["meta"]["template_id"] == "four_frame"


def test_resolve_output_dir_input_sibling(tmp_path):
    img = tmp_path / "EP01_S03.png"
    img.write_bytes(b"")
    out = resolve_output_dir(image_path=img, default_output_dir=None)
    assert out == tmp_path / "_prompts"


def test_resolve_output_dir_explicit(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"")
    out = resolve_output_dir(image_path=img, default_output_dir=str(tmp_path / "out"))
    assert out == tmp_path / "out"


def test_write_outputs_overwrite_existing(tmp_path):
    r = _make_result()
    write_outputs(result=r, output_dir=tmp_path, base_name="x",
                  template_id="t", provider="p", model="m")
    r.global_prompt = "GP2"
    md_path, _ = write_outputs(result=r, output_dir=tmp_path, base_name="x",
                               template_id="t", provider="p", model="m")
    assert "GP2" in md_path.read_text(encoding="utf-8")
