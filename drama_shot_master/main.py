"""桌面应用入口：QApplication + AppShell"""
from __future__ import annotations

import sys


def _maybe_run_agent(argv: list[str]) -> int | None:
    """打包后同一 exe 兼作 agent 宿主：检测 `--run-agent <name>`。

    命中 → 在本进程跑对应 agent server，返回其退出码（不再启动 GUI）；
    未命中 → 返回 None，照常启动 GUI。
    （冻结态 sys.executable 是 app.exe，无法 `python -m`，故走此分发。）
    """
    if "--run-agent" not in argv:
        return None
    i = argv.index("--run-agent")
    which = argv[i + 1] if i + 1 < len(argv) else ""
    rest = argv[i + 2:]
    if which == "screenwriter":
        from screenwriter_agent.__main__ import main as agent_main
        return agent_main(rest)
    return None


def main() -> int:
    rc = _maybe_run_agent(sys.argv)
    if rc is not None:
        return rc
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
    # 打印 per-stage 解析结果（不打 key 内容，只打是否有 + 模型名 + 平台名），
    # 让用户直观看出哪一阶段配置缺失。
    if lifecycle.is_alive():
        print(f"[main] screenwriter_agent listening on :{actual_port}")
        stage_assigns = getattr(_early_cfg, "screenwriter_stage_assignments", {}) or {}
        providers = getattr(_early_cfg, "llm_providers", {}) or {}
        for stage in ("ideate", "script", "storyboard", "prompts"):
            a = stage_assigns.get(stage) or {}
            pname = a.get("provider", "")
            model = a.get("model", "")
            pkey_ok = bool((providers.get(pname) or {}).get("api_key")) if pname else False
            marker = "OK" if (pname and model and pkey_ok) else "缺"
            print(f"[main]   stage={stage:10s} provider={pname or '(空)':10s} "
                  f"model={model or '(空)':40s} key={'有' if pkey_ok else '无'}  [{marker}]")
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
