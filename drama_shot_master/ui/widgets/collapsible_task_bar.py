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
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QSplitter, QStackedWidget,
    QPushButton,
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
        self._expand_btn.setStyleSheet(
            "QPushButton{background:#3b6fd4;color:#fff;border:none;padding:0;"
            "border-radius:0 0 5px 5px;font-size:14px;font-weight:700;}"
            "QPushButton:hover{background:#4a83f0;}"
        )
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


# ── CollapsibleTaskBar ─────────────────────────────────────────────────────

class CollapsibleTaskBar(QWidget):
    """包裹任意 task manager，提供折叠/展开能力。

    使用方式：
        bar = CollapsibleTaskBar(manager_widget, splitter, manager_index=0)
        splitter.addWidget(bar)   # 替换原来直接插入 manager 的位置
    """

    collapsed = Signal()
    expanded = Signal()

    def __init__(self, manager: QWidget, splitter: QSplitter,
                 manager_index: int = 0,
                 expanded_width: int = 280,
                 collapsed_width: int = 40,
                 min_expanded_width: int = 240,
                 parent=None):
        super().__init__(parent)
        self._manager = manager
        self._splitter = splitter
        self._manager_index = manager_index
        self._expanded_width = expanded_width
        self._collapsed_width = collapsed_width
        # 展开态最小宽度不得超过初始展开宽度（防 min > size 的约束冲突）
        self._min_expanded_width = min(min_expanded_width, expanded_width)
        self._is_collapsed = False
        self._build_ui()
        # 初始为展开态：锁住最小宽度，splitter 无法把任务名挤扁
        self.setMinimumWidth(self._min_expanded_width)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()

        # page 0: 展开视图 —— 顶部细条(折叠按钮，布局管理，不浮动) + manager
        expanded_page = QWidget()
        ep_layout = QVBoxLayout(expanded_page)
        ep_layout.setContentsMargins(0, 0, 0, 0)
        ep_layout.setSpacing(0)

        top_strip = QWidget()
        ts_layout = QHBoxLayout(top_strip)
        ts_layout.setContentsMargins(0, 2, 4, 2)
        ts_layout.setSpacing(0)
        ts_layout.addStretch(1)
        self._collapse_btn = QPushButton("◀")
        self._collapse_btn.setFixedSize(28, 22)
        self._collapse_btn.setObjectName("taskBarCollapseBtn")
        self._collapse_btn.setToolTip("折叠任务栏")
        self._collapse_btn.setStyleSheet(
            "QPushButton{background:#3b6fd4;color:#fff;border:none;padding:0;"
            "border-radius:5px;font-size:13px;font-weight:700;}"
            "QPushButton:hover{background:#4a83f0;}"
        )
        self._collapse_btn.clicked.connect(self.collapse)
        ts_layout.addWidget(self._collapse_btn)
        ep_layout.addWidget(top_strip)
        ep_layout.addWidget(self._manager, 1)

        # page 1: 折叠视图 —— 图标轨
        self._icon_rail = _IconRail()
        self._icon_rail.expand_clicked.connect(self.expand)

        self._stack.addWidget(expanded_page)    # index 0
        self._stack.addWidget(self._icon_rail)  # index 1
        root.addWidget(self._stack)

        self._expanded_page = expanded_page

    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def _move_splitter_to(self, target_px: int) -> None:
        """通过 moveSplitter 精确设置本面板宽度，绕过 setSizes 的最小值约束。

        handle_index = manager_index + 1（handle 在本 widget 右侧）。
        """
        handle_idx = self._manager_index + 1
        # 累计前面所有面板的偏移量（含 handle 宽度）
        sizes = self._splitter.sizes()
        hw = self._splitter.handleWidth()
        offset = target_px
        for i in range(self._manager_index):
            offset += sizes[i] + hw
        self._splitter.moveSplitter(offset, handle_idx)

    def collapse(self) -> None:
        if self._is_collapsed:
            return
        sizes = self._splitter.sizes()
        if sizes and self._manager_index < len(sizes):
            current = sizes[self._manager_index]
            # 只有当实际宽度与记录值差距 > 1px 时才更新，
            # 避免 splitter 像素舍入覆盖外部传入的精确值
            if abs(current - self._expanded_width) > 1:
                self._expanded_width = current
        self._icon_rail.refresh(self._manager.icon_rail_items())
        self._stack.setCurrentIndex(1)
        self._splitter.setCollapsible(self._manager_index, True)
        # 先放开最小宽度约束，splitter 才能缩到图标轨宽度（40px）
        self.setMinimumWidth(self._collapsed_width)
        self._move_splitter_to(self._collapsed_width)
        self._is_collapsed = True
        self.collapsed.emit()

    def expand(self) -> None:
        if not self._is_collapsed:
            return
        self._stack.setCurrentIndex(0)
        # 恢复展开态最小宽度：splitter 不能再把任务名挤扁
        self.setMinimumWidth(self._min_expanded_width)
        self._move_splitter_to(self._expanded_width)
        self._is_collapsed = False
        self.expanded.emit()

    def toggle(self) -> None:
        if self._is_collapsed:
            self.expand()
        else:
            self.collapse()
