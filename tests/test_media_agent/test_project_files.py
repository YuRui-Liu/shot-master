"""media_agent /project/files 列目录端点 — 无 Qt、无网络（tmp 目录）。

覆盖：
- 列文件、按文件名排序、posix 路径、size 字段。
- ext 扩展名过滤（逗号分隔、小写、不含点）。
- sub 子目录。
- 缺目录 → 空列表；project 空 → 400。
"""
from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())


def _touch(p, data=b"x"):
    p.write_bytes(data)
    return p


def test_files_lists_all_sorted(tmp_path):
    pdir = tmp_path / "P-001"
    pdir.mkdir()
    _touch(pdir / "b.json", b"{}")
    _touch(pdir / "a.md", b"# hi")
    _touch(pdir / "c.txt", b"note")
    (pdir / "sub").mkdir()  # 目录不应出现

    r = client.get("/project/files", params={"project": str(pdir)})
    assert r.status_code == 200, r.text
    files = r.json()["files"]
    assert [f["name"] for f in files] == ["a.md", "b.json", "c.txt"]
    by_name = {f["name"]: f for f in files}
    assert by_name["a.md"]["size"] == len(b"# hi")
    assert by_name["a.md"]["path"].endswith("P-001/a.md")
    assert "\\" not in by_name["a.md"]["path"]  # posix 路径


def test_files_ext_filter(tmp_path):
    pdir = tmp_path / "P-002"
    pdir.mkdir()
    _touch(pdir / "a.md")
    _touch(pdir / "b.json")
    _touch(pdir / "c.txt")

    r = client.get(
        "/project/files", params={"project": str(pdir), "ext": "md,json"})
    assert r.status_code == 200, r.text
    names = [f["name"] for f in r.json()["files"]]
    assert names == ["a.md", "b.json"]


def test_files_ext_filter_single(tmp_path):
    pdir = tmp_path / "P-003"
    pdir.mkdir()
    _touch(pdir / "a.md")
    _touch(pdir / "b.MD")  # 大小写不敏感
    _touch(pdir / "c.txt")

    r = client.get(
        "/project/files", params={"project": str(pdir), "ext": "md"})
    assert r.status_code == 200, r.text
    names = [f["name"] for f in r.json()["files"]]
    assert names == ["a.md", "b.MD"]


def test_files_sub_directory(tmp_path):
    pdir = tmp_path / "P-004"
    sub = pdir / "docs"
    sub.mkdir(parents=True)
    _touch(sub / "spec.md")
    _touch(pdir / "root.md")  # 根目录文件不应出现在 sub 列表

    r = client.get(
        "/project/files", params={"project": str(pdir), "sub": "docs"})
    assert r.status_code == 200, r.text
    names = [f["name"] for f in r.json()["files"]]
    assert names == ["spec.md"]


def test_files_missing_dir_empty(tmp_path):
    r = client.get(
        "/project/files", params={"project": str(tmp_path / "no_such")})
    assert r.status_code == 200, r.text
    assert r.json()["files"] == []


def test_files_empty_project_400():
    assert client.get(
        "/project/files", params={"project": "  "}).status_code == 400
