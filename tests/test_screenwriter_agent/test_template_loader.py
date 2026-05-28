import pytest
from pathlib import Path
from screenwriter_agent.core.template_loader import load_template, BUILTIN_IDS


def test_builtin_ids_set():
    assert set(BUILTIN_IDS) == {"ideate", "script", "storyboard",
                                "character_ref", "grid_prompt"}


def test_load_builtin_returns_text(tmp_path):
    # builtin 路径在 screenwriter_agent/templates/，不存在则跳过该断言
    for tid in BUILTIN_IDS:
        try:
            text, source = load_template(tid, project_dir=tmp_path)
            assert isinstance(text, str) and len(text) > 0
            assert source in ("project", "builtin")
        except FileNotFoundError:
            pytest.skip(f"builtin {tid} not yet written (Task 16)")


def test_project_override_wins(tmp_path):
    proj_tpl = tmp_path / ".agent" / "templates" / "ideate.md"
    proj_tpl.parent.mkdir(parents=True)
    proj_tpl.write_text("override-content", encoding="utf-8")
    text, source = load_template("ideate", project_dir=tmp_path)
    assert text == "override-content"
    assert source == "project"


def test_unknown_id_raises(tmp_path):
    with pytest.raises(ValueError):
        load_template("nonsense", project_dir=tmp_path)
