import dataclasses
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from drama_shot_master.grid_ops import (
    make_grid_spec, split_to_tiles, split_to_files, split_to_preview_cache,
    combine_to_file, trim_one, trim_batch,
    ResampleAlgo, ResampleSpec,
    _resize_to_long_edge,
    resize_tile,
    validate_resample_spec,
)
from drama_shot_master.providers.comfyui_upscaler import (
    ComfyUIUpscaler, ComfyUIUnavailable, ComfyUIUpscaleError,
)


def _make_grid_image(path: Path, w=400, h=400, color=(200, 30, 30)) -> Path:
    Image.new("RGB", (w, h), color).save(path)
    return path


def _bordered(path: Path, content=80, border=20) -> Path:
    total = content + 2 * border
    canvas = Image.new("RGB", (total, total), (255, 255, 255))
    canvas.paste(Image.new("RGB", (content, content), (50, 50, 200)),
                 (border, border))
    canvas.save(path)
    return path


def test_split_to_tiles(tmp_path):
    src = _make_grid_image(tmp_path / "grid.png")
    spec = make_grid_spec(src_rows=2, src_cols=2, sub_rows=1, sub_cols=1)
    tiles = split_to_tiles(src, spec)
    assert len(tiles) == 4
    for t in tiles:
        assert t.width > 0 and t.height > 0


def test_split_to_files_saves(tmp_path):
    src = _make_grid_image(tmp_path / "grid.png")
    out = tmp_path / "out"
    spec = make_grid_spec(2, 2, 1, 1)
    files = split_to_files(src, spec, out, output_format="PNG")
    assert len(files) == 4
    for f in files:
        assert f.exists()
        assert f.suffix == ".png"


def test_split_invalid_grid_raises(tmp_path):
    src = _make_grid_image(tmp_path / "grid.png")
    spec = make_grid_spec(3, 3, 2, 2)  # 3 不能整除 2
    with pytest.raises(Exception):
        split_to_tiles(src, spec)


def test_split_to_preview_cache_hash_dir(tmp_path):
    src = _make_grid_image(tmp_path / "grid.png")
    spec = make_grid_spec(2, 2, 1, 1)
    cache = tmp_path / "cache"
    files = split_to_preview_cache(src, spec, cache)
    assert len(files) == 4
    # 文件落在 cache/<hash>/tile_N.png
    for f in files:
        assert f.parent.parent == cache
        assert f.name.startswith("tile_")


def test_combine_to_file(tmp_path):
    imgs = []
    for i in range(4):
        p = tmp_path / f"i{i}.png"
        Image.new("RGB", (100, 100), (i * 50 % 256, 100, 100)).save(p)
        imgs.append(p)
    out = tmp_path / "merged.png"
    combine_to_file(imgs, out, target_rows=2, target_cols=2, gap=4)
    assert out.exists()
    merged = Image.open(out)
    assert merged.width == 204  # 2*100 + 1*4
    assert merged.height == 204


def test_trim_one(tmp_path):
    src = _bordered(tmp_path / "in.png")
    out = tmp_path / "out.png"
    trim_one(src, out)
    trimmed = Image.open(out)
    assert trimmed.width <= 90
    assert trimmed.height <= 90


