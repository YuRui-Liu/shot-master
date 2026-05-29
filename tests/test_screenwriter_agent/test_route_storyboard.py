from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_storyboard_missing_script_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/storyboard", json={"project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in ("UPSTREAM_PRODUCT_MISSING", "PROJECT_DIR_NOT_FOUND")


def test_storyboard_missing_script_with_file_400(tmp_path):
    """episode_id 指定集的剧本不存在时，应返回 UPSTREAM_PRODUCT_MISSING。"""
    # E2 的剧本不存在，即使 E1 存在也不行
    (tmp_path / "剧本_E1.md").write_text("# 标题：测试\n内容", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/storyboard", json={"project_dir": str(tmp_path), "episode_id": "E2", "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UPSTREAM_PRODUCT_MISSING"
