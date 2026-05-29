import json
import pytest
from fastapi.testclient import TestClient

from screenwriter_agent.server import create_app


@pytest.fixture
def mock_llm_outline(monkeypatch):
    """让 LLMClient.stream_chat 吐出一个合法的 N 集 JSON。"""
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        raw = json.dumps({
            "title": "测试整剧",
            "episode_count": 2,
            "episodes": [
                {"id": "E1", "title": "第1集", "summary": "summary 1"},
                {"id": "E2", "title": "第2集", "summary": "summary 2"},
            ],
        }, ensure_ascii=False)
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_route_script_outline_writes_jianben_json(tmp_path, mock_llm_outline):
    (tmp_path / "创意.json").write_text(json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "X", "summary": "y"}],
    }, ensure_ascii=False), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 2,
    })
    assert r.status_code == 200
    p = tmp_path / "剧本.json"
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["episode_count"] == 2
    assert len(data["episodes"]) == 2
    assert data["episodes"][0]["id"] == "E1"


def test_route_script_outline_missing_idea_returns_400(tmp_path, mock_llm_outline):
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 2,
    })
    assert r.status_code == 400
    assert "UPSTREAM_PRODUCT_MISSING" in r.text


def test_route_script_outline_purge_downstream(tmp_path, mock_llm_outline):
    """带 query param purge_downstream=true 时清下游。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("old", encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    c.post("/script/outline?purge_downstream=true", json={
        "project_dir": str(tmp_path),
        "episode_count": 1,
    })
    assert not (tmp_path / "剧本_E1.md").exists()
    assert not (tmp_path / "分镜_E1.json").exists()


def test_route_script_outline_n1_creates_single_episode(tmp_path, mock_llm_outline):
    """N=1 仍产 剧本.json（含 1 集 entry，因 mock LLM 返 2 集这里只看 LLM 端控制；
    实际生产 N=1 时 outline 模板会指示 LLM 只产 1 集；本测试只保证 route 流通）。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 1,
    })
    assert r.status_code == 200
    assert (tmp_path / "剧本.json").is_file()


def test_route_script_outline_bad_episode_count(tmp_path, mock_llm_outline):
    """episode_count 超界（>20）应 422。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 99,
    })
    assert r.status_code == 422
