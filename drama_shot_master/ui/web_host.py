"""QWebEngine 宿主窗口 — Web UI 重构的起步壳。

支持无边框模式：去掉原生标题栏，只留 HTML 壳自带的「糯米 AI」标题栏（避免双标题栏）。
窗控(最小化/最大化/关闭/拖动)经 QWebChannel 暴露给 JS：window.winctl。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, QObject, Slot, QFile, QIODevice
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineScript
from PySide6.QtWebChannel import QWebChannel


class _WinCtl(QObject):
    """暴露给 JS 的窗控对象（window.winctl）。"""

    def __init__(self, win: QMainWindow):
        super().__init__(win)
        self._win = win

    @Slot()
    def minimize(self):
        self._win.showMinimized()

    @Slot()
    def toggleMax(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    @Slot()
    def closeWin(self):
        self._win.close()

    @Slot()
    def startMove(self):
        wh = self._win.windowHandle()
        if wh is not None:
            wh.startSystemMove()


class WebHostWindow(QMainWindow):
    """加载本地 HTML 页面的 QWebEngine 窗口。

    frameless=True 时去原生边框，由 HTML 壳标题栏 + winctl 桥接管窗控。
    """

    def __init__(self, page_url: QUrl, title: str = "糯米AI · 分镜影视创作台",
                 frameless: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 720)
        if frameless:
            self.setWindowFlags(Qt.FramelessWindowHint)

        self.view = QWebEngineView(self)
        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        if frameless:
            self._winctl = _WinCtl(self)
            self._channel = QWebChannel(self)
            self._channel.registerObject("winctl", self._winctl)
            self.view.page().setWebChannel(self._channel)
            self._inject_winctl_bridge()

        self.view.load(page_url)
        self.setCentralWidget(self.view)

    def _inject_winctl_bridge(self):
        """注入 qwebchannel.js + 建立 window.winctl（DocumentCreation 早于页面脚本）。"""
        f = QFile(":/qtwebchannel/qwebchannel.js")
        if not f.open(QIODevice.ReadOnly):
            return
        js = bytes(f.readAll().data()).decode("utf-8")
        f.close()
        setup = js + """
        (function(){
          function bind(){
            new QWebChannel(qt.webChannelTransport, function(ch){
              window.winctl = ch.objects.winctl;
              document.documentElement.setAttribute('data-host','qt');
            });
          }
          if (window.qt && qt.webChannelTransport) bind();
          else document.addEventListener('DOMContentLoaded', bind);
        })();
        """
        script = QWebEngineScript()
        script.setName("winctl-bridge")
        script.setSourceCode(setup)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self.view.page().scripts().insert(script)

    @classmethod
    def for_page(cls, page_path: Path, query: str = "", **kw) -> "WebHostWindow":
        url = QUrl.fromLocalFile(str(Path(page_path).resolve()))
        if query:
            url.setQuery(query)
        return cls(url, **kw)
