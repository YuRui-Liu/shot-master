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

    # 先 spawn lifecycle 并 poll /health 确认 agent 监听端口（冲突时 +1..+9 偏移）；
    # 实际端口写回 cfg，再把同一个 cfg 实例传给 AppShell ——这样 ScreenwriterPanel
    # 从 cfg.screenwriter_agent_port 取端口能命中真实监听。
    print("[main] starting screenwriter_agent subprocess...")
    lifecycle = ScreenwriterLifecycle(
        base_port=_early_cfg.screenwriter_agent_port, cfg=_early_cfg)
    actual_port = lifecycle.spawn()
    _early_cfg.screenwriter_agent_port = actual_port
    has_key = bool(_early_cfg.screenwriter_llm_api_key or any(
        (p or {}).get("api_key")
        for p in (_early_cfg.llm_providers or {}).values()))
    if lifecycle.is_alive():
        print(f"[main] screenwriter_agent listening on :{actual_port}; "
              f"LLM key configured: {has_key}")
        if not has_key:
            print("[main] WARNING: 编剧 LLM API key 未配置 → "
                  "agent 会收到请求但 LLM 调用空返回。请在 [设置] → [平台核心 / 编剧] 填入 key")
    else:
        print("[main] WARNING: screenwriter_agent subprocess died during spawn; "
              "check ~/.drama_shot_master/logs/screenwriter_agent.log")

    w = AppShell(cfg=_early_cfg)
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
