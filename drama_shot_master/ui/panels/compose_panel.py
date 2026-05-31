"""成片编辑器：看片剔除/排序/trim + 一键 xfade 拼接。对照 成片合成-layout.html。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSplitter,
    QProgressBar, QFileDialog,
)

from drama_shot_master.core.composition_model import CompositionModel, ReelClip
from drama_shot_master.core.ffmpeg_locate import probe_duration
from drama_shot_master.core import transition_render as tr
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget
from drama_shot_master.ui.widgets.compose.clip_strip import ClipStrip
from drama_shot_master.ui.widgets.compose.trim_bar import TrimBar
from drama_shot_master.ui.widgets.compose.transition_inspector import TransitionInspector
from drama_shot_master.ui.worker import FunctionWorker

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}


class ComposePanel(QWidget):
    statusMessage = Signal(str)
    dirty = Signal()
    renderRequested = Signal()
    renderStarted = Signal(str)    # task_id
    renderCompleted = Signal(str, str)  # task_id, out_path
    sendToSoundtrack = Signal(str)
    analyzeRequested = Signal()

    def __init__(self, cfg, payload: dict | None = None, task_id: str = "", parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._task_id = task_id
        self._model = CompositionModel.from_dict(payload or {"clips": []})
        self._worker = None
        self._sel_clip = None
        self._model_output = ""
        self._build_ui()
        self._reload()

    def model(self) -> CompositionModel:
        return self._model

    def to_payload(self) -> dict:
        return self._model.to_dict()

    def add_clips(self, paths: list[str]):
        for p in paths:
            try:
                dur = probe_duration(p)
            except Exception:
                dur = 0.0
            self._model.clips.append(ReelClip.new(path=p, duration=dur))
        self._reload(); self.dirty.emit()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        tb = QHBoxLayout(); tb.setContentsMargins(12, 10, 12, 10)
        self._title = QLabel("成片"); self._title.setObjectName("ComposeTitle")
        tb.addWidget(self._title); tb.addStretch(1)
        b_listdir = QPushButton("⟳ 列出生成目录"); b_listdir.clicked.connect(self._list_output_dir)
        b_add = QPushButton("＋ 添加片段"); b_add.clicked.connect(self._pick_files)
        self._b_analyze = QPushButton("✦ 一键智能转场"); self._b_analyze.setObjectName("ComposePrimary")
        self._b_analyze.clicked.connect(self._on_analyze)
        self._b_render = QPushButton("⬇ 生成成片"); self._b_render.setObjectName("ComposeRenderBtn")
        self._b_render.clicked.connect(self._on_render)
        for b in (b_listdir, b_add, self._b_analyze, self._b_render):
            tb.addWidget(b)
        root.addLayout(tb)

        self._strip = ClipStrip()
        self._strip.clipSelected.connect(self._on_clip_selected)
        self._strip.connectorSelected.connect(self._on_conn_selected)
        self._strip.keepToggled.connect(lambda *_: self.dirty.emit())
        self._strip.orderChanged.connect(self._on_reorder)
        root.addWidget(self._strip)

        lower = QSplitter(Qt.Horizontal)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(12, 8, 12, 8)
        self._preview = VideoPreviewWidget()
        self._trim = TrimBar(); self._trim.trimChanged.connect(self._on_trim)
        lv.addWidget(self._preview, 1); lv.addWidget(self._trim)
        lower.addWidget(left)
        self._inspector = TransitionInspector()
        self._inspector.changed.connect(self._on_transition_changed)
        self._inspector.resetToAuto.connect(self._on_reset_auto)
        self._inspector.applyToAll.connect(self._on_apply_all)
        lower.addWidget(self._inspector)
        lower.setSizes([700, 248])
        root.addWidget(lower, 1)

        rb = QHBoxLayout(); rb.setContentsMargins(12, 8, 12, 8)
        self._progress = QProgressBar(); self._progress.setVisible(False)
        self._status = QLabel("")
        self._b_send = QPushButton("送去配乐 ›"); self._b_send.setEnabled(False)
        self._b_send.clicked.connect(lambda: self.sendToSoundtrack.emit(self._model_output))
        rb.addWidget(self._status); rb.addWidget(self._progress, 1); rb.addWidget(self._b_send)
        root.addLayout(rb)

    def _reload(self):
        self._strip.set_model(self._model)

    def _list_output_dir(self):
        d = getattr(self.cfg, "video_output_dir", "") or ""
        if not d or not Path(d).is_dir():
            self.statusMessage.emit("未设置视频输出目录"); return
        found = [str(p) for p in sorted(Path(d).glob("*")) if p.suffix.lower() in _VIDEO_EXTS]
        existing = {c.path for c in self._model.clips}
        self.add_clips([p for p in found if p not in existing])

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "添加片段", "", "视频 (*.mp4 *.mov *.mkv *.webm)")
        if files:
            self.add_clips(files)

    def _on_clip_selected(self, cid):
        c = self._model.get(cid)
        if c is None:
            return
        self._preview.set_source(c.path)
        self._trim.set_clip(c.duration, c.in_point, c.out_point)
        self._sel_clip = cid

    def _on_trim(self, i, o):
        if self._sel_clip:
            self._model.update_clip(self._sel_clip, in_point=i, out_point=o); self.dirty.emit()

    def _on_conn_selected(self, idx):
        kept = self._model.kept_clips()
        if idx >= len(kept) - 1:
            return
        c = kept[idx]
        src = "user" if c.user_transition else "auto"
        self._inspector.set_connector(idx, c.effective_transition(), c.effective_duration(), src, c.locked,
                                      cv_scores=c.cv_scores)

    def _on_transition_changed(self, idx, eff, dur, locked):
        kept = self._model.kept_clips()
        if idx < len(kept) - 1:
            kept[idx].user_transition = eff; kept[idx].user_duration = dur; kept[idx].locked = locked
            self._strip.refresh(); self.dirty.emit()

    def _on_reset_auto(self, idx):
        kept = self._model.kept_clips()
        if idx < len(kept) - 1:
            kept[idx].user_transition = None; kept[idx].user_duration = None
            self._strip.refresh(); self.dirty.emit()

    def _on_apply_all(self, eff, dur):
        for c in self._model.kept_clips()[:-1]:
            if not c.locked:
                c.user_transition = eff; c.user_duration = dur
        self._strip.refresh(); self.dirty.emit()

    def _on_reorder(self, ordered_ids):
        self._model.reorder_clips(ordered_ids); self._reload(); self.dirty.emit()

    def _on_analyze(self):
        from drama_shot_master.core import transition_analyzer as ta
        if len(self._model.kept_clips()) < 2:
            self.statusMessage.emit("至少 2 个保留片段才能分析转场"); return
        self._progress.setVisible(True); self._progress.setRange(0, 0)
        self._status.setText("CV 分析中…"); self._b_analyze.setEnabled(False)
        comp = self._model
        def job():
            ta.analyze_composition(comp, progress_cb=None)
            return True
        self._aworker = FunctionWorker(job)
        self._aworker.finished_with_result.connect(self._on_analyze_done)
        self._aworker.failed.connect(self._on_analyze_failed)
        self._aworker.start(); self.analyzeRequested.emit()

    def _run_analyze(self, analyzer=None):
        """同步分析入口（测试/无线程）。"""
        from drama_shot_master.core import transition_analyzer as ta
        (analyzer or ta.analyze_composition)(self._model, progress_cb=None)
        self._strip.refresh(); self.dirty.emit()

    def _on_analyze_done(self, _ok):
        self._progress.setVisible(False); self._b_analyze.setEnabled(True)
        self._status.setText("CV 分析完成"); self._strip.refresh(); self.dirty.emit()
        self.statusMessage.emit("智能转场分析完成，请审阅各切口推荐")

    def _on_analyze_failed(self, err):
        self._progress.setVisible(False); self._b_analyze.setEnabled(True)
        self._status.setText("分析失败"); self.statusMessage.emit(err)

    def _on_render(self):
        ok, msg = self._model.validate()
        if not ok:
            self.statusMessage.emit(msg); return
        if msg != "ok":
            self.statusMessage.emit(msg)
        out_dir = getattr(self.cfg, "video_output_dir", "") or "."
        name = self._task_id or f"{id(self):x}"
        out = str(Path(out_dir) / f"{self._model.output_prefix}_{name}.mp4")
        self._progress.setVisible(True); self._progress.setRange(0, 0)
        self._status.setText("渲染中…"); self._b_render.setEnabled(False)
        comp = CompositionModel.from_dict(self._model.to_dict())
        self._worker = FunctionWorker(tr.render, comp, out)
        self._worker.finished_with_result.connect(self._on_render_done)
        self._worker.failed.connect(self._on_render_failed)
        self._worker.start()
        self.renderRequested.emit()
        self.renderStarted.emit(self._task_id)

    def _on_render_done(self, out_path):
        self._model_output = out_path
        self._progress.setVisible(False); self._b_render.setEnabled(True)
        self._b_send.setEnabled(True); self._status.setText("成片完成")
        self._preview.set_source(out_path)
        self.statusMessage.emit(f"成片完成：{out_path}")
        self.renderCompleted.emit(self._task_id, out_path)

    def _on_render_failed(self, err):
        self._progress.setVisible(False); self._b_render.setEnabled(True)
        self._status.setText("渲染失败")
        self.statusMessage.emit(err)
