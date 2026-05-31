"""media_agent 创作技能端点 — 无 Qt、无网络（真实读 templates/skills/creations/*.md）。"""
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


# ---------- /skills/list ----------

def test_list_returns_skills():
    r = client.get("/skills/list")
    assert r.status_code == 200, r.text
    skills = r.json()["skills"]
    assert isinstance(skills, list) and len(skills) >= 3
    ids = {s["id"] for s in skills}
    assert "ai-short-drama-oneshot" in ids


def test_list_manifest_shape():
    r = client.get("/skills/list")
    s = next(x for x in r.json()["skills"]
             if x["id"] == "ai-short-drama-oneshot")
    for key in ("id", "name", "cat", "medium", "icon", "desc",
                "output", "modules", "style_hint", "source_path"):
        assert key in s, f"缺字段 {key}"
    assert s["cat"] == "短剧"
    assert isinstance(s["modules"], list) and s["modules"]
    m = s["modules"][0]
    assert {"id", "stage", "priority"} <= set(m.keys())


# ---------- /skills/detail ----------

def test_detail_by_id():
    r = client.get("/skills/detail", params={"id": "flat-illust-dance-mv"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "flat-illust-dance-mv"
    assert body["cat"] == "MV"
    # 详情含正文（注入素材）
    assert "body_md" in body and body["body_md"].strip()


def test_detail_unknown_404():
    r = client.get("/skills/detail", params={"id": "nope-xxx"})
    assert r.status_code == 404


def test_detail_empty_400():
    r = client.get("/skills/detail", params={"id": "  "})
    assert r.status_code == 400
