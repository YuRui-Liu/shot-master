import json
import pytest
from fastapi.testclient import TestClient

from screenwriter_agent.server import create_app


@pytest.fixture
def mock_llm_episode(monkeypatch):
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        md = "## 镜头 1\n雨夜画面…\n## 镜头 2\n书生撑伞…"
        for ch in md:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=md)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def _setup_with_index(tmp_path):
    (tmp_path / "创意.json").write_text(json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "X"}],
    }), encoding="utf-8")
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 2,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
        ],
    }), encoding="utf-8")


def test_route_script_episode_writes_episode_md(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert r.status_code == 200
    assert (tmp_path / "剧本_E1.md").is_file()
    assert "## 镜头" in (tmp_path / "剧本_E1.md").read_text(encoding="utf-8")


def test_route_script_episode_missing_index_returns_400(tmp_path, mock_llm_episode):
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert r.status_code == 400 or "UPSTREAM_PRODUCT_MISSING" in r.text


def test_route_script_episode_unknown_episode_returns_400(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E99",
    })
    assert r.status_code == 400
    assert "EPISODE_NOT_FOUND" in r.text


def test_route_script_episode_purge_downstream(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    c.post("/script/episode?purge_downstream=true", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert not (tmp_path / "分镜_E1.json").exists()


def test_route_script_episode_bad_id_pattern(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "e1",
    })
    assert r.status_code == 422
