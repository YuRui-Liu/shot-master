"""ComposeTaskManagerPanel：成片合成任务列表（master 面板）。

drop-in 兼容 VideoTaskManagerPanel，用于 TaskWorkspacePage(manager=...) 的 manager 参数。
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QWidget,
)

from drama_shot_master.core.compose_task_store import ComposeTaskStore


class ComposeTaskManagerPanel(QWidget):
    """任务列表 + 新建/删除/重命名。

    主-详模式下由 TaskWorkspacePage 承载：选中行发 taskSelected、删除发 taskDeleted。
    """

    taskRenamed = Signal(str, str)   # (task_id, new_name)
    taskSelected = Signal(object)    # 选中的 ComposeTask（主-详用）
    taskDeleted = Signal(str)        # 删除任务后通知页面清理其缓存编辑器
    icon_rail_updated = Signal()

    def __init__(self, store: ComposeTaskStore, on_persist, parent=None):
        super().__init__(parent)
        self.store = store
        self._persist_cb = on_persist
        self._live_status: dict[str, str] = {}
        self._build_ui()
        self.refresh()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_new = QPushButton("新建")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "更新时间"])
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)        # 名称
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # 状态
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)        # 更新时间
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 140)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table, 1)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_del.clicked.connect(self._on_del)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport() and ev.type() == QEvent.Resize:
            self._fit_name_col()
        return super().eventFilter(obj, ev)

    def _fit_name_col(self):
        vw = self.table.viewport().width()
        self.table.setColumnWidth(0, max(120, vw - self.table.columnWidth(1)))

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for t in self.store.all():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(t.name)
            name_item.setData(Qt.UserRole, t.id)
            self.table.setItem(r, 0, name_item)
            status = self._live_status.get(t.id, t.status or "空闲")
            self.table.setItem(r, 1, self._status_item(status))
            ts = (time.strftime("%m-%d %H:%M", time.localtime(t.updated_at))
                  if t.updated_at else "—")
            self.table.setItem(r, 2, self._readonly(ts))
        self.table.blockSignals(False)
        self._fit_name_col()
        self.icon_rail_updated.emit()

    @staticmethod
    def _readonly(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    def _status_item(self, status: str) -> QTableWidgetItem:
        it = self._readonly(status)
        _STATUS_COLORS = {
            "生成中": "#4a9eff",
            "完成": "#52b788",
            "失败": "#e05252",
            "空闲": None,
        }
        color = _STATUS_COLORS.get(status)
        if color:
            it.setForeground(QColor(color))
            if status in ("生成中", "失败"):
                f = QFont()
                f.setBold(True)
                it.setFont(f)
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

    def get_status(self, task_id: str) -> str:
        """返回 live_status，若未设置则回退到 store 中任务的状态字段，最终默认"空闲"。"""
        if task_id in self._live_status:
            return self._live_status[task_id]
        t = self.store.get(task_id)
        if t is not None and t.status:
            return t.status
        return "空闲"

    def clear_task_status(self, task_id: str):
        self._live_status.pop(task_id, None)
        self.refresh()

    def update_task_name(self, task_id: str, name: str):
        """TaskWorkspacePage 重命名同步回调。"""
        self.store.update(task_id, name=name)

    def selected_task(self):
        """当前选中行对应的 task（无选中返回 None）。"""
        tid = self._selected_task_id()
        return self.store.get(tid) if tid else None

    def select_by_id(self, item_id: str) -> None:
        """CollapsibleTaskBar 图标轨点击后跳转到对应行。"""
        self._select_task(item_id)

    def icon_rail_items(self):
        """折叠模式下图标轨所需数据；CollapsibleTaskBar.collapse() 会调用此方法。"""
        from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem
        items = []
        for i, t in enumerate(self.store.all()):
            raw = self._live_status.get(t.id, t.status or "")
            if raw == "生成中":
                status = "running"
            elif raw == "失败":
                status = "error"
            elif raw == "完成":
                status = "done"
            else:
                status = "idle"
            items.append(IconRailItem(
                index=i + 1, label=t.name[:2], status=status,
                tooltip=f"{t.name}\n状态: {raw or '空闲'}", item_id=t.id))
        return items

    # ---------- private ----------
    def _on_selection_changed(self):
        tid = self._selected_task_id()
        if not tid:
            return
        t = self.store.get(tid)
        if t is not None:
            self.taskSelected.emit(t)

    def _select_task(self, task_id: str):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.data(Qt.UserRole) == task_id:
                self.table.setCurrentCell(r, 0)
                break

    # ---------- slots ----------
    def _on_new(self):
        n = len(self.store.all()) + 1
        t = self.store.add(f"成片 {n}", {"clips": []})
        self._persist_cb()
        self.refresh()
        self._select_task(t.id)

    def _on_del(self):
        tid = self._selected_task_id()
        if not tid:
            return
        if QMessageBox.question(
                self, "删除任务", "确定删除该任务？不可恢复。",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.store.remove(tid)
        self._live_status.pop(tid, None)
        self._persist_cb()
        self.refresh()
        self.taskDeleted.emit(tid)

    def _on_item_changed(self, item):
        if item.column() != 0:
            return
        tid = item.data(Qt.UserRole)
        new_name = item.text().strip()
        if tid and new_name:
            self.store.update(tid, name=new_name)
            self._persist_cb()
            self.taskRenamed.emit(tid, new_name)
