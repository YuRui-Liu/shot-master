from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import create_app


def _setup(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
        "ANTHROPIC_API_KEY=ak\n"
    )
    monkeypatch.chdir(tmp_path)


def test_get_settings_returns_current(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_provider"] == "gemini"
    assert data["current_model"] == "gemini-2.5-pro"
    assert "providers" in data
    names = {p["name"] for p in data["providers"]}
    assert "gemini" in names
    assert "anthropic" in names
    assert "openai" in names  # openai_compat preset 展开 endpoint 名


def test_update_settings_persists(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.put("/api/settings", json={
        "current_provider": "anthropic",
        "current_model": "claude-opus-4-7",
    })
    assert resp.status_code == 200
    assert (tmp_path / "settings.json").exists()
    resp2 = client.get("/api/settings")
    assert resp2.json()["current_provider"] == "anthropic"


def test_ping_provider_success(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text="pong")
        resp = client.post("/api/settings/ping", json={
            "provider": "gemini", "model": "gemini-2.5-pro",
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ping_provider_failure(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.side_effect = RuntimeError("auth fail")
        resp = client.post("/api/settings/ping", json={
            "provider": "gemini", "model": "gemini-2.5-pro",
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "auth fail" in resp.json()["error"]
