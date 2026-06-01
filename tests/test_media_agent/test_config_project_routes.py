"""media_agent /config + /recent + /project/overview 端点 — 无 Qt、无网络。"""
from pathlib import Path

from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


# ---------- GET /config ----------

def test_get_config_returns_dict_with_known_keys():
    r = client.get("/config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    # 设置页用到的几类字段都在
    for key in (
        "runninghub_base_url", "llm_providers", "imggen_provider",
        "soundtrack_workflow_id", "current_translator",
        "pipeline_lock_enabled", "screenwriter_models", "projects_root",
    ):
        assert key in body, f"缺字段 {key}"


# ---------- PUT /config ----------

def test_put_config_calls_update_settings(monkeypatch):
    from media_agent.routes import config as config_mod

    captured = {}

    class FakeCfg:
        def update_settings(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(config_mod, "load_config", lambda: FakeCfg())

    r = client.put("/config", json={"imggen_model": "doubao-seedream",
                                    "pipeline_lock_enabled": True})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert captured == {"imggen_model": "doubao-seedream",
                        "pipeline_lock_enabled": True}


def test_put_config_drops_projects_root(monkeypatch):
    from media_agent.routes import config as config_mod
    captured = {}

    class FakeCfg:
        def update_settings(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(config_mod, "load_config", lambda: FakeCfg())
    r = client.put("/config", json={"projects_root": "/tmp/x",
                                    "imggen_model": "m"})
    assert r.status_code == 200, r.text
    assert "projects_root" not in captured
    assert captured == {"imggen_model": "m"}


# ---------- /recent/* ----------

def test_recent_remove(tmp_path, monkeypatch):
    from media_agent.routes import projectx as projectx_mod
    monkeypatch.setattr(projectx_mod, "_SETTINGS_PATH", tmp_path / "settings.json")

    mgr = projectx_mod._manager()
    proj = tmp_path / "P-001_demo"
    proj.mkdir()
    mgr.push(str(proj), name="demo")
    assert any(p["path"] == str(proj) for p in mgr.load())

    r = client.post("/recent/remove", json={"path": str(proj)})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert not any(p["path"] == str(proj) for p in mgr.load())


def test_recent_delete_folder(tmp_path, monkeypatch):
    from media_agent.routes import projectx as projectx_mod
    monkeypatch.setattr(projectx_mod, "_SETTINGS_PATH", tmp_path / "settings.json")

    mgr = projectx_mod._manager()
    proj = tmp_path / "P-002_del"
    proj.mkdir()
    (proj / "a.txt").write_text("x", encoding="utf-8")
    mgr.push(str(proj), name="del")

    r = client.post("/recent/delete_folder", json={"path": str(proj)})
    assert r.status_code == 200, r.text
    assert not proj.exists()
    assert not any(p["path"] == str(proj) for p in mgr.load())


def test_recent_clear(tmp_path, monkeypatch):
    from media_agent.routes import projectx as projectx_mod
    monkeypatch.setattr(projectx_mod, "_SETTINGS_PATH", tmp_path / "settings.json")

    mgr = projectx_mod._manager()
    for i in range(3):
        d = tmp_path / f"P-00{i}_p"
        d.mkdir()
        mgr.push(str(d), name=f"p{i}")
    assert len(mgr.load()) == 3

    r = client.post("/recent/clear")
    assert r.status_code == 200, r.text
    assert r.json()["cleared"] == 3
    assert mgr.load() == []


def test_recent_remove_empty_path_400():
    assert client.post("/recent/remove", json={"path": "  "}).status_code == 400


# ---------- /project/overview ----------

def _write_manifest(proj_dir: Path) -> None:
    from drama_shot_master.core.compass.manifest import (
        EpisodeProgress, ProjectManifest, save_manifest)

    m = ProjectManifest(
        project_id="P-007",
        project_name="替嫁新娘的逆袭",
        genre="real-drama",
        params={"episodes": 12, "aspect": "9:16"},
        style_bible={"name": "cinematic-warm-v1", "desc": "暖调电影感"},
    )
    m.set_stage("screenwriter", "completed")
    m.set_stage("storyboard", "completed")
    m.set_stage("production", "in_progress", next_action="去补全出图")
    m.episodes["E01"] = EpisodeProgress(
        title="第1集", shots_done=["1-1", "1-2", "1-3"], video_done=False)
    m.episodes["E02"] = EpisodeProgress(
        title="第2集", shots_done=["2-1"], video_done=True)
    save_manifest(m, proj_dir)


def test_project_overview_shape(tmp_path):
    """P6-2：阶段 status 由磁盘真实产物判定（不再信僵尸 manifest pipeline）。

    project_id/name/genre/bible/aspect 仍读 manifest（PUT 后权威）；
    next_action 仍尊重 manifest 显式 next_action。
    """
    proj = tmp_path / "P-007_xinniang"
    proj.mkdir()
    _write_manifest(proj)
    # 磁盘真实产物：创意.json(已选) + 两集剧本 + 一集分镜 + prompts/ + 两张图
    (proj / "创意.json").write_text(
        '{"candidates": [{"id": "C1"}], "selected_id": "C1"}', encoding="utf-8")
    (proj / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    (proj / "剧本_E2.md").write_text("# E2", encoding="utf-8")
    (proj / "分镜_E1.json").write_text("{}", encoding="utf-8")
    (proj / "prompts").mkdir()
    (proj / "prompts" / "E1.txt").write_text("p", encoding="utf-8")
    (proj / "shot1.png").write_bytes(b"x")
    (proj / "shot2.jpg").write_bytes(b"x")

    r = client.get("/project/overview", params={"project": str(proj)})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["project"]["project_id"] == "P-007"
    assert body["project"]["project_name"] == "替嫁新娘的逆袭"
    # 集数由 剧本_E*.md 推断（磁盘真实）
    assert body["project"]["episode_count"] == 2
    # 分镜数由 分镜_E*.json 推断（磁盘真实）
    assert body["project"]["shots_total"] == 1
    assert body["project"]["images_done"] == 2
    assert body["project"]["aspect"] == "9:16"
    assert body["genre"] == "real-drama"
    assert body["bible"]["name"] == "cinematic-warm-v1"
    # manifest 显式 next_action 仍优先
    assert body["next_action"] == "去补全出图"

    stages = body["stages"]
    assert [s["key"] for s in stages] == [
        "ideate", "script", "storyboard", "imggen", "video", "audio", "final"]
    by_key = {s["key"]: s for s in stages}
    # 全部由磁盘产物判定
    assert by_key["ideate"]["status"] == "done"      # 创意.json + selected_id
    assert by_key["script"]["status"] == "done"      # 剧本_E*.md
    assert by_key["storyboard"]["status"] == "done"  # 分镜_E1.json
    assert by_key["imggen"]["status"] == "done"      # prompts/ 非空
    assert by_key["imggen"]["done"] == 2             # 图片数
    assert by_key["video"]["status"] == "lock"       # 无 video/ 目录


def test_project_overview_missing_404():
    assert client.get(
        "/project/overview",
        params={"project": str(Path("/no/such/proj/zzz"))},
    ).status_code == 404


def test_project_overview_empty_400():
    assert client.get(
        "/project/overview", params={"project": "  "}).status_code == 400
