"""BatchToolPage：批处理功能（拆图/拼图/去白边）的主区页。

把现状 main_window 里「中栏 ThumbnailGrid + 右栏 BasePanel + 底部 预览/执行」
收拢为一个自包含页。BasePanel 的 validate/execute/select_mode/has_preview/
overlay_spec 契约保持不变；本页只负责布局与按钮联动。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QMessageBox,
)

from drama_shot_master.config import Config
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.thumbnail_grid import ThumbnailGrid
from drama_shot_master.ui.preview_dialog import PreviewDialog
from drama_shot_master.ui.theme import _tokens, current_theme


class BatchToolPage(QWidget):
    def __init__(self, panel: BasePanel, state: AppState, cfg: Config,
                 parent=None):
        super().__init__(parent)
        self.panel = panel
        self.state = state
        self.cfg = cfg

        self.thumb = ThumbnailGrid()
        self.thumb.set_mode(panel.select_mode())

        right = QVBoxLayout()
        right.addWidget(panel, 1)
        act = QHBoxLayout()
        self.btn_preview = QPushButton("预览")
        self.btn_exec = QPushButton("执行")
        self.btn_exec.setObjectName("AccentButton")
        self.exec_hint = QLabel("")
        _t = _tokens(current_theme(self.cfg))
        self.exec_hint.setStyleSheet(f"color:{_t['fg_muted']}")
        act.addWidget(self.btn_preview)
        act.addWidget(self.btn_exec)
        act.addWidget(self.exec_hint, 1)
        right.addLayout(act)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setMinimumWidth(340)
        right_w.setMaximumWidth(420)

        root = QHBoxLayout(self)
        root.addWidget(self.thumb, 1)
        root.addWidget(right_w)

        self.btn_preview.clicked.connect(self._do_preview)
        self.btn_exec.clicked.connect(self._do_execute)
        self.thumb.selectionChanged.connect(self._on_selection)
        self.thumb.previewRequested.connect(self._on_thumb_double)
        if hasattr(panel, "validityChanged"):
            panel.validityChanged.connect(self.refresh_validity)
        self.btn_preview.setVisible(panel.has_preview())
        self.refresh_validity()

    def populate(self, images):
        self.thumb.populate(images)
        self.refresh_validity()

    def selected_order(self) -> list[int]:
        return self.thumb.selected_order()

    def _on_selection(self, order):
        self.state.selected = list(order)
        self.refresh_validity()

    def refresh_validity(self):
        ok, why = self.panel.validate()
        self.btn_exec.setEnabled(ok)
        self.exec_hint.setText(why)

    def _do_preview(self):
        sel = self.state.selected_paths()
        if not sel:
            QMessageBox.information(self, "预览", "请先选一张图")
            return
        PreviewDialog(sel[0], overlay_spec=self.panel.overlay_spec(),
                      parent=self).exec()

    def _on_thumb_double(self, row: int):
        if not (0 <= row < len(self.state.images)):
            return
        path = self.state.images[row].path
        PreviewDialog(path, overlay_spec=self.panel.overlay_spec(),
                      parent=self).exec()

    def _do_execute(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            QMessageBox.warning(self, "需要激活", "请先在「关于」中激活。")
            return
        ok, why = self.panel.validate()
        if not ok:
            QMessageBox.warning(self, "无法执行", why)
            return
        self.panel.execute()
