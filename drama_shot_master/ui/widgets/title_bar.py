# drama_shot_master/ui/widgets/title_bar.py
"""无边框窗口自定义标题栏。

替代 Win11 原生标题栏 + 欢迎页旧 nav bar（糯米AI + 全局设置）的双栏叠加。
只保留一条：图标 + 「糯米 AI」 + 〈stretch〉 + ⚙全局设置 + ➖最小化 □最大化/还原 ✕关闭。

纯色自绘底（navy）+ 细下边框，避开 Win11 QSS 渐变坑（WA_StyledBackground）。
窗控按钮直接操作 self.window()；标题栏区域可拖动窗口、双击切最大化。
用户已接受放弃 Windows Aero Snap（无边框窗口手动管理拖动/缩放）。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)

# 主题 token（navy #0d1020 / 蓝 #4a9eff / 紫 #8b7fd9）
_TITLEBAR_BG = "#0d1020"        # navy 底
_TITLEBAR_BORDER = "#1e1e3a"    # 细下边框
_APP_NAME_FG = "#8b7fd9"        # 蓝紫——「糯米 AI」名色
_BTN_FG = "#9aa0a6"             # 窗控/设置常态字色
_BTN_HOVER_BG = "rgba(74,158,255,0.16)"   # 蓝调 hover 底
_BTN_PRESS_BG = "rgba(74,158,255,0.28)"
_CLOSE_HOVER_BG = "#e8434f"     # ✕ hover 红
_CLOSE_HOVER_FG = "#ffffff"

_BAR_HEIGHT = 38


def _app_icon_path() -> Path | None:
    """assets/app_icon.png 路径（按本文件相对定位，缺失返回 None）。"""
    p = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
    return p if p.exists() else None


class FramelessTitleBar(QWidget):
    """无边框窗口自定义标题栏（固定高 ~38）。

    信号：
        settingsRequested —— 用户点「⚙ 全局设置」时发射。
    窗控按钮直接驱动 self.window()：最小化 / 最大化-还原 / 关闭。
    """

    settingsRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("FramelessTitleBar")
        # 纯色自绘底（避开 Win11 QSS 渐变坑）
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(_BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 拖动偏移（globalPos - window().pos()）
        self._drag_offset = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(8)

        # 左：图标 + 「糯米 AI」
        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(20, 20)
        self._icon_lbl.setScaledContents(True)
        icon_path = _app_icon_path()
        if icon_path is not None:
            pm = QPixmap(str(icon_path))
            if not pm.isNull():
                self._icon_lbl.setPixmap(pm)
        lay.addWidget(self._icon_lbl)

        self._name_lbl = QLabel("糯米 AI")
        self._name_lbl.setObjectName("TitleBarAppName")
        self._name_lbl.setStyleSheet(
            f"color: {_APP_NAME_FG}; font-weight: 600; font-size: 13px;")
        lay.addWidget(self._name_lbl)

        # 中：stretch
        lay.addStretch(1)

        # 右：⚙ 全局设置
        self.btn_settings = QPushButton("⚙  全局设置")
        self.btn_settings.setObjectName("TitleBarSettingsBtn")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setFixedHeight(26)
        self.btn_settings.setStyleSheet(self._settings_btn_qss())
        self.btn_settings.clicked.connect(self.settingsRequested)
        lay.addWidget(self.btn_settings)
        lay.addSpacing(6)

        # 右：三窗控按钮 ➖ □ ✕
        self.btn_min = self._make_ctrl_btn("➖", is_close=False)   # ➖
        self.btn_max = self._make_ctrl_btn("□", is_close=False)   # □
        # ✕ 与 ➖/□ 同色（用户要求统一窗控按钮颜色，不用红 hover）
        self.btn_close = self._make_ctrl_btn("✕", is_close=False)  # ✕

        self.btn_min.clicked.connect(self._on_minimize)
        self.btn_max.clicked.connect(self._on_toggle_max)
        self.btn_close.clicked.connect(self._on_close)

        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

    def _make_ctrl_btn(self, text: str, *, is_close: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("TitleBarCtrlClose" if is_close else "TitleBarCtrl")
        btn.setFixedSize(46, _BAR_HEIGHT)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(self._ctrl_btn_qss(is_close=is_close))
        return btn

    @staticmethod
    def _settings_btn_qss() -> str:
        return (
            f"QPushButton#TitleBarSettingsBtn{{"
            f"  color:{_BTN_FG}; background:transparent; border:none;"
            f"  padding:0 12px; font-size:12px; border-radius:4px;}}"
            f"QPushButton#TitleBarSettingsBtn:hover{{"
            f"  background:{_BTN_HOVER_BG}; color:#e8eaed;}}"
            f"QPushButton#TitleBarSettingsBtn:pressed{{"
            f"  background:{_BTN_PRESS_BG};}}"
        )

    @staticmethod
    def _ctrl_btn_qss(*, is_close: bool) -> str:
        if is_close:
            return (
                f"QPushButton#TitleBarCtrlClose{{"
                f"  color:{_BTN_FG}; background:transparent; border:none;"
                f"  font-size:13px;}}"
                f"QPushButton#TitleBarCtrlClose:hover{{"
                f"  background:{_CLOSE_HOVER_BG}; color:{_CLOSE_HOVER_FG};}}"
                f"QPushButton#TitleBarCtrlClose:pressed{{"
                f"  background:#c5323d; color:{_CLOSE_HOVER_FG};}}"
            )
        return (
            f"QPushButton#TitleBarCtrl{{"
            f"  color:{_BTN_FG}; background:transparent; border:none;"
            f"  font-size:13px;}}"
            f"QPushButton#TitleBarCtrl:hover{{"
            f"  background:{_BTN_HOVER_BG}; color:#e8eaed;}}"
            f"QPushButton#TitleBarCtrl:pressed{{"
            f"  background:{_BTN_PRESS_BG};}}"
        )

    # ------------------------------------------------------------------ #
    # 窗控
    # ------------------------------------------------------------------ #

    def _on_minimize(self) -> None:
        win = self.window()
        if win is not None:
            win.showMinimized()

    def _on_toggle_max(self) -> None:
        """切最大化/还原，并按状态切图标 □/❐。"""
        win = self.window()
        if win is None:
            return
        if win.isMaximized():
            win.showNormal()
            self.btn_max.setText("□")        # □
        else:
            win.showMaximized()
            self.btn_max.setText("❐")        # ❐ 还原态图标
        self._sync_max_icon()

    def _sync_max_icon(self) -> None:
        """按当前窗口状态同步最大化按钮图标（外部 resize 后也可调）。"""
        win = self.window()
        if win is None:
            return
        self.btn_max.setText("❐" if win.isMaximized() else "□")

    def _on_close(self) -> None:
        win = self.window()
        if win is not None:
            win.close()

    # ------------------------------------------------------------------ #
    # 拖动 + 双击最大化
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            win = self.window()
            if win is not None:
                self._drag_offset = (
                    event.globalPosition().toPoint() - win.pos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        win = self.window()
        if (self._drag_offset is not None
                and event.buttons() & Qt.LeftButton
                and win is not None
                and not win.isMaximized()):
            win.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._on_toggle_max()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------ #
    # 自绘：navy 纯色底 + 细下边框
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(_TITLEBAR_BG))
        pen = QPen(QColor(_TITLEBAR_BORDER))
        pen.setWidth(1)
        p.setPen(pen)
        y = self.height() - 1
        p.drawLine(0, y, self.width(), y)
        p.end()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(super().sizeHint().width(), _BAR_HEIGHT)
