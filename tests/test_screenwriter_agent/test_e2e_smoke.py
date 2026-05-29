"""端到端 smoke：mock LLM 输出，依次跑 4 阶段，断言产物落盘 + 内容形状合规。"""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from screenwriter_agent.server import create_app


_STORYBOARD_JSON = {
    "title": "demo",
    "aspectRatio": "9:16",
    "fps": 24,
    "totalDuration": 12,
    "globalStyle": "古风水墨",
    "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾披肩长发"}],
    "shots": [
        {"shotId": "S01", "description": "雨夜画面", "duration": 6,
         "stylePrompt": "古风水墨，雨夜松林，狐妖立于树下，整体调性沉静"},
        {"shotId": "S02", "description": "书生撑伞", "duration": 6,
         "stylePrompt": "古风水墨，雨夜书生撑伞踱步，整体调性温润"},
    ],
}


@pytest.fixture
def mock_llm(monkeypatch):
    """把 LLMClient.stream_chat 替换为返回写死内容的迭代器。"""
    from screenwriter_agent.core import llm_client

    def _fake_stream(self, messages):
        text = ""
        all_text = " ".join(m.get("content", "") for m in messages)
        # 按模板 id 判断阶段（每个模板的 front-matter 里有 template_id: xxx）
        if "template_id: storyboard" in all_text or "只输出一个 JSON 代码块" in all_text:
            # storyboard 阶段
            text = "```json\n" + json.dumps(_STORYBOARD_JSON, ensure_ascii=False) + "\n```"
        elif "template_id: script" in all_text:
            # script 阶段
            text = "# 剧本信息\n标题: demo\n## 镜头 01\n画面：xxx\n## 镜头 02\n画面：yyy"
        elif "template_id: ideate" in all_text:
            # ideate 阶段
            text = "候选 1｜标题：躺平农夫\n切入角度：反转命运\n摘要：xxx\n看点：yyy\n\n候选 2｜标题：xxx"
        else:
            # character_ref / grid_prompt
            text = "角色参考图提示词或 N 宫格 prompt 占位"
        from screenwriter_agent.core.llm_client import StreamChunk
        for ch in text:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=text)

    monkeypatch.setattr(llm_client.LLMClient, "stream_chat", _fake_stream)


def test_e2e_chain(tmp_path, mock_llm, monkeypatch):
    monkeypatch.setenv("SCREENWRITER_LLM_API_KEY", "dummy")
    monkeypatch.setenv("SCREENWRITER_LLM_BASE_URL", "https://example.com")
    c = TestClient(create_app())

    # 1) /ideate/chat
    r = c.post("/ideate/chat", json={
        "project_dir": str(tmp_path),
        "context": {"core_idea": "古风狐妖", "candidate_count": 2},
        "messages": [{"role": "user", "content": "出 2 个候选"}],
    })
    assert r.status_code == 200
    assert (tmp_path / "创意.json").is_file()

    # 2) /ideate/select
    idea = json.loads((tmp_path / "创意.json").read_text(encoding="utf-8"))
    if idea.get("candidates"):
        cid = idea["candidates"][0]["id"]
        r = c.post("/ideate/select", json={
            "project_dir": str(tmp_path), "selected_id": cid})
        assert r.status_code == 200

    # 3) /script
    r = c.post("/script", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "剧本.md").is_file()

    # 4) /storyboard
    r = c.post("/storyboard", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "分镜.json").is_file()
    sb = json.loads((tmp_path / "分镜.json").read_text(encoding="utf-8"))
    assert sb["title"] == "demo"
    assert len(sb["shots"]) == 2

    # 5) /prompts
    r = c.post("/prompts", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "prompts").is_dir()
    n_grid = list((tmp_path / "prompts" / "N宫格").glob("S*.md")) if (tmp_path / "prompts" / "N宫格").is_dir() else []
    assert len(n_grid) >= 1
