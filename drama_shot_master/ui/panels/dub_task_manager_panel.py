"""配音任务栏：任务表 + 新建/打开/复制/删除。镜像 VideoTaskManagerPanel。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QInputDialog, QMessageBox, QHeaderView,
)

from drama_shot_master.config import Config
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState


class DubTaskManagerPanel(BasePanel):
    taskRenamed = Signal(str, str)

    def __init__(self, state: AppState, cfg: Config, store: DubTaskStore,
                 open_window_cb, close_window_cb, persist_cb, parent=None):
        super().__init__(state, cfg, parent)
        self.store = store
        self._open_cb = open_window_cb
        self._close_cb = close_window_cb
        self._persist = persist_cb
        self._live_status: dict[str, str] = {}
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self):
        return True, ""

    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        for txt, slot in (("新建", self._new), ("打开", self._open),
                          ("复制", self._dup), ("删除", self._del),
                          ("重命名", self._rename)):
            b = QPushButton(txt); b.clicked.connect(slot); bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "模式", "状态", "最近输出", "更新时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.doubleClicked.connect(lambda *_: self._open())
        root.addWidget(self.table, 1)

    def _selected_id(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def refresh(self):
        import time
        tasks = self.store.all()
        self.table.setRowCount(len(tasks))
        for r, t in enumerate(tasks):
            name = QTableWidgetItem(t.name); name.setData(Qt.UserRole, t.id)
            mode = "音色设计" if t.mode == "design" else "声音克隆"
            status = self._live_status.get(t.id, "—")
            updated = time.strftime("%m-%d %H:%M", time.localtime(t.updated_at)) if t.updated_at else ""
            for c, val in enumerate([name, QTableWidgetItem(mode),
                                     QTableWidgetItem(status),
                                     QTableWidgetItem(t.last_result),
                                     QTableWidgetItem(updated)]):
                self.table.setItem(r, c, val)

    def set_task_status(self, task_id: str, status: str):
        self._live_status[task_id] = status
        self.refresh()

    def clear_task_status(self, task_id: str):
        self._live_status.pop(task_id, None)
        self.refresh()

    def _new(self):
        name, ok = QInputDialog.getText(self, "新建配音任务", "名称:")
        if not ok or not name.strip():
            return
        t = self.store.add(name.strip(), mode="clone", payload={"mode_kind": "clone"})
        self._persist(); self.refresh(); self._open_cb(t)

    def _open(self):
        tid = self._selected_id()
        if tid:
            self._open_cb(self.store.get(tid))

    def _dup(self):
        tid = self._selected_id()
        if tid:
            self.store.duplicate(tid); self._persist(); self.refresh()

    def _del(self):
        tid = self._selected_id()
        if not tid:
            return
        if QMessageBox.question(self, "删除", "确定删除该任务？") == QMessageBox.Yes:
            self._close_cb(tid); self.store.remove(tid); self._persist(); self.refresh()

    def _rename(self):
        tid = self._selected_id()
        if not tid:
            return
        t = self.store.get(tid)
        name, ok = QInputDialog.getText(self, "重命名", "名称:", text=t.name)
        if ok and name.strip():
            self.store.update(tid, name=name.strip()); self._persist()
            self.refresh(); self.taskRenamed.emit(tid, name.strip())
