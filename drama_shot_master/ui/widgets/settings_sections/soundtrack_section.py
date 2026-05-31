"""SoundtrackSection：配乐 workflow_id / 输出目录 / 候选数 / crossfade 等配置 section。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QSpinBox,
    QDoubleSpinBox, QHBoxLayout, QFileDialog, QComboBox, QLabel, QCheckBox,
)


class SoundtrackSection(QWidget):
    title = "配乐"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.workflow_edit = QLineEdit()
        form.addRow("ACE-Step ID", self.workflow_edit)

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("空=用 视频输出目录/soundtrack")
        b = QPushButton("浏览…")
        b.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(b)
        out_wrap = QWidget()
        out_wrap.setLayout(out_row)
        form.addRow("默认输出目录", out_wrap)

        self.seeds_spin = QSpinBox()
        self.seeds_spin.setRange(1, 4)
        form.addRow("默认候选数", self.seeds_spin)

        self.crossfade_spin = QDoubleSpinBox()
        self.crossfade_spin.setRange(0.0, 3.0)
        self.crossfade_spin.setSingleStep(0.1)
        self.crossfade_spin.setDecimals(1)
        self.crossfade_spin.setSuffix(" s")
        form.addRow("crossfade 时长", self.crossfade_spin)

        # ACE-Step 末尾结构标记开关：开启会让 BGM 末段约 25% 衰减到静音；默认关闭。
        self.fade_out_check = QCheckBox("BGM 末尾自然淡出（关闭可保住完整段长，推荐关闭）")
        self.fade_out_check.setToolTip(
            "勾选时给 ACE-Step prompt 追加 [Quick smooth fade out] 结构标记。\n"
            "模型会将该标记解读为 outro，使短段（20-30s）末尾约 25% 渐衰到静音。\n"
            "默认关闭——大多剧用场景需要完整有声 BGM，由 mix 阶段统一做 crossfade。")
        form.addRow("末尾淡出", self.fade_out_check)

        self.big_thresh_spin = QDoubleSpinBox()
        self.big_thresh_spin.setRange(0.0, 1.0)
        self.big_thresh_spin.setSingleStep(0.05)
        self.big_thresh_spin.setDecimals(2)
        form.addRow("大卡点强度阈值", self.big_thresh_spin)

        self.snap_window_spin = QDoubleSpinBox()
        self.snap_window_spin.setRange(0.0, 3.0)
        self.snap_window_spin.setSingleStep(0.1)
        self.snap_window_spin.setDecimals(1)
        self.snap_window_spin.setSuffix(" s")
        form.addRow("段切吸附窗口", self.snap_window_spin)

        # === Sprint 0：曝光 Phase 1+2+3 后端能力 ===

        self.frames_combo = QComboBox()
        self.frames_combo.addItems(["1", "3", "5"])
        form.addRow("精排抽帧数 (1/3/5)", self.frames_combo)

        self.refine_max_spin = QSpinBox()
        self.refine_max_spin.setRange(1, 10)
        form.addRow("邻接合并段数上限", self.refine_max_spin)

        self.refine_thresh_spin = QDoubleSpinBox()
        self.refine_thresh_spin.setRange(0.0, 1.0)
        self.refine_thresh_spin.setSingleStep(0.05)
        self.refine_thresh_spin.setDecimals(2)
        form.addRow("邻接合并相似阈值", self.refine_thresh_spin)

        self.stretch_spin = QDoubleSpinBox()
        self.stretch_spin.setRange(0.0, 0.5)
        self.stretch_spin.setSingleStep(0.01)
        self.stretch_spin.setDecimals(2)
        form.addRow("真·卡点拉伸上限 (±)", self.stretch_spin)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 10)
        form.addRow("生成并发上限", self.concurrency_spin)

        # 打分权重三轴
        weights_row = QHBoxLayout()
        self.w_health = QDoubleSpinBox()
        self.w_health.setRange(0.0, 1.0); self.w_health.setSingleStep(0.05); self.w_health.setDecimals(2)
        self.w_headroom = QDoubleSpinBox()
        self.w_headroom.setRange(0.0, 1.0); self.w_headroom.setSingleStep(0.05); self.w_headroom.setDecimals(2)
        self.w_beat = QDoubleSpinBox()
        self.w_beat.setRange(0.0, 1.0); self.w_beat.setSingleStep(0.05); self.w_beat.setDecimals(2)
        weights_row.addWidget(QLabel("health"))
        weights_row.addWidget(self.w_health)
        weights_row.addWidget(QLabel("headroom"))
        weights_row.addWidget(self.w_headroom)
        weights_row.addWidget(QLabel("beat"))
        weights_row.addWidget(self.w_beat)
        weights_wrap = QWidget()
        weights_wrap.setLayout(weights_row)
        form.addRow("候选打分权重", weights_wrap)

        # === Phase 4a SFX 层配置 ===

        self.sfx_workflow_edit = QLineEdit()
        self.sfx_workflow_edit.setPlaceholderText("Stable Audio 3 / RunningHub workflow id")
        form.addRow("SFX Workflow ID", self.sfx_workflow_edit)

        self.sfx_frames_combo = QComboBox()
        self.sfx_frames_combo.addItems(["1", "3", "5"])
        form.addRow("SFX 检测抽帧数", self.sfx_frames_combo)

        self.sfx_concurrency_spin = QSpinBox()
        self.sfx_concurrency_spin.setRange(1, 10)
        form.addRow("SFX 并发上限", self.sfx_concurrency_spin)

        self.sfx_volume_spin = QDoubleSpinBox()
        self.sfx_volume_spin.setRange(0.0, 1.5)
        self.sfx_volume_spin.setSingleStep(0.05)
        self.sfx_volume_spin.setDecimals(2)
        form.addRow("SFX 默认音量", self.sfx_volume_spin)

        self.sfx_ducking_spin = QDoubleSpinBox()
        self.sfx_ducking_spin.setRange(-20.0, 0.0)
        self.sfx_ducking_spin.setSingleStep(0.5)
        self.sfx_ducking_spin.setDecimals(1)
        self.sfx_ducking_spin.setSuffix(" dB")
        form.addRow("SFX 触发 BGM 衰减", self.sfx_ducking_spin)

        self.sfx_seeds_spin = QSpinBox()
        self.sfx_seeds_spin.setRange(1, 5)
        form.addRow("SFX 单镜候选数", self.sfx_seeds_spin)

        root.addLayout(form)
        root.addStretch(1)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择默认输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def load_from(self, cfg):
        self.workflow_edit.setText(
            getattr(cfg, "soundtrack_workflow_id", "") or "")
        self.out_edit.setText(
            getattr(cfg, "soundtrack_output_dir", "") or "")
        self.seeds_spin.setValue(
            int(getattr(cfg, "soundtrack_seeds_count", 2)))
        self.crossfade_spin.setValue(
            float(getattr(cfg, "soundtrack_crossfade", 0.5)))
        self.fade_out_check.setChecked(
            bool(getattr(cfg, "soundtrack_fade_out", False)))
        self.big_thresh_spin.setValue(
            float(getattr(cfg, "accent_big_threshold", 0.7)))
        self.snap_window_spin.setValue(
            float(getattr(cfg, "accent_snap_window", 0.6)))
        self.frames_combo.setCurrentText(
            str(int(getattr(cfg, "refine_frames_per_shot", 3))))
        self.refine_max_spin.setValue(int(getattr(cfg, "refine_max_segments", 5)))
        self.refine_thresh_spin.setValue(
            float(getattr(cfg, "refine_merge_threshold", 0.25)))
        self.stretch_spin.setValue(float(getattr(cfg, "accent_max_stretch", 0.10)))
        self.concurrency_spin.setValue(
            int(getattr(cfg, "soundtrack_max_concurrency", 3)))
        w = getattr(cfg, "soundtrack_score_weights", None) \
            or {"health": 0.5, "headroom": 0.3, "beat": 0.2}
        self.w_health.setValue(float(w.get("health", 0.5)))
        self.w_headroom.setValue(float(w.get("headroom", 0.3)))
        self.w_beat.setValue(float(w.get("beat", 0.2)))
        self.sfx_workflow_edit.setText(
            str(getattr(cfg, "sfx_workflow_id", "") or ""))
        self.sfx_frames_combo.setCurrentText(
            str(int(getattr(cfg, "sfx_plan_frames_per_shot", 3))))
        self.sfx_concurrency_spin.setValue(
            int(getattr(cfg, "sfx_max_concurrency", 3)))
        self.sfx_volume_spin.setValue(
            float(getattr(cfg, "sfx_default_volume", 0.8)))
        self.sfx_ducking_spin.setValue(
            float(getattr(cfg, "sfx_ducking_db", -6.0)))
        self.sfx_seeds_spin.setValue(
            int(getattr(cfg, "sfx_seeds_count", 1)))

    def save_to(self, cfg):
        cfg.update_settings(
            soundtrack_workflow_id=self.workflow_edit.text().strip(),
            soundtrack_output_dir=self.out_edit.text().strip(),
            soundtrack_seeds_count=self.seeds_spin.value(),
            soundtrack_crossfade=self.crossfade_spin.value(),
            accent_big_threshold=self.big_thresh_spin.value(),
            accent_snap_window=self.snap_window_spin.value(),
            # Sprint 0：曝光 Phase 1+2+3 后端能力
            refine_frames_per_shot=int(self.frames_combo.currentText()),
            refine_max_segments=self.refine_max_spin.value(),
            refine_merge_threshold=float(self.refine_thresh_spin.value()),
            accent_max_stretch=float(self.stretch_spin.value()),
            soundtrack_max_concurrency=self.concurrency_spin.value(),
            soundtrack_score_weights={
                "health": float(self.w_health.value()),
                "headroom": float(self.w_headroom.value()),
                "beat": float(self.w_beat.value()),
            },
            soundtrack_fade_out=bool(self.fade_out_check.isChecked()),
            sfx_workflow_id=self.sfx_workflow_edit.text().strip(),
            sfx_plan_frames_per_shot=int(self.sfx_frames_combo.currentText()),
            sfx_max_concurrency=self.sfx_concurrency_spin.value(),
            sfx_default_volume=float(self.sfx_volume_spin.value()),
            sfx_ducking_db=float(self.sfx_ducking_spin.value()),
            sfx_seeds_count=self.sfx_seeds_spin.value(),
        )

    def validate(self):
        return (True, "")

    def cancel_workers(self):
        pass
