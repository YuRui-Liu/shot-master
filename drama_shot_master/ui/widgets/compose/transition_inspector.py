"""切口转场编辑器：效果下拉(分类) + 时长 + 锁定。发 changed(index, effect, duration, locked)。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QPushButton,
)

from drama_shot_master.core.transition_render import XFADE_EFFECTS

_CAT_LABEL = {"universal": "万能适配", "directional": "方向推进", "creative": "创意", "cut": "硬切"}


class TransitionInspector(QWidget):
    changed = Signal(int, str, float, bool)
    resetToAuto = Signal(int)
    applyToAll = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._index = -1
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(12)
        self._title = QLabel("转场"); self._title.setObjectName("ComposeInspTitle")
        lay.addWidget(self._title)

        lay.addWidget(QLabel("转场效果"))
        self._combo = QComboBox()
        last_cat = None
        for e in XFADE_EFFECTS:
            if e["category"] != last_cat:
                self._combo.addItem(f"—— {_CAT_LABEL[e['category']]} ——")
                self._combo.model().item(self._combo.count() - 1).setEnabled(False)
                last_cat = e["category"]
            self._combo.addItem(e["label"], e["name"])
        self._combo.currentIndexChanged.connect(self._emit)
        lay.addWidget(self._combo)

        lay.addWidget(QLabel("时长 (0.3–2.0s)"))
        self._dur = QDoubleSpinBox(); self._dur.setRange(0.3, 2.0); self._dur.setSingleStep(0.1)
        self._dur.valueChanged.connect(self._emit)
        lay.addWidget(self._dur)

        self._lock = QCheckBox("锁定此切口（重跑不覆盖）")
        self._lock.stateChanged.connect(self._emit)
        lay.addWidget(self._lock)

        self._reset = QPushButton("↺ 重置为 AI")
        self._reset.clicked.connect(lambda: self.resetToAuto.emit(self._index))
        lay.addWidget(self._reset)
        self._all = QPushButton("应用到全部切口")
        self._all.clicked.connect(lambda: self.applyToAll.emit(self.effect(), self.duration()))
        lay.addWidget(self._all)
        lay.addStretch(1)

    def set_connector(self, index, effect, duration, source, locked):
        self._index = index
        self._title.setText(f"转场（切口 #{index + 1}） · {('AI' if source == 'auto' else '手动')}")
        self._set_effect_silent(effect)
        self._dur.blockSignals(True); self._dur.setValue(float(duration)); self._dur.blockSignals(False)
        self._lock.blockSignals(True); self._lock.setChecked(bool(locked)); self._lock.blockSignals(False)

    def effect(self) -> str:
        return self._combo.currentData() or "dissolve"

    def duration(self) -> float:
        return float(self._dur.value())

    def set_effect(self, name): self._set_effect_silent(name); self._emit()
    def set_duration(self, v): self._dur.setValue(float(v))
    def set_locked(self, on): self._lock.setChecked(bool(on))

    def _set_effect_silent(self, name):
        self._combo.blockSignals(True)
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == name:
                self._combo.setCurrentIndex(i); break
        self._combo.blockSignals(False)

    def _emit(self, *_):
        if self._index < 0:
            return
        self.changed.emit(self._index, self.effect(), self.duration(), self._lock.isChecked())
