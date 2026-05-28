"""任务中心抽屉：跨 4 个生成功能的只读总览 + 跳转。
右侧 QDockWidget，默认隐藏；3 组 QListWidget（生成中 / 失败 / 最近完成）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox,
)


_KIND_LABELS = {"video": "视频", "imggen": "出图",
                "dub": "配音", "soundtrack": "配乐"}


class TaskCenterDock(QDockWidget):
    taskActivated = Signal(str, str)         # (kind, task_id)

    def __init__(self, aggregator, parent=None):
        super().__init__("任务中心", parent)
        self.setAllowedAreas(Qt.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self._agg = aggregator
        self._recent_complete_limit = 20
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        w = QWidget()
        v = QVBoxLayout(w)
        # 顶 toolbar
        tb = QHBoxLayout()
        self.lbl_counts = QLabel("")
        tb.addWidget(self.lbl_counts, 1)
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setFlat(True)
        self.btn_refresh.setToolTip("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        tb.addWidget(self.btn_refresh)
        v.addLayout(tb)
        # 3 个分组
        self.list_running = QListWidget()
        self.list_failed = QListWidget()
        self.list_done = QListWidget()
        for grp_title, lst in (("生成中", self.list_running),
                                ("失败",   self.list_failed),
                                ("最近完成", self.list_done)):
            box = QGroupBox(grp_title)
            bv = QVBoxLayout(box)
            bv.addWidget(lst)
            lst.itemDoubleClicked.connect(self._on_double_click)
            v.addWidget(box)
        self.setWidget(w)

    def refresh(self):
        records = self._agg.snapshot()
        running = [r for r in records if r.status == "生成中"]
        failed = [r for r in records if r.status == "失败"]
        done = [r for r in records if r.status == "完成" and r.last_result]
        done = self._sort_recent(done)[: self._recent_complete_limit]
        self._fill(self.list_running, running)
        self._fill(self.list_failed, failed)
        self._fill(self.list_done, done)
        self.lbl_counts.setText(
            f"生成中 {len(running)} · 失败 {len(failed)} · 完成 {len(done)}")

    def _fill(self, lst: QListWidget, records: list):
        lst.clear()
        for r in records:
            it = QListWidgetItem(self._row_text(r))
            it.setData(Qt.UserRole, (r.kind, r.task_id))
            lst.addItem(it)

    def _row_text(self, r) -> str:
        suffix = (" · " + Path(r.last_result).name) if r.last_result else ""
        kind_lbl = _KIND_LABELS.get(r.kind, r.kind)
        return f"[{kind_lbl}] {r.name}{suffix}"

    def _on_double_click(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        kind, tid = data
        self.taskActivated.emit(kind, tid)

    def _sort_recent(self, records: list) -> list:
        """按 last_result 文件 mtime 倒序；不可读则按原序。"""
        def key(r):
            try:
                return -Path(r.last_result).stat().st_mtime
            except Exception:
                return 0
        return sorted(records, key=key)
