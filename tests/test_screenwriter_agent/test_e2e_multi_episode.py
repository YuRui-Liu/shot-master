"""N=1 / N=3 端到端流程（mock LLM）。"""
import json
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


@pytest.fixture
def mock_llm_universal(monkeypatch):
    """根据消息内容判断该返大纲 JSON / episode md / storyboard JSON。"""
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        content = "\n".join(m.get("content", "") for m in messages)
        if "集索引" in content:
            # /script/outline → 纯 JSON（json_object mode）
            raw = json.dumps({
                "title": "x", "episode_count": 3,
                "episodes": [{"id": f"E{i}", "title": f"t{i}", "summary": "s"}
                              for i in (1, 2, 3)],
            }, ensure_ascii=False)
        elif "本集大纲" in content:
            # /script/episode → markdown
            raw = "## 镜头 1\n…\n## 镜头 2\n…"
        elif "只输出一个 JSON 代码块" in content or "shotId" in content:
            # /storyboard → JSON
            raw = json.dumps({
                "title": "E", "aspectRatio": "9:16", "fps": 24,
                "totalDuration": 60, "globalStyle": "古风",
                "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾"}],
                "shots": [{"shotId": "S01", "duration": 6, "composition": "中景",
                            "description": "雨夜", "stylePrompt": "古风水墨"}],
            }, ensure_ascii=False)
        elif "template_id: ideate" in content:
            raw = "候选 1｜标题：守株待兔\n切入角度：反转\n摘要：xxx\n看点：yyy"
        else:
            raw = "default"
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_e2e_n1_chain(tmp_path, mock_llm_universal, monkeypatch):
    """N=1：创意 → 大纲 → 单集剧本 → 分镜（mock LLM）。"""
    monkeypatch.setenv("SCREENWRITER_LLM_API_KEY", "dummy")
    monkeypatch.setenv("SCREENWRITER_LLM_BASE_URL", "https://example.com")
    c = TestClient(create_app())
    # 1) 创意
    r = c.post("/ideate/chat", json={
        "project_dir": str(tmp_path),
        "context": {"core_idea": "守株待兔", "candidate_count": 1},
        "messages": [{"role": "user", "content": "出 1 个候选"}],
    })
    assert r.status_code == 200
    assert (tmp_path / "创意.json").is_file()
    # 2) 大纲
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 1,
    })
    assert r.status_code == 200
    assert (tmp_path / "剧本.json").is_file()
    # 3) 单集剧本
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert r.status_code == 200
    assert (tmp_path / "剧本_E1.md").is_file()
    # 4) 分镜
    r = c.post("/storyboard", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert r.status_code == 200
    assert (tmp_path / "分镜_E1.json").is_file()


def test_e2e_n3_chain(tmp_path, mock_llm_universal, monkeypatch):
    """N=3：完整三集流水线。"""
    monkeypatch.setenv("SCREENWRITER_LLM_API_KEY", "dummy")
    monkeypatch.setenv("SCREENWRITER_LLM_BASE_URL", "https://example.com")
    c = TestClient(create_app())
    # 创意
    c.post("/ideate/chat", json={
        "project_dir": str(tmp_path),
        "context": {"core_idea": "测试", "candidate_count": 1},
        "messages": [{"role": "user", "content": "出候选"}],
    })
    # 大纲（mock 返 3 集）
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 3,
    })
    assert r.status_code == 200
    si = json.loads((tmp_path / "剧本.json").read_text(encoding="utf-8"))
    assert si["episode_count"] == 3
    # 逐集剧本 + 分镜
    for i in (1, 2, 3):
        ep = f"E{i}"
        r = c.post("/script/episode", json={
            "project_dir": str(tmp_path),
            "episode_id": ep,
        })
        assert r.status_code == 200
        r = c.post("/storyboard", json={
            "project_dir": str(tmp_path),
            "episode_id": ep,
        })
        assert r.status_code == 200
    for i in (1, 2, 3):
        assert (tmp_path / f"剧本_E{i}.md").is_file()
        assert (tmp_path / f"分镜_E{i}.json").is_file()
