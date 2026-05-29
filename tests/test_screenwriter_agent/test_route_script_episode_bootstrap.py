"""单集快路径：无 剧本.json 时从已选创意 bootstrap 最小索引（仅 E1）。"""
import json
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def _write_idea(tmp_path, selected="c1"):
    idea = {
        "input": {},
        "candidates": [
            {"id": "c1", "title": "守株待兔", "summary": "一个关于等待的故事",
             "highlights": "反转结局"},
        ],
        "selected_id": selected,
    }
    (tmp_path / "创意.json").write_text(
        json.dumps(idea, ensure_ascii=False), encoding="utf-8")


def test_episode_e1_bootstraps_index_when_missing(tmp_path):
    """无 剧本.json + 有已选创意 + E1 → 自举索引，不报 UPSTREAM_PRODUCT_MISSING。"""
    _write_idea(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode",
               json={"project_dir": str(tmp_path), "episode_id": "E1",
                     "options": {}})
    # 进入 SSE 流（200），而非 400；LLM 失败只会在流内出 error 事件
    assert r.status_code == 200
    # bootstrap 已落盘 剧本.json
    si_path = tmp_path / "剧本.json"
    assert si_path.exists()
    si = json.loads(si_path.read_text(encoding="utf-8"))
    assert si["episodes"][0]["id"] == "E1"
    assert si["episodes"][0]["title"] == "守株待兔"


def test_episode_e2_still_400_without_index(tmp_path):
    """E2+ 无索引仍应 400（确实需要先生成大纲）。"""
    _write_idea(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode",
               json={"project_dir": str(tmp_path), "episode_id": "E2",
                     "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UPSTREAM_PRODUCT_MISSING"


def test_episode_e1_400_when_no_idea(tmp_path):
    """E1 但连创意都没有 → 仍 400（无从自举）。"""
    c = TestClient(create_app())
    r = c.post("/script/episode",
               json={"project_dir": str(tmp_path), "episode_id": "E1",
                     "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UPSTREAM_PRODUCT_MISSING"
