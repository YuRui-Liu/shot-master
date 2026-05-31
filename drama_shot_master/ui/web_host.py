"""QWebEngine 宿主窗口 — Web UI 重构(M1)的起步壳。

绞杀者模式：用 QWebEngineView 在现有 PySide6 进程里承载 HTML 页面（设计稿即 UI），
页面经 fetch 调本地 media_agent(零 Qt 后端)。Web 资产将来可零改动平移到 pywebview/Tauri。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings


class WebHostWindow(QMainWindow):
    """加载本地 HTML 页面的 QWebEngine 窗口。

    page_url 可带 query（如 ?api=...&img=...）。开发期允许 file:// 内容访问
    远程(本地 media_agent) URL。
    """

    def __init__(self, page_url: QUrl, title: str = "糯米AI · Web 预览",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 720)
        self.view = QWebEngineView(self)
        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.view.load(page_url)
        self.setCentralWidget(self.view)

    @classmethod
    def for_page(cls, page_path: Path, query: str = "", **kw) -> "WebHostWindow":
        """从本地 HTML 文件路径构造（query 形如 'api=...&img=...'）。"""
        url = QUrl.fromLocalFile(str(Path(page_path).resolve()))
        if query:
            url.setQuery(query)
        return cls(url, **kw)
