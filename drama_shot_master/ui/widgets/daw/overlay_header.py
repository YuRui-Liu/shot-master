"""动态叠加区头部控件列：折叠头 + 每 lane 一行 M/音量。

固定宽 130（与 TrackHeaderColumn 对齐）；放在 header 列容器中
TrackHeaderColumn 下方。行高/顺序与 DawTrackView 叠加区严格对齐
（复用 overlay_layout 的 overlay_rows/lanes_of 分组）。

每 lane 头一个 mute 开关 + 音量滑条，作用于该 lane 内所有 segment。
M/vol 初值按 lane 内 segment 聚合：任一 enabled=False → 该行 M checked；
音量取 lane 内首段 volume*100。
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
)

from .overlay_layout import overlay_rows, _OV_LANE_H, _OV_HEAD_H
from .track_header_column import _MUTE_QSS


class OverlayHeaderSection(QWidget):
    collapseToggled = Signal()
    laneMuteToggled = Signal(str, int, bool)     # kind, lane, muted
    laneVolumeChanged = Signal(str, int, float)  # kind, lane, volume

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(130)
        self._lane_rows = []   # [{"widget","kind","lane","mute","vol","label"}]
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(2, 0, 2, 0)
        self._root.setSpacing(0)
        # 折叠头按钮行
        self._head_btn = QPushButton("动态叠加区")
        self._head_btn.setFixedHeight(_OV_HEAD_H)
        self._head_btn.setStyleSheet(
            "QPushButton{text-align:left;border:none;font-size:10px;"
            "color:#a6adc8;font-weight:700;}")
        self._head_btn.clicked.connect(lambda: self.collapseToggled.emit())
        self._root.addWidget(self._head_btn)
        self._root.addStretch(1)
        self.hide()

    def set_overlay(self, segments, *, collapsed) -> None:
        """清空重建：折叠头行（点击 emit collapseToggled）+ 展开时每 lane 一行
        （标签 'bgm·0' + M 按钮 + 音量 slider）。空 segments → 整体隐藏。"""
        # 清空旧 lane 行
        for row in self._lane_rows:
            row["widget"].setParent(None)
            row["widget"].deleteLater()
        self._lane_rows = []

        if not segments:
            self.hide()
            return

        rows, _ = overlay_rows(segments, base_y=0, collapsed=False)
        n = len(rows)
        arrow = "▶" if collapsed else "▼"   # ▶ / ▼
        self._head_btn.setText(f"{arrow} 动态叠加区({n})")

        # stretch 在末尾（index = count-1），lane 行插在它之前
        for r in rows:
            row_w = self._build_lane_row(r)
            row_w.setHidden(collapsed)
            self._root.insertWidget(self._root.count() - 1, row_w)

        self.show()

    def _build_lane_row(self, r) -> QWidget:
        row_w = QWidget()
        row_w.setFixedHeight(_OV_LANE_H)
        hl = QHBoxLayout(row_w)
        hl.setContentsMargins(2, 1, 2, 1)
        hl.setSpacing(3)

        label = QLabel(f"{r.kind}·{r.lane}")   # bgm·0
        label.setStyleSheet("font-size:10px;color:#cdd6f4;")
        label.setFixedWidth(40)
        hl.addWidget(label)

        mute = QPushButton("M")
        mute.setCheckable(True)
        mute.setFixedWidth(20)
        mute.setStyleSheet(_MUTE_QSS)
        # 聚合初值：任一 enabled=False → 该行 mute
        muted = any(not s.enabled for s in r.segments)
        mute.setChecked(muted)
        mute.clicked.connect(
            lambda checked, k=r.kind, l=r.lane:
            self.laneMuteToggled.emit(k, l, checked))
        hl.addWidget(mute)

        vol = QSlider(Qt.Horizontal)
        vol.setRange(0, 150)
        first_vol = r.segments[0].volume if r.segments else 1.0
        vol.setValue(int(round(first_vol * 100)))
        vol.valueChanged.connect(
            lambda v, k=r.kind, l=r.lane:
            self.laneVolumeChanged.emit(k, l, v / 100.0))
        hl.addWidget(vol, 1)

        self._lane_rows.append({
            "widget": row_w, "kind": r.kind, "lane": r.lane,
            "mute": mute, "vol": vol, "label": label,
        })
        return row_w
