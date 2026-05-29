# Phase 4b 顶部预览（VideoPreview + OverviewTimeline 4 轨）设计

**日期**：2026-05-29
**作者**：sound_track_agent 维护者
**状态**：设计稿，待用户确认

> 路线图位置：Phase 4a 已完成（后端 + P1 卡片 UI）→ **本 4b 加 顶部预览**（视频窗 + 4 轨 mini-timeline）→ Phase 4c 主区改 DAW 多轨编辑器。
> 上游 spec：`docs/superpowers/specs/2026-05-29-soundtrack-phase4-sfx-daw-roadmap-design.md` §0.3 4b 验收 + 用户 brainstorm 升级（加 QVideoWidget 联动）

---

## §1 架构 + 组件

### §1.1 UI 布局（L1 上下）

```
SoundtrackEditor (浮出窗)
├── 顶部预览区 (~320px 高，QVBoxLayout)
│   ├── VideoPreviewWidget (~180px 高，16:9)
│   │   ├── QVideoWidget (mediaplayer 视频呈现)
│   │   └── 工具栏: [▶/⏸] 00:12.4/00:30  音量[━●━]
│   └── OverviewTimeline (~140px 高，自绘 painted widget)
│       ├── 时间刻度行 (~14px)
│       ├── 视频轨 (~18px, 灰色块 + shot 黑切线)
│       ├── BGM 轨  (~22px, 蓝色块 + 风格短文字)
│       ├── SFX 轨  (~22px, 橙色块 + prompt 短文字)
│       ├── 对白轨 (~22px, 绿色块 + 角色名)
│       └── 红色播放头竖线（可拖，30Hz scrubbing）
└── 现有 4 tab (配置 / BGM / 卡点 / SFX) 不变
```

### §1.2 新增 / 改动文件

```
drama_shot_master/ui/widgets/
├── video_preview_widget.py        # NEW: QVideoWidget + 工具栏 + 节流 seek
├── overview_timeline.py            # NEW: 自绘 4 轨 widget + 播放头 + scrubbing
├── overview_timeline_model.py      # NEW: derive_cues 纯函数（数据派生）
└── soundtrack_editor.py            # CHANGED: _build_ui 顶部插预览区 + 5 个新方法
```

零后端改动（4b 后端零新增，复用 4a + Sprint 0 数据源）。

---

## §2 数据流

### §2.1 7 个 lifecycle 场景

| # | 触发 | 动作 |
|---|------|------|
| 1 | `SoundtrackEditor.__init__` 完成 | `VideoPreviewWidget.set_source(session.output or task.mp4)` → `_rebuild_overview()` |
| 2 | BGM `_on_done(sess)` 回调 | `_rebuild_overview()` + 若 sess.output 变化 → `video_preview.set_source(sess.output)` |
| 3 | SFX `_on_sfx_generate_done(sess)` 回调 | `_rebuild_overview()` |
| 4 | `tabs.currentChanged` signal | `_rebuild_overview()`（轻量重画，<10ms） |
| 5 | 用户拖 timeline 播放头（mouseMoveEvent） | `OverviewTimeline.playheadDragged(t)` → 节流 30Hz → `video_preview.seek(t)` |
| 6 | `QMediaPlayer.positionChanged(ms)` | `video_preview.positionChanged(t)` → `overview.set_playhead(t)` |
| 7 | 用户点 timeline 上 BGM/SFX cue | `OverviewTimeline.cueClicked(track, seg_index, t_start)` → 切对应 tab + scroll 到卡片 + `video_preview.seek(t_start)` |

### §2.2 试听互斥

`SegmentReviewWidget._on_candidate` / `SfxReviewWidget._on_candidate` 开始播音频候选时，发新 signal `previewStarted` → `SoundtrackEditor` 调 `video_preview.pause()`。视频暂停状态保留，用户可手动恢复。**不实现自动 resume**（避免试听完候选后视频突然续播打断思考）。

### §2.3 视频源优先级

```python
def _resolve_video_source(self) -> str | None:
    """有 BGM mix 完成的 session.output → 用成片；否则原 task mp4。"""
    if self._session is not None:
        out = getattr(self._session, "output", None)
        if out and Path(out).exists():
            return out
    mp4 = (self._task.get("mp4") or "").strip()
    return mp4 if mp4 and Path(mp4).exists() else None
```

