import json
from pathlib import Path
import pytest

from screenwriter_agent.core.project_scanner import scan_project, ProjectState


def test_empty_dir(tmp_path):
    st = scan_project(tmp_path)
    assert st.status == "empty"
    assert not st.stages["ideate"]["done"]
    assert st.recommended_next == "ideate"


def test_idea_without_selected(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [
            {"id": "c1", "title": "t1"}], "selected_id": ""}),
        encoding="utf-8")
    st = scan_project(tmp_path)
    assert st.status == "ideating"
    assert st.stages["ideate"]["done"] is False


def test_idea_selected_no_script(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [
            {"id": "c1", "title": "t1"}], "selected_id": "c1"}),
        encoding="utf-8")
    st = scan_project(tmp_path)
    assert st.status == "script_pending"
    assert st.stages["ideate"]["done"] is True
    assert st.recommended_next == "script"


def test_full_chain(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t"}],
        "selected_id": "c1"}), encoding="utf-8")
    (tmp_path / "剧本.md").write_text("# 剧本信息\n标题: x\n", encoding="utf-8")
    (tmp_path / "分镜.json").write_text(json.dumps({"title": "x", "shots": [{}]}), encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "S1.md").write_text("p", encoding="utf-8")
    st = scan_project(tmp_path)
    assert st.status == "done"
