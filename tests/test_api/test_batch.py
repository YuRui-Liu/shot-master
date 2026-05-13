import json
import re
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import create_app


SAMPLE_TPL = """---
name: Single
suggest_when: image_count == 1
variables: []
---
You are an image describer.
"""

FAKE_OUTPUT = """## 1. global_prompt
```
GP
```
"""


def _setup(tmp_path, monkeypatch, n_images=3):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "single.md").write_text(SAMPLE_TPL, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
    )
    folder = tmp_path / "imgs"
    folder.mkdir()
    for i in range(n_images):
        (folder / f"ep01_s{i:02d}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    monkeypatch.chdir(tmp_path)
    return folder


def test_batch_creates_task_and_streams_events(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch, n_images=2)
    app = create_app()
    client = TestClient(app)

    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/batch", json={
            "folder": str(folder),
            "template_id": "single",
            "supplement": {},
        })
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]
        assert task_id

        # 读 SSE
        with client.stream("GET", f"/api/batch/{task_id}/stream") as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")

    # body 是 SSE 格式： "event: progress\ndata: {...}\n\n..."
    events = re.findall(r"event:\s*(\S+)\s*\ndata:\s*({.*?})\s*\n\n", body)
    assert len(events) >= 4   # 2 progress + 2 item_done + 1 complete
    types = [e[0] for e in events]
    assert types.count("progress") == 2
    assert types.count("item_done") == 2
    assert "complete" in types
    last = json.loads(events[-1][1])
    assert last["ok"] == 2
    assert last["failed"] == 0


def test_batch_invalid_folder(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/batch", json={
        "folder": str(tmp_path / "no_such_folder"),
        "template_id": "single",
        "supplement": {},
    })
    assert resp.status_code == 400


def test_batch_skips_existing_outputs(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch, n_images=2)
    out = folder / "_prompts"
    out.mkdir()
    # 让 ep01_s00.md 已经存在
    (out / "ep01_s00.md").write_text("preexisting", encoding="utf-8")
    (out / "ep01_s00.json").write_text("{}", encoding="utf-8")

    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/batch", json={
            "folder": str(folder),
            "template_id": "single",
            "supplement": {},
            "skip_existing": True,
        })
        task_id = resp.json()["task_id"]
        with client.stream("GET", f"/api/batch/{task_id}/stream") as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")

    events = re.findall(r"event:\s*(\S+)\s*\ndata:\s*({.*?})\s*\n\n", body)
    # 应该有 1 个被 skip，1 个被处理
    item_dones = [json.loads(e[1]) for e in events if e[0] == "item_done"]
    statuses = [d["status"] for d in item_dones]
    assert "skipped" in statuses


def test_batch_per_image_supplement(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch, n_images=2)
    # 为 ep01_s00.png 配一份同名 .md（作为剧本）
    (folder / "ep01_s00.md").write_text("这是 ep01_s00 的剧本", encoding="utf-8")
    # 为 ep01_s01.png 配一份同名 .json
    (folder / "ep01_s01.json").write_text('{"style_note": "暗调"}', encoding="utf-8")

    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/batch", json={
            "folder": str(folder),
            "template_id": "single",
            "supplement": {},
            "per_image_supplement": True,
        })
        task_id = resp.json()["task_id"]
        with client.stream("GET", f"/api/batch/{task_id}/stream") as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")
    # 验证 2 张都成功
    events = re.findall(r"event:\s*(\S+)\s*\ndata:\s*({.*?})\s*\n\n", body)
    last = json.loads(events[-1][1])
    assert last["ok"] == 2
