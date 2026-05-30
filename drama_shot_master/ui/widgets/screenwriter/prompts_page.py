"""PromptsPage：提示词阶段子面板（已适配 worker dict + 3-arg StreamWorker）。

顶 _ParamBar + 上游 banner + 主区 QSplitter（左 _ProductTree + 右编辑器预览）。
partial 事件 → 树状态点变 ✓；落盘后右侧预览自动刷新。
重生 = 清空 prompts/ + purge_downstream。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QPlainTextEdit,
    QComboBox, QCheckBox, QMessageBox, QWidget, QLineEdit,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._product_tree import _ProductTree
from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector
from drama_shot_master.ui.widgets.screenwriter._paths import (
    storyboard_episode_read_path_in, episode_prompts_dir_in,
)
from screenwriter_agent.core.atomic_write import atomic_write_text


class PromptsPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._prompts_dir: Path | None = None
        self._current_episode: str = "E1"
        self._sb: dict | None = None
        self._current_file: Path | None = None
        self._original_text: str = ""
        self._last_load_mtime: float = 0.0
        self._build_ui()
        self.set_project(None)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        self._episode_selector = _EpisodeSelector(
            file_pattern_for_status="prompts/{ep}")
        self._episode_selector.episodeChanged.connect(self._on_episode_changed)
        root.addWidget(self._episode_selector)
        self._upstream_banner = _UpstreamBanner()
        root.addWidget(self._upstream_banner)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 540])
        root.addWidget(splitter, 1)

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._char_refs_chk = QCheckBox("角色参考")
        self._char_refs_chk.setChecked(True)
        self._char_refs_chk.toggled.connect(self._rebuild_tree)
        bar.addWidget(self._char_refs_chk)
        self._quality_chk = QCheckBox("画质增强")
        self._quality_chk.setChecked(True)
        bar.addWidget(self._quality_chk)
        bar.addWidget(QLabel("风格补充:"))
        self._style_extra_edit = QLineEdit()
        self._style_extra_edit.setMaximumWidth(160)
        self._style_extra_edit.setPlaceholderText("如：电影感/赛博朋克…")
        bar.addWidget(self._style_extra_edit)
        bar.addWidget(QLabel("负向:"))
        self._negative_combo = QComboBox()
        self._negative_combo.addItems(["标准 SDXL", "无", "禁手部", "禁文字"])
        bar.addWidget(self._negative_combo)
        bar.addStretch(1)
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        self._gen_btn = QPushButton("生成提示词")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止"); self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        return bar

    def _default_grid_mode(self) -> str:
        """从 cfg（经 client 注入）读分镜默认宫格，缺省四宫格。"""
        cfg = getattr(self._client, "_cfg", None)
        val = getattr(cfg, "prompts_default_grid", "4") if cfg else "4"
        return val if val in ("single", "4", "9") else "4"

    def _build_left(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        self._group_editor = _GridGroupEditor(
            default_grid_mode=self._default_grid_mode())
        self._group_editor.generateAll.connect(self._on_generate_clicked)
        self._group_editor.generateGroup.connect(self._on_generate_group)
        self._group_editor.groupsChanged.connect(self._rebuild_tree)
        v.addWidget(self._group_editor)
        self._tree = _ProductTree()
        self._tree.fileActivated.connect(self._on_file_activated)
        v.addWidget(self._tree, 1)
        btn = QPushButton("📂 打开 prompts/")
        btn.clicked.connect(self._on_open_prompts_dir)
        v.addWidget(btn)
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        self._preview_label = QLabel("预览：（点左侧文件）")
        v.addWidget(self._preview_label)
        self._editor = QPlainTextEdit()
        self._editor.textChanged.connect(self._on_editor_changed)
        v.addWidget(self._editor, 1)
        bar = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_clicked)
        bar.addWidget(self._save_btn)
        bar.addStretch(1)
        self._complete_btn = QPushButton("完成 ✓")
        self._complete_btn.clicked.connect(self._on_complete_clicked)
        bar.addWidget(self._complete_btn)
        self._advance_btn = QPushButton("推进到视频提示词 →")
        self._advance_btn.clicked.connect(self._on_advance_to_video)
        bar.addWidget(self._advance_btn)
        v.addLayout(bar)
        return w

    # —— set_project / try_release ——

    def set_project(self, path: Path | None):
        if self._project_dir is not None and not self.try_release():
            return
        old = self._project_dir
        self._project_dir = path
        if path is None:
            self._episode_selector.set_project(None)
            self._upstream_banner.hide_banner()
            self._prompts_dir = None
            self._sb = None
            self._current_file = None
            self._tree.clear()
            self._tree.tree_items = {}
            self._editor.blockSignals(True); self._editor.clear()
            self._editor.blockSignals(False)
            self._original_text = ""
            for b in (self._gen_btn, self._save_btn, self._complete_btn):
                b.setEnabled(False)
            return
        # 自检上游：按当前集读分镜
        self._current_episode = "E1"
        self._episode_selector.set_project(path)
        upstream = storyboard_episode_read_path_in(path, self._current_episode)
        if upstream is None:
            self._upstream_banner.show_missing(
                stage_name="分镜", expected_file="分镜.json")
            self._sb = None
            self._gen_btn.setEnabled(False)
            self._complete_btn.setEnabled(False)
            self._tree.clear()
            self._tree.tree_items = {}
            self._prompts_dir = None
            return
        else:
            self._upstream_banner.hide_banner()
        self._prompts_dir = episode_prompts_dir_in(path, self._current_episode)
        try:
            self._sb = json.loads(upstream.read_text(encoding="utf-8"))
        except Exception:
            self._sb = None
        if self._sb is not None:
            self._group_editor.set_shots(
                [str(s.get("shotId") or s.get("shot_id") or s.get("id") or "")
                 for s in (self._sb.get("shots") or [])])
        self._rebuild_tree()
        self._gen_btn.setEnabled(self._sb is not None)
        self._complete_btn.setEnabled(True)
        self._editor.blockSignals(True); self._editor.clear()
        self._editor.blockSignals(False)
        self._current_file = None
        self._original_text = ""
        self._preview_label.setText("预览：（点左侧文件）")
        # 后台 worker 显示
        if path in self._workers and self._workers[path] and self._workers[path].isRunning():
            self._stream_label.setText("● 后台生成中…")
        else:
            self._stream_label.setText("")
        self._on_project_switched(old, path)

    def _on_episode_changed(self, ep_id: str) -> None:
        self._current_episode = ep_id
        if self._project_dir is None:
            return
        upstream = storyboard_episode_read_path_in(self._project_dir, ep_id)
        if upstream is None:
            self._upstream_banner.show_missing(
                stage_name="分镜", expected_file=f"分镜_{ep_id}.json")
            self._sb = None
            self._gen_btn.setEnabled(False)
            self._prompts_dir = None
            self._tree.clear()
            self._tree.tree_items = {}
            return
        self._upstream_banner.hide_banner()
        self._prompts_dir = episode_prompts_dir_in(self._project_dir, ep_id)
        try:
            self._sb = json.loads(upstream.read_text(encoding="utf-8"))
        except Exception:
            self._sb = None
        if self._sb is not None:
            self._group_editor.set_shots(
                [str(s.get("shotId") or s.get("shot_id") or s.get("id") or "")
                 for s in (self._sb.get("shots") or [])])
        self._rebuild_tree()
        self._gen_btn.setEnabled(self._sb is not None)
        self._complete_btn.setEnabled(True)
        self._current_file = None
        self._editor.blockSignals(True); self._editor.clear()
        self._editor.blockSignals(False)
        self._original_text = ""

    def revalidate_upstream(self) -> None:
        """切回本 stage 时重新校验上游分镜并刷新 banner（修会话内生成后误报缺失）。"""
        if self._project_dir is None:
            return
        self._on_episode_changed(self._current_episode)

    def try_release(self) -> bool:
        if not self._is_dirty():
            return True
        ans = QMessageBox.question(
            self, "提示词文件有未保存改动",
            "切换前是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            self._on_save_clicked()
            return True
        if ans == QMessageBox.Discard:
            return True
        return False

    def _is_dirty(self) -> bool:
        return (self._current_file is not None
                and self._editor.toPlainText() != self._original_text)

    # —— 树/预览 ——

    def _rebuild_tree(self, *_):
        if self._prompts_dir is None or self._sb is None:
            self._tree.clear()
            self._tree.tree_items = {}
            return
        self._tree.build_from_sb(
            self._prompts_dir, self._sb,
            groups=self._group_editor.groups(),
            include_character_refs=self._char_refs_chk.isChecked())

    def _on_file_activated(self, path: Path):
        if self._is_dirty() and not self.try_release():
            return
        if not path.is_file():
            self._preview_label.setText(f"预览：{path.name}（未生成）")
            self._editor.blockSignals(True); self._editor.clear()
            self._editor.blockSignals(False)
            self._current_file = None
            self._original_text = ""
            self._save_btn.setEnabled(False)
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "打开失败", str(e))
            return
        self._current_file = path
        self._original_text = text
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        try:
            self._last_load_mtime = path.stat().st_mtime
        except OSError:
            pass
        self._preview_label.setText(f"预览：{path.name}")
        self._save_btn.setEnabled(False)

    def _on_editor_changed(self):
        self._save_btn.setEnabled(self._is_dirty())

    def _on_save_clicked(self):
        if self._current_file is None:
            return
        try:
            atomic_write_text(self._current_file, self._editor.toPlainText())
            self._original_text = self._editor.toPlainText()
            self._last_load_mtime = self._current_file.stat().st_mtime
            self._save_btn.setEnabled(False)
            self.statusMessage.emit(f"{self._current_file.name} 已保存")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_open_prompts_dir(self):
        if self._prompts_dir and self._prompts_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._prompts_dir)))

    def _on_complete_clicked(self):
        # 不切阶段；只发完成信号
        self.statusMessage.emit("项目已完成 ✓")
        self.projectStateChanged.emit()

    def _on_advance_to_video(self) -> None:
        self.stageAdvanceRequested.emit(4)   # Stage 5 = index 4

    def start_generation_if_idle(self) -> None:
        """上游 分镜.json 在 + prompts/E{id}/ 空 → 自动跑生成。"""
        if self._project_dir is None:
            return
        upstream = storyboard_episode_read_path_in(
            self._project_dir, self._current_episode)
        if upstream is None:
            return
        prompts_dir = episode_prompts_dir_in(self._project_dir, self._current_episode)
        if prompts_dir.is_dir() and any(prompts_dir.iterdir()):
            return
        self._on_generate_clicked()

    # —— 生成 / SSE ——

    def _on_generate_clicked(self):
        if self._project_dir is None or self._sb is None:
            QMessageBox.warning(self, "上游缺失",
                                  "请先在「分镜」阶段生成分镜.json。")
            return
        # 重生确认
        params = None
        if self._prompts_dir and self._prompts_dir.exists() and \
                any(self._prompts_dir.iterdir()):
            ans = QMessageBox.question(
                self, "重新生成",
                "重新生成会清空 prompts/。继续？",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            params = {"purge_downstream": "true"}
            shutil.rmtree(self._prompts_dir, ignore_errors=True)
        body = {
            "project_dir": str(self._project_dir),
            "episode_id": self._current_episode,
            "options": {
                "include_character_refs": self._char_refs_chk.isChecked(),
                "style_extra": self._style_extra_edit.text().strip(),
                "negative_preset": self._negative_combo.currentText(),
                "quality_boost": self._quality_chk.isChecked(),
                "groups": self._group_editor.groups(),
            },
        }
        self._rebuild_tree()       # 现 prompts/ 已清空，树全 ○
        self._start_stream("/prompts", body, params)

    def _on_generate_group(self, index: int):
        if self._project_dir is None or self._sb is None:
            QMessageBox.warning(self, "上游缺失",
                                 "请先在「分镜」阶段生成分镜.json。")
            return
        body = {
            "project_dir": str(self._project_dir),
            "episode_id": self._current_episode,
            "options": {
                "include_character_refs": False,
                "style_extra": self._style_extra_edit.text().strip(),
                "negative_preset": self._negative_combo.currentText(),
                "quality_boost": self._quality_chk.isChecked(),
                "groups": self._group_editor.groups(),
                "only_group_index": index,
            },
        }
        self._start_stream("/prompts", body, None)

    def _start_stream(self, path: str, body: dict, params=None):
        if self._project_dir is None:
            return
        self._state_by_project[self._project_dir] = "streaming"
        self._buf_by_project.setdefault(self._project_dir, "")
        self._gen_btn.hide(); self._stop_btn.show()
        self._stream_label.setText("● 流式 · 准备中…")
        worker = StreamWorker(self._client, path, body, params,
                               project_dir=self._project_dir, parent=self)
        self._workers[self._project_dir] = worker
        worker.event.connect(self._on_sse_event)
        worker.finished_ok.connect(self._on_stream_done_signal)
        worker.failed.connect(self._on_stream_failed)
        worker.start()

    def _stop_stream(self):
        w = self._active_worker()
        if w and w.isRunning():
            w.stop()
            w.wait(2000)
        self._gen_btn.show(); self._stop_btn.hide()
        self._stream_label.setText("")

    def _on_sse_event(self, event_name: str, data: dict, project_dir_str: str):
        proj = Path(project_dir_str)
        if event_name == "partial":
            saved = data.get("saved", "")
            kind = data.get("kind", "")
            # 后台项目：仅记 state，不动 UI
            if proj != self._project_dir:
                self.projectStateChanged.emit()
                return
            if saved:
                p = Path(saved)
                self._tree.set_status(p, "done")
                self._stream_label.setText(f"● 已生成 {p.name}（{kind}）")
                if self._current_file == p and not self._is_dirty():
                    self._on_file_activated(p)

    def _on_stream_done_signal(self, project_dir_str: str):
        proj = Path(project_dir_str)
        if proj in self._workers:
            self._workers[proj] = None
        self._state_by_project[proj] = "done"
        if proj == self._project_dir:
            self._gen_btn.show(); self._stop_btn.hide()
            self._stream_label.setText("")
            self.statusMessage.emit("提示词全部已生成 ✓")
        self.projectStateChanged.emit()

    def _on_stream_failed(self, msg: str, project_dir_str: str):
        proj = Path(project_dir_str)
        self._error_by_project[proj] = msg
        self._state_by_project[proj] = "error"
        if proj in self._workers:
            self._workers[proj] = None
        if proj == self._project_dir:
            self._stop_stream()
            QMessageBox.warning(self, "生成失败",
                                 f"提示词生成失败：{msg}\n请检查网络或 LLM 配置。")
        self.projectStateChanged.emit()
