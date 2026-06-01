"""归档/恢复下游产物 + archives 列举 + restore 端点。

设计：docs/explorer/立意切换归档方案与接口标准.md
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from screenwriter_agent.core.downstream import (
    archive_downstream,
    list_archives,
    restore_downstream,
    safe_name,
)
from screenwriter_agent.server import create_app


# ---------------------------------------------------------------------------
# safe_name
# ---------------------------------------------------------------------------

def test_safe_name_strips_illegal_and_truncates():
    assert safe_name('a/b:c*d?"<>|e') == "abcde"
    assert safe_name("  好 标题  ") == "好 标题"
    assert len(safe_name("子" * 100)) <= 40
    assert safe_name("") == "untitled"


# ---------------------------------------------------------------------------
# archive_downstream / restore_downstream
# ---------------------------------------------------------------------------

def _setup_products(tmp_path: Path):
    (tmp_path / "剧本.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("E1 正文", encoding="utf-8")
    (tmp_path / "剧本_E2.md").write_text("E2 正文", encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text('{"e":1}', encoding="utf-8")
    pd = tmp_path / "prompts" / "E1"
    pd.mkdir(parents=True)
    (pd / "x.md").write_text("p", encoding="utf-8")


def test_archive_moves_downstream_to_archive_dir(tmp_path):
    _setup_products(tmp_path)
    res = archive_downstream(tmp_path, "c1", "替嫁后她惊艳全场")
    assert res["dir"] == "归档/c1__替嫁后她惊艳全场"
    arc = tmp_path / "归档" / "c1__替嫁后她惊艳全场"
    # 移动而非删除：原位无，归档区有
    assert not (tmp_path / "剧本.json").exists()
    assert not (tmp_path / "剧本_E1.md").exists()
    assert not (tmp_path / "prompts").exists()
    assert (arc / "剧本.json").is_file()
    assert (arc / "剧本_E1.md").read_text(encoding="utf-8") == "E1 正文"
    assert (arc / "prompts" / "E1" / "x.md").is_file()
    assert "剧本.json" in res["files"]
    assert "prompts/" in res["files"]


def test_archive_empty_when_no_products(tmp_path):
    res = archive_downstream(tmp_path, "c1", "标题")
    assert res == {"dir": None, "files": []}
    assert not (tmp_path / "归档").exists()


def test_archive_does_not_move_idea_or_media(tmp_path):
    """创意.json 常驻；imggen/video/soundtrack 默认不搬。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本.json").write_text("{}", encoding="utf-8")
    (tmp_path / "imggen").mkdir()
    (tmp_path / "imggen" / "big.png").write_text("x", encoding="utf-8")
    archive_downstream(tmp_path, "c1", "t")
    assert (tmp_path / "创意.json").is_file()
    assert (tmp_path / "imggen" / "big.png").is_file()


def test_restore_moves_archive_back_to_root(tmp_path):
    _setup_products(tmp_path)
    archive_downstream(tmp_path, "c1", "标题甲")
    res = restore_downstream(tmp_path, "c1")
    assert (tmp_path / "剧本.json").is_file()
    assert (tmp_path / "剧本_E1.md").read_text(encoding="utf-8") == "E1 正文"
    assert (tmp_path / "prompts" / "E1" / "x.md").is_file()
    # 归档子目录搬空被删
    assert not (tmp_path / "归档" / "c1__标题甲").exists()
    assert "剧本.json" in res["files"]


def test_restore_missing_archive_returns_empty(tmp_path):
    assert restore_downstream(tmp_path, "cX") == {"files": []}


