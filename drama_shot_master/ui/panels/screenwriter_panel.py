"""ScreenwriterPanel：编剧 Wizard 面板（项目列表 + 4 阶段详情）。

沿用 video/imggen/soundtrack 面板的"viewport eventFilter + 名称列吃可见区
+ blank-click swallow"约定。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget, QLabel, QPlainTextEdit, QMessageBox, QInputDialog,
)

from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.theme import status_color


_STAGE_NAMES = ("创意", "剧本", "分镜", "提示词")


class ScreenwriterPanel(BasePanel):
    """编剧面板。"""

    statusMessage = Signal(str)

    def __init__(self, cfg, client, lifecycle, state=None, parent=None):
        # BasePanel.__init__ 需要 state 和 cfg；按其它面板的调用方式
        super().__init__(state, cfg, parent)
        self._client = client          # ScreenwriterClient
        self._lifecycle = lifecycle    # ScreenwriterLifecycle
        self._current_project: Path | None = None
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self):
        return False, "请通过列表管理编剧项目"

    def execute(self):
        raise NotImplementedError

    def _build_ui(self):
        root = QVBoxLayout(self)
        # 顶部按钮
        bar = QHBoxLayout()
        self.btn_new = QPushButton("新建")
        self.btn_open = QPushButton("打开项目目录…")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        # 项目列表（4 列）
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "最近输出", "更新时间"])
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 150)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        root.addWidget(self.table, 1)
        self.table.viewport().installEventFilter(self)

        # Wizard 区（4 阶段子面板）
        self.wizard = QStackedWidget()
        for name in _STAGE_NAMES:
            w = QWidget()
            v = QVBoxLayout(w)
            v.addWidget(QLabel(f"阶段：{name}（MVP 占位）"))
            edit = QPlainTextEdit()
            edit.setPlaceholderText(f"{name} 阶段产物预览/编辑（MVP 简版）")
            v.addWidget(edit, 1)
            row = QHBoxLayout()
            btn_gen = QPushButton(f"生成 {name}")
            btn_open = QPushButton("打开输出目录")
            row.addWidget(btn_gen)
            row.addWidget(btn_open)
            row.addStretch(1)
            v.addLayout(row)
            self.wizard.addWidget(w)
        root.addWidget(self.wizard, 1)

        # 绑定
        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_del.clicked.connect(self._on_del)
        self.table.itemSelectionChanged.connect(self._on_row_selected)

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport():
            if ev.type() == QEvent.Resize:
                self._fit_name_col()
            elif ev.type() == QEvent.MouseButtonPress:
                if not self.table.indexAt(ev.pos()).isValid():
                    return True
        return super().eventFilter(obj, ev)

    def _fit_name_col(self):
        vw = self.table.viewport().width()
        self.table.setColumnWidth(0, max(150, vw - self.table.columnWidth(1)))

    # ---- 项目管理（MVP：扫描 cfg.screenwriter_project_root）----

    def _project_root(self) -> Path:
        return Path(getattr(self.cfg, "screenwriter_project_root", "") or "")

    def refresh(self):
        self.table.setRowCount(0)
        root = self._project_root()
        if not root.is_dir():
            return
        for sub in sorted([p for p in root.iterdir() if p.is_dir()]):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(sub.name))
            # MVP：状态拉自 Agent /project；若 client 无 → 显示"未知"
            status_str = "未知"
            if self._client is not None:
                try:
                    st = self._client.scan_project(sub)
                    status_str = st.get("status", "未知")
                except Exception:
                    pass
            si = QTableWidgetItem(status_str)
            try:
                si.setForeground(QColor(status_color(status_str, self.cfg)))
            except Exception:
                pass
            self.table.setItem(r, 1, si)
            self.table.setItem(r, 2, QTableWidgetItem("—"))
            self.table.setItem(r, 3, QTableWidgetItem(""))
        self._fit_name_col()

    def _on_new(self):
        root = self._project_root()
        if not root.is_dir():
            QMessageBox.information(self, "未配置目录",
                                    "请在设置里指定编剧项目目录（screenwriter_project_root）")
            return
        name, ok = QInputDialog.getText(self, "新建编剧项目", "项目名:")
        if not ok or not name.strip():
            return
        new_dir = root / name.strip()
        try:
            new_dir.mkdir(exist_ok=False)
        except FileExistsError:
            QMessageBox.warning(self, "已存在", "项目名已存在")
            return
        self.refresh()

    def _on_open(self):
        d = QFileDialog.getExistingDirectory(self, "打开编剧项目目录")
        if not d:
            return
        if hasattr(self.cfg, "update_settings"):
            self.cfg.update_settings(screenwriter_project_root=d)
        else:
            self.cfg.screenwriter_project_root = d
        self.refresh()

    def _on_del(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r, 0).text()
        if QMessageBox.question(
                self, "删除", f"确定删除项目「{name}」（连同目录）？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        import shutil
        shutil.rmtree(self._project_root() / name, ignore_errors=True)
        self.refresh()

    def _on_row_selected(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r, 0).text()
        self._current_project = self._project_root() / name
        # 切到 recommended_next 对应的 wizard 页
        idx = 0
        if self._client is not None:
            try:
                st = self._client.scan_project(self._current_project)
                idx = {"ideate": 0, "script": 1,
                       "storyboard": 2, "prompts": 3}.get(
                    st.get("recommended_next", "ideate"), 0)
            except Exception:
                pass
        self.wizard.setCurrentIndex(idx)