---

## §3 模块设计

### §3.1 `video_preview_widget.py`

```python
"""视频预览 widget：QVideoWidget + 工具栏 + 节流 seek。

封装 QMediaPlayer 让上层只看到 set_source/seek/play/pause/duration/is_playing 6 个方法
+ 1 个 positionChanged(float) signal。
"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Signal, QUrl, QTimer, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
)


class VideoPreviewWidget(QWidget):
    positionChanged = Signal(float)   # 秒

    _SEEK_THROTTLE_MS = 33            # ~30Hz

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = None           # 懒建（避免 headless 测试 segfault）
        self._audio = None
        self._video_widget = None
        self._duration_sec = 0.0
        self._pending_seek_ms: int | None = None
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(self._SEEK_THROTTLE_MS)
        self._seek_timer.timeout.connect(self._flush_seek)
        self._build_ui()

    def _build_ui(self):
        from PySide6.QtMultimediaWidgets import QVideoWidget
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._video_widget = QVideoWidget(self)
        self._video_widget.setMinimumHeight(180)
        self._video_widget.setStyleSheet("background:#000;")
        root.addWidget(self._video_widget, 1)
        bar = QHBoxLayout()
        self.btn_play = QPushButton("▶")
        self.btn_play.setMaximumWidth(40)
        self.btn_play.clicked.connect(self._toggle_play)
        self.time_label = QLabel("0:00 / 0:00")
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(80)
        self.vol_slider.setMaximumWidth(120)
        self.vol_slider.valueChanged.connect(self._on_volume)
        bar.addWidget(self.btn_play)
        bar.addWidget(self.time_label)
        bar.addStretch(1)
        bar.addWidget(QLabel("🔊"))
        bar.addWidget(self.vol_slider)
        root.addLayout(bar)

    def _ensure_player(self):
        if self._player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self._video_widget)
            self._player.positionChanged.connect(self._on_position_changed)
            self._player.durationChanged.connect(self._on_duration_changed)
            self._player.playbackStateChanged.connect(self._on_state_changed)
            self._audio.setVolume(self.vol_slider.value() / 100.0)
        return self._player

    def set_source(self, video_path: str | None) -> None:
        """加载 mp4；None 或不存在 → 不加载，黑屏。"""
        if not video_path or not Path(video_path).exists():
            if self._player is not None:
                self._player.stop()
            return
        player = self._ensure_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(str(video_path)))

    def seek(self, t_sec: float) -> None:
        """节流 seek：~30Hz；timer 内 flush 实际 setPosition。"""
        if self._player is None:
            return
        self._pending_seek_ms = max(0, int(round(t_sec * 1000)))
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _flush_seek(self):
        if self._player is None or self._pending_seek_ms is None:
            return
        self._player.setPosition(self._pending_seek_ms)
        self._pending_seek_ms = None

    def play(self) -> None:
        if self._player is not None:
            self._player.play()

    def pause(self) -> None:
        if self._player is not None:
            self._player.pause()

    def is_playing(self) -> bool:
        if self._player is None:
            return False
        from PySide6.QtMultimedia import QMediaPlayer
        return self._player.playbackState() == QMediaPlayer.PlayingState

    def duration(self) -> float:
        return self._duration_sec

    def _toggle_play(self):
        if self._player is None:
            return
        if self.is_playing():
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, ms: int):
        self.positionChanged.emit(ms / 1000.0)
        self._update_time_label(ms / 1000.0)

    def _on_duration_changed(self, ms: int):
        self._duration_sec = ms / 1000.0
        self._update_time_label(0.0)

    def _on_state_changed(self, _state):
        from PySide6.QtMultimedia import QMediaPlayer
        playing = (self._player is not None
                   and self._player.playbackState() == QMediaPlayer.PlayingState)
        self.btn_play.setText("⏸" if playing else "▶")

    def _on_volume(self, val: int):
        if self._audio is not None:
            self._audio.setVolume(val / 100.0)

    def _update_time_label(self, t_sec: float):
        def _fmt(s: float) -> str:
            s = max(0, int(s))
            return f"{s // 60}:{s % 60:02d}"
        self.time_label.setText(f"{_fmt(t_sec)} / {_fmt(self._duration_sec)}")
```

