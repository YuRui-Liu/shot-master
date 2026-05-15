"""去白边 Tab：单图或批量。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QSpinBox, QComboBox, QFileDialog, QMessageBox, QFormLayout, QGroupBox,
    QRadioButton, QButtonGroup, QStackedWidget,
)

from app.config import Config
from app.grid_ops import trim_one, trim_batch


class TrimTab(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        root = QVBoxLayout(self)

        # 模式
        mode_row = QHBoxLayout()
        self.rb_single = QRadioButton("单图")
        self.rb_batch = QRadioButton("批量")
        self.rb_single.setChecked(True)
        self.bg = QButtonGroup(self)
        self.bg.addButton(self.rb_single, 0)
        self.bg.addButton(self.rb_batch, 1)
        self.bg.idClicked.connect(self._on_mode)
        mode_row.addWidget(QLabel("模式:"))
        mode_row.addWidget(self.rb_single)
        mode_row.addWidget(self.rb_batch)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        # 堆叠：单图 / 批量
        self.stack = QStackedWidget()
        # 单图
        single_box = QGroupBox("单图")
        sf = QFormLayout(single_box)
        src_row = QHBoxLayout()
        self.s_src = QLineEdit()
        btn_ss = QPushButton("选择…")
        btn_ss.clicked.connect(self._pick_single_src)
        src_row.addWidget(self.s_src, 1); src_row.addWidget(btn_ss)
        sf.addRow("源图", src_row)
        out_row = QHBoxLayout()
        self.s_out = QLineEdit()
        btn_so = QPushButton("保存为…")
        btn_so.clicked.connect(self._pick_single_out)
        out_row.addWidget(self.s_out, 1); out_row.addWidget(btn_so)
        sf.addRow("输出", out_row)
        self.stack.addWidget(single_box)
        # 批量
        batch_box = QGroupBox("批量")
        bf = QFormLayout(batch_box)
        bsrc = QHBoxLayout()
        self.b_src = QLineEdit()
        btn_bs = QPushButton("选择目录…")
        btn_bs.clicked.connect(self._pick_batch_src)
        bsrc.addWidget(self.b_src, 1); bsrc.addWidget(btn_bs)
        bf.addRow("源目录", bsrc)
        bout = QHBoxLayout()
        self.b_out = QLineEdit()
        btn_bo = QPushButton("选择目录…")
        btn_bo.clicked.connect(self._pick_batch_out)
        bout.addWidget(self.b_out, 1); bout.addWidget(btn_bo)
        bf.addRow("输出目录", bout)
        self.b_suffix = QLineEdit("_trim")
        bf.addRow("命名后缀", self.b_suffix)
        self.stack.addWidget(batch_box)
        root.addWidget(self.stack)

        # 参数
        para_box = QGroupBox("参数")
        pf = QFormLayout(para_box)
        self.thresh = QSpinBox(); self.thresh.setRange(0, 255); self.thresh.setValue(240)
        self.iter = QSpinBox(); self.iter.setRange(1, 20); self.iter.setValue(5)
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        pf.addRow("阈值", self.thresh)
        pf.addRow("迭代", self.iter)
        pf.addRow("格式", self.fmt)
        root.addWidget(para_box)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("💾 执行")
        self.btn_run.clicked.connect(self._run)
        btn_row.addWidget(self.btn_run)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)
        root.addStretch(1)

    def _on_mode(self, idx):
        self.stack.setCurrentIndex(idx)

    def _pick_single_src(self):
        d = QFileDialog.getOpenFileName(self, "源图", self.s_src.text() or str(Path.home()),
                                        "Images (*.png *.jpg *.jpeg *.webp)")
        if d[0]: self.s_src.setText(d[0])

    def _pick_single_out(self):
        d = QFileDialog.getSaveFileName(self, "保存为", self.s_out.text() or "trimmed.png",
                                        "Images (*.png *.jpg)")
        if d[0]: self.s_out.setText(d[0])

    def _pick_batch_src(self):
        d = QFileDialog.getExistingDirectory(self, "源目录", self.b_src.text() or str(Path.home()))
        if d: self.b_src.setText(d)

    def _pick_batch_out(self):
        d = QFileDialog.getExistingDirectory(self, "输出目录", self.b_out.text() or str(Path.home()))
        if d: self.b_out.setText(d)

    def _run(self):
        try:
            if self.stack.currentIndex() == 0:
                trim_one(Path(self.s_src.text().strip()),
                         Path(self.s_out.text().strip()),
                         threshold=self.thresh.value(),
                         max_iter=self.iter.value(),
                         output_format=self.fmt.currentText())
                self.result_label.setText(f"✅ 已保存 {self.s_out.text().strip()}")
            else:
                files = trim_batch(
                    Path(self.b_src.text().strip()),
                    Path(self.b_out.text().strip()),
                    threshold=self.thresh.value(),
                    max_iter=self.iter.value(),
                    output_format=self.fmt.currentText(),
                    name_suffix=self.b_suffix.text(),
                )
                self.result_label.setText(f"✅ 已保存 {len(files)} 张")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))
