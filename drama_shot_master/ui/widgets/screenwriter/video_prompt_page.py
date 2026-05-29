"""VideoPromptPage：视频提示词阶段子面板（Stage 5）。

读取上游 分镜_{ep}.json → 调 /video_prompt agent → 生成
  video_prompts/{ep}/global.md   全局画风提示词
  video_prompts/{ep}/shots.json  各镜头提示词列表

SSE partial 事件 → 实时刷新 _global_prompt_edit / _shots_table。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QSplitter, QWidget, QMessageBox,
    QHeaderView,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._paths import (
    storyboard_episode_read_path_in,
    video_prompt_dir_in,
)


class VideoPromptPage(_BaseStagePage):
    """Stage 5：LTX 2.3 视频提示词生成面板。"""

    # 列索引
    _COL_ID = 0
    _COL_PROMPT = 1
    _COL_DUR = 2
    _COL_COPY = 3

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._current_episode: str = "E1"
        self._sb: dict | None = None
        self._build_ui()
        self.set_project(None)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # 顶部工具栏
        root.addLayout(self._build_toolbar())

        # 集选择器
        self._episode_sel = _EpisodeSelector(
            file_pattern_for_status="video_prompts/{ep}/shots.json")
        self._episode_sel.episodeChanged.connect(self._on_episode_changed)
        root.addWidget(self._episode_sel)

        # 主区：splitter（上：全局提示词；下：镜头表格）
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_global_panel())
        splitter.addWidget(self._build_shots_panel())
        splitter.setSizes([150, 400])
        root.addWidget(splitter, 1)

        # 底部：状态 + 推进按钮
        bottom = QHBoxLayout()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #4a9eff")
        bottom.addWidget(self._status_lbl)
        bottom.addStretch(1)
        self._advance_btn = QPushButton("推进到配音配乐 →")
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        bottom.addWidget(self._advance_btn)
        root.addLayout(bottom)

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._gen_btn = QPushButton("生成视频提示词")
        self._gen_btn.setEnabled(False)
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止")
        self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        bar.addStretch(1)
        return bar

    def _build_global_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel("全局画风提示词（global.md）："))
        self._global_prompt_edit = QPlainTextEdit()
        self._global_prompt_edit.setPlaceholderText("生成后自动填充…")
        self._global_prompt_edit.setMaximumHeight(120)
        v.addWidget(self._global_prompt_edit)
        return w

    def _build_shots_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel("分镜视频提示词（shots.json）："))
        self._shots_table = QTableWidget(0, 4)
        self._shots_table.setHorizontalHeaderLabels(
            ["ID", "local_prompt", "时长(s)", "📋"])
        self._shots_table.horizontalHeader().setSectionResizeMode(
            self._COL_PROMPT, QHeaderView.Stretch)
        self._shots_table.horizontalHeader().setSectionResizeMode(
            self._COL_ID, QHeaderView.ResizeToContents)
        self._shots_table.horizontalHeader().setSectionResizeMode(
            self._COL_DUR, QHeaderView.ResizeToContents)
        self._shots_table.horizontalHeader().setSectionResizeMode(
            self._COL_COPY, QHeaderView.ResizeToContents)
        self._shots_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._shots_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._shots_table.cellClicked.connect(self._on_table_cell_clicked)
        v.addWidget(self._shots_table, 1)
        return w

    # ------------------------------------------------------------------
    # set_project
    # ------------------------------------------------------------------

    def set_project(self, path: Path | None) -> None:
        old = self._project_dir
        self._project_dir = path

        if path is None:
            self._episode_sel.set_project(None)
            self._sb = None
            self._gen_btn.setEnabled(False)
            self._global_prompt_edit.clear()
            self._shots_table.setRowCount(0)
            self._status_lbl.setText("")
            return

        self._current_episode = "E1"
        self._episode_sel.set_project(path)

        upstream = storyboard_episode_read_path_in(path, self._current_episode)
        if upstream is None:
            self._sb = None
            self._gen_btn.setEnabled(False)
            self._global_prompt_edit.clear()
            self._shots_table.setRowCount(0)
            return

        try:
            self._sb = json.loads(upstream.read_text(encoding="utf-8"))
        except Exception:
            self._sb = None

        self._gen_btn.setEnabled(self._sb is not None)

        # 若已有产物 → 加载
        self._load_from_disk(path, self._current_episode)

        # 后台 worker 状态
        key = (path, self._current_episode)
        if key in self._workers and self._workers[key] and self._workers[key].isRunning():
            self._status_lbl.setText("● 后台生成中…")
        else:
            self._status_lbl.setText("")

        self._on_project_switched(old, path)

    def _on_episode_changed(self, ep_id: str) -> None:
        self._current_episode = ep_id
        if self._project_dir is None:
            return
        upstream = storyboard_episode_read_path_in(self._project_dir, ep_id)
        if upstream is None:
            self._sb = None
            self._gen_btn.setEnabled(False)
            self._global_prompt_edit.clear()
            self._shots_table.setRowCount(0)
            return
        try:
            self._sb = json.loads(upstream.read_text(encoding="utf-8"))
        except Exception:
            self._sb = None
        self._gen_btn.setEnabled(self._sb is not None)
        self._load_from_disk(self._project_dir, ep_id)

    def _load_from_disk(self, project_dir: Path, episode_id: str) -> None:
        """若 video_prompts/{ep}/global.md + shots.json 已存在则填充 UI。"""
        vdir = video_prompt_dir_in(project_dir, episode_id)
        global_md = vdir / "global.md"
        shots_json = vdir / "shots.json"

        if global_md.is_file():
            try:
                self._global_prompt_edit.setPlainText(
                    global_md.read_text(encoding="utf-8"))
            except OSError:
                pass
        else:
            self._global_prompt_edit.clear()

        if shots_json.is_file():
            try:
                shots = json.loads(shots_json.read_text(encoding="utf-8"))
                self._populate_shots_table(shots)
                return
            except Exception:
                pass
        self._shots_table.setRowCount(0)

    def _populate_shots_table(self, shots: list[dict]) -> None:
        self._shots_table.setRowCount(0)
        for shot in shots:
            row = self._shots_table.rowCount()
            self._shots_table.insertRow(row)
            self._shots_table.setItem(
                row, self._COL_ID,
                QTableWidgetItem(str(shot.get("shotId", shot.get("id", "")))))
            self._shots_table.setItem(
                row, self._COL_PROMPT,
                QTableWidgetItem(str(shot.get("local_prompt", ""))))
            self._shots_table.setItem(
                row, self._COL_DUR,
                QTableWidgetItem(str(shot.get("duration", ""))))
            copy_btn = QPushButton("📋")
            copy_btn.setFixedWidth(32)
            prompt_text = str(shot.get("local_prompt", ""))
            copy_btn.clicked.connect(
                lambda _=False, t=prompt_text: self._copy_to_clipboard(t))
            self._shots_table.setCellWidget(row, self._COL_COPY, copy_btn)

    def _copy_to_clipboard(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        if col == self._COL_COPY:
            item = self._shots_table.item(row, self._COL_PROMPT)
            if item:
                self._copy_to_clipboard(item.text())

    # ------------------------------------------------------------------
    # 生成 / SSE
    # ------------------------------------------------------------------

    def start_generation_if_idle(self) -> None:
        """上游分镜存在 + shots.json 不存在 → 自动触发生成。"""
        if self._project_dir is None:
            return
        upstream = storyboard_episode_read_path_in(
            self._project_dir, self._current_episode)
        if upstream is None:
            return
        shots_json = video_prompt_dir_in(
            self._project_dir, self._current_episode) / "shots.json"
        if shots_json.is_file():
            return
        self._on_generate_clicked()

    def _on_generate_clicked(self) -> None:
        if self._project_dir is None or self._sb is None:
            QMessageBox.warning(self, "上游缺失",
                                "请先在「分镜」阶段生成分镜.json。")
            return
        body = {
            "project_dir": str(self._project_dir),
            "episode_id": self._current_episode,
        }
        self._start_stream("/video_prompt", body)

    def _start_stream(self, path: str, body: dict, params=None) -> None:
        if self._project_dir is None:
            return
        key = (self._project_dir, self._current_episode)
        self._state_by_project[self._project_dir] = "streaming"
        self._gen_btn.hide()
        self._stop_btn.show()
        self._status_lbl.setText("● 流式 · 准备中…")
        worker = StreamWorker(self._client, path, body, params,
                              project_dir=self._project_dir, parent=self)
        self._workers[key] = worker
        worker.event.connect(self._on_sse_event)
        worker.finished_ok.connect(self._on_stream_done_signal)
        worker.failed.connect(self._on_stream_failed)
        worker.start()

    def _stop_stream(self) -> None:
        key = (self._project_dir, self._current_episode)
        w = self._workers.get(key)
        if w and w.isRunning():
            w.stop()
            w.wait(2000)
        self._gen_btn.show()
        self._stop_btn.hide()
        self._status_lbl.setText("")

    def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str) -> None:
        proj = Path(project_dir_str)
        if event_name != "partial":
            return
        # 后台项目：仅发状态变更信号
        if proj != self._project_dir:
            self.projectStateChanged.emit()
            return

        kind = data.get("kind", "")
        saved = data.get("saved", "")

        if kind == "global_md" and saved:
            try:
                text = Path(saved).read_text(encoding="utf-8")
                self._global_prompt_edit.setPlainText(text)
            except OSError:
                pass
            self._status_lbl.setText("● 全局提示词已生成")

        elif kind == "shots_json" and saved:
            try:
                shots = json.loads(Path(saved).read_text(encoding="utf-8"))
                self._populate_shots_table(shots)
            except Exception:
                pass
            self._status_lbl.setText(f"● shots.json 已生成（{self._shots_table.rowCount()}镜）")

        elif saved:
            self._status_lbl.setText(f"● 已生成 {Path(saved).name}")

    def _on_stream_done_signal(self, project_dir_str: str) -> None:
        proj = Path(project_dir_str)
        key = (proj, self._current_episode)
        if key in self._workers:
            self._workers[key] = None
        self._state_by_project[proj] = "done"
        if proj == self._project_dir:
            self._gen_btn.show()
            self._stop_btn.hide()
            self._status_lbl.setText("")
            self.statusMessage.emit("视频提示词全部已生成 ✓")
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str, project_dir_str: str) -> None:
        proj = Path(project_dir_str)
        key = (proj, self._current_episode)
        self._error_by_project[proj] = msg
        self._state_by_project[proj] = "error"
        if key in self._workers:
            self._workers[key] = None
        if proj == self._project_dir:
            self._stop_stream()
            QMessageBox.warning(self, "生成失败",
                                f"视频提示词生成失败：{msg}\n请检查网络或 LLM 配置。")
        self.projectStateChanged.emit()

    def cancel_workers(self) -> None:
        """取消所有运行中的 worker。"""
        for key, w in list(self._workers.items()):
            if w and w.isRunning():
                w.stop()
                w.wait(2000)
        self._workers.clear()

    # ------------------------------------------------------------------
    # 推进
    # ------------------------------------------------------------------

    def _on_advance_clicked(self) -> None:
        self.stageAdvanceRequested.emit(4)   # Stage 5 = index 4
