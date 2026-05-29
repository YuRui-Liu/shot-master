"""template_loader 单测（project > global > builtin 三级优先级）。"""
import os
from pathlib import Path
import pytest

from screenwriter_agent.templates import template_loader as tl

# ── 原有测试（兼容新路径）──────────────────────────────────────────────────

def test_builtin_ids_set():
    assert set(tl.BUILTIN_IDS) == {"ideate", "script", "script_outline",
                                   "script_episode", "storyboard",
                                   "character_ref", "grid_prompt",
                                   "video_prompt"}


def test_load_builtin_returns_text(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    for tid in tl.BUILTIN_IDS:
        text, source = tl.load_template(tid, project_dir=str(tmp_path / "proj"))
        assert isinstance(text, str) and len(text) > 0
        assert source in ("project", "builtin")


def test_project_override_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    proj_tpl = tmp_path / ".agent" / "templates" / "ideate.md"
    proj_tpl.parent.mkdir(parents=True)
    proj_tpl.write_text("override-content", encoding="utf-8")
    text, source = tl.load_template("ideate", project_dir=tmp_path)
    assert text == "override-content"
    assert source == "project"


def test_unknown_id_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    with pytest.raises(ValueError):
        tl.load_template("nonsense", project_dir=tmp_path)


# ── 新增：global 层测试 ───────────────────────────────────────────────────

def test_load_falls_back_to_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    text, src = tl.load_template("ideate", project_dir=str(tmp_path / "proj"))
    assert src == "builtin"
    assert len(text) > 0


def test_global_override_takes_precedence_over_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    (tmp_path / "global").mkdir(parents=True)
    (tmp_path / "global" / "ideate.md").write_text("MY GLOBAL", encoding="utf-8")
    text, src = tl.load_template("ideate", project_dir=str(tmp_path / "proj"))
    assert src == "global"
    assert text == "MY GLOBAL"


def test_project_override_beats_global(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    (tmp_path / "global").mkdir(parents=True)
    (tmp_path / "global" / "ideate.md").write_text("GLOBAL", encoding="utf-8")
    proj = tmp_path / "proj"
    (proj / ".agent" / "templates").mkdir(parents=True)
    (proj / ".agent" / "templates" / "ideate.md").write_text("PROJ", encoding="utf-8")
    text, src = tl.load_template("ideate", project_dir=str(proj))
    assert src == "project"
    assert text == "PROJ"


def test_write_global_template_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    tl.write_global_template("script", "NEW CONTENT")
    p = tmp_path / "global" / "script.md"
    assert p.is_file()
    assert p.read_text(encoding="utf-8") == "NEW CONTENT"


def test_write_global_template_empty_deletes(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    (tmp_path / "global").mkdir()
    (tmp_path / "global" / "script.md").write_text("X", encoding="utf-8")
    tl.write_global_template("script", "")
    assert not (tmp_path / "global" / "script.md").exists()


def test_write_unknown_tid_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    with pytest.raises(ValueError):
        tl.write_global_template("unknown_tid", "x")
