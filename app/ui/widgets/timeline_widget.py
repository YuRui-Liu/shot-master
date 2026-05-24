"""TimelineWidget：DAW 比例条样式的时间轴（QGraphicsScene 自绘）。

外部信号契约：所有 model 修改都由信号触发，外部 panel 负责写回 model + 调 rebuild()。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QRectF, QSize, QPointF, QMimeData
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QPixmapCache, QDrag, QFont,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsScene, QGraphicsView, QGraphicsTextItem,
)

from app.core.video_timeline_model import (
    TimelineModel, TimelineSegment, TimelineAudio,
)


# ---------- 布局常量 ----------

SEG_LANE_Y = 0
SEG_HEIGHT = 60
LANE_GAP = 10
AUDIO_LANE_Y = SEG_HEIGHT + LANE_GAP   # 70
AUDIO_HEIGHT = 30
RESIZE_HANDLE_W = 6
DEFAULT_PX_PER_FRAME = 5.0
MIN_PX_PER_FRAME = 0.5
MAX_PX_PER_FRAME = 50.0

# MIME types
MIME_IMG_PATH = "application/x-spb-image-path"


# ---------- 缩略图缓存 ----------

def _cached_thumb(path: Path, w: int = 40, h: int = 30) -> QPixmap:
    key = f"spb_seg_thumb::{path}"
    pix = QPixmapCache.find(key)
    if pix:
        return pix
    pix = QPixmap(str(path))
    if pix.isNull():
        pix = QPixmap(w, h); pix.fill(QColor("#444"))
    else:
        pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    QPixmapCache.insert(key, pix)
    return pix


# ---------- Segment Item ----------

class SegmentItem(QGraphicsItem):
    """主轨段卡：宽度 ∝ length_frames。仅渲染；不改 model。"""

    def __init__(self, seg: TimelineSegment, x: float, width: float,
                 display_mode: str, frame_rate: int):
        super().__init__()
        self.seg = seg
        self._width = max(width, 8.0)
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self.setPos(x, SEG_LANE_Y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        # 交互状态
        self._press_x: Optional[float] = None
        self._press_mode: str = "none"     # "resize" | "move" | "none"
        self._resize_start_w: float = 0.0

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, SEG_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        # 1. 背景
        bg = (QColor("#3a4a5f") if self.seg.segment_type == "image"
              else QColor("#4a3a3a"))
        painter.fillRect(rect, bg)
        # 2. 边框（选中时高亮）
        if self.isSelected():
            painter.setPen(QPen(QColor("#ffaa00"), 2))
        else:
            painter.setPen(QPen(QColor("#5577aa")
                                 if self.seg.segment_type == "image"
                                 else QColor("#aa6677"), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        # 3. 缩略图（仅 image 段）
        thumb_w = 40
        if self.seg.image_path:
            thumb = _cached_thumb(self.seg.image_path, thumb_w, 30)
            painter.drawPixmap(QRectF(4, 4, thumb_w, 30), thumb, thumb.rect())
        # 4. length badge
        if self._display_mode == "frames":
            badge = f"{self.seg.length_frames}f"
        else:
            sec = self.seg.length_frames / max(self._frame_rate, 1)
            badge = f"{sec:.2f}s"
        painter.setPen(QColor("#ffcc66"))
        f = QFont(); f.setPointSize(8); painter.setFont(f)
        painter.drawText(
            QRectF(4, SEG_HEIGHT - 16, self._width - 8, 12),
            Qt.AlignLeft, badge)
        # 5. prompt 前缀
        if self.seg.local_prompt:
            painter.setPen(QColor("#dddddd"))
            preview = self.seg.local_prompt[:18]
            text_x = thumb_w + 8 if self.seg.image_path else 4
            painter.drawText(
                QRectF(text_x, 4, max(self._width - text_x - 4, 0), SEG_HEIGHT - 20),
                Qt.AlignLeft | Qt.TextWordWrap, preview)

    def hoverMoveEvent(self, event):
        local_x = event.pos().x()
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        local_x = event.pos().x()
        self._press_x = local_x
        self._resize_start_w = self._width
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self._press_mode = "resize"
        else:
            self._press_mode = "move"
        self.setSelected(True)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            event.accept()
            return
        if self._press_mode == "move":
            # 启动 QDrag 一旦移动超过 8px
            if abs(event.pos().x() - self._press_x) > 8:
                self._start_drag()
                self._press_mode = "none"   # drag 启动后状态机重置
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press_mode == "resize":
            view = self._top_view()
            ppf = view.pixels_per_frame if view else 5.0
            new_len = max(1, int(round(self._width / ppf)))
            if view is not None:
                view.segmentChanged.emit(self.seg.seg_id, new_len)
            self._press_mode = "none"
            event.accept()
            return
        if self._press_mode == "move":
            # 原位释放 = 仅选中
            view = self._top_view()
            if view is not None:
                view.segmentSelected.emit(self.seg.seg_id)
            self._press_mode = "none"
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        view = self._top_view()
        if view is not None:
            view.segmentDoubleClicked.emit(self.seg.seg_id)
        event.accept()

    def _start_drag(self):
        view = self._top_view()
        if view is None:
            return
        mime = QMimeData()
        mime.setData("application/x-spb-seg-id",
                     self.seg.seg_id.encode("utf-8"))
        drag = QDrag(view)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def _top_view(self) -> Optional["TimelineWidget"]:
        scene = self.scene()
        if scene is None:
            return None
        views = scene.views()
        return views[0] if views else None


# ---------- Audio Item ----------

class AudioItem(QGraphicsItem):
    """音频段卡：整体拖动改 start_frame；右沿拖动改 length。"""

    def __init__(self, audio: TimelineAudio, x: float, width: float,
                 display_mode: str, frame_rate: int):
        super().__init__()
        self.audio = audio
        self._width = max(width, 8.0)
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self.setPos(x, AUDIO_LANE_Y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._press_x: Optional[float] = None
        self._press_mode: str = "none"
        self._resize_start_w: float = 0.0
        self._move_start_pos: Optional[QPointF] = None

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, AUDIO_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        painter.fillRect(rect, QColor("#3a4a3a"))
        if self.isSelected():
            painter.setPen(QPen(QColor("#ffaa00"), 2))
        else:
            painter.setPen(QPen(QColor("#66aa77"), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QColor("#ddffdd"))
        f = QFont(); f.setPointSize(8); painter.setFont(f)
        if self._display_mode == "frames":
            badge = f"♪ {self.audio.length_frames}f @{self.audio.start_frame}f"
        else:
            sec_len = self.audio.length_frames / max(self._frame_rate, 1)
            sec_start = self.audio.start_frame / max(self._frame_rate, 1)
            badge = f"♪ {sec_len:.2f}s @{sec_start:.2f}s"
        painter.drawText(rect.adjusted(4, 0, -4, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, badge)

    def hoverMoveEvent(self, event):
        local_x = event.pos().x()
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        local_x = event.pos().x()
        self._press_x = local_x
        self._resize_start_w = self._width
        self._move_start_pos = QPointF(self.pos())
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self._press_mode = "resize"
        else:
            self._press_mode = "move"
        self.setSelected(True)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            event.accept()
            return
        if self._press_mode == "move":
            scene_dx = event.scenePos().x() - (
                self._move_start_pos.x() + self._press_x)
            new_x = max(0, self._move_start_pos.x() + scene_dx)
            self.setPos(new_x, AUDIO_LANE_Y)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        view = self._top_view()
        if view is None:
            return super().mouseReleaseEvent(event)
        ppf = view.pixels_per_frame
        if self._press_mode == "resize":
            new_len = max(1, int(round(self._width / ppf)))
            view.audioChanged.emit(self.audio.audio_id,
                                    self.audio.start_frame, new_len)
            self._press_mode = "none"
            event.accept()
            return
        if self._press_mode == "move":
            new_start = max(0, int(round(self.pos().x() / ppf)))
            view.audioChanged.emit(self.audio.audio_id,
                                    new_start, self.audio.length_frames)
            self._press_mode = "none"
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _top_view(self) -> Optional["TimelineWidget"]:
        scene = self.scene()
        if scene is None:
            return None
        views = scene.views()
        return views[0] if views else None


# ---------- Scene ----------

class TimelineScene(QGraphicsScene):
    """场景管理：从 model 重建 items。"""

    def __init__(self, model: TimelineModel, pixels_per_frame: float, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_frame = pixels_per_frame

    def rebuild(self):
        self.clear()
        x = 0.0
        for seg in self.model.segments:
            w = seg.length_frames * self.pixels_per_frame
            item = SegmentItem(seg, x, w,
                                self.model.display_mode, self.model.frame_rate)
            self.addItem(item)
            x += w
        for audio in self.model.audios:
            ax = audio.start_frame * self.pixels_per_frame
            aw = audio.length_frames * self.pixels_per_frame
            self.addItem(
                AudioItem(audio, ax, aw,
                          self.model.display_mode, self.model.frame_rate))
        total_w = max(x, 200) + 100
        self.setSceneRect(0, 0, total_w, AUDIO_LANE_Y + AUDIO_HEIGHT + 20)
        if not self.model.segments and not self.model.audios:
            hint = QGraphicsTextItem("拖一张图到这里开始")
            hint.setDefaultTextColor(QColor("#666"))
            hint.setPos(20, SEG_HEIGHT / 2 - 10)
            self.addItem(hint)

    def dragEnterEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        view = self.views()[0] if self.views() else None
        if view is None:
            return super().dropEvent(e)
        drop_x = e.scenePos().x()
        insert_idx = self._find_seg_insert_index(drop_x)
        if e.mimeData().hasFormat("application/x-spb-seg-id"):
            seg_id = e.mimeData().data(
                "application/x-spb-seg-id").data().decode("utf-8")
            ids = [s.seg_id for s in self.model.segments]
            if seg_id in ids:
                ids.remove(seg_id)
                ids.insert(min(insert_idx, len(ids)), seg_id)
                view.segmentReordered.emit(ids)
            e.acceptProposedAction()
            return
        if e.mimeData().hasFormat(MIME_IMG_PATH):
            raw = e.mimeData().data(MIME_IMG_PATH).data().decode("utf-8")
            path = Path(raw)
            view.imageDroppedAt.emit(path, insert_idx)
            e.acceptProposedAction()
            return
        super().dropEvent(e)

    def _find_seg_insert_index(self, drop_x: float) -> int:
        x = 0.0
        for i, s in enumerate(self.model.segments):
            w = s.length_frames * self.pixels_per_frame
            if drop_x < x + w / 2:
                return i
            x += w
        return len(self.model.segments)


# ---------- View ----------

class TimelineWidget(QGraphicsView):
    """DAW 时间轴 widget。Ctrl+wheel 等比缩放，纯 wheel 横向滚。"""

    # Task 8 / 9 会启用更多信号；本任务先定义全部契约（emit 调用方占位）
    segmentSelected = Signal(str)
    segmentChanged = Signal(str, int)           # (seg_id, new_length_frames)
    segmentReordered = Signal(list)             # [seg_id, ...]
    segmentDoubleClicked = Signal(str)
    segmentDeleteRequested = Signal(str)
    audioChanged = Signal(str, int, int)        # (audio_id, new_start, new_length)
    audioDeleteRequested = Signal(str)
    imageDroppedAt = Signal(object, int)        # (Path, insert_index)
    zoomChanged = Signal(float)

    def __init__(self, model: TimelineModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_frame = DEFAULT_PX_PER_FRAME
        self._scene = TimelineScene(model, self.pixels_per_frame)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setAcceptDrops(True)
        self.rebuild()

    def rebuild(self):
        selected_id = self._current_selected_seg_id() if hasattr(self, "_scene") else ""
        self._scene.pixels_per_frame = self.pixels_per_frame
        self._scene.rebuild()
        if selected_id:
            for item in self._scene.items():
                if isinstance(item, SegmentItem) and item.seg.seg_id == selected_id:
                    item.setSelected(True)
                    break

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            items = self._scene.selectedItems()
            for item in items:
                if isinstance(item, SegmentItem):
                    self.segmentDeleteRequested.emit(item.seg.seg_id)
                    return
                if isinstance(item, AudioItem):
                    self.audioDeleteRequested.emit(item.audio.audio_id)
                    return
        super().keyPressEvent(e)

    def _current_selected_seg_id(self) -> str:
        for item in self._scene.selectedItems():
            if isinstance(item, SegmentItem):
                return item.seg.seg_id
        return ""

    def currently_selected_seg_id(self) -> str:
        """公共 API 给 VideoPanel 调（display_mode 切换时获取当前段）。"""
        return self._current_selected_seg_id()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
            new_ppf = self.pixels_per_frame * factor
            self.pixels_per_frame = max(MIN_PX_PER_FRAME,
                                         min(MAX_PX_PER_FRAME, new_ppf))
            self.rebuild()
            self.zoomChanged.emit(self.pixels_per_frame)
        else:
            super().wheelEvent(e)
