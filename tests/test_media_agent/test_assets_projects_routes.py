"""media_agent 内容资产 + 项目端点 — 无 Qt、无网络（真实读 templates/）。"""
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


# ---------- /assets/genres + /assets/genre ----------

def test_genres_non_empty():
    r = client.get("/assets/genres")
    assert r.status_code == 200, r.text
    genres = r.json()["genres"]
    assert isinstance(genres, list) and len(genres) >= 1


def test_genre_detail_shape():
    gid = client.get("/assets/genres").json()["genres"][0]
    r = client.get("/assets/genre", params={"id": gid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["genre_id"] == gid


def test_genre_unknown_404():
    assert client.get("/assets/genre", params={"id": "nope-xxx"}).status_code == 404


def test_genre_empty_400():
    assert client.get("/assets/genre", params={"id": "  "}).status_code == 400


# ---------- /assets/styles + /assets/style ----------

def test_styles_non_empty():
    r = client.get("/assets/styles")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    assert isinstance(body.get("styles"), list) and len(body["styles"]) >= 1


def test_style_detail_shape():
    sid = client.get("/assets/styles").json()["styles"][0]["style_id"]
    r = client.get("/assets/style", params={"id": sid})
    assert r.status_code == 200, r.text
    assert r.json()["style_id"] == sid


def test_style_unknown_404():
    assert client.get("/assets/style", params={"id": "nope-xxx"}).status_code == 404


# ---------- /projects/list + open + create ----------

def test_projects_list_returns_list():
    r = client.get("/projects/list")
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["projects"], list)


def test_projects_create_and_open(tmp_path, monkeypatch):
    # 把 recent_projects.json 指向 tmp，避免污染仓库根散文件。
    from media_agent.routes import projects as projects_mod
    monkeypatch.setattr(projects_mod, "_SETTINGS_PATH", tmp_path / "settings.json")

    root = tmp_path / "projects_root"
    r = client.post(
        "/projects/create",
        json={"name": "我的测试剧 Demo!", "projects_root": str(root)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    path = body["path"]
    assert body["project_id"].startswith("P-")
    from pathlib import Path
    assert Path(path).is_dir()
    assert (root / "index.json").is_file()

    # 打开刚建的项目
    r2 = client.post("/projects/open", json={"path": path})
    assert r2.status_code == 200, r2.text
    assert r2.json()["ok"] is True
    assert r2.json()["project"]["path"] == str(Path(path))


def test_projects_open_missing_404():
    r = client.post("/projects/open", json={"path": "/no/such/proj/xyz"})
    assert r.status_code == 404
