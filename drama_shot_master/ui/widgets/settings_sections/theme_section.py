"""主题切换 section（实时持久化、不依赖[保存]按钮）。"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox

from drama_shot_master.ui import theme as theme_mod


class ThemeSection(QWidget):
    title = "主题"
    category = "外观"

    def __init__(self, app, cfg, parent=None):
        super().__init__(parent)
        self._app = app
        self._cfg = cfg
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("界面主题（切换即生效、自动保存）"))
        self.combo = QComboBox()
        self.combo.addItems(["深色", "浅色"])
        cur_name = theme_mod.current_theme(self._cfg)
        self.combo.setCurrentText("浅色" if cur_name == "light" else "深色")
        self.combo.currentTextChanged.connect(self._apply_now)
        root.addWidget(self.combo)
        root.addStretch(1)

    def _apply_now(self, txt: str):
        name = "light" if txt == "浅色" else "dark"
        theme_mod.apply_theme(self._app, name)
        # 给本 dialog 自己的窗 + 主窗都换原生标题栏
        top = self.window()
        theme_mod.apply_titlebar(top, name)
        parent = top.parent() if top is not None else None
        if parent is not None:
            theme_mod.apply_titlebar(parent, name)
        try:
            self._cfg.update_settings(theme=name)
        except Exception:
            pass

    def load_from(self, cfg): pass        # ctor 已读
    def save_to(self, cfg): pass          # 实时持久化，无延迟保存
    def validate(self): return (True, "")
    def cancel_workers(self): pass
