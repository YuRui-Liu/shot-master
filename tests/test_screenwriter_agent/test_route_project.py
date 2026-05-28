from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_project_dir_not_found_400(tmp_path):
    c = TestClient(create_app())
    r = c.get("/project", params={"dir": str(tmp_path / "ghost")})
    assert r.status_code == 400
    j = r.json()
    assert j["error"]["code"] == "PROJECT_DIR_NOT_FOUND"


def test_project_empty_dir_returns_state(tmp_path):
    c = TestClient(create_app())
    r = c.get("/project", params={"dir": str(tmp_path)})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "empty"
    assert j["stages"]["ideate"]["done"] is False
    assert j["recommended_next"] == "ideate"
