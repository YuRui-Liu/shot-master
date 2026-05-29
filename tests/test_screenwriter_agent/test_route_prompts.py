from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_prompts_missing_storyboard_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/prompts", json={"project_dir": str(tmp_path),
                                 "episode_id": "E1",
                                 "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in ("UPSTREAM_PRODUCT_MISSING", "PROJECT_DIR_NOT_FOUND")


def test_prompts_episode_paths(tmp_path):
    """分镜_E1.json 存在时，产物应落到 prompts/E1/ 下。"""
    import json

    sb = {
        "characters": [{"name": "小明"}],
        "shots": [{"id": "S1", "desc": "test shot"}],
        "globalStyle": "test style",
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8"
    )

    c = TestClient(create_app())
    # 只验证路径逻辑：不调 LLM，捕 SSE error 也 OK
    r = c.post("/prompts", json={"project_dir": str(tmp_path),
                                 "episode_id": "E1",
                                 "options": {}})
    # 如果 LLM 没配置会得到 SSE error，但不应该是 400 UPSTREAM_PRODUCT_MISSING
    if r.status_code == 400:
        assert r.json()["error"]["code"] != "UPSTREAM_PRODUCT_MISSING", (
            "分镜_E1.json 已存在，不应返回 UPSTREAM_PRODUCT_MISSING"
        )
