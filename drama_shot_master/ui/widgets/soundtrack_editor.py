"""SoundtrackEditor：单集配乐编辑器（QWidget，4 页签）。

从退役的 SoundtrackTaskWindow 抽取：① 配置+生成 ② 试听选优 ③ 卡点 ④ SFX 音效。
浮出由通用 DetachedEditorWindow 承载，故本类不带 closed/closeEvent。
输出路径：任务 output_dir → cfg.soundtrack_output_dir → cfg.video_output_dir/soundtrack。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QComboBox, QProgressBar, QTabWidget,
    QFileDialog, QMessageBox,
)

from drama_shot_master.ui.worker import FunctionWorker
from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
from drama_shot_master.ui.widgets.accent_editor_widget import AccentEditorWidget
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
        self._session = None
        self._review = None
        self._accent = None
        self._sfx_session = None
        self._sfx_worker = None
        self._video_preview = None
        self._overview_timeline = None
        self._build_ui()
        self._try_load_existing()

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

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # 顶部预览区 (Phase 4b)
        from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget
        from drama_shot_master.ui.widgets.overview_timeline import OverviewTimeline
        self._video_preview = VideoPreviewWidget()
        self._overview_timeline = OverviewTimeline()
        self._video_preview.positionChanged.connect(
            self._on_video_position_changed)
        self._overview_timeline.playheadDragged.connect(
            self._on_overview_playhead_dragged)
        self._overview_timeline.cueClicked.connect(
            self._on_overview_cue_clicked)
        root.addWidget(self._video_preview)
        root.addWidget(self._overview_timeline)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_config_tab(), "① 配置+生成")
        self._review_holder = QWidget(); QVBoxLayout(self._review_holder)
        self.tabs.addTab(self._review_holder, "② 试听选优")
        self._accent_holder = QWidget(); QVBoxLayout(self._accent_holder)
        self.tabs.addTab(self._accent_holder, "③ 卡点")
        self.tabs.addTab(self._build_sfx_tab(), "④ 🔊 SFX 音效")
        # 启动时尝试加载已有 sfx session
        from sound_track_agent.sfx import facade as sfx_fac
        try:
            self._sfx_session = sfx_fac.load_sfx_session(self._work_dir())
        except Exception:
            self._sfx_session = None
        if self._sfx_session is not None:
            self._rebuild_sfx_review()
        self.tabs.currentChanged.connect(lambda _i: self._rebuild_overview())
        self._rebuild_overview()
        src = self._resolve_video_source()
        if src:
            self._video_preview.set_source(src)

    def _build_sfx_tab(self) -> QWidget:
        sfx_tab = QWidget()
        sfx_lay = QVBoxLayout(sfx_tab)
        bar = QHBoxLayout()
        self.btn_sfx_plan = QPushButton("🎬 检测 SFX 时机")
        self.btn_sfx_plan.clicked.connect(self._on_sfx_plan_clicked)
        self.btn_sfx_gen = QPushButton("🔊 生成全部")
        self.btn_sfx_gen.clicked.connect(self._on_sfx_generate_clicked)
        bar.addWidget(self.btn_sfx_plan)
        bar.addWidget(self.btn_sfx_gen)
        bar.addStretch(1)
        sfx_lay.addLayout(bar)
        self._sfx_review_holder = QWidget()
        self._sfx_review_lay = QVBoxLayout(self._sfx_review_holder)
        sfx_lay.addWidget(self._sfx_review_holder, 1)
        return sfx_tab

    def _build_config_tab(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page)

        mp4_row = QHBoxLayout()
        mp4_row.addWidget(QLabel("成片 MP4:"))
        self.mp4_edit = QLineEdit(self._task.get("mp4", ""))
        b = QPushButton("浏览…"); b.clicked.connect(self._browse_mp4)
        mp4_row.addWidget(self.mp4_edit, 1); mp4_row.addWidget(b)
        root.addLayout(mp4_row)

        root.addWidget(QLabel("总风格:"))
        self.style_edit = QPlainTextEdit(self._task.get("style", ""))
        self.style_edit.setMaximumHeight(70)
        root.addWidget(self.style_edit)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("本任务输出目录(可空=用全局默认):"))
        self.out_edit = QLineEdit(self._task.get("output_dir", ""))
        ob = QPushButton("浏览…"); ob.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1); out_row.addWidget(ob)
        root.addLayout(out_row)

        stop_row = QHBoxLayout()
        stop_row.addWidget(QLabel("停在:"))
        self.stop_combo = QComboBox()
        for s in _STAGES:
            self.stop_combo.addItem(_STAGE_LABELS[s], s)
        self.stop_combo.setCurrentIndex(_STAGES.index("generate"))
        stop_row.addWidget(self.stop_combo); stop_row.addStretch(1)
        root.addLayout(stop_row)

        root.addWidget(QLabel("段落预览:"))
        self.seg_preview = QPlainTextEdit(); self.seg_preview.setReadOnly(True)
        self.seg_preview.setMaximumHeight(140)
        root.addWidget(self.seg_preview, 1)

        act = QHBoxLayout()
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
        act.addWidget(self.btn_start); act.addWidget(self.btn_resegment)
        act.addWidget(self.btn_export)
        act.addWidget(self.btn_open_dir); act.addWidget(self.btn_preview)
        act.addStretch(1)
        root.addLayout(act)

        self.progress = QProgressBar(); self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress_label = QLabel(""); self.progress_label.setWordWrap(True)
        root.addWidget(self.progress); root.addWidget(self.progress_label)
        return page

    def _try_load_existing(self):
        from sound_track_agent import facade
        sess = facade.load_session(self._work_dir())
        if sess is not None:
            self._session = sess
            self._mount_session_tabs()
            self._post_seg_preview(sess)
            self.progress_label.setText("已加载上次进度（可续跑/选优/编辑卡点）")
            self._update_preview_enabled()

    def _mount_session_tabs(self):
        # ② 试听选优
        lay = self._review_holder.layout()
        while lay.count():
            old = lay.takeAt(0).widget()
            if old: old.deleteLater()
        self._review = SegmentReviewWidget(self._session)
        self._review.regenerateRequested.connect(self._on_regenerate)
        self._review.chosenChanged.connect(self._on_chosen_changed)
        self._review.segmentVolumeChanged.connect(self._persist_session)
        lay.addWidget(self._review)
        # ③ 卡点
        lay2 = self._accent_holder.layout()
        while lay2.count():
            old = lay2.takeAt(0).widget()
            if old: old.deleteLater()
        self._accent = AccentEditorWidget(
            self._session,
            big_threshold=float(getattr(self.cfg, "accent_big_threshold", 0.7)),
            work_dir=str(self._work_dir()),
            crossfade=float(getattr(self.cfg, "soundtrack_crossfade", 0.5)),
            snap_window=float(getattr(self.cfg, "accent_snap_window", 0.6)))
        self._accent.accentsChanged.connect(self._persist_session)
        lay2.addWidget(self._accent)

    def _persist_session(self):
        if self._session is not None:
            self._session.save(self._work_dir() / "session.json")

    def _on_chosen_changed(self):
        """试听选优变化 → 选定进度提示 + 落盘选定。"""
        if self._session is None:
            return
        self._persist_session()
        if self._review is not None and not self._review.all_chosen():
            n = sum(1 for s in self._session.segments
                    if s.chosen_candidate is not None)
            total = len(self._session.segments)
            self.progress_label.setText(
                f"已选定 {n}/{total} 段；全部选定后「停在」选「出片」可出成片")

    def _worker_busy(self) -> bool:
        """有 worker 在跑则 True（防并发改同一 session）。"""
        return self._worker is not None and self._worker.isRunning()

    def _browse_mp4(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择成片 MP4", self.mp4_edit.text() or "", "视频 (*.mp4 *.mov)")
        if p:
            self.mp4_edit.setText(p)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "本任务输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def _post_progress(self, msg: str):
        QTimer.singleShot(0, lambda: self.progress_label.setText(msg))

    def _on_start(self):
        self._run_pipeline(self.stop_combo.currentData())

    def _on_export(self):
        self._run_pipeline("mix")

    def _run_pipeline(self, stop_after):
        if self._worker_busy():
            QMessageBox.information(self, "请稍候", "当前有任务在运行"); return
        mp4 = self.mp4_edit.text().strip()
        style = self.style_edit.toPlainText().strip()
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无法开始", "请选择存在的成片 MP4"); return
        if not style:
            QMessageBox.warning(self, "无法开始", "请填写总风格"); return
        # 出片门控：到 mix 阶段需所有段已选定候选
        if stop_after == "mix" and self._session is not None and \
                self._review is not None and not self._review.all_chosen():
            QMessageBox.warning(self, "无法出片",
                                "还有段未选定候选，请先到「② 试听选优」全部选定")
            self.tabs.setCurrentIndex(1)
            return
        self._task["output_dir"] = self.out_edit.text().strip()
        self._task["mp4"] = mp4
        self._task["style"] = style
        workflow_id = getattr(self.cfg, "soundtrack_workflow_id", "")
        seeds = int(getattr(self.cfg, "soundtrack_seeds_count", 2))
        work_dir = self._work_dir()
        cfg = self.cfg

        sfx_session = self._sfx_session

        def task():
            from sound_track_agent import facade
            sess = facade.load_session(work_dir)
            if sess is None:
                # 从 video_tasks 派生对白段，复用配音轨而非 Demucs 盲分离；无匹配返回 [] → 传 None → 走回退
                dialogue_segs = derive_dialogue_segments(cfg, mp4) or None
                sess = facade.prepare_session(
                    mp4, style, work_dir, dialogue_segments=dialogue_segs)
            self._post_seg_preview(sess)
            facade.advance(sess, work_dir, cfg=cfg, workflow_id=workflow_id,
                           seeds_count=seeds, stop_after=stop_after,
                           on_progress=self._post_progress,
                           sfx_session=sfx_session)
            return sess

        self.btn_start.setEnabled(False); self.progress.show()
        self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_regenerate(self, seg_index: int):
        if self._session is None:
            return
        if self._worker_busy():
            QMessageBox.information(self, "请稍候", "当前有任务在运行"); return
        workflow_id = getattr(self.cfg, "soundtrack_workflow_id", "")
        seeds = int(getattr(self.cfg, "soundtrack_seeds_count", 2))
        work_dir = self._work_dir(); cfg = self.cfg; sess = self._session

        def task():
            from sound_track_agent import facade
            facade.regenerate_segment(sess, seg_index, work_dir, cfg=cfg,
                                      workflow_id=workflow_id, seeds_count=seeds)
            return sess

        self.progress.show(); self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_regen_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _post_seg_preview(self, sess):
        lines = [f"段{s.index}  {s.t_start:.1f}–{s.t_end:.1f}s" for s in sess.segments]
        QTimer.singleShot(0, lambda: self.seg_preview.setPlainText("\n".join(lines)))

    def _on_done(self, sess):
        self.progress.hide(); self.btn_start.setEnabled(True)
        self._session = sess
        self._mount_session_tabs()
        out = getattr(sess, "output", None)
        if out:
            self.statusChanged.emit(self.task_id, "完成")
            self.resultReady.emit(self.task_id, out)
            self.progress_label.setText(f"完成：{out}")
        else:
            self.statusChanged.emit(self.task_id, "空闲")
            self.progress_label.setText(
                f"已停在选优点：候选已生成在 {self._work_dir()}（切到「② 试听选优」试听选定）")
            self.tabs.setCurrentIndex(1)
        self._update_preview_enabled()
        self._rebuild_overview()
        new_src = self._resolve_video_source()
        if new_src and self._video_preview is not None:
            self._video_preview.set_source(new_src)

    def _on_regen_done(self, sess):
        self.progress.hide()
        self._mount_session_tabs()
        self.tabs.setCurrentIndex(1)
        self.statusChanged.emit(self.task_id, "空闲")

    def _on_failed(self, err: str):
        self.progress.hide(); self.btn_start.setEnabled(True)
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
            QMessageBox.information(self, "预览成片", "还没有成片,请先导出成片")

    def _open_output_dir(self):
        wd = self._work_dir()
        if wd.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(wd)))
        else:
            QMessageBox.information(self, "打开输出目录", "还没有输出（先运行一次）")

    def _on_resegment(self):
        """🔄 重排段落：清空已有候选/prompt/emotion，重置 segments_refined，重跑 refine 阶段。"""
        if not self._session:
            QMessageBox.warning(self, "无法重排", "请先开始配乐生成 session")
            return
        # 重要：worker 忙时不能 reset——否则 session 落盘清空后 refine 被 _run_pipeline
        # 早退拦截，用户会拿到一个被静默清空候选的 session。与 _on_regenerate 对齐。
        if self._worker_busy():
            QMessageBox.information(self, "请稍候", "当前有任务在运行"); return
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

    # ------------------------------------------------------------------
    # SFX tab 方法
    # ------------------------------------------------------------------

    def _rebuild_sfx_review(self):
        from drama_shot_master.ui.widgets.sfx_review_widget import SfxReviewWidget
        while self._sfx_review_lay.count():
            w = self._sfx_review_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        if self._sfx_session is None:
            return
        review = SfxReviewWidget(self._sfx_session)
        review.regenerateRequested.connect(self._on_sfx_regenerate_one)
        review.shotEdited.connect(lambda: self._sfx_session.save(
            self._work_dir() / "sfx_session.json"))
        review.chosenChanged.connect(lambda: self._sfx_session.save(
            self._work_dir() / "sfx_session.json"))
        self._sfx_review_lay.addWidget(review)

    def _on_sfx_plan_clicked(self):
        if self._sfx_worker is not None and self._sfx_worker.isRunning():
            QMessageBox.information(self, "请稍候", "SFX 任务正在运行")
            return
        mp4 = self.mp4_edit.text().strip()
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无 MP4", "请先选择视频文件")
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
        self._rebuild_sfx_review()

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
        self._rebuild_sfx_review()
        self._rebuild_overview()

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

    # ------------------------------------------------------------------
    # Phase 4b: 顶部预览方法
    # ------------------------------------------------------------------

    def _resolve_video_source(self):
        """有 BGM mix 完成 session.output → 用成片；否则用原 mp4."""
        if self._session is not None:
            out = getattr(self._session, "output", None)
            if out and Path(out).exists():
                return out
        mp4 = (self._task.get("mp4") or "").strip()
        if not mp4:
            mp4 = self.mp4_edit.text().strip()
        return mp4 if mp4 and Path(mp4).exists() else None

    def _rebuild_overview(self):
        if self._overview_timeline is None:
            return
        from drama_shot_master.ui.widgets.overview_timeline_model import (
            derive_video_cues, derive_bgm_cues, derive_sfx_cues,
            derive_dialogue_cues, derive_total_duration,
        )
        bgm_cues = derive_bgm_cues(self._session)
        sfx_cues = derive_sfx_cues(self._sfx_session)
        timeline = None
        mp4 = self.mp4_edit.text().strip() if hasattr(self, "mp4_edit") else ""
        for t in (getattr(self.cfg, "video_tasks", []) or []):
            if str(t.get("last_result", "")) == mp4:
                timeline = t.get("timeline"); break
        dial_cues = derive_dialogue_cues(timeline)
        shot_bounds = []
        if self._session is not None:
            shot_bounds = [float(s.t_end)
                           for s in (self._session.segments or [])]
        video_dur = (self._video_preview.duration()
                     if self._video_preview else 0.0)
        total = derive_total_duration(
            bgm_session=self._session,
            sfx_session=self._sfx_session,
            dialogue_audios=timeline,
            video_duration=video_dur)
        video_cues = derive_video_cues(shot_bounds, total)
        self._overview_timeline.set_duration(total)
        self._overview_timeline.set_cues(
            video_cues + bgm_cues + sfx_cues + dial_cues)

    def _on_overview_playhead_dragged(self, t: float):
        if self._video_preview is not None:
            self._video_preview.seek(t)

    def _on_video_position_changed(self, t: float):
        if self._overview_timeline is not None:
            self._overview_timeline.set_playhead(t)

    def _on_overview_cue_clicked(self, track: str, idx: int, t_start: float):
        # BGM/对白 → tab 1（试听选优）；SFX → tab 3
        tab_map = {"bgm": 1, "dialogue": 1, "sfx": 3}
        if track in tab_map:
            self.tabs.setCurrentIndex(tab_map[track])
        if self._video_preview is not None:
            self._video_preview.seek(t_start)

    def to_payload(self) -> dict:
        return {"mp4": self.mp4_edit.text().strip(),
                "style": self.style_edit.toPlainText().strip(),
                "output_dir": self.out_edit.text().strip()}
