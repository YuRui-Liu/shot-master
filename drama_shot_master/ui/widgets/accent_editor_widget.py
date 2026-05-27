"""③卡点：时间轴可视化(刻度+段落带+爆点标记) + 自动检测 + 增删微调。

时间轴自绘(对齐 accent-editor.html mockup)；自动检测用光流(detect_accents)
对 session.source_mp4 跑，后台线程，不卡 UI。列表/数值微调保留作精调。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QDoubleSpinBox, QMessageBox, QCheckBox, QSlider,
)

from sound_track_agent.session import AccentPoint
from drama_shot_master.ui.worker import FunctionWorker

_SEG_COLORS = ["#3a4a5f", "#4a3a3a", "#3a4a3a", "#4a443a", "#3a3a4a"]


class _AccentTimeline(QWidget):
    """自绘时间轴：刻度尺 + 段落带 + 爆点菱形标记。点击选中最近爆点。"""

    selectionChanged = Signal(int)        # sorted_index（-1=未选）

    def __init__(self, session, parent=None, *, big_threshold: float = 0.7):
        super().__init__(parent)
        self._session = session
        self._selected = -1
        self._big_threshold = big_threshold
        self.setMinimumHeight(96)

    def set_selected(self, sorted_index: int):
        self._selected = sorted_index
        self.update()

    def _sorted_points(self):
        return sorted(self._session.accent_points, key=lambda a: a.t)

    def _total(self) -> float:
        ts = [s.t_end for s in self._session.segments]
        ts += [a.t for a in self._session.accent_points]
        t = max(ts, default=0.0)
        return t if t > 0 else 1.0

    def _x(self, t: float, w: int) -> float:
        return 8 + (w - 16) * (t / self._total())

    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#1a1b1e"))
        total = self._total()

        # 刻度尺（约 8 格）
        p.setPen(QPen(QColor("#7a8597"), 1))
        step = max(1.0, round(total / 8))
        t = 0.0
        while t <= total + 1e-6:
            x = self._x(t, w)
            p.drawLine(int(x), 4, int(x), 12)
            p.drawText(int(x) + 2, 14, f"{t:.0f}s")
            t += step

        # 段落带
        band_y, band_h = 22, 26
        for i, s in enumerate(self._session.segments):
            x0 = self._x(s.t_start, w); x1 = self._x(s.t_end, w)
            p.fillRect(QRectF(x0, band_y, max(1.0, x1 - x0), band_h),
                       QColor(_SEG_COLORS[i % len(_SEG_COLORS)]))
            p.setPen(QPen(QColor("#4a9eff"), 1))
            p.drawLine(int(x1), band_y, int(x1), band_y + band_h)
            p.setPen(QColor("#cdd"))
            p.drawText(int(x0) + 3, band_y + 17, f"段{s.index}")

        # 爆点菱形
        my = band_y + band_h + 20
        for idx, a in enumerate(self._sorted_points()):
            x = self._x(a.t, w)
            sel = (idx == self._selected)
            color = QColor("#ff8c42") if sel else QColor("#ff5c5c")
            rad = 9 if a.intensity >= self._big_threshold else 6
            poly = QPolygonF([QPointF(x, my - rad - 1), QPointF(x + rad, my),
                              QPointF(x, my + rad + 1), QPointF(x - rad, my)])
            p.setBrush(color); p.setPen(QPen(color, 1))
            p.drawPolygon(poly)
            p.setPen(QColor("#9aa0a6"))
            p.drawText(int(x) - 12, my + 22, f"{a.t:.1f}s")
        p.end()

    def mousePressEvent(self, ev):
        pts = self._sorted_points()
        if not pts:
            return
        w = self.width()
        xclick = ev.position().x() if hasattr(ev, "position") else ev.x()
        # 选最近的爆点（容差 14px）
        best, bestd = -1, 1e9
        for idx, a in enumerate(pts):
            d = abs(self._x(a.t, w) - xclick)
            if d < bestd:
                best, bestd = idx, d
        if bestd <= 14:
            self._selected = best
            self.update()
            self.selectionChanged.emit(best)


class AccentEditorWidget(QWidget):
    """爆点编辑：时间轴可视化 + 自动检测 + 增删微调，写回 session.accent_points。"""

    accentsChanged = Signal()

    def __init__(self, session, parent=None, *, big_threshold: float = 0.7,
                 work_dir=None, crossfade: float = 0.5, snap_window: float = 0.6):
        super().__init__(parent)
        self._session = session
        self._worker = None
        self._big_threshold = big_threshold
        self._work_dir = work_dir
        self._crossfade = crossfade
        self._snap_window = snap_window
        self._player = None
        self._audio = None
        self._preview_worker = None
        self._build_ui()
        self._refresh()

    def accent_count(self) -> int:
        return len(self._session.accent_points)

    def _sorted_points(self) -> list:
        return sorted(self._session.accent_points, key=lambda a: a.t)

    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("爆点（出片时音乐重音吸附到这些时间点）："))
        top.addStretch(1)
        self.chk_mix = QCheckBox("卡点混音")
        self.chk_mix.setChecked(bool(getattr(self._session, "accent_mix_enabled", True)))
        self.chk_mix.toggled.connect(self._on_mix_toggled)
        top.addWidget(self.chk_mix)
        top.addWidget(QLabel("泵感"))
        self.pump_slider = QSlider(Qt.Horizontal)
        self.pump_slider.setRange(0, 100)
        self.pump_slider.setFixedWidth(120)
        self.pump_slider.setValue(int(round(float(getattr(self._session, "pump_strength", 0.6)) * 100)))
        self.pump_slider.valueChanged.connect(self._on_pump_changed)
        top.addWidget(self.pump_slider)
        self.btn_detect = QPushButton("🎬 自动检测")
        self.btn_detect.clicked.connect(self._on_auto_detect)
        top.addWidget(self.btn_detect)
        self.btn_preview_mix = QPushButton("🎧 试听卡点效果")
        self.btn_preview_mix.setEnabled(bool(self._work_dir))
        self.btn_preview_mix.clicked.connect(self._on_preview_mix)
        top.addWidget(self.btn_preview_mix)
        root.addLayout(top)

        self.timeline = _AccentTimeline(self._session,
                                        big_threshold=self._big_threshold)
        self.timeline.selectionChanged.connect(self._on_timeline_select)
        root.addWidget(self.timeline)

        self.listw = QListWidget()
        self.listw.currentRowChanged.connect(self._on_list_row)
        root.addWidget(self.listw, 1)

        row = QHBoxLayout()
        self.new_spin = QDoubleSpinBox()
        self.new_spin.setRange(0.0, 36000.0); self.new_spin.setDecimals(2)
        self.new_spin.setSuffix(" s")
        btn_add = QPushButton("+ 新增")
        btn_add.clicked.connect(lambda: self.add_accent(self.new_spin.value()))
        btn_del = QPushButton("🗑 删除选中")
        btn_del.clicked.connect(self._delete_selected)
        btn_minus = QPushButton("−0.1s")
        btn_minus.clicked.connect(lambda: self._nudge_selected(-0.1))
        btn_plus = QPushButton("+0.1s")
        btn_plus.clicked.connect(lambda: self._nudge_selected(0.1))
        for wdg in (self.new_spin, btn_add, btn_del, btn_minus, btn_plus):
            row.addWidget(wdg)
        row.addStretch(1)
        root.addLayout(row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#9aa0a6;")
        root.addWidget(self.status_label)

    def _refresh(self):
        self.listw.blockSignals(True)
        self.listw.clear()
        for a in self._sorted_points():
            self.listw.addItem(f"{a.t:.2f}s  (强度 {a.intensity:.2f})")
        self.listw.blockSignals(False)
        self.timeline.update()

    # ---------- 选中同步 ----------
    def _on_timeline_select(self, idx: int):
        self.listw.setCurrentRow(idx)

    def _on_list_row(self, idx: int):
        self.timeline.set_selected(idx)

    # ---------- 自动检测 ----------
    def _on_auto_detect(self):
        if self._worker is not None and self._worker.isRunning():
            return
        mp4 = self._session.source_mp4
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无法检测", f"成片不存在：{mp4}")
            return
        self.btn_detect.setEnabled(False)
        self.status_label.setText("光流检测中…（约 10-30s）")

        def task():
            from sound_track_agent.accent_detector import detect_accents
            return detect_accents(mp4)

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._apply_detected)
        self._worker.failed.connect(self._on_detect_failed)
        self._worker.start()

    def _apply_detected(self, points: list):
        self._session.accent_points = list(points)
        self.btn_detect.setEnabled(True)
        self.status_label.setText(f"自动检测到 {len(points)} 个爆点")
        self._refresh()
        self.accentsChanged.emit()

    def _on_detect_failed(self, err: str):
        self.btn_detect.setEnabled(True)
        self.status_label.setText("检测失败")
        QMessageBox.critical(self, "检测失败", err)

    # ---------- 卡点试听预览 ----------
    def _ensure_player(self):
        if self._player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
        return self._player

    def _play_path(self, path: str):
        from PySide6.QtCore import QUrl
        player = self._ensure_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(path))
        player.play()

    def _on_preview_mix(self):
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return
        if not self._work_dir:
            QMessageBox.information(self, "试听卡点", "无工作目录,无法试听"); return
        if not self._session.segments:
            QMessageBox.information(self, "试听卡点", "还没有段落/候选,先在①生成"); return
        self.btn_preview_mix.setEnabled(False)
        self.status_label.setText("正在合成卡点试听…")
        sess = self._session
        work = str(self._work_dir); cf = self._crossfade
        bt = self._big_threshold; sw = self._snap_window

        def task():
            from sound_track_agent import facade
            return facade.build_accent_preview(
                sess, work, crossfade=cf, big_threshold=bt, snap_window=sw)

        self._preview_worker = FunctionWorker(task)
        self._preview_worker.finished_with_result.connect(self._on_preview_done)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.start()

    def _on_preview_done(self, path: str):
        self.btn_preview_mix.setEnabled(True)
        self.status_label.setText("▶ 卡点试听播放中")
        self._play_path(path)

    def _on_preview_failed(self, err: str):
        self.btn_preview_mix.setEnabled(True)
        self.status_label.setText("试听失败")
        QMessageBox.critical(self, "试听失败", err)

    # ---------- 卡点混音 / 泵感 ----------
    def _on_mix_toggled(self, checked: bool):
        self._session.accent_mix_enabled = bool(checked)
        self.accentsChanged.emit()

    def _on_pump_changed(self, val: int):
        self._session.pump_strength = val / 100.0
        self.accentsChanged.emit()

    # ---------- 增删微调 ----------
    def add_accent(self, t: float):
        self._session.accent_points.append(
            AccentPoint(t=float(t), intensity=1.0, confirmed=True))
        self._refresh()
        self.accentsChanged.emit()

    def delete_accent(self, sorted_index: int):
        pts = self._sorted_points()
        if not (0 <= sorted_index < len(pts)):
            return
        self._session.accent_points.remove(pts[sorted_index])
        self._refresh()
        self.accentsChanged.emit()

    def nudge_accent(self, sorted_index: int, delta: float):
        pts = self._sorted_points()
        if not (0 <= sorted_index < len(pts)):
            return
        target = pts[sorted_index]
        target.t = max(0.0, target.t + delta)
        target.confirmed = True
        self._refresh()
        self.accentsChanged.emit()

    def _delete_selected(self):
        self.delete_accent(self.listw.currentRow())

    def _nudge_selected(self, delta: float):
        self.nudge_accent(self.listw.currentRow(), delta)
