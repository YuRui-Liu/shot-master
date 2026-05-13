import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


def test_save_edited_overwrites_md_json(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "_prompts"
    out.mkdir()
    md = out / "x.md"
    md.write_text("old")
    js = out / "x.json"
    js.write_text("{}")

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/inference/save", json={
        "md_path": str(md),
        "json_path": str(js),
        "fields": {
            "global_prompt": "NEW GP",
            "timeline_data": "{}",
            "local_prompts": "LP",
            "segment_lengths": [10],
            "max_frames": 10,
            "frame_indices": [0, -1, -1, -1, -1],
            "strengths": [1, 0, 0, 0, 0],
            "epsilon": 0.1,
            "notes": "n",
        },
        "meta": {"template_id": "t", "provider": "p", "model": "m"},
    })
    assert resp.status_code == 200
    assert "NEW GP" in md.read_text(encoding="utf-8")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["global_prompt"] == "NEW GP"
