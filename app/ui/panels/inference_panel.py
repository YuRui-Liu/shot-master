"""反推面板：模板 + 补充输入 + 宫格防灾门禁 + 结果可编辑保存。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QComboBox, QSpinBox, QCheckBox,
    QPlainTextEdit, QPushButton, QHBoxLayout, QMessageBox, QApplication,
)

from app.config import Config
from app.core.output_writer import resolve_output_dir, write_outputs
from app.core.result_parser import parse_result, ParsedResult
from app.core.template_engine import (
    list_templates, render_template, recommend_template, Template,
)
from app.grid_ops import make_grid_spec, split_to_preview_cache
from app.providers import factory
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.widgets.template_form import TemplateFormWidget
from app.ui.worker import FunctionWorker

TEMPLATES_DIR = Path("templates")
PREVIEW_CACHE = Path("app/.cache/preview")


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class InferencePanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        self._templates: list[Template] = []
        self._result: Optional[ParsedResult] = None
        self._result_md: Optional[Path] = None
        self._result_meta: dict = {}

        root = QVBoxLayout(self)

        mode_box = QGroupBox("模式")
        mf = QFormLayout(mode_box)
        self.mode = QComboBox()
        self.mode.addItems(["单图", "多图", "宫格"])
        self.mode.currentTextChanged.connect(lambda _: self.validityChanged.emit())
        mf.addRow("反推模式", self.mode)
        root.addWidget(mode_box)

        self.grid_box = QGroupBox("宫格拆分")
        gf = QFormLayout(self.grid_box)
        self.g_sr = _spin(1, 50, 2)
        self.g_sc = _spin(1, 50, 2)
        self.g_br = _spin(1, 50, 1)
        self.g_bc = _spin(1, 50, 1)
        gf.addRow("源 行", self.g_sr)
        gf.addRow("源 列", self.g_sc)
        gf.addRow("子 行", self.g_br)
        gf.addRow("子 列", self.g_bc)
        self.confirm = QCheckBox("我确认拆图正确，可以送入反推")
        self.confirm.toggled.connect(lambda _: self.validityChanged.emit())
        gf.addRow(self.confirm)
        root.addWidget(self.grid_box)

        tpl_box = QGroupBox("模板")
        tf = QFormLayout(tpl_box)
        self.tpl = QComboBox()
        self.tpl.currentIndexChanged.connect(self._on_tpl_changed)
        tf.addRow("反推模板", self.tpl)
        root.addWidget(tpl_box)

        self.form = TemplateFormWidget()
        root.addWidget(self.form)

        self.result_box = QGroupBox("结果（可编辑后保存）")
        rf = QFormLayout(self.result_box)
        self.f_global = QPlainTextEdit(); self.f_global.setFixedHeight(50)
        self.f_timeline = QPlainTextEdit(); self.f_timeline.setFixedHeight(70)
        self.f_local = QPlainTextEdit(); self.f_local.setFixedHeight(50)
        self.f_struct = QPlainTextEdit(); self.f_struct.setFixedHeight(70)
        self.f_struct.setReadOnly(True)
        rf.addRow("global_prompt", self.f_global)
        rf.addRow("timeline_data", self.f_timeline)
        rf.addRow("local_prompts", self.f_local)
        rf.addRow("结构字段(只读)", self.f_struct)
        btns = QHBoxLayout()
        b_save = QPushButton("保存覆盖 md+json")
        b_save.clicked.connect(self._save_result)
        b_copy = QPushButton("复制 global_prompt")
        b_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self.f_global.toPlainText()))
        btns.addWidget(b_save); btns.addWidget(b_copy); btns.addStretch(1)
        rf.addRow(btns)
        self.result_box.setVisible(False)
        root.addWidget(self.result_box)
        root.addStretch(1)

        self._reload_templates()
        self.mode.currentTextChanged.connect(self._sync_grid_visible)
        self._sync_grid_visible()

    def _sync_grid_visible(self):
        self.grid_box.setVisible(self.mode.currentText() == "宫格")

    def _reload_templates(self):
        self._templates = list_templates(TEMPLATES_DIR)
        self.tpl.blockSignals(True)
        self.tpl.clear()
        for t in self._templates:
            self.tpl.addItem(f"{t.name} ({t.id})", t.id)
        self.tpl.blockSignals(False)
        self._on_tpl_changed()

    def _current_tpl(self) -> Optional[Template]:
        tid = self.tpl.currentData()
        return next((t for t in self._templates if t.id == tid), None)

    def _on_tpl_changed(self):
        t = self._current_tpl()
        if t:
            self.form.set_variables(t.variables)

    def select_mode(self) -> str:
        return "multi"

    def validate(self) -> tuple[bool, str]:
        if not self._current_tpl():
            return False, "请先选模板"
        sel = self.state.selected_paths()
        m = self.mode.currentText()
        if m == "宫格":
            if len(sel) != 1:
                return False, "宫格模式请只选 1 张"
            if not self.confirm.isChecked():
                return False, "请先勾选「我确认拆图正确」"
            return True, ""
        if m == "单图" and len(sel) != 1:
            return False, "请选 1 张图"
        if m == "多图" and not sel:
            return False, "请至少选 1 张图"
        return True, ""

    def execute(self):
        tpl = self._current_tpl()
        try:
            system_prompt = render_template(tpl, self.form.get_values())
        except ValueError as e:
            QMessageBox.warning(self, "模板字段缺失", str(e)); return

        sel = self.state.selected_paths()
        if self.mode.currentText() == "宫格":
            spec = make_grid_spec(self.g_sr.value(), self.g_sc.value(),
                                  self.g_br.value(), self.g_bc.value())
            images = split_to_preview_cache(sel[0], spec, PREVIEW_CACHE)
        else:
            images = sel

        cfg = self.cfg
        try:
            provider = factory.build_provider(
                cfg, cfg.current_provider, cfg.current_model)
        except Exception as e:
            QMessageBox.critical(self, "Provider 错误", str(e)); return
        out_dir = (self.state.output_dir
                   or resolve_output_dir(images[0], cfg.default_output_dir))
        base = images[0].stem
        tid = tpl.id

        def task():
            raw = provider.generate(images, system_prompt, "")
            parsed = parse_result(raw)
            md, js = write_outputs(
                result=parsed, output_dir=out_dir, base_name=base,
                template_id=tid, provider=cfg.current_provider,
                model=cfg.current_model)
            return parsed, md

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "反推失败", e))
        self._worker.start()

    def _on_done(self, payload):
        parsed, md = payload
        self._result = parsed
        self._result_md = md
        self._result_meta = {
            "template_id": self._current_tpl().id,
            "provider": self.cfg.current_provider,
            "model": self.cfg.current_model,
        }
        self.f_global.setPlainText(parsed.global_prompt)
        self.f_timeline.setPlainText(parsed.timeline_data)
        self.f_local.setPlainText(parsed.local_prompts)
        self.f_struct.setPlainText(json.dumps({
            "segment_lengths": parsed.segment_lengths,
            "max_frames": parsed.max_frames,
            "frame_indices": parsed.frame_indices,
            "strengths": parsed.strengths,
            "epsilon": parsed.epsilon,
        }, indent=2, ensure_ascii=False))
        self.result_box.setVisible(True)
        QMessageBox.information(self, "完成", f"已写入 {md}")

    def _save_result(self):
        if not self._result or not self._result_md:
            return
        self._result.global_prompt = self.f_global.toPlainText()
        self._result.timeline_data = self.f_timeline.toPlainText()
        self._result.local_prompts = self.f_local.toPlainText()
        try:
            write_outputs(
                result=self._result, output_dir=self._result_md.parent,
                base_name=self._result_md.stem,
                template_id=self._result_meta["template_id"],
                provider=self._result_meta["provider"],
                model=self._result_meta["model"])
            QMessageBox.information(self, "已保存", str(self._result_md))
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
