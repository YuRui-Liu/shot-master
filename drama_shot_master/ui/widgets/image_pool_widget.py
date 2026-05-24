"""ImagePoolWidget：持久图片池。横向 IconMode + 拖出到 TimelineWidget。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal, QMimeData
from PySide6.QtGui import QBrush, QColor, QDrag, QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem


MIME_IMG_PATH = "application/x-spb-image-path"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
THUMB_SIZE = QSize(64, 48)


class ImagePoolWidget(QListWidget):
    """图片池：拖出到时间轴；显示已用/未用着色。"""

    imagesAdded = Signal(list)              # list[Path]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Static)
        self.setResizeMode(QListWidget.Adjust)
        self.setIconSize(THUMB_SIZE)
        self.setSpacing(4)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QListWidget.SingleSelection)

    # ---------- 外部 API ----------

    def set_paths(self, paths: list[Path]):
        """重建池子里的 items（VideoPanel 在 model.pool 变化后调）。"""
        self.clear()
        for p in paths:
            item = QListWidgetItem(self._make_icon(p), p.name)
            item.setData(Qt.UserRole, p)
            item.setToolTip(str(p))
            self.addItem(item)

    def refresh_usage(self, usage: dict[Path, int]):
        """根据 model.pool_usage() 给已用/未用着色。"""
        for i in range(self.count()):
            item = self.item(i)
            p = item.data(Qt.UserRole)
            used = usage.get(p, 0) > 0
            item.setForeground(QBrush(QColor("#ffffff") if used
                                        else QColor("#666666")))
            item.setToolTip(f"{p}\n被引用 {usage.get(p, 0)} 次")

    # ---------- 拖出（→ TimelineWidget） ----------

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        path: Path = item.data(Qt.UserRole)
        mime = QMimeData()
        mime.setData(MIME_IMG_PATH, str(path).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(item.icon().pixmap(THUMB_SIZE))
        drag.exec(Qt.CopyAction)

    # ---------- 拖入（OS 文件 → 池） ----------

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not e.mimeData().hasUrls():
            return super().dropEvent(e)
        paths = []
        for url in e.mimeData().urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in IMG_EXTS:
                paths.append(Path(local))
        if paths:
            self.imagesAdded.emit(paths)
            e.acceptProposedAction()

    # ---------- 私有 ----------

    def _make_icon(self, path: Path) -> QIcon:
        pix = QPixmap(str(path))
        if pix.isNull():
            pix = QPixmap(THUMB_SIZE); pix.fill(QColor("#444"))
        else:
            pix = pix.scaled(THUMB_SIZE, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
        return QIcon(pix)
