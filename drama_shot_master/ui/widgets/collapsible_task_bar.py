"""CollapsibleTaskBar：任务栏折叠/展开包装器。

组件层次：
  IconRailItem          dataclass — 图标轨一行数据
  _RailBadge            QWidget   — 单个圆形徽章行（40×36px）
  _IconRail             QWidget   — 整个图标轨（顶部展开按钮 + 徽章列表）
  CollapsibleTaskBar    QWidget   — 包装任意 task manager，提供折叠/展开
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QSplitter, QStackedWidget, QPushButton,
)


# ── 数据类 ─────────────────────────────────────────────────────────────────

@dataclass
class IconRailItem:
    index: int        # 1-based 序号
    label: str        # 项目名首两字（备用）
    status: str       # "done" | "running" | "idle" | "error"
    tooltip: str      # "项目名\n当前阶段: xxx"
    item_id: str      # 路径或 task_id 字符串


# ── _RailBadge ─────────────────────────────────────────────────────────────

class _RailBadge(QWidget):
    """40×36px 圆形徽章行：序号圆 + 右下角状态点。点击发出 clicked(item_id)。"""

    clicked = Signal(str)

    STATUS_COLORS: dict[str, str] = {
        "done":    "#52b788",
        "running": "#4a9eff",
        "idle":    "#666666",
        "error":   "#e05252",
    }

    def __init__(self, item: IconRailItem, parent=None):
        super().__init__(parent)
        self._item = item
        self.setFixedSize(40, 36)
        self.setToolTip(item.tooltip)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        badge_size = 24
        bx = (self.width() - badge_size) // 2
        by = (self.height() - badge_size) // 2 - 1
        p.setBrush(QColor("#3a3f4a"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(bx, by, badge_size, badge_size)

        p.setPen(QPen(QColor("#d0d4dc")))
        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(bx, by, badge_size, badge_size,
                   Qt.AlignCenter, str(self._item.index))

        dot_color = self.STATUS_COLORS.get(self._item.status, "#666666")
        p.setBrush(QColor(dot_color))
        p.setPen(Qt.NoPen)
        dot_size = 8
        dx = bx + badge_size - dot_size // 2
        dy = by + badge_size - dot_size // 2
        p.drawEllipse(dx, dy, dot_size, dot_size)

        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._item.item_id)
        super().mousePressEvent(event)


# ── _IconRail ──────────────────────────────────────────────────────────────

class _IconRail(QWidget):
    """固定 40px 宽的图标轨：顶部 ▶ 展开按钮 + 下方徽章列表。"""

    expand_clicked = Signal()
    item_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(40)
        self._badges: list[_RailBadge] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        self._expand_btn = QPushButton("▶")
        self._expand_btn.setFixedSize(40, 28)
        self._expand_btn.setToolTip("展开任务栏")
        self._expand_btn.setObjectName("iconRailExpandBtn")
        self._expand_btn.clicked.connect(self.expand_clicked)
        layout.addWidget(self._expand_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll = scroll

        container = QWidget()
        self._badge_layout = QVBoxLayout(container)
        self._badge_layout.setContentsMargins(0, 2, 0, 2)
        self._badge_layout.setSpacing(0)
        self._badge_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

    def refresh(self, items: list[IconRailItem]) -> None:
        for badge in self._badges:
            self._badge_layout.removeWidget(badge)
            badge.deleteLater()
        self._badges.clear()

        for item in items:
            badge = _RailBadge(item)
            badge.clicked.connect(self.item_clicked)
            self._badge_layout.insertWidget(
                self._badge_layout.count() - 1, badge)
            self._badges.append(badge)

    def badge_count(self) -> int:
        return len(self._badges)