### §3.2 `overview_timeline_model.py`（纯函数派生）

```python
"""数据派生：4 个数据源 → 统一 _Cue 列表。无 IO，可单测。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class _Cue:
    track: Literal["video", "bgm", "sfx", "dialogue"]
    t_start: float
    t_end: float
    label: str
    seg_index: int          # cue 在原 stem 列表里的下标（供 click handler 跳转用）


def _label_from_prompt(text: str, max_chars: int = 8) -> str:
    """取 prompt 前 N 字作为色块内文字。"""
    t = (text or "").strip()
    return t[:max_chars] if t else ""


def derive_video_cues(shot_boundaries: list[float],
                      total_duration: float) -> list[_Cue]:
    """shot_detector.detect_shots 输出 → 视频轨灰色块。"""
    if not shot_boundaries or total_duration <= 0:
        return [_Cue("video", 0.0, total_duration, "", 0)] if total_duration > 0 else []
    cues = []
    edges = [0.0] + list(shot_boundaries) + [total_duration]
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        if b > a:
            cues.append(_Cue("video", float(a), float(b), "", i))
    return cues


def derive_bgm_cues(bgm_session) -> list[_Cue]:
    """ScoringSession.segments → BGM 蓝色块。chosen_candidate=None 也画（淡色），
    但 label 不显示，让用户知道这段未选定。"""
    if bgm_session is None:
        return []
    out = []
    for i, seg in enumerate(getattr(bgm_session, "segments", []) or []):
        prompt = getattr(seg, "music_prompt", "") or ""
        label = _label_from_prompt(prompt, 8) if seg.chosen_candidate is not None else "(未选)"
        out.append(_Cue("bgm", float(seg.t_start), float(seg.t_end),
                        label, i))
    return out


def derive_sfx_cues(sfx_session) -> list[_Cue]:
    """SFXSession.shots → SFX 橙色块。仅 enabled & status=generated 的 shot 才出。"""
    if sfx_session is None:
        return []
    out = []
    for i, shot in enumerate(getattr(sfx_session, "shots", []) or []):
        if not getattr(shot, "enabled", True):
            continue
        if getattr(shot, "status", "") != "generated":
            continue
        label = _label_from_prompt(getattr(shot, "prompt_short", ""), 6)
        out.append(_Cue("sfx", float(shot.t_start),
                        float(shot.t_start + shot.duration),
                        label, i))
    return out


def derive_dialogue_cues(timeline_dict: Optional[dict],
                          frame_rate: float = 24.0) -> list[_Cue]:
    """cfg.video_tasks[*].timeline.audios → 对白绿色块。"""
    if not timeline_dict:
        return []
    audios = timeline_dict.get("audios") or []
    fps = float(timeline_dict.get("frame_rate", frame_rate)) or frame_rate
    out = []
    for i, a in enumerate(audios):
        try:
            start_f = float(a.get("start_frame", 0))
            length_f = float(a.get("length_frames", 0))
        except (TypeError, ValueError):
            continue
        if length_f <= 0:
            continue
        t_start = start_f / fps
        t_end = t_start + length_f / fps
        path = a.get("audio_path") or ""
        label = path.rsplit("/", 1)[-1].rsplit(".", 1)[0][:6] if path else f"对白{i}"
        out.append(_Cue("dialogue", t_start, t_end, label, i))
    return out


def derive_total_duration(*, bgm_session, sfx_session,
                          dialogue_audios: Optional[dict],
                          video_duration: float = 0.0) -> float:
    """取 4 源最大 t_end。video_duration 由 video_preview.duration() 提供（最准）。"""
    candidates = [float(video_duration)]
    if bgm_session is not None:
        for s in getattr(bgm_session, "segments", []) or []:
            candidates.append(float(s.t_end))
    if sfx_session is not None:
        for s in getattr(sfx_session, "shots", []) or []:
            candidates.append(float(s.t_start + s.duration))
    if dialogue_audios:
        fps = float(dialogue_audios.get("frame_rate", 24.0)) or 24.0
        for a in dialogue_audios.get("audios") or []:
            try:
                candidates.append((float(a["start_frame"]) + float(a["length_frames"])) / fps)
            except (TypeError, ValueError, KeyError):
                continue
    return max(candidates) if candidates else 30.0
```

