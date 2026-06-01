"""media_agent 本地文件流式端点 GET /file — 无 Qt、无网络（tmp 文件）。

覆盖：绝对路径、相对路径(project 基)、content-type 映射、404、400。
"""
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


def _touch(p, data=b"x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_file_absolute_png(tmp_path):
    f = _touch(tmp_path / "a.png", b"\x89PNG-data")
    r = client.get("/file", params={"path": str(f)})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == b"\x89PNG-data"


def test_file_content_type_by_ext(tmp_path):
    cases = {
        "v.mp4": "video/mp4",
        "s.wav": "audio/wav",
        "p.jpeg": "image/jpeg",
        "w.webm": "video/webm",
        "m.mp3": "audio/mpeg",
    }
    for name, ctype in cases.items():
        f = _touch(tmp_path / name, b"data")
        r = client.get("/file", params={"path": str(f)})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith(ctype), name


def test_file_relative_with_project(tmp_path):
    pdir = tmp_path / "P-001"
    _touch(pdir / "shots" / "c.jpg", b"jpgdata")
    r = client.get(
        "/file", params={"path": "shots/c.jpg", "project": str(pdir)})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.content == b"jpgdata"


def test_file_not_found_404(tmp_path):
    r = client.get("/file", params={"path": str(tmp_path / "nope.png")})
    assert r.status_code == 404


def test_file_directory_is_404(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    r = client.get("/file", params={"path": str(d)})
    assert r.status_code == 404


def test_file_empty_path_400():
    assert client.get("/file", params={"path": "  "}).status_code == 400
