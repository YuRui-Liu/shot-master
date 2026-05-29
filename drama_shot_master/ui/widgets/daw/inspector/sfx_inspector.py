from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QSlider, QButtonGroup,
    QRadioButton, QDoubleSpinBox, QCheckBox,
)
from drama_shot_master.ui.widgets.daw.commands import ResizeCue


class SfxInspector(QWidget):
    promptEditRequested = Signal(object)    # _CueRef
    candidateChosen = Signal(object, int)   # _CueRef, new_idx
    regenerateRequested = Signal(object)    # _CueRef
    volumeChanged = Signal(object, float)   # _CueRef, volume
    enabledChanged = Signal(object, bool)   # _CueRef, enabled
    commandIssued = Signal(object)          # Command（ResizeCue）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ref = None
        self._session = None
        self._suppress_dur = False
        self._old_duration = 0.0
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("SFX 镜")
        lay.addWidget(self.title)
        self.time_label = QLabel("0:00 (3.0s)")
        lay.addWidget(self.time_label)
        lay.addWidget(QLabel("时长 (s):"))
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(1.0, 15.0)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setSuffix(" s")
        self.duration_spin.valueChanged.connect(self._on_duration)
        lay.addWidget(self.duration_spin)
        lay.addWidget(QLabel("短描述:"))
        self.prompt_label = QLabel("")
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            "background:#1a1a1a;padding:4px;border-radius:2px;")
        lay.addWidget(self.prompt_label)
        self.btn_edit_prompt = QPushButton("✎ 编辑 prompt")
        self.btn_edit_prompt.clicked.connect(
            lambda: self._ref and self.promptEditRequested.emit(self._ref))
        lay.addWidget(self.btn_edit_prompt)
        lay.addWidget(QLabel("候选:"))
        self.cand_group = QButtonGroup(self)
        self.cand_layout = QVBoxLayout()
        lay.addLayout(self.cand_layout)
        lay.addWidget(QLabel("音量:"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(80)
        self.vol_slider.valueChanged.connect(self._on_volume)
        lay.addWidget(self.vol_slider)
        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True)
        self.enabled_check.toggled.connect(self._on_enabled)
        lay.addWidget(self.enabled_check)
        self.btn_regen = QPushButton("↻ 重生成")
        self.btn_regen.clicked.connect(
            lambda: self._ref and self.regenerateRequested.emit(self._ref))
        lay.addWidget(self.btn_regen)
        lay.addStretch(1)

    def set_cue_ref(self, ref, session):
        self._ref = ref
        self._session = session
        shot = session.shots[ref.seg_index] if session else None
        if shot is None:
            return
        self.title.setText(f"SFX 镜 {ref.seg_index}")
        self.time_label.setText(f"{shot.t_start:.1f}s ({shot.duration:.1f}s)")
        self._suppress_dur = True
        self.duration_spin.setValue(float(shot.duration))
        self._suppress_dur = False
        self._old_duration = float(shot.duration)
        self.prompt_label.setText(getattr(shot, "prompt_short", "") or "(空)")
        self.vol_slider.setValue(int(getattr(shot, "volume", 1.0) * 100))
        self.enabled_check.setChecked(getattr(shot, "enabled", True))
        for btn in list(self.cand_group.buttons()):
            self.cand_group.removeButton(btn)
            btn.deleteLater()
        for i, c in enumerate(shot.candidates):
            rb = QRadioButton(f"seed={c.seed}")
            self.cand_group.addButton(rb, i)
            self.cand_layout.addWidget(rb)
            if i == shot.chosen_candidate:
                rb.setChecked(True)
            rb.toggled.connect(
                lambda checked, idx=i:
                    checked and self._ref
                    and self.candidateChosen.emit(self._ref, idx))

    def _on_duration(self, new_val: float):
        if self._suppress_dur or self._ref is None:
            return
        dt = new_val - self._old_duration
        self._old_duration = new_val
        cmd = ResizeCue(None, self._session, self._ref, side="end", dt_sec=dt)
        self.commandIssued.emit(cmd)

    def _on_volume(self, val: int):
        if self._ref:
            self.volumeChanged.emit(self._ref, val / 100.0)

    def _on_enabled(self, checked: bool):
        if self._ref:
            self.enabledChanged.emit(self._ref, checked)