### §3.3 `overview_timeline.py`（自绘 painted widget）

```python
"""4 轨自绘 mini-timeline + 播放头 + scrubbing。

不使用 QGraphicsView（杀鸡用牛刀），自绘 paintEvent。
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Signal, Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue


# 4 轨视觉常量
_TRACK_HEIGHTS = {"video": 18, "bgm": 22, "sfx": 22, "dialogue": 22}
_TRACK_ORDER = ["video", "bgm", "sfx", "dialogue"]
_TRACK_COLORS = {
    "video":    QColor("#555555"),
    "bgm":      QColor("#4a7eb8"),
    "sfx":      QColor("#c2884c"),
    "dialogue": QColor("#5a9f5a"),
}
_LABEL_WIDTH = 60
_AXIS_HEIGHT = 14
_ROW_GAP = 2
_PLAYHEAD_COLOR = QColor("#e63946")
_BG_TRACK_COLOR = QColor("#2a2a2a")
_BG_FRAME_COLOR = QColor("#1e1e1e")
_AXIS_COLOR = QColor("#444444")
_TEXT_COLOR = QColor("#ffffff")
_LABEL_COLOR = QColor("#888888")


class OverviewTimeline(QWidget):
    playheadDragged = Signal(float)        # 用户拖到的时间秒（30Hz 节流）
    cueClicked = Signal(str, int, float)   # (track, seg_index, t_start)

    _DRAG_THROTTLE_MS = 33

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cues: list[_Cue] = []
        self._duration = 30.0
        self._playhead = 0.0
        self._dragging = False
        self._pending_drag_t: Optional[float] = None
        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.setInterval(self._DRAG_THROTTLE_MS)
        self._drag_timer.timeout.connect(self._flush_drag)
        # 总高 = axis + 4 * (track height + gap)
        total = _AXIS_HEIGHT + sum(_TRACK_HEIGHTS.values()) + 3 * _ROW_GAP
        self.setMinimumHeight(total)
        self.setMouseTracking(True)

    def set_cues(self, cues: list[_Cue]) -> None:
        self._cues = list(cues)
        self.update()

    def set_duration(self, total_sec: float) -> None:
        self._duration = max(0.001, float(total_sec))
        self.update()

    def set_playhead(self, t_sec: float) -> None:
        """外部驱动（QMediaPlayer.positionChanged），不 emit playheadDragged。"""
        self._playhead = max(0.0, min(self._duration, float(t_sec)))
        if not self._dragging:
            self.update()

    # ---------- 坐标变换 ----------
    def _track_y(self, track: str) -> tuple[int, int]:
        y = _AXIS_HEIGHT
        for t in _TRACK_ORDER:
            h = _TRACK_HEIGHTS[t]
            if t == track:
                return y, h
            y += h + _ROW_GAP
        return -1, 0

    def _t_to_x(self, t: float) -> int:
        track_w = max(1, self.width() - _LABEL_WIDTH)
        return _LABEL_WIDTH + int(track_w * (t / self._duration))

    def _x_to_t(self, x: int) -> float:
        track_w = max(1, self.width() - _LABEL_WIDTH)
        return max(0.0, min(self._duration,
                             (x - _LABEL_WIDTH) / track_w * self._duration))

    def _cue_at(self, x: int, y: int) -> Optional[_Cue]:
        for c in self._cues:
            ty, th = self._track_y(c.track)
            if y < ty or y >= ty + th:
                continue
            cx_a = self._t_to_x(c.t_start)
            cx_b = self._t_to_x(c.t_end)
            if cx_a <= x <= cx_b:
                return c
        return None

    # ---------- paint ----------
    def paintEvent(self, _event):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), _BG_FRAME_COLOR)
            # 轴
            self._paint_axis(p)
            # 4 轨背景
            for track in _TRACK_ORDER:
                ty, th = self._track_y(track)
                p.fillRect(_LABEL_WIDTH, ty, self.width() - _LABEL_WIDTH,
                           th, _BG_TRACK_COLOR)
                self._paint_label(p, track, ty, th)
            # 所有 cue
            font = QFont(); font.setPointSize(8); p.setFont(font)
            fm = QFontMetrics(font)
            for c in self._cues:
                ty, th = self._track_y(c.track)
                x_a = self._t_to_x(c.t_start)
                x_b = self._t_to_x(c.t_end)
                color = _TRACK_COLORS[c.track]
                rect = QRect(x_a, ty, max(2, x_b - x_a), th)
                p.fillRect(rect, color)
                # 视频轨：黑切线
                if c.track == "video":
                    p.setPen(QColor("#000000"))
                    p.drawLine(x_b, ty, x_b, ty + th)
                # cue 文字（超宽截断）
                if c.label and rect.width() >= 30:
                    p.setPen(_TEXT_COLOR)
                    elide_w = rect.width() - 6
                    text = fm.elidedText(c.label, Qt.ElideRight, elide_w)
                    p.drawText(rect.adjusted(3, 0, -3, 0),
                               Qt.AlignVCenter | Qt.AlignLeft, text)
            # 播放头
            px = self._t_to_x(self._playhead)
            p.setPen(_PLAYHEAD_COLOR)
            p.drawLine(px, 0, px, self.height())
        finally:
            p.end()

    def _paint_axis(self, p: QPainter):
        p.fillRect(0, 0, self.width(), _AXIS_HEIGHT, _BG_FRAME_COLOR)
        p.setPen(_AXIS_COLOR)
        p.drawLine(_LABEL_WIDTH, _AXIS_HEIGHT - 1,
                   self.width(), _AXIS_HEIGHT - 1)
        # 5 个等分时间标签
        font = QFont(); font.setPointSize(7); p.setFont(font)
        p.setPen(_LABEL_COLOR)
        for i in range(5):
            t = self._duration * i / 4
            x = self._t_to_x(t)
            mins = int(t // 60); secs = int(t % 60)
            p.drawText(x + 2, _AXIS_HEIGHT - 3, f"{mins}:{secs:02d}")
            if i > 0 and i < 4:
                p.setPen(_AXIS_COLOR)
                p.drawLine(x, 0, x, _AXIS_HEIGHT - 1)
                p.setPen(_LABEL_COLOR)

    def _paint_label(self, p: QPainter, track: str, ty: int, th: int):
        p.setPen(_LABEL_COLOR)
        font = QFont(); font.setPointSize(8); p.setFont(font)
        text = {"video": "视频", "bgm": "BGM",
                "sfx": "SFX", "dialogue": "对白"}[track]
        p.drawText(QRect(0, ty, _LABEL_WIDTH - 4, th),
                   Qt.AlignVCenter | Qt.AlignRight, text)

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        x, y = event.pos().x(), event.pos().y()
        # 优先 cue 点击
        cue = self._cue_at(x, y)
        if cue is not None and cue.track != "video":
            self.cueClicked.emit(cue.track, cue.seg_index, cue.t_start)
            return
        # 否则进入拖动模式（视频轨点击也算 seek）
        if x >= _LABEL_WIDTH:
            self._dragging = True
            self._emit_drag(self._x_to_t(x))

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        x = event.pos().x()
        if x >= _LABEL_WIDTH:
            self._emit_drag(self._x_to_t(x))

    def mouseReleaseEvent(self, _event):
        if self._dragging:
            self._dragging = False
            # 释放时立即 flush（不等节流，确保最终位置准确）
            self._flush_drag()

    def _emit_drag(self, t: float):
        self._pending_drag_t = t
        self._playhead = t
        self.update()
        if not self._drag_timer.isActive():
            self._drag_timer.start()

    def _flush_drag(self):
        if self._pending_drag_t is None:
            return
        self.playheadDragged.emit(self._pending_drag_t)
        self._pending_drag_t = None
```

