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

from drama_shot_master.core.video_timeline_model import (
    TimelineModel, TimelineSegment, TimelineAudio,
)


# ---------- 布局常量 ----------

RULER_HEIGHT = 20
SEG_LANE_Y = RULER_HEIGHT
SEG_HEIGHT = 60
LANE_GAP = 10
AUDIO_LANE_Y = SEG_LANE_Y + SEG_HEIGHT + LANE_GAP   # 20 + 60 + 10 = 90
AUDIO_HEIGHT = 30
RESIZE_HANDLE_W = 6
DEFAULT_PX_PER_FRAME = 5.0
MIN_PX_PER_FRAME = 0.5
MAX_PX_PER_FRAME = 50.0

# ---------- 刻度尺常量 ----------

TARGET_MAJOR_PX = 80              # 相邻 major tick 目标间距（像素）
MINOR_RATIO = 5                   # minor = max(1, major // 5)
SECONDS_CANDIDATES = [0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]  # 秒
FRAMES_CANDIDATES = [1, 5, 10, 30, 60, 120, 300, 600]            # 帧

# ---------- 刻度尺 / 游标配色 ----------

SCENE_BG = "#1e1f22"              # 时间轴画布背景（与主题窗口底一致）
RULER_BAND_COLOR = "#2b2f3a"      # 背景带（略亮于场景背景）
TICK_MINOR_COLOR = "#7a8597"      # minor tick（中灰）
TICK_MAJOR_COLOR = "#d4dae6"      # major tick（近白）
TICK_LABEL_COLOR = "#e6ebf2"      # 标签文字（近白）
CURSOR_LINE_COLOR = "#ff4d4d"     # 红色游标线
CURSOR_LABEL_BG = "#ff4d4d"       # 游标标签底（红）
CURSOR_LABEL_FG = "#ffffff"       # 游标标签字（白）


