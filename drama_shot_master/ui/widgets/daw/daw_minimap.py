"""3 轨 minimap + 蓝色窗口框。viewportRequested(offset) 信号让 DawTrackView 跟随。"""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt, QRect
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget


_TRACK_COLORS = {
    "bgm":      QColor("#4a7eb8"),
    "sfx":      QColor("#c2884c"),
    "dialogue": QColor("#5a9f5a"),
}


class DawMinimap(QWidget):
    viewportRequested = Signal(float)    # scroll_offset 0.0-1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cues = []
        self._duration = 30.0
        self._scroll_offset = 0.0
        self._viewport_fraction = 1.0    # 默认 100%（FIT）
        self.setMinimumHeight(28)
        self.setMaximumHeight(40)
        self.setMouseTracking(True)

    def set_cues(self, cues) -> None:
        self._cues = list(cues)
        self.update()

    def set_duration(self, total_sec: float) -> None:
        self._duration = max(0.001, float(total_sec))
        self.update()

    def set_viewport(self, scroll_offset: float, viewport_fraction: float) -> None:
        self._scroll_offset = max(0.0, min(1.0, float(scroll_offset)))
        self._viewport_fraction = max(0.01, min(1.0, float(viewport_fraction)))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor("#1a1a1a"))
            h_per = max(2, self.height() // 3 - 1)
            for i, track in enumerate(["bgm", "sfx", "dialogue"]):
                y = i * (h_per + 1) + 1
                p.fillRect(0, y, self.width(), h_per, QColor("#2a2a2a"))
                color = _TRACK_COLORS[track]
                for c in self._cues:
                    if c.track != track:
                        continue
                    x_a = int(self.width() * c.t_start / self._duration)
                    x_b = int(self.width() * c.t_end / self._duration)
                    p.fillRect(x_a, y, max(1, x_b - x_a), h_per, color)
            # 蓝色 viewport 窗口
            win_x = int(self.width() * self._scroll_offset)
            win_w = max(2, int(self.width() * self._viewport_fraction))
            p.setPen(QColor("#4a7eb8"))
            p.fillRect(QRect(win_x, 0, win_w, self.height()),
                       QColor(74, 126, 184, 50))
            p.drawRect(win_x, 0, win_w, self.height() - 1)
        finally:
            p.end()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        x = ev.pos().x()
        target_center = x / max(1, self.width())
        new_offset = max(0.0, target_center - self._viewport_fraction / 2)
        new_offset = min(new_offset, 1.0 - self._viewport_fraction)
        self.viewportRequested.emit(new_offset)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            self.mousePressEvent(ev)
