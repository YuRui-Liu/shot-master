"""缩略图徽章 delegate：order 模式下左上角画蓝圈白色序号；multi 模式画蓝色描边。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QFont, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle


BADGE_ROLE = Qt.UserRole + 100      # int 序号，或 None
SELECTED_ROLE = Qt.UserRole + 101   # bool，multi 模式高亮


class ThumbnailDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        rect = option.rect

        selected = index.data(SELECTED_ROLE)
        if selected:
            painter.save()
            pen = QPen(QColor(79, 142, 220))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(2, 2, -2, -2))
            painter.restore()

        badge = index.data(BADGE_ROLE)
        if badge is not None:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            d = 24
            x = rect.left() + 6
            y = rect.top() + 6
            painter.setBrush(QColor(79, 142, 220))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(x, y, d, d)
            painter.setPen(Qt.white)
            f = QFont()
            f.setBold(True)
            f.setPointSize(10)
            painter.setFont(f)
            painter.drawText(QRectF(x, y, d, d), Qt.AlignCenter, str(badge))
            painter.restore()
