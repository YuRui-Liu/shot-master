"""缩略图列表：拿一个文件夹，加载所有图片缩略图；支持单选/多选/有序多选+顺序徽章。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QListView, QAbstractItemView,
)


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class ThumbnailListWidget(QListWidget):
    """三种模式：
      mode='single' 单选
      mode='multi'  多选（点击顺序不重要）
      mode='order'  多选+顺序徽章（拼图、反推按时间序选图）
    """
    selection_changed = Signal(list)  # list[Path]

    def __init__(self, mode: str = "multi", thumb_size: int = 160, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._thumb_size = thumb_size
        self._order: list[Path] = []   # for mode='order'
        self.setViewMode(QListView.IconMode)
        self.setIconSize(QSize(thumb_size, thumb_size))
        self.setGridSize(QSize(thumb_size + 24, thumb_size + 50))
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        if mode == "single":
            self.setSelectionMode(QAbstractItemView.SingleSelection)
        elif mode == "multi":
            self.setSelectionMode(QAbstractItemView.MultiSelection)
        elif mode == "order":
            self.setSelectionMode(QAbstractItemView.NoSelection)
            self.itemClicked.connect(self._on_item_clicked_order)

        if mode != "order":
            self.itemSelectionChanged.connect(self._emit_changed)

    def load_folder(self, folder: Path):
        self.clear()
        self._order = []
        if not folder or not folder.is_dir():
            return
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                self._add_item(p)
        self._emit_changed()

    def _add_item(self, path: Path):
        pix = QPixmap(str(path))
        if pix.isNull():
            return
        pix = pix.scaled(self._thumb_size, self._thumb_size,
                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
        item = QListWidgetItem(QIcon(pix), path.name)
        item.setData(Qt.UserRole, str(path))
        item.setSizeHint(QSize(self._thumb_size + 24, self._thumb_size + 50))
        item.setTextAlignment(Qt.AlignCenter)
        self.addItem(item)

    def selected_paths(self) -> list[Path]:
        if self._mode == "order":
            return list(self._order)
        return [Path(it.data(Qt.UserRole)) for it in self.selectedItems()]

    def _on_item_clicked_order(self, item: QListWidgetItem):
        p = Path(item.data(Qt.UserRole))
        if p in self._order:
            self._order.remove(p)
        else:
            self._order.append(p)
        self._refresh_order_badges()
        self._emit_changed()

    def _refresh_order_badges(self):
        for i in range(self.count()):
            item = self.item(i)
            p = Path(item.data(Qt.UserRole))
            base = QPixmap(str(p))
            if base.isNull():
                continue
            base = base.scaled(self._thumb_size, self._thumb_size,
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if p in self._order:
                idx = self._order.index(p) + 1
                badge = QPixmap(base)
                painter = QPainter(badge)
                painter.setRenderHint(QPainter.Antialiasing)
                r = 22
                painter.setBrush(QColor(79, 142, 220))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(4, 4, r, r)
                painter.setPen(Qt.white)
                f = QFont()
                f.setBold(True)
                painter.setFont(f)
                painter.drawText(4, 4, r, r, Qt.AlignCenter, str(idx))
                painter.end()
                item.setIcon(QIcon(badge))
            else:
                item.setIcon(QIcon(base))

    def _emit_changed(self):
        self.selection_changed.emit(self.selected_paths())

    def clear_order(self):
        self._order = []
        self._refresh_order_badges()
        self._emit_changed()