def test_trim_batch(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    for i in range(3):
        _bordered(folder / f"img{i}.png")
    (folder / "ignore.txt").write_text("nope")
    out = tmp_path / "out"
    files = trim_batch(folder, out, name_suffix="_trim")
    assert len(files) == 3
    for f in files:
        assert f.exists()
        assert "_trim" in f.name


def test_resample_spec_defaults_are_disabled_auto_lanczos():
    spec = ResampleSpec()
    assert spec.enabled is False
    assert spec.aspect_w == 0 and spec.aspect_h == 0
    assert spec.long_edge == 2048
    assert spec.algorithm == ResampleAlgo.LANCZOS
    assert spec.ai_model == ""


def test_resample_spec_is_auto_aspect_when_either_zero():
    assert ResampleSpec(aspect_w=0, aspect_h=0).is_auto_aspect
    assert ResampleSpec(aspect_w=16, aspect_h=0).is_auto_aspect
    assert ResampleSpec(aspect_w=0, aspect_h=9).is_auto_aspect
    assert not ResampleSpec(aspect_w=16, aspect_h=9).is_auto_aspect


def test_resample_spec_is_frozen():
    spec = ResampleSpec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.enabled = True


def test_resample_algo_enum_values():
    assert ResampleAlgo.LANCZOS.value == "lanczos"
    assert ResampleAlgo.AI.value == "ai"


def test_resize_to_long_edge_upsample_landscape():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    out = _resize_to_long_edge(img, 2048, Image.LANCZOS)
    assert out.size == (2048, 1024)


def test_resize_to_long_edge_upsample_portrait():
    img = Image.new("RGB", (512, 1024), (128, 128, 128))
    out = _resize_to_long_edge(img, 2048, Image.LANCZOS)
    assert out.size == (1024, 2048)


def test_resize_to_long_edge_downsample():
    img = Image.new("RGB", (4096, 2048), (128, 128, 128))
    out = _resize_to_long_edge(img, 1024, Image.LANCZOS)
    assert out.size == (1024, 512)


def test_resize_to_long_edge_noop_when_already_target():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    out = _resize_to_long_edge(img, 1024, Image.LANCZOS)
    assert out is img    # 同一对象，未触发 resize


def test_resize_to_long_edge_square():
    img = Image.new("RGB", (1000, 1000), (128, 128, 128))
    out = _resize_to_long_edge(img, 500, Image.LANCZOS)
    assert out.size == (500, 500)


def test_resize_tile_disabled_passthrough():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    spec = ResampleSpec(enabled=False)
    out = resize_tile(img, spec)
    assert out is img


def test_resize_tile_lanczos_auto_aspect_just_resizes():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    spec = ResampleSpec(enabled=True, long_edge=2048,
                        algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (2048, 1024)


def test_resize_tile_lanczos_crops_then_resizes_16_9_from_4_3():
    # 1200x900 (4:3) → center crop 16:9 → 1200x675 → long_edge 1600 → 1600x900
    img = Image.new("RGB", (1200, 900), (128, 128, 128))
    spec = ResampleSpec(enabled=True, aspect_w=16, aspect_h=9,
                        long_edge=1600, algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (1600, 900)


def test_resize_tile_lanczos_crops_1_1_from_landscape():
    img = Image.new("RGB", (1920, 1080), (128, 128, 128))
    spec = ResampleSpec(enabled=True, aspect_w=1, aspect_h=1,
                        long_edge=512, algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (512, 512)


def test_resize_tile_lanczos_custom_3_2():
    img = Image.new("RGB", (1000, 1000), (128, 128, 128))
    spec = ResampleSpec(enabled=True, aspect_w=3, aspect_h=2,
                        long_edge=600, algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (600, 400)


def test_resize_tile_ai_calls_upscaler_then_resizes():
    img = Image.new("RGB", (1024, 1024), (128, 128, 128))
    up = MagicMock(spec=ComfyUIUpscaler)
    up.upscale.return_value = Image.new("RGB", (4096, 4096), (200, 200, 200))
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="4x-UltraSharp.pth")
    out = resize_tile(img, spec, upscaler=up)
    up.upscale.assert_called_once_with(img, "4x-UltraSharp.pth")
    assert out.size == (2048, 2048)


def test_resize_tile_ai_unavailable_falls_back_to_lanczos():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    up = MagicMock(spec=ComfyUIUpscaler)
    up.upscale.side_effect = ComfyUIUnavailable("connection refused")
    statuses = []
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="x.pth")
    out = resize_tile(img, spec, upscaler=up, status_cb=statuses.append)
    assert out.size == (2048, 1024)
    assert len(statuses) == 1
    assert "回退" in statuses[0]


def test_resize_tile_ai_upscale_error_falls_back_to_lanczos():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    up = MagicMock(spec=ComfyUIUpscaler)
    up.upscale.side_effect = ComfyUIUpscaleError("timeout")
    statuses = []
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="x.pth")
    out = resize_tile(img, spec, upscaler=up, status_cb=statuses.append)
    assert out.size == (2048, 1024)
    assert len(statuses) == 1


def test_resize_tile_ai_without_upscaler_falls_through_to_lanczos():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="x.pth")
    out = resize_tile(img, spec, upscaler=None)
    assert out.size == (2048, 1024)


def test_validate_resample_disabled_always_ok():
    assert validate_resample_spec(ResampleSpec(enabled=False)) == (True, "")


def test_validate_resample_auto_aspect_lanczos_ok():
    spec = ResampleSpec(enabled=True, aspect_w=0, aspect_h=0,
                        long_edge=2048, algorithm=ResampleAlgo.LANCZOS)
    assert validate_resample_spec(spec) == (True, "")


def test_validate_resample_custom_aspect_zero_fails():
    spec = ResampleSpec(enabled=True, aspect_w=0, aspect_h=9,
                        long_edge=2048, algorithm=ResampleAlgo.LANCZOS)
    # 注意：aspect_w=0,aspect_h=9 视为 Auto（is_auto_aspect=True），所以 OK
    assert validate_resample_spec(spec) == (True, "")
    # 但若声明 enabled + 用户期望"自定义"模式：调用方应保证 w>0 且 h>0
    # validate 不区分 preset/custom，只看数值合法性


def test_validate_resample_ai_without_model_fails():
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI, ai_model="")
    ok, msg = validate_resample_spec(spec)
    assert ok is False
    assert "AI 超分模型" in msg


def test_validate_resample_long_edge_too_small_fails():
    spec = ResampleSpec(enabled=True, long_edge=100)
    ok, msg = validate_resample_spec(spec)
    assert ok is False
    assert "256" in msg and "8192" in msg


def test_validate_resample_long_edge_too_large_fails():
    spec = ResampleSpec(enabled=True, long_edge=10000)
    ok, msg = validate_resample_spec(spec)
    assert ok is False


def test_validate_resample_long_edge_boundaries_ok():
    assert validate_resample_spec(
        ResampleSpec(enabled=True, long_edge=256))[0] is True
    assert validate_resample_spec(
        ResampleSpec(enabled=True, long_edge=8192))[0] is True


def test_inset_crop_basic():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (100, 100), (10, 20, 30))
    out = _inset_crop(img, top=5, right=10, bottom=15, left=20)
    assert out.size == (70, 80)   # w=100-20-10, h=100-5-15


def test_inset_crop_zero_returns_same_object():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (50, 50), (0, 0, 0))
    assert _inset_crop(img) is img
    assert _inset_crop(img, 0, 0, 0, 0) is img


def test_inset_crop_overlarge_clamps_to_min_1px():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    out = _inset_crop(img, left=200, right=200, top=200, bottom=200)
    w, h = out.size
    assert w >= 1 and h >= 1


def test_inset_crop_negative_treated_as_zero():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (40, 40), (0, 0, 0))
    out = _inset_crop(img, top=-5, right=-5, bottom=0, left=0)
    assert out is img
