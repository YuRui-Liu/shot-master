"""FlowSidebar：原生流程式侧栏（替换 qfluentwidgets NavigationInterface）。

按 nav_config.PHASES 渲染：阶段标题(非点击 QLabel) + 功能项(checkable QToolButton, 互斥)；
底部 设置/帮助 按钮。可折叠为纯图标条。发 currentChanged(key)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QToolButton, QButtonGroup, QFrame, QSizePolicy,
)

from drama_shot_master.ui import nav_config

EXPANDED_W = 184
COLLAPSED_W = 52


class FlowSidebar(QWidget):
    currentChanged = Signal(str)      # 功能 key
    settingsRequested = Signal()
    helpRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FlowSidebar")
        self._buttons: dict[str, QToolButton] = {}
        self._phase_labels: list[QLabel] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._collapsed = False
        self.setMinimumWidth(EXPANDED_W)
        self.setMaximumWidth(EXPANDED_W)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(2)

        self.btn_collapse = QToolButton()
        self.btn_collapse.setObjectName("navCollapse")
        self.btn_collapse.setText("≡")
        self.btn_collapse.clicked.connect(self.toggle_collapsed)
        lay.addWidget(self.btn_collapse)

        for phase_title, keys in nav_config.PHASES:
            lbl = QLabel(phase_title)
            lbl.setObjectName("navPhase")
            self._phase_labels.append(lbl)
            lay.addWidget(lbl)
            for key in keys:
                btn = self._make_item(nav_config.LABELS[key], nav_config.ICONS[key])
                btn.setCheckable(True)
                self._group.addButton(btn)
                self._buttons[key] = btn
                btn.clicked.connect(lambda _=False, k=key: self.currentChanged.emit(k))
                lay.addWidget(btn)

        lay.addStretch(1)
        sep = QFrame()
        sep.setObjectName("navSep")
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)
        self.btn_settings = self._make_item("设置", nav_config.ICON_SETTINGS)
        self.btn_settings.clicked.connect(self.settingsRequested)
        lay.addWidget(self.btn_settings)
        self.btn_help = self._make_item("帮助 / 关于", nav_config.ICON_HELP)
        self.btn_help.clicked.connect(self.helpRequested)
        lay.addWidget(self.btn_help)

    def _make_item(self, text: str, icon_filename: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        p = nav_config.icon_path(icon_filename)
        if p is not None:
            btn.setIcon(QIcon(str(p)))
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setToolTip(text)
        return btn

    def _menu_buttons(self):
        return [self.btn_settings, self.btn_help]

    def set_active(self, key: str):
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        style = Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon
        for b in list(self._buttons.values()) + self._menu_buttons():
            b.setToolButtonStyle(style)
        for lbl in self._phase_labels:
            lbl.setVisible(not collapsed)
        target = COLLAPSED_W if collapsed else EXPANDED_W
        # 即时收放（平滑动画留待后续精修阶段）；同步定宽保证布局与测试确定。
        self.setMinimumWidth(target)
        self.setMaximumWidth(target)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed
