"""底部四步工作流指示条（纯视觉，无交互）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QFont, QFontMetrics,
    QBrush,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

_STEPS = [
    ("01", "剧本创作"),
    ("02", "AI 分镜出图"),
    ("03", "生成视频"),
    ("04", "后期配音配乐"),
]

_C_ACTIVE_LABEL = QColor("#c0c8e0")
_C_INACTIVE_LABEL = QColor("#3a4a6a")
_C_ACTIVE_ARROW = QColor("#4a9eff")
_C_INACTIVE_ARROW = QColor("#252540")
_C_DOT_INACTIVE_BG = QColor("#111128")
_C_DOT_INACTIVE_BORDER = QColor("#252540")
_C_LINE = QColor("#1e1e3a")


class WorkflowStrip(QWidget):
    """一行四步流程条，active_index 对应高亮步骤（默认 0 = 剧本创作）。"""

    def __init__(self, active_index: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self._active = active_index
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_active(self, index: int) -> None:
        self._active = index
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cy = h // 2

        # — fading horizontal lines —
        for start_x, end_x in [(0, w // 4), (w * 3 // 4, w)]:
            grad = QLinearGradient(start_x, 0, end_x, 0)
            if start_x == 0:
                grad.setColorAt(0, QColor(0, 0, 0, 0))
                grad.setColorAt(1, _C_LINE)
            else:
                grad.setColorAt(0, _C_LINE)
                grad.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRect(start_x, cy - 1, end_x - start_x, 2)

        # — compute step positions —
        dot_r = 10          # radius of step dot
        font_label = QFont(self.font())
        font_label.setPixelSize(11)
        font_num = QFont(self.font())
        font_num.setPixelSize(9)
        font_num.setBold(True)

        # Measure total content width for centering
        arrow_w = 14
        label_gap = 5
        step_widths = []
        fm_label = QFontMetrics(font_label)
        for _num, label in _STEPS:
            step_widths.append(dot_r * 2 + label_gap + fm_label.horizontalAdvance(label))
        total_w = sum(step_widths) + arrow_w * (len(_STEPS) - 1)
        x = (w - total_w) // 2

        for i, (num, label) in enumerate(_STEPS):
            active = i == self._active
            cx = x + dot_r

            # dot background
            if active:
                grad = QLinearGradient(cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r)
                grad.setColorAt(0, QColor("#4a9eff"))
                grad.setColorAt(1, QColor("#a06cff"))
                p.setBrush(QBrush(grad))
                p.setPen(Qt.NoPen)
            else:
                p.setBrush(QColor(_C_DOT_INACTIVE_BG))
                p.setPen(QColor(_C_DOT_INACTIVE_BORDER))

            p.drawEllipse(QPoint(cx, cy), dot_r, dot_r)

            # dot number
            p.setPen(_C_ACTIVE_LABEL if active else _C_INACTIVE_LABEL)
            p.setFont(font_num)
            p.drawText(
                QRect(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2),
                Qt.AlignCenter, num,
            )

            # label
            lx = cx + dot_r + label_gap
            if active:
                bold_font = QFont(font_label)
                bold_font.setBold(True)
                p.setFont(bold_font)
                p.setPen(_C_ACTIVE_LABEL)
            else:
                p.setFont(font_label)
                p.setPen(_C_INACTIVE_LABEL)

            label_rect = QRect(lx, cy - 10, step_widths[i] - dot_r * 2 - label_gap, 20)
            p.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

            x += step_widths[i]

            # arrow
            if i < len(_STEPS) - 1:
                p.setPen(_C_ACTIVE_ARROW if active else _C_INACTIVE_ARROW)
                p.setFont(QFont(self.font()))
                p.drawText(
                    QRect(x, cy - 10, arrow_w, 20),
                    Qt.AlignCenter, "›",
                )
                x += arrow_w

        p.end()
