"""「不截断：按输入首帧图尺寸出图」——fit_to_input_image 单测。

覆盖两个 profile：
- director (有 resolution_node=34，走 TTResolutionSelector custom 三件套)
- director_v3 (无 resolution_node，落 director 节点 672 的 custom_width/height)

并验证：16:9 输入图 → 框宽>高且比≈16:9、divisible_by 32；无图/读图失败 → 回退预设不崩。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from drama_shot_master.core.workflow_profiles import (
    get_profile, fit_box_to_aspect, read_image_wh,
)
from drama_shot_master.providers.runninghub import (
    LTXSegment, LTXDirectorSpec, LTXTaskBuilder,
)

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


# ---------- fixtures ----------

@pytest.fixture
def director_builder():
    p = (Path(__file__).resolve().parent.parent.parent
         / "drama_shot_master" / "templates" / "ltx_director_v23.json")
    return LTXTaskBuilder(p, get_profile("director"))


@pytest.fixture
def hd_builder():
    p = (Path(__file__).resolve().parent.parent.parent
         / "drama_shot_master" / "templates" / "ltx_director_v3_api.json")
    return LTXTaskBuilder(p, get_profile("director_v3"))


def _make_image(path: Path, w: int, h: int) -> Path:
    Image.new("RGB", (w, h), (10, 20, 30)).save(path)
    return path


def _res_map(items: list[dict], node_id: str) -> dict:
    """从 nodeInfoList 抽出指定节点的 {fieldName: fieldValue}。"""
    return {it["fieldName"]: it["fieldValue"]
            for it in items if it["nodeId"] == node_id}


def _spec_with_image(img: Path | None, **kw) -> LTXDirectorSpec:
    seg = LTXSegment(local_prompt="s", length=10, image_path=img,
                     segment_type="image" if img else "text")
    return LTXDirectorSpec(segments=(seg,), frame_rate=24,
                           output_dir=Path("./out"), **kw)


# ---------- 纯函数 fit_box_to_aspect ----------

def test_fit_box_16_9_landscape():
    w, h = fit_box_to_aspect(1920, 1080)
    assert w > h
    assert w % 32 == 0 and h % 32 == 0
    assert abs(w / h - 16 / 9) < 0.05


def test_fit_box_9_16_portrait():
    w, h = fit_box_to_aspect(1080, 1920)
    assert h > w
    assert w % 32 == 0 and h % 32 == 0
    assert abs(h / w - 16 / 9) < 0.05


def test_fit_box_square():
    w, h = fit_box_to_aspect(1000, 1000)
    assert w == h
    assert w % 32 == 0


def test_fit_box_zero_falls_back_to_square():
    w, h = fit_box_to_aspect(0, 0)
    assert w == h > 0 and w % 32 == 0


# ---------- read_image_wh 容错 ----------

def test_read_image_wh_ok(tmp_path):
    img = _make_image(tmp_path / "a.png", 640, 360)
    assert read_image_wh(img) == (640, 360)


def test_read_image_wh_missing_file_returns_none(tmp_path):
    assert read_image_wh(tmp_path / "nope.png") is None


def test_read_image_wh_corrupt_returns_none(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert read_image_wh(bad) is None


def test_read_image_wh_none_returns_none():
    assert read_image_wh(None) is None


# ---------- director profile (node 34) ----------

def test_director_fit_16_9_overrides_resolution_node(director_builder, tmp_path):
    img = _make_image(tmp_path / "fhd.png", 1920, 1080)
    spec = _spec_with_image(img,
                            resolution_preset="1080x1080 (1:1) (方形)")
    items = director_builder.build_node_info_list(spec, {img: "openapi/fhd.png"})
    res = _res_map(items, "34")
    assert res["use_custom_resolution"] is True
    w, h = res["custom_width"], res["custom_height"]
    assert w > h and abs(w / h - 16 / 9) < 0.05
    assert w % 32 == 0 and h % 32 == 0


def test_director_no_image_falls_back_to_preset(director_builder, tmp_path):
    spec = _spec_with_image(None, resolution_preset="1280x720 (16:9) (横屏)")
    items = director_builder.build_node_info_list(spec, {})
    res = _res_map(items, "34")
    assert (res["custom_width"], res["custom_height"]) == (1280, 720)


def test_director_corrupt_image_falls_back_no_crash(director_builder, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"xxx")
    spec = _spec_with_image(bad, resolution_preset="1280x720 (16:9) (横屏)")
    items = director_builder.build_node_info_list(spec, {bad: "openapi/bad.png"})
    res = _res_map(items, "34")
    assert (res["custom_width"], res["custom_height"]) == (1280, 720)


def test_director_explicit_custom_res_skips_fit(director_builder, tmp_path):
    img = _make_image(tmp_path / "fhd.png", 1920, 1080)
    spec = _spec_with_image(img, use_custom_resolution=True,
                            custom_width=512, custom_height=512)
    items = director_builder.build_node_info_list(spec, {img: "openapi/fhd.png"})
    res = _res_map(items, "34")
    assert (res["custom_width"], res["custom_height"]) == (512, 512)


def test_director_fit_disabled_uses_preset(director_builder, tmp_path):
    img = _make_image(tmp_path / "fhd.png", 1920, 1080)
    spec = _spec_with_image(img, fit_to_input_image=False,
                            resolution_preset="1280x720 (16:9) (横屏)")
    items = director_builder.build_node_info_list(spec, {img: "openapi/fhd.png"})
    res = _res_map(items, "34")
    assert (res["custom_width"], res["custom_height"]) == (1280, 720)


# ---------- director_v3 profile (node 672, no resolution_node) ----------

def test_hd_fit_16_9_overrides_director_node(hd_builder, tmp_path):
    prof = get_profile("director_v3")
    img = _make_image(tmp_path / "fhd.png", 1920, 1080)
    spec = _spec_with_image(img, resolution_preset="1080x1080 (1:1) (方形)")
    items = hd_builder.build_node_info_list(spec, {img: "openapi/fhd.png"})
    res = _res_map(items, prof.director_node)
    w, h = res["custom_width"], res["custom_height"]
    assert w > h and abs(w / h - 16 / 9) < 0.05
    assert w % 32 == 0 and h % 32 == 0


def test_hd_no_image_falls_back_to_preset(hd_builder, tmp_path):
    prof = get_profile("director_v3")
    spec = _spec_with_image(None, resolution_preset="1280x720 (16:9) (横屏)")
    items = hd_builder.build_node_info_list(spec, {})
    res = _res_map(items, prof.director_node)
    assert (res["custom_width"], res["custom_height"]) == (1280, 720)
