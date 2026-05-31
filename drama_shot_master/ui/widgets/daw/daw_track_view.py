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
from drama_shot_master.ui.widgets.daw.overlay_layout import (
    overlay_rows, _OV_HEAD_H, _OV_LANE_H,
)

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
# 固定区高度（4 固定轨）。叠加区高度按 overlay_rows 动态追加。
_FIXED_H = _AXIS_H + sum(_TRACK_H[t] + _GAP for t in _TRACK_ORDER) + 20
_MIN_H = _FIXED_H  # 向后兼容别名

# 叠加区斜纹区分色（bgm/sfx），与固定轨纯色区分
_OV_SEG_COLORS = {
    "bgm": QColor("#5a9e6f"),
    "sfx": QColor("#e8a838"),
}
_OV_LANE_BG = QColor("#202024")

# 供 TrackHeaderColumn 等外部对齐使用的公开常量别名
TRACK_ORDER = _TRACK_ORDER
TRACK_H = _TRACK_H
AXIS_H = _AXIS_H
LABEL_W = _LABEL_W


class DawTrackView(QWidget):
    cueClicked = Signal(object, object)          # _CueRef, KeyboardModifier flags
    cueDoubleClicked = Signal(object)           # _CueRef
    dragCommandIssued = Signal(object)          # Command
    rubberBandReleased = Signal(object, object) # QRect, KeyboardModifier flags
    contextMenuRequested = Signal(object, object)   # _CueRef, QPoint
    playheadDragged = Signal(float)             # time_sec
    playheadDropped = Signal(float)             # time_sec
    overlayCollapseToggled = Signal()           # 折叠头点击
    overlaySegmentClicked = Signal(str, object) # seg_id, KeyboardModifier flags

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

        # 动态叠加区状态
        self._overlay_segs: list = []
        self._overlay_collapsed: bool = False
        self._overlay_sel_id: Optional[str] = None

        self.setMinimumHeight(_FIXED_H)
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

    def set_overlay(self, segments, *, collapsed: bool = False) -> None:
        """存 overlay 片段 + 折叠态，按 overlay_rows 重算动态高度并重绘。"""
        self._overlay_segs = list(segments)
        self._overlay_collapsed = collapsed
        _, region_h = overlay_rows(
            self._overlay_segs, base_y=0, collapsed=collapsed
        )
        self.setMinimumHeight(_FIXED_H + region_h)
        self.update()

    def set_overlay_selection(self, seg_id: Optional[str]) -> None:
        """设置当前选中的 overlay 片段（用于描边高亮）。"""
        self._overlay_sel_id = seg_id
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

    # ── overlay helpers ──────────────────────────────────────────────

    def _overlay_rows(self):
        """当前 overlay 行布局（base_y=_FIXED_H）。"""
        return overlay_rows(
            self._overlay_segs, base_y=_FIXED_H,
            collapsed=self._overlay_collapsed,
        )

    def _overlay_head_rect(self):
        """折叠头矩形；overlay 为空 → None。"""
        if not self._overlay_segs:
            return None
        return QRect(0, _FIXED_H, self.width(), _OV_HEAD_H)

    def _overlay_seg_at(self, x: int, y: int):
        """纯逻辑：命中叠加区某片段返回其 id，否则 None（折叠头/空白）。"""
        rows, _ = self._overlay_rows()
        for row in rows:
            if not (row.y <= y < row.y + _OV_LANE_H):
                continue
            for seg in row.segments:
                x0 = self._t_to_x(seg.t_start)
                x1 = self._t_to_x(seg.t_end)
                if x0 <= x <= max(x1, x0 + 2):
                    return seg.id
            return None
        return None

    # ── mouse events ─────────────────────────────────────────────────

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        x, y = ev.pos().x(), ev.pos().y()
        mod = ev.modifiers()

        # 叠加区命中（y ≥ 固定区底）：折叠头 / 片段 / 空白
        if self._overlay_segs and y >= _FIXED_H:
            head = self._overlay_head_rect()
            if head is not None and head.contains(x, y):
                self.overlayCollapseToggled.emit()
                return
            seg_id = self._overlay_seg_at(x, y)
            if seg_id is not None:
                self.overlaySegmentClicked.emit(seg_id, mod)
                return
            # 空白叠加区 → 吞掉（不拖 playhead）
            return

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

    def _paint_overlay(self, painter: QPainter, w: int) -> None:
        """画动态叠加区：折叠头（▼/▶ + '动态叠加区(N)'）+ 展开时 lane 行 + 片段块。"""
        if not self._overlay_segs:
            return

        from drama_shot_master.ui.widgets.daw.overlay_layout import lane_count

        # 折叠头
        head_y = _FIXED_H
        painter.fillRect(0, head_y, w, _OV_HEAD_H, QColor("#2a2a2e"))
        arrow = "▶" if self._overlay_collapsed else "▼"
        n = lane_count(self._overlay_segs)
        painter.setPen(QColor("#cccccc"))
        painter.drawText(6, head_y, w - 12, _OV_HEAD_H,
                         Qt.AlignVCenter | Qt.AlignLeft,
                         f"{arrow} 动态叠加区({n})")

        if self._overlay_collapsed:
            return

        rows, _ = self._overlay_rows()
        for row in rows:
            # lane 背景行
            painter.fillRect(_LABEL_W, row.y, w - _LABEL_W, _OV_LANE_H,
                             _OV_LANE_BG)
            painter.setPen(QColor("#888888"))
            painter.drawText(4, row.y, _LABEL_W - 8, _OV_LANE_H,
                             Qt.AlignVCenter | Qt.AlignLeft,
                             f"{row.kind}·{row.lane}")
            # 片段块（斜纹区分 bgm/sfx；选中描边）
            color = _OV_SEG_COLORS.get(row.kind, QColor("#5577aa"))
            for seg in row.segments:
                x0 = int(self._t_to_x(seg.t_start))
                x1 = int(self._t_to_x(seg.t_end))
                cw = max(x1 - x0, 2)
                rect = QRect(x0, row.y + 2, cw, _OV_LANE_H - 4)
                painter.fillRect(rect, QBrush(color, Qt.BDiagPattern))
                if seg.id == self._overlay_sel_id:
                    painter.setPen(QPen(QColor("#ffffff"), 2))
                    painter.drawRect(rect)

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

        # 动态叠加区
        self._paint_overlay(painter, w)

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
