"""ProjectCard：欢迎首页项目卡片，支持深度样式（far/near/center），点击发 clicked(path)。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QFont, QBrush, QPen, QPainterPath,
)
from PySide6.QtWidgets import (
    QWidget, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QSizePolicy,
)

# 各深度的不透明度
_DEPTH_OPACITY = {"far": 0.50, "near": 0.72, "center": 1.0, "add": 0.60}

# 各深度的高度比例（相对卡片区可用高度），中心卡最高、两侧渐矮，配合垂直居中形成景深阶梯
_DEPTH_HEIGHT_RATIO = {"far": 0.78, "near": 0.88, "center": 1.0, "add": 0.72}

# 缩略图渐变配色（每次显示固定色，不随机）
_THUMB_COLORS = [
    ("#1a2848", "#2a1848"),  # 蓝紫
    ("#281020", "#1a1030"),  # 深红紫
    ("#102820", "#1a2028"),  # 深绿
    ("#201a10", "#281818"),  # 暖棕
]


class ProjectCard(QWidget):
    """单张项目卡片。

    Args:
        project: 项目信息字典 {"name", "path", "last_opened", "shot_count"}，
                 None 时显示"新建"虚线卡。
        depth:   "far" | "near" | "center" | "add"，控制大小和透明度。
        color_index: 缩略图渐变色序号（0-3），默认 0。
        is_add_button: True 时强制为新建卡（忽略 project 值）。
    """

    clicked = Signal(str)  # path（add 卡为空字符串）

    def __init__(
        self,
        project: dict | None = None,
        depth: str = "center",
        color_index: int = 0,
        is_add_button: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._project = project
        self._depth = depth
        self._color_index = color_index % len(_THUMB_COLORS)
        self._is_add = is_add_button or project is None
        self._height_ratio = _DEPTH_HEIGHT_RATIO.get(depth, 1.0)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 自绘圆角背景，透明底让圆角/发光干净呈现
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 一个 QWidget 只能挂一个 graphicsEffect：
        #   中心卡(opacity≈1) → 蓝紫外发光；其余 → 景深不透明度
        opacity = _DEPTH_OPACITY.get(depth, 1.0)
        if depth == "center":
            glow = QGraphicsDropShadowEffect(self)
            glow.setBlurRadius(48)
            glow.setOffset(0, 0)
            glow.setColor(QColor(74, 158, 255, 130))   # #4a9eff 辉光
            self.setGraphicsEffect(glow)
        elif opacity < 0.99:
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(opacity)
            self.setGraphicsEffect(effect)

    def height_ratio(self) -> float:
        """相对卡片区可用高度的高度比例（景深用）。"""
        return self._height_ratio

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            path = "" if self._is_add else (self._project or {}).get("path", "")
            self.clicked.emit(path)
        super().mousePressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()

        if self._is_add:
            self._paint_add(p, r)
        else:
            self._paint_project(p, r)
        p.end()

    def _paint_add(self, p: QPainter, r: QRect) -> None:
        pen = QPen(QColor("#252540"))
        pen.setStyle(Qt.DashLine)
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)
        p.setPen(QColor("#353555"))
        font = QFont(self.font())
        font.setPixelSize(28)
        p.setFont(font)
        p.drawText(QRect(r.x(), r.y(), r.width(), r.height() - 20), Qt.AlignCenter, "＋")
        font.setPixelSize(10)
        p.setFont(font)
        p.drawText(QRect(r.x(), r.bottom() - 28, r.width(), 20), Qt.AlignCenter, "新建项目")

    def _paint_project(self, p: QPainter, r: QRect) -> None:
        colors = _THUMB_COLORS[self._color_index]
        bg_grad = QLinearGradient(r.topLeft(), r.bottomRight())
        bg_grad.setColorAt(0, QColor("#1a1a38"))
        bg_grad.setColorAt(1, QColor("#131328"))
        p.setBrush(QBrush(bg_grad))
        if self._depth == "center":
            p.setPen(QPen(QColor("#4a9eff"), 1))
        else:
            p.setPen(QPen(QColor("#252540"), 1))
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)

        meta_h = 44
        thumb_r = QRect(r.x(), r.y(), r.width(), r.height() - meta_h)
        thumb_grad = QLinearGradient(thumb_r.topLeft(), thumb_r.bottomRight())
        thumb_grad.setColorAt(0, QColor(colors[0]))
        thumb_grad.setColorAt(1, QColor(colors[1]))
        p.setBrush(QBrush(thumb_grad))
        p.setPen(Qt.NoPen)
        cp = QPainterPath()
        cp.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 10, 10)
        p.setClipPath(cp)
        p.drawRect(thumb_r)

        mask_h = thumb_r.height() // 2
        mask_grad = QLinearGradient(0, thumb_r.bottom() - mask_h, 0, thumb_r.bottom())
        mask_grad.setColorAt(0, QColor(0, 0, 0, 0))
        mask_grad.setColorAt(1, QColor(10, 10, 28, 210))
        p.setBrush(QBrush(mask_grad))
        p.drawRect(QRect(thumb_r.x(), thumb_r.bottom() - mask_h, thumb_r.width(), mask_h))

        if self._depth == "center":
            tag_r = QRect(thumb_r.x() + 10, thumb_r.y() + 10, 50, 18)
            p.setBrush(QColor(74, 158, 255, 64))
            p.setPen(QPen(QColor("#4a9eff"), 1))
            p.drawRoundedRect(tag_r, 3, 3)
            p.setPen(QColor("#a0c8ff"))
            font = QFont(self.font())
            font.setPixelSize(9)
            p.setFont(font)
            p.drawText(tag_r, Qt.AlignCenter, "AI 主创")

        p.setClipping(False)

        meta_r = QRect(r.x(), r.bottom() - meta_h, r.width(), meta_h)
        p.setBrush(QColor(13, 13, 30, 230))
        p.setPen(Qt.NoPen)
        bottom_cp = QPainterPath()
        # Extend upward by 10px so top corners are clipped away — only bottom corners remain rounded
        bottom_cp.addRoundedRect(
            meta_r.x(), meta_r.y() - 10,
            meta_r.width(), meta_r.height() + 10,
            10, 10
        )
        p.setClipPath(bottom_cp)
        p.drawRect(meta_r)
        p.setClipping(False)

        name = (self._project or {}).get("name", "")
        shot_count = (self._project or {}).get("shot_count", 0)
        last_opened = (self._project or {}).get("last_opened", "")

        font_name = QFont(self.font())
        font_name.setPixelSize(11)
        font_name.setBold(True)
        p.setFont(font_name)
        p.setPen(QColor("#d0d8f0"))
        p.drawText(QRect(meta_r.x() + 10, meta_r.y() + 6, meta_r.width() - 20, 16),
                   Qt.AlignVCenter | Qt.AlignLeft, name)

        dot_cx = meta_r.x() + 10 + 3
        dot_cy = meta_r.y() + 28
        if self._depth == "center":
            p.setBrush(QColor("#4a9eff"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(dot_cx - 3, dot_cy - 3, 6, 6)

        info_parts = []
        if shot_count:
            info_parts.append(f"{shot_count}张分镜")
        if last_opened:
            try:
                dt = datetime.fromisoformat(last_opened)
                delta = (datetime.now() - dt).days
                if delta == 0:
                    info_parts.append("今天")
                elif delta == 1:
                    info_parts.append("昨天")
                elif delta < 7:
                    info_parts.append(f"{delta}天前")
                else:
                    info_parts.append(f"{delta // 7}周前")
            except Exception:
                pass
        info_text = " · ".join(info_parts)
        font_info = QFont(self.font())
        font_info.setPixelSize(9)
        p.setFont(font_info)
        p.setPen(QColor("#5a6a8a"))
        info_x = (dot_cx + 7) if self._depth == "center" else meta_r.x() + 10
        p.drawText(QRect(info_x, meta_r.y() + 20, meta_r.width() - 20, 16),
                   Qt.AlignVCenter | Qt.AlignLeft, info_text)