### §3.4 `SoundtrackEditor` 改动（最小）

`__init__` 加：
```python
        self._overview_timeline = None
        self._video_preview = None
```

`_build_ui` 在 tabs 创建**之前**插：
```python
        from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget
        from drama_shot_master.ui.widgets.overview_timeline import OverviewTimeline
        self._video_preview = VideoPreviewWidget()
        self._overview_timeline = OverviewTimeline()
        self._video_preview.positionChanged.connect(
            self._on_video_position_changed)
        self._overview_timeline.playheadDragged.connect(
            self._on_overview_playhead_dragged)
        self._overview_timeline.cueClicked.connect(
            self._on_overview_cue_clicked)
        root.addWidget(self._video_preview)
        root.addWidget(self._overview_timeline)
```

`__init__` 末尾 + 加 tabs.currentChanged 接线：
```python
        self.tabs.currentChanged.connect(lambda _i: self._rebuild_overview())
        self._rebuild_overview()
        src = self._resolve_video_source()
        if src:
            self._video_preview.set_source(src)
```

加 5 个新方法：
```python
    def _resolve_video_source(self) -> str | None: ...  # §2.3 已给

    def _rebuild_overview(self) -> None:
        from drama_shot_master.ui.widgets.overview_timeline_model import (
            derive_video_cues, derive_bgm_cues, derive_sfx_cues,
            derive_dialogue_cues, derive_total_duration,
        )
        # 4 个数据源派生 cue
        shot_bounds = []
        if self._session is not None:
            shot_bounds = [s.t_end for s in self._session.segments]
        bgm_cues = derive_bgm_cues(self._session)
        sfx_cues = derive_sfx_cues(self._sfx_session)
        # cfg.video_tasks 找当前 mp4 对应的 timeline
        timeline = None
        mp4 = self.mp4_edit.text().strip()
        for t in getattr(self.cfg, "video_tasks", []) or []:
            if str(t.get("last_result", "")) == mp4:
                timeline = t.get("timeline"); break
        dial_cues = derive_dialogue_cues(timeline)
        # 总时长：优先视频
        video_dur = self._video_preview.duration() if self._video_preview else 0.0
        total = derive_total_duration(
            bgm_session=self._session,
            sfx_session=self._sfx_session,
            dialogue_audios=timeline,
            video_duration=video_dur)
        video_cues = derive_video_cues(shot_bounds, total)
        self._overview_timeline.set_duration(total)
        self._overview_timeline.set_cues(
            video_cues + bgm_cues + sfx_cues + dial_cues)

    def _on_overview_playhead_dragged(self, t: float) -> None:
        self._video_preview.seek(t)

    def _on_video_position_changed(self, t: float) -> None:
        self._overview_timeline.set_playhead(t)

    def _on_overview_cue_clicked(self, track: str, idx: int, t_start: float) -> None:
        # 切对应 tab + scroll 到卡片 + 视频 seek
        tab_map = {"bgm": 1, "dialogue": 1, "sfx": 3}   # BGM/对白 共享 BGM tab；SFX 独立
        if track in tab_map:
            self.tabs.setCurrentIndex(tab_map[track])
        self._video_preview.seek(t_start)
```

