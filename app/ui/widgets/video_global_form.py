"""VideoGlobalForm：全局参数表单。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QFormLayout, QPlainTextEdit, QCheckBox, QSpinBox,
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
        form = QFormLayout(self)

        # global_prompt
        self.use_global_cb = QCheckBox("启用 global_prompt")
        self.use_global_cb.setChecked(True)
        form.addRow(self.use_global_cb)

        self.global_prompt_edit = QPlainTextEdit()
        self.global_prompt_edit.setMaximumHeight(60)
        self.global_prompt_edit.setPlaceholderText("全片统一风格/角色描述…")
        form.addRow("Global prompt", self.global_prompt_edit)

        # frame_rate
        self.fr_spin = QSpinBox()
        self.fr_spin.setRange(1, 120)
        self.fr_spin.setValue(24)
        self.fr_spin.setSuffix(" fps")
        form.addRow("帧率", self.fr_spin)

        # display_mode
        mode_row = QHBoxLayout()
        self.mode_seconds_btn = QRadioButton("秒")
        self.mode_frames_btn = QRadioButton("帧")
        self.mode_seconds_btn.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.mode_seconds_btn)
        self._mode_group.addButton(self.mode_frames_btn)
        mode_row.addWidget(self.mode_seconds_btn)
        mode_row.addWidget(self.mode_frames_btn)
        mode_row.addStretch(1)
        mode_wrap = QWidget(); mode_wrap.setLayout(mode_row)
        form.addRow("时间显示", mode_wrap)

        # 分辨率
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTION_PRESETS)
        form.addRow("分辨率", self.resolution_combo)

        custom_row = QHBoxLayout()
        self.custom_w_spin = QSpinBox()
        self.custom_w_spin.setRange(64, 4096); self.custom_w_spin.setValue(1024)
        self.custom_h_spin = QSpinBox()
        self.custom_h_spin.setRange(64, 4096); self.custom_h_spin.setValue(1024)
        custom_row.addWidget(self.custom_w_spin)
        custom_row.addWidget(QLabel("×"))
        custom_row.addWidget(self.custom_h_spin)
        custom_row.addStretch(1)
        self.custom_wrap = QWidget(); self.custom_wrap.setLayout(custom_row)
        self.custom_wrap.setVisible(False)
        form.addRow("自定义 W×H", self.custom_wrap)

        # filename_prefix
        self.filename_prefix_edit = QLineEdit("spb_video")
        form.addRow("输出文件名前缀", self.filename_prefix_edit)

    def _wire(self):
        self.use_global_cb.toggled.connect(self._emit)
        self.global_prompt_edit.textChanged.connect(self._emit)
        self.fr_spin.valueChanged.connect(self._emit)
        self.mode_seconds_btn.toggled.connect(self._emit)
        self.resolution_combo.currentTextChanged.connect(self._on_res_changed)
        self.custom_w_spin.valueChanged.connect(self._emit)
        self.custom_h_spin.valueChanged.connect(self._emit)
        self.filename_prefix_edit.textChanged.connect(self._emit)

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
        self._suspend = False
