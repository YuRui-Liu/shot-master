"""VideoGlobalForm：全局参数表单。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QPlainTextEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QLineEdit, QHBoxLayout, QWidget, QRadioButton, QButtonGroup,
    QLabel,
)

from app.core.video_timeline_model import TimelineModel


RESOLUTION_PRESETS = [
    "1280x720 (16:9) (横屏)",
    "720x1280 (9:16) (竖屏)",
    "1024x1024 (1:1)",
    "自定义...",
]


class VideoGlobalForm(QGroupBox):
    """全局：global_prompt / frame_rate / display_mode / 分辨率 / filename_prefix。

    单一 globalChanged 信号；外部用 get_state() 一次性读所有字段。
    """

    globalChanged = Signal()

    def __init__(self, parent=None):
        super().__init__("全局参数", parent)
        self._suspend = False
        self._build_ui()
        self._wire()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ---------- Row 1: 两个启用复选框 ----------
        self.use_global_cb = QCheckBox("启用 global_prompt")
        self.use_global_cb.setChecked(True)
        self.use_custom_audio_cb = QCheckBox("启用音频轨（use_custom_audio）")
        self.use_custom_audio_cb.setChecked(False)
        row1 = QHBoxLayout()
        row1.addWidget(self.use_global_cb)
        row1.addSpacing(24)
        row1.addWidget(self.use_custom_audio_cb)
        row1.addStretch(1)
        root.addLayout(row1)

        # ---------- Row 2: Global prompt 多行 ----------
        root.addWidget(QLabel("Global prompt"))
        self.global_prompt_edit = QPlainTextEdit()
        self.global_prompt_edit.setMaximumHeight(60)
        self.global_prompt_edit.setPlaceholderText("全片统一风格/角色描述…")
        root.addWidget(self.global_prompt_edit)

        # ---------- Row 3: 帧率 / 时间显示 / 分辨率 / 自定义 W×H ----------
        # 帧率
        self.fr_spin = QSpinBox()
        self.fr_spin.setRange(1, 120)
        self.fr_spin.setValue(24)
        self.fr_spin.setSuffix(" fps")
        # 时间显示
        self.mode_seconds_btn = QRadioButton("秒")
        self.mode_frames_btn = QRadioButton("帧")
        self.mode_seconds_btn.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.mode_seconds_btn)
        self._mode_group.addButton(self.mode_frames_btn)
        # 分辨率
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTION_PRESETS)
        self.resolution_combo.setMinimumWidth(200)
        # 自定义 W×H（默认隐藏）
        self.custom_w_spin = QSpinBox()
        self.custom_w_spin.setRange(64, 4096); self.custom_w_spin.setValue(1024)
        self.custom_h_spin = QSpinBox()
        self.custom_h_spin.setRange(64, 4096); self.custom_h_spin.setValue(1024)
        custom_inner = QHBoxLayout()
        custom_inner.setContentsMargins(0, 0, 0, 0)
        custom_inner.setSpacing(2)
        custom_inner.addWidget(QLabel("W"))
        custom_inner.addWidget(self.custom_w_spin)
        custom_inner.addWidget(QLabel("×"))
        custom_inner.addWidget(QLabel("H"))
        custom_inner.addWidget(self.custom_h_spin)
        self.custom_wrap = QWidget()
        self.custom_wrap.setLayout(custom_inner)
        self.custom_wrap.setVisible(False)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("帧率"))
        row3.addWidget(self.fr_spin)
        row3.addSpacing(20)
        row3.addWidget(QLabel("时间显示"))
        row3.addWidget(self.mode_seconds_btn)
        row3.addWidget(self.mode_frames_btn)
        row3.addSpacing(20)
        row3.addWidget(QLabel("分辨率"))
        row3.addWidget(self.resolution_combo)
        row3.addSpacing(12)
        row3.addWidget(self.custom_wrap)
        row3.addStretch(1)
        root.addLayout(row3)

        # ---------- Row 4: 输出文件名前缀 / Epsilon ----------
        self.filename_prefix_edit = QLineEdit("spb_video")
        self.epsilon_spin = QDoubleSpinBox()
        self.epsilon_spin.setRange(0.0, 1.0)
        self.epsilon_spin.setSingleStep(0.05)
        self.epsilon_spin.setDecimals(2)
        self.epsilon_spin.setValue(0.5)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("输出文件名前缀"))
        row4.addWidget(self.filename_prefix_edit, 3)
        row4.addSpacing(20)
        row4.addWidget(QLabel("Epsilon"))
        row4.addWidget(self.epsilon_spin)
        row4.addStretch(1)
        root.addLayout(row4)

    def _wire(self):
        self.use_global_cb.toggled.connect(self._emit)
        self.global_prompt_edit.textChanged.connect(self._emit)
        self.fr_spin.valueChanged.connect(self._emit)
        self.mode_seconds_btn.toggled.connect(self._emit)
        self.resolution_combo.currentTextChanged.connect(self._on_res_changed)
        self.custom_w_spin.valueChanged.connect(self._emit)
        self.custom_h_spin.valueChanged.connect(self._emit)
        self.filename_prefix_edit.textChanged.connect(self._emit)
        self.use_custom_audio_cb.toggled.connect(self._emit)
        self.epsilon_spin.valueChanged.connect(self._emit)

    def _on_res_changed(self, text: str):
        self.custom_wrap.setVisible(text == "自定义...")
        self._emit()

    def _emit(self, *_args):
        if self._suspend:
            return
        self.globalChanged.emit()

    # ---------- 公共 API ----------

    def get_state(self) -> dict:
        is_custom = self.resolution_combo.currentText() == "自定义..."
        return {
            "global_prompt": self.global_prompt_edit.toPlainText(),
            "use_global_prompt": self.use_global_cb.isChecked(),
            "frame_rate": self.fr_spin.value(),
            "display_mode": "seconds" if self.mode_seconds_btn.isChecked() else "frames",
            "resolution_preset": (self.resolution_combo.currentText()
                                   if not is_custom
                                   else "1280x720 (16:9) (横屏)"),
            "use_custom_resolution": is_custom,
            "custom_width": self.custom_w_spin.value(),
            "custom_height": self.custom_h_spin.value(),
            "filename_prefix": self.filename_prefix_edit.text().strip()
                                or "spb_video",
            "use_custom_audio": self.use_custom_audio_cb.isChecked(),
            "epsilon": self.epsilon_spin.value(),
        }

    def set_state(self, m: TimelineModel) -> None:
        self._suspend = True
        self.use_global_cb.setChecked(m.use_global_prompt)
        self.global_prompt_edit.setPlainText(m.global_prompt)
        self.fr_spin.setValue(m.frame_rate)
        if m.display_mode == "seconds":
            self.mode_seconds_btn.setChecked(True)
        else:
            self.mode_frames_btn.setChecked(True)
        if m.use_custom_resolution:
            self.resolution_combo.setCurrentText("自定义...")
            self.custom_w_spin.setValue(m.custom_width)
            self.custom_h_spin.setValue(m.custom_height)
        else:
            idx = self.resolution_combo.findText(m.resolution_preset)
            if idx >= 0:
                self.resolution_combo.setCurrentIndex(idx)
        self.filename_prefix_edit.setText(m.filename_prefix)
        self.custom_wrap.setVisible(m.use_custom_resolution)
        self.use_custom_audio_cb.setChecked(m.use_custom_audio)
        self.epsilon_spin.setValue(m.epsilon)
        self._suspend = False
