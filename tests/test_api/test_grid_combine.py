from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _make_imgs(tmp_path, n, w=100, h=100) -> list[Path]:
    paths = []
    for i in range(n):
        img = Image.new("RGB", (w, h), (i * 50 % 256, 100, 100))
        p = tmp_path / f"img{i}.png"
        img.save(p)
        paths.append(p)
    return paths


def test_combine_2x2(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    imgs = _make_imgs(tmp_path, 4)
    out = tmp_path / "out.png"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/combine", json={
        "images": [str(p) for p in imgs],
        "output_path": str(out),
        "target_rows": 2, "target_cols": 2,
        "gap": 4,
        "output_format": "PNG",
    })
    assert resp.status_code == 200
    assert out.exists()
    result = Image.open(out)
    # 2x2 with gap=4: width ≈ 2*100 + 1*4 = 204
    assert result.width == 204
    assert result.height == 204


def test_combine_count_mismatch(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    imgs = _make_imgs(tmp_path, 3)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/combine", json={
        "images": [str(p) for p in imgs],
        "output_path": str(tmp_path / "out.png"),
        "target_rows": 2, "target_cols": 2,
        "gap": 0,
    })
    assert resp.status_code == 400
    assert "expected" in resp.json()["detail"].lower() or "count" in resp.json()["detail"].lower()
