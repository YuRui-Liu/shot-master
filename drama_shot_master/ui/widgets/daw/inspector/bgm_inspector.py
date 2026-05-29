from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QSlider,
    QButtonGroup, QRadioButton,
)
from drama_shot_master.ui.widgets.daw.selection import _CueRef


class BgmInspector(QWidget):
    promptEditRequested = Signal(object)    # _CueRef
    candidateChosen = Signal(object, int)   # _CueRef, new_idx
    regenerateRequested = Signal(object)    # _CueRef
    volumeChanged = Signal(object, float)   # _CueRef, volume

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ref = None
        self._session = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("BGM 段")
        lay.addWidget(self.title)
        self.time_label = QLabel("0:00 → 0:00")
        lay.addWidget(self.time_label)
        lay.addWidget(QLabel("风格 prompt:"))
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
        self.vol_slider.setValue(100)
        self.vol_slider.valueChanged.connect(self._on_volume)
        lay.addWidget(self.vol_slider)
        self.btn_regen = QPushButton("↻ 重生成")
        self.btn_regen.clicked.connect(
            lambda: self._ref and self.regenerateRequested.emit(self._ref))
        lay.addWidget(self.btn_regen)
        lay.addStretch(1)

    def set_cue_ref(self, ref, session):
        self._ref = ref
        self._session = session
        seg = session.segments[ref.seg_index] if session else None
        if seg is None:
            return
        self.title.setText(f"BGM 段 {ref.seg_index}")
        self.time_label.setText(f"{seg.t_start:.1f}s → {seg.t_end:.1f}s")
        prompt = getattr(seg, "music_prompt", "") or "(空)"
        self.prompt_label.setText(prompt[:80] + ("..." if len(prompt) > 80 else ""))
        self.vol_slider.setValue(int(getattr(seg, "volume", 1.0) * 100))
        for btn in list(self.cand_group.buttons()):
            self.cand_group.removeButton(btn)
            btn.deleteLater()
        for i, c in enumerate(seg.candidates):
            rb = QRadioButton(f"seed={c.seed}")
            self.cand_group.addButton(rb, i)
            self.cand_layout.addWidget(rb)
            if i == seg.chosen_candidate:
                rb.setChecked(True)
            rb.toggled.connect(
                lambda checked, idx=i:
                    checked and self._ref
                    and self.candidateChosen.emit(self._ref, idx))

    def _on_volume(self, val: int):
        if self._ref:
            self.volumeChanged.emit(self._ref, val / 100.0)
