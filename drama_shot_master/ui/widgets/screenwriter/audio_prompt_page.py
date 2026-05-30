"""AudioPromptPage：配音配乐提示词阶段子面板（Stage 6）。

读取上游 分镜_{ep}.json → 调 /audio_prompt agent → 生成
  audio_prompts/{ep}/voices.json   角色音色卡列表
  audio_prompts/{ep}/sfx_cues.json 分镜配音配乐匹配表

SSE partial 事件 → 实时刷新 _voice_table / _cue_table。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem,
    QAbstractItemView, QSplitter, QWidget, QMessageBox,
    QHeaderView,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._paths import (
    storyboard_episode_read_path_in,
    audio_prompt_dir_in,
)


class AudioPromptPage(_BaseStagePage):
    """Stage 6：配音配乐提示词生成面板（最后阶段）。"""

    # _voice_table 列索引
    _VCOL_NAME = 0
    _VCOL_GENDER_AGE = 1
    _VCOL_TONE = 2
    _VCOL_EMOTION = 3
    _VCOL_TTS = 4

    # _cue_table 列索引
    _CCOL_ID = 0
    _CCOL_LINE = 1
    _CCOL_SFX = 2
    _CCOL_BGM = 3
    _CCOL_COPY = 4

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
            file_pattern_for_status="audio_prompts/{ep}/voices.json")
        self._episode_sel.episodeChanged.connect(self._on_episode_changed)
        root.addWidget(self._episode_sel)

        # 主区：splitter（上：角色音色卡；下：配音配乐匹配表）
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_voice_panel())
        splitter.addWidget(self._build_cue_panel())
        splitter.setSizes([200, 350])
        root.addWidget(splitter, 1)

        # 底部：状态 + 完成按钮（最后阶段，无推进）
        bottom = QHBoxLayout()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #4a9eff")
        bottom.addWidget(self._status_lbl)
        bottom.addStretch(1)
        self._complete_btn = QPushButton("完成项目 ✓")
        self._complete_btn.clicked.connect(self._on_complete_clicked)
        bottom.addWidget(self._complete_btn)
        root.addLayout(bottom)

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._gen_btn = QPushButton("生成配音配乐提示词")
        self._gen_btn.setEnabled(False)
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止")
        self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        bar.addStretch(1)
        return bar

    def _build_voice_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel("角色音色卡（voices.json）："))
        self._voice_table = QTableWidget(0, 5)
        self._voice_table.setHorizontalHeaderLabels(
            ["角色", "性别年龄", "语调", "情绪范围", "TTS风格词"])
        hh = self._voice_table.horizontalHeader()
        hh.setSectionResizeMode(self._VCOL_NAME, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self._VCOL_GENDER_AGE, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self._VCOL_TONE, QHeaderView.Stretch)
        hh.setSectionResizeMode(self._VCOL_EMOTION, QHeaderView.Stretch)
        hh.setSectionResizeMode(self._VCOL_TTS, QHeaderView.Stretch)
        self._voice_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._voice_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.addWidget(self._voice_table, 1)
        return w

    def _build_cue_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel("分镜配音配乐匹配表（sfx_cues.json）："))
        self._cue_table = QTableWidget(0, 5)
        self._cue_table.setHorizontalHeaderLabels(
            ["ID", "角色+台词", "音效", "BGM情绪", "复制"])
        hh = self._cue_table.horizontalHeader()
        hh.setSectionResizeMode(self._CCOL_ID, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self._CCOL_LINE, QHeaderView.Stretch)
        hh.setSectionResizeMode(self._CCOL_SFX, QHeaderView.Stretch)
        hh.setSectionResizeMode(self._CCOL_BGM, QHeaderView.Stretch)
        # 复制列固定宽：ResizeToContents 不量 cellWidget 会塌缩裁切按钮文字
        hh.setSectionResizeMode(self._CCOL_COPY, QHeaderView.Fixed)
        self._cue_table.setColumnWidth(self._CCOL_COPY, 68)
        self._cue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.addWidget(self._cue_table, 1)
        return w

    # ------------------------------------------------------------------
    # set_project
    # ------------------------------------------------------------------

    def _reload_storyboard(self) -> None:
        """从分镜文件重载 _sb + 刷新生成按钮可用性（与 set_project 一致）。
        修复：切 stage 后只 _load_from_disk 会让 _sb stale → 误报"分镜缺失"。"""
        if self._project_dir is None:
            self._sb = None
            self._gen_btn.setEnabled(False)
            return
        upstream = storyboard_episode_read_path_in(
            self._project_dir, self._current_episode)
        self._sb = None
        if upstream is not None:
            try:
                self._sb = json.loads(upstream.read_text(encoding="utf-8"))
            except Exception:
                self._sb = None
        self._gen_btn.setEnabled(self._sb is not None)

    def revalidate_upstream(self) -> None:
        """切回本 stage 时重新校验上游分镜并刷新生成按钮/已有产物。"""
        if self._project_dir is None:
            return
        self._reload_storyboard()                       # 关键：重载 _sb
        self._load_from_disk(self._project_dir, self._current_episode)

    def set_project(self, path: Path | None) -> None:
        old = self._project_dir
        self._project_dir = path

        if path is None:
            self._episode_sel.set_project(None)
            self._sb = None
            self._gen_btn.setEnabled(False)
            self._voice_table.setRowCount(0)
            self._cue_table.setRowCount(0)
            self._status_lbl.setText("")
            return

        self._current_episode = "E1"
        self._episode_sel.set_project(path)

        upstream = storyboard_episode_read_path_in(path, self._current_episode)
        if upstream is None:
            self._sb = None
            self._gen_btn.setEnabled(False)
            self._voice_table.setRowCount(0)
            self._cue_table.setRowCount(0)
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
            self._voice_table.setRowCount(0)
            self._cue_table.setRowCount(0)
            return
        try:
            self._sb = json.loads(upstream.read_text(encoding="utf-8"))
        except Exception:
            self._sb = None
        self._gen_btn.setEnabled(self._sb is not None)
        self._load_from_disk(self._project_dir, ep_id)

    def _load_from_disk(self, project_dir: Path, episode_id: str) -> None:
        """若 audio_prompts/{ep}/voices.json + sfx_cues.json 已存在则填充 UI。"""
        adir = audio_prompt_dir_in(project_dir, episode_id)
        voices_json = adir / "voices.json"
        cues_json = adir / "sfx_cues.json"

        if voices_json.is_file():
            try:
                voices = json.loads(voices_json.read_text(encoding="utf-8"))
                self._populate_voices(voices)
            except Exception:
                self._voice_table.setRowCount(0)
        else:
            self._voice_table.setRowCount(0)

        if cues_json.is_file():
            try:
                cues = json.loads(cues_json.read_text(encoding="utf-8"))
                self._populate_cues(cues)
            except Exception:
                self._cue_table.setRowCount(0)
        else:
            self._cue_table.setRowCount(0)

    def _populate_voices(self, voices) -> None:
        # 兼容后端写入的包裹结构 {"voices": [...]} 与裸数组 [...]
        if isinstance(voices, dict):
            voices = voices.get("voices", [])
        self._voice_table.setRowCount(0)
        for v in voices:
            row = self._voice_table.rowCount()
            self._voice_table.insertRow(row)
            self._voice_table.setItem(
                row, self._VCOL_NAME,
                QTableWidgetItem(str(v.get("name", ""))))
            gender_age = v.get("gender", "")
            age_range = v.get("age_range", "")
            if age_range:
                gender_age = f"{gender_age} {age_range}".strip()
            self._voice_table.setItem(
                row, self._VCOL_GENDER_AGE,
                QTableWidgetItem(gender_age))
            self._voice_table.setItem(
                row, self._VCOL_TONE,
                QTableWidgetItem(str(v.get("tone_description", ""))))
            emotion_range = v.get("emotion_range", [])
            if isinstance(emotion_range, list):
                emotion_str = "、".join(emotion_range)
            else:
                emotion_str = str(emotion_range)
            self._voice_table.setItem(
                row, self._VCOL_EMOTION,
                QTableWidgetItem(emotion_str))
            self._voice_table.setItem(
                row, self._VCOL_TTS,
                QTableWidgetItem(str(v.get("tts_style_prompt", ""))))

    def _populate_cues(self, cues) -> None:
        # 兼容后端写入的包裹结构 {"cues": [...]} 与裸数组 [...]
        if isinstance(cues, dict):
            cues = cues.get("cues", [])
        self._cue_table.setRowCount(0)
        for cue in cues:
            row = self._cue_table.rowCount()
            self._cue_table.insertRow(row)
            # 实际后端键：shot_id / speaker / dialogue / sfx / bgm_emotion
            self._cue_table.setItem(
                row, self._CCOL_ID,
                QTableWidgetItem(str(cue.get("shot_id",
                                             cue.get("shotId",
                                                     cue.get("id", ""))))))
            # 角色+台词："角色名：台词" 格式
            char_name = str(cue.get("speaker", cue.get("character", "")))
            line = str(cue.get("dialogue", cue.get("line", "")))
            if char_name and char_name != "-" and line and line != "-":
                line_text = f"{char_name}：{line}"
            elif line and line != "-":
                line_text = line
            else:
                line_text = "—"
            self._cue_table.setItem(
                row, self._CCOL_LINE,
                QTableWidgetItem(line_text))
            self._cue_table.setItem(
                row, self._CCOL_SFX,
                QTableWidgetItem(str(cue.get("sfx", cue.get("sound_effect", "")))))
            self._cue_table.setItem(
                row, self._CCOL_BGM,
                QTableWidgetItem(str(cue.get("bgm_emotion",
                                             cue.get("bgm_mood",
                                                     cue.get("bgm", ""))))))
            copy_btn = QPushButton("复制")
            copy_btn.setMinimumWidth(60)
            copy_text = str(cue.get("dialogue", cue.get("line", "")))
            copy_btn.clicked.connect(
                lambda _=False, t=copy_text: self._copy_to_clipboard(t))
            self._cue_table.setCellWidget(row, self._CCOL_COPY, copy_btn)

    def _copy_to_clipboard(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        from drama_shot_master.ui.widgets.toast import show_toast
        QApplication.clipboard().setText(text)
        show_toast(self, "✓ 已复制到剪贴板")     # 可见轻提示
        self.statusMessage.emit("✓ 已复制到剪贴板")

    # ------------------------------------------------------------------
    # 生成 / SSE
    # ------------------------------------------------------------------

    def start_generation_if_idle(self) -> None:
        """上游分镜存在 + voices.json 不存在 → 自动触发生成。"""
        if self._project_dir is None:
            return
        upstream = storyboard_episode_read_path_in(
            self._project_dir, self._current_episode)
        if upstream is None:
            return
        voices_json = audio_prompt_dir_in(
            self._project_dir, self._current_episode) / "voices.json"
        if voices_json.is_file():
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
        self._start_stream("/audio_prompt", body)

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

        file_path = data.get("file", "")
        content = data.get("content", "")

        if "voices.json" in file_path and content:
            try:
                voices = json.loads(content)
                self._populate_voices(voices)
                self._status_lbl.setText(f"● 音色卡已生成（{self._voice_table.rowCount()}个角色）")
            except Exception:
                pass

        elif "sfx_cues.json" in file_path and content:
            try:
                cues = json.loads(content)
                self._populate_cues(cues)
                self._status_lbl.setText(f"● 配乐匹配表已生成（{self._cue_table.rowCount()}条）")
            except Exception:
                pass

        else:
            saved = data.get("saved", "")
            if saved:
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
            self.statusMessage.emit("配音配乐提示词全部已生成 ✓")
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
                                f"配音配乐提示词生成失败：{msg}\n请检查网络或 LLM 配置。")
        self.projectStateChanged.emit()

    def cancel_workers(self) -> None:
        """取消所有运行中的 worker。"""
        for key, w in list(self._workers.items()):
            if w and w.isRunning():
                w.stop()
                w.wait(2000)
        self._workers.clear()

    # ------------------------------------------------------------------
    # 完成（最后阶段，无推进按钮）
    # ------------------------------------------------------------------

    def _on_complete_clicked(self) -> None:
        self.statusMessage.emit("项目已完成 ✓")
