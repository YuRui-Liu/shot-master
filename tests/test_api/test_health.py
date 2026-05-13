from fastapi.testclient import TestClient
from app.main import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "provider" in data
    assert "model" in data


def test_root_serves_index_html(tmp_path, monkeypatch):
    # 创建假 web/index.html
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><body>HI</body></html>")
    monkeypatch.chdir(tmp_path)
    # .env 不存在也能跑
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"HI" in resp.content
