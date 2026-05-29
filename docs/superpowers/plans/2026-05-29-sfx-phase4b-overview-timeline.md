# Phase 4b 顶部预览（VideoPreview + OverviewTimeline）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SoundtrackEditor 顶部加 16:9 视频预览窗 + 4 轨 mini-timeline，timeline 拖动 30Hz 实时 scrubbing 视频画面，BGM/SFX cue 点击跳对应 Tab 卡片。

**Architecture:** 3 个新 UI widget（VideoPreviewWidget / OverviewTimeline / overview_timeline_model）+ SoundtrackEditor `_build_ui` 顶部插预览区 + 5 个新方法。零后端改动；复用 4a 的 ScoringSession / SFXSession / cfg.video_tasks 4 数据源；与 4c 共享视觉骨架。

**Tech Stack:** PySide6 (QVideoWidget / QMediaPlayer / QPainter 自绘) / blake2b hash for thumbnail cache key (后续 4c 用) / pytest with QT_QPA_PLATFORM=offscreen

**Spec:** `docs/superpowers/specs/2026-05-29-soundtrack-phase4b-overview-timeline-design.md`

**Branch:** `feat/sfx-phase4b`（Task 0 开）

---

## File Map

```
drama_shot_master/ui/widgets/
├── overview_timeline_model.py        # NEW（T2）: _Cue dataclass + 5 个 derive_* 纯函数
├── video_preview_widget.py            # NEW（T3）: QVideoWidget 包装 + 节流 seek
├── overview_timeline.py               # NEW（T4）: 自绘 4 轨 painted widget + scrubbing
├── soundtrack_editor.py               # CHANGED（T5）: 顶部插预览区 + 5 新方法 + 接线
├── segment_review_widget.py           # CHANGED（T6）: + previewStarted signal
└── sfx_review_widget.py               # CHANGED（T6）: + previewStarted signal
```

---

### Task 0: 开 feat/sfx-phase4b 分支

- [ ] **Step 0.1: 从 main 开新分支**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
git branch --show-current     # 应为 main（已含 4a 全部 14 commit）
git checkout -b feat/sfx-phase4b
git branch --show-current     # feat/sfx-phase4b
```

后续所有 commit 必须落在 `feat/sfx-phase4b`，每 task 开始前 implementer 验证。

---

### Task 1: _Cue dataclass 骨架

**Files:**
- Create: `drama_shot_master/ui/widgets/overview_timeline_model.py`
- Test: `tests/test_ui/test_overview_timeline_model.py`

- [ ] **Step 1.1: 写失败测试** — 新建 `tests/test_ui/test_overview_timeline_model.py`：

```python
"""overview_timeline_model: _Cue dataclass + derive_* 纯函数."""
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue


def test_cue_fields():
    c = _Cue(track="bgm", t_start=0.0, t_end=3.0, label="末日", seg_index=0)
    assert c.track == "bgm"
    assert c.t_start == 0.0
    assert c.t_end == 3.0
    assert c.label == "末日"
    assert c.seg_index == 0
```

- [ ] **Step 1.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/test_overview_timeline_model.py::test_cue_fields -q
```
Expected: 1 FAILED (ModuleNotFoundError)

- [ ] **Step 1.3: 创建 model 文件**

```python
"""数据派生：4 个数据源 → 统一 _Cue 列表。无 IO，可单测。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


@dataclass
class _Cue:
    track: Literal["video", "bgm", "sfx", "dialogue"]
    t_start: float
    t_end: float
    label: str
    seg_index: int
```

- [ ] **Step 1.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/test_overview_timeline_model.py::test_cue_fields -q
```
Expected: 1 passed

- [ ] **Step 1.5: 提交**

```bash
git branch --show-current     # feat/sfx-phase4b
git add drama_shot_master/ui/widgets/overview_timeline_model.py \
        tests/test_ui/test_overview_timeline_model.py
git commit -m "feat(ui): + overview_timeline_model._Cue dataclass

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 5 个 derive_* 纯函数

**Files:**
- Modify: `drama_shot_master/ui/widgets/overview_timeline_model.py`
- Modify: `tests/test_ui/test_overview_timeline_model.py`

- [ ] **Step 2.1: 写 9 个失败测试** — 追加到 `tests/test_ui/test_overview_timeline_model.py`：

