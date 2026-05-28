import json
from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_ideate_select_writes_selected_id(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t1"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select", json={"project_dir": str(tmp_path),
                                       "selected_id": "c1"})
    assert r.status_code == 200
    on_disk = json.loads((tmp_path / "idea.json").read_text(encoding="utf-8"))
    assert on_disk["selected_id"] == "c1"


def test_ideate_select_unknown_id_400(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select", json={"project_dir": str(tmp_path),
                                       "selected_id": "nope"})
    assert r.status_code == 400
