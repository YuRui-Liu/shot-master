from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _img_with_white_border(tmp_path, content_w=80, content_h=80, border=20) -> Path:
    total_w = content_w + 2 * border
    total_h = content_h + 2 * border
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    inner = Image.new("RGB", (content_w, content_h), (50, 50, 200))
    canvas.paste(inner, (border, border))
    p = tmp_path / "bordered.png"
    canvas.save(p)
    return p


def test_trim_single_image(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    src = _img_with_white_border(tmp_path)
    out = tmp_path / "trimmed.png"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/border/trim", json={
        "image_path": str(src),
        "output_path": str(out),
        "threshold": 240,
    })
    assert resp.status_code == 200
    assert out.exists()
    trimmed = Image.open(out)
    assert trimmed.width <= 90
    assert trimmed.height <= 90


def test_trim_batch(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "in"
    folder.mkdir()
    for i in range(3):
        canvas = Image.new("RGB", (120, 120), (255, 255, 255))
        canvas.paste(Image.new("RGB", (80, 80), (i * 50 % 256, 100, 100)), (20, 20))
        canvas.save(folder / f"img{i}.png")
    out_dir = tmp_path / "out"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/border/trim_batch", json={
        "folder": str(folder),
        "output_dir": str(out_dir),
        "threshold": 240,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["files"]) == 3
    for f in data["files"]:
        assert Path(f).exists()
