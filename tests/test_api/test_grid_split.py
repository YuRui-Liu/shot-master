from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _make_grid(tmp_path, w=400, h=400, color=(200, 30, 30)) -> Path:
    img = Image.new("RGB", (w, h), color)
    p = tmp_path / "grid.png"
    img.save(p)
    return p


def test_preview_returns_tile_urls(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    img = _make_grid(tmp_path)

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/preview", json={
        "image_path": str(img),
        "src_rows": 2, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "tiles" in data
    assert len(data["tiles"]) == 4
    for t in data["tiles"]:
        assert t.startswith("/cache/preview/")


def test_preview_invalid_grid(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    img = _make_grid(tmp_path)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/preview", json={
        "image_path": str(img),
        "src_rows": 3, "src_cols": 3,
        "sub_rows": 2, "sub_cols": 2,  # 3 不能整除 2
    })
    assert resp.status_code == 400


def test_split_saves_files_to_output_dir(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    img = _make_grid(tmp_path, w=400, h=400)
    out = tmp_path / "split_out"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/split", json={
        "image_path": str(img),
        "output_dir": str(out),
        "src_rows": 2, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1,
        "output_format": "PNG",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["files"]) == 4
    for f in data["files"]:
        assert Path(f).exists()
