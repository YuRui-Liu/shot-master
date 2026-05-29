import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_script_missing_idea_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/script", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in ("UPSTREAM_PRODUCT_MISSING", "PROJECT_DIR_NOT_FOUND")


def test_script_unselected_idea_400(tmp_path):
    (tmp_path / "创意.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 400
