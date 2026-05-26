"""拆图面板：网格参数 + 白边/网格一键检测 + 可选重采样 + 批量拆。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QPushButton, QHBoxLayout, QMessageBox,
)

from drama_shot_master.imaging.border_detector import detect_borders, infer_grid
from drama_shot_master.imaging.saver import save_image as sm_save_image

from drama_shot_master.config import Config
from drama_shot_master.grid_ops import (
    make_grid_spec, split_to_tiles,
    ResampleAlgo, resize_tile, validate_resample_spec,
)
from drama_shot_master.providers.comfyui_upscaler import ComfyUIUpscaler
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.widgets.resample_group import ResampleGroup
from drama_shot_master.ui.worker import FunctionWorker


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class SplitPanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        root = QVBoxLayout(self)

        grid = QGroupBox("网格")
        gf = QFormLayout(grid)
        self.src_rows = _spin(1, 50, 2)
        self.src_cols = _spin(1, 50, 2)
        self.sub_rows = _spin(1, 50, 1)
        self.sub_cols = _spin(1, 50, 1)
        for w in (self.src_rows, self.src_cols, self.sub_rows, self.sub_cols):
            w.valueChanged.connect(self.validityChanged)
        gf.addRow("源图 行", self.src_rows)
        gf.addRow("源图 列", self.src_cols)
        gf.addRow("子图 行", self.sub_rows)
        gf.addRow("子图 列", self.sub_cols)
        root.addWidget(grid)

        mar = QGroupBox("白边 / 间距")
        mf = QFormLayout(mar)
        self.m_top = _spin(0, 9999, 0)
        self.m_right = _spin(0, 9999, 0)
        self.m_bottom = _spin(0, 9999, 0)
        self.m_left = _spin(0, 9999, 0)
        self.gap = _spin(0, 9999, 0)
        mf.addRow("上", self.m_top)
        mf.addRow("右", self.m_right)
        mf.addRow("下", self.m_bottom)
        mf.addRow("左", self.m_left)
        mf.addRow("间距", self.gap)
        det_row = QHBoxLayout()
        btn_border = QPushButton("检测白边")
        btn_border.clicked.connect(self._detect_borders)
        btn_grid = QPushButton("推断网格")
        btn_grid.clicked.connect(self._infer_grid)
        det_row.addWidget(btn_border)
        det_row.addWidget(btn_grid)
        mf.addRow(det_row)
        root.addWidget(mar)

        self.resample = ResampleGroup(
            list_models_fn=self._fetch_upscale_models,
            initial=self.cfg.split_resample_defaults,
        )
        self.resample.specChanged.connect(self.validityChanged)
        root.addWidget(self.resample)

        out = QGroupBox("输出")
        of = QFormLayout(out)
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        of.addRow("格式", self.fmt)
        root.addWidget(out)
        root.addStretch(1)

    def select_mode(self) -> str:
        return "multi"

    def _first_selected_image(self) -> Path | None:
        paths = self.state.selected_paths()
        return paths[0] if paths else None

    def _detect_borders(self):
        p = self._first_selected_image()
        if not p:
            QMessageBox.information(self, "检测白边", "请先在中间选一张图")
            return
        try:
            m, g = detect_borders(Image.open(p))
        except Exception as e:
            QMessageBox.warning(self, "检测失败", str(e))
            return
        self.m_top.setValue(m.top); self.m_right.setValue(m.right)
        self.m_bottom.setValue(m.bottom); self.m_left.setValue(m.left)
        self.gap.setValue(g)
        self.statusMessage.emit(
            f"白边 上{m.top} 右{m.right} 下{m.bottom} 左{m.left} 间距{g}")

    def _infer_grid(self):
        p = self._first_selected_image()
        if not p:
            QMessageBox.information(self, "推断网格", "请先在中间选一张图")
            return
        try:
            rows, cols = infer_grid(Image.open(p))
        except Exception as e:
            QMessageBox.warning(self, "推断失败", str(e))
            return
        self.src_rows.setValue(rows)
        self.src_cols.setValue(cols)
        self.statusMessage.emit(f"推断网格 {rows}×{cols}")

    def overlay_spec(self) -> dict:
        return dict(
            src_rows=self.src_rows.value(), src_cols=self.src_cols.value(),
            sub_rows=self.sub_rows.value(), sub_cols=self.sub_cols.value(),
            margin_top=self.m_top.value(), margin_right=self.m_right.value(),
            margin_bottom=self.m_bottom.value(), margin_left=self.m_left.value(),
            gap=self.gap.value(),
        )

    def validate(self) -> tuple[bool, str]:
        if not self.state.selected_paths():
            return False, "请先选图"
        if not self.state.output_dir:
            return False, "请先设置输出目录"
        sr, sc = self.src_rows.value(), self.src_cols.value()
        br, bc = self.sub_rows.value(), self.sub_cols.value()
        if sr % br != 0 or sc % bc != 0:
            return False, f"子图 {br}×{bc} 必须整除源图 {sr}×{sc}"
        # 重采样校验
        rspec = self.resample.get_spec()
        ok, msg = validate_resample_spec(rspec)
        if not ok:
            return False, msg
        # 自定义比例时强校验 w/h>0（validate_resample_spec 不做这层）
        if rspec.enabled and self.resample.aspect_combo.currentText() == "自定义":
            if rspec.aspect_w <= 0 or rspec.aspect_h <= 0:
                return False, "请填写自定义比例（w 和 h 都需 >0）"
        return True, ""

    def execute(self):
        paths = self.state.selected_paths()
        spec = make_grid_spec(
            self.src_rows.value(), self.src_cols.value(),
            self.sub_rows.value(), self.sub_cols.value(),
            self.m_top.value(), self.m_right.value(),
            self.m_bottom.value(), self.m_left.value(),
            self.gap.value(),
        )
        rspec = self.resample.get_spec()
        out_dir = self.state.output_dir
        fmt = self.fmt.currentText()
        ext = ".png" if fmt.upper() == "PNG" else ".jpg"

        # 持久化当前重采样默认值
        self.cfg.update_settings(
            split_resample_defaults=self.resample.to_dict())

        # AI 档才构造 upscaler
        upscaler = None
        if rspec.enabled and rspec.algorithm == ResampleAlgo.AI:
            upscaler = ComfyUIUpscaler(self.cfg.comfyui_url)

        status_emit = self.statusMessage.emit
        seen_statuses: set[str] = set()
        # 容器跨 closure 共享一个 per-tile 标志
        tile_state = {"fell_back": False}

        def dedupe_status(msg: str):
            tile_state["fell_back"] = True
            if msg not in seen_statuses:
                seen_statuses.add(msg)
                status_emit(msg)

        def task():
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                total = 0
                ai_total = 0
                ai_fallback = 0
                for src_path in paths:
                    tiles = split_to_tiles(src_path, spec)
                    for i, tile in enumerate(tiles):
                        if rspec.enabled and rspec.algorithm == ResampleAlgo.AI:
                            ai_total += 1
                            tile_state["fell_back"] = False
                            resized = resize_tile(
                                tile, rspec, upscaler=upscaler,
                                status_cb=dedupe_status)
                            if tile_state["fell_back"]:
                                ai_fallback += 1
                        else:
                            resized = resize_tile(tile, rspec)
                        out_path = out_dir / f"{src_path.stem}_{i+1}{ext}"
                        sm_save_image(resized, out_path, fmt)
                        total += 1
                return {"total": total, "ai_total": ai_total,
                        "ai_fallback": ai_fallback}
            finally:
                if upscaler is not None:
                    upscaler.close()

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "拆图失败", e))
        self._worker.start()

    def _fetch_upscale_models(self) -> list[str]:
        with ComfyUIUpscaler(self.cfg.comfyui_url) as up:
            return up.list_models()

    def _on_done(self, result):
        n = result["total"]
        ai_fb = result["ai_fallback"]
        ai_total = result["ai_total"]
        msg = f"已拆出 {n} 张"
        if ai_fb:
            msg += f"\n（其中 {ai_fb}/{ai_total} 张因超分失败回退 LANCZOS）"
        QMessageBox.information(self, "完成", msg)
