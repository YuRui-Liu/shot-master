from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _make_imgs(folder, n=3):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (50, 50), (i*30 % 256, 100, 100)).save(folder / f"img{i}.png")


def test_list_images_in_folder(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "data"
    _make_imgs(folder, n=3)
    (folder / "ignore.txt").write_text("nope")

    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/files/list", params={"folder": str(folder)})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    for it in items:
        assert it["name"].endswith(".png")
        assert "path" in it
        assert "size" in it


def test_list_folder_not_found(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/files/list", params={"folder": str(tmp_path / "nope")})
    assert resp.status_code == 400


def test_thumbnail_endpoint(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "data"
    _make_imgs(folder, n=1)
    target = folder / "img0.png"

    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/files/thumbnail", params={"path": str(target), "size": 32})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
