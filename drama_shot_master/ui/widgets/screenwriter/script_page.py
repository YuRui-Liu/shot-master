"""ScriptPage v2：多集剧本子面板。

布局：参数栏（集数 spin + 时长 + 语言风格 + 流式状态 + [生成大纲/生成剧本] + [中止]）
     上游 banner
     大纲表 QTableWidget（集 / 标题 / 概要 / 操作 列）
     [一键全集] + 进度 label
     当前集 md 编辑器 QPlainTextEdit
     操作栏：[保存][打开][推进到分镜 →]
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QSpinBox,
    QComboBox, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
from drama_shot_master.ui.widgets.screenwriter._paths import (
    idea_file_in, idea_exists_in,
    script_index_path_in, script_episode_path_in, script_episode_read_path_in,
)
from screenwriter_agent.core.atomic_write import atomic_write_text


class ScriptPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._si: dict | None = None                  # 加载的 剧本.json
        self._current_episode: str = ""               # 当前选中行 id
        self._episode_md: dict[str, str] = {}         # 各集 md 内容缓存
        self._original_md: dict[str, str] = {}        # 用于 dirty 检测
        self._build_ui()
        self.set_project(None)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        self._upstream_banner = _UpstreamBanner()
        root.addWidget(self._upstream_banner)
        # 大纲表
        self._outline_table = QTableWidget(0, 4)
        self._outline_table.setHorizontalHeaderLabels(["集", "标题", "概要", "操作"])
        h = self._outline_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Interactive)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        # 操作列内是 cellWidget 按钮，ResizeToContents 不量 widget → 列塌缩裁切，
        # 改固定宽容纳「生成此集」
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        self._outline_table.setColumnWidth(3, 92)
        self._outline_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._outline_table.setSelectionMode(QTableWidget.SingleSelection)
        self._outline_table.setMaximumHeight(200)
        self._outline_table.itemSelectionChanged.connect(self._on_outline_row_selected)
        root.addWidget(self._outline_table)
        # 一键全集 + 进度
        batch_bar = QHBoxLayout()
        self._batch_btn = QPushButton("一键全集 ▶")
        self._batch_btn.clicked.connect(self._on_batch_clicked)
        batch_bar.addWidget(self._batch_btn)
        self._batch_progress = QLabel("")
        batch_bar.addWidget(self._batch_progress)
        batch_bar.addStretch(1)
        root.addLayout(batch_bar)
        # 当前集 editor
        self._episode_editor = QPlainTextEdit()
        self._episode_editor.setPlaceholderText("选中上方某行后显示该集 md（或在此直接编写）")
        self._episode_editor.textChanged.connect(self._on_editor_changed)
        root.addWidget(self._episode_editor, 1)
        root.addLayout(self._build_action_bar())

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("集数:"))
        self._episode_count_spin = QSpinBox()
        self._episode_count_spin.setRange(1, 20)
        self._episode_count_spin.setValue(1)
        self._episode_count_spin.valueChanged.connect(self._update_gen_button_text)
        bar.addWidget(self._episode_count_spin)
        bar.addWidget(QLabel("时长/集(s):"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(15, 600)
        self._duration_spin.setValue(60)
        bar.addWidget(self._duration_spin)
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
        self._save_btn = QPushButton("💾 保存")
        self._save_btn.clicked.connect(self._on_save_clicked)
        self._save_btn.setEnabled(False)
        bar.addWidget(self._save_btn)
        self._open_btn = QPushButton("📂 打开")
        self._open_btn.clicked.connect(self._on_open_file_clicked)
        self._open_btn.setEnabled(False)
        bar.addWidget(self._open_btn)
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进到分镜 →")
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        self._advance_btn.setEnabled(False)
        bar.addWidget(self._advance_btn)
        return bar

    # —— update button text ——

    def _update_gen_button_text(self):
        n = self._episode_count_spin.value()
        self._gen_btn.setText("生成剧本" if n == 1 else "生成大纲")

    # —— set_project ——

    def set_project(self, path: Path | None) -> None:
        if self._project_dir is not None and not self.try_release():
            return
        self._project_dir = path
        self._si = None
        self._current_episode = ""
        self._episode_md.clear()
        self._original_md.clear()
        if path is None:
            self._upstream_banner.hide_banner()
            self._outline_table.setRowCount(0)
            self._episode_editor.blockSignals(True)
            self._episode_editor.clear()
            self._episode_editor.blockSignals(False)
            for b in (self._gen_btn, self._save_btn, self._open_btn,
                       self._advance_btn, self._batch_btn):
                b.setEnabled(False)
            return
        # 上游检查
        if not idea_exists_in(path):
            self._upstream_banner.show_missing(
                stage_name="创意", expected_file="创意.json")
            self._gen_btn.setEnabled(False)
        else:
            self._upstream_banner.hide_banner()
            self._gen_btn.setEnabled(True)
        self._open_btn.setEnabled(True)
        self._batch_btn.setEnabled(True)
        self._load_index()
        # 若正在 streaming（任一集），恢复流式视图
        if self.is_streaming(path):
            self._enter_streaming_view()
        else:
            self._exit_streaming_view()

    def _load_index(self):
        """读 剧本.json + 渲染大纲表 + 选第一行。"""
        if self._project_dir is None:
            return
        si_path = script_index_path_in(self._project_dir)
        if si_path.is_file():
            try:
                self._si = json.loads(si_path.read_text(encoding="utf-8"))
            except Exception:
                self._si = None
        else:
            self._si = None

        episodes = self._si.get("episodes", []) if self._si else []
        self._outline_table.blockSignals(True)
        self._outline_table.setRowCount(0)
        for ep in episodes:
            row = self._outline_table.rowCount()
            self._outline_table.insertRow(row)
            self._outline_table.setItem(row, 0, QTableWidgetItem(ep.get("id", "")))
            self._outline_table.setItem(row, 1, QTableWidgetItem(ep.get("title", "")))
            self._outline_table.setItem(row, 2, QTableWidgetItem(ep.get("summary", "")))
            gen_btn = QPushButton("生成此集")
            gen_btn.setMinimumWidth(84)
            ep_id = ep.get("id", "")
            gen_btn.clicked.connect(lambda _=False, eid=ep_id: self._on_per_row_gen_clicked(eid))
            self._outline_table.setCellWidget(row, 3, gen_btn)
        self._outline_table.blockSignals(False)

        # legacy 兼容：无 剧本.json 但有 剧本.md → 直接装进 editor（不渲染表）
        if not episodes:
            legacy = (self._project_dir / "剧本.md") if self._project_dir else None
            if legacy and legacy.is_file():
                text = legacy.read_text(encoding="utf-8")
                self._episode_editor.blockSignals(True)
                self._episode_editor.setPlainText(text)
                self._episode_editor.blockSignals(False)
                self._original_md["__legacy__"] = text
                self._current_episode = "E1"
            return

        # 自动选第一行
        if episodes:
            self._outline_table.selectRow(0)
            self._on_outline_row_selected()

        # 更新推进按钮
        self._refresh_advance_btn()

    def _on_outline_row_selected(self):
        rows = self._outline_table.selectedItems()
        if not rows:
            return
        row = self._outline_table.currentRow()
        if row < 0 or self._si is None:
            return
        episodes = self._si.get("episodes", [])
        if row >= len(episodes):
            return
        ep_id = episodes[row].get("id", "")
        if ep_id == self._current_episode:
            return
        # 先保存当前集 dirty
        if self._is_dirty():
            self._flush_current_episode()
        self._current_episode = ep_id
        # 加载 md
        if ep_id in self._episode_md:
            text = self._episode_md[ep_id]
        else:
            ep_path = (script_episode_read_path_in(self._project_dir, ep_id)
                       if self._project_dir else None)
            text = ep_path.read_text(encoding="utf-8") if ep_path else ""
            self._episode_md[ep_id] = text
            self._original_md[ep_id] = text
        self._episode_editor.blockSignals(True)
        self._episode_editor.setPlainText(text)
        self._episode_editor.blockSignals(False)
        self._save_btn.setEnabled(False)
        self._open_btn.setEnabled(True)
        self._refresh_advance_btn()

    def _flush_current_episode(self):
        if not self._current_episode or self._project_dir is None:
            return
        text = self._episode_editor.toPlainText()
        ep_path = script_episode_path_in(self._project_dir, self._current_episode)
        try:
            atomic_write_text(ep_path, text)
            self._original_md[self._current_episode] = text
            self._episode_md[self._current_episode] = text
        except OSError:
            pass

    def _refresh_advance_btn(self):
        if self._project_dir is None or not self._current_episode:
            self._advance_btn.setEnabled(False)
            return
        ep_path = script_episode_read_path_in(self._project_dir, self._current_episode)
        self._advance_btn.setEnabled(ep_path is not None and ep_path.is_file())

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
            if self._current_episode:
                self._episode_editor.blockSignals(True)
                self._episode_editor.setPlainText(
                    self._original_md.get(self._current_episode, ""))
                self._episode_editor.blockSignals(False)
            self._save_btn.setEnabled(False)
            return True
        return False

    def _is_dirty(self) -> bool:
        if not self._current_episode:
            return False
        return self._episode_editor.toPlainText() != self._original_md.get(
            self._current_episode, "")

    def _on_editor_changed(self):
        self._save_btn.setEnabled(self._is_dirty())

    def _on_save_clicked(self):
        if not self._current_episode or self._project_dir is None:
            return
        ep_path = script_episode_path_in(self._project_dir, self._current_episode)
        try:
            text = self._episode_editor.toPlainText()
            atomic_write_text(ep_path, text)
            self._original_md[self._current_episode] = text
            self._episode_md[self._current_episode] = text
            self._save_btn.setEnabled(False)
            self._refresh_advance_btn()
            self.projectStateChanged.emit()
            self.statusMessage.emit(f"{ep_path.name} 已保存")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_open_file_clicked(self):
        if self._current_episode and self._project_dir:
            ep_path = script_episode_read_path_in(self._project_dir, self._current_episode)
            if ep_path and ep_path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(ep_path)))

    def _on_advance_clicked(self):
        if self._is_dirty() and not self.try_release():
            return
        # 落 selected_episode 到 剧本.json
        if self._si is not None and self._current_episode and self._project_dir:
            self._si["selected_episode"] = self._current_episode
            si_path = script_index_path_in(self._project_dir)
            try:
                atomic_write_text(
                    si_path,
                    json.dumps(self._si, ensure_ascii=False, indent=2))
            except OSError:
                pass
        self.stageAdvanceRequested.emit(2)

    def _on_generate_clicked(self):
        if self._project_dir is None:
            return
        idea_path = idea_file_in(self._project_dir)
        if idea_path is None:
            QMessageBox.warning(self, "上游缺失",
                                  "请先在「创意」阶段生成候选并选定一个。")
            return
        n = self._episode_count_spin.value()
        if n == 1:
            # 快路径：直接生成 E1
            self._start_episode_stream("E1")
        else:
            # 先生成大纲，再逐集
            self._start_outline_stream(n)

    def _start_outline_stream(self, n: int):
        body = {
            "project_dir": str(self._project_dir),
            "episode_count": n,
            "options": {
                "duration_sec": self._duration_spin.value(),
                "language_style": self._lang_combo.currentText(),
            },
        }
        self._stream_label.setText("● 生成大纲…")
        self._gen_btn.hide(); self._stop_btn.show()
        key = (self._project_dir, "__outline__")
        worker = StreamWorker(self._client, "/script/outline", body, None,
                               project_dir=self._project_dir, parent=self)
        self._workers[key] = worker
        worker.event.connect(self._on_sse_event)
        worker.finished_ok.connect(self._on_stream_done_signal)
        worker.failed.connect(self._on_stream_failed)
        worker.start()

    def _start_episode_stream(self, episode_id: str):
        body = {
            "project_dir": str(self._project_dir),
            "episode_id": episode_id,
            "options": {
                "duration_sec": self._duration_spin.value(),
                "language_style": self._lang_combo.currentText(),
            },
        }
        self._enter_streaming_view()
        key = (self._project_dir, episode_id)
        worker = StreamWorker(self._client, "/script/episode", body, None,
                               project_dir=self._project_dir, parent=self)
        self._workers[key] = worker
        worker.event.connect(self._on_sse_event)
        worker.finished_ok.connect(self._on_stream_done_signal)
        worker.failed.connect(self._on_stream_failed)
        worker.start()

    def _on_per_row_gen_clicked(self, episode_id: str):
        if self._project_dir is None:
            return
        self._start_episode_stream(episode_id)

    def _on_batch_clicked(self):
        if self._project_dir is None or self._si is None:
            return
        episodes = self._si.get("episodes", [])
        if not episodes:
            return
        # 串行触发第一集，其余在 done 事件中继续
        self._batch_queue = [ep["id"] for ep in episodes]
        self._batch_total = len(self._batch_queue)
        self._batch_done_count = 0
        self._batch_btn.setEnabled(False)
        self._run_next_batch()

    def _run_next_batch(self):
        if not getattr(self, "_batch_queue", []):
            self._batch_btn.setEnabled(True)
            self._batch_progress.setText("✓ 全集生成完毕")
            return
        ep_id = self._batch_queue.pop(0)
        self._batch_progress.setText(f"{self._batch_done_count + 1}/{self._batch_total} 生成中…")
        self._start_episode_stream(ep_id)

    def _stop_stream(self):
        for key, w in list(self._workers.items()):
            if isinstance(key, tuple) and w and w.isRunning():
                w.stop()
                w.wait(2000)
                self._workers[key] = None
        if hasattr(self, "_batch_queue"):
            self._batch_queue.clear()
        self._exit_streaming_view()

    # —— 流式 UI ——

    def _enter_streaming_view(self):
        self._gen_btn.hide()
        self._stop_btn.show()
        self._stream_label.setText("● 流式中…")
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(False)

    def _exit_streaming_view(self):
        self._gen_btn.show()
        self._stop_btn.hide()
        self._stream_label.setText("")
        self._save_btn.setEnabled(self._is_dirty())
        self._refresh_advance_btn()

    def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
        proj = Path(project_dir_str)
        ep_id = data.get("episode_id", self._current_episode)

        if event_name == "delta":
            text = data.get("text", "")
            if text and proj == self._project_dir and ep_id == self._current_episode:
                self._episode_editor.blockSignals(True)
                self._episode_editor.moveCursor(QTextCursor.End)
                self._episode_editor.insertPlainText(text)
                self._episode_editor.blockSignals(False)
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._episode_editor.toPlainText())} 字")
        elif event_name == "done":
            if proj == self._project_dir:
                # 重读大纲表（outline 落了新 剧本.json）
                saved = data.get("saved", "")
                if saved and saved.endswith("剧本.json"):
                    self._load_index()
                elif ep_id:
                    # episode md 落盘了，刷缓存
                    ep_path = script_episode_read_path_in(proj, ep_id)
                    if ep_path and ep_path.is_file():
                        txt = ep_path.read_text(encoding="utf-8")
                        self._episode_md[ep_id] = txt
                        self._original_md[ep_id] = txt
                        if ep_id == self._current_episode:
                            self._episode_editor.blockSignals(True)
                            self._episode_editor.setPlainText(txt)
                            self._episode_editor.blockSignals(False)
                # 批量：继续下一集
                if getattr(self, "_batch_queue", []):
                    self._batch_done_count += 1
                    self._run_next_batch()
                    return
                self._exit_streaming_view()
                self._refresh_advance_btn()
            self.projectStateChanged.emit()
        elif event_name == "error":
            if proj == self._project_dir:
                QMessageBox.warning(self, "生成失败",
                                     data.get("hint") or data.get("message", ""))
                self._exit_streaming_view()
            self.projectStateChanged.emit()

    def _on_stream_done_signal(self, project_dir_str: str):
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str, project_dir_str: str):
        proj = Path(project_dir_str)
        if proj == self._project_dir:
            QMessageBox.warning(self, "生成失败", f"生成失败：{msg}")
            self._exit_streaming_view()
        self.projectStateChanged.emit()

    def start_generation_if_idle(self) -> None:
        if self._project_dir is None:
            return
        if not idea_exists_in(self._project_dir):
            return
        si_path = script_index_path_in(self._project_dir)
        if si_path.is_file():
            return
        self._on_generate_clicked()
