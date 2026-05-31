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
    homeRequested = Signal()          # 返回欢迎首页
    settingsRequested = Signal()
    helpRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FlowSidebar")
        self._buttons: dict[str, QToolButton] = {}
        self._phase_labels: list[QLabel] = []
        # func_key → 门禁阶段（STAGE_NAMES 之一）反向映射；_build 里填充。
        self._phase_of: dict[str, str] = {}
        # 阶段(STAGE_NAMES) → 该阶段标签下的「下一步」小字提示 QLabel。
        self._next_action_labels: dict[str, QLabel] = {}
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

        self.btn_home = self._make_item("首页", "home.svg")
        self.btn_home.clicked.connect(self.homeRequested)
        lay.addWidget(self.btn_home)

        for phase_title, keys in nav_config.PHASES:
            lbl = QLabel(phase_title)
            lbl.setObjectName("navPhase")
            self._phase_labels.append(lbl)
            lay.addWidget(lbl)
            # 阶段标题下的「下一步」小字提示（默认空、隐藏）；按 STAGE_NAMES 键存。
            stage = nav_config.PHASE_STAGE_MAP[phase_title]
            hint = QLabel("")
            hint.setObjectName("navNextAction")
            hint.setWordWrap(True)
            hint.setVisible(False)
            self._next_action_labels[stage] = hint
            lay.addWidget(hint)
            for key in keys:
                btn = self._make_item(nav_config.LABELS[key], nav_config.ICONS[key])
                btn.setCheckable(True)
                self._group.addButton(btn)
                self._buttons[key] = btn
                # func_key → 门禁阶段（STAGE_NAMES 之一）反向映射。
                self._phase_of[key] = stage
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
        return [self.btn_home, self.btn_settings, self.btn_help]

    def set_active(self, key: str):
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def _phase_buttons(self, phase_key: str) -> list[QToolButton]:
        """phase_key（STAGE_NAMES 之一）→ 该阶段下的功能按钮列表（按渲染顺序）。"""
        return [b for k, b in self._buttons.items() if self._phase_of.get(k) == phase_key]

    def set_phase_accessible(self, phase_key: str, accessible: bool):
        """门禁：开关某阶段（STAGE_NAMES 之一）全部功能按钮的可达性。

        禁用前若当前选中按钮落在该阶段，先把选中态转移到下一个可达按钮
        （互斥 QButtonGroup 红线：不可让禁用按钮残留选中态）。
        默认不调用本方法 → 全部按钮 enabled，行为与现状完全一致。
        """
        targets = self._phase_buttons(phase_key)
        if not accessible:
            checked = self._group.checkedButton()
            if checked is not None and checked in targets:
                # 找一个仍可达（不在本次禁用集内）的按钮承接选中态。
                fallback = next(
                    (b for b in self._buttons.values() if b not in targets), None
                )
                if fallback is not None:
                    # 互斥组下需临时放开排他，避免禁用瞬间无按钮选中导致漂移。
                    fallback.setChecked(True)
                else:
                    self._group.setExclusive(False)
                    checked.setChecked(False)
                    self._group.setExclusive(True)
        for b in targets:
            b.setEnabled(accessible)

    def set_next_action(self, phase_key: str, text: str):
        """在某阶段（STAGE_NAMES 之一）标题下显示「下一步」小字提示。

        空字符串 → 清除并隐藏。未知 phase_key 静默忽略（不抛）。
        """
        lbl = self._next_action_labels.get(phase_key)
        if lbl is None:
            return
        lbl.setText(text or "")
        lbl.setVisible(bool(text) and not self._collapsed)

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        style = Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon
        for b in list(self._buttons.values()) + self._menu_buttons():
            b.setToolButtonStyle(style)
        for lbl in self._phase_labels:
            lbl.setVisible(not collapsed)
        # 「下一步」提示仅在展开且有文本时可见。
        for hint in self._next_action_labels.values():
            hint.setVisible(not collapsed and bool(hint.text()))
        target = COLLAPSED_W if collapsed else EXPANDED_W
        # 即时收放（平滑动画留待后续精修阶段）；同步定宽保证布局与测试确定。
        self.setMinimumWidth(target)
        self.setMaximumWidth(target)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed
