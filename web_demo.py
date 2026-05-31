"""M1 端到端演示启动器：spawn media_agent → QWebEngine 加载 web 页 → fetch 调后端。

证明整条 Web 路径：QWebEngine 渲染设计系统(保真) ↔ fetch HTTP ↔ media_agent(零 Qt 后端)。
开发期用 --disable-web-security 免 CORS（须在 QApplication 前设环境变量）。
"""
import os
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-web-security")

import sys
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent.resolve()
API = "http://127.0.0.1:18450"


def make_sample() -> Path:
    """蓝底 + 中间整列白带 → infer_grid 应得 1 行 × 2 列。"""
    img = Image.new("RGB", (240, 120), (30, 60, 200))
    for x in range(116, 124):
        for y in range(120):
            img.putpixel((x, y), (255, 255, 255))
    p = Path(tempfile.gettempdir()) / "nuomi_sample_grid.png"
    img.save(p)
    return p


def wait_health(timeout=20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(API + "/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def main() -> int:
    proc = subprocess.Popen([sys.executable, "-m", "media_agent.server"])
    try:
        ok = wait_health()
        print(f"[web_demo] media_agent health: {'OK' if ok else 'TIMEOUT'}")
        sample = make_sample()

        from PySide6.QtWidgets import QApplication
        from drama_shot_master.ui.web_host import WebHostWindow

        app = QApplication(sys.argv)
        query = urllib.parse.urlencode({"api": API, "img": str(sample)})
        page = ROOT / "web" / "split-tool.html"
        win = WebHostWindow.for_page(page, query=query,
                                     title="糯米AI · M1 Web 端到端验证")
        win.show()
        ret = app.exec()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    return ret


if __name__ == "__main__":
    raise SystemExit(main())
