"""拆图 Tab：网格 → 子网格切分并落盘。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QSpinBox, QComboBox, QFileDialog, QMessageBox, QFormLayout, QGroupBox,
)

from app.config import Config
from app.grid_ops import make_grid_spec, split_to_files, split_to_preview_cache
from app.ui.widgets.thumbnail_list import ThumbnailListWidget


PREVIEW_CACHE = Path("app/.cache/preview_split")


class SplitTab(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        root = QVBoxLayout(self)

        box = QGroupBox("拆图")
        form = QFormLayout(box)
        # 源图
        src_row = QHBoxLayout()
        self.src_edit = QLineEdit()
        btn_src = QPushButton("选择文件…")
        btn_src.clicked.connect(self._pick_src)
        src_row.addWidget(self.src_edit, 1)
        src_row.addWidget(btn_src)
        form.addRow("源图路径", src_row)
        # 网格
        grid_row = QHBoxLayout()
        self.src_rows = QSpinBox(); self.src_rows.setRange(1, 20); self.src_rows.setValue(2)
        self.src_cols = QSpinBox(); self.src_cols.setRange(1, 20); self.src_cols.setValue(2)
        self.sub_rows = QSpinBox(); self.sub_rows.setRange(1, 20); self.sub_rows.setValue(1)
        self.sub_cols = QSpinBox(); self.sub_cols.setRange(1, 20); self.sub_cols.setValue(1)
        for w in (QLabel("源:"), self.src_rows, QLabel("×"), self.src_cols,
                  QLabel("  子:"), self.sub_rows, QLabel("×"), self.sub_cols):
            grid_row.addWidget(w)
        grid_row.addStretch(1)
        form.addRow("网格", grid_row)
        # 输出目录
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        btn_out = QPushButton("选择目录…")
        btn_out.clicked.connect(self._pick_out)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(btn_out)
        form.addRow("输出目录", out_row)
        # 命名前缀 / 格式
        misc_row = QHBoxLayout()
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("默认 = 源图文件名")
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["PNG", "JPG"])
        misc_row.addWidget(QLabel("前缀:"))
        misc_row.addWidget(self.prefix_edit, 1)
        misc_row.addWidget(QLabel("格式:"))
        misc_row.addWidget(self.fmt_combo)
        form.addRow("", misc_row)
        # 按钮
        btn_row = QHBoxLayout()
        btn_preview = QPushButton("▶ 预览")
        btn_preview.clicked.connect(self._preview)
        btn_run = QPushButton("💾 拆分并落盘")
        btn_run.clicked.connect(self._run)
        btn_row.addWidget(btn_preview)
        btn_row.addWidget(btn_run)
        btn_row.addStretch(1)
        form.addRow("", btn_row)
        root.addWidget(box)

        # 预览结果
        self.preview_view = ThumbnailListWidget(mode="multi", thumb_size=100)
        self.preview_view.setMaximumHeight(300)
        root.addWidget(self.preview_view, 1)
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)

    def _pick_src(self):
        d = QFileDialog.getOpenFileName(self, "选择源图",
                                        self.src_edit.text() or str(Path.home()),
                                        "Images (*.png *.jpg *.jpeg *.webp)")
        if d[0]:
            self.src_edit.setText(d[0])

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "输出目录",
                                             self.out_edit.text() or str(Path.home()))
        if d:
            self.out_edit.setText(d)

    def _spec(self):
        return make_grid_spec(self.src_rows.value(), self.src_cols.value(),
                              self.sub_rows.value(), self.sub_cols.value())

    def _preview(self):
        src = self.src_edit.text().strip()
        if not src:
            QMessageBox.warning(self, "提示", "请先选源图")
            return
        try:
            tiles = split_to_preview_cache(Path(src), self._spec(), PREVIEW_CACHE)
        except Exception as e:
            QMessageBox.critical(self, "拆图失败", str(e))
            return
        from PySide6.QtGui import QPixmap, QIcon
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QListWidgetItem
        self.preview_view.clear()
        for p in tiles:
            pix = QPixmap(str(p)).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            it = QListWidgetItem(QIcon(pix), p.name)
            it.setData(Qt.UserRole, str(p))
            it.setSizeHint(QSize(124, 140))
            self.preview_view.addItem(it)
        self.result_label.setText(f"预览 {len(tiles)} 个子图")

    def _run(self):
        src = self.src_edit.text().strip()
        out = self.out_edit.text().strip()
        if not src or not out:
            QMessageBox.warning(self, "提示", "请填源图和输出目录")
            return
        try:
            files = split_to_files(
                Path(src), self._spec(), Path(out),
                name_prefix=self.prefix_edit.text().strip() or None,
                output_format=self.fmt_combo.currentText(),
            )
        except Exception as e:
            QMessageBox.critical(self, "拆图失败", str(e))
            return
        self.result_label.setText(f"✅ 已保存 {len(files)} 张到 {out}")
