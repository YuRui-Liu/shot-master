"""ScriptPage：剧本阶段子面板。

顶 _ParamBar + 中 QPlainTextEdit + 底 _ActionBar。
状态机 idle/streaming/done；磁盘是真相源；外部 mtime 检测；
重生确认 + purge_downstream；切阶段时 dirty 拦截。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QSpinBox,
    QComboBox, QMessageBox,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from screenwriter_agent.core.atomic_write import atomic_write_text


class ScriptPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._script_path: Path | None = None
        self._original_text: str = ""
        self._last_load_mtime: float = 0.0
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.addLayout(self._build_param_bar())
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("剧本.md 内容（生成或加载后显示在此）")
        self._editor.textChanged.connect(self._on_editor_changed)
        root.addWidget(self._editor, 1)
        root.addLayout(self._build_action_bar())

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("时长(s):"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(15, 600); self._duration_spin.setValue(60)
        bar.addWidget(self._duration_spin)
        bar.addWidget(QLabel("fps:"))
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(12, 60); self._fps_spin.setValue(24)
        bar.addWidget(self._fps_spin)
        bar.addWidget(QLabel("语言风格:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["口语化", "书面语", "古风"])
        bar.addWidget(self._lang_combo)
        bar.addStretch(1)
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        self._gen_btn = QPushButton("生成剧本")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止")
        self._stop_btn.clicked.connect(self._stop_stream)
        self._stop_btn.hide()
        bar.addWidget(self._stop_btn)
        return bar

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存修改")
        self._save_btn.clicked.connect(self._on_save_clicked)
        self._save_btn.setEnabled(False)
        bar.addWidget(self._save_btn)
        self._open_btn = QPushButton("📂 打开文件")
        self._open_btn.clicked.connect(self._on_open_file_clicked)
        bar.addWidget(self._open_btn)
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进到分镜 →")
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        self._advance_btn.setEnabled(False)
        bar.addWidget(self._advance_btn)
        return bar

    # —— set_project / try_release ——

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        self._project_dir = path
        if path is None:
            self._script_path = None
            self._editor.blockSignals(True)
            self._editor.clear()
            self._editor.blockSignals(False)
            self._original_text = ""
            self._state = "idle"
            for b in (self._gen_btn, self._save_btn, self._open_btn,
                       self._advance_btn):
                b.setEnabled(False)
            return
        self._script_path = path / "剧本.md"
        self._load_from_disk()
        self._gen_btn.setEnabled(True)
        self._open_btn.setEnabled(True)

    def _load_from_disk(self):
        text = ""
        if self._script_path is not None and self._script_path.is_file():
            try:
                text = self._script_path.read_text(encoding="utf-8")
                self._last_load_mtime = self._script_path.stat().st_mtime
            except OSError:
                text = ""
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self._original_text = text
        self._state = "done" if text else "idle"
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(self._state == "done")

    def try_release(self) -> bool:
        if not self._is_dirty():
            return True
        ans = QMessageBox.question(
            self, "剧本有未保存改动",
            "切换前是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            self._on_save_clicked()
            return True
        if ans == QMessageBox.Discard:
            self._editor.blockSignals(True)
            self._editor.setPlainText(self._original_text)
            self._editor.blockSignals(False)
            self._save_btn.setEnabled(False)
            return True
        return False    # Cancel

    def _is_dirty(self) -> bool:
        return self._editor.toPlainText() != self._original_text

    # —— 用户交互 ——

    def _on_editor_changed(self):
        self._save_btn.setEnabled(self._is_dirty())

    def _on_save_clicked(self):
        if self._script_path is None:
            return
        try:
            atomic_write_text(self._script_path, self._editor.toPlainText())
            self._original_text = self._editor.toPlainText()
            self._last_load_mtime = self._script_path.stat().st_mtime
            self._save_btn.setEnabled(False)
            self._state = "done"
            self._advance_btn.setEnabled(True)
            self.projectStateChanged.emit()
            self.statusMessage.emit("剧本.md 已保存")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_open_file_clicked(self):
        if self._script_path and self._script_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._script_path)))

    def _on_advance_clicked(self):
        if self._is_dirty() and not self.try_release():
            return
        self.stageAdvanceRequested.emit(2)

    def _on_generate_clicked(self):
        if self._project_dir is None:
            return
        # 上游检查
        idea_path = self._project_dir / "idea.json"
        if not idea_path.is_file():
            QMessageBox.warning(self, "上游缺失",
                                  "请先在「创意」阶段生成候选并选定一个。")
            return
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
        except Exception:
            QMessageBox.warning(self, "上游损坏", "idea.json 解析失败。")
            return
        if not idea.get("selected_id"):
            QMessageBox.warning(self, "未选定候选",
                                  "请先在「创意」阶段选定一个候选。")
            return
        # 重生确认
        params = None
        if self._state == "done":
            ans = QMessageBox.question(
                self, "重新生成",
                "重新生成会覆盖剧本.md，并删除下游 分镜.json + prompts/。继续？",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            params = {"purge_downstream": "true"}
        # 启流
        body = {
            "project_dir": str(self._project_dir),
            "options": {
                "length_preset": "完整版",
                "language_style": self._lang_combo.currentText(),
                "fps": self._fps_spin.value(),
                "duration_sec": self._duration_spin.value(),
            },
        }
        self._editor.blockSignals(True)
        self._editor.clear()
        self._editor.blockSignals(False)
        self._start_stream("/script", body, params)

    # —— SSE 流 ——

    def _start_stream(self, path, body, params=None):
        self._state = "streaming"
        self._gen_btn.hide(); self._stop_btn.show()
        self._stream_label.setText("● 流式 · 已 0 字")
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(False)
        self._worker = StreamWorker(self._client, path, body, params, parent=self)
        self._worker.event.connect(self._on_sse_event)
        self._worker.finished_ok.connect(self._on_stream_done)
        self._worker.failed.connect(self._on_stream_failed)
        self._worker.start()

    def _stop_stream(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._reset_stream_ui("idle")

    def _on_sse_event(self, event_name: str, data: dict):
        if event_name == "delta":
            text = data.get("text", "")
            if text:
                # 追加到编辑器末尾
                self._editor.blockSignals(True)
                self._editor.moveCursor(self._editor.textCursor().End)
                self._editor.insertPlainText(text)
                self._editor.blockSignals(False)
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._editor.toPlainText())} 字")

    def _on_stream_done(self):
        # 重读磁盘
        self._load_from_disk()
        self._reset_stream_ui("done")
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str):
        self._reset_stream_ui("idle")
        QMessageBox.warning(self, "生成失败",
                             f"剧本生成失败：{msg}\n请检查网络或 LLM 配置。")

    def _reset_stream_ui(self, state: str):
        self._state = state
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")
        self._save_btn.setEnabled(self._is_dirty())
        self._advance_btn.setEnabled(state == "done" and not self._is_dirty())