```python
from drama_shot_master.ui.widgets.overview_timeline_model import (
    derive_video_cues, derive_bgm_cues, derive_sfx_cues,
    derive_dialogue_cues, derive_total_duration,
)


def test_derive_video_cues_from_shot_boundaries():
    cues = derive_video_cues([5.0, 12.0, 20.0], total_duration=30.0)
    # 切分: [0-5][5-12][12-20][20-30] = 4 段
    assert len(cues) == 4
    assert cues[0].t_start == 0.0 and cues[0].t_end == 5.0
    assert cues[1].t_start == 5.0 and cues[1].t_end == 12.0
    assert cues[3].t_end == 30.0
    assert all(c.track == "video" for c in cues)


def test_derive_video_cues_empty_boundaries_returns_single_block():
    cues = derive_video_cues([], total_duration=30.0)
    assert len(cues) == 1
    assert cues[0].t_start == 0.0 and cues[0].t_end == 30.0


def test_derive_video_cues_zero_duration_returns_empty():
    assert derive_video_cues([], total_duration=0.0) == []


def test_derive_bgm_cues_chosen_vs_unchosen_label(monkeypatch):
    """chosen_candidate=None → label='(未选)'；否则 prompt 前 8 字."""
    from dataclasses import dataclass

    @dataclass
    class _Seg:
        t_start: float
        t_end: float
        chosen_candidate: object
        music_prompt: str
    sess = type("S", (), {"segments": [
        _Seg(0.0, 3.0, 0, "末日废土冷色调阴郁"),
        _Seg(3.0, 6.0, None, "古风"),
    ]})()
    cues = derive_bgm_cues(sess)
    assert len(cues) == 2
    assert cues[0].label == "末日废土冷色调阴郁"[:8]
    assert cues[1].label == "(未选)"
    assert all(c.track == "bgm" for c in cues)


def test_derive_bgm_cues_none_session():
    assert derive_bgm_cues(None) == []


def test_derive_sfx_cues_only_enabled_and_generated():
    """skipped / 未生成 / disabled 都过滤."""
    from dataclasses import dataclass

    @dataclass
    class _Shot:
        t_start: float
        duration: float
        prompt_short: str
        status: str = "generated"
        enabled: bool = True
    sess = type("S", (), {"shots": [
        _Shot(0.0, 3.0, "门吱呀", "generated", True),    # 应入
        _Shot(3.0, 3.0, "无", "skipped", True),          # 跳过
        _Shot(6.0, 2.0, "脚步", "generated", False),     # disabled 跳
        _Shot(8.0, 3.0, "雨", "planned", True),          # 未生成
    ]})()
    cues = derive_sfx_cues(sess)
    assert len(cues) == 1
    assert cues[0].label == "门吱呀"[:6]
    assert cues[0].t_start == 0.0 and cues[0].t_end == 3.0


def test_derive_dialogue_cues_from_timeline_dict():
    timeline = {"frame_rate": 24.0, "audios": [
        {"audio_path": "/a/voice_charA.flac",
         "start_frame": 0, "length_frames": 48},
        {"audio_path": "/a/voice_charB.flac",
         "start_frame": 72, "length_frames": 96},
    ]}
    cues = derive_dialogue_cues(timeline)
    assert len(cues) == 2
    assert abs(cues[0].t_start - 0.0) < 1e-6
    assert abs(cues[0].t_end - 2.0) < 1e-6           # 48/24
    assert abs(cues[1].t_start - 3.0) < 1e-6         # 72/24
    assert abs(cues[1].t_end - 7.0) < 1e-6           # (72+96)/24


def test_derive_dialogue_cues_empty_or_none():
    assert derive_dialogue_cues(None) == []
    assert derive_dialogue_cues({}) == []
    assert derive_dialogue_cues({"audios": []}) == []


def test_derive_total_duration_max_of_all():
    from dataclasses import dataclass

    @dataclass
    class _Seg:
        t_end: float

    @dataclass
    class _Shot:
        t_start: float
        duration: float
    bgm = type("B", (), {"segments": [_Seg(10.0), _Seg(20.0)]})()
    sfx = type("S", (), {"shots": [_Shot(15.0, 5.0)]})()
    timeline = {"frame_rate": 24.0, "audios": [
        {"start_frame": 0, "length_frames": 600},    # 25s
    ]}
    total = derive_total_duration(
        bgm_session=bgm, sfx_session=sfx,
        dialogue_audios=timeline, video_duration=22.0)
    assert total == 25.0    # 对白 25s 最长


def test_derive_total_duration_empty_falls_back_to_30():
    total = derive_total_duration(
        bgm_session=None, sfx_session=None,
        dialogue_audios=None, video_duration=0.0)
    assert total == 30.0
```

- [ ] **Step 2.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/test_overview_timeline_model.py -q
```
Expected: 10 FAILED（除了 Task 1 的 test_cue_fields 外，9 个新用例 FAIL）

- [ ] **Step 2.3: 实现 5 个 derive 函数 + label helper**

追加到 `drama_shot_master/ui/widgets/overview_timeline_model.py`：

```python
from typing import Optional


def _label_from_prompt(text: str, max_chars: int = 8) -> str:
    t = (text or "").strip()
    return t[:max_chars] if t else ""


def derive_video_cues(shot_boundaries: list[float],
                      total_duration: float) -> list[_Cue]:
    if total_duration <= 0:
        return []
    if not shot_boundaries:
        return [_Cue("video", 0.0, total_duration, "", 0)]
    edges = [0.0] + list(shot_boundaries) + [total_duration]
    cues = []
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        if b > a:
            cues.append(_Cue("video", float(a), float(b), "", i))
    return cues


