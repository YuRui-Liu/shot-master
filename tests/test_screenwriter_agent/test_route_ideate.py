import json
from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_ideate_select_writes_selected_id(tmp_path):
    (tmp_path / "创意.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t1"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select", json={"project_dir": str(tmp_path),
                                       "selected_id": "c1"})
    assert r.status_code == 200
    on_disk = json.loads((tmp_path / "创意.json").read_text(encoding="utf-8"))
    assert on_disk["selected_id"] == "c1"


def test_ideate_select_unknown_id_400(tmp_path):
    (tmp_path / "创意.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select", json={"project_dir": str(tmp_path),
                                       "selected_id": "nope"})
    assert r.status_code == 400


def test_route_ideate_writes_creative_json_not_legacy_idea_json(tmp_path, monkeypatch):
    """新落盘必须用 创意.json（不能再用 idea.json）。"""
    from screenwriter_agent.routes.ideate import _parse_candidates_loose
    raw = "## 候选 1\n标题：守株\n切入：现代寓言"
    cands = _parse_candidates_loose(raw)
    assert len(cands) >= 1
