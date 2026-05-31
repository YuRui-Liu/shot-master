"""media_agent imaging 端点 — 无 Qt（TestClient）。M0 验证：后端不依赖 Qt 也能跑通。"""
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from media_agent.server import create_app

client = TestClient(create_app())


def _make_img(path: Path, w=120, h=120, color=(30, 60, 200)):
    Image.new("RGB", (w, h), color).save(path)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"]


def test_split_creates_cells(tmp_path):
    src = tmp_path / "src.png"
    _make_img(src, 120, 120)
    out = tmp_path / "cells"
    # 把源图当 2x2 网格、每个 sub 1x1 → 抽出 4 格
    r = client.post("/imaging/split", json={
        "src_path": str(src), "src_rows": 2, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1, "out_dir": str(out),
        "base_name": "c", "fmt": "PNG",
    })
    assert r.status_code == 200, r.text
    outputs = r.json()["outputs"]
    assert len(outputs) == 4
    for p in outputs:
        assert Path(p).exists()
        with Image.open(p) as im:
            assert im.size[0] > 0


def test_trim_white_edges(tmp_path):
    # 白底中间一块深色 → trim 后应变小
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(30, 70):
        for y in range(30, 70):
            img.putpixel((x, y), (10, 10, 10))
    src = tmp_path / "bordered.png"
    img.save(src)
    out = tmp_path / "trimmed.png"
    r = client.post("/imaging/trim", json={
        "src_path": str(src), "threshold": 240, "out_path": str(out), "fmt": "PNG",
    })
    assert r.status_code == 200, r.text
    assert Path(out).exists()
    with Image.open(out) as im:
        assert im.width < 100 and im.height < 100   # 白边被裁掉


def test_combine_grid(tmp_path):
    paths = []
    for i in range(4):
        p = tmp_path / f"in_{i}.png"
        _make_img(p, 50, 50, (i * 40, 100, 150))
        paths.append(str(p))
    out = tmp_path / "combined.png"
    r = client.post("/imaging/combine", json={
        "src_paths": paths, "target_rows": 2, "target_cols": 2,
        "out_path": str(out), "fmt": "PNG",
    })
    assert r.status_code == 200, r.text
    assert Path(out).exists()


def test_batch_split_sse(tmp_path):
    src = tmp_path / "s.png"
    _make_img(src, 80, 80)
    out = tmp_path / "b"
    r = client.post("/imaging/batch_split", json={"items": [{
        "src_path": str(src), "src_rows": 1, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1, "out_dir": str(out),
        "base_name": "x", "fmt": "PNG",
    }]})
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: progress" in body
    assert "event: item_done" in body
    assert "event: complete" in body


def _img_with_vstrip(path: Path, w=120, h=60):
    """蓝底 + 中间整列白带 → 1 条内部竖白带（cols=2, rows=1）。"""
    img = Image.new("RGB", (w, h), (30, 60, 200))
    for x in range(56, 64):
        for y in range(h):
            img.putpixel((x, y), (255, 255, 255))
    img.save(path)


def test_infer_grid(tmp_path):
    src = tmp_path / "grid.png"
    _img_with_vstrip(src)
    r = client.post("/imaging/infer_grid", json={"src_path": str(src)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == 1 and body["cols"] == 2


def test_detect_borders(tmp_path):
    src = tmp_path / "b.png"
    _img_with_vstrip(src)
    r = client.post("/imaging/detect_borders", json={"src_path": str(src)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["margins"]) == {"top", "right", "bottom", "left"}
    assert body["gap"] >= 0


def test_cell_boxes(tmp_path):
    src = tmp_path / "c.png"
    _img_with_vstrip(src)
    r = client.post("/imaging/cell_boxes", json={
        "src_path": str(src), "n_rows": 1, "n_cols": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["boxes"]) == 2 and body["mode"] in ("bands", "uniform")


def test_crop_aspect(tmp_path):
    src = tmp_path / "wide.png"
    _make_img(src, 200, 100)
    out = tmp_path / "sq.png"
    r = client.post("/imaging/crop_aspect", json={
        "src_path": str(src), "aspect": {"w": 1, "h": 1},
        "out_path": str(out), "fmt": "PNG"})
    assert r.status_code == 200, r.text
    with Image.open(out) as im:
        assert im.width == im.height and im.width <= 200


def test_backend_imports_without_qt():
    """子进程断言：导入 media_agent.server 不拉起 PySide6（后端零 Qt）。"""
    code = "import media_agent.server, sys; assert 'PySide6' not in sys.modules; print('OK')"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout
