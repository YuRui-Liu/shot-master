"""SegmentEditor：per-seg 编辑表单。始终可见，未选中时灰化。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QFormLayout, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
    QWidget,
)

from app.core.video_timeline_model import TimelineSegment


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

        form = QFormLayout(self)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setPlaceholderText("本段 prompt（仅作用于此段）")
        form.addRow("Prompt", self.prompt_edit)

        self.length_spin = QSpinBox()
        self.length_spin.setRange(1, 99999)
        self.length_spin.setValue(24)
        form.addRow("长度", self.length_spin)

        self.guide_spin = QDoubleSpinBox()
        self.guide_spin.setRange(0.0, 1.0)
        self.guide_spin.setSingleStep(0.05)
        self.guide_spin.setDecimals(2)
        self.guide_spin.setValue(1.0)
        form.addRow("Guide", self.guide_spin)

        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.length_spin.valueChanged.connect(self._on_length_changed)
        self.guide_spin.valueChanged.connect(self._on_guide_changed)

        self._set_enabled_all(False)

    # ---------- 公共 API ----------

    def bind_to(self, seg: Optional[TimelineSegment],
                display_mode: str, frame_rate: int) -> None:
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self._suspend = True
        if seg is None:
            self._bound_seg_id = ""
            self.prompt_edit.clear()
            self.length_spin.setValue(1)
            self.guide_spin.setValue(1.0)
            self._set_enabled_all(False)
        else:
            self._bound_seg_id = seg.seg_id
            self.prompt_edit.setPlainText(seg.local_prompt)
            self.length_spin.setValue(seg.length_frames)
            self.guide_spin.setValue(seg.guide_strength)
            self._update_length_suffix(seg.length_frames)
            self._set_enabled_all(True)
        self._suspend = False

    # ---------- 内部 ----------

    def _set_enabled_all(self, on: bool):
        for w in (self.prompt_edit, self.length_spin, self.guide_spin):
            w.setEnabled(on)

    def _update_length_suffix(self, frames: int):
        if self._display_mode == "frames":
            self.length_spin.setSuffix(" f")
        else:
            sec = frames / max(self._frame_rate, 1)
            self.length_spin.setSuffix(f" f (≈{sec:.2f}s)")

    def _on_prompt_changed(self):
        if self._suspend or not self._bound_seg_id:
            return
        self.segmentEdited.emit(self._bound_seg_id, "local_prompt",
                                 self.prompt_edit.toPlainText())

    def _on_length_changed(self, value: int):
        if self._suspend or not self._bound_seg_id:
            return
        self._update_length_suffix(value)
        self.segmentEdited.emit(self._bound_seg_id, "length_frames", value)

    def _on_guide_changed(self, value: float):
        if self._suspend or not self._bound_seg_id:
            return
        self.segmentEdited.emit(self._bound_seg_id, "guide_strength", value)
