from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


SAMPLE = """---
name: T1
suggest_when: image_count == 1
variables: []
---
body line
"""


def _setup(tmp_path, monkeypatch):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "t1.md").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)


def test_list_templates(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "t1"
    assert data[0]["name"] == "T1"


def test_get_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/templates/t1")
    assert resp.status_code == 200
    data = resp.json()
    assert "body line" in data["body"]
    assert data["suggest_when"] == "image_count == 1"


def test_recommend_template_endpoint(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/templates/recommend?image_count=1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "t1"


def test_create_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/templates", json={
        "id": "new1",
        "raw_markdown": "---\nname: New\nvariables: []\n---\nhello",
    })
    assert resp.status_code == 200
    assert (tmp_path / "templates" / "new1.md").exists()


def test_update_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.put("/api/templates/t1", json={
        "raw_markdown": "---\nname: T1Modified\nvariables: []\n---\nnew body"
    })
    assert resp.status_code == 200
    assert "T1Modified" in (tmp_path / "templates" / "t1.md").read_text(encoding="utf-8")


def test_delete_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.delete("/api/templates/t1")
    assert resp.status_code == 200
    assert not (tmp_path / "templates" / "t1.md").exists()


def test_create_conflict(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/templates", json={
        "id": "t1",
        "raw_markdown": "---\nname: x\n---\n",
    })
    assert resp.status_code == 409
