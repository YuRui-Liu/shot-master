"""SoundtrackEditor：单集配乐编辑器（QWidget）。Phase 4c：DAW 多轨时间轴替换 4 tab 体系。

输出路径：任务 output_dir → cfg.soundtrack_output_dir → cfg.video_output_dir/soundtrack。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar,
    QFileDialog, QMessageBox, QScrollBar,
)

from drama_shot_master.ui.worker import FunctionWorker
from drama_shot_master.core.dialogue_segment_deriver import derive_dialogue_segments

_STAGES = ["tag_emotion", "compose_prompt", "generate", "align", "mix"]
_STAGE_LABELS = {"tag_emotion": "切段+情绪", "compose_prompt": "prompt",
                 "generate": "生成(选优点)", "align": "对齐", "mix": "出片"}


class SoundtrackEditor(QWidget):
    statusChanged = Signal(str, str)
    resultReady = Signal(str, str)

    def __init__(self, task: dict, cfg, work_root, parent=None):
        super().__init__(parent)
        self._task = task
        self.cfg = cfg
        self._work_root = Path(work_root)
        self._worker = None
        self._sfx_worker = None
        self._session = None
        self._sfx_session = None
        self._video_preview = None
        self._overview_timeline = None
        # 4c DAW 组件
        self._daw_toolbar = None
        self._track_view = None
        self._minimap = None
        self._inspector_container = None
        self._current_inspector = None
        from drama_shot_master.ui.widgets.daw.selection import Selection
        from drama_shot_master.ui.widgets.daw.undo_stack import UndoStack
        self._selection = Selection(self)
        self._undo = UndoStack(self)
        self._build_ui()
        self._setup_shortcuts()
        self._try_load_existing()

    # ── identity ──────────────────────────────────────────────────────

    @property
    def task_id(self) -> str:
        return self._task.get("id", "")

    def _work_dir(self) -> Path:
        return self._resolve_output_base() / self.task_id

    def _resolve_output_base(self) -> Path:
        task_out = (self._task.get("output_dir") or "").strip()
        if task_out:
            return Path(task_out)
        cfg_out = (getattr(self.cfg, "soundtrack_output_dir", "") or "").strip()
        if cfg_out:
            return Path(cfg_out)
        vout = getattr(self.cfg, "video_output_dir", "") or "."
        return Path(vout) / "soundtrack"

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget
        from drama_shot_master.ui.widgets.overview_timeline import OverviewTimeline
        self._video_preview = VideoPreviewWidget()
        self._overview_timeline = OverviewTimeline()
        self._video_preview.positionChanged.connect(self._on_video_position_changed)
        self._overview_timeline.playheadDragged.connect(self._on_overview_playhead_dragged)
        self._overview_timeline.cueClicked.connect(self._on_overview_cue_clicked)
        root.addWidget(self._video_preview)
        root.addWidget(self._overview_timeline)
        self._build_daw_main(root)
        # 生成控制条（保留生成/重排/导出/预览按钮）
        self._build_action_bar(root)

    def _build_daw_main(self, root):
        from drama_shot_master.ui.widgets.daw.daw_toolbar import DawToolbar
        from drama_shot_master.ui.widgets.daw.daw_track_view import DawTrackView
        from drama_shot_master.ui.widgets.daw.daw_minimap import DawMinimap
        from drama_shot_master.ui.widgets.daw.inspector import EmptyInspector
        self._daw_toolbar = DawToolbar(self._undo)
        self._daw_toolbar.undoRequested.connect(self._undo.undo)
        self._daw_toolbar.redoRequested.connect(self._undo.redo)
        self._daw_toolbar.configRequested.connect(self._on_open_config_dialog)
        self._daw_toolbar.playPauseRequested.connect(self._on_toolbar_play)
        self._daw_toolbar.fitRequested.connect(self._on_fit)
        self._daw_toolbar.zoomInRequested.connect(lambda: self._on_zoom_step(1.5))
        self._daw_toolbar.zoomOutRequested.connect(lambda: self._on_zoom_step(1 / 1.5))
        root.addWidget(self._daw_toolbar)

        main_h = QHBoxLayout()
        main_h.setContentsMargins(0, 0, 0, 0)
        main_h.setSpacing(0)

        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(0)
        self._track_view = DawTrackView(self._selection)
        self._track_view.cueClicked.connect(self._on_cue_clicked)
        self._track_view.cueDoubleClicked.connect(self._on_open_prompt_edit_dialog)
        self._track_view.dragCommandIssued.connect(self._on_command_from_widget)
        self._track_view.rubberBandReleased.connect(self._on_rubber_band)
        self._track_view.contextMenuRequested.connect(self._on_context_menu)
        self._track_view.playheadDragged.connect(self._on_track_playhead_dragged)
        self._scrollbar = QScrollBar(Qt.Horizontal)
        self._scrollbar.setRange(0, 1000)
        self._scrollbar.valueChanged.connect(
            lambda v: self._track_view.set_scroll_offset(v / 1000.0))
        self._minimap = DawMinimap()
        self._minimap.viewportRequested.connect(
            lambda off: self._scrollbar.setValue(int(off * 1000)))
        left_col.addWidget(self._track_view, 1)
        left_col.addWidget(self._scrollbar)
        left_col.addWidget(self._minimap)
        left_w = QWidget()
        left_w.setLayout(left_col)
        main_h.addWidget(left_w, 1)

        self._inspector_container = QWidget()
        self._inspector_container.setFixedWidth(280)
        ic_lay = QVBoxLayout(self._inspector_container)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        self._current_inspector = EmptyInspector()
        ic_lay.addWidget(self._current_inspector)
        main_h.addWidget(self._inspector_container)

        main_w = QWidget()
        main_w.setLayout(main_h)
        root.addWidget(main_w, 1)
        self._selection.changed.connect(self._refresh_inspector)

    def _build_action_bar(self, root):
        bar = QHBoxLayout()
        self.stop_combo = QComboBox()
        for s in _STAGES:
            self.stop_combo.addItem(_STAGE_LABELS[s], s)
        self.stop_combo.setCurrentIndex(_STAGES.index("generate"))
        bar.addWidget(QLabel("停在:"))
        bar.addWidget(self.stop_combo)
        self.btn_start = QPushButton("🎬 开始配乐")
        self.btn_start.setObjectName("AccentButton")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_resegment = QPushButton("🔄 重排段落")
        self.btn_resegment.clicked.connect(self._on_resegment)
        self.btn_export = QPushButton("🎬 导出成片")
        self.btn_export.setObjectName("AccentButton")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_open_dir = QPushButton("📂 打开输出目录")
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        self.btn_preview = QPushButton("▶ 预览成片")
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_preview.setEnabled(False)
        btn_sfx_plan = QPushButton("🎬 检测 SFX")
        btn_sfx_plan.clicked.connect(self._on_sfx_plan_clicked)
        btn_sfx_gen = QPushButton("🔊 生成 SFX")
        btn_sfx_gen.clicked.connect(self._on_sfx_generate_clicked)
        for w in (self.btn_start, self.btn_resegment, self.btn_export,
                  self.btn_open_dir, self.btn_preview,
                  btn_sfx_plan, btn_sfx_gen):
            bar.addWidget(w)
        bar.addStretch(1)
        bar_w = QWidget()
        bar_w.setLayout(bar)
        root.addWidget(bar_w)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        root.addWidget(self.progress)
        root.addWidget(self.progress_label)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Space), self, self._on_toolbar_play)
        QShortcut(QKeySequence(Qt.Key_R), self, self._on_regen_selected)
        QShortcut(QKeySequence(Qt.Key_Delete), self, self._on_delete_selected)
        QShortcut(QKeySequence(QKeySequence.Undo), self, self._undo.undo)
        QShortcut(QKeySequence(QKeySequence.Redo), self, self._undo.redo)
        QShortcut(QKeySequence(QKeySequence.SelectAll), self, self._on_select_all)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._selection.clear)
        QShortcut(QKeySequence(Qt.Key_Home), self,
                  lambda: self._video_preview.seek(0.0)
                          if self._video_preview else None)
        QShortcut(QKeySequence(Qt.Key_End), self,
                  lambda: self._video_preview.seek(
                      self._track_view._duration if self._track_view else 0)
                          if self._video_preview else None)
        QShortcut(QKeySequence("+"), self, lambda: self._on_zoom_step(1.5))
        QShortcut(QKeySequence("-"), self, lambda: self._on_zoom_step(1 / 1.5))

    # ── session load ─────────────────────────────────────────────────

    def _try_load_existing(self):
        from sound_track_agent import facade
        sess = facade.load_session(self._work_dir())
        if sess is not None:
            self._session = sess
        from sound_track_agent.sfx import facade as sfx_fac
        try:
            sfx_sess = sfx_fac.load_sfx_session(self._work_dir())
        except Exception:
            sfx_sess = None
        if sfx_sess is not None:
            self._sfx_session = sfx_sess
        src = self._resolve_video_source()
        if src and self._video_preview:
            self._video_preview.set_source(src)
        self._refresh_track_view()

    # ── Inspector ────────────────────────────────────────────────────

    def _refresh_inspector(self):
        from drama_shot_master.ui.widgets.daw.inspector import (
            EmptyInspector, BgmInspector, SfxInspector, DialogueInspector,
        )
        refs = self._selection.get()
        if len(refs) != 1:
            new_insp = EmptyInspector()
        else:
            ref = refs[0]
            if ref.track == "bgm" and self._session:
                insp = BgmInspector()
                insp.set_cue_ref(ref, self._session)
                insp.regenerateRequested.connect(self._on_regen_one)
                insp.promptEditRequested.connect(self._on_open_prompt_edit_dialog)
                insp.candidateChosen.connect(self._on_inspector_candidate_chosen)
                new_insp = insp
            elif ref.track == "sfx" and self._sfx_session:
                insp = SfxInspector()
                insp.set_cue_ref(ref, self._sfx_session)
                insp.regenerateRequested.connect(self._on_sfx_regen_one_inspector)
                insp.promptEditRequested.connect(self._on_open_prompt_edit_dialog)
                insp.candidateChosen.connect(self._on_inspector_candidate_chosen)
                insp.commandIssued.connect(self._on_command_from_widget)
                new_insp = insp
            elif ref.track == "dialogue":
                insp = DialogueInspector()
                timeline = self._dialogue_timeline_for_current_mp4()
                insp.set_cue_ref(ref, timeline)
                new_insp = insp
            else:
                new_insp = EmptyInspector()
        self._swap_inspector(new_insp)

    def _swap_inspector(self, new):
        lay = self._inspector_container.layout()
        while lay.count():
            old = lay.takeAt(0).widget()
            if old:
                old.deleteLater()
        self._current_inspector = new
        lay.addWidget(new)

    # ── track view refresh ───────────────────────────────────────────

    def _refresh_track_view(self):
        if self._track_view is None:
            return
        from drama_shot_master.ui.widgets.overview_timeline_model import (
            derive_video_cues, derive_bgm_cues, derive_sfx_cues,
            derive_dialogue_cues, derive_total_duration,
        )
        bgm_cues = derive_bgm_cues(self._session)
        sfx_cues = derive_sfx_cues(self._sfx_session)
        timeline = self._dialogue_timeline_for_current_mp4()
        dial_cues = derive_dialogue_cues(timeline)
        shot_bounds = []
        if self._session:
            shot_bounds = [float(s.t_end) for s in (self._session.segments or [])]
        video_dur = self._video_preview.duration() if self._video_preview else 0.0
        total = derive_total_duration(
            bgm_session=self._session, sfx_session=self._sfx_session,
            dialogue_audios=timeline, video_duration=video_dur)
        video_cues = derive_video_cues(shot_bounds, total)
        cues = video_cues + bgm_cues + sfx_cues + dial_cues
        self._track_view.set_duration(total)
        self._track_view.set_cues(cues)
        self._minimap.set_duration(total)
        self._minimap.set_cues(cues)
        # 同步 overview timeline
        if self._overview_timeline is not None:
            self._overview_timeline.set_duration(total)
            self._overview_timeline.set_cues(cues)

    def _dialogue_timeline_for_current_mp4(self):
        mp4 = str(self._task.get("mp4", "")).strip()
        for t in (getattr(self.cfg, "video_tasks", []) or []):
            if str(t.get("last_result", "")) == mp4:
                return t.get("timeline")
        return None

    # ── commands / undo ──────────────────────────────────────────────

    def _on_command_from_widget(self, cmd):
        self._undo.push(cmd)
        self._persist_session()
        self._refresh_track_view()

    def _on_delete_selected(self):
        refs = self._selection.get()
        if not refs:
            return
        from drama_shot_master.ui.widgets.daw.commands import DeleteCue
        refs = [r for r in refs if r.track in ("bgm", "sfx")]
        if not refs:
            return
        cmd = DeleteCue(self._session, self._sfx_session, refs)
        self._undo.push(cmd)
        self._persist_session()
        self._refresh_track_view()

    def _on_select_all(self):
        from drama_shot_master.ui.widgets.daw.selection import _CueRef
        refs = []
        if self._session:
            refs += [_CueRef("bgm", i) for i, _ in enumerate(self._session.segments)]
        if self._sfx_session:
            refs += [_CueRef("sfx", i)
                     for i, s in enumerate(self._sfx_session.shots)
                     if getattr(s, "enabled", True) and s.status == "generated"]
        self._selection.set(refs)

    def _on_regen_selected(self):
        by_track = self._selection.by_track()
        for idx in by_track.get("bgm", []):
            self._on_regenerate(idx)
        for idx in by_track.get("sfx", []):
            self._on_sfx_regenerate_one(idx)

    def _on_regen_one(self, ref):
        self._on_regenerate(ref.seg_index)

    def _on_sfx_regen_one_inspector(self, ref):
        self._on_sfx_regenerate_one(ref.seg_index)

    def _on_inspector_candidate_chosen(self, ref, idx):
        if ref.track == "bgm" and self._session:
            self._session.segments[ref.seg_index].chosen_candidate = idx
            self._persist_session()
        elif ref.track == "sfx" and self._sfx_session:
            self._sfx_session.shots[ref.seg_index].chosen_candidate = idx
            try:
                self._sfx_session.save(self._work_dir() / "sfx_session.json")
            except Exception:
                pass

    # ── keyboard ─────────────────────────────────────────────────────

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Delete:
            self._on_delete_selected()
        else:
            super().keyPressEvent(ev)

    # ── DAW interaction ──────────────────────────────────────────────

    def _on_cue_clicked(self, ref, mod):
        if mod & Qt.ControlModifier:
            self._selection.toggle(ref)
        else:
            self._selection.set([ref])

    def _on_rubber_band(self, rect, mod):
        pass  # future: collect cues inside rect

    def _on_context_menu(self, ref, pos):
        pass  # future: context menu

    def _on_track_playhead_dragged(self, t: float):
        if self._video_preview:
            self._video_preview.seek(t)

    def _on_toolbar_play(self):
        if self._video_preview is None:
            return
        try:
            if self._video_preview.is_playing():
                self._video_preview.pause()
            else:
                self._video_preview.play()
        except Exception:
            pass

    def _on_zoom_step(self, factor: float):
        if self._track_view:
            self._track_view.set_zoom(self._track_view._zoom * factor)

    def _on_fit(self):
        if self._track_view:
            self._track_view.set_zoom(1.0)
            self._track_view.set_scroll_offset(0.0)
        if self._scrollbar:
            self._scrollbar.setValue(0)

    # ── dialogs ──────────────────────────────────────────────────────

    def _on_open_config_dialog(self):
        from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
        from PySide6.QtWidgets import QDialog
        initial = {"mp4": self._task.get("mp4", ""),
                   "style": self._task.get("style", ""),
                   "output_dir": self._task.get("output_dir", "")}
        dlg = ConfigDialog(initial, self)
        if dlg.exec() == QDialog.Accepted:
            p = dlg.to_payload()
            self._task.update(p)
            src = self._resolve_video_source()
            if src and self._video_preview:
                self._video_preview.set_source(src)

    def _on_open_prompt_edit_dialog(self, ref):
        from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
        from drama_shot_master.ui.widgets.daw.commands import ChangePrompt
        from PySide6.QtWidgets import QDialog
        initial = ""
        if ref.track == "bgm" and self._session:
            initial = getattr(self._session.segments[ref.seg_index],
                              "music_prompt", "") or ""
        elif ref.track == "sfx" and self._sfx_session:
            initial = self._sfx_session.shots[ref.seg_index].prompt_short or ""
        title = f"{ref.track.upper()} 段 {ref.seg_index} prompt"
        dlg = PromptEditDialog(initial, title, self)
        if dlg.exec() == QDialog.Accepted:
            new_prompt = dlg.to_payload()
            if new_prompt != initial:
                cmd = ChangePrompt(self._session, self._sfx_session, ref, new_prompt)
                self._undo.push(cmd)
                self._persist_session()
                self._refresh_inspector()
                self._refresh_track_view()

    # ── persist ───────────────────────────────────────────────────────

    def _persist_session(self):
        if self._session is not None:
            try:
                self._session.save(self._work_dir() / "session.json")
            except Exception:
                pass
        if self._sfx_session is not None:
            try:
                self._sfx_session.save(self._work_dir() / "sfx_session.json")
            except Exception:
                pass

    def _post_progress(self, msg: str):
        QTimer.singleShot(0, lambda: self.progress_label.setText(msg))

    # ── pipeline / workers ────────────────────────────────────────────

    def _worker_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _on_start(self):
        self._run_pipeline(self.stop_combo.currentData())

    def _on_export(self):
        self._run_pipeline("mix")

    def _run_pipeline(self, stop_after):
        if self._worker_busy():
            QMessageBox.information(self, "请稍候", "当前有任务在运行")
            return
        mp4 = self._task.get("mp4", "").strip()
        style = self._task.get("style", "").strip()
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无法开始", "请先配置存在的成片 MP4（点工具栏 ⚙）")
            return
        if not style:
            QMessageBox.warning(self, "无法开始", "请先填写总风格（点工具栏 ⚙）")
            return
        workflow_id = getattr(self.cfg, "soundtrack_workflow_id", "")
        seeds = int(getattr(self.cfg, "soundtrack_seeds_count", 2))
        work_dir = self._work_dir()
        cfg = self.cfg
        sfx_session = self._sfx_session

        def task():
            from sound_track_agent import facade
            sess = facade.load_session(work_dir)
            if sess is None:
                dialogue_segs = derive_dialogue_segments(cfg, mp4) or None
                sess = facade.prepare_session(
                    mp4, style, work_dir, dialogue_segments=dialogue_segs)
            self._post_seg_preview(sess)
            facade.advance(sess, work_dir, cfg=cfg, workflow_id=workflow_id,
                           seeds_count=seeds, stop_after=stop_after,
                           on_progress=self._post_progress,
                           sfx_session=sfx_session)
            return sess

        self.btn_start.setEnabled(False)
        self.progress.show()
        self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_regenerate(self, seg_index: int):
        if self._session is None:
            return
        if self._worker_busy():
            QMessageBox.information(self, "请稍候", "当前有任务在运行")
            return
        workflow_id = getattr(self.cfg, "soundtrack_workflow_id", "")
        seeds = int(getattr(self.cfg, "soundtrack_seeds_count", 2))
        work_dir = self._work_dir()
        cfg = self.cfg
        sess = self._session

        def task():
            from sound_track_agent import facade
            facade.regenerate_segment(sess, seg_index, work_dir, cfg=cfg,
                                      workflow_id=workflow_id, seeds_count=seeds)
            return sess

        self.progress.show()
        self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_regen_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _post_seg_preview(self, sess):
        lines = [f"段{s.index}  {s.t_start:.1f}–{s.t_end:.1f}s" for s in sess.segments]
        QTimer.singleShot(0, lambda: self.progress_label.setText("\n".join(lines)))

    def _on_done(self, sess):
        self.progress.hide()
        self.btn_start.setEnabled(True)
        self._session = sess
        out = getattr(sess, "output", None)
        if out:
            self.statusChanged.emit(self.task_id, "完成")
            self.resultReady.emit(self.task_id, out)
            self.progress_label.setText(f"完成：{out}")
        else:
            self.statusChanged.emit(self.task_id, "空闲")
            self.progress_label.setText(
                f"已停在选优点：候选已生成在 {self._work_dir()}")
        self._update_preview_enabled()
        self._refresh_track_view()
        new_src = self._resolve_video_source()
        if new_src and self._video_preview is not None:
            self._video_preview.set_source(new_src)

    def _on_regen_done(self, sess):
        self.progress.hide()
        self._session = sess
        self.statusChanged.emit(self.task_id, "空闲")
        self._refresh_track_view()
        self._refresh_inspector()

    def _on_failed(self, err: str):
        self.progress.hide()
        self.btn_start.setEnabled(True)
        self.statusChanged.emit(self.task_id, "失败")
        QMessageBox.critical(self, "配乐失败", err)

    def _update_preview_enabled(self):
        out = getattr(self._session, "output", None) if self._session else None
        self.btn_preview.setEnabled(bool(out) and Path(out).exists())

    def _on_preview(self):
        out = getattr(self._session, "output", None) if self._session else None
        if out and Path(out).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
        else:
            QMessageBox.information(self, "预览成片", "还没有成片，请先导出成片")

    def _open_output_dir(self):
        wd = self._work_dir()
        if wd.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(wd)))
        else:
            QMessageBox.information(self, "打开输出目录", "还没有输出（先运行一次）")

    def _on_resegment(self):
        if not self._session:
            QMessageBox.warning(self, "无法重排", "请先开始配乐生成 session")
            return
        if self._worker_busy():
            QMessageBox.information(self, "请稍候", "当前有任务在运行")
            return
        if any(s.candidates for s in self._session.segments):
            if QMessageBox.warning(
                    self, "重排会清空候选",
                    "已有 BGM 候选会被清空丢弃，确定重排？",
                    QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
                return
        for s in self._session.segments:
            s.candidates = []
            s.chosen_candidate = None
            s.music_prompt = ""
            s.status = "pending"
            s.emotion = None
        self._session.segments_refined = False
        self._persist_session()
        self._run_pipeline("refine_segments")

    # ── SFX workers ───────────────────────────────────────────────────

    def _on_sfx_plan_clicked(self):
        if self._sfx_worker is not None and self._sfx_worker.isRunning():
            QMessageBox.information(self, "请稍候", "SFX 任务正在运行")
            return
        mp4 = self._task.get("mp4", "").strip()
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无 MP4", "请先配置视频文件（点工具栏 ⚙）")
            return
        cfg = self.cfg
        work_dir = self._work_dir()
        from sound_track_agent.sfx import facade as sfx_fac

        def task():
            return sfx_fac.plan_sfx_session(mp4, work_dir, cfg=cfg)

        self._sfx_worker = FunctionWorker(task)
        self._sfx_worker.finished_with_result.connect(self._on_sfx_plan_done)
        self._sfx_worker.failed.connect(
            lambda err: QMessageBox.critical(self, "SFX 检测失败", err))
        self._sfx_worker.start()

    def _on_sfx_plan_done(self, session):
        self._sfx_session = session
        self._refresh_track_view()

    def _on_sfx_generate_clicked(self):
        if self._sfx_worker is not None and self._sfx_worker.isRunning():
            QMessageBox.information(self, "请稍候", "SFX 任务正在运行")
            return
        if self._sfx_session is None:
            QMessageBox.warning(self, "未检测", "请先点 🎬 检测 SFX 时机")
            return
        cfg = self.cfg
        sess = self._sfx_session
        work_dir = self._work_dir()
        from sound_track_agent.sfx import facade as sfx_fac

        def task():
            sfx_fac.generate_sfx_all(sess, work_dir, cfg=cfg)
            return sess

        self._sfx_worker = FunctionWorker(task)
        self._sfx_worker.finished_with_result.connect(self._on_sfx_generate_done)
        self._sfx_worker.failed.connect(
            lambda err: QMessageBox.critical(self, "SFX 生成失败", err))
        self._sfx_worker.start()

    def _on_sfx_generate_done(self, _sess):
        self._refresh_track_view()

    def _on_sfx_regenerate_one(self, shot_index: int):
        if self._sfx_session is None:
            return
        if self._sfx_worker is not None and self._sfx_worker.isRunning():
            return
        cfg = self.cfg
        sess = self._sfx_session
        work_dir = self._work_dir()
        from sound_track_agent.sfx import facade as sfx_fac

        def task():
            sfx_fac.regenerate_sfx_one(sess, shot_index, work_dir, cfg=cfg)
            return sess

        self._sfx_worker = FunctionWorker(task)
        self._sfx_worker.finished_with_result.connect(self._on_sfx_generate_done)
        self._sfx_worker.failed.connect(
            lambda err: QMessageBox.critical(self, "SFX 重生成失败", err))
        self._sfx_worker.start()

    # ── video preview helpers ─────────────────────────────────────────

    def _resolve_video_source(self):
        if self._session is not None:
            out = getattr(self._session, "output", None)
            if out and Path(out).exists():
                return out
        mp4 = (self._task.get("mp4") or "").strip()
        return mp4 if mp4 and Path(mp4).exists() else None

    def _on_overview_playhead_dragged(self, t: float):
        if self._video_preview is not None:
            self._video_preview.seek(t)

    def _on_video_position_changed(self, t: float):
        if self._overview_timeline is not None:
            self._overview_timeline.set_playhead(t)
        if self._daw_toolbar is not None:
            total = self._track_view._duration if self._track_view else 0
            self._daw_toolbar.set_time(t, total)

    def _on_overview_cue_clicked(self, track: str, idx: int, t_start: float):
        from drama_shot_master.ui.widgets.daw.selection import _CueRef
        self._selection.set([_CueRef(track, idx)])
        if self._video_preview is not None:
            self._video_preview.seek(t_start)

    def to_payload(self) -> dict:
        return {
            "mp4": self._task.get("mp4", ""),
            "style": self._task.get("style", ""),
            "output_dir": self._task.get("output_dir", ""),
        }
