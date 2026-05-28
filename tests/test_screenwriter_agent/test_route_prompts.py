from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_prompts_missing_storyboard_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/prompts", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in ("UPSTREAM_PRODUCT_MISSING", "PROJECT_DIR_NOT_FOUND")
