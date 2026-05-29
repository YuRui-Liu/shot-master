"""自绘 DAW 多轨时间轴 QWidget。"""
from __future__ import annotations
from typing import List, Optional
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush,
                            QMouseEvent, QFontMetrics)
from PySide6.QtWidgets import QWidget, QSizePolicy

from drama_shot_master.ui.widgets.overview_timeline_model import _Cue
from drama_shot_master.ui.widgets.daw.selection import Selection, _CueRef
from drama_shot_master.ui.widgets.daw.commands import MoveCue, ResizeCue

_LABEL_W = 60
_AXIS_H = 14
_TRACK_H = {"video": 36, "bgm": 40, "sfx": 36, "dialogue": 36}
_GAP = 2
_TRACK_ORDER = ["video", "bgm", "sfx", "dialogue"]
_TRACK_COLORS = {
    "video":    QColor("#3a7bd5"),
    "bgm":      QColor("#5a9e6f"),
    "sfx":      QColor("#e8a838"),
    "dialogue": QColor("#9b59b6"),
}


def _build_track_y() -> dict:
    y = _AXIS_H
    out: dict = {}
    for t in _TRACK_ORDER:
        out[t] = y
        y += _TRACK_H[t] + _GAP
    return out


_TRACK_Y = _build_track_y()
_MIN_H = _AXIS_H + sum(_TRACK_H[t] + _GAP for t in _TRACK_ORDER) + 20


