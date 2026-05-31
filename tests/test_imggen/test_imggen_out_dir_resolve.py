"""出图输出目录解析：空时回退到主面板「输出目录」(last_output_dir)，而非 cwd。"""
from pathlib import Path
from types import SimpleNamespace

from drama_shot_master.ui.panels.imggen_panel import resolve_imggen_out_dir


def test_falls_back_to_main_output_dir():
    cfg = SimpleNamespace(imggen_output_dir="", last_output_dir="/tmp/proj")
    assert resolve_imggen_out_dir(cfg) == Path("/tmp/proj") / "imggen"


def test_prefers_own_imggen_dir():
    cfg = SimpleNamespace(imggen_output_dir="/a/b", last_output_dir="/tmp/proj")
    assert resolve_imggen_out_dir(cfg) == Path("/a/b") / "imggen"


def test_cwd_as_last_resort():
    cfg = SimpleNamespace(imggen_output_dir="", last_output_dir=None)
    assert resolve_imggen_out_dir(cfg) == Path(".") / "imggen"
