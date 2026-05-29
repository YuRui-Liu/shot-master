"""StoryboardPage：分镜阶段子面板。

顶 _ParamBar + 全局头（标题/比例/时长/globalStyle/characters）+ 中表格 + 底 _WarningsBanner + ActionBar。
流式期间不解析、只显字数；done 时一次性解析 + 渲染表格。
重生确认 + purge_downstream；dirty 切换护栏。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QSpinBox,
    QComboBox, QPlainTextEdit, QMessageBox, QFrame, QTableView, QDoubleSpinBox,
    QDialog, QDialogButtonBox, QHeaderView,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._shots_table_model import _ShotsTableModel
from drama_shot_master.ui.widgets.screenwriter._character_row import _CharacterRow
from drama_shot_master.ui.widgets.screenwriter._warnings_banner import _WarningsBanner
from screenwriter_agent.core.atomic_write import atomic_write_text


class StoryboardPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._sb_path: Path | None = None
        self._sb: dict | None = None
        self._original_sb_json: str = ""
        self._last_load_mtime: float = 0.0
        self._warnings: list[dict] = []
        self._dirty: bool = False
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._buf: str = ""
        self._character_rows: list[_CharacterRow] = []
        self._shots_model = _ShotsTableModel()
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        root.addWidget(self._build_global_header())
        self._table = QTableView()
        self._table.setModel(self._shots_model)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)
        self._shots_model.dataChanged.connect(lambda *a: self._mark_dirty())
        root.addWidget(self._table, 1)
        self._warnings_banner = _WarningsBanner()
        self._warnings_banner.warningClicked.connect(self._on_warning_clicked)
        root.addWidget(self._warnings_banner)
        root.addLayout(self._build_action_bar())

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("比例:"))
        self._aspect_combo = QComboBox()
        self._aspect_combo.addItems(["9:16", "16:9", "1:1"])
        bar.addWidget(self._aspect_combo)
        bar.addWidget(QLabel("fps:"))
        self._fps_spin = QSpinBox(); self._fps_spin.setRange(12, 60)
        self._fps_spin.setValue(24)
        bar.addWidget(self._fps_spin)
        bar.addWidget(QLabel("默认时长:"))
        self._default_dur_spin = QDoubleSpinBox()
        self._default_dur_spin.setRange(0.5, 30.0); self._default_dur_spin.setValue(3.0)
        bar.addWidget(self._default_dur_spin)
        bar.addWidget(QLabel("密度:"))
        self._density_combo = QComboBox()
        self._density_combo.addItems(["稀疏", "常规", "紧凑"])
        self._density_combo.setCurrentText("常规")
        bar.addWidget(self._density_combo)
        bar.addStretch(1)
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        self._gen_btn = QPushButton("生成分镜")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止"); self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        return bar

    def _build_global_header(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(f)
        v.setContentsMargins(6, 4, 6, 4); v.setSpacing(4)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("标题:"))
        self._title_edit = QLineEdit()
        self._title_edit.textChanged.connect(lambda _: self._mark_dirty())
        row1.addWidget(self._title_edit, 1)
        row1.addWidget(QLabel("时长(s):"))
        self._total_duration_label = QLabel("0")
        row1.addWidget(self._total_duration_label)
        v.addLayout(row1)
        v.addWidget(QLabel("globalStyle:"))
        self._global_style_edit = QPlainTextEdit()
        self._global_style_edit.setMaximumHeight(50)
        self._global_style_edit.textChanged.connect(self._mark_dirty)
        v.addWidget(self._global_style_edit)
        # 角色区
        char_top = QHBoxLayout()
        char_top.addWidget(QLabel("角色:"))
        char_top.addStretch(1)
        btn_add = QPushButton("+ 加角色")
        btn_add.clicked.connect(self._on_add_character)
        char_top.addWidget(btn_add)
        v.addLayout(char_top)
        self._characters_layout = QVBoxLayout()
        v.addLayout(self._characters_layout)
        return f

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存修改")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_clicked)
        bar.addWidget(self._save_btn)
        self._view_json_btn = QPushButton("{ } 看原始 JSON")
        self._view_json_btn.clicked.connect(self._on_view_json_clicked)
        bar.addWidget(self._view_json_btn)
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进到提示词 →")
        self._advance_btn.setEnabled(False)
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        bar.addWidget(self._advance_btn)
        return bar

    # —— set_project / try_release ——

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        self._project_dir = path
        if path is None:
            self._sb_path = None
            self._sb = None
            self._set_sb_to_ui(None)
            self._state = "idle"
            for b in (self._gen_btn, self._save_btn, self._view_json_btn,
                       self._advance_btn):
                b.setEnabled(False)
            return
        self._sb_path = path / "分镜.json"
        self._load_from_disk()
        self._gen_btn.setEnabled(True)
        self._view_json_btn.setEnabled(self._sb is not None)

    def _load_from_disk(self):
        self._sb = None
        if self._sb_path and self._sb_path.is_file():
            try:
                self._sb = json.loads(self._sb_path.read_text(encoding="utf-8"))
                self._last_load_mtime = self._sb_path.stat().st_mtime
                self._original_sb_json = json.dumps(self._sb, ensure_ascii=False,
                                                     sort_keys=True)
            except Exception:
                self._sb = None
        self._set_sb_to_ui(self._sb)
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._state = "done" if self._sb else "idle"
        self._advance_btn.setEnabled(self._state == "done")

    def _set_sb_to_ui(self, sb: dict | None):
        # 清空角色行
        for r in self._character_rows:
            r.deleteLater()
        self._character_rows = []
        if sb is None:
            self._title_edit.blockSignals(True); self._title_edit.clear()
            self._title_edit.blockSignals(False)
            self._total_duration_label.setText("0")
            self._global_style_edit.blockSignals(True)
            self._global_style_edit.clear()
            self._global_style_edit.blockSignals(False)
            self._shots_model.set_shots([])
            self._warnings_banner.set_warnings([])
            return
        self._title_edit.blockSignals(True)
        self._title_edit.setText(sb.get("title", ""))
        self._title_edit.blockSignals(False)
        self._total_duration_label.setText(str(sb.get("totalDuration", 0)))
        self._global_style_edit.blockSignals(True)
        self._global_style_edit.setPlainText(sb.get("globalStyle", ""))
        self._global_style_edit.blockSignals(False)
        # characters
        for i, ch in enumerate(sb.get("characters", []) or []):
            row = _CharacterRow(i, ch.get("name", ""), ch.get("appearance", ""))
            row.changed.connect(self._mark_dirty)
            row.removeClicked.connect(self._on_remove_character)
            self._characters_layout.addWidget(row)
            self._character_rows.append(row)
        # shots 表（直接传引用，setData 写回原 dict）
        self._shots_model.set_shots(sb.get("shots", []) or [])
        self._warnings_banner.set_warnings(self._warnings)

    def try_release(self) -> bool:
        if not self._dirty:
            return True
        ans = QMessageBox.question(
            self, "分镜有未保存改动", "切换前是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            self._on_save_clicked()
            return True
        if ans == QMessageBox.Discard:
            self._load_from_disk()
            return True
        return False

    # —— UI 事件 ——

    def _mark_dirty(self):
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._advance_btn.setEnabled(False)

    def _on_add_character(self):
        if self._sb is None:
            self._sb = {"title": "", "globalStyle": "", "characters": [], "shots": []}
        self._sb.setdefault("characters", []).append({"name": "", "appearance": ""})
        idx = len(self._sb["characters"]) - 1
        row = _CharacterRow(idx, "", "")
        row.changed.connect(self._mark_dirty)
        row.removeClicked.connect(self._on_remove_character)
        self._characters_layout.addWidget(row)
        self._character_rows.append(row)
        self._mark_dirty()

    def _on_remove_character(self, idx: int):
        if self._sb is None:
            return
        chars = self._sb.get("characters", [])
        if 0 <= idx < len(chars):
            chars.pop(idx)
            # 重渲染（角色 idx 会变）
            self._set_sb_to_ui(self._sb)
            self._mark_dirty()

    def _on_save_clicked(self):
        if self._sb is None or self._sb_path is None:
            return
        # 把 UI 状态吸回 _sb
        self._sb["title"] = self._title_edit.text().strip()
        self._sb["globalStyle"] = self._global_style_edit.toPlainText().strip()
        self._sb["characters"] = [
            {"name": n, "appearance": a}
            for r in self._character_rows
            for (n, a) in [r.values()]
        ]
        # pydantic 二次校验
        try:
            from screenwriter_agent.models.storyboard_schema import Storyboard
            Storyboard.model_validate(self._sb)
        except Exception as e:
            QMessageBox.warning(self, "保存失败：数据无效", str(e))
            return
        try:
            atomic_write_text(
                self._sb_path,
                json.dumps(self._sb, ensure_ascii=False, indent=2))
            self._last_load_mtime = self._sb_path.stat().st_mtime
            self._original_sb_json = json.dumps(self._sb, ensure_ascii=False,
                                                 sort_keys=True)
            self._dirty = False
            self._save_btn.setEnabled(False)
            self._state = "done"
            self._advance_btn.setEnabled(True)
            self.projectStateChanged.emit()
            self.statusMessage.emit("分镜.json 已保存")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_view_json_clicked(self):
        if self._sb is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("分镜.json（只读）")
        dlg.resize(720, 600)
        v = QVBoxLayout(dlg)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(json.dumps(self._sb, ensure_ascii=False, indent=2))
        v.addWidget(viewer)
        bar = QHBoxLayout()
        btn_copy = QPushButton("复制到剪贴板")
        btn_copy.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(viewer.toPlainText()))
        bar.addWidget(btn_copy)
        btn_open = QPushButton("打开文件")
        btn_open.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._sb_path))))
        bar.addWidget(btn_open)
        bar.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bar.addWidget(bb)
        v.addLayout(bar)
        dlg.exec()

    def _on_advance_clicked(self):
        if self._dirty and not self.try_release():
            return
        self.stageAdvanceRequested.emit(3)

    def _on_warning_clicked(self, path: str):
        # 解析 shots[N].field → 高亮表格行 N
        import re
        m = re.match(r"shots\[(\d+)\]", path)
        if m:
            row = int(m.group(1))
            if 0 <= row < self._shots_model.rowCount():
                self._table.selectRow(row)

    # —— 生成 / SSE ——

    def _on_generate_clicked(self):
        if self._project_dir is None:
            return
        script_path = self._project_dir / "剧本.md"
        if not script_path.is_file():
            QMessageBox.warning(self, "上游缺失",
                                  "请先在「剧本」阶段生成剧本.md。")
            return
        params = None
        if self._state == "done":
            ans = QMessageBox.question(
                self, "重新生成",
                "重新生成会覆盖分镜.json，并删除下游 prompts/。继续？",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            params = {"purge_downstream": "true"}
        body = {
            "project_dir": str(self._project_dir),
            "options": {
                "aspect_ratio": self._aspect_combo.currentText(),
                "fps": self._fps_spin.value(),
                "shot_duration_default": self._default_dur_spin.value(),
                "density": self._density_combo.currentText(),
            },
        }
        self._buf = ""
        self._start_stream("/storyboard", body, params)

    def _start_stream(self, path, body, params=None):
        self._state = "streaming"
        self._gen_btn.hide(); self._stop_btn.show()
        self._stream_label.setText("● 流式 · 已 0 字")
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(False)
        self._worker = StreamWorker(self._client, path, body, params, parent=self)
        self._worker.event.connect(self._on_sse_event)
        self._worker.finished_ok.connect(self._on_stream_done_signal)
        self._worker.failed.connect(self._on_stream_failed)
        self._worker.start()

    def _stop_stream(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._state = "idle"
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")

    def _on_sse_event(self, event_name: str, data: dict):
        if event_name == "delta":
            text = data.get("text", "")
            self._buf += text
            self._stream_label.setText(f"● 流式 · 已 {len(self._buf)} 字")
        elif event_name == "status":
            phase = data.get("phase", "")
            if phase == "validating":
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._buf)} 字 · 修复中…")
        elif event_name == "done":
            # 直接消费 done 携带的 result + warnings
            sb = data.get("result")
            warns = data.get("warnings", [])
            saved = data.get("saved", "")
            if sb is not None:
                self._sb = sb
                self._warnings = warns or []
                self._original_sb_json = json.dumps(sb, ensure_ascii=False,
                                                     sort_keys=True)
                if saved:
                    try:
                        self._last_load_mtime = Path(saved).stat().st_mtime
                    except OSError:
                        pass
                self._set_sb_to_ui(sb)
                self._dirty = False
                self._save_btn.setEnabled(False)
                self._state = "done"
                self._advance_btn.setEnabled(True)
        elif event_name == "error":
            code = data.get("code", "")
            hint = data.get("hint") or data.get("message", "")
            details = data.get("details", {})
            if code == "JSON_REPAIR_FAILED":
                raw_path = details.get("raw_output_path", "")
                ans = QMessageBox.warning(
                    self, "JSON 修复失败",
                    f"{hint}\n\nraw 文件: {raw_path}",
                    QMessageBox.Open | QMessageBox.Close)
                if ans == QMessageBox.Open and raw_path:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(raw_path))
            else:
                QMessageBox.warning(self, "分镜生成失败", hint or code)
            self._stop_stream()

    def _on_stream_done_signal(self):
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str):
        self._stop_stream()
        QMessageBox.warning(self, "生成失败",
                             f"分镜生成失败：{msg}\n请检查网络或 LLM 配置。")
