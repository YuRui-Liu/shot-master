"""拼图 Tab：N 张图按点击顺序拼成 R×C 网格。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QSpinBox, QComboBox, QFileDialog, QMessageBox, QFormLayout, QGroupBox,
)

from app.config import Config
from app.grid_ops import combine_to_file
from app.ui.widgets.thumbnail_list import ThumbnailListWidget


class CombineTab(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        root = QVBoxLayout(self)

        # 文件夹
        box = QGroupBox("拼图：N 张图 → R×C 网格")
        form = QFormLayout(box)
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        btn_fold = QPushButton("浏览…")
        btn_fold.clicked.connect(self._pick_folder)
        btn_load = QPushButton("载入")
        btn_load.clicked.connect(self._load)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(btn_fold)
        folder_row.addWidget(btn_load)
        form.addRow("文件夹", folder_row)

        grid_row = QHBoxLayout()
        self.tr = QSpinBox(); self.tr.setRange(1, 20); self.tr.setValue(2)
        self.tc = QSpinBox(); self.tc.setRange(1, 20); self.tc.setValue(2)
        self.gap = QSpinBox(); self.gap.setRange(0, 200); self.gap.setValue(4)
        self.scale = QComboBox(); self.scale.addItems(["letterbox", "crop", "stretch"])
        for w in (QLabel("目标:"), self.tr, QLabel("×"), self.tc,
                  QLabel(" 间距:"), self.gap, QLabel(" 缩放:"), self.scale):
            grid_row.addWidget(w)
        grid_row.addStretch(1)
        form.addRow("网格", grid_row)

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        btn_out = QPushButton("保存为…")
        btn_out.clicked.connect(self._pick_out)
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(btn_out)
        out_row.addWidget(self.fmt)
        form.addRow("输出", out_row)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("💾 拼接")
        self.btn_run.clicked.connect(self._run)
        self.btn_clear = QPushButton("清空顺序")
        self.btn_clear.clicked.connect(lambda: self.thumb_list.clear_order())
        self.count_label = QLabel("0 / 0 张")
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_clear)
        btn_row.addWidget(self.count_label)
        btn_row.addStretch(1)
        form.addRow("", btn_row)
        root.addWidget(box)

        # 缩略图（按点击顺序选）
        self.thumb_list = ThumbnailListWidget(mode="order", thumb_size=120)
        self.thumb_list.selection_changed.connect(self._on_sel_changed)
        root.addWidget(self.thumb_list, 1)

        self.result_label = QLabel("")
        root.addWidget(self.result_label)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹",
                                             self.folder_edit.text() or str(Path.home()))
        if d:
            self.folder_edit.setText(d)
            self._load()

    def _pick_out(self):
        d = QFileDialog.getSaveFileName(self, "保存为", self.out_edit.text() or "merged.png",
                                        "Images (*.png *.jpg)")
        if d[0]:
            self.out_edit.setText(d[0])

    def _load(self):
        p = Path(self.folder_edit.text().strip())
        if not p.is_dir():
            QMessageBox.warning(self, "提示", "无效文件夹")
            return
        self.thumb_list.load_folder(p)

    def _on_sel_changed(self, paths):
        total = self.tr.value() * self.tc.value()
        self.count_label.setText(f"{len(paths)} / {total} 张")

    def _run(self):
        sel = self.thumb_list.selected_paths()
        total = self.tr.value() * self.tc.value()
        if len(sel) != total:
            QMessageBox.warning(self, "数量不对",
                                f"目标 {self.tr.value()}×{self.tc.value()}={total}，但只选了 {len(sel)} 张")
            return
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "提示", "请填输出路径")
            return
        try:
            combine_to_file(
                sel, Path(out),
                target_rows=self.tr.value(), target_cols=self.tc.value(),
                gap=self.gap.value(),
                scale_mode=self.scale.currentText(),
                output_format=self.fmt.currentText(),
            )
        except Exception as e:
            QMessageBox.critical(self, "拼图失败", str(e))
            return
        self.result_label.setText(f"✅ 已生成: {out}")
