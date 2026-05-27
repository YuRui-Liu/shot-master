"""中栏共享缩略图网格。

两种选择模式（由外部 set_mode 切换）：
  - "multi": 点击切换选中，蓝色描边
  - "order": 点击累加序号徽章，再点取消并重排
双击发 previewRequested(int)。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QApplication,
)

from drama_shot_master.imaging.loader import ImageInfo
from drama_shot_master.ui.thumbnail_delegate import (
    ThumbnailDelegate, BADGE_ROLE, SELECTED_ROLE,
)


THUMB_MIN, THUMB_MAX, THUMB_DEFAULT = 80, 240, 140


class ThumbnailGrid(QWidget):
    selectionChanged = Signal(list)     # list[int]，order 模式按点击顺序
    previewRequested = Signal(int)
    thumbSizeChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "multi"
        self._order: list[int] = []
        self._anchor: int | None = None   # 上次普通点击的行，作 Shift 区间锚点
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(8)
        self.list.setIconSize(QSize(THUMB_DEFAULT, THUMB_DEFAULT))
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setItemDelegate(ThumbnailDelegate(self.list))
        self.list.itemClicked.connect(self._on_clicked)
        self.list.itemDoubleClicked.connect(self._on_double)
        layout.addWidget(self.list, 1)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("缩略图大小:"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(THUMB_MIN)
        self.slider.setMaximum(THUMB_MAX)
        self.slider.setValue(THUMB_DEFAULT)
        self.slider.valueChanged.connect(self._on_size)
        bar.addWidget(self.slider, 1)
        clr = QPushButton("清空选择")
        clr.clicked.connect(self.clear_selection)
        bar.addWidget(clr)
        layout.addLayout(bar)

    def set_mode(self, mode: str):
        """'multi' 或 'order'。切换时清空当前选择。"""
        if mode not in ("multi", "order"):
            return
        self._mode = mode
        self.clear_selection()

    def set_thumb_size(self, size: int):
        size = max(THUMB_MIN, min(THUMB_MAX, size))
        self.slider.setValue(size)

    def populate(self, images: list[ImageInfo]):
        self.list.clear()
        self._order = []
        self._anchor = None
        for info in images:
            pix = QPixmap(str(info.path))
            if pix.isNull():
                continue
            pix = pix.scaled(THUMB_MAX, THUMB_MAX,
                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
            it = QListWidgetItem(QIcon(pix), info.path.name)
            it.setData(BADGE_ROLE, None)
            it.setData(SELECTED_ROLE, False)
            sz = self.slider.value()
            it.setSizeHint(QSize(sz + 24, sz + 50))
            self.list.addItem(it)
        self.selectionChanged.emit([])

    def _on_clicked(self, item: QListWidgetItem):
        row = self.list.row(item)
        shift = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
        if shift and self._anchor is not None:
            self._select_range(self._anchor, row)
        else:
            self._toggle(row)
            self._anchor = row
        self.list.viewport().update()
        self.selectionChanged.emit(list(self._order))

    def _toggle(self, row: int):
        item = self.list.item(row)
        if self._mode == "multi":
            cur = bool(item.data(SELECTED_ROLE))
            item.setData(SELECTED_ROLE, not cur)
            if not cur:
                self._order.append(row)
            elif row in self._order:
                self._order.remove(row)
        else:  # order
            if row in self._order:
                self._order.remove(row)
            else:
                self._order.append(row)
            self._refresh_badges()

    def _select_range(self, anchor: int, row: int):
        """Shift 区间选：把 [anchor, row] 区间内未选中的行按行序（升序）追加，
        已选中的保持原有次序。锚点不变，便于继续扩选。"""
        lo, hi = sorted((anchor, row))
        for r in range(lo, hi + 1):
            if r not in self._order:
                self._order.append(r)
                if self._mode == "multi":
                    self.list.item(r).setData(SELECTED_ROLE, True)
        if self._mode == "order":
            self._refresh_badges()

    def _refresh_badges(self):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if i in self._order:
                it.setData(BADGE_ROLE, self._order.index(i) + 1)
            else:
                it.setData(BADGE_ROLE, None)

    def _on_double(self, item: QListWidgetItem):
        self.previewRequested.emit(self.list.row(item))

    def _on_size(self, size: int):
        self.list.setIconSize(QSize(size, size))
        for i in range(self.list.count()):
            self.list.item(i).setSizeHint(QSize(size + 24, size + 50))
        self.thumbSizeChanged.emit(size)

    def clear_selection(self):
        self._order = []
        self._anchor = None
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setData(BADGE_ROLE, None)
            it.setData(SELECTED_ROLE, False)
        self.list.viewport().update()
        self.selectionChanged.emit([])

    def selected_order(self) -> list[int]:
        """当前选择（按点击顺序的行号列表）。"""
        return list(self._order)
