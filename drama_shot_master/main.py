"""桌面应用入口：QApplication + AppShell"""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from drama_shot_master.ui.app_shell import AppShell
    from drama_shot_master.ui.theme import apply_theme, apply_app_icon, current_theme
    from drama_shot_master.config import load_config

    app = QApplication(sys.argv)
    app.setApplicationName("Drama-Shot-Master")
    _early_cfg = load_config()
    apply_theme(app, current_theme(_early_cfg))
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
    from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle

    # 先 spawn lifecycle（端口冲突时 +1..+9 偏移），随后把实际端口写回 cfg
    # ——任务栏化后的 ScreenwriterPanel 从 cfg.screenwriter_agent_port 读端口建 client，
    # 故必须先反写 cfg 再构建 AppShell。
    lifecycle = ScreenwriterLifecycle(base_port=_early_cfg.screenwriter_agent_port)
    lifecycle.spawn()
    _early_cfg.screenwriter_agent_port = lifecycle.port

    w = AppShell()
    w.screenwriter_lifecycle = lifecycle    # 保留引用，便于退出时 terminate

    w.show()
    try:
        ret = app.exec()
    finally:
        try:
            lifecycle.terminate()
        except Exception:
            pass
    return ret


if __name__ == "__main__":
    raise SystemExit(main())
