"""SoundtrackPanel：配乐任务列表（顶部"配乐"tab 内容）。

任务以 list[dict] 维护，结构：{id,name,mp4,style,workflow_id,status,output}。
状态色标同视频任务。开窗/持久化由 main_window 经回调注入。
"""
from __future__ import annotations

import time
from secrets import token_hex

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView,
)

from drama_shot_master.ui.panels.base_panel import BasePanel

_STATUS_COLORS = {
    "空闲": "#9aa0a6", "生成中": "#4a9eff", "完成": "#4ec98f", "失败": "#ff5c5c",
}


def _gen_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


class SoundtrackPanel(BasePanel):
    """配乐任务列表。开窗与持久化由回调交给 main_window。"""

    def __init__(self, state, cfg, open_window_cb, persist_cb, parent=None):
        super().__init__(state, cfg, parent)
        self._open_window_cb = open_window_cb
        self._persist_cb = persist_cb
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self) -> tuple[bool, str]:
        return False, "请用列表内按钮管理配乐任务"

    def execute(self):
        raise NotImplementedError

    def _tasks(self) -> list:
        return getattr(self.cfg, "soundtrack_tasks", [])

    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_new = QPushButton("+ 新建配乐任务")
        self.btn_open = QPushButton("打开")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "成片 MP4", "状态", "输出"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table, 1)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_del.clicked.connect(self._on_del)

    @staticmethod
    def _ro(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    def _status_item(self, status: str) -> QTableWidgetItem:
        it = self._ro(status)
        color = _STATUS_COLORS.get(status)
        if color:
            it.setForeground(QColor(color))
            if status in ("生成中", "失败"):
                f = QFont(); f.setBold(True); it.setFont(f)
        return it

    def refresh(self):
        self.table.blockSignals(True)        # 程序填充别触发 itemChanged
        self.table.setRowCount(0)
        for t in self._tasks():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(t.get("name", "未命名"))  # 名称列可编辑
            name_item.setData(Qt.UserRole, t.get("id"))
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, self._ro(t.get("mp4", "")))
            self.table.setItem(r, 2, self._status_item(t.get("status", "空闲")))
            self.table.setItem(r, 3, self._ro(t.get("output") or "—"))
        self.table.blockSignals(False)

    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        tid = item.data(Qt.UserRole) if item else None
        return next((t for t in self._tasks() if t.get("id") == tid), None)

    def _on_new(self):
        n = len(self._tasks()) + 1
        task = {"id": _gen_id(), "name": f"配乐任务 {n}", "mp4": "",
                "style": "", "workflow_id": "", "status": "空闲", "output": ""}
        self._tasks().append(task)
        self._persist_cb()
        self.refresh()
        self._open_window_cb(task)

    def _on_open(self):
        t = self._selected()
        if not t:
            QMessageBox.information(self, "打开", "请先选一个任务")
            return
        self._open_window_cb(t)

    def _on_double_clicked(self, item):
        # 双击名称列(0)进入内联改名；双击其它列打开任务（同视频生成）
        if item.column() == 0:
            return
        self._on_open()

    def _on_item_changed(self, item):
        # 名称列编辑完成 → 写回任务 + 落盘
        if item.column() != 0:
            return
        tid = item.data(Qt.UserRole)
        new_name = item.text().strip()
        if not tid or not new_name:
            return
        for t in self._tasks():
            if t.get("id") == tid:
                t["name"] = new_name
                break
        self._persist_cb()

    def _on_del(self):
        t = self._selected()
        if not t:
            return
        if QMessageBox.question(self, "删除", "确定删除该配乐任务？",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._tasks().remove(t)
        self._persist_cb()
        self.refresh()
