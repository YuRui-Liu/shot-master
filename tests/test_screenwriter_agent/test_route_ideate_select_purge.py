import json
from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_ideate_select_purges_script_json(tmp_path):
    """重选 selected_id → 剧本.json 应被删除（触发下游重生成）。"""
    idea = {"candidates": [{"id": "c1", "title": "t"}], "selected_id": None}
    (tmp_path / "创意.json").write_text(json.dumps(idea), encoding="utf-8")
    # 先写一个假的剧本.json 模拟"已有旧产物"
    (tmp_path / "剧本.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select",
               json={"project_dir": str(tmp_path), "selected_id": "c1"})
    assert r.status_code == 200
    assert not (tmp_path / "剧本.json").exists(), "重选后剧本.json 应被清除"


def test_ideate_select_purges_storyboard(tmp_path):
    """重选后分镜_E1.json 也应被删除。"""
    idea = {"candidates": [{"id": "c2"}], "selected_id": None}
    (tmp_path / "创意.json").write_text(json.dumps(idea), encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select",
               json={"project_dir": str(tmp_path), "selected_id": "c2"})
    assert r.status_code == 200
    assert not (tmp_path / "分镜_E1.json").exists()


def test_ideate_reselect_same_id_does_not_purge(tmp_path):
    """重选「同一个」selected_id 绝不清下游（防数据丢失 bug：
    重开项目后再次点「推进」/重复确认不得误删已生成的剧本/分镜/prompts）。"""
    idea = {"candidates": [{"id": "c1", "title": "t"}], "selected_id": "c1"}
    (tmp_path / "创意.json").write_text(json.dumps(idea), encoding="utf-8")
    (tmp_path / "剧本.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("正文", encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select",
               json={"project_dir": str(tmp_path), "selected_id": "c1"})
    assert r.status_code == 200
    assert r.json().get("selection_changed") is False
    assert (tmp_path / "剧本.json").exists(), "重选同一立意不应删 剧本.json"
    assert (tmp_path / "剧本_E1.md").exists(), "重选同一立意不应删 剧本_E1.md"
    assert (tmp_path / "分镜_E1.json").exists(), "重选同一立意不应删 分镜_E1.json"
