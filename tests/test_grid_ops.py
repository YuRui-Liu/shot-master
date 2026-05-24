import dataclasses
from pathlib import Path

import pytest
from PIL import Image

from app.grid_ops import (
    make_grid_spec, split_to_tiles, split_to_files, split_to_preview_cache,
    combine_to_file, trim_one, trim_batch,
    ResampleAlgo, ResampleSpec,
    _resize_to_long_edge,
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
