"""SoundtrackTaskWindow：单集配乐任务窗（第一期骨架）。

表单 + 段落预览 + 进度。开始 → FunctionWorker 跑 facade.prepare_session + advance。
试听选优/卡点编辑留第二期。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QComboBox, QProgressBar,
    QFileDialog, QMessageBox,
)

from drama_shot_master.ui.worker import FunctionWorker

DEFAULT_WORKFLOW_ID = "2059090557116440578"
_STAGES = ["tag_emotion", "compose_prompt", "generate", "align", "mix"]
_STAGE_LABELS = {"tag_emotion": "切段+情绪", "compose_prompt": "prompt",
                 "generate": "生成(选优点)", "align": "对齐", "mix": "出片"}


class SoundtrackTaskWindow(QMainWindow):
    """单集配乐任务窗。"""

    statusChanged = Signal(str, str)        # (task_id, status_text)
    resultReady = Signal(str, str)          # (task_id, output_path)

    def __init__(self, task: dict, cfg, work_root, parent=None):
        super().__init__(parent)
        self._task = task
        self.cfg = cfg
        self._work_root = Path(work_root)
        self._worker = None
        self.setWindowTitle(f"配乐 · {task.get('name', '')}")
        self.resize(680, 560)
        self._build_ui()

    @property
    def task_id(self) -> str:
        return self._task.get("id", "")

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)

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

        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("Workflow ID:"))
        self.workflow_edit = QLineEdit(
            self._task.get("workflow_id") or DEFAULT_WORKFLOW_ID)
        cfg_row.addWidget(self.workflow_edit, 1)
        cfg_row.addWidget(QLabel("候选数:"))
        self.seeds_spin = QSpinBox(); self.seeds_spin.setRange(1, 4)
        self.seeds_spin.setValue(2)
        cfg_row.addWidget(self.seeds_spin)
        cfg_row.addWidget(QLabel("停在:"))
        self.stop_combo = QComboBox()
        for s in _STAGES:
            self.stop_combo.addItem(_STAGE_LABELS[s], s)
        self.stop_combo.setCurrentIndex(_STAGES.index("generate"))
        cfg_row.addWidget(self.stop_combo)
        root.addLayout(cfg_row)

        root.addWidget(QLabel("段落预览:"))
        self.seg_preview = QPlainTextEdit(); self.seg_preview.setReadOnly(True)
        self.seg_preview.setMaximumHeight(160)
        root.addWidget(self.seg_preview, 1)

        act = QHBoxLayout()
        self.btn_start = QPushButton("🎬 开始配乐")
        self.btn_start.setObjectName("AccentButton")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel = QPushButton("取消"); self.btn_cancel.setEnabled(False)
        act.addWidget(self.btn_start); act.addWidget(self.btn_cancel)
        act.addStretch(1)
        root.addLayout(act)

        self.progress = QProgressBar(); self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress_label = QLabel("")
        root.addWidget(self.progress); root.addWidget(self.progress_label)

    def _browse_mp4(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择成片 MP4", self.mp4_edit.text() or "", "视频 (*.mp4 *.mov)")
        if p:
            self.mp4_edit.setText(p)

    def _post_progress(self, msg: str):
        QTimer.singleShot(0, lambda: self.progress_label.setText(msg))

    def _on_start(self):
        mp4 = self.mp4_edit.text().strip()
        style = self.style_edit.toPlainText().strip()
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无法开始", "请选择存在的成片 MP4")
            return
        if not style:
            QMessageBox.warning(self, "无法开始", "请填写总风格")
            return
        workflow_id = self.workflow_edit.text().strip() or DEFAULT_WORKFLOW_ID
        seeds = self.seeds_spin.value()
        stop_after = self.stop_combo.currentData()
        work_dir = self._work_root / self.task_id
        cfg = self.cfg

        def task():
            from sound_track_agent import facade
            sess = facade.prepare_session(mp4, style, work_dir)
            self._post_seg_preview(sess)
            return facade.advance(
                sess, work_dir, cfg=cfg, workflow_id=workflow_id,
                seeds_count=seeds, stop_after=stop_after,
                on_progress=self._post_progress)

        self.btn_start.setEnabled(False)
        self.progress.show()
        self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _post_seg_preview(self, sess):
        lines = [f"段{s.index}  {s.t_start:.1f}–{s.t_end:.1f}s" for s in sess.segments]
        QTimer.singleShot(0, lambda: self.seg_preview.setPlainText("\n".join(lines)))

    def _on_done(self, sess):
        self.progress.hide()
        self.btn_start.setEnabled(True)
        out = getattr(sess, "output", None)
        if out:
            self.statusChanged.emit(self.task_id, "完成")
            self.resultReady.emit(self.task_id, out)
            self.progress_label.setText(f"完成：{out}")
        else:
            self.statusChanged.emit(self.task_id, "空闲")
            self.progress_label.setText("已停在选优点（候选已生成）")

    def _on_failed(self, err: str):
        self.progress.hide()
        self.btn_start.setEnabled(True)
        self.statusChanged.emit(self.task_id, "失败")
        QMessageBox.critical(self, "配乐失败", err)
