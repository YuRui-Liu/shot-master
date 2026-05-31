"""media_agent 配乐端点 — 无 Qt、无网络。

compose_prompt 真实调纯函数；generate_bgm/batch 注入假 client 验证落盘/批量管线。
"""
from pathlib import Path

import media_agent.routes.soundtrack as st_mod
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


class _FakeRHClient:
    """假 RunningHub 客户端：create/query/download 全本地，不触网。"""

    def __init__(self):
        self.calls = []

    def create_task(self, *, workflow_id, node_info_list=None, **kw):
        self.calls.append((workflow_id, node_info_list))
        return "task-abc"

    def query_task(self, task_id):
        return {"status": "SUCCESS",
                "results": [{"url": "http://fake/bgm.mp3"}]}

    def download_file(self, url, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FAKE_MP3_BYTES")
        return dest


def _patch(monkeypatch):
    monkeypatch.setattr(st_mod, "_client_factory", lambda cfg: _FakeRHClient())
    monkeypatch.setattr(st_mod, "_load_cfg", lambda: object())


# ---------- compose_prompt：真实纯函数 ----------

def test_compose_prompt_basic():
    r = client.post("/soundtrack/compose_prompt", json={
        "global_style": "cinematic suspense",
        "emotion": {"labels": ["tense", "dark"], "arousal": 0.8},
        "duration": 25.0,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["music_prompt"]
    assert "cinematic suspense" in body["music_prompt"]
    assert "tense" in body["music_prompt"]
    ace = body["acestep"]
    assert ace["tags"] and "cinematic suspense" in ace["tags"]
    assert isinstance(ace["bpm"], int) and ace["bpm"] > 0
    assert ace["duration"] == 25.0


def test_compose_prompt_no_emotion():
    r = client.post("/soundtrack/compose_prompt", json={
        "global_style": "soft piano", "duration": 12.0})
    assert r.status_code == 200, r.text
    assert "soft piano" in r.json()["music_prompt"]


def test_compose_prompt_empty_style_400():
    r = client.post("/soundtrack/compose_prompt", json={
        "global_style": "   ", "duration": 10.0})
    assert r.status_code == 400


# ---------- generate_bgm：注入假 client，验证落盘 ----------

def test_generate_bgm_saves_candidates(tmp_path, monkeypatch):
    _patch(monkeypatch)
    out = tmp_path / "bgm"
    r = client.post("/soundtrack/generate_bgm", json={
        "workflow_id": "wf-1", "out_dir": str(out),
        "seeds": [1, 2],
        "global_style": "epic orchestral", "duration": 20.0,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["acestep"]["tags"]
    cands = body["candidates"]
    assert len(cands) == 2
    for c in cands:
        p = Path(c["path"])
        assert p.exists() and p.read_bytes() == b"FAKE_MP3_BYTES"
        assert c["seed"] in (1, 2)


def test_generate_bgm_explicit_tags(tmp_path, monkeypatch):
    _patch(monkeypatch)
    out = tmp_path / "bgm2"
    r = client.post("/soundtrack/generate_bgm", json={
        "workflow_id": "wf-2", "out_dir": str(out), "seeds": [7],
        "tags": "custom tags", "bpm": 100, "duration": 15.0,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["acestep"]["tags"] == "custom tags"
    assert body["acestep"]["bpm"] == 100
    assert len(body["candidates"]) == 1


def test_generate_bgm_missing_inputs_400(tmp_path, monkeypatch):
    _patch(monkeypatch)
    # 既无三元组也无 global_style → 400
    r = client.post("/soundtrack/generate_bgm", json={
        "workflow_id": "wf-3", "out_dir": str(tmp_path), "seeds": [1]})
    assert r.status_code == 400


def test_generate_bgm_empty_workflow_400(tmp_path, monkeypatch):
    _patch(monkeypatch)
    r = client.post("/soundtrack/generate_bgm", json={
        "workflow_id": "  ", "out_dir": str(tmp_path), "seeds": [1],
        "tags": "t", "bpm": 90, "duration": 10.0})
    assert r.status_code == 400


# ---------- batch_generate：SSE ----------

def test_batch_generate_sse(tmp_path, monkeypatch):
    _patch(monkeypatch)
    r = client.post("/soundtrack/batch_generate", json={"items": [
        {"workflow_id": "wf", "out_dir": str(tmp_path / "a"), "seeds": [1],
         "tags": "t1", "bpm": 90, "duration": 10.0},
        {"workflow_id": "wf", "out_dir": str(tmp_path / "b"), "seeds": [1],
         "tags": "t2", "bpm": 95, "duration": 12.0},
    ]})
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: progress" in body
    assert body.count("event: item_done") == 2
    assert "event: complete" in body
