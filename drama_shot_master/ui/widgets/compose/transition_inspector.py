"""切口转场编辑器：效果下拉(分类) + 时长 + 锁定。发 changed(index, effect, duration, locked)。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QProgressBar, QFrame,
)

from drama_shot_master.core.transition_render import XFADE_EFFECTS

_CAT_LABEL = {"universal": "万能适配", "directional": "方向推进", "creative": "创意", "cut": "硬切"}


def _score_category(score: float) -> str:
    if score >= 0.7:
        return "高匹配 → 万能类"
    if score >= 0.4:
        return "中匹配 → 方向类"
    return "低匹配 → 创意类"


class _ScoreRow(QWidget):
    """One labeled row: label + QProgressBar + numeric text."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFixedWidth(42)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setFixedHeight(10)
        self._bar.setTextVisible(False)
        self._bar.setEnabled(False)
        self._val = QLabel("—")
        self._val.setFixedWidth(36)
        self._val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        h.addWidget(lbl)
        h.addWidget(self._bar, 1)
        h.addWidget(self._val)

    def set_value(self, v: float):
        self._bar.setValue(int(round(v * 100)))
        self._val.setText(f"{v:.2f}")


class _CVCard(QFrame):
    """Read-only card showing CV score breakdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CVScoreCard")
        self.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        title = QLabel("CV 评分拆解")
        title.setObjectName("CVCardTitle")
        v.addWidget(title)

        self._row_hist = _ScoreRow("画面色")
        self._row_feat = _ScoreRow("结构")
        self._row_mot = _ScoreRow("运动")
        for row in (self._row_hist, self._row_feat, self._row_mot):
            v.addWidget(row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        v.addWidget(sep)

        self._score_lbl = QLabel("综合分：—")
        self._score_lbl.setObjectName("CVScoreTotal")
        v.addWidget(self._score_lbl)

        self._cat_lbl = QLabel("")
        self._cat_lbl.setObjectName("CVScoreCat")
        v.addWidget(self._cat_lbl)

    def populate(self, scores: dict):
        self._row_hist.set_value(scores.get("hist", 0.0))
        self._row_feat.set_value(scores.get("feature", 0.0))
        self._row_mot.set_value(scores.get("motion", 0.0))
        s = scores.get("score", 0.0)
        self._score_lbl.setText(f"综合分：{s:.2f}")
        self._cat_lbl.setText(_score_category(s))


class TransitionInspector(QWidget):
    changed = Signal(int, str, float, bool)
    resetToAuto = Signal(int)
    applyToAll = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._index = -1
        self._cv_scores: dict = {}
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

        # CV score breakdown card (read-only, built once)
        self._cv_card = _CVCard()
        self._cv_card.setVisible(False)
        lay.addWidget(self._cv_card)

        lay.addStretch(1)

    def set_connector(self, index, effect, duration, source, locked,
                      cv_scores: dict | None = None):
        self._index = index
        self._title.setText(f"转场（切口 #{index + 1}） · {('AI' if source == 'auto' else '手动')}")
        self._set_effect_silent(effect)
        self._dur.blockSignals(True); self._dur.setValue(float(duration)); self._dur.blockSignals(False)
        self._lock.blockSignals(True); self._lock.setChecked(bool(locked)); self._lock.blockSignals(False)

        self._cv_scores = cv_scores or {}
        if self._cv_scores.get("score") is not None:
            self._cv_card.populate(self._cv_scores)
            self._cv_card.setVisible(True)
        else:
            self._cv_card.setVisible(False)

    def has_scores(self) -> bool:
        return self._cv_scores.get("score") is not None

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
