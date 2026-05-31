"""media_agent 出图端点 — 无 Qt、无网络。注入假 provider 验证存盘/批量管线。"""
import media_agent.routes.imggen as imggen_mod
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


class _FakeProvider:
    def generate(self, prompt, references, *, size, n):
        return [b"FAKE_PNG_BYTES_%d" % i for i in range(n)]


def _patch(monkeypatch):
    monkeypatch.setattr(imggen_mod, "_provider_factory", lambda cfg: _FakeProvider())
    # 避免 load_config 触网/读盘异常影响（假工厂忽略 cfg）
    monkeypatch.setattr(imggen_mod, "_load_cfg", lambda: object())


def test_generate_saves_bytes(tmp_path, monkeypatch):
    _patch(monkeypatch)
    out = tmp_path / "g"
    r = client.post("/imggen/generate", json={
        "prompt": "一只赛博朋克的猫", "size": "512x512", "n": 2,
        "out_dir": str(out), "base_name": "cat", "ext": "png"})
    assert r.status_code == 200, r.text
    outputs = r.json()["outputs"]
    assert len(outputs) == 2
    from pathlib import Path
    for p in outputs:
        assert Path(p).exists() and Path(p).read_bytes().startswith(b"FAKE_PNG")


def test_generate_empty_prompt_400(tmp_path, monkeypatch):
    _patch(monkeypatch)
    r = client.post("/imggen/generate", json={
        "prompt": "   ", "out_dir": str(tmp_path), "n": 1})
    assert r.status_code == 400


def test_batch_generate_sse(tmp_path, monkeypatch):
    _patch(monkeypatch)
    out = tmp_path / "b"
    r = client.post("/imggen/batch_generate", json={"items": [
        {"prompt": "p1", "out_dir": str(out), "base_name": "a", "n": 1},
        {"prompt": "p2", "out_dir": str(out), "base_name": "b", "n": 1},
    ]})
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: progress" in body
    assert body.count("event: item_done") == 2
    assert "event: complete" in body
