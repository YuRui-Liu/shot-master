"""media_agent 题材卡片明细 + 项目片段列目录端点 — 无 Qt、无网络（tmp 目录）。

覆盖：
- GET /assets/genres/detail：返回全部题材的卡片字段，单个加载失败容错跳过。
- GET /project/clips：列视频/图片、子目录、排序、空/缺目录降级、project 空 400。
"""
import media_agent.routes.assets as assets_mod
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


# ---------- GET /assets/genres/detail ----------

def test_genres_detail_cards():
    r = client.get("/assets/genres/detail")
    assert r.status_code == 200, r.text
    genres = r.json()["genres"]
    assert len(genres) >= 1
    by_id = {g["genre_id"]: g for g in genres}
    # 内置短剧应在内且字段齐全
    sd = by_id["short-drama"]
    assert sd["display_name"] == "短剧"
    assert isinstance(sd["one_liner"], str) and sd["one_liner"]
    assert isinstance(sd["satisfaction_weights"], dict)
    assert sd["satisfaction_weights"].get("打脸") == 40
    # 每条都带四个键
    for g in genres:
        assert set(g) == {
            "genre_id", "display_name", "one_liner", "satisfaction_weights"}


def test_genres_detail_skips_broken(monkeypatch):
    """单个 load_genre 抛错时该条跳过，其余正常返回（容错不崩）。"""
    monkeypatch.setattr(
        assets_mod.genre_templates, "list_genres",
        lambda: ["short-drama", "__broken__"])

    real_load = assets_mod.genre_templates.load_genre

    def fake_load(gid):
        if gid == "__broken__":
            raise FileNotFoundError("nope")
        return real_load(gid)

    monkeypatch.setattr(assets_mod.genre_templates, "load_genre", fake_load)

    r = client.get("/assets/genres/detail")
    assert r.status_code == 200, r.text
    ids = [g["genre_id"] for g in r.json()["genres"]]
    assert ids == ["short-drama"]


# ---------- GET /project/clips ----------

def _touch(p, data=b"x"):
    p.write_bytes(data)
    return p


def test_clips_lists_videos_and_images(tmp_path):
    pdir = tmp_path / "P-001"
    pdir.mkdir()
    _touch(pdir / "b.mp4", b"vid")
    _touch(pdir / "a.png", b"img")
    _touch(pdir / "notes.txt")  # 非媒体应被忽略

    r = client.get("/project/clips", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    clips = r.json()["clips"]
    # 排序按 name（a.png 在 b.mp4 前）
    assert [c["name"] for c in clips] == ["a.png", "b.mp4"]
    by_name = {c["name"]: c for c in clips}
    assert by_name["a.png"]["kind"] == "image"
    assert by_name["b.mp4"]["kind"] == "video"
    assert by_name["b.mp4"]["size"] == len(b"vid")
    assert by_name["a.png"]["path"].endswith("P-001/a.png")
    assert "\\" not in by_name["a.png"]["path"]  # posix 路径


def test_clips_sub_directory(tmp_path):
    pdir = tmp_path / "P-002"
    sub = pdir / "shots"
    sub.mkdir(parents=True)
    _touch(sub / "shot1.mov", b"v")
    _touch(pdir / "root.png", b"i")  # 根目录文件不应出现在 sub 列表

    r = client.get(
        "/project/clips", params={"project": str(pdir), "sub": "shots"})
    assert r.status_code == 200, r.text
    names = [c["name"] for c in r.json()["clips"]]
    assert names == ["shot1.mov"]


def test_clips_missing_dir_empty(tmp_path):
    r = client.get(
        "/project/clips", params={"project": str(tmp_path / "no_such")})
    assert r.status_code == 200, r.text
    assert r.json()["clips"] == []


def test_clips_empty_project_400():
    assert client.get(
        "/project/clips", params={"project": "  "}).status_code == 400
