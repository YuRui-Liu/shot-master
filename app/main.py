"""桌面应用入口：QApplication + MainWindow"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 shot-master 可被 import（开发期间用相对路径定位，打包发布版可走 pip install -e）
_SHOT_MASTER = Path(__file__).resolve().parent.parent.parent.parent / "shot-master"
if _SHOT_MASTER.exists() and str(_SHOT_MASTER) not in sys.path:
    sys.path.insert(0, str(_SHOT_MASTER))


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Shot-Prompt-Backwards")
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
