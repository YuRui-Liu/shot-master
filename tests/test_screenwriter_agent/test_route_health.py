from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_health_returns_status_ok():
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["version"]
    assert set(j["default_models"].keys()) == {"ideate", "script", "storyboard", "prompts"}
