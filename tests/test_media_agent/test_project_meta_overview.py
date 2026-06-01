"""media_agent /project/overview（磁盘扫描判状态）+ PUT /project/meta — 无 Qt、tmp 目录。

覆盖：
- 创意.json(selected_id) → overview ideate=done；存在未选 → cur；无 → lock。
- PUT /project/meta 写 style_bible / genre → overview.bible / overview.genre 反映。
- 放 剧本_E1.md → script=done；分镜_E1.json → storyboard=done；prompts/ → imggen=done。
- 集数由 剧本_E*.md 推断。
- 缺参数/缺目录边界：project 空 → 400；目录不存在 → 404。
"""
import json

from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


def _stage(stages, key):
    return next(s for s in stages if s["key"] == key)


def _write_idea(pdir, selected_id="", inp=None):
    data = {"candidates": [{"id": "C1"}], "selected_id": selected_id}
    if inp is not None:
        data["input"] = inp
    (pdir / "创意.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_overview_empty_project_400():
    assert client.get(
        "/project/overview", params={"project": "  "}).status_code == 400


def test_overview_missing_dir_404(tmp_path):
    r = client.get(
        "/project/overview", params={"project": str(tmp_path / "no_such")})
    assert r.status_code == 404


def test_overview_ideate_lock_when_no_idea(tmp_path):
    pdir = tmp_path / "P-ovw-1"
    pdir.mkdir()
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert _stage(data["stages"], "ideate")["status"] == "lock"
    # next_action 指向首个非 done（ideate）
    assert data["next_action"]


def test_overview_ideate_cur_when_unselected(tmp_path):
    pdir = tmp_path / "P-ovw-2"
    pdir.mkdir()
    _write_idea(pdir, selected_id="")
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    assert _stage(r.json()["stages"], "ideate")["status"] == "cur"


def test_overview_ideate_done_when_selected(tmp_path):
    pdir = tmp_path / "P-ovw-3"
    pdir.mkdir()
    _write_idea(pdir, selected_id="C1")
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    assert _stage(r.json()["stages"], "ideate")["status"] == "done"


def test_overview_script_done_with_episode_md(tmp_path):
    pdir = tmp_path / "P-ovw-4"
    pdir.mkdir()
    _write_idea(pdir, selected_id="C1")
    (pdir / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    (pdir / "剧本_E2.md").write_text("# E2", encoding="utf-8")
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert _stage(data["stages"], "script")["status"] == "done"
    # 集数由 剧本_E*.md 推断
    assert data["project"]["episode_count"] == 2


def test_overview_script_done_legacy_single_md(tmp_path):
    pdir = tmp_path / "P-ovw-4b"
    pdir.mkdir()
    (pdir / "剧本.md").write_text("# 剧本", encoding="utf-8")
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert _stage(r.json()["stages"], "script")["status"] == "done"


def test_overview_storyboard_and_prompts_done(tmp_path):
    pdir = tmp_path / "P-ovw-5"
    pdir.mkdir()
    (pdir / "分镜_E1.json").write_text("{}", encoding="utf-8")
    (pdir / "prompts").mkdir()
    (pdir / "prompts" / "E1.txt").write_text("p", encoding="utf-8")
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    stages = r.json()["stages"]
    assert _stage(stages, "storyboard")["status"] == "done"
    assert _stage(stages, "imggen")["status"] == "done"


def test_overview_video_done(tmp_path):
    pdir = tmp_path / "P-ovw-6"
    pdir.mkdir()
    (pdir / "video").mkdir()
    (pdir / "video" / "E1.mp4").write_bytes(b"x")
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert _stage(r.json()["stages"], "video")["status"] == "done"


def test_overview_genre_bible_from_idea_input(tmp_path):
    pdir = tmp_path / "P-ovw-7"
    pdir.mkdir()
    _write_idea(pdir, selected_id="C1", inp={
        "genre": "都市悬疑",
        "style_bible": {"name": "冷峻写实", "description": "高对比夜景"},
        "aspect_ratio": "9:16",
    })
    r = client.get("/project/overview", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["genre"] == "都市悬疑"
    assert data["bible"].get("name") == "冷峻写实"
    assert data["project"]["aspect"] == "9:16"


def test_meta_empty_project_400():
    assert client.put(
        "/project/meta", json={"project": "  "}).status_code == 400


def test_meta_missing_dir_404(tmp_path):
    r = client.put(
        "/project/meta", json={"project": str(tmp_path / "no_such"), "genre": "x"})
    assert r.status_code == 404


def test_meta_writes_style_bible_reflected_in_overview(tmp_path):
    pdir = tmp_path / "P-meta-1"
    pdir.mkdir()
    _write_idea(pdir, selected_id="C1")

    r = client.put("/project/meta", json={
        "project": str(pdir),
        "genre": "古装权谋",
        "style_bible": {"name": "工笔重彩", "description": "金碧辉煌"},
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    ov = client.get("/project/overview", params={"project": str(pdir)}).json()
    assert ov["genre"] == "古装权谋"
    assert ov["bible"].get("name") == "工笔重彩"


def test_meta_style_bible_as_string(tmp_path):
    pdir = tmp_path / "P-meta-2"
    pdir.mkdir()
    r = client.put("/project/meta", json={
        "project": str(pdir),
        "style_bible": "赛博霓虹冷色调",
    })
    assert r.status_code == 200, r.text
    ov = client.get("/project/overview", params={"project": str(pdir)}).json()
    # 字符串包成 {description}
    assert "赛博霓虹冷色调" in json.dumps(ov["bible"], ensure_ascii=False)


def test_meta_manifest_genre_overrides_idea(tmp_path):
    """manifest（PUT 后）优先于 创意.json input。"""
    pdir = tmp_path / "P-meta-3"
    pdir.mkdir()
    _write_idea(pdir, selected_id="C1", inp={"genre": "来自创意的题材"})

    client.put("/project/meta", json={"project": str(pdir), "genre": "来自manifest的题材"})
    ov = client.get("/project/overview", params={"project": str(pdir)}).json()
    assert ov["genre"] == "来自manifest的题材"
