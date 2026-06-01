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
import time
import urllib.request

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
    from PySide6.QtCore import QUrl
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

    # 1) media_agent —— 媒体后端 + /ui 静态托管
    media = subprocess.Popen([sys.executable, "-m", "media_agent.server"])
    media_ok = _wait_health(MEDIA_API + "/health")
    print(f"[web_app] media_agent: {'OK' if media_ok else 'TIMEOUT'} @ {MEDIA_API}")

    # 2) screenwriter_agent —— 编剧链路（复用现成 lifecycle：端口探测/health/nonce/terminate）
    lifecycle = None
    sw_port = getattr(cfg, "screenwriter_agent_port", 18430)
    try:
        from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
        lifecycle = ScreenwriterLifecycle(base_port=sw_port, cfg=cfg)
        sw_port = lifecycle.spawn() or sw_port
        print(f"[web_app] screenwriter_agent @ :{sw_port} alive={lifecycle.is_alive()}")
    except Exception as e:
        print(f"[web_app] screenwriter_agent spawn 失败(编剧页将不可用): {e}")

    # 3) 打开 Web 应用壳（同源 /ui，?sw=&media= 注入后端地址）
    url = QUrl(f"{MEDIA_API}/ui/app.html?sw=http://127.0.0.1:{sw_port}&media={MEDIA_API}")
    win = WebHostWindow(url, title="糯米 AI · 分镜影视创作台", frameless=True)
    win.resize(1360, 900)
    win.show()

    try:
        ret = app.exec()
    finally:
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