`_on_done` / `_on_sfx_generate_done` 末尾追加：
```python
        self._rebuild_overview()
        new_src = self._resolve_video_source()
        if new_src:
            self._video_preview.set_source(new_src)
```

`SegmentReviewWidget` 加 `previewStarted` signal（在 `_on_candidate` 调 `player.play()` 之前 emit），`SfxReviewWidget` 同；`SoundtrackEditor._mount_session_tabs` / `_build_sfx_tab` 连：
```python
        review.previewStarted.connect(
            lambda: self._video_preview.pause() if self._video_preview else None)
```

---

## §4 错误处理

| 场景 | 处理 |
|------|------|
| `task.mp4` 不存在 / 损坏 | `set_source` 检查 `Path.exists()`；不存在 → 不加载，黑屏；不抛 |
| `session.output` 路径无效 | `_resolve_video_source` fall back 到原 mp4 |
| `cfg.video_tasks` 无匹配（dialogue 缺） | `derive_dialogue_cues` 返回 []；对白轨空白 |
| `shot_detector` 失败 / 未跑 | `shot_bounds=[]` → `derive_video_cues` 返回 1 个全长灰色块 |
| `bgm_session.segments` 空 | BGM 轨空白 |
| `sfx_session.shots` 全 skipped | SFX 轨空白 |
| `total_duration == 0` | timeline 不画 cue，仅画空轨 + axis（不崩） |
| `QMediaPlayer` 解码失败 | 信号 `mediaStatusChanged` 走 InvalidMedia，UI 显示黑屏；不阻塞 timeline |

---

