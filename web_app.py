"""糯米 AI · Web 应用启动器 —— 让软件真正进入 HTML UI（绞杀者迁移的运行入口）。

启动流程：
  1) spawn media_agent(18450)：既是媒体后端(imaging/转场/出图/配乐/skills)，又经 /ui
     静态同源托管 web/ 设计系统页面。
  2) spawn screenwriter_agent：编剧链路 SSE(立意/剧本/分镜/提示词/视频/配音)。
  3) QWebEngine 打开 http://127.0.0.1:18450/ui/app.html —— 即 web/app.html 应用壳
     (糯米 AI 顶栏 + 本项目 6 导航 + hash 路由)，各内容页经 ?sw=&media= 调两个后端。
  4) 退出：确定性 teardown 先 terminate 两个 agent 再回收窗口，避免 exit5 native 崩溃。

与现有 PySide6 `python -m drama_shot_master.main` 并存（绞杀者：Web 入口逐步取代）。
"""
import os
os.environ.setdefault("PYTHONUNBUFFERED", "1")

import sys
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

MEDIA_PORT = 18450
MEDIA_API = f"http://127.0.0.1:{MEDIA_PORT}"


def _wait_health(url: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QUrl, QTimer
    from drama_shot_master.config import load_config
    from drama_shot_master.ui.web_host import WebHostWindow

    app = QApplication(sys.argv)
    app.setApplicationName("糯米AI分镜影视创作台")
    cfg = load_config()
    try:
        from drama_shot_master.ui.theme import apply_theme, current_theme
        apply_theme(app, current_theme(cfg))
    except Exception:
        pass

    # 0) 打开即显加载页(splash.html, file://) —— 立刻可见，缓解等待感
    web_dir = Path(__file__).parent / "web"
    win = WebHostWindow(QUrl.fromLocalFile(str(web_dir / "splash.html")),
                        title="糯米 AI · 分镜影视创作台", frameless=True)
    win.resize(1360, 900)
    win.show()
    app.processEvents()   # 立即渲染 splash

    def _js(code: str):
        try:
            win.view.page().runJavaScript(code)
        except Exception:
            pass

    state = {"lifecycle": None, "media": None, "media_ok": False, "ready": False,
             "sw_port": getattr(cfg, "screenwriter_agent_port", 18430)}

    def _work():
        # 后台线程 spawn 两个 agent —— 不阻塞 GUI，splash 才能立即渲染+动画
        state["media"] = subprocess.Popen([sys.executable, "-m", "media_agent.server"])
        state["media_ok"] = _wait_health(MEDIA_API + "/health")
        print(f"[web_app] media_agent: {'OK' if state['media_ok'] else 'TIMEOUT'} @ {MEDIA_API}")
        try:
            from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
            lc = ScreenwriterLifecycle(base_port=state["sw_port"], cfg=cfg)
            state["sw_port"] = lc.spawn() or state["sw_port"]
            state["lifecycle"] = lc
            print(f"[web_app] screenwriter_agent @ :{state['sw_port']} alive={lc.is_alive()}")
        except Exception as e:
            print(f"[web_app] screenwriter_agent spawn 失败(编剧页将不可用): {e}")
        state["ready"] = True

    prog = {"p": 0.06, "m": False}
    timer = QTimer()

    def _tick():
        # 主线程驱动 splash 进度/阶段；ready 后切 app.html
        if state["media_ok"] and not prog["m"]:
            prog["m"] = True
            _js("window.splashStage && (splashStage(0,'done'),splashStage(1,'active'))")
        prog["p"] = min(0.92, prog["p"] + 0.02)
        _js(f"window.splashProgress && splashProgress({prog['p']:.3f})")
        if state["ready"]:
            timer.stop()
            _js("window.splashStage && (splashStage(1,'done'),splashStage(2,'done'),splashStage(3,'done')); window.splashProgress && splashProgress(1)")
            sw = state["sw_port"]
            win.view.load(QUrl(f"{MEDIA_API}/ui/app.html?sw=http://127.0.0.1:{sw}&media={MEDIA_API}"))

    state["_timer"] = timer
    timer.timeout.connect(_tick)
    def _start():
        _js("window.splashStage && splashStage(0,'active')")
        threading.Thread(target=_work, daemon=True).start()
        timer.start(150)
    QTimer.singleShot(120, _start)   # 让 splash 先绘出再起后端(后台线程)

    try:
        ret = app.exec()
    finally:
        lifecycle = state["lifecycle"]
        media = state["media"]
        # 4) 确定性 teardown（避免 widget 在 QApplication 销毁后析构 → exit5）
        if lifecycle is not None:
            try:
                lifecycle.terminate()
            except Exception:
                pass
        try:
            media.terminate(); media.wait(timeout=5)
        except Exception:
            try:
                media.kill()
            except Exception:
                pass
        try:
            win.hide(); win.deleteLater()
            app.processEvents(); app.sendPostedEvents(None, 0)
        except Exception:
            pass
    return ret if isinstance(ret, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
