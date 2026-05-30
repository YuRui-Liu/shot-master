"""StoryboardPage：分镜阶段子面板。

顶 _ParamBar + _UpstreamBanner + 全局头（标题/比例/时长/globalStyle/characters）+ 中表格 + 底 _WarningsBanner + ActionBar。
流式期间不解析、只显字数；done 时一次性解析 + 渲染表格。
重生确认 + purge_downstream；dirty 切换护栏。

T7：worker dict 模式（_workers[project_dir]）+ _UpstreamBanner 自检上游 剧本.md。
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
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector
from drama_shot_master.ui.widgets.screenwriter._paths import (
    script_episode_read_path_in, storyboard_episode_path_in,
    storyboard_episode_read_path_in,
)
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
        self._current_episode: str = "E1"
        # Legacy single-worker ref kept for _stop_stream compatibility;
        # canonical store is self._workers[project_dir] (from _BaseStagePage).
        self._worker: StreamWorker | None = None
        self._state: str = "idle"
        self._character_rows: list[_CharacterRow] = []
        self._shots_model = _ShotsTableModel()
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        self._episode_selector = _EpisodeSelector(
            file_pattern_for_status="分镜_{ep}.json")
        self._episode_selector.episodeChanged.connect(self._on_episode_changed)
        root.addWidget(self._episode_selector)
        self._upstream_banner = _UpstreamBanner()
        root.addWidget(self._upstream_banner)
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
        old = self._project_dir
        self._project_dir = path
        if path is None:
            self._episode_selector.set_project(None)
            self._upstream_banner.hide_banner()
            self._sb_path = None
            self._sb = None
            self._set_sb_to_ui(None)
            self._state = "idle"
            for b in (self._gen_btn, self._save_btn, self._view_json_btn,
                       self._advance_btn):
                b.setEnabled(False)
            return
        # 重置到 E1
        self._current_episode = "E1"
        self._episode_selector.set_project(path)
        # 自检上游：用当前集
        upstream = script_episode_read_path_in(path, self._current_episode)
        if upstream is None:
            self._upstream_banner.show_missing(
                stage_name="剧本", expected_file="剧本.md")
            self._gen_btn.setEnabled(False)
        else:
            self._upstream_banner.hide_banner()
            self._gen_btn.setEnabled(True)
        # _sb_path：优先已有文件（向后兼容 分镜.json）
        read_path = storyboard_episode_read_path_in(path, self._current_episode)
        self._sb_path = read_path if read_path is not None else storyboard_episode_path_in(path, self._current_episode)
        self._load_from_disk()
        self._view_json_btn.setEnabled(self._sb is not None)
        # 检查 active worker（key 为 tuple (project_dir, episode_id)）
        worker_key = (path, self._current_episode)
        if worker_key in self._workers and self._workers[worker_key] and self._workers[worker_key].isRunning():
            self._stream_label.setText(
                f"● 流式 · 已 {len(self._buf_by_project.get(path, ''))} 字（后台跑）")
        else:
            self._stream_label.setText("")
        self._on_project_switched(old, path)

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

    def _on_episode_changed(self, ep_id: str) -> None:
        if self._dirty and not self.try_release():
            self._episode_selector.blockSignals(True)
            self._episode_selector.select_episode(self._current_episode)
            self._episode_selector.blockSignals(False)
            return
        self._current_episode = ep_id
        if self._project_dir is None:
            return
        upstream = script_episode_read_path_in(self._project_dir, ep_id)
        if upstream is None:
            self._upstream_banner.show_missing(
                stage_name="剧本", expected_file=f"剧本_{ep_id}.md")
            self._gen_btn.setEnabled(False)
        else:
            self._upstream_banner.hide_banner()
            self._gen_btn.setEnabled(True)
        read_path = storyboard_episode_read_path_in(self._project_dir, ep_id)
        self._sb_path = read_path if read_path is not None else storyboard_episode_path_in(self._project_dir, ep_id)
        self._load_from_disk()

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

    def start_generation_if_idle(self) -> None:
        """分镜阶段不自动生成：时长范围/密度需用户先配置，再手动点「生成分镜」。

        （上游 banner 的刷新由 panel 监听 stageChanged → revalidate_upstream 负责，
        不在此处触发生成。）
        """
        return

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
        script_path = script_episode_read_path_in(self._project_dir, self._current_episode)
        if script_path is None:
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
            "episode_id": self._current_episode,
            "options": {
                "aspect_ratio": self._aspect_combo.currentText(),
                "fps": self._fps_spin.value(),
                "shot_duration_default": self._default_dur_spin.value(),
                "density": self._density_combo.currentText(),
            },
        }
        self._buf_by_project[self._project_dir] = ""
        self._start_stream("/storyboard", body, params)

    def _start_stream(self, path, body, params=None):
        if self._project_dir is None:
            return
        self._state_by_project[self._project_dir] = "streaming"
        self._buf_by_project.setdefault(self._project_dir, "")
        self._state = "streaming"
        self._gen_btn.hide(); self._stop_btn.show()
        self._stream_label.setText("● 流式 · 已 0 字")
        self._save_btn.setEnabled(False)
        self._advance_btn.setEnabled(False)
        worker = StreamWorker(self._client, path, body, params,
                               project_dir=self._project_dir, parent=self)
        self._workers[(self._project_dir, self._current_episode)] = worker
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
            for k in list(self._workers.keys()):
                if (isinstance(k, tuple) and k[0] == self._project_dir) or k == self._project_dir:
                    self._workers[k] = None
        self._state = "idle"
        self._worker = None
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")

    def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
        proj = Path(project_dir_str)
        if event_name == "delta":
            self._buf_by_project[proj] = self._buf_by_project.get(proj, "") + data.get("text", "")
        elif event_name == "status":
            pass   # 不缓存 phase
        elif event_name == "done":
            # 落盘已由 agent 端做；这里只解析 result + warnings
            sb = data.get("result")
            warns = data.get("warnings", [])
            if sb is not None and proj == self._project_dir:
                # 前台：更新表格
                self._sb = sb
                self._warnings = warns or []
                self._set_sb_to_ui(sb)
                self._dirty = False
                self._save_btn.setEnabled(False)
                self._state = "done"
                self._advance_btn.setEnabled(True)
            elif sb is not None:
                # 后台：仅记 state，让 TaskManager 刷新
                self._state_by_project[proj] = "done"
            self.projectStateChanged.emit()
        elif event_name == "error":
            self._error_by_project[proj] = data.get("hint") or data.get("message", "")
            self._state_by_project[proj] = "error"
            self.projectStateChanged.emit()

        if proj != self._project_dir:
            return

        if event_name == "delta":
            self._stream_label.setText(
                f"● 流式 · 已 {len(self._buf_by_project.get(proj, ''))} 字")
        elif event_name == "status":
            phase = data.get("phase", "")
            if phase == "validating":
                self._stream_label.setText(
                    f"● 流式 · 已 {len(self._buf_by_project.get(proj, ''))} 字 · 修复中…")
        elif event_name == "error":
            code = data.get("code", "")
            hint = self._error_by_project.get(proj, "")
            details = data.get("details", {})
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtWidgets import QMessageBox
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

    def _on_stream_done_signal(self, project_dir_str: str):
        proj = Path(project_dir_str)
        if proj in self._workers:
            self._workers[proj] = None
        if proj == self._project_dir:
            self._worker = None
            self._gen_btn.show(); self._stop_btn.hide()
            self._stream_label.setText("")
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str, project_dir_str: str):
        proj = Path(project_dir_str)
        self._error_by_project[proj] = msg
        self._state_by_project[proj] = "error"
        if proj in self._workers:
            self._workers[proj] = None
        if proj == self._project_dir:
            self._worker = None
            self._stop_stream()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "生成失败",
                                 f"分镜生成失败：{msg}\n请检查网络或 LLM 配置。")
        self.projectStateChanged.emit()