## §5 测试策略

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_ui/test_overview_timeline_model.py` | 9-10 | derive_video_cues / derive_bgm_cues / derive_sfx_cues / derive_dialogue_cues / derive_total_duration 各自 + 空数据源 + 边界 |
| `tests/test_ui/test_overview_timeline_smoke.py` | 6-7 | set_cues 后 paintEvent 不崩 / set_playhead 更新 / 鼠标点击 cue emit cueClicked / 鼠标拖动 emit playheadDragged 节流验证 |
| `tests/test_ui/test_video_preview_widget_smoke.py` | 4-5 | __init__ 不崩 / set_source 无效路径不抛 / seek 节流 timer / play/pause/is_playing 状态机 / duration 默认 0 |
| `tests/test_ui/test_soundtrack_editor_overview_smoke.py` | 4-5 | 顶部 widget 存在 / tab 切换触发 rebuild / playhead 双向同步 / cue 点击切 tab |

**总估计 ~25 用例**。

测试中要点：
- Qt 测试一律 `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`
- VideoPreviewWidget 不真加载视频（headless 无 codec），仅测信号 + 状态机
- OverviewTimeline 的 paintEvent 通过 `widget.grab()` 触发即可，不验像素

---

## §6 验收标准

1. **顶部预览存在**：打开 SoundtrackEditor，顶部能看到 16:9 视频窗 + 4 轨 timeline
2. **4 数据源都正确渲染**：拿一段已跑完 4a 的视频（含 BGM + SFX + 对白）打开 SoundtrackEditor，4 轨色块按时间正确分布，cue 内文字为 prompt 前 N 字
3. **scrubbing 流畅**：拖播放头时视频实时显示对应帧，~30Hz 节流后不卡
4. **双向同步**：视频自然播放时 timeline 播放头同步右移；拖 timeline 时视频跳到对应帧
5. **cue 跳转**：点 BGM 色块 → 切到 BGM tab；点 SFX 色块 → 切到 SFX tab；点视频轨 → 不切 tab 仅 seek
6. **试听互斥**：BGM/SFX 候选试听开始时，视频自动暂停
7. **rebuild 时机**：BGM 生成完成 → timeline 出现 BGM 色块；SFX 生成完成 → 出现 SFX 色块；切 tab 后 rebuild 一次
8. **回归零**：现有 BGM/SFX tab 功能（试听 / 重生成 / 切候选 / 出片）零回归
9. **测试**：~25 新用例全绿

---

## §App A：数据源派生表

| 数据源 | 提供方 | _Cue 字段映射 |
|---|---|---|
| `ScoringSession.segments[i]` | `sound_track_agent.session` | `track="bgm"`, `t_start=seg.t_start`, `t_end=seg.t_end`, `label=music_prompt[:8] or "(未选)"`, `seg_index=i` |
| `SFXSession.shots[i]` (enabled & generated) | `sound_track_agent.sfx.session` | `track="sfx"`, `t_start=shot.t_start`, `t_end=t_start+duration`, `label=prompt_short[:6]`, `seg_index=i` |
| `cfg.video_tasks[*].timeline.audios[i]` | `drama_shot_master.config` | `track="dialogue"`, `t_start=start_frame/fps`, `t_end=t_start+length_frames/fps`, `label=audio_path basename[:6]`, `seg_index=i` |
| `shot_detector.detect_shots(mp4).t_end[]` | `sound_track_agent.shot_detector` | `track="video"`, 每个相邻 t_end 一个色块, `label=""`, `seg_index=i` |
| Video duration (ffprobe via QMediaPlayer.durationChanged) | `QMediaPlayer` | 决定 timeline 总宽度 |

## §App B：与 4a / 4c 的关系

**与 4a**：零后端改动。复用 `ScoringSession` / `SFXSession` / `cfg.video_tasks` / `shot_detector` 4 个数据源；UI 上只在 SoundtrackEditor 顶部插预览区，原 4 tab 完全保留。

**与 4c**：本 4b 的 `OverviewTimeline` 是 4c 多轨编辑器的**视觉骨架**——4c 时不替换，而是**扩展**：加 cue 拖动（mouseMove 改 cue.t_start）/ 边界 resize / 双击 inspector / 右键 split-duplicate-delete / 撤销栈 / 横向 zoom + scroll。`derive_cues` 纯函数 + `VideoPreviewWidget` 也直接复用，4c 不动它们。
