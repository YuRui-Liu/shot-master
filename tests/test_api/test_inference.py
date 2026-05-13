import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import create_app


SAMPLE_TPL = """---
name: Four
suggest_when: image_count == 4
variables:
  - {name: total_seconds, type: int, default: 16, label: T}
---
You are LTX engineer. T={{total_seconds}}.
"""

FAKE_OUTPUT = """## 1. global_prompt
```
GP HERE
```
## 2. timeline_data
```json
{"segments": []}
```
## 5. max_frames
```
192
```
"""


def _setup_env(tmp_path, monkeypatch):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "four.md").write_text(SAMPLE_TPL, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
    )
    monkeypatch.chdir(tmp_path)


def test_inference_single_image_success(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    app = create_app()
    client = TestClient(app)

    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/inference", json={
            "images": [str(img)],
            "template_id": "four",
            "supplement": {"total_seconds": 20},
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["global_prompt"] == "GP HERE"
    assert data["max_frames"] == 192
    assert "md_path" in data
    assert "json_path" in data
    assert Path(data["md_path"]).exists()
    assert Path(data["json_path"]).exists()


def test_inference_template_not_found(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    img = tmp_path / "x.png"
    img.write_bytes(b"\x00")
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/inference", json={
        "images": [str(img)],
        "template_id": "nonexistent",
        "supplement": {},
    })
    assert resp.status_code == 400
    assert "template" in resp.json()["detail"].lower()


def test_inference_image_not_found(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/inference", json={
        "images": [str(tmp_path / "missing.png")],
        "template_id": "four",
        "supplement": {},
    })
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower() or "exists" in resp.json()["detail"].lower()


def test_inference_provider_override(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nGEMINI_API_KEY=k\nANTHROPIC_API_KEY=ak\n"
    )
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    app = create_app()
    client = TestClient(app)
    with patch("app.providers.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = MagicMock(
            content=[MagicMock(text=FAKE_OUTPUT)]
        )
        resp = client.post("/api/inference", json={
            "images": [str(img)],
            "template_id": "four",
            "supplement": {},
            "override": {"provider": "anthropic", "model": "claude-opus-4-7"},
        })
    assert resp.status_code == 200
    assert resp.json()["meta"]["provider"] == "anthropic"
    assert resp.json()["meta"]["model"] == "claude-opus-4-7"