def _pick_tick_interval(ppf: float, frame_rate: int, display_mode: str
                        ) -> tuple[int, int]:
    """选 (major_frames, minor_frames) 使相邻 major tick 间距 >= TARGET_MAJOR_PX。

    遍历候选间隔（升序），返回首个满足像素阈值的；都不满足则取最大候选。
    minor_frames = max(1, major_frames // MINOR_RATIO)。
    """
    fr = max(frame_rate, 1)
    if display_mode == "seconds":
        for sec in SECONDS_CANDIDATES:
            major_frames = max(1, int(round(sec * fr)))
            if major_frames * ppf >= TARGET_MAJOR_PX:
                return (major_frames, max(1, major_frames // MINOR_RATIO))
        last = max(1, int(round(SECONDS_CANDIDATES[-1] * fr)))
        return (last, max(1, last // MINOR_RATIO))
    # frames
    for f in FRAMES_CANDIDATES:
        if f * ppf >= TARGET_MAJOR_PX:
            return (f, max(1, f // MINOR_RATIO))
    last = FRAMES_CANDIDATES[-1]
    return (last, max(1, last // MINOR_RATIO))


def _format_cursor_label(x: float, ppf: float, frame_rate: int,
                         display_mode: str) -> str:
    """游标 scene-x → 当前帧/秒的显示文本。"""
    if ppf <= 0:
        frame = 0
    else:
        frame = max(0, int(round(x / ppf)))
    if display_mode == "frames":
        return f"{frame}f"
    sec = frame / max(frame_rate, 1)
    return f"{sec:.2f}s"


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
            self._set_scene_cursor(self.pos().x() + new_w)
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
            seg_id = self.seg.seg_id
            # 先做完所有碰 self 的事，emit 放最后：handler 会重建时间轴并
            # 删除本 C++ item，发射后再访问 self 会触发 already-deleted 崩溃。
            self._set_scene_cursor(None)
            self._press_mode = "none"
            event.accept()
            if view is not None:
                view.segmentChanged.emit(seg_id, new_len)
            return
        if self._press_mode == "move":
            # 原位释放 = 仅选中
            view = self._top_view()
            seg_id = self.seg.seg_id
            self._set_scene_cursor(None)
            self._press_mode = "none"
            event.accept()
            if view is not None:
                view.segmentSelected.emit(seg_id)
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

    def _set_scene_cursor(self, x: Optional[float]) -> None:
        scene = self.scene()
        if isinstance(scene, TimelineScene):
            scene.set_cursor_x(x)


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
            self._set_scene_cursor(self.pos().x() + new_w)
            event.accept()
            return
        if self._press_mode == "move":
            scene_dx = event.scenePos().x() - (
                self._move_start_pos.x() + self._press_x)
            new_x = max(0, self._move_start_pos.x() + scene_dx)
            self.setPos(new_x, AUDIO_LANE_Y)
            self._set_scene_cursor(new_x)
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
            self._set_scene_cursor(None)
            self._press_mode = "none"
            event.accept()
            return
        if self._press_mode == "move":
            new_start = max(0, int(round(self.pos().x() / ppf)))
            view.audioChanged.emit(self.audio.audio_id,
                                    new_start, self.audio.length_frames)
            self._set_scene_cursor(None)
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

    def _set_scene_cursor(self, x: Optional[float]) -> None:
        scene = self.scene()
        if isinstance(scene, TimelineScene):
            scene.set_cursor_x(x)


# ---------- Scene ----------

class TimelineScene(QGraphicsScene):
    """场景管理：从 model 重建 items。"""

    def __init__(self, model: TimelineModel, pixels_per_frame: float, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_frame = pixels_per_frame
        self._cursor_x: Optional[float] = None
        # 背景刷设在 scene（不是 view）：view 设 brush 会短路 scene.drawBackground，
        # 导致刻度尺整段不绘制。scene.drawBackground 先 super() 填此底色再画刻度。
        self.setBackgroundBrush(QColor(SCENE_BG))

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
            hint.setPos(20, SEG_LANE_Y + SEG_HEIGHT / 2 - 10)
            self.addItem(hint)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        scene_w = self.sceneRect().width()
        # 1. 背景带
        band = QRectF(0, 0, scene_w, RULER_HEIGHT)
        painter.fillRect(band, QColor(RULER_BAND_COLOR))
        # 2. 选刻度间隔
        major, minor = _pick_tick_interval(
            self.pixels_per_frame,
            self.model.frame_rate,
            self.model.display_mode,
        )
        ppf = self.pixels_per_frame
        if ppf <= 0:
            return
        # 3. 可见 x 范围（rect 是脏区域；裁掉负数和超出 sceneRect）
        x_start = max(0.0, rect.left())
        x_end = min(scene_w, rect.right())
        # 4. minor ticks
        painter.setPen(QPen(QColor(TICK_MINOR_COLOR), 1))
        frame = (int(x_start / ppf) // minor) * minor
        while frame * ppf <= x_end:
            if frame % major != 0:
                x = frame * ppf
                painter.drawLine(QPointF(x, RULER_HEIGHT - 6),
                                 QPointF(x, RULER_HEIGHT))
            frame += minor
        # 5. major ticks + 标签
        major_pen = QPen(QColor(TICK_MAJOR_COLOR), 1)
        label_color = QColor(TICK_LABEL_COLOR)
        f = QFont(); f.setPointSize(7); painter.setFont(f)
        fr = max(self.model.frame_rate, 1)
        frame = (int(x_start / ppf) // major) * major
        while frame * ppf <= x_end:
            x = frame * ppf
            painter.setPen(major_pen)
            painter.drawLine(QPointF(x, RULER_HEIGHT - 12),
                             QPointF(x, RULER_HEIGHT))
            if self.model.display_mode == "frames":
                label = f"{frame}f"
            else:
                sec = frame / fr
                label = (f"{int(sec)}s" if sec == int(sec)
                         else f"{sec:.1f}s")
            painter.setPen(label_color)
            painter.drawText(QPointF(x + 2, RULER_HEIGHT - 14), label)
            frame += major

    def set_cursor_x(self, x: Optional[float]) -> None:
        """设/清游标 x（scene 坐标）。None = 隐藏。"""
        if self._cursor_x == x:
            return
        self._cursor_x = x
        self.update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._cursor_x is None:
            return
        x = self._cursor_x
        h = self.sceneRect().height()
        # 1. 红色竖线
        painter.setPen(QPen(QColor(CURSOR_LINE_COLOR), 1))
        painter.drawLine(QPointF(x, 0), QPointF(x, h))
        # 2. 顶部标签
        label = _format_cursor_label(
            x, self.pixels_per_frame, self.model.frame_rate,
            self.model.display_mode)
        f = QFont(); f.setPointSize(7); painter.setFont(f)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 6
        th = fm.height() + 2
        box = QRectF(x + 1, 0, tw, th)
        painter.fillRect(box, QColor(CURSOR_LABEL_BG))
        painter.setPen(QColor(CURSOR_LABEL_FG))
        painter.drawText(box, Qt.AlignCenter, label)

    def dragEnterEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            self.set_cursor_x(e.scenePos().x())
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        self.set_cursor_x(None)
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

    def dragLeaveEvent(self, e):
        self.set_cursor_x(None)
        super().dragLeaveEvent(e)

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
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.rebuild()

    def rebuild(self):
        # 保留所有选中（含 SegmentItem + AudioItem）跨 rebuild
        selected_seg_ids: set[str] = set()
        selected_audio_ids: set[str] = set()
        if hasattr(self, "_scene"):
            for item in self._scene.selectedItems():
                if isinstance(item, SegmentItem):
                    selected_seg_ids.add(item.seg.seg_id)
                elif isinstance(item, AudioItem):
                    selected_audio_ids.add(item.audio.audio_id)
        self._scene.pixels_per_frame = self.pixels_per_frame
        self._scene.rebuild()
        # 恢复
        for item in self._scene.items():
            if isinstance(item, SegmentItem) and item.seg.seg_id in selected_seg_ids:
                item.setSelected(True)
            elif isinstance(item, AudioItem) and item.audio.audio_id in selected_audio_ids:
                item.setSelected(True)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            seg_ids: list[str] = []
            audio_ids: list[str] = []
            for item in self._scene.selectedItems():
                if isinstance(item, SegmentItem):
                    seg_ids.append(item.seg.seg_id)
                elif isinstance(item, AudioItem):
                    audio_ids.append(item.audio.audio_id)
            for sid in seg_ids:
                self.segmentDeleteRequested.emit(sid)
            for aid in audio_ids:
                self.audioDeleteRequested.emit(aid)
            if seg_ids or audio_ids:
                e.accept()
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
