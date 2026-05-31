"""桌面应用入口：QApplication + AppShell"""
from __future__ import annotations

import sys

# 启动加载窗口：QApplication 之后、子进程/cfg/AppShell 构造期间分阶段显示。
# 顶层导入便于测试以 monkeypatch main.SplashScreen 注入轻量替身。
from drama_shot_master.ui.widgets.splash import SplashScreen


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


def _splash_credits(cfg) -> tuple[str, str]:
    """从 cfg 取作者 / 商务字段（有则显，缺则降级默认）。

    config 当前无专门字段，故从 ui 字典 / 可选属性宽松读取，避免硬依赖。
    """
    author = (
        getattr(cfg, "splash_author", None)
        or (getattr(cfg, "ui", {}) or {}).get("splash_author")
        or "二进制糯米"
    )
    business = (
        getattr(cfg, "splash_business", None)
        or (getattr(cfg, "ui", {}) or {}).get("splash_business")
        or ""
    )
    return str(author), str(business)


def _run_with_splash(cfg, *, shell_factory=None, lifecycle_factory=None):
    """在 splash 加载窗口下完成「spawn agent → 构造 AppShell → 显示主窗」。

    分阶段驱动 splash（加载配置 / 索引项目 / 准备工作区），AppShell 构造完毕后
    close splash 再 show 主窗。show()/processEvents 不阻塞事件循环。

    参数 shell_factory / lifecycle_factory 仅供测试注入轻量替身；生产为 None 时
    分别取真实 AppShell / ScreenwriterLifecycle。返回构造好的（已 show 的）shell。
    """
    if shell_factory is None:
        from drama_shot_master.ui.app_shell import AppShell
        shell_factory = AppShell
    if lifecycle_factory is None:
        from drama_shot_master.agents.screenwriter_lifecycle import (
            ScreenwriterLifecycle,
        )
        lifecycle_factory = ScreenwriterLifecycle

    splash = SplashScreen()
    author, business = _splash_credits(cfg)
    splash.set_credits(author, business)
    splash.show()
    _pump()

    # ── 阶段 0：加载配置 / 风格圣经（cfg 已 load，这里仅标记 + 起 agent 子进程）
    splash.set_stage(0, "active")
    splash.set_progress(0.1)
    _pump()
    print("[main] starting screenwriter_agent subprocess...")
    lifecycle = lifecycle_factory(
        base_port=cfg.screenwriter_agent_port, cfg=cfg)
    actual_port = lifecycle.spawn()
    cfg.screenwriter_agent_port = actual_port
    # 打印 per-stage 解析结果（不打 key 内容，只打是否有 + 模型名 + 平台名），
    # 让用户直观看出哪一阶段配置缺失。
    if lifecycle.is_alive():
        print(f"[main] screenwriter_agent listening on :{actual_port}")
        stage_assigns = getattr(cfg, "screenwriter_stage_assignments", {}) or {}
        providers = getattr(cfg, "llm_providers", {}) or {}
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
    splash.set_stage(0, "done")
    splash.set_progress(0.4)
    _pump()

    # ── 阶段 1：索引项目资源
    splash.set_stage(1, "active")
    _pump()
    splash.set_stage(1, "done")
    splash.set_progress(0.6)
    _pump()

    # ── 阶段 2：准备工作区（构造 AppShell — 最重的一步）
    splash.set_stage(2, "active")
    _pump()
    w = shell_factory(cfg=cfg)
    w.screenwriter_lifecycle = lifecycle    # 保留引用，便于退出时 terminate
    splash.set_stage(2, "done")
    splash.set_progress(1.0)
    _pump()

    # close splash 再 show 主窗（避免置顶 splash 盖主窗）
    splash.close()
    w.show()
    return w


def _pump() -> None:
    """刷事件队列让 splash 立即重绘，不阻塞主事件循环。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def main() -> int:
    rc = _maybe_run_agent(sys.argv)
    if rc is not None:
        return rc
    from PySide6.QtWidgets import QApplication
    from drama_shot_master.ui.app_shell import AppShell
    from drama_shot_master.ui.theme import apply_theme, apply_app_icon, current_theme
    from drama_shot_master.config import load_config

    app = QApplication(sys.argv)
    app.setApplicationName("糯米AI分镜影视创作台")
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
    w = _run_with_splash(_early_cfg)
    lifecycle = w.screenwriter_lifecycle    # 退出时 terminate 用
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
