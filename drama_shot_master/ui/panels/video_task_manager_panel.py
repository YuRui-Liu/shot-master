"""VideoTaskManagerPanel：视频生成任务列表（替换原 VideoPanel 在 stack 中的位置）。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView,
)

# 状态 → 文字颜色（深色主题下的色标）
_STATUS_COLORS = {
    "空闲": "#9aa0a6",     # 灰
    "生成中": "#4a9eff",   # 蓝（强调）
    "完成": "#4ec98f",     # 绿
    "失败": "#ff5c5c",     # 红
}

from drama_shot_master.config import Config
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.core.video_timeline_model import TimelineModel
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState


class VideoTaskManagerPanel(BasePanel):
    """任务列表 + 新建/打开/复制/删除。开窗与持久化由回调交给 main_window。"""

    taskRenamed = Signal(str, str)   # (task_id, new_name) → main_window 同步已开窗标题

    def __init__(self, state: AppState, cfg: Config,
                 store: VideoTaskStore,
                 open_window_cb, close_window_cb, persist_cb,
                 parent=None):
        super().__init__(state, cfg, parent)
        self.store = store
        self._open_window_cb = open_window_cb
        self._close_window_cb = close_window_cb
        self._persist_cb = persist_cb
        self._live_status: dict[str, str] = {}
        self._build_ui()
        self.refresh()

    # ---------- BasePanel ----------
    def select_mode(self) -> str:
        return "none"

    def validate(self) -> tuple[bool, str]:
        return False, "请用列表内按钮管理任务"

    def execute(self):
        raise NotImplementedError("manager uses list buttons")

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_new = QPushButton("+ 新建任务")
        self.btn_open = QPushButton("打开")
        self.btn_dup = QPushButton("复制")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_dup, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "上次结果", "更新时间"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        root.addWidget(self.table, 1)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_dup.clicked.connect(self._on_dup)
        self.btn_del.clicked.connect(self._on_del)

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for t in self.store.all():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(t.name)
            name_item.setData(Qt.UserRole, t.id)
            self.table.setItem(r, 0, name_item)
            status = self._live_status.get(t.id, "空闲")
            self.table.setItem(r, 1, self._status_item(status))
            res = Path(t.last_result).name if t.last_result else "—"
            self.table.setItem(r, 2, self._readonly(res))
            ts = (time.strftime("%m-%d %H:%M", time.localtime(t.updated_at))
                  if t.updated_at else "—")
            self.table.setItem(r, 3, self._readonly(ts))
        self.table.blockSignals(False)

    @staticmethod
    def _readonly(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    @classmethod
    def _status_item(cls, status: str) -> QTableWidgetItem:
        it = cls._readonly(status)
        color = _STATUS_COLORS.get(status)
        if color:
            it.setForeground(QColor(color))
            if status in ("生成中", "失败"):
                f = QFont(); f.setBold(True); it.setFont(f)
        return it

    def _selected_task_id(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else ""

    # ---------- public ----------
    def set_task_status(self, task_id: str, status: str):
        self._live_status[task_id] = status
        self.refresh()

    def clear_task_status(self, task_id: str):
        self._live_status.pop(task_id, None)
        self.refresh()

    # ---------- slots ----------
    def _on_new(self):
        n = len(self.store.all()) + 1
        t = self.store.add(f"任务 {n}", TimelineModel().to_dict())
        self._persist_cb()
        self.refresh()
        self._open_window_cb(t)

    def _on_open(self):
        tid = self._selected_task_id()
        if not tid:
            QMessageBox.information(self, "打开", "请先选一个任务")
            return
        t = self.store.get(tid)
        if t:
            self._open_window_cb(t)

    def _on_double_clicked(self, item):
        if item.column() == 0:
            return
        tid = self._selected_task_id()
        t = self.store.get(tid) if tid else None
        if t:
            self._open_window_cb(t)

    def _on_dup(self):
        tid = self._selected_task_id()
        if not tid:
            return
        if self.store.duplicate(tid):
            self._persist_cb()
            self.refresh()

    def _on_del(self):
        tid = self._selected_task_id()
        if not tid:
            return
        if QMessageBox.question(
                self, "删除任务", "确定删除该任务？不可恢复。",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._close_window_cb(tid)
        self.store.remove(tid)
        self._live_status.pop(tid, None)
        self._persist_cb()
        self.refresh()

    def _on_item_changed(self, item):
        if item.column() != 0:
            return
        tid = item.data(Qt.UserRole)
        new_name = item.text().strip()
        if tid and new_name:
            self.store.update(tid, name=new_name)
            self._persist_cb()
            self.taskRenamed.emit(tid, new_name)
