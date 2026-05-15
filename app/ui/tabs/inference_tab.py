"""反推 Tab：4 种输入模式 + 防灾门禁 + 结果可编辑保存 + 批量进度。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QRadioButton,
    QButtonGroup, QFileDialog, QGroupBox, QSpinBox, QComboBox, QCheckBox,
    QTextEdit, QFormLayout, QPlainTextEdit, QSplitter, QMessageBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
)

from app.config import Config
from app.core.output_writer import resolve_output_dir, write_outputs
from app.core.result_parser import parse_result, ParsedResult
from app.core.template_engine import (
    list_templates, render_template, recommend_template, Template,
)
from app.grid_ops import make_grid_spec, split_to_preview_cache
from app.providers import factory
from app.ui.widgets.thumbnail_list import ThumbnailListWidget
from app.ui.widgets.template_form import TemplateFormWidget
from app.ui.worker import FunctionWorker, BatchWorker


TEMPLATES_DIR = Path("templates")
PREVIEW_CACHE = Path("app/.cache/preview")


class InferenceTab(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._templates: list[Template] = []
        self._tile_paths: list[Path] = []
        self._split_confirmed = False
        self._result: Optional[ParsedResult] = None
        self._result_md: Optional[Path] = None
        self._result_json: Optional[Path] = None
        self._result_meta: dict = {}
        self._worker: Optional[FunctionWorker] = None
        self._batch_worker: Optional[BatchWorker] = None

        root = QVBoxLayout(self)

        # === 1. 输入模式 ===
        mode_box = QGroupBox("1. 输入模式")
        mh = QHBoxLayout(mode_box)
        self.mode_group = QButtonGroup(self)
        for label, key in [("拼接宫格图", "grid"),
                           ("多张独立图", "multi"),
                           ("单张图", "single"),
                           ("文件夹批量", "batch")]:
            rb = QRadioButton(label)
            rb.setProperty("mode_key", key)
            self.mode_group.addButton(rb)
            mh.addWidget(rb)
            if key == "multi":
                rb.setChecked(True)
        self.mode_group.buttonToggled.connect(self._on_mode_changed)
        root.addWidget(mode_box)

        # === 2. 选图 ===
        sel_box = QGroupBox("2. 选图")
        sv = QVBoxLayout(sel_box)
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("文件夹路径")
        btn_browse = QPushButton("浏览…")
        btn_browse.clicked.connect(self._browse_folder)
        btn_load = QPushButton("载入")
        btn_load.clicked.connect(self._load_folder)
        folder_row.addWidget(QLabel("文件夹:"))
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(btn_browse)
        folder_row.addWidget(btn_load)
        sv.addLayout(folder_row)
        self.thumb_list = ThumbnailListWidget(mode="multi", thumb_size=140)
        self.thumb_list.selection_changed.connect(self._on_selection_changed)
        sv.addWidget(self.thumb_list, 1)
        root.addWidget(sel_box, 2)

        # === 3. 拆图预览（仅宫格模式） ===
        self.split_box = QGroupBox("3. 拆图预览（必须人工确认）")
        sb = QVBoxLayout(self.split_box)
        grid_row = QHBoxLayout()
        self.src_rows = QSpinBox(); self.src_rows.setRange(1, 10); self.src_rows.setValue(2)
        self.src_cols = QSpinBox(); self.src_cols.setRange(1, 10); self.src_cols.setValue(2)
        self.sub_rows = QSpinBox(); self.sub_rows.setRange(1, 10); self.sub_rows.setValue(1)
        self.sub_cols = QSpinBox(); self.sub_cols.setRange(1, 10); self.sub_cols.setValue(1)
        for w in (QLabel("源:"), self.src_rows, QLabel("×"), self.src_cols,
                  QLabel(" 子:"), self.sub_rows, QLabel("×"), self.sub_cols):
            grid_row.addWidget(w)
        btn_preview = QPushButton("▶ 预览拆图")
        btn_preview.clicked.connect(self._preview_split)
        grid_row.addWidget(btn_preview)
        grid_row.addStretch(1)
        sb.addLayout(grid_row)
        self.tiles_view = ThumbnailListWidget(mode="multi", thumb_size=100)
        self.tiles_view.setMaximumHeight(180)
        sb.addWidget(self.tiles_view)
        self.confirm_check = QCheckBox("我确认拆图正确，可以送入反推")
        self.confirm_check.toggled.connect(self._on_confirm_toggled)
        sb.addWidget(self.confirm_check)
        self.split_box.setVisible(False)
        root.addWidget(self.split_box)

        # === 4. 模板 ===
        tpl_box = QGroupBox("4. 反推模板")
        th = QHBoxLayout(tpl_box)
        self.tpl_combo = QComboBox()
        self.tpl_combo.currentIndexChanged.connect(self._on_template_changed)
        self.recommend_label = QLabel("")
        self.recommend_label.setStyleSheet("color:#888")
        th.addWidget(QLabel("模板:"))
        th.addWidget(self.tpl_combo, 1)
        th.addWidget(self.recommend_label)
        root.addWidget(tpl_box)

        # === 5. 补充输入 ===
        sup_box = QGroupBox("5. 补充输入")
        sv2 = QVBoxLayout(sup_box)
        self.form_widget = TemplateFormWidget()
        sv2.addWidget(self.form_widget)
        # 批量复用策略
        self.per_image_check = QCheckBox("批量模式：按文件名规则逐项映射（同名 .md/.json/.txt 自动注入）")
        self.per_image_check.setVisible(False)
        sv2.addWidget(self.per_image_check)
        root.addWidget(sup_box)

        # === 6. 执行 + 结果 ===
        run_row = QHBoxLayout()
        self.btn_run = QPushButton("🚀 开始反推")
        self.btn_run.clicked.connect(self._run)
        self.run_hint = QLabel("")
        self.run_hint.setStyleSheet("color:#888")
        run_row.addWidget(self.btn_run)
        run_row.addWidget(self.run_hint, 1)
        root.addLayout(run_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        # 批量结果表
        self.batch_table = QTableWidget(0, 3)
        self.batch_table.setHorizontalHeaderLabels(["#", "文件", "状态"])
        self.batch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.batch_table.setVisible(False)
        root.addWidget(self.batch_table, 1)

        # 单图结果（可编辑）
        self.result_box = QGroupBox("结果（可编辑后重保存）")
        rv = QFormLayout(self.result_box)
        self.field_global = QPlainTextEdit(); self.field_global.setFixedHeight(60)
        self.field_timeline = QPlainTextEdit(); self.field_timeline.setFixedHeight(80)
        self.field_locals = QPlainTextEdit(); self.field_locals.setFixedHeight(60)
        self.field_notes = QPlainTextEdit(); self.field_notes.setFixedHeight(60)
        self.field_struct = QPlainTextEdit(); self.field_struct.setFixedHeight(80)
        rv.addRow("global_prompt", self.field_global)
        rv.addRow("timeline_data", self.field_timeline)
        rv.addRow("local_prompts", self.field_locals)
        rv.addRow("结构字段(只读)", self.field_struct)
        self.field_struct.setReadOnly(True)
        rv.addRow("notes", self.field_notes)
        save_row = QHBoxLayout()
        btn_save = QPushButton("💾 保存覆盖 md+json")
        btn_save.clicked.connect(self._save_result)
        btn_copy_gp = QPushButton("复制 global_prompt")
        btn_copy_gp.clicked.connect(lambda: self._copy(self.field_global.toPlainText()))
        btn_copy_local = QPushButton("复制 local_prompts")
        btn_copy_local.clicked.connect(lambda: self._copy(self.field_locals.toPlainText()))
        save_row.addWidget(btn_save)
        save_row.addWidget(btn_copy_gp)
        save_row.addWidget(btn_copy_local)
        save_row.addStretch(1)
        rv.addRow(save_row)
        self.result_box.setVisible(False)
        root.addWidget(self.result_box, 1)

        self._reload_templates()
        self._update_run_state()

    # ---------------- 辅助 ----------------

    @property
    def mode(self) -> str:
        btn = self.mode_group.checkedButton()
        return btn.property("mode_key") if btn else "multi"

    def _on_mode_changed(self):
        m = self.mode
        self.split_box.setVisible(m == "grid")
        self.per_image_check.setVisible(m == "batch")
        if m == "grid":
            self.thumb_list._mode = "single"
        elif m == "multi":
            self.thumb_list._mode = "multi"
        elif m == "single":
            self.thumb_list._mode = "single"
        else:  # batch
            self.thumb_list._mode = "single"
        self._tile_paths = []
        self._split_confirmed = False
        self.confirm_check.setChecked(False)
        self.tiles_view.clear()
        self._auto_recommend()
        self._update_run_state()

    def _on_selection_changed(self, paths):
        self._auto_recommend()
        self._update_run_state()

    def _on_confirm_toggled(self, checked):
        self._split_confirmed = checked
        self._update_run_state()

    def _browse_folder(self):
        cur = self.folder_edit.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "选择文件夹", cur)
        if d:
            self.folder_edit.setText(d)
            self._load_folder()

    def _load_folder(self):
        p = Path(self.folder_edit.text().strip())
        if not p.is_dir():
            QMessageBox.warning(self, "提示", f"文件夹不存在: {p}")
            return
        self.thumb_list.load_folder(p)

    def _copy(self, text: str):
        from PySide6.QtGui import QClipboard
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    # ---------------- 模板 ----------------

    def _reload_templates(self):
        self._templates = list_templates(TEMPLATES_DIR)
        self.tpl_combo.blockSignals(True)
        self.tpl_combo.clear()
        for t in self._templates:
            self.tpl_combo.addItem(f"{t.name}  ({t.id})", t.id)
        self.tpl_combo.blockSignals(False)
        self._on_template_changed()

    def _current_template(self) -> Optional[Template]:
        tpl_id = self.tpl_combo.currentData()
        return next((t for t in self._templates if t.id == tpl_id), None)

    def _on_template_changed(self):
        tpl = self._current_template()
        if tpl:
            self.form_widget.set_variables(tpl.variables)

    def _auto_recommend(self):
        if self.mode == "grid":
            count = (self.src_rows.value() // self.sub_rows.value()) * (
                self.src_cols.value() // self.sub_cols.value())
        else:
            count = max(1, len(self.thumb_list.selected_paths()))
        rec = recommend_template(self._templates, image_count=count)
        if rec:
            self.recommend_label.setText(f"推荐: {rec.id}")
            # 自动切换（除非用户已经手动选了别的同模板）
            idx = self.tpl_combo.findData(rec.id)
            if idx >= 0 and idx != self.tpl_combo.currentIndex():
                self.tpl_combo.setCurrentIndex(idx)
        else:
            self.recommend_label.setText("")

    # ---------------- 拆图 ----------------

    def _preview_split(self):
        sel = self.thumb_list.selected_paths()
        if not sel:
            QMessageBox.warning(self, "提示", "先在上方选 1 张宫格图")
            return
        img = sel[0]
        spec = make_grid_spec(
            self.src_rows.value(), self.src_cols.value(),
            self.sub_rows.value(), self.sub_cols.value(),
        )
        try:
            tiles = split_to_preview_cache(img, spec, PREVIEW_CACHE)
        except Exception as e:
            QMessageBox.critical(self, "拆图失败", str(e))
            return
        self._tile_paths = tiles
        # 临时塞进 tiles_view（自定义放入）
        self.tiles_view.clear()
        from PySide6.QtGui import QPixmap, QIcon
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QListWidgetItem
        for p in tiles:
            pix = QPixmap(str(p)).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            it = QListWidgetItem(QIcon(pix), p.name)
            it.setData(Qt.UserRole, str(p))
            it.setSizeHint(QSize(124, 140))
            self.tiles_view.addItem(it)
        self.confirm_check.setChecked(False)
        self._split_confirmed = False
        self._auto_recommend()
        self._update_run_state()

    # ---------------- 执行 ----------------

    def _can_run(self) -> tuple[bool, str]:
        if self._worker and self._worker.isRunning():
            return False, "运行中…"
        if self._batch_worker and self._batch_worker.isRunning():
            return False, "批量运行中…"
        m = self.mode
        if not self.tpl_combo.currentData():
            return False, "请先选模板"
        if m == "batch":
            if not self.folder_edit.text().strip():
                return False, "请填文件夹路径"
            return True, ""
        sel = self.thumb_list.selected_paths()
        if m == "grid":
            if len(sel) != 1:
                return False, "宫格模式：请只选 1 张图"
            if not self._tile_paths:
                return False, "请先点「预览拆图」"
            if not self._split_confirmed:
                return False, "请勾选「我确认拆图正确」"
            return True, ""
        if m == "single":
            if len(sel) != 1:
                return False, "请选 1 张图"
        else:  # multi
            if not sel:
                return False, "请至少选 1 张图"
        return True, ""

    def _update_run_state(self):
        ok, reason = self._can_run()
        self.btn_run.setEnabled(ok)
        self.run_hint.setText(reason)

    def _run(self):
        ok, reason = self._can_run()
        if not ok:
            QMessageBox.warning(self, "无法运行", reason)
            return
        m = self.mode
        if m == "batch":
            self._run_batch()
        else:
            self._run_single()

    def _gather_images(self) -> list[Path]:
        m = self.mode
        if m == "grid":
            return list(self._tile_paths)
        return self.thumb_list.selected_paths()

    def _run_single(self):
        images = self._gather_images()
        tpl = self._current_template()
        supp = self.form_widget.get_values()
        try:
            system_prompt = render_template(tpl, supp)
        except ValueError as e:
            QMessageBox.warning(self, "模板字段缺失", str(e))
            return
        try:
            provider = factory.build_provider(
                self.cfg, self.cfg.current_provider, self.cfg.current_model)
        except Exception as e:
            QMessageBox.critical(self, "Provider 错误", str(e))
            return

        def task():
            raw = provider.generate(images, system_prompt, "")
            parsed = parse_result(raw)
            out_dir = resolve_output_dir(images[0], self.cfg.default_output_dir)
            md, js = write_outputs(
                result=parsed, output_dir=out_dir, base_name=images[0].stem,
                template_id=tpl.id,
                provider=self.cfg.current_provider, model=self.cfg.current_model,
            )
            return parsed, md, js

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_single_done)
        self._worker.failed.connect(self._on_single_failed)
        self.btn_run.setText("反推中…")
        self.btn_run.setEnabled(False)
        self._worker.start()

    def _on_single_done(self, payload):
        parsed, md, js = payload
        self._result = parsed
        self._result_md = md
        self._result_json = js
        self._result_meta = {
            "template_id": self._current_template().id,
            "provider": self.cfg.current_provider,
            "model": self.cfg.current_model,
        }
        self.field_global.setPlainText(parsed.global_prompt)
        self.field_timeline.setPlainText(parsed.timeline_data)
        self.field_locals.setPlainText(parsed.local_prompts)
        self.field_notes.setPlainText(parsed.notes)
        import json
        self.field_struct.setPlainText(json.dumps({
            "segment_lengths": parsed.segment_lengths,
            "max_frames": parsed.max_frames,
            "frame_indices": parsed.frame_indices,
            "strengths": parsed.strengths,
            "epsilon": parsed.epsilon,
        }, indent=2, ensure_ascii=False))
        self.result_box.setVisible(True)
        self.btn_run.setText("🚀 开始反推")
        self._update_run_state()

    def _on_single_failed(self, err):
        QMessageBox.critical(self, "反推失败", err)
        self.btn_run.setText("🚀 开始反推")
        self._update_run_state()

    def _save_result(self):
        if not self._result or not self._result_md:
            return
        # 写回字段
        self._result.global_prompt = self.field_global.toPlainText()
        self._result.timeline_data = self.field_timeline.toPlainText()
        self._result.local_prompts = self.field_locals.toPlainText()
        self._result.notes = self.field_notes.toPlainText()
        try:
            write_outputs(
                result=self._result,
                output_dir=self._result_md.parent,
                base_name=self._result_md.stem,
                template_id=self._result_meta.get("template_id", ""),
                provider=self._result_meta.get("provider", ""),
                model=self._result_meta.get("model", ""),
            )
            QMessageBox.information(self, "已保存", f"覆盖写入：\n{self._result_md}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # ---------------- 批量 ----------------

    def _run_batch(self):
        folder = Path(self.folder_edit.text().strip())
        if not folder.is_dir():
            QMessageBox.warning(self, "无效目录", str(folder))
            return
        from app.grid_ops import SUPPORTED_IMG_EXTS
        images = sorted(p for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in SUPPORTED_IMG_EXTS)
        if not images:
            QMessageBox.warning(self, "空目录", "未找到图片")
            return
        tpl = self._current_template()
        supp = self.form_widget.get_values()
        cfg = self.cfg
        out_dir_default = resolve_output_dir(images[0], cfg.default_output_dir)
        per_image = self.per_image_check.isChecked()

        def per_image_supp(img: Path, base: dict) -> dict:
            import json as _json
            res = dict(base)
            j = img.with_suffix(".json")
            if j.exists():
                try:
                    d = _json.loads(j.read_text(encoding="utf-8"))
                    if isinstance(d, dict):
                        for k, v in d.items():
                            res.setdefault(k, v)
                except Exception:
                    pass
            for ext in (".md", ".txt"):
                p = img.with_suffix(ext)
                if p.exists() and not res.get("script"):
                    res["script"] = p.read_text(encoding="utf-8")
                    break
            return res

        def worker(item: dict):
            img: Path = item["image"]
            if (out_dir_default / f"{img.stem}.md").exists() and (out_dir_default / f"{img.stem}.json").exists():
                return {"status": "skipped"}
            eff = per_image_supp(img, supp) if per_image else supp
            sp = render_template(tpl, eff)
            provider = factory.build_provider(cfg, cfg.current_provider, cfg.current_model)
            raw = provider.generate([img], sp, "")
            parsed = parse_result(raw)
            md, js = write_outputs(
                result=parsed, output_dir=out_dir_default, base_name=img.stem,
                template_id=tpl.id, provider=cfg.current_provider, model=cfg.current_model,
            )
            return {"status": "ok", "md": str(md)}

        items = [{"image": p, "base_name": p.stem} for p in images]
        self.batch_table.setRowCount(0)
        self.batch_table.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setMaximum(len(items))
        self.progress.setValue(0)
        self._batch_worker = BatchWorker(items, worker)
        self._batch_worker.item_done.connect(self._on_batch_item)
        self._batch_worker.all_done.connect(self._on_batch_done)
        self.btn_run.setEnabled(False)
        self.btn_run.setText("批量中…")
        self._batch_worker.start()

    def _on_batch_item(self, idx, total, base_name, status, payload):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        self.batch_table.setItem(row, 0, QTableWidgetItem(str(idx + 1)))
        self.batch_table.setItem(row, 1, QTableWidgetItem(base_name))
        s = QTableWidgetItem(status if not isinstance(payload, str) or status != "failed"
                             else f"failed: {payload}")
        self.batch_table.setItem(row, 2, s)
        self.progress.setValue(idx + 1)

    def _on_batch_done(self, ok, failed):
        QMessageBox.information(self, "批量完成", f"成功 {ok} · 失败 {failed}")
        self.btn_run.setText("🚀 开始反推")
        self._update_run_state()
