import json
from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_video_prompt_missing_storyboard_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/video_prompt",
               json={"project_dir": str(tmp_path), "episode_id": "E1"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UPSTREAM_PRODUCT_MISSING"


def test_video_prompt_missing_project_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/video_prompt",
               json={"project_dir": str(tmp_path / "nonexistent"), "episode_id": "E1"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "PROJECT_DIR_NOT_FOUND"


def test_video_prompt_bad_episode_id_422(tmp_path):
    c = TestClient(create_app())
    r = c.post("/video_prompt",
               json={"project_dir": str(tmp_path), "episode_id": "bad"})
    assert r.status_code == 422
