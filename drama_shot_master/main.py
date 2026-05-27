"""桌面应用入口：QApplication + AppShell"""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from drama_shot_master.ui.app_shell import AppShell
    from drama_shot_master.ui.theme import apply_theme, apply_app_icon, init_fluent_theme

    app = QApplication(sys.argv)
    app.setApplicationName("Drama-Shot-Master")
    apply_theme(app)
    init_fluent_theme(app)
    apply_app_icon(app)
    from drama_shot_master.licensing import manager
    from drama_shot_master.config import load_config as _lc
    if manager.requires_activation(manager.status().state):
        from drama_shot_master.ui.dialogs.about_dialog import AboutDialog
        gate = AboutDialog(_lc(), activation_focus=True)
        gate.setWindowTitle("激活 Drama-Shot-Master")
        gate.exec()
        if manager.requires_activation(manager.status().state):
            return 0          # 仍未激活 → 退出，不进主界面
    w = AppShell()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