class DawTrackView(QWidget):
    cueClicked = Signal(object, object)          # _CueRef, KeyboardModifier flags
    cueDoubleClicked = Signal(object)           # _CueRef
    dragCommandIssued = Signal(object)          # Command
    rubberBandReleased = Signal(object, object) # QRect, KeyboardModifier flags
    contextMenuRequested = Signal(object, object)   # _CueRef, QPoint
    playheadDragged = Signal(float)             # time_sec
    playheadDropped = Signal(float)             # time_sec

    _RESIZE_HOTSPOT_PX = 4

    def __init__(self, selection: Selection, parent=None):
        super().__init__(parent)
        self._selection = selection
        self._selection.changed.connect(self.update)

        self._cues: List[_Cue] = []
        self._duration: float = 60.0
        self._zoom: float = 1.0
        self._scroll_offset: float = 0.0   # fraction of duration shown before left edge
        self._playhead_t: float = 0.0

        self._mode: Optional[str] = None
        self._drag_cue: Optional[_Cue] = None
        self._press_x: int = 0
        self._drag_orig_t_start: float = 0.0
        self._drag_orig_t_end: float = 0.0
        self._rubber_band_start: QPoint = QPoint()
        self._rubber_band_rect: QRect = QRect()

        self.setMinimumHeight(_MIN_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMouseTracking(True)

    # ── public API ────────────────────────────────────────────────────

    def set_cues(self, cues: List[_Cue]) -> None:
        self._cues = list(cues)
        self.update()

    def set_duration(self, duration: float) -> None:
        self._duration = max(duration, 0.01)
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(zoom, 0.1)
        self.update()

    def set_scroll_offset(self, offset: float) -> None:
        self._scroll_offset = max(0.0, min(offset, 1.0))
        self.update()

    def set_playhead(self, t: float) -> None:
        self._playhead_t = t
        self.update()

    # ── coordinate helpers ────────────────────────────────────────────

    def _canvas_w(self) -> int:
        return max(self.width() - _LABEL_W, 1)

    def _t_to_x(self, t: float) -> float:
        cw = self._canvas_w()
        return _LABEL_W + (t / self._duration - self._scroll_offset) * self._zoom * cw

    def _x_to_t(self, x: int) -> float:
        cw = self._canvas_w()
        return (x - _LABEL_W) / (self._zoom * cw) * self._duration + self._scroll_offset * self._duration

    def _cue_x_end(self, cue: _Cue) -> float:
        return self._t_to_x(cue.t_end)

    def _cue_at(self, x: int, y: int) -> Optional[_Cue]:
        hot = self._RESIZE_HOTSPOT_PX
        for cue in self._cues:
            ty = _TRACK_Y.get(cue.track)
            if ty is None:
                continue
            if not (ty <= y < ty + _TRACK_H[cue.track]):
                continue
            x0 = self._t_to_x(cue.t_start)
            x1 = self._cue_x_end(cue)
            if x0 - hot <= x <= x1 + hot:
                return cue
        return None

    # ── mouse events ─────────────────────────────────────────────────

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        x, y = ev.pos().x(), ev.pos().y()
        mod = ev.modifiers()
        cue = self._cue_at(x, y)

        if cue is not None and cue.track != "video":
            x0 = self._t_to_x(cue.t_start)
            x1 = self._cue_x_end(cue)
            hot = self._RESIZE_HOTSPOT_PX

            if abs(x - x0) <= hot:
                self._mode = "resize_start"
                self._drag_cue = cue
                self._press_x = x
                self._drag_orig_t_start = cue.t_start
                self._drag_orig_t_end = cue.t_end
                return

            if abs(x - x1) <= hot:
                self._mode = "resize_end"
                self._drag_cue = cue
                self._press_x = x
                self._drag_orig_t_start = cue.t_start
                self._drag_orig_t_end = cue.t_end
                return

            # cue body → click + start drag
            self.cueClicked.emit(_CueRef(cue.track, cue.seg_index), mod)
            self._mode = "drag_cue"
            self._drag_cue = cue
            self._press_x = x
            self._drag_orig_t_start = cue.t_start
            self._drag_orig_t_end = cue.t_end
            return

        # empty area or video track
        if ev.modifiers() & Qt.ShiftModifier:
            self._mode = "rubber_band"
            self._rubber_band_start = QPoint(x, y)
            self._rubber_band_rect = QRect()
        else:
            self._mode = "playhead"
            self.playheadDragged.emit(self._x_to_t(x))

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        x, y = ev.pos().x(), ev.pos().y()

        if self._mode == "drag_cue" and self._drag_cue is not None:
            dt = self._x_to_t(x) - self._x_to_t(self._press_x)
            self._drag_cue.t_start = self._drag_orig_t_start + dt
            self._drag_cue.t_end = self._drag_orig_t_end + dt
            self.update()

        elif self._mode == "resize_start" and self._drag_cue is not None:
            dt = self._x_to_t(x) - self._x_to_t(self._press_x)
            new_t = self._drag_orig_t_start + dt
            if new_t < self._drag_cue.t_end - 0.1:
                self._drag_cue.t_start = new_t
            self.update()

        elif self._mode == "resize_end" and self._drag_cue is not None:
            dt = self._x_to_t(x) - self._x_to_t(self._press_x)
            new_t = self._drag_orig_t_end + dt
            if new_t > self._drag_cue.t_start + 0.1:
                self._drag_cue.t_end = new_t
            self.update()

        elif self._mode == "rubber_band":
            self._rubber_band_rect = QRect(
                self._rubber_band_start, QPoint(x, y)
            ).normalized()
            self.update()

        elif self._mode == "playhead":
            self.playheadDragged.emit(self._x_to_t(x))

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        x = ev.pos().x()
        mod = ev.modifiers()

        if self._mode == "drag_cue" and self._drag_cue is not None:
            dt = self._x_to_t(x) - self._x_to_t(self._press_x)
            if abs(dt) > 1e-6:
                ref = _CueRef(self._drag_cue.track, self._drag_cue.seg_index)
                self.dragCommandIssued.emit(
                    MoveCue(bgm_session=None, sfx_session=None,
                            refs=[ref], dt_sec=dt)
                )

        elif self._mode == "resize_start" and self._drag_cue is not None:
            dt = self._x_to_t(x) - self._x_to_t(self._press_x)
            if abs(dt) > 1e-6:
                ref = _CueRef(self._drag_cue.track, self._drag_cue.seg_index)
                self.dragCommandIssued.emit(
                    ResizeCue(bgm_session=None, sfx_session=None,
                              ref=ref, side="start", dt_sec=dt)
                )

        elif self._mode == "resize_end" and self._drag_cue is not None:
            dt = self._x_to_t(x) - self._x_to_t(self._press_x)
            if abs(dt) > 1e-6:
                ref = _CueRef(self._drag_cue.track, self._drag_cue.seg_index)
                self.dragCommandIssued.emit(
                    ResizeCue(bgm_session=None, sfx_session=None,
                              ref=ref, side="end", dt_sec=dt)
                )

        elif self._mode == "rubber_band":
            self.rubberBandReleased.emit(self._rubber_band_rect, mod)
            self._rubber_band_rect = QRect()

        elif self._mode == "playhead":
            self.playheadDropped.emit(self._x_to_t(x))

        self._mode = None
        self._drag_cue = None
        self.update()

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        pos = ev.pos()
        cue = self._cue_at(pos.x(), pos.y())
        if cue is not None and cue.track != "video":
            self.cueDoubleClicked.emit(_CueRef(cue.track, cue.seg_index))

    # ── paint ─────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#1e1e1e"))

        # track lanes + labels
        selected = {(r.track, r.seg_index) for r in self._selection.get()}

        for track in _TRACK_ORDER:
            ty = _TRACK_Y[track]
            th = _TRACK_H[track]
            painter.fillRect(_LABEL_W, ty, w - _LABEL_W, th, QColor("#252525"))
            painter.setPen(QColor("#666666"))
            painter.drawText(2, ty, _LABEL_W - 4, th,
                             Qt.AlignVCenter | Qt.AlignLeft, track)

        # cue blocks
        for cue in self._cues:
            ty = _TRACK_Y.get(cue.track)
            if ty is None:
                continue
            th = _TRACK_H[cue.track]
            x0 = int(self._t_to_x(cue.t_start))
            x1 = int(self._cue_x_end(cue))
            cw = max(x1 - x0, 2)
            color = _TRACK_COLORS.get(cue.track, QColor("#5577aa"))
            if (cue.track, cue.seg_index) in selected:
                color = color.lighter(140)
            painter.fillRect(x0, ty + 2, cw, th - 4, color)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(x0 + 4, ty + 2, max(cw - 8, 0), th - 4,
                             Qt.AlignVCenter | Qt.AlignLeft, cue.label)

        # rubber band overlay
        if self._mode == "rubber_band" and not self._rubber_band_rect.isEmpty():
            pen = QPen(QColor("#5599ff"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(85, 153, 255, 40)))
            painter.drawRect(self._rubber_band_rect)

        # playhead
        ph_x = int(self._t_to_x(self._playhead_t))
        if _LABEL_W <= ph_x < w:
            painter.setPen(QPen(QColor("#ff4444"), 1))
            painter.drawLine(ph_x, 0, ph_x, h)

        painter.end()
