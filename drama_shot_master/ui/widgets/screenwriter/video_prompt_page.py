"""VideoPromptPage：视频提示词阶段子面板（Stage 5）。

读取上游 分镜_{ep}.json → 调 /video_prompt agent → 生成
  video_prompts/{ep}/shots.json  {global_prompt, shots:[...]} 单文件

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
    QHeaderView, QComboBox,
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
        bar.addWidget(QLabel("模板:"))
        self._template_combo = QComboBox()
        # (显示名, id)；新 LTX2.3 增强默认在前
        self._template_combo.addItem("LTX2.3 增强（画面/运镜/音效）", "ltx")
        self._template_combo.addItem("简洁（Camera:…）", "simple")
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        bar.addWidget(self._template_combo)
        bar.addWidget(QLabel("语言:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("English", "en")   # 默认全英文
        self._lang_combo.addItem("中文", "zh")
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        bar.addWidget(self._lang_combo)
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

    # —— 模板 / 语言 选择 + 按项目持久化 ————————————————————

    def current_template_id(self) -> str:
        return self._template_combo.currentData()

    def current_language(self) -> str:
        return self._lang_combo.currentData()

    def _set_combo_by_data(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def set_template_id(self, tid: str) -> None:
        self._set_combo_by_data(self._template_combo, tid)
        self._save_template_config()

    def set_language(self, lang: str) -> None:
        self._set_combo_by_data(self._lang_combo, lang)
        self._save_template_config()

    def _on_template_changed(self, *_):
        self._save_template_config()

    def _on_language_changed(self, *_):
        self._save_template_config()

    def _config_path(self):
        if self._project_dir is None:
            return None
        return self._project_dir / "video_prompts" / "_config.json"

    def _save_template_config(self) -> None:
        cp = self._config_path()
        if cp is None:
            return
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps({
                "template": self.current_template_id(),
                "language": self.current_language(),
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load_template_config(self) -> None:
        cp = self._config_path()
        if cp is None or not cp.is_file():
            return
        try:
            cfg = json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            return
        if cfg.get("template"):
            self._set_combo_by_data(self._template_combo, cfg["template"])
        if cfg.get("language"):
            self._set_combo_by_data(self._lang_combo, cfg["language"])

    def _build_global_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel("全局画风提示词："))
        head.addStretch(1)
        self._global_copy_btn = QPushButton("复制")
        self._global_copy_btn.clicked.connect(self._on_copy_global)
        head.addWidget(self._global_copy_btn)
        v.addLayout(head)
        self._global_prompt_edit = QPlainTextEdit()
        self._global_prompt_edit.setPlaceholderText("生成后自动填充…")
        self._global_prompt_edit.setMaximumHeight(120)
        v.addWidget(self._global_prompt_edit)
        return w

    def _on_copy_global(self) -> None:
        self._copy_to_clipboard(self._global_prompt_edit.toPlainText())

    @staticmethod
    def _strip_global_header(text: str) -> str:
        """去掉 global.md 历史写入的 '# global_prompt' 头，避免污染复制。"""
        t = text.lstrip()
        if t.startswith("# global_prompt"):
            t = t[len("# global_prompt"):]
        return t.strip()

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
        # 复制列固定宽：ResizeToContents 不量 cellWidget 会塌缩裁切按钮文字
        self._shots_table.horizontalHeader().setSectionResizeMode(
            self._COL_COPY, QHeaderView.Fixed)
        self._shots_table.setColumnWidth(self._COL_COPY, 68)
        self._shots_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._shots_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._shots_table.cellClicked.connect(self._on_table_cell_clicked)
        v.addWidget(self._shots_table, 1)
        return w

    # ------------------------------------------------------------------
    # set_project
    # ------------------------------------------------------------------

    def revalidate_upstream(self) -> None:
        """切回本 stage 时重新校验上游分镜并刷新生成按钮/已有产物。"""
        if self._project_dir is None:
            return
        self._load_from_disk(self._project_dir, self._current_episode)

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
        self._load_template_config()        # 按项目恢复模板/语言选择

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
        """读 video_prompts/{ep}/shots.json：
        - 新格式：对象 {global_prompt, shots:[...]} → 字段取值
        - 旧格式：裸数组 [...] + 同目录 global.md → 回退读
        """
        vdir = video_prompt_dir_in(project_dir, episode_id)
        shots_json = vdir / "shots.json"
        global_md = vdir / "global.md"

        global_text = ""
        shots: list = []
        if shots_json.is_file():
            try:
                data = json.loads(shots_json.read_text(encoding="utf-8"))
            except Exception:
                data = None
            if isinstance(data, dict):                  # 新对象格式
                global_text = str(data.get("global_prompt", ""))
                shots = data.get("shots", []) or []
            elif isinstance(data, list):                # 旧裸数组
                shots = data
                if global_md.is_file():
                    try:
                        global_text = self._strip_global_header(
                            global_md.read_text(encoding="utf-8"))
                    except OSError:
                        global_text = ""
        elif global_md.is_file():                       # 仅有旧 global.md
            try:
                global_text = self._strip_global_header(
                    global_md.read_text(encoding="utf-8"))
            except OSError:
                global_text = ""

        if global_text:
            self._global_prompt_edit.setPlainText(global_text)
        else:
            self._global_prompt_edit.clear()
        self._populate_shots_table(shots)

    def _populate_shots_table(self, shots: list[dict]) -> None:
        self._shots_table.setRowCount(0)
        for shot in shots:
            row = self._shots_table.rowCount()
            self._shots_table.insertRow(row)
            # 实际后端键：shot_id / local_prompt / duration_s（兼容旧 shotId/duration）
            self._shots_table.setItem(
                row, self._COL_ID,
                QTableWidgetItem(str(shot.get("shot_id",
                                              shot.get("shotId",
                                                       shot.get("id", ""))))))
            self._shots_table.setItem(
                row, self._COL_PROMPT,
                QTableWidgetItem(str(shot.get("local_prompt", ""))))
            self._shots_table.setItem(
                row, self._COL_DUR,
                QTableWidgetItem(str(shot.get("duration_s",
                                              shot.get("duration", "")))))
            copy_btn = QPushButton("复制")
            copy_btn.setMinimumWidth(60)
            prompt_text = str(shot.get("local_prompt", ""))
            copy_btn.clicked.connect(
                lambda _=False, t=prompt_text: self._copy_to_clipboard(t))
            self._shots_table.setCellWidget(row, self._COL_COPY, copy_btn)

    def _copy_to_clipboard(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        from drama_shot_master.ui.widgets.toast import show_toast
        QApplication.clipboard().setText(text)
        show_toast(self, "✓ 已复制到剪贴板")     # 可见轻提示
        self.statusMessage.emit("✓ 已复制到剪贴板")

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        # 复制改由单元格内「复制」按钮处理，避免与 cellClicked 双重触发
        return

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
            "options": {
                "template_id": self.current_template_id(),
                "language": self.current_language(),
            },
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

        # 路由 partial 事件形如 {"file": "...relative...", "content": "..."}
        fname = data.get("file", "") or data.get("saved", "")
        content = data.get("content", "")

        if fname.endswith("shots.json"):
            try:
                data = json.loads(content) if content else json.loads(
                    Path(fname).read_text(encoding="utf-8"))
            except Exception:
                data = None
            if isinstance(data, dict):
                self._global_prompt_edit.setPlainText(
                    str(data.get("global_prompt", "")))
                self._populate_shots_table(data.get("shots", []) or [])
            elif isinstance(data, list):
                self._populate_shots_table(data)
            self._status_lbl.setText(
                f"● shots.json 已生成（{self._shots_table.rowCount()}镜）")

        elif fname.endswith("global.md"):
            # 兼容旧后端仍发 global.md 事件的情形（回退）
            if not content:
                try:
                    content = Path(fname).read_text(encoding="utf-8")
                except OSError:
                    content = ""
            self._global_prompt_edit.setPlainText(
                self._strip_global_header(content))
            self._status_lbl.setText("● 全局提示词已生成")

        elif fname:
            self._status_lbl.setText(f"● 已生成 {Path(fname).name}")

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
