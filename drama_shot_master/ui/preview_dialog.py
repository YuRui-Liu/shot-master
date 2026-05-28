"""大图预览对话框。overlay=split spec 时叠加红线网格。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel

from drama_shot_master.ui.geometry import compute_grid_lines, tile_count
from drama_shot_master.ui.theme import _tokens, current_theme


class PreviewDialog(QDialog):
    def __init__(self, image_path: Path,
                 overlay_spec: Optional[dict] = None,
                 parent=None):
        """overlay_spec: None=普通预览；dict 含
        src_rows/src_cols/sub_rows/sub_cols/margin_top/right/bottom/left/gap
        """
        super().__init__(parent)
        self.setWindowTitle(f"预览 · {image_path.name}")
        self.resize(900, 760)
        self._path = image_path
        self._spec = overlay_spec

        layout = QVBoxLayout(self)
        self.hint = QLabel("")
        self.hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.hint)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.canvas, 1)

        self._render()

    def _render(self):
        pix = QPixmap(str(self._path))
        if pix.isNull():
            self.hint.setText("无法加载图片")
            return
        max_w, max_h = 860, 680
        disp = pix.scaled(max_w, max_h, Qt.KeepAspectRatio,
                          Qt.SmoothTransformation)

        if not self._spec:
            self.hint.setText(f"{pix.width()} × {pix.height()}")
            self.canvas.setPixmap(disp)
            return

        s = self._spec
        try:
            n = tile_count(s["src_rows"], s["src_cols"],
                           s["sub_rows"], s["sub_cols"])
        except ValueError as e:
            self.hint.setText(f"⚠ {e}")
            _t = _tokens(current_theme(None))
            self.hint.setStyleSheet(f"color:{_t['status_failed']};font-weight:bold")
            self.canvas.setPixmap(disp)
            return
        self.hint.setStyleSheet("")
        self.hint.setText(
            f"源 {s['src_rows']}×{s['src_cols']} → "
            f"子 {s['sub_rows']}×{s['sub_cols']} = 将切出 {n} 张")

        lines = compute_grid_lines(
            img_w=pix.width(), img_h=pix.height(),
            src_rows=s["src_rows"], src_cols=s["src_cols"],
            sub_rows=s["sub_rows"], sub_cols=s["sub_cols"],
            margin_top=s["margin_top"], margin_right=s["margin_right"],
            margin_bottom=s["margin_bottom"], margin_left=s["margin_left"],
            gap=s["gap"],
            display_w=disp.width(), display_h=disp.height(),
        )
        canvas = QPixmap(disp)
        _t = _tokens(current_theme(None))
        p = QPainter(canvas)
        for ln in lines:
            pen = QPen(QColor(_t["status_failed"]))
            if ln.style == "dashed":
                pen.setStyle(Qt.DashLine)
                pen.setWidth(1)
            else:
                pen.setWidth(2)
            p.setPen(pen)
            if ln.orientation == "v":
                p.drawLine(int(ln.pos), 0, int(ln.pos), canvas.height())
            else:
                p.drawLine(0, int(ln.pos), canvas.width(), int(ln.pos))
        p.end()
        self.canvas.setPixmap(canvas)
