import json
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_audio_prompt_missing_storyboard_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/audio_prompt",
               json={"project_dir": str(tmp_path), "episode_id": "E1"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UPSTREAM_PRODUCT_MISSING"


def test_audio_prompt_missing_project_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/audio_prompt",
               json={"project_dir": str(tmp_path / "x"), "episode_id": "E1"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "PROJECT_DIR_NOT_FOUND"


def test_audio_prompt_bad_episode_422(tmp_path):
    c = TestClient(create_app())
    r = c.post("/audio_prompt",
               json={"project_dir": str(tmp_path), "episode_id": "0"})
    assert r.status_code == 422
