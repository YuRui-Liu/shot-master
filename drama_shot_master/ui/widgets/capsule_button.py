"""CapsuleButton：自绘胶囊按钮。

Windows11 原生 QStyle 对 QPushButton 的 QSS 渐变背景 + border-radius 支持不稳定
（渐变常常不绘制 / 圆角不裁剪），故欢迎页 CTA 改用自绘，保证跨样式一致的胶囊外观。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen, QFont
from PySide6.QtWidgets import QPushButton, QSizePolicy


class CapsuleButton(QPushButton):
    """胶囊按钮。variant='primary'（蓝紫渐变实心）或 'secondary'（描边毛玻璃）。"""

    def __init__(self, text: str, variant: str = "primary", parent=None):
        super().__init__(text, parent)
        self._variant = variant
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # 关掉原生样式表/边框影响，仅靠 paintEvent
        self.setFlat(True)
        self.setAttribute(Qt.WA_Hover, True)

    def enterEvent(self, event):  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = r.height() / 2.0
        hovered = self.underMouse()
        pressed = self.isDown()

        if self._variant == "primary":
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
            if pressed:
                grad.setColorAt(0, QColor("#3a8adf")); grad.setColorAt(1, QColor("#8a5ccf"))
            elif hovered:
                grad.setColorAt(0, QColor("#6ab0ff")); grad.setColorAt(1, QColor("#b07fff"))
            else:
                grad.setColorAt(0, QColor("#4a9eff")); grad.setColorAt(1, QColor("#a06cff"))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(r, radius, radius)
            p.setPen(QColor("#ffffff"))
        else:
            bg = QColor(30, 30, 60, 200) if hovered else QColor(19, 19, 42, 153)
            p.setBrush(QBrush(bg))
            p.setPen(QPen(QColor("#2a2a4a"), 1))
            p.drawRoundedRect(r, radius, radius)
            p.setPen(QColor("#c4cad6") if hovered else QColor("#9aa0a6"))

        f = QFont(self.font())
        f.setPixelSize(13)
        if self._variant == "primary":
            f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self.text())
        p.end()
