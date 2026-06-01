"""换立意「归档而非删除」：原断言"删除"的用例改为断言"移动到 归档/"。

设计：docs/explorer/立意切换归档方案与接口标准.md
- 换立意 → 旧下游产物移动到 归档/<旧idea>__<旧标题>/，**绝不删除**。
- 重选同一立意 → 不归档不动（防数据丢失）。
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from screenwriter_agent.server import create_app


def _archive_subdir(tmp_path: Path, idea_id: str) -> Path | None:
    root = tmp_path / "归档"
    if not root.is_dir():
        return None
    for d in root.iterdir():
        if d.is_dir() and d.name.startswith(f"{idea_id}__"):
            return d
    return None


def test_ideate_select_archives_script_json(tmp_path):
    """换立意 → 剧本.json 应被移动到 归档/<旧idea>/，不再留在项目根，也不删除。"""
    idea = {"candidates": [{"id": "c1", "title": "标题一"},
                            {"id": "c2", "title": "标题二"}],
            "selected_id": "c1"}
    (tmp_path / "创意.json").write_text(
        json.dumps(idea, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "剧本.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select",
               json={"project_dir": str(tmp_path), "selected_id": "c2"})
    assert r.status_code == 200
    body = r.json()
    assert body["selection_changed"] is True
    assert body["archived"] is not None
    assert "purged" not in body  # 绝不再返回 purged
    # 不在项目根
    assert not (tmp_path / "剧本.json").exists()
    # 移到 归档/c1__.../剧本.json（旧立意 id 是 c1）
    sub = _archive_subdir(tmp_path, "c1")
    assert sub is not None
    assert (sub / "剧本.json").is_file(), "剧本.json 应被归档而非删除"


def test_ideate_select_archives_storyboard(tmp_path):
    """换立意后 分镜_E1.json 也应被归档（移动而非删除）。"""
    idea = {"candidates": [{"id": "c1", "title": "甲"},
                            {"id": "c2", "title": "乙"}],
            "selected_id": "c1"}
    (tmp_path / "创意.json").write_text(
        json.dumps(idea, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select",
               json={"project_dir": str(tmp_path), "selected_id": "c2"})
    assert r.status_code == 200
    assert not (tmp_path / "分镜_E1.json").exists()
    sub = _archive_subdir(tmp_path, "c1")
    assert sub is not None
    assert (sub / "分镜_E1.json").is_file()


def test_ideate_reselect_same_id_does_not_archive(tmp_path):
    """重选「同一个」selected_id 绝不归档/不动（防数据丢失）。"""
    idea = {"candidates": [{"id": "c1", "title": "t"}], "selected_id": "c1"}
    (tmp_path / "创意.json").write_text(
        json.dumps(idea, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "剧本.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("正文", encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select",
               json={"project_dir": str(tmp_path), "selected_id": "c1"})
    assert r.status_code == 200
    body = r.json()
    assert body["selection_changed"] is False
    assert body["archived"] is None
    assert (tmp_path / "剧本.json").exists()
    assert (tmp_path / "剧本_E1.md").exists()
    assert (tmp_path / "分镜_E1.json").exists()
    assert not (tmp_path / "归档").exists(), "同立意不应产生归档目录"
