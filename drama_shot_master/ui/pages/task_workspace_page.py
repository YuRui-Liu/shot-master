"""TaskWorkspacePage：生成类功能的窗内主-详页。

左 master（注入的 *TaskManagerPanel，发 taskSelected(task)）；
右详情 = 头条（任务名 + 「⧉ 浮出独立窗」）+ QStackedWidget（index0 占位，其余每任务缓存的编辑器）。
- 每任务首次选中懒建编辑器并缓存；切任务不丢未存编辑；提交后台线程跑 → 窗内并行。
- 浮出 = 把活编辑器 reparent 进 DetachedEditorWindow；关窗收回；单一数据源。
与具体功能解耦：editor_factory/wire_editor/payload_of/on_persist/title_for 注入。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget,
)
from PySide6.QtCore import Qt

from drama_shot_master.ui.windows.detached_editor_window import DetachedEditorWindow


class TaskWorkspacePage(QWidget):
    def __init__(self, manager, editor_factory, wire_editor, payload_of,
                 on_persist, title_for, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._editor_factory = editor_factory
        self._wire_editor = wire_editor
        self._payload_of = payload_of
        self._on_persist = on_persist
        self._title_for = title_for

        self._editors: dict[str, QWidget] = {}
        self._detached: dict[str, DetachedEditorWindow] = {}
        self._current_task = None

        self._build_ui()
        self.manager.taskSelected.connect(self._on_task_selected)

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.manager)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 6, 8, 8)
        head = QHBoxLayout()
        self.lbl_task = QLabel("未选择任务")
        self.lbl_task.setObjectName("detailTaskName")
        self.btn_popout = QPushButton("⧉ 浮出独立窗")
        self.btn_popout.setEnabled(False)
        self.btn_popout.clicked.connect(self.pop_out)
        head.addWidget(self.lbl_task, 1)
        head.addWidget(self.btn_popout)
        rv.addLayout(head)

        self.stack = QStackedWidget()
        self._placeholder = QLabel("选择左侧任务以编辑")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setObjectName("detailPlaceholder")
        self.stack.addWidget(self._placeholder)
        rv.addWidget(self.stack, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

    def _on_task_selected(self, task):
        if self._current_task is not None and self._current_task.id == task.id:
            return
        self._persist_current()
        self._current_task = task
        tid = task.id
        self.lbl_task.setText(getattr(task, "name", tid))
        if tid in self._detached:
            self.stack.setCurrentWidget(self._placeholder)
            self.btn_popout.setEnabled(False)
            return
        ed = self._ensure_editor(task)
        self.stack.setCurrentWidget(ed)
        self.btn_popout.setEnabled(True)

    def _ensure_editor(self, task):
        tid = task.id
        ed = self._editors.get(tid)
        if ed is None:
            ed = self._editor_factory(task)
            self._wire_editor(ed, task)
            self.stack.addWidget(ed)
            self._editors[tid] = ed
        return ed

    def _persist_current(self):
        t = self._current_task
        if t is None:
            return
        ed = self._editors.get(t.id)
        if ed is not None and t.id not in self._detached:
            self._on_persist(t.id, self._payload_of(ed))

    def pop_out(self):
        t = self._current_task
        if t is None or t.id in self._detached:
            return
        ed = self._editors.get(t.id)
        if ed is None:
            return
        self._persist_current()
        ed.setParent(None)
        win = DetachedEditorWindow(ed, self._title_for(t), t.id)
        win.closed.connect(self._dock_back)
        self._detached[t.id] = win
        self.stack.setCurrentWidget(self._placeholder)
        self.btn_popout.setEnabled(False)
        win.show()

    def _dock_back(self, task_id: str):
        win = self._detached.pop(task_id, None)
        ed = self._editors.get(task_id)
        if ed is not None:
            ed.setParent(None)
            self.stack.addWidget(ed)
            if self._current_task is not None and self._current_task.id == task_id:
                self.stack.setCurrentWidget(ed)
                self.btn_popout.setEnabled(True)
        if win is not None:
            win.deleteLater()

    def flush_all(self):
        """落盘所有缓存编辑器（含已浮出的——其 widget 仍存活可读）。"""
        for tid, ed in self._editors.items():
            self._on_persist(tid, self._payload_of(ed))

    def discard_editor(self, task_id: str):
        """任务被删时清理其缓存编辑器与浮出窗；若正显示它则切回占位。"""
        win = self._detached.pop(task_id, None)
        if win is not None:
            try:
                win.closed.disconnect(self._dock_back)
            except (RuntimeError, TypeError):
                pass
            win.close()
            win.deleteLater()
        ed = self._editors.pop(task_id, None)
        was_current = (self._current_task is not None
                       and self._current_task.id == task_id)
        if ed is not None:
            self.stack.removeWidget(ed)
            ed.deleteLater()
        if was_current:
            self._current_task = None
            self.lbl_task.setText("未选择任务")
            self.btn_popout.setEnabled(False)
            self.stack.setCurrentWidget(self._placeholder)
