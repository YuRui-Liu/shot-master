"""图片生成任务栏：任务表 + 新建/打开/复制/删除。镜像 VideoTaskManagerPanel。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QInputDialog, QMessageBox, QHeaderView,
)

from drama_shot_master.config import Config
from drama_shot_master.core.imggen_task_store import ImgGenTaskStore
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState


class ImgGenTaskManagerPanel(BasePanel):
    taskRenamed = Signal(str, str)
    taskSelected = Signal(object)
    taskDeleted = Signal(str)

    def __init__(self, state: AppState, cfg: Config, store: ImgGenTaskStore,
                 open_window_cb, close_window_cb, persist_cb, parent=None):
        super().__init__(state, cfg, parent)
        self.store = store
        self._open_cb = open_window_cb
        self._close_cb = close_window_cb
        self._persist = persist_cb
        self._live_status: dict[str, str] = {}
        self._loading = False
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self):
        return True, ""

    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        for txt, slot in (("新建", self._new),
                          ("复制", self._dup), ("删除", self._del)):
            b = QPushButton(txt); b.clicked.connect(slot); bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "最近输出", "更新时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.DoubleClicked)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self.table, 1)

    def _on_selection_changed(self):
        if self._loading:            # refresh 重建表期间不误发
            return
        tid = self._selected_id()
        if not tid:
            return
        t = self.store.get(tid)
        if t is not None:
            self.taskSelected.emit(t)

    def _selected_id(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def refresh(self):
        import time
        self._loading = True
        tasks = self.store.all()
        self.table.setRowCount(len(tasks))
        for r, t in enumerate(tasks):
            name = QTableWidgetItem(t.name); name.setData(Qt.UserRole, t.id)
            name.setFlags(name.flags() | Qt.ItemIsEditable)
            status = self._live_status.get(t.id, "—")
            updated = time.strftime("%m-%d %H:%M", time.localtime(t.updated_at)) if t.updated_at else ""
            for c, val in enumerate([name,
                                     QTableWidgetItem(status),
                                     QTableWidgetItem(t.last_result),
                                     QTableWidgetItem(updated)]):
                if c != 0:
                    val.setFlags(val.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, val)
        self._loading = False

    def _on_item_changed(self, item):
        if self._loading or item.column() != 0:
            return
        tid = item.data(Qt.UserRole)
        new_name = item.text().strip()
        if tid and new_name:
            self.store.update(tid, name=new_name); self._persist()
            self.taskRenamed.emit(tid, new_name)

    def set_task_status(self, task_id: str, status: str):
        self._live_status[task_id] = status
        self.refresh()

    def clear_task_status(self, task_id: str):
        self._live_status.pop(task_id, None)
        self.refresh()

    def _new(self):
        name, ok = QInputDialog.getText(self, "新建图片生成任务", "名称:")
        if not ok or not name.strip():
            return
        t = self.store.add(name.strip(), payload={"quality": "2K", "ratio": "自动", "n": 1})
        self._persist(); self.refresh(); self._select_task(t.id)

    def _select_task(self, task_id):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.data(Qt.UserRole) == task_id:
                self.table.setCurrentCell(r, 0)
                break

    def _dup(self):
        tid = self._selected_id()
        if tid:
            self.store.duplicate(tid); self._persist(); self.refresh()

    def _del(self):
        tid = self._selected_id()
        if not tid:
            return
        if QMessageBox.question(self, "删除", "确定删除该任务？") == QMessageBox.Yes:
            self.store.remove(tid); self._persist(); self.refresh()
            self.taskDeleted.emit(tid)

