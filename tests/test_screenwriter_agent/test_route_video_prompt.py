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


def test_write_video_output_single_file(tmp_path):
    """write_video_output 写单个 shots.json（含 global_prompt），不写 global.md。"""
    from screenwriter_agent.routes.video_prompt import write_video_output
    data = {"global_prompt": "GP",
            "shots": [{"shot_id": "S01", "local_prompt": "x", "duration_s": 4.0}]}
    rel = write_video_output(tmp_path, data)
    sj = tmp_path / "shots.json"
    assert sj.is_file()
    assert not (tmp_path / "global.md").exists()
    import json as _j
    obj = _j.loads(sj.read_text(encoding="utf-8"))
    assert obj["global_prompt"] == "GP"
    assert obj["shots"][0]["shot_id"] == "S01"
    assert rel.endswith("shots.json")