def derive_bgm_cues(bgm_session) -> list[_Cue]:
    if bgm_session is None:
        return []
    out = []
    for i, seg in enumerate(getattr(bgm_session, "segments", []) or []):
        prompt = getattr(seg, "music_prompt", "") or ""
        label = (_label_from_prompt(prompt, 8)
                 if seg.chosen_candidate is not None else "(未选)")
        out.append(_Cue("bgm", float(seg.t_start), float(seg.t_end),
                        label, i))
    return out


def derive_sfx_cues(sfx_session) -> list[_Cue]:
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
        label = (path.rsplit("/", 1)[-1].rsplit(".", 1)[0][:6]
                 if path else f"对白{i}")
        out.append(_Cue("dialogue", t_start, t_end, label, i))
    return out


def derive_total_duration(*, bgm_session, sfx_session,
                          dialogue_audios: Optional[dict],
                          video_duration: float = 0.0) -> float:
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
                candidates.append(
                    (float(a["start_frame"]) + float(a["length_frames"])) / fps)
            except (TypeError, ValueError, KeyError):
                continue
    pos = max([c for c in candidates if c > 0], default=0.0)
    return pos if pos > 0 else 30.0
```

- [ ] **Step 2.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/test_overview_timeline_model.py -q
```
Expected: 10 passed

- [ ] **Step 2.5: 提交**

```bash
git add drama_shot_master/ui/widgets/overview_timeline_model.py \
        tests/test_ui/test_overview_timeline_model.py
git commit -m "feat(ui): + 5 个 derive_*_cues 纯函数（BGM/SFX/对白/视频/总时长）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: VideoPreviewWidget

**Files:**
- Create: `drama_shot_master/ui/widgets/video_preview_widget.py`
- Test: `tests/test_ui/test_video_preview_widget_smoke.py`

- [ ] **Step 3.1: 写失败测试** — 新建 `tests/test_ui/test_video_preview_widget_smoke.py`：

```python
"""VideoPreviewWidget smoke：构造不崩 + set_source 路径校验 + seek 节流 + 状态机。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct_does_not_crash(app):
    w = VideoPreviewWidget()
    assert w.duration() == 0.0
    assert w.is_playing() is False


def test_set_source_nonexistent_does_not_raise(app, tmp_path):
    w = VideoPreviewWidget()
    # 不存在路径不该抛
    w.set_source(str(tmp_path / "nope.mp4"))
    w.set_source(None)
    w.set_source("")
    assert w.is_playing() is False


def test_seek_throttles(app, tmp_path, monkeypatch):
    """连续调 seek 应只触发 1 次 timer.start（节流）。"""
    w = VideoPreviewWidget()
    # 强制建 player（避免 lazy 模式不进 seek）
    w._ensure_player()
    starts = {"n": 0}
    orig_start = w._seek_timer.start
    def fake_start(*a, **kw):
        starts["n"] += 1
        return orig_start(*a, **kw)
    monkeypatch.setattr(w._seek_timer, "start", fake_start)
    w.seek(1.0); w.seek(2.0); w.seek(3.0)
    # 节流：3 次连续 seek 只有 1 次 timer.start（timer 还在 active）
    assert starts["n"] == 1


def test_play_pause_no_player_returns_silently(app):
    w = VideoPreviewWidget()
    # 没建 player 时 play/pause 不该崩
    w.play()
    w.pause()
    assert w.is_playing() is False


def test_position_changed_signal_emitted(app):
    """模拟 player.positionChanged → widget 应 emit positionChanged(秒)."""
    w = VideoPreviewWidget()
    w._ensure_player()
    received = []
    w.positionChanged.connect(lambda t: received.append(t))
    w._on_position_changed(2500)        # ms
    assert len(received) == 1
    assert abs(received[0] - 2.5) < 1e-6
```

- [ ] **Step 3.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/test_video_preview_widget_smoke.py -q
```
Expected: 5 FAILED (ImportError)

- [ ] **Step 3.3: 创建 VideoPreviewWidget**

新建 `drama_shot_master/ui/widgets/video_preview_widget.py`，**完整代码**：

```python
"""视频预览 widget：QVideoWidget + 工具栏 + 节流 seek。

封装 QMediaPlayer 让上层只看到 set_source/seek/play/pause/duration/is_playing 6 个
方法 + 1 个 positionChanged(float) signal。

