"""SegmentEditor：per-seg 编辑表单。

按 display_mode 切换长度输入单位：
  - "frames": QSpinBox 显示帧数（如 "33 f"）
  - "seconds": QDoubleSpinBox 显示秒数（如 "1.38 s"），内部换算回帧数

未绑定段时全控件 disabled。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox,
    QDoubleSpinBox, QStackedWidget, QWidget,
)

from drama_shot_master.core.video_timeline_model import TimelineSegment
from drama_shot_master.ui.widgets.translate_button import attach_translate_button


class SegmentEditor(QGroupBox):
    """per-seg 编辑：local_prompt + length（按 display_mode 切单位）+ guide_strength。

    所有控件未绑定时 disabled；bind_to 切换显示对象。
    每次字段变化 emit segmentEdited(seg_id, field_name, new_value)。
    """

    segmentEdited = Signal(str, str, object)   # (seg_id, field, value)

    def __init__(self, parent=None):
        super().__init__("当前段（点时间轴选中编辑）", parent)
        self._bound_seg_id = ""
        self._display_mode = "seconds"
        self._frame_rate = 24
        self._suspend = False

        root = QVBoxLayout(self)
        root.setSpacing(6)

        # Prompt label + 译按钮 + multi-line edit
        self.prompt_edit = QPlainTextEdit()
        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("Prompt"))
        prompt_row.addStretch(1)
        prompt_row.addWidget(attach_translate_button(self.prompt_edit, self))
        root.addLayout(prompt_row)
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setPlaceholderText("本段 prompt（仅作用于此段）")
        root.addWidget(self.prompt_edit)

        # 长度（按 display_mode 切单位的 stacked spin）
        self.length_frames_spin = QSpinBox()
        self.length_frames_spin.setRange(1, 99999)
        self.length_frames_spin.setValue(24)
        self.length_frames_spin.setSuffix(" f")

        self.length_seconds_spin = QDoubleSpinBox()
        self.length_seconds_spin.setRange(0.01, 9999.99)
        self.length_seconds_spin.setSingleStep(0.10)
        self.length_seconds_spin.setDecimals(2)
        self.length_seconds_spin.setValue(1.0)
        self.length_seconds_spin.setSuffix(" s")

        self.length_stack = QStackedWidget()
        self.length_stack.addWidget(self.length_frames_spin)   # index 0
        self.length_stack.addWidget(self.length_seconds_spin)  # index 1
        # 让 stack 不要无限拉伸——固定到 spin 的高度
        self.length_stack.setSizePolicy(
            self.length_stack.sizePolicy().horizontalPolicy(),
            self.length_frames_spin.sizePolicy().verticalPolicy())
        self.length_stack.setMaximumHeight(
            self.length_frames_spin.sizeHint().height() + 4)

        # Guide
        self.guide_spin = QDoubleSpinBox()
        self.guide_spin.setRange(0.0, 1.0)
        self.guide_spin.setSingleStep(0.05)
        self.guide_spin.setDecimals(2)
        self.guide_spin.setValue(1.0)

        # 同行：长度 + Guide
        row = QHBoxLayout()
        row.addWidget(QLabel("长度"))
        row.addWidget(self.length_stack)
        row.addSpacing(24)
        row.addWidget(QLabel("Guide"))
        row.addWidget(self.guide_spin)
        row.addStretch(1)
        root.addLayout(row)

        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.length_frames_spin.valueChanged.connect(
            self._on_length_frames_changed)
        self.length_seconds_spin.valueChanged.connect(
            self._on_length_seconds_changed)
        self.guide_spin.valueChanged.connect(self._on_guide_changed)

        self._set_enabled_all(False)

    # ---------- 公共 API ----------

    def bind_to(self, seg: Optional[TimelineSegment],
                display_mode: str, frame_rate: int) -> None:
        self._display_mode = display_mode
        self._frame_rate = max(frame_rate, 1)
        self._suspend = True
        # 切换 stack 显示页
        self.length_stack.setCurrentIndex(
            0 if display_mode == "frames" else 1)
        if seg is None:
            self._bound_seg_id = ""
            self.prompt_edit.clear()
            self.length_frames_spin.setValue(1)
            self.length_seconds_spin.setValue(1.0 / self._frame_rate)
            self.guide_spin.setValue(1.0)
            self._set_enabled_all(False)
        else:
            self._bound_seg_id = seg.seg_id
            self.prompt_edit.setPlainText(seg.local_prompt)
            self._set_length_display_from_frames(seg.length_frames)
            self.guide_spin.setValue(seg.guide_strength)
            self._set_enabled_all(True)
        self._suspend = False

    # ---------- 内部 ----------

    def _set_enabled_all(self, on: bool):
        for w in (self.prompt_edit, self.length_stack, self.guide_spin):
            w.setEnabled(on)

    def _set_length_display_from_frames(self, frames: int):
        """根据当前 display_mode 把帧数显示到对应 spin。"""
        self.length_frames_spin.setValue(frames)
        seconds = frames / max(self._frame_rate, 1)
        self.length_seconds_spin.setValue(max(seconds, 0.01))

    def _on_prompt_changed(self):
        if self._suspend or not self._bound_seg_id:
            return
        self.segmentEdited.emit(self._bound_seg_id, "local_prompt",
                                 self.prompt_edit.toPlainText())

    def _on_length_frames_changed(self, value: int):
        if self._suspend or not self._bound_seg_id:
            return
        # 同步秒值（不触发反向 emit）
        self._suspend = True
        self.length_seconds_spin.setValue(value / max(self._frame_rate, 1))
        self._suspend = False
        self.segmentEdited.emit(self._bound_seg_id, "length_frames", value)

    def _on_length_seconds_changed(self, value: float):
        if self._suspend or not self._bound_seg_id:
            return
        frames = max(1, int(round(value * self._frame_rate)))
        # 同步帧值（不触发反向 emit）
        self._suspend = True
        self.length_frames_spin.setValue(frames)
        self._suspend = False
        self.segmentEdited.emit(self._bound_seg_id, "length_frames", frames)

    def _on_guide_changed(self, value: float):
        if self._suspend or not self._bound_seg_id:
            return
        self.segmentEdited.emit(self._bound_seg_id, "guide_strength", value)
