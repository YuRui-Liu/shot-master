"""4 轨自绘 mini-timeline + 播放头 + scrubbing。

不使用 QGraphicsView（杀鸡用牛刀），自绘 paintEvent。
4 轨顺序: 视频 / BGM / SFX / 对白；播放头红色竖线穿透所有轨。
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget

from drama_shot_master.ui.widgets.overview_timeline_model import _Cue


_TRACK_HEIGHTS = {"video": 18, "bgm": 22, "sfx": 22, "dialogue": 22}
_TRACK_ORDER = ["video", "bgm", "sfx", "dialogue"]
_TRACK_COLORS = {
    "video":    QColor("#555555"),
    "bgm":      QColor("#4a7eb8"),
    "sfx":      QColor("#c2884c"),
    "dialogue": QColor("#5a9f5a"),
}
_LABEL_WIDTH = 60
_AXIS_HEIGHT = 14
_ROW_GAP = 2
_PLAYHEAD_COLOR = QColor("#e63946")
_BG_TRACK_COLOR = QColor("#2a2a2a")
_BG_FRAME_COLOR = QColor("#1e1e1e")
_AXIS_COLOR = QColor("#444444")
_TEXT_COLOR = QColor("#ffffff")
_LABEL_COLOR = QColor("#888888")


class OverviewTimeline(QWidget):
    playheadDragged = Signal(float)
    cueClicked = Signal(str, int, float)
    _DRAG_THROTTLE_MS = 33

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cues: list[_Cue] = []
        self._duration = 30.0
        self._playhead = 0.0
        self._dragging = False
        self._pending_drag_t: Optional[float] = None
        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.setInterval(self._DRAG_THROTTLE_MS)
        self._drag_timer.timeout.connect(self._flush_drag)
        total = _AXIS_HEIGHT + sum(_TRACK_HEIGHTS.values()) + 3 * _ROW_GAP
        self.setMinimumHeight(total)
        self.setMouseTracking(True)

    def set_cues(self, cues: list[_Cue]) -> None:
        self._cues = list(cues)
        self.update()

    def set_duration(self, total_sec: float) -> None:
        self._duration = max(0.001, float(total_sec))
        self.update()

    def set_playhead(self, t_sec: float) -> None:
        self._playhead = max(0.0, min(self._duration, float(t_sec)))
        if not self._dragging:
            self.update()

    def _track_y(self, track: str) -> tuple[int, int]:
        y = _AXIS_HEIGHT
        for t in _TRACK_ORDER:
            h = _TRACK_HEIGHTS[t]
            if t == track:
                return y, h
            y += h + _ROW_GAP
        return -1, 0

    def _t_to_x(self, t: float) -> int:
        track_w = max(1, self.width() - _LABEL_WIDTH)
        return _LABEL_WIDTH + int(track_w * (t / self._duration))

    def _x_to_t(self, x: int) -> float:
        track_w = max(1, self.width() - _LABEL_WIDTH)
        return max(0.0, min(self._duration,
                             (x - _LABEL_WIDTH) / track_w * self._duration))

    def _cue_at(self, x: int, y: int) -> Optional[_Cue]:
        for c in self._cues:
            ty, th = self._track_y(c.track)
            if y < ty or y >= ty + th:
                continue
            cx_a = self._t_to_x(c.t_start)
            cx_b = self._t_to_x(c.t_end)
            if cx_a <= x <= cx_b:
                return c
        return None

    def paintEvent(self, _event):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), _BG_FRAME_COLOR)
            self._paint_axis(p)
            for track in _TRACK_ORDER:
                ty, th = self._track_y(track)
                p.fillRect(_LABEL_WIDTH, ty, self.width() - _LABEL_WIDTH,
                           th, _BG_TRACK_COLOR)
                self._paint_label(p, track, ty, th)
            font = QFont(); font.setPointSize(8); p.setFont(font)
            fm = QFontMetrics(font)
            for c in self._cues:
                ty, th = self._track_y(c.track)
                x_a = self._t_to_x(c.t_start)
                x_b = self._t_to_x(c.t_end)
                color = _TRACK_COLORS[c.track]
                rect = QRect(x_a, ty, max(2, x_b - x_a), th)
                p.fillRect(rect, color)
                if c.track == "video":
                    p.setPen(QColor("#000000"))
                    p.drawLine(x_b, ty, x_b, ty + th)
                if c.label and rect.width() >= 30:
                    p.setPen(_TEXT_COLOR)
                    elide_w = rect.width() - 6
                    text = fm.elidedText(c.label, Qt.ElideRight, elide_w)
                    p.drawText(rect.adjusted(3, 0, -3, 0),
                               Qt.AlignVCenter | Qt.AlignLeft, text)
            px = self._t_to_x(self._playhead)
            p.setPen(_PLAYHEAD_COLOR)
            p.drawLine(px, 0, px, self.height())
        finally:
            p.end()

    def _paint_axis(self, p: QPainter):
        p.fillRect(0, 0, self.width(), _AXIS_HEIGHT, _BG_FRAME_COLOR)
        p.setPen(_AXIS_COLOR)
        p.drawLine(_LABEL_WIDTH, _AXIS_HEIGHT - 1,
                   self.width(), _AXIS_HEIGHT - 1)
        font = QFont(); font.setPointSize(7); p.setFont(font)
        p.setPen(_LABEL_COLOR)
        for i in range(5):
            t = self._duration * i / 4
            x = self._t_to_x(t)
            mins = int(t // 60); secs = int(t % 60)
            p.drawText(x + 2, _AXIS_HEIGHT - 3, f"{mins}:{secs:02d}")
            if 0 < i < 4:
                p.setPen(_AXIS_COLOR)
                p.drawLine(x, 0, x, _AXIS_HEIGHT - 1)
                p.setPen(_LABEL_COLOR)

    def _paint_label(self, p: QPainter, track: str, ty: int, th: int):
        p.setPen(_LABEL_COLOR)
        font = QFont(); font.setPointSize(8); p.setFont(font)
        text = {"video": "视频", "bgm": "BGM",
                "sfx": "SFX", "dialogue": "对白"}[track]
        p.drawText(QRect(0, ty, _LABEL_WIDTH - 4, th),
                   Qt.AlignVCenter | Qt.AlignRight, text)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        x, y = event.pos().x(), event.pos().y()
        cue = self._cue_at(x, y)
        if cue is not None and cue.track != "video":
            self.cueClicked.emit(cue.track, cue.seg_index, cue.t_start)
            return
        if x >= _LABEL_WIDTH:
            self._dragging = True
            self._emit_drag(self._x_to_t(x))

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        x = event.pos().x()
        if x >= _LABEL_WIDTH:
            self._emit_drag(self._x_to_t(x))

    def mouseReleaseEvent(self, _event):
        if self._dragging:
            self._dragging = False
            self._flush_drag()

    def _emit_drag(self, t: float):
        self._pending_drag_t = t
        self._playhead = t
        self.update()
        if not self._drag_timer.isActive():
            self._drag_timer.start()

    def _flush_drag(self):
        if self._pending_drag_t is None:
            return
        self.playheadDragged.emit(self._pending_drag_t)
        self._pending_drag_t = None