Player 懒创建（避免 headless 测试 segfault），首次 set_source 才碰音视频后端。
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
        self._player = None
        self._audio = None
        self._video_widget = None
        self._duration_sec = 0.0
        self._pending_seek_ms = None
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

    def set_source(self, video_path) -> None:
        """加载 mp4；None / 空 / 不存在 → 仅 stop，不加载（黑屏）。"""
        if not video_path or not Path(str(video_path)).exists():
            if self._player is not None:
                self._player.stop()
            return
        player = self._ensure_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(str(video_path)))

    def seek(self, t_sec: float) -> None:
        if self._player is None:
            return
        self._pending_seek_ms = max(0, int(round(float(t_sec) * 1000)))
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
        t = ms / 1000.0
        self.positionChanged.emit(t)
        self._update_time_label(t)

    def _on_duration_changed(self, ms: int):
        self._duration_sec = ms / 1000.0
        self._update_time_label(0.0)

    def _on_state_changed(self, _state):
        self.btn_play.setText("⏸" if self.is_playing() else "▶")

    def _on_volume(self, val: int):
        if self._audio is not None:
            self._audio.setVolume(val / 100.0)

    def _update_time_label(self, t_sec: float):
        def _fmt(s: float) -> str:
            s = max(0, int(s))
            return f"{s // 60}:{s % 60:02d}"
        self.time_label.setText(f"{_fmt(t_sec)} / {_fmt(self._duration_sec)}")
```

- [ ] **Step 3.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/test_video_preview_widget_smoke.py -q
```
Expected: 5 passed

- [ ] **Step 3.5: 提交**

```bash
git add drama_shot_master/ui/widgets/video_preview_widget.py \
        tests/test_ui/test_video_preview_widget_smoke.py
git commit -m "feat(ui): + VideoPreviewWidget（QVideoWidget + 工具栏 + 30Hz 节流 seek）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: OverviewTimeline 自绘 widget

**Files:**
- Create: `drama_shot_master/ui/widgets/overview_timeline.py`
- Test: `tests/test_ui/test_overview_timeline_smoke.py`

- [ ] **Step 4.1: 写失败测试** — 新建 `tests/test_ui/test_overview_timeline_smoke.py`：

```python
"""OverviewTimeline smoke：set_cues 不崩 + 鼠标点击 emit cueClicked + 拖动 emit playheadDragged + 节流."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue
from drama_shot_master.ui.widgets.overview_timeline import OverviewTimeline


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _press(widget, x, y):
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(x, y),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    widget.mousePressEvent(ev)


def _move(widget, x, y):
    ev = QMouseEvent(QMouseEvent.MouseMove, QPoint(x, y),
                     Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    widget.mouseMoveEvent(ev)


def _release(widget, x, y):
    ev = QMouseEvent(QMouseEvent.MouseButtonRelease, QPoint(x, y),
                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    widget.mouseReleaseEvent(ev)


def test_construct_minimum_height(app):
    w = OverviewTimeline()
    assert w.minimumHeight() >= 80


def test_set_cues_and_set_duration_does_not_crash(app):
    w = OverviewTimeline()
    w.set_duration(30.0)
    w.set_cues([
        _Cue("bgm", 0.0, 10.0, "末日", 0),
        _Cue("sfx", 5.0, 6.0, "门", 0),
        _Cue("dialogue", 0.0, 3.0, "A1", 0),
        _Cue("video", 0.0, 30.0, "", 0),
    ])
    w.resize(600, 140)
    w.grab()    # 触发 paintEvent


def test_set_playhead_clamps(app):
    w = OverviewTimeline()
    w.set_duration(10.0)
    w.set_playhead(-1.0)
    assert w._playhead == 0.0
    w.set_playhead(20.0)
    assert w._playhead == 10.0


def test_click_on_cue_emits_cueClicked(app):
    w = OverviewTimeline()
    w.resize(600, 140)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "末日", 0)])
    received = []
    w.cueClicked.connect(lambda *a: received.append(a))
    # BGM 轨 y ~= 14 (axis) + 18 (video) + 2 (gap) + 11 (BGM 中段) = ~45
    # BGM cue 占 x ~= 60 + 0 ~ 60 + 200 (30s 全宽 600，10s 占 1/3)
    # 点 x=100 落在 BGM cue 内
    _press(w, 100, 45)
    assert received and received[0][0] == "bgm" and received[0][1] == 0


def test_click_on_video_track_seeks_not_cue(app):
    """视频轨点击应当只触发 drag seek，不 emit cueClicked。"""
    w = OverviewTimeline()
    w.resize(600, 140)
    w.set_duration(30.0)
    w.set_cues([_Cue("video", 0.0, 30.0, "", 0)])
    cue_received = []
    drag_received = []
    w.cueClicked.connect(lambda *a: cue_received.append(a))
    w.playheadDragged.connect(lambda t: drag_received.append(t))
    # 视频轨 y ~= 14 + 9 = 23 (中段)
    _press(w, 200, 23)
    _release(w, 200, 23)
    assert cue_received == []        # 不 emit cueClicked
    # 视频轨视为 drag，应 emit playheadDragged（释放时 flush）
    assert len(drag_received) == 1


def test_drag_throttle_emits_at_30hz(app):
    """连续多次 move 节流到 30Hz：第一次 emit + 中间被合并到 timer + release flush。"""
    w = OverviewTimeline()
    w.resize(600, 140)
    w.set_duration(30.0)
    received = []
    w.playheadDragged.connect(lambda t: received.append(t))
    # 视频轨拖动
    _press(w, 100, 23)
    _move(w, 200, 23)
    _move(w, 300, 23)
    _move(w, 400, 23)
    _release(w, 400, 23)
    # 至少 emit 1 次（释放时 flush），最多受 timer 启动一次 + release flush 一次
    assert len(received) >= 1
    # 最后一次 emit 的位置应当对应 release 点
    last_t = received[-1]
    # x=400 对应 t = (400-60)/(600-60) * 30 ≈ 18.9s
    assert 17 < last_t < 21
```

- [ ] **Step 4.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/test_overview_timeline_smoke.py -q
```
Expected: 7 FAILED (ImportError)

- [ ] **Step 4.3: 创建 OverviewTimeline**

新建 `drama_shot_master/ui/widgets/overview_timeline.py`，**完整代码**（按 spec §3.3）：

```python
"""4 轨自绘 mini-timeline + 播放头 + scrubbing。

