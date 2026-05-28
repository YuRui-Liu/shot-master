"""SoundtrackPanel：配乐任务列表（顶部"配乐"tab 内容）。

任务以 list[dict] 维护，结构：{id,name,mp4,style,workflow_id,status,output}。
状态色标同视频任务。开窗/持久化由 main_window 经回调注入。
"""
from __future__ import annotations

import time
from secrets import token_hex

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView,
)

from drama_shot_master.ui.panels.base_panel import BasePanel


def _gen_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


class _SoundtrackTaskView:
    """把 cfg.soundtrack_tasks 的 dict 暴露成 .id/.name/.payload（活引用），
    供通用 TaskWorkspacePage（按属性访问）消费。"""

    def __init__(self, d: dict):
        self._d = d

    @property
    def id(self):
        return self._d.get("id", "")

    @property
    def name(self):
        return self._d.get("name", "")

    @property
    def payload(self):
        return self._d


class SoundtrackPanel(BasePanel):
    """配乐任务列表。开窗与持久化由回调交给 main_window。"""

    taskSelected = Signal(object)
    taskDeleted = Signal(str)
    taskRenamed = Signal(str, str)

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
        self.btn_new = QPushButton("新建")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "成片 MP4", "输出"])
        # 与生视频/出图/配音 一致：名称+状态默认占满可见区，成片 MP4/输出 推到右侧滑动看
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)        # 名称
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # 状态
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)        # 成片 MP4
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)        # 输出
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self.table, 1)
        self.table.viewport().installEventFilter(self)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_del.clicked.connect(self._on_del)

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport():
            if ev.type() == QEvent.Resize:
                self._fit_name_col()
            elif ev.type() == QEvent.MouseButtonPress:
                # 点空白区不要清掉行选中
                if not self.table.indexAt(ev.pos()).isValid():
                    return True
        return super().eventFilter(obj, ev)

    def _fit_name_col(self):
        vw = self.table.viewport().width()
        self.table.setColumnWidth(0, max(150, vw - self.table.columnWidth(1)))

    @staticmethod
    def _ro(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    def _status_item(self, status: str) -> QTableWidgetItem:
        it = self._ro(status)
        from drama_shot_master.ui.theme import status_color
        color = status_color(status, self.cfg)
        if color:
            it.setForeground(QColor(color))
            if status in ("生成中", "失败"):
                f = QFont(); f.setBold(True); it.setFont(f)
        return it

    def refresh(self):
        self.table.blockSignals(True)        # 程序填充别触发 itemChanged/itemSelectionChanged
        self.table.setRowCount(0)
        for t in self._tasks():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(t.get("name", "未命名"))  # 名称列可编辑
            name_item.setData(Qt.UserRole, t.get("id"))
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, self._status_item(t.get("status", "空闲")))
            self.table.setItem(r, 2, self._ro(t.get("mp4", "")))
            self.table.setItem(r, 3, self._ro(t.get("output") or "—"))
        self.table.blockSignals(False)
        self._fit_name_col()             # 数据填完后按最终"状态"宽度重算名称列

    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        tid = item.data(Qt.UserRole) if item else None
        return next((t for t in self._tasks() if t.get("id") == tid), None)

    def _on_selection_changed(self):
        d = self._selected()
        if d is not None:
            self.taskSelected.emit(_SoundtrackTaskView(d))

    def _select_task(self, tid: str):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.data(Qt.UserRole) == tid:
                self.table.setCurrentCell(r, 0)
                return

    def _on_new(self):
        n = len(self._tasks()) + 1
        task = {"id": _gen_id(), "name": f"配乐任务 {n}", "mp4": "",
                "style": "", "workflow_id": "", "status": "空闲", "output": ""}
        self._tasks().append(task)
        self._persist_cb()
        self.refresh()
        self._select_task(task["id"])

    def _on_item_changed(self, item):
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
        self.taskRenamed.emit(tid, new_name)

    def _on_del(self):
        t = self._selected()
        if not t:
            return
        if QMessageBox.question(self, "删除", "确定删除该配乐任务？",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        tid = t.get("id")
        self._tasks().remove(t)
        self._persist_cb()
        self.refresh()
        self.taskDeleted.emit(tid)
