"""主窗口：QMainWindow + 6 Tab"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel,
    QHBoxLayout, QWidget,
)

from app.config import load_config
import app.providers  # noqa: F401  触发 provider 注册

from app.ui.tabs.inference_tab import InferenceTab
from app.ui.tabs.split_tab import SplitTab
from app.ui.tabs.combine_tab import CombineTab
from app.ui.tabs.trim_tab import TrimTab
from app.ui.tabs.templates_tab import TemplatesTab
from app.ui.tabs.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shot-Prompt-Backwards · 分镜提示词反推工具")
        self.resize(1280, 820)

        self.cfg = load_config()

        # 6 Tab
        tabs = QTabWidget()
        tabs.addTab(InferenceTab(self.cfg, parent=self), "反推")
        tabs.addTab(SplitTab(self.cfg, parent=self), "拆图")
        tabs.addTab(CombineTab(self.cfg, parent=self), "拼图")
        tabs.addTab(TrimTab(self.cfg, parent=self), "去白边")
        tabs.addTab(TemplatesTab(self.cfg, parent=self), "模板")
        tabs.addTab(SettingsTab(self.cfg, parent=self), "设置")
        self.setCentralWidget(tabs)
        self.tabs = tabs

        # 状态栏：显示当前 provider / model
        sb = QStatusBar()
        self.status_label = QLabel(self._status_text())
        sb.addPermanentWidget(self.status_label)
        self.setStatusBar(sb)

    def _status_text(self) -> str:
        return f"后端: {self.cfg.current_provider} · 模型: {self.cfg.current_model}"

    def refresh_status(self):
        """SettingsTab 改了 provider/model 后调"""
        self.status_label.setText(self._status_text())