不使用 QGraphicsView（杀鸡用牛刀），自绘 paintEvent。
4 轨顺序: 视频 / BGM / SFX / 对白；播放头红色竖线穿透所有轨。
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget

from drama_shot_master.ui.widgets.overview_timeline_model import _Cue


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
    playheadDragged = Signal(float)
    cueClicked = Signal(str, int, float)
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
        self._playhead = max(0.0, min(self._duration, float(t_sec)))
        if not self._dragging:
            self.update()

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

    def paintEvent(self, _event):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), _BG_FRAME_COLOR)
            self._paint_axis(p)
            for track in _TRACK_ORDER:
                ty, th = self._track_y(track)
                p.fillRect(_LABEL_WIDTH, ty, self.width() - _LABEL_WIDTH,
                           th, _BG_TRACK_COLOR)
                self._paint_label(p, track, ty, th)
            font = QFont(); font.setPointSize(8); p.setFont(font)
            fm = QFontMetrics(font)
            for c in self._cues:
                ty, th = self._track_y(c.track)
                x_a = self._t_to_x(c.t_start)
                x_b = self._t_to_x(c.t_end)
                color = _TRACK_COLORS[c.track]
                rect = QRect(x_a, ty, max(2, x_b - x_a), th)
                p.fillRect(rect, color)
                if c.track == "video":
                    p.setPen(QColor("#000000"))
                    p.drawLine(x_b, ty, x_b, ty + th)
                if c.label and rect.width() >= 30:
                    p.setPen(_TEXT_COLOR)
                    elide_w = rect.width() - 6
                    text = fm.elidedText(c.label, Qt.ElideRight, elide_w)
                    p.drawText(rect.adjusted(3, 0, -3, 0),
                               Qt.AlignVCenter | Qt.AlignLeft, text)
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
        font = QFont(); font.setPointSize(7); p.setFont(font)
        p.setPen(_LABEL_COLOR)
        for i in range(5):
            t = self._duration * i / 4
            x = self._t_to_x(t)
            mins = int(t // 60); secs = int(t % 60)
            p.drawText(x + 2, _AXIS_HEIGHT - 3, f"{mins}:{secs:02d}")
            if 0 < i < 4:
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

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        x, y = event.pos().x(), event.pos().y()
        cue = self._cue_at(x, y)
        if cue is not None and cue.track != "video":
            self.cueClicked.emit(cue.track, cue.seg_index, cue.t_start)
            return
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

- [ ] **Step 4.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/test_overview_timeline_smoke.py -q
```
Expected: 7 passed

- [ ] **Step 4.5: 提交**

```bash
git add drama_shot_master/ui/widgets/overview_timeline.py \
        tests/test_ui/test_overview_timeline_smoke.py
git commit -m "feat(ui): + OverviewTimeline 自绘 4 轨 widget + 30Hz scrubbing

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: SoundtrackEditor 集成顶部预览

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_soundtrack_editor_overview_smoke.py`

- [ ] **Step 5.1: 先 Read soundtrack_editor.py 当前结构**

```bash
grep -n "def _build_ui\|self.tabs\|self._sfx_session\|def _on_done\|def _on_sfx_generate_done\|_mount_session_tabs\|self._review =\|_build_sfx_tab" \
  drama_shot_master/ui/widgets/soundtrack_editor.py
```

Note 关键属性名（`self.tabs` / `self._session` / `self._sfx_session` / `self.mp4_edit` / `self.cfg` / `self._task`），确认与下面 Step 5.3 代码一致。

- [ ] **Step 5.2: 写失败测试** — 新建 `tests/test_ui/test_soundtrack_editor_overview_smoke.py`：

```python
"""SoundtrackEditor 顶部预览 smoke：widget 存在 + tab 切换触发 rebuild + cue 点击切 tab."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config()
    c.settings_path = tmp_path / "s.json"
    return c


def _task(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    return {"id": "t1", "name": "测试", "mp4": str(mp4),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}


def test_editor_has_overview_widgets(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    assert ed._video_preview is not None
    assert ed._overview_timeline is not None


def test_rebuild_overview_does_not_crash_with_empty_session(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    # 没 BGM/SFX session 也应该不崩
    ed._rebuild_overview()


def test_tab_change_triggers_rebuild(tmp_path, monkeypatch):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    rebuilt = {"n": 0}
    orig = ed._rebuild_overview
    def fake_rebuild():
        rebuilt["n"] += 1
        return orig()
    monkeypatch.setattr(ed, "_rebuild_overview", fake_rebuild)
    ed.tabs.setCurrentIndex(2)        # 切到第 3 tab
    assert rebuilt["n"] >= 1


def test_overview_playhead_drag_calls_video_seek(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    seeks = []
    # monkeypatch video preview seek
    ed._video_preview.seek = lambda t: seeks.append(t)
    ed._overview_timeline.playheadDragged.emit(5.5)
    assert seeks == [5.5]


def test_overview_cue_clicked_switches_tab(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    # 当前 BGM tab 是 index 1（试听选优）；SFX tab 是 index 3
    seeks = []
    ed._video_preview.seek = lambda t: seeks.append(t)
    ed._overview_timeline.cueClicked.emit("bgm", 0, 2.5)
    assert ed.tabs.currentIndex() == 1
    assert seeks == [2.5]
    ed._overview_timeline.cueClicked.emit("sfx", 0, 6.0)
    assert ed.tabs.currentIndex() == 3
```

- [ ] **Step 5.3: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/test_soundtrack_editor_overview_smoke.py -q
```
Expected: 5 FAILED（AttributeError: _video_preview / _overview_timeline）

- [ ] **Step 5.4: 改 SoundtrackEditor**

打开 `drama_shot_master/ui/widgets/soundtrack_editor.py`。

(a) `__init__` 加属性（紧跟 `self._sfx_worker = None` 之后）：

```python
        self._video_preview = None
        self._overview_timeline = None
```

(b) `_build_ui()` 在 `self.tabs = QTabWidget()` 之前插预览区（即把预览放在 `tabs` 之上）：

```python
        # 顶部预览区 (Phase 4b)
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
```

然后在 `root.addWidget(self.tabs)` 之前插：

```python
        root.addWidget(self._video_preview)
        root.addWidget(self._overview_timeline)
```

(c) `_build_ui()` 末尾接 tabs.currentChanged + 初次 rebuild：

```python
        self.tabs.currentChanged.connect(lambda _i: self._rebuild_overview())
        self._rebuild_overview()
        src = self._resolve_video_source()
        if src:
            self._video_preview.set_source(src)
```

(d) 在文件末尾（`to_payload` 之前）追加 6 个新方法：

```python
    # ------------------------------------------------------------------
    # Phase 4b: 顶部预览方法
    # ------------------------------------------------------------------

    def _resolve_video_source(self):
        """有 BGM mix 完成 session.output → 用成片；否则用原 mp4."""
        if self._session is not None:
            out = getattr(self._session, "output", None)
            if out and Path(out).exists():
                return out
        mp4 = (self._task.get("mp4") or "").strip()
        if not mp4:
            mp4 = self.mp4_edit.text().strip()
        return mp4 if mp4 and Path(mp4).exists() else None

    def _rebuild_overview(self):
        if self._overview_timeline is None:
            return
        from drama_shot_master.ui.widgets.overview_timeline_model import (
            derive_video_cues, derive_bgm_cues, derive_sfx_cues,
            derive_dialogue_cues, derive_total_duration,
        )
        bgm_cues = derive_bgm_cues(self._session)
        sfx_cues = derive_sfx_cues(self._sfx_session)
        timeline = None
        mp4 = self.mp4_edit.text().strip() if hasattr(self, "mp4_edit") else ""
        for t in (getattr(self.cfg, "video_tasks", []) or []):
            if str(t.get("last_result", "")) == mp4:
                timeline = t.get("timeline"); break
        dial_cues = derive_dialogue_cues(timeline)
        shot_bounds = []
        if self._session is not None:
            shot_bounds = [float(s.t_end)
                           for s in (self._session.segments or [])]
        video_dur = (self._video_preview.duration()
                     if self._video_preview else 0.0)
        total = derive_total_duration(
            bgm_session=self._session,
            sfx_session=self._sfx_session,
            dialogue_audios=timeline,
            video_duration=video_dur)
        video_cues = derive_video_cues(shot_bounds, total)
        self._overview_timeline.set_duration(total)
        self._overview_timeline.set_cues(
            video_cues + bgm_cues + sfx_cues + dial_cues)

    def _on_overview_playhead_dragged(self, t: float):
        if self._video_preview is not None:
            self._video_preview.seek(t)

    def _on_video_position_changed(self, t: float):
        if self._overview_timeline is not None:
            self._overview_timeline.set_playhead(t)

    def _on_overview_cue_clicked(self, track: str, idx: int, t_start: float):
        # BGM/对白 → tab 1（试听选优）；SFX → tab 3
        tab_map = {"bgm": 1, "dialogue": 1, "sfx": 3}
        if track in tab_map:
            self.tabs.setCurrentIndex(tab_map[track])
        if self._video_preview is not None:
            self._video_preview.seek(t_start)
```

(e) 在 `_on_done` 末尾追加（让 BGM 生成完成时更新预览）：

```python
        self._rebuild_overview()
        new_src = self._resolve_video_source()
        if new_src and self._video_preview is not None:
            self._video_preview.set_source(new_src)
```

(f) 在 `_on_sfx_generate_done` 末尾追加：

```python
        self._rebuild_overview()
```

(g) Import：文件顶部 imports 处确认有 `from pathlib import Path`（已有，跳过）。

- [ ] **Step 5.5: 跑测试确认 PASS + 现有 editor 测试零回归**

```bash
python -m pytest tests/test_ui/test_soundtrack_editor_overview_smoke.py \
                 tests/test_ui/test_soundtrack_editor_smoke.py \
                 tests/test_ui/test_soundtrack_editor_sfx_tab_smoke.py -q
```
Expected: 全绿

- [ ] **Step 5.6: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py \
        tests/test_ui/test_soundtrack_editor_overview_smoke.py
git commit -m "feat(ui): SoundtrackEditor 顶部插 VideoPreview + OverviewTimeline + 6 新方法

- 预览区在 tabs 之上（视频窗 + 4 轨 timeline）
- tab 切换 / _on_done / _on_sfx_generate_done 触发 _rebuild_overview
- playhead 双向同步 (video <-> timeline)
- cue 点击切对应 Tab + video seek

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 试听互斥（previewStarted signal）

**Files:**
- Modify: `drama_shot_master/ui/widgets/segment_review_widget.py`
- Modify: `drama_shot_master/ui/widgets/sfx_review_widget.py`
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_overview_preview_mutex.py`

- [ ] **Step 6.1: 写失败测试** — 新建 `tests/test_ui/test_overview_preview_mutex.py`：

```python
"""试听 BGM/SFX 候选时视频应自动暂停。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config()
    c.settings_path = tmp_path / "s.json"
    return c


def _task(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    return {"id": "t1", "name": "测试", "mp4": str(mp4),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}


def test_bgm_review_widget_has_preview_started_signal():
    """SegmentReviewWidget 应当有 previewStarted 信号."""
    from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
    assert hasattr(SegmentReviewWidget, "previewStarted")


def test_sfx_review_widget_has_preview_started_signal():
    from drama_shot_master.ui.widgets.sfx_review_widget import SfxReviewWidget
    assert hasattr(SfxReviewWidget, "previewStarted")


def test_bgm_preview_started_pauses_video(tmp_path):
    """SoundtrackEditor 收到 BGM 试听 signal → 调 video_preview.pause."""
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    # 挂载 BGM review（用空 session stub）
    from sound_track_agent.session import ScoringSession
    stub = ScoringSession(source_mp4="", source_hash="", global_style="",
                          frame_rate=24.0, segments=[])
    ed._session = stub
    ed._mount_session_tabs()
    paused = {"n": 0}
    ed._video_preview.pause = lambda: paused.__setitem__("n", paused["n"] + 1)
    ed._review.previewStarted.emit()
    assert paused["n"] == 1


def test_sfx_preview_started_pauses_video(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
    ed._sfx_session = SFXSession(
        source_mp4="", source_hash="", frame_rate=24.0,
        shots=[SFXShot(0, 0.0, 3.0, status="generated",
                       candidates=[SFXCandidate("/a.mp3", 1, "x")],
                       chosen_candidate=0)])
    ed._rebuild_sfx_review()
    paused = {"n": 0}
    ed._video_preview.pause = lambda: paused.__setitem__("n", paused["n"] + 1)
    # 找到 SfxReviewWidget 实例
    sfx_review = None
    for i in range(ed._sfx_review_lay.count()):
        w = ed._sfx_review_lay.itemAt(i).widget()
        if w is not None and w.__class__.__name__ == "SfxReviewWidget":
            sfx_review = w; break
    assert sfx_review is not None
    sfx_review.previewStarted.emit()
    assert paused["n"] == 1
```

- [ ] **Step 6.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/test_overview_preview_mutex.py -q
```
Expected: 4 FAILED

- [ ] **Step 6.3: SegmentReviewWidget + SfxReviewWidget 加 signal**

打开 `drama_shot_master/ui/widgets/segment_review_widget.py`，找到 class `SegmentReviewWidget` 定义内的 signal 声明（如 `chosenChanged = Signal()`），后面追加：

```python
    previewStarted = Signal()
```

然后找到 `_on_candidate` 方法里**调 `player.play()` 之前**追加：

```python
        self.previewStarted.emit()
```

打开 `drama_shot_master/ui/widgets/sfx_review_widget.py`，同操作：在 signal 声明（`chosenChanged = Signal()` 等）后追加：

```python
    previewStarted = Signal()
```

在 `_on_candidate` 方法里**调 `player.play()` 之前**追加：

```python
        self.previewStarted.emit()
```

- [ ] **Step 6.4: SoundtrackEditor 连 signal**

打开 `drama_shot_master/ui/widgets/soundtrack_editor.py`。

(a) 找到 `_mount_session_tabs` 里 `self._review = SegmentReviewWidget(self._session)` 那行**之后**，在 `lay.addWidget(self._review)` **之前**追加：

```python
        self._review.previewStarted.connect(
            lambda: self._video_preview.pause()
                    if self._video_preview is not None else None)
```

(b) 找到 `_rebuild_sfx_review` 里 `review.chosenChanged.connect(...)` 那行**之后**，`self._sfx_review_lay.addWidget(review)` **之前**追加：

```python
        review.previewStarted.connect(
            lambda: self._video_preview.pause()
                    if self._video_preview is not None else None)
```

- [ ] **Step 6.5: 跑测试确认 PASS + 现有 review widget 测试零回归**

```bash
python -m pytest tests/test_ui/test_overview_preview_mutex.py \
                 tests/test_ui/test_segment_review_smoke.py \
                 tests/test_ui/test_sfx_review_widget_smoke.py -q
```
Expected: 全绿

- [ ] **Step 6.6: 提交**

```bash
git add drama_shot_master/ui/widgets/segment_review_widget.py \
        drama_shot_master/ui/widgets/sfx_review_widget.py \
        drama_shot_master/ui/widgets/soundtrack_editor.py \
        tests/test_ui/test_overview_preview_mutex.py
git commit -m "feat(ui): 试听互斥（BGM/SFX 候选试听 → video 自动暂停）

SegmentReviewWidget / SfxReviewWidget 加 previewStarted signal
（_on_candidate 调 player.play 前 emit）；SoundtrackEditor 连接到
video_preview.pause()。不实现自动 resume（用户停止试听后手动续播）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: 收尾验证 + 文档更新

**Files:**
- 无新文件，仅跑回归
- 可选 Modify: `docs/explorer/配乐智能体开发者手册.md`（如果存在），追加 4b 顶部预览章节

- [ ] **Step 7.1: 全套回归**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
python -m pytest tests/test_sound_track_agent/ tests/test_ui/ tests/test_config/ tests/test_core/ -q 2>&1 | tail -5
```
Expected: 全绿（约 ~370+ 用例：Sprint 0 + Phase 4a 现有 + 4b 新增 ~25 个）

- [ ] **Step 7.2: 手工 e2e 验证**（按 spec §6 验收 1-8 逐条）

1. 打开 SoundtrackEditor，顶部能看到 16:9 视频窗 + 4 轨 timeline ✓
2. 拖播放头 → 视频实时显示对应帧 ✓
3. 视频自然播放 → timeline 播放头同步右移 ✓
4. 点 BGM 色块 → 切到 BGM tab ✓
5. 点 SFX 色块 → 切到 SFX tab ✓
6. 试听候选 → 视频自动暂停 ✓
7. BGM 生成完成 → timeline 出现 BGM 色块 ✓
8. SFX 生成完成 → timeline 出现 SFX 色块 ✓

如有任一项不通过，回到对应 Task 修复。

- [ ] **Step 7.3:**（可选）更新开发者手册

如果 `docs/explorer/配乐智能体开发者手册.md` 存在，追加一节：

```markdown
## Phase 4b: 顶部预览（VideoPreview + OverviewTimeline）

SoundtrackEditor 顶部新增视频预览窗（QVideoWidget）+ 4 轨 mini-timeline（自绘）：
- 视频源自动切换：有 `session.output` 用成片含 BGM+SFX；否则用 task.mp4
- timeline 4 轨：视频镜头 / BGM 段 / SFX 镜 / 对白音频，颜色固定
- 双向 playhead 同步：QMediaPlayer.positionChanged ↔ timeline 拖动 (30Hz 节流)
- cue 点击：BGM/对白 → tab 1；SFX → tab 3；视频轨 → 仅 seek
- 试听互斥：BGM/SFX 候选试听开始 → video 自动 pause
- 数据派生：`overview_timeline_model.derive_*_cues` 5 个纯函数（无 IO，可单测）
```

提交：
```bash
git add docs/explorer/配乐智能体开发者手册.md
git commit -m "docs: 开发者手册追加 Phase 4b 顶部预览章节

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7.4:** Sprint 收尾 — 走 `superpowers:finishing-a-development-branch`

按 user 习惯（Sprint 0 选保留分支自己处理，Phase 4a 合到 main），询问用户：
- 选项 1: merge `feat/sfx-phase4b` → main
- 选项 2: 推 origin/feat/sfx-phase4b 暂不合
- 选项 3: 保留本地不动
- 选项 4: discard（需确认）

---

## 收尾验证（全部任务完成后）

按 spec §6 验收 9 条逐项确认；任一未达标 → 回到对应 Task 修复 → 再验。