def test_archive_merges_into_existing_dir(tmp_path):
    """同 idea 二次归档：并入/覆盖同名，不报错。"""
    (tmp_path / "剧本.json").write_text("v1", encoding="utf-8")
    archive_downstream(tmp_path, "c1", "标题")
    (tmp_path / "剧本.json").write_text("v2", encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("ep", encoding="utf-8")
    archive_downstream(tmp_path, "c1", "标题")
    arc = tmp_path / "归档" / "c1__标题"
    assert (arc / "剧本.json").read_text(encoding="utf-8") == "v2"  # 覆盖
    assert (arc / "剧本_E1.md").read_text(encoding="utf-8") == "ep"  # 并入


# ---------------------------------------------------------------------------
# 端到端：换立意 → 旧进归档、新立意有归档则恢复、切回旧立意产物回根
# ---------------------------------------------------------------------------

def _write_idea(tmp_path: Path, selected: str):
    idea = {"candidates": [{"id": "c1", "title": "甲立意"},
                            {"id": "c2", "title": "乙立意"}],
            "selected_id": selected}
    (tmp_path / "创意.json").write_text(
        json.dumps(idea, ensure_ascii=False), encoding="utf-8")


def test_switch_then_switch_back_roundtrip(tmp_path):
    _write_idea(tmp_path, "c1")
    (tmp_path / "剧本_E1.md").write_text("甲的剧本", encoding="utf-8")
    c = TestClient(create_app())

    # c1 → c2：甲产物进归档
    r1 = c.post("/ideate/select",
                json={"project_dir": str(tmp_path), "selected_id": "c2"})
    assert r1.status_code == 200
    assert r1.json()["archived"]["idea_id"] == "c1"
    assert r1.json()["restored"] is None       # c2 无归档
    assert not (tmp_path / "剧本_E1.md").exists()

    # 给 c2 造产物
    (tmp_path / "剧本_E1.md").write_text("乙的剧本", encoding="utf-8")

    # c2 → c1：乙产物进归档，甲产物恢复回根
    r2 = c.post("/ideate/select",
                json={"project_dir": str(tmp_path), "selected_id": "c1"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["archived"]["idea_id"] == "c2"
    assert body["restored"]["idea_id"] == "c1"
    assert (tmp_path / "剧本_E1.md").read_text(encoding="utf-8") == "甲的剧本"


# ---------------------------------------------------------------------------
# GET /project/archives + POST /project/archive/restore
# ---------------------------------------------------------------------------

def test_archives_list_endpoint(tmp_path):
    _write_idea(tmp_path, "c1")
    (tmp_path / "剧本_E1.md").write_text("甲", encoding="utf-8")
    c = TestClient(create_app())
    c.post("/ideate/select",
           json={"project_dir": str(tmp_path), "selected_id": "c2"})
    r = c.get("/project/archives", params={"project": str(tmp_path)})
    assert r.status_code == 200
    arcs = r.json()["archives"]
    assert len(arcs) == 1
    a = arcs[0]
    assert a["idea_id"] == "c1"
    assert a["title"] == "甲立意"
    assert a["file_count"] >= 1
    assert a["is_active"] is False


def test_archive_restore_endpoint(tmp_path):
    _write_idea(tmp_path, "c1")
    (tmp_path / "剧本_E1.md").write_text("甲", encoding="utf-8")
    c = TestClient(create_app())
    # 换到 c2（甲归档），c2 造产物
    c.post("/ideate/select",
           json={"project_dir": str(tmp_path), "selected_id": "c2"})
    (tmp_path / "剧本_E1.md").write_text("乙", encoding="utf-8")
    # 显式 restore 回 c1
    r = c.post("/project/archive/restore",
               json={"project_dir": str(tmp_path), "idea_id": "c1"})
    assert r.status_code == 200
    body = r.json()
    assert body["selected"]["id"] == "c1"
    assert body["archived"]["idea_id"] == "c2"
    assert body["restored"]["idea_id"] == "c1"
    assert (tmp_path / "剧本_E1.md").read_text(encoding="utf-8") == "甲"
    # 创意.json.selected_id 已设为 c1
    idea = json.loads((tmp_path / "创意.json").read_text(encoding="utf-8"))
    assert idea["selected_id"] == "c1"
