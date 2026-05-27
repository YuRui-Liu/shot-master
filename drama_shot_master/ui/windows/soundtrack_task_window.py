"""SoundtrackTaskWindow：单集配乐任务窗（第二期，3 页签）。

① 配置+生成（精简：去 workflow/seeds，从 cfg 读） ② 试听选优 ③ 卡点。
构造时 load_session 续跑。输出路径：任务 output_dir → cfg.soundtrack_output_dir
→ cfg.video_output_dir/soundtrack。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QComboBox, QProgressBar, QTabWidget,
    QFileDialog, QMessageBox,
)

from drama_shot_master.ui.worker import FunctionWorker
from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
from drama_shot_master.ui.widgets.accent_editor_widget import AccentEditorWidget

_STAGES = ["tag_emotion", "compose_prompt", "generate", "align", "mix"]
_STAGE_LABELS = {"tag_emotion": "切段+情绪", "compose_prompt": "prompt",
                 "generate": "生成(选优点)", "align": "对齐", "mix": "出片"}


class SoundtrackTaskWindow(QMainWindow):
    statusChanged = Signal(str, str)
    resultReady = Signal(str, str)
    closed = Signal(str)

    def __init__(self, task: dict, cfg, work_root, parent=None):
        super().__init__(parent)
        self._task = task
        self.cfg = cfg
        self._work_root = Path(work_root)
        self._worker = None
        self._session = None
        self._review = None
        self._accent = None
        self.setWindowTitle(f"配乐 · {task.get('name', '')}")
        self.resize(1100, 820)        # 同视频任务窗，保持一致性
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
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._build_config_tab(), "① 配置+生成")
        self._review_holder = QWidget(); QVBoxLayout(self._review_holder)
        self.tabs.addTab(self._review_holder, "② 试听选优")
        self._accent_holder = QWidget(); QVBoxLayout(self._accent_holder)
        self.tabs.addTab(self._accent_holder, "③ 卡点")

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
        self.btn_export = QPushButton("🎬 导出成片")
        self.btn_export.setObjectName("AccentButton")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_open_dir = QPushButton("📂 打开输出目录")
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        act.addWidget(self.btn_start); act.addWidget(self.btn_export)
        act.addWidget(self.btn_open_dir)
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

    def _mount_session_tabs(self):
        # ② 试听选优
        lay = self._review_holder.layout()
        while lay.count():
            old = lay.takeAt(0).widget()
            if old: old.deleteLater()
        self._review = SegmentReviewWidget(self._session)
        self._review.regenerateRequested.connect(self._on_regenerate)
        self._review.chosenChanged.connect(self._on_chosen_changed)
        lay.addWidget(self._review)
        # ③ 卡点
        lay2 = self._accent_holder.layout()
        while lay2.count():
            old = lay2.takeAt(0).widget()
            if old: old.deleteLater()
        self._accent = AccentEditorWidget(
            self._session,
            big_threshold=float(getattr(self.cfg, "accent_big_threshold", 0.7)))
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

        def task():
            from sound_track_agent import facade
            sess = facade.load_session(work_dir) or facade.prepare_session(
                mp4, style, work_dir)
            self._post_seg_preview(sess)
            facade.advance(sess, work_dir, cfg=cfg, workflow_id=workflow_id,
                           seeds_count=seeds, stop_after=stop_after,
                           on_progress=self._post_progress)
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

    def _on_regen_done(self, sess):
        self.progress.hide()
        self._mount_session_tabs()
        self.tabs.setCurrentIndex(1)
        self.statusChanged.emit(self.task_id, "空闲")

    def _on_failed(self, err: str):
        self.progress.hide(); self.btn_start.setEnabled(True)
        self.statusChanged.emit(self.task_id, "失败")
        QMessageBox.critical(self, "配乐失败", err)

    def _open_output_dir(self):
        wd = self._work_dir()
        if wd.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(wd)))
        else:
            QMessageBox.information(self, "打开输出目录", "还没有输出（先运行一次）")

    def closeEvent(self, event):
        self.closed.emit(self.task_id)
        super().closeEvent(event)
