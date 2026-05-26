"""③卡点：列出/增删/微调 session.accent_points（第一版按钮+数值交互）。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QDoubleSpinBox,
)

from sound_track_agent.session import AccentPoint


class AccentEditorWidget(QWidget):
    """爆点编辑：增删微调，写回 session.accent_points。"""

    accentsChanged = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._build_ui()
        self._refresh()

    def accent_count(self) -> int:
        return len(self._session.accent_points)

    def _sorted_points(self) -> list:
        return sorted(self._session.accent_points, key=lambda a: a.t)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("爆点（出片时音乐重音吸附到这些时间点）："))
        self.listw = QListWidget()
        root.addWidget(self.listw, 1)

        row = QHBoxLayout()
        self.new_spin = QDoubleSpinBox()
        self.new_spin.setRange(0.0, 36000.0); self.new_spin.setDecimals(2)
        self.new_spin.setSuffix(" s")
        btn_add = QPushButton("+ 新增")
        btn_add.clicked.connect(lambda: self.add_accent(self.new_spin.value()))
        btn_del = QPushButton("🗑 删除选中")
        btn_del.clicked.connect(self._delete_selected)
        btn_minus = QPushButton("−0.1s")
        btn_minus.clicked.connect(lambda: self._nudge_selected(-0.1))
        btn_plus = QPushButton("+0.1s")
        btn_plus.clicked.connect(lambda: self._nudge_selected(0.1))
        for wdg in (self.new_spin, btn_add, btn_del, btn_minus, btn_plus):
            row.addWidget(wdg)
        row.addStretch(1)
        root.addLayout(row)

    def _refresh(self):
        self.listw.clear()
        for a in self._sorted_points():
            self.listw.addItem(f"{a.t:.2f}s  (强度 {a.intensity:.2f})")

    def add_accent(self, t: float):
        self._session.accent_points.append(
            AccentPoint(t=float(t), intensity=1.0, confirmed=True))
        self._refresh()
        self.accentsChanged.emit()

    def delete_accent(self, sorted_index: int):
        pts = self._sorted_points()
        if not (0 <= sorted_index < len(pts)):
            return
        target = pts[sorted_index]
        self._session.accent_points.remove(target)
        self._refresh()
        self.accentsChanged.emit()

    def nudge_accent(self, sorted_index: int, delta: float):
        pts = self._sorted_points()
        if not (0 <= sorted_index < len(pts)):
            return
        target = pts[sorted_index]
        target.t = max(0.0, target.t + delta)
        target.confirmed = True
        self._refresh()
        self.accentsChanged.emit()

    def _delete_selected(self):
        self.delete_accent(self.listw.currentRow())

    def _nudge_selected(self, delta: float):
        self.nudge_accent(self.listw.currentRow(), delta)
