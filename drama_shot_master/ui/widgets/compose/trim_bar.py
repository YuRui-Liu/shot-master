"""Trim 条：双手柄设入/出点（秒）。缩略图刷条背景可后填，逻辑独立可测。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class TrimBar(QWidget):
    trimChanged = Signal(float, float)   # in_point, out_point（秒）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dur = 0.0
        self._in = 0.0
        self._out = 0.0
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("—"); self._label.setObjectName("ComposeTrimLabel")
        lay.addWidget(self._label)
        self._scrub = _ScrubBar(self)
        self._scrub.handleMoved.connect(self._on_handle)
        lay.addWidget(self._scrub)

    def set_clip(self, duration: float, in_point, out_point):
        self._dur = max(0.0, float(duration))
        self._in = float(in_point) if in_point is not None else 0.0
        self._out = float(out_point) if out_point is not None else self._dur
        self._scrub.set_range(self._dur, self._in, self._out)
        self._update_label()

    def in_point(self) -> float: return self._in
    def out_point(self) -> float: return self._out

    def set_in(self, v: float):
        old = self._in
        self._in = max(0.0, min(float(v), self._out - 0.1))
        self._scrub.set_range(self._dur, self._in, self._out)
        self._update_label()
        if self._in != old:
            self.trimChanged.emit(self._in, self._out)

    def set_out(self, v: float):
        old = self._out
        self._out = min(self._dur, max(float(v), self._in + 0.1))
        self._scrub.set_range(self._dur, self._in, self._out)
        self._update_label()
        if self._out != old:
            self.trimChanged.emit(self._in, self._out)

    def _on_handle(self, which: str, t: float):
        self.set_in(t) if which == "in" else self.set_out(t)

    def _update_label(self):
        self._label.setText(f"入点 {self._in:.1f}s — 出点 {self._out:.1f}s（保留 {self._out - self._in:.1f}s）")


class _ScrubBar(QWidget):
    handleMoved = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40); self._dur = 0.0; self._in = 0.0; self._out = 0.0
        self._drag = None

    def set_range(self, dur, i, o):
        self._dur, self._in, self._out = dur, i, o; self.update()

    def _x_to_t(self, x: int) -> float:
        if self.width() <= 0 or self._dur <= 0:
            return 0.0
        return max(0.0, min(self._dur, x / self.width() * self._dur))

    def mousePressEvent(self, e):
        if self._dur <= 0:
            return
        t = self._x_to_t(int(e.position().x()))
        self._drag = "in" if abs(t - self._in) <= abs(t - self._out) else "out"
        self.handleMoved.emit(self._drag, t)

    def mouseMoveEvent(self, e):
        if self._drag:
            self.handleMoved.emit(self._drag, self._x_to_t(int(e.position().x())))

    def mouseReleaseEvent(self, e):
        self._drag = None

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(self); w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#1a2848"))
        if self._dur > 0:
            xi = int(self._in / self._dur * w); xo = int(self._out / self._dur * w)
            p.fillRect(xi, 0, xo - xi, h, QColor(74, 158, 255, 60))
            p.fillRect(xi, 0, 4, h, QColor("#4a9eff")); p.fillRect(xo - 4, 0, 4, h, QColor("#4a9eff"))
        p.end()
