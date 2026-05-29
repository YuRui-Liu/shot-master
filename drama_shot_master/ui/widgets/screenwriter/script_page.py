"""ScriptPage：剧本阶段子面板。

顶 _ParamBar + 中 QPlainTextEdit + 底 _ActionBar。
状态机 idle/streaming/done；磁盘是真相源；外部 mtime 检测；
重生确认 + purge_downstream；切阶段时 dirty 拦截。

T6：worker dict 模式（_workers[project_dir]）+ _UpstreamBanner 自检上游。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QSpinBox,
    QComboBox, QMessageBox,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
from screenwriter_agent.core.atomic_write import atomic_write_text


class ScriptPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._script_path: Path | None = None
        self._original_text: str = ""
        self._last_load_mtime: float = 0.0
        # Legacy single-worker ref kept for _stop_stream compatibility;
        # canonical store is self._workers[project_dir] (from _BaseStagePage).
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        self._upstream_banner = _UpstreamBanner()
        root.addWidget(self._upstream_banner)
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

    # —— 流式 UI 状态 ——

    def _enter_streaming_view(self):
        """进入 streaming 显示状态：隐藏「生成」按钮，显示「中止」按钮 + 流式提示。"""
        self._gen_btn.hide()
        self._stop_btn.show()
        self._stream_label.setText("● 流式 · 已 0 字")
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(False)

    def _exit_streaming_view(self):
        """退出 streaming 显示状态：恢复「生成」按钮，隐藏「中止」按钮。"""
        self._gen_btn.show()
        self._stop_btn.hide()
        self._stream_label.setText("")
        self._save_btn.setEnabled(self._is_dirty())
        self._advance_btn.setEnabled(self._state == "done" and not self._is_dirty())

    # —— set_project / try_release ——

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        old = self._project_dir
        self._project_dir = path
        if path is None:
            self._upstream_banner.hide_banner()
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
        # 自检上游
        upstream = path / "创意.json"
        if not upstream.is_file():
            self._upstream_banner.show_missing(
                stage_name="创意", expected_file="创意.json")
            self._gen_btn.setEnabled(False)
        else:
            self._upstream_banner.hide_banner()
            self._gen_btn.setEnabled(True)
        self._open_btn.setEnabled(True)
        self._load_from_disk()
        # 检查 active worker
        if path in self._workers and self._workers[path] and self._workers[path].isRunning():
            self._enter_streaming_view()
        else:
            self._exit_streaming_view()
        self._on_project_switched(old, path)

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

    def start_generation_if_idle(self) -> None:
        """上游 创意.json 在 + 本阶段 剧本.md 不在 + idle → 自动跑生成。"""
        if self._project_dir is None or self._state == "streaming":
            return
        upstream = self._project_dir / "创意.json"
        if not upstream.is_file():
            return
        if self._script_path is not None and self._script_path.is_file():
            return  # 已有剧本不强制覆盖，让用户手动决定
        self._on_generate_clicked()

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
        if self._project_dir is None:
            return
        self._state_by_project[self._project_dir] = "streaming"
        self._buf_by_project.setdefault(self._project_dir, "")
        self._enter_streaming_view()
        worker = StreamWorker(self._client, path, body, params,
                               project_dir=self._project_dir, parent=self)
        self._workers[self._project_dir] = worker
        # Keep legacy ref for _stop_stream (points to current project's worker)
        self._worker = worker
        worker.event.connect(self._on_sse_event)
        worker.finished_ok.connect(self._on_stream_done_signal)
        worker.failed.connect(self._on_stream_failed)
        worker.start()

    def _stop_stream(self):
        w = self._active_worker()
        if w and w.isRunning():
            w.stop()
            w.wait(2000)
        if self._project_dir is not None:
            self._state_by_project[self._project_dir] = "idle"
            self._workers[self._project_dir] = None
        self._state = "idle"
        self._worker = None
        self._exit_streaming_view()

    def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
        proj = Path(project_dir_str)
        # 累 buffer（不论是否当前显示）
        if event_name == "delta":
            text = data.get("text", "")
            self._buf_by_project[proj] = self._buf_by_project.get(proj, "") + text
        elif event_name == "done":
            self._handle_done_for_project(proj, data)
            self._state_by_project[proj] = "done"
        elif event_name == "error":
            self._error_by_project[proj] = data.get("hint") or data.get("message", "")
            self._state_by_project[proj] = "error"

        # 只有当前显示项目才动 UI
        if proj != self._project_dir:
            if event_name in ("done", "error"):
                self.projectStateChanged.emit()
            return

        # 当前显示项目的 UI 更新
        if event_name == "delta":
            text = data.get("text", "")
            if text:
                self._editor.blockSignals(True)
                self._editor.moveCursor(QTextCursor.End)
                self._editor.insertPlainText(text)
                self._editor.blockSignals(False)
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._editor.toPlainText())} 字")
        elif event_name == "done":
            self._exit_streaming_view()
        elif event_name == "error":
            QMessageBox.warning(self, "剧本生成失败",
                                 self._error_by_project.get(proj, ""))
            self._exit_streaming_view()

    def _handle_done_for_project(self, proj: Path, data: dict):
        """落盘逻辑：剧本.md 由 Agent 服务端写出；本端只在切回该项目时重读。
        此方法不操作 UI，安全用于后台项目。"""
        pass

    def _on_stream_done_signal(self, project_dir_str: str):
        proj = Path(project_dir_str)
        if proj in self._workers:
            self._workers[proj] = None
        if proj == self._project_dir:
            self._worker = None
            self._state = "done"
            # 重读磁盘（Agent 已落盘）
            self._load_from_disk()
            self._exit_streaming_view()
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str, project_dir_str: str):
        proj = Path(project_dir_str)
        self._error_by_project[proj] = msg
        self._state_by_project[proj] = "error"
        if proj in self._workers:
            self._workers[proj] = None
        if proj == self._project_dir:
            self._worker = None
            self._state = "idle"
            QMessageBox.warning(self, "生成失败", f"剧本生成失败：{msg}")
            self._exit_streaming_view()
        self.projectStateChanged.emit()
