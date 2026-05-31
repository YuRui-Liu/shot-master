"""项目管理 section：列出最近项目，支持「仅移除显示」与「删除文件夹」。

避免最近项目无限堆叠。删文件夹不可逆，按钮处先 QMessageBox 二次确认；
remove_from_list / delete_folder 为纯逻辑入口（无弹窗），便于测试与复用。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QMessageBox,
)


class ProjectManagementSection(QWidget):
    title = "项目管理"
    category = "应用"

    def __init__(self, cfg, parent=None, recent_mgr=None):
        super().__init__(parent)
        self._cfg = cfg
        self._mgr = recent_mgr or self._make_mgr(cfg)
        self._build_ui()
        self._reload()

    @staticmethod
    def _make_mgr(cfg):
        from drama_shot_master.core.recent_projects import RecentProjectsManager
        sp = getattr(cfg, "settings_path", "") or "settings.json"
        return RecentProjectsManager.alongside_settings(Path(sp))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("最近项目（避免无限堆叠：可仅移除显示，或彻底删除文件夹）"))
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._list = QWidget()
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(6)
        self._scroll.setWidget(self._list)
        root.addWidget(self._scroll, 1)
        self._empty = QLabel("（暂无最近项目）")
        self._empty.setStyleSheet("color:#9aa0a6;")
        root.addWidget(self._empty)

    def _reload(self):
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        records = self._mgr.load()
        for rec in records:
            self._list_lay.addWidget(self._make_row(rec))
        self._list_lay.addStretch(1)
        self._empty.setVisible(not records)

    def _make_row(self, rec: dict) -> QWidget:
        path = rec.get("path", "")
        name = rec.get("name") or Path(path).name
        row = QFrame()
        row.setObjectName("ProjectRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 6, 8, 6)
        col = QVBoxLayout()
        lbl_name = QLabel(name)
        lbl_path = QLabel(path)
        lbl_path.setStyleSheet("color:#9aa0a6;font-size:11px;")
        col.addWidget(lbl_name)
        col.addWidget(lbl_path)
        h.addLayout(col, 1)
        b_remove = QPushButton("仅移除显示")
        b_remove.clicked.connect(lambda: self.remove_from_list(path))
        b_delete = QPushButton("删除文件夹")
        b_delete.setObjectName("DangerBtn")
        b_delete.clicked.connect(lambda: self._on_delete_clicked(path, name))
        h.addWidget(b_remove)
        h.addWidget(b_delete)
        return row

    # ── 纯逻辑入口（无弹窗，便于测试/复用）──
    def remove_from_list(self, path: str):
        self._mgr.remove(path)
        self._reload()

    def delete_folder(self, path: str):
        shutil.rmtree(path, ignore_errors=True)
        self._mgr.remove(path)
        self._reload()

    def _on_delete_clicked(self, path: str, name: str):
        ans = QMessageBox.warning(
            self, "删除项目文件夹",
            f"将永久删除「{name}」的整个文件夹：\n{path}\n\n此操作不可恢复，确定？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            self.delete_folder(path)

    def load_from(self, cfg):
        self._reload()

    def save_to(self, cfg):
        pass            # 操作即时生效，无需延迟保存

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
