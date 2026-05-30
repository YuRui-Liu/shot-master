# 轨级混音控件 实施计划（子项目 #2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给配乐 DAW 加左侧轨道头混音控件——原声/BGM/SFX 三轨各有 M(静音)/S(独奏)/音量，实时作用于叠加播放并持久化。

**Architecture:** `TrackMixState`(纯逻辑：mute/solo/volume + 独奏解算 + mix.json 持久化) ← `TrackHeaderColumn`(左侧控件列) → editor `_apply_audio_state`(把 play_mode + mix 合成每轨最终音频，驱动 OverlayMixer + VideoPreviewWidget)。DawTrackView 去掉画字标签并导出布局常量供对齐。

**Tech Stack:** Python dataclass / PySide6(QPushButton checkable / QSlider / Signal) / pytest(offscreen)

**Spec:** `docs/superpowers/specs/2026-05-30-track-mixer-design.md`

**Branch:** main

---

## File Map

```
新增:
  drama_shot_master/ui/widgets/daw/track_mix.py            # T1: TrackMixState + load/save
  drama_shot_master/ui/widgets/daw/track_header_column.py  # T3: TrackHeaderColumn
  tests/test_ui/daw/test_track_mix.py                       # T1
  tests/test_ui/test_video_preview_volume.py                # T2
  tests/test_ui/daw/test_track_header_column.py             # T3
  tests/test_ui/test_soundtrack_mix_wiring.py               # T5
改:
  drama_shot_master/ui/widgets/video_preview_widget.py     # T2: set_volume/set_muted
  drama_shot_master/ui/widgets/daw/daw_track_view.py       # T4: 导出常量 + 去画字标签
  drama_shot_master/ui/widgets/soundtrack_editor.py        # T5: header 列接线 + _apply_audio_state
```

---

## Task 1: TrackMixState + mix.json 持久化

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/track_mix.py`
- Test: `tests/test_ui/daw/test_track_mix.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/daw/test_track_mix.py`：

```python
"""TrackMixState：mute/solo/volume + 独奏解算 + mix.json 持久化。"""
from drama_shot_master.ui.widgets.daw.track_mix import (
    TrackMixState, load_mix, save_mix, TRACKS)


def test_tracks_are_three_audio_tracks():
    assert TRACKS == ("video", "bgm", "sfx")


def test_default_all_audible_full_volume():
    m = TrackMixState()
    for t in TRACKS:
        assert m.is_muted(t) is False
        assert m.is_soloed(t) is False
        assert m.volume(t) == 1.0
        assert m.audible(t) is True


def test_mute_makes_inaudible():
    m = TrackMixState()
    m.set_muted("bgm", True)
    assert m.audible("bgm") is False
    assert m.audible("video") is True


def test_solo_silences_others():
    m = TrackMixState()
    m.set_soloed("bgm", True)
    assert m.audible("bgm") is True
    assert m.audible("video") is False
    assert m.audible("sfx") is False


def test_multi_solo():
    m = TrackMixState()
    m.set_soloed("bgm", True)
    m.set_soloed("sfx", True)
    assert m.audible("bgm") is True and m.audible("sfx") is True
    assert m.audible("video") is False


def test_muted_solo_track_still_inaudible():
    m = TrackMixState()
    m.set_soloed("bgm", True)
    m.set_muted("bgm", True)
    assert m.audible("bgm") is False     # mute 优先


def test_volume_clamped():
    m = TrackMixState()
    m.set_volume("bgm", 2.0); assert m.volume("bgm") == 1.5
    m.set_volume("bgm", -1.0); assert m.volume("bgm") == 0.0


def test_effective_volume_zero_when_inaudible():
    m = TrackMixState()
    m.set_volume("bgm", 1.2)
    assert m.effective_volume("bgm") == 1.2
    m.set_muted("bgm", True)
    assert m.effective_volume("bgm") == 0.0


def test_to_from_dict_roundtrip():
    m = TrackMixState()
    m.set_muted("bgm", True); m.set_soloed("sfx", True); m.set_volume("video", 0.5)
    m2 = TrackMixState.from_dict(m.to_dict())
    assert m2.is_muted("bgm") and m2.is_soloed("sfx") and m2.volume("video") == 0.5


def test_save_load_roundtrip(tmp_path):
    m = TrackMixState(); m.set_muted("sfx", True); m.set_volume("bgm", 0.8)
    save_mix(tmp_path, m)
    m2 = load_mix(tmp_path)
    assert m2.is_muted("sfx") and m2.volume("bgm") == 0.8


def test_load_missing_returns_default(tmp_path):
    m = load_mix(tmp_path)               # 无 mix.json
    assert all(m.audible(t) for t in TRACKS)


def test_load_corrupt_returns_default(tmp_path):
    (tmp_path / "mix.json").write_text("{bad json", encoding="utf-8")
    m = load_mix(tmp_path)
    assert all(m.audible(t) for t in TRACKS)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/daw/test_track_mix.py -q`
Expected: FAIL — `ModuleNotFoundError: ... track_mix`

- [ ] **Step 3: 实现** — 新建 `drama_shot_master/ui/widgets/daw/track_mix.py`：

```python
"""三轨混音状态（原声/BGM/SFX）：mute/solo/volume + 独奏解算 + mix.json 持久化。

纯逻辑，无 Qt 依赖，可单测。dialogue 轨无独立音频，不在此管理。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

TRACKS = ("video", "bgm", "sfx")


@dataclass
class _TrackState:
    muted: bool = False
    soloed: bool = False
    volume: float = 1.0


class TrackMixState:
    def __init__(self):
        self._st = {t: _TrackState() for t in TRACKS}

    def set_muted(self, track: str, on: bool) -> None:
        self._st[track].muted = bool(on)

    def is_muted(self, track: str) -> bool:
        return self._st[track].muted

    def set_soloed(self, track: str, on: bool) -> None:
        self._st[track].soloed = bool(on)

    def is_soloed(self, track: str) -> bool:
        return self._st[track].soloed

    def set_volume(self, track: str, v: float) -> None:
        self._st[track].volume = max(0.0, min(1.5, float(v)))

    def volume(self, track: str) -> float:
        return self._st[track].volume

    def _any_solo(self) -> bool:
        return any(s.soloed for s in self._st.values())

    def audible(self, track: str) -> bool:
        s = self._st[track]
        if s.muted:
            return False
        if self._any_solo():
            return s.soloed
        return True

    def effective_volume(self, track: str) -> float:
        return self._st[track].volume if self.audible(track) else 0.0

    def to_dict(self) -> dict:
        return {t: {"muted": s.muted, "soloed": s.soloed, "volume": s.volume}
                for t, s in self._st.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "TrackMixState":
        m = cls()
        for t in TRACKS:
            e = (d or {}).get(t) or {}
            m._st[t] = _TrackState(
                muted=bool(e.get("muted", False)),
                soloed=bool(e.get("soloed", False)),
                volume=max(0.0, min(1.5, float(e.get("volume", 1.0)))))
        return m


def _mix_path(work_dir) -> Path:
    return Path(work_dir) / "mix.json"


def load_mix(work_dir) -> TrackMixState:
    p = _mix_path(work_dir)
    if not p.is_file():
        return TrackMixState()
    try:
        return TrackMixState.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return TrackMixState()


def save_mix(work_dir, state: TrackMixState) -> None:
    p = _mix_path(work_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                 encoding="utf-8")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/daw/test_track_mix.py -q`
Expected: PASS（12 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/track_mix.py tests/test_ui/daw/test_track_mix.py
git commit -m "feat(soundtrack): + TrackMixState 三轨混音状态 + 独奏解算 + mix.json

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: VideoPreviewWidget.set_volume / set_muted（原声轨控制）

**Files:**
- Modify: `drama_shot_master/ui/widgets/video_preview_widget.py`
- Test: `tests/test_ui/test_video_preview_volume.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_video_preview_volume.py`：

```python
"""VideoPreviewWidget.set_volume/set_muted：懒建前后都生效。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_set_volume_before_player_no_crash(app):
    w = VideoPreviewWidget()
    w.set_volume(0.5)             # player 未懒建
    assert w._pending_volume == 0.5


def test_set_muted_before_player_no_crash(app):
    w = VideoPreviewWidget()
    w.set_muted(True)
    assert w._pending_muted is True


def test_volume_applied_after_player_built(app, tmp_path):
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"x")
    w = VideoPreviewWidget()
    w.set_volume(0.3)
    w.set_muted(True)
    w.set_source(str(mp4))        # 触发懒建
    assert w._audio.volume() == pytest.approx(0.3, abs=0.01)
    assert w._audio.isMuted() is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_video_preview_volume.py -q`
Expected: FAIL — `AttributeError: ... 'set_volume'`/'_pending_volume'

- [ ] **Step 3: 实现**

在 `drama_shot_master/ui/widgets/video_preview_widget.py` 的 `__init__`，在 `self._loaded_source = None` 之后加：

```python
        self._pending_volume = None
        self._pending_muted = None
```

在 `_ensure_player` 里，建好 `self._audio` 之后（现有 `self._audio.setVolume(self.vol_slider.value() / 100.0)` 那行**之后**）加应用待定值：

```python
            if self._pending_volume is not None:
                self._audio.setVolume(self._pending_volume)
            if self._pending_muted is not None:
                self._audio.setMuted(self._pending_muted)
```

在 `duration` 方法附近（公开 API 区）加：

```python
    def set_volume(self, v: float) -> None:
        """设原声音量 0–1.5。player 未建则记录，建后应用。"""
        v = max(0.0, min(1.5, float(v)))
        self._pending_volume = v
        if self._audio is not None:
            self._audio.setVolume(v)

    def set_muted(self, on: bool) -> None:
        self._pending_muted = bool(on)
        if self._audio is not None:
            self._audio.setMuted(bool(on))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_video_preview_volume.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/video_preview_widget.py tests/test_ui/test_video_preview_volume.py
git commit -m "feat(preview): VideoPreviewWidget.set_volume/set_muted（原声轨混音控制）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: TrackHeaderColumn 控件列

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/track_header_column.py`
- Test: `tests/test_ui/daw/test_track_header_column.py`

依赖：DawTrackView 需先导出常量（见 Task 4），但 Task 3 用本地常量副本即可独立；为简单，TrackHeaderColumn 自带行高常量（与 DawTrackView 一致）。

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/daw/test_track_header_column.py`：

```python
"""TrackHeaderColumn：三轨 M/S/音量行 + dialogue 只读 + 信号 + set_state。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.track_mix import TrackMixState
from drama_shot_master.ui.widgets.daw.track_header_column import TrackHeaderColumn


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct_has_three_audio_rows(app):
    w = TrackHeaderColumn()
    for t in ("video", "bgm", "sfx"):
        assert t in w._rows                       # 三轨行
    assert "dialogue" not in w._rows              # 对白无控件行


def test_mute_button_emits(app):
    w = TrackHeaderColumn()
    got = []
    w.muteToggled.connect(lambda t, on: got.append((t, on)))
    w._rows["bgm"]["mute"].click()
    assert got == [("bgm", True)]


def test_solo_button_emits(app):
    w = TrackHeaderColumn()
    got = []
    w.soloToggled.connect(lambda t, on: got.append((t, on)))
    w._rows["sfx"]["solo"].click()
    assert got == [("sfx", True)]


def test_volume_slider_emits(app):
    w = TrackHeaderColumn()
    got = []
    w.volumeChanged.connect(lambda t, v: got.append((t, v)))
    w._rows["video"]["vol"].setValue(50)          # 0–150 → 0.5
    assert got and got[-1][0] == "video"
    assert abs(got[-1][1] - 0.5) < 1e-6


def test_set_state_reflects_mute_solo(app):
    w = TrackHeaderColumn()
    m = TrackMixState(); m.set_muted("bgm", True); m.set_soloed("sfx", True)
    w.set_state(m)
    assert w._rows["bgm"]["mute"].isChecked() is True
    assert w._rows["sfx"]["solo"].isChecked() is True
    assert w._rows["video"]["mute"].isChecked() is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/daw/test_track_header_column.py -q`
Expected: FAIL — `ModuleNotFoundError: ... track_header_column`

- [ ] **Step 3: 实现** — 新建 `drama_shot_master/ui/widgets/daw/track_header_column.py`：

```python
"""左侧轨道头控件列：原声/BGM/SFX 各一行 M/S/音量；对白只读占位。

行高/顺序与 DawTrackView 一致（垂直静态对齐）。
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
)

# 与 daw_track_view 一致
_AXIS_H = 14
_TRACK_H = {"video": 36, "bgm": 40, "sfx": 36, "dialogue": 36}
_TRACK_ORDER = ["video", "bgm", "sfx", "dialogue"]
_AUDIO_TRACKS = ["video", "bgm", "sfx"]
_GAP = 2
_NAMES = {"video": "原声", "bgm": "BGM", "sfx": "SFX", "dialogue": "对白"}

_MUTE_QSS = ("QPushButton{width:18px;border:1px solid #3d3d55;border-radius:3px;"
             "color:#a6adc8;font-size:10px;font-weight:700;}"
             "QPushButton:checked{background:#e05252;color:#fff;border-color:#e05252;}")
_SOLO_QSS = ("QPushButton{width:18px;border:1px solid #3d3d55;border-radius:3px;"
             "color:#a6adc8;font-size:10px;font-weight:700;}"
             "QPushButton:checked{background:#f9e2af;color:#1e1e2e;border-color:#f9e2af;}")


class TrackHeaderColumn(QWidget):
    muteToggled = Signal(str, bool)
    soloToggled = Signal(str, bool)
    volumeChanged = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(130)
        self._rows = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 0, 2, 0)
        root.setSpacing(_GAP)
        root.addSpacing(_AXIS_H)         # 对齐时间线轴
        for track in _TRACK_ORDER:
            row = QWidget()
            row.setFixedHeight(_TRACK_H[track])
            hl = QHBoxLayout(row)
            hl.setContentsMargins(2, 1, 2, 1)
            hl.setSpacing(3)
            name = QLabel(_NAMES[track])
            name.setStyleSheet("font-size:11px;color:#cdd6f4;")
            name.setFixedWidth(30)
            hl.addWidget(name)
            if track in _AUDIO_TRACKS:
                mute = QPushButton("M"); mute.setCheckable(True)
                mute.setFixedWidth(20); mute.setStyleSheet(_MUTE_QSS)
                mute.clicked.connect(
                    lambda checked, t=track: self.muteToggled.emit(t, checked))
                solo = QPushButton("S"); solo.setCheckable(True)
                solo.setFixedWidth(20); solo.setStyleSheet(_SOLO_QSS)
                solo.clicked.connect(
                    lambda checked, t=track: self.soloToggled.emit(t, checked))
                vol = QSlider(Qt.Horizontal)
                vol.setRange(0, 150); vol.setValue(100)
                vol.valueChanged.connect(
                    lambda v, t=track: self.volumeChanged.emit(t, v / 100.0))
                hl.addWidget(mute); hl.addWidget(solo); hl.addWidget(vol, 1)
                self._rows[track] = {"mute": mute, "solo": solo, "vol": vol}
            else:
                ro = QLabel("（只读）")
                ro.setStyleSheet("font-size:9px;color:#6c7086;")
                hl.addWidget(ro); hl.addStretch(1)
            root.addWidget(row)
        root.addStretch(1)

    def set_state(self, mix) -> None:
        for track, ctl in self._rows.items():
            ctl["mute"].setChecked(mix.is_muted(track))
            ctl["solo"].setChecked(mix.is_soloed(track))
            ctl["vol"].blockSignals(True)
            ctl["vol"].setValue(int(round(mix.volume(track) * 100)))
            ctl["vol"].blockSignals(False)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/daw/test_track_header_column.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/track_header_column.py tests/test_ui/daw/test_track_header_column.py
git commit -m "feat(soundtrack): + TrackHeaderColumn 左侧轨道头 M/S/音量控件列

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: DawTrackView 导出常量 + 去画字标签

**Files:**
- Modify: `drama_shot_master/ui/widgets/daw/daw_track_view.py`
- Test: `tests/test_ui/daw/test_daw_track_view_smoke.py`（既有，回归）

- [ ] **Step 1: 写失败测试** — 在 `tests/test_ui/daw/test_daw_track_view_smoke.py` 末尾追加：

```python
def test_exports_layout_constants():
    import drama_shot_master.ui.widgets.daw.daw_track_view as m
    assert m.TRACK_ORDER == ["video", "bgm", "sfx", "dialogue"]
    assert m.TRACK_H["bgm"] == 40
    assert m.AXIS_H == 14
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/daw/test_daw_track_view_smoke.py::test_exports_layout_constants -q`
Expected: FAIL — `AttributeError: ... 'TRACK_ORDER'`

- [ ] **Step 3: 导出常量 + 去标签文字**

在 `drama_shot_master/ui/widgets/daw/daw_track_view.py`，`_TRACK_Y = _build_track_y()` 之后加公开别名：

```python
# 供 TrackHeaderColumn 等外部对齐使用的公开常量别名
TRACK_ORDER = _TRACK_ORDER
TRACK_H = _TRACK_H
AXIS_H = _AXIS_H
LABEL_W = _LABEL_W
```

在 paintEvent 的轨道 lane 绘制循环里，**删除**画轨名的两行（保留 fillRect lane 背景）。原代码：

```python
        for track in _TRACK_ORDER:
            ty = _TRACK_Y[track]
            th = _TRACK_H[track]
            painter.fillRect(_LABEL_W, ty, w - _LABEL_W, th, QColor("#252525"))
            painter.setPen(QColor("#666666"))
            painter.drawText(2, ty, _LABEL_W - 4, th,
                             Qt.AlignVCenter | Qt.AlignLeft, track)
```

改为（去掉 setPen + drawText）：

```python
        for track in _TRACK_ORDER:
            ty = _TRACK_Y[track]
            th = _TRACK_H[track]
            painter.fillRect(_LABEL_W, ty, w - _LABEL_W, th, QColor("#252525"))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/daw/test_daw_track_view_smoke.py -q`
Expected: PASS（既有 smoke 全绿 + 新常量测试；去标签不影响点击坐标，_LABEL_W 不变）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/daw_track_view.py tests/test_ui/daw/test_daw_track_view_smoke.py
git commit -m "refactor(daw): DawTrackView 导出布局常量 + 去画字标签（移到 header 列）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: SoundtrackEditor 接线 header 列 + _apply_audio_state

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_soundtrack_mix_wiring.py`

先读 `_build_daw_main` 确认 `left_col`/`track_view` 构建与 `_apply_play_mode_tracks` 现状。

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_soundtrack_mix_wiring.py`：

```python
"""SoundtrackEditor 混音接线：header 列存在 + _apply_audio_state 解算 + 落盘。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _ed(tmp_path):
    mp4 = tmp_path / "raw.mp4"; mp4.write_bytes(b"x")
    return SoundtrackEditor({"id": "t1", "name": "t", "mp4": str(mp4),
                             "style": "x", "output_dir": str(tmp_path)},
                            _cfg(tmp_path), tmp_path)


def test_header_column_and_mix_exist(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._track_header is not None
    assert ed._mix is not None


def test_mute_bgm_disables_overlay_bgm_in_bgm_mode(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._play_mode = "bgm"
    calls = {}
    ed._overlay.set_enabled = lambda trk, on: calls.__setitem__(trk, on)
    ed._overlay.set_volume = lambda trk, v: None
    ed._video_preview.set_muted = lambda on: None
    ed._video_preview.set_volume = lambda v: None
    ed._mix.set_muted("bgm", True)
    ed._apply_audio_state()
    assert calls["bgm"] is False              # bgm 静音 → 不可听


def test_solo_video_silences_bgm(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._play_mode = "mix"
    vid = {}
    ov = {}
    ed._video_preview.set_muted = lambda on: vid.__setitem__("muted", on)
    ed._video_preview.set_volume = lambda v: None
    ed._overlay.set_enabled = lambda trk, on: ov.__setitem__(trk, on)
    ed._overlay.set_volume = lambda trk, v: None
    ed._mix.set_soloed("video", True)
    ed._apply_audio_state()
    assert vid["muted"] is False              # 原声 solo → 可听
    assert ov["bgm"] is False and ov["sfx"] is False   # 其余静音


def test_mute_toggle_persists_mix_json(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._on_mute_toggled("sfx", True)
    from drama_shot_master.ui.widgets.daw.track_mix import load_mix
    reloaded = load_mix(ed._work_dir())
    assert reloaded.is_muted("sfx") is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_mix_wiring.py -q`
Expected: FAIL — `AttributeError: ... '_track_header'`

- [ ] **Step 3: __init__ 建 mix + header**

在 `drama_shot_master/ui/widgets/soundtrack_editor.py` 的 `__init__`，`self._dir_worker = None` 之后加：

```python
        from drama_shot_master.ui.widgets.daw.track_mix import load_mix
        self._mix = load_mix(self._work_dir())
```

（`self._track_header` 在 `_build_daw_main` 建，见 Step 4。）

- [ ] **Step 4: _build_daw_main 插入 header 列**

在 `_build_daw_main` 里，找到 left_col 构建 track_view 的位置。当前是：

```python
        left_col.addWidget(self._track_view, 1)
        left_col.addWidget(self._scrollbar)
        left_col.addWidget(self._minimap)
```

把 `left_col.addWidget(self._track_view, 1)` 这行替换为 header + track_view 的 HBox：

```python
        from drama_shot_master.ui.widgets.daw.track_header_column import TrackHeaderColumn
        from PySide6.QtWidgets import QHBoxLayout as _QHBox, QWidget as _QW
        self._track_header = TrackHeaderColumn()
        self._track_header.muteToggled.connect(self._on_mute_toggled)
        self._track_header.soloToggled.connect(self._on_solo_toggled)
        self._track_header.volumeChanged.connect(self._on_volume_changed)
        self._track_header.set_state(self._mix)
        tv_row = _QHBox(); tv_row.setContentsMargins(0, 0, 0, 0); tv_row.setSpacing(0)
        tv_row.addWidget(self._track_header)
        tv_row.addWidget(self._track_view, 1)
        tv_row_w = _QW(); tv_row_w.setLayout(tv_row)
        left_col.addWidget(tv_row_w, 1)
```

- [ ] **Step 5: 加接线方法 + _apply_audio_state**

在 `_apply_play_mode_tracks` 附近加：

```python
    def _on_mute_toggled(self, track: str, on: bool):
        self._mix.set_muted(track, on); self._after_mix_change()

    def _on_solo_toggled(self, track: str, on: bool):
        self._mix.set_soloed(track, on); self._after_mix_change()

    def _on_volume_changed(self, track: str, v: float):
        self._mix.set_volume(track, v); self._after_mix_change()

    def _after_mix_change(self):
        self._track_header.set_state(self._mix)   # solo 改变影响其它轨高亮
        self._apply_audio_state()
        from drama_shot_master.ui.widgets.daw.track_mix import save_mix
        save_mix(self._work_dir(), self._mix)

    def _apply_audio_state(self):
        """把 play_mode + mix 合成每轨最终音频状态。"""
        if self._video_preview is not None:
            self._video_preview.set_muted(not self._mix.audible("video"))
            self._video_preview.set_volume(self._mix.volume("video"))
        for trk in ("bgm", "sfx"):
            mode_on = ((trk == "bgm" and self._play_mode in ("bgm", "mix"))
                       or (trk == "sfx" and self._play_mode == "mix"))
            self._overlay.set_enabled(trk, mode_on and self._mix.audible(trk))
            self._overlay.set_volume(trk, self._mix.volume(trk))
```

- [ ] **Step 6: _apply_play_mode_tracks 改走统一入口**

找到现有 `_apply_play_mode_tracks`：

```python
    def _apply_play_mode_tracks(self, mode: str) -> None:
        self._overlay.set_enabled("bgm", mode in ("bgm", "mix"))
        self._overlay.set_enabled("sfx", mode == "mix")
```

替换为（委托给 _apply_audio_state，确保 mix 与 mode 合成）：

```python
    def _apply_play_mode_tracks(self, mode: str) -> None:
        self._play_mode = mode
        self._apply_audio_state()
```

（注意：调用方 `_on_play_mode_changed` 已先设 `self._play_mode = mode` 再调本方法；此处再设一次幂等无害。）

- [ ] **Step 7: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_mix_wiring.py tests/test_ui/test_soundtrack_play_mode.py tests/test_ui/test_soundtrack_editor_daw_smoke.py -q`
Expected: PASS（4 新 wiring + play_mode + daw smoke 全绿）

- [ ] **Step 8: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py tests/test_ui/test_soundtrack_mix_wiring.py
git commit -m "feat(soundtrack): 接线 TrackHeaderColumn + _apply_audio_state（play_mode+mix 合成）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 全套回归

- [ ] **Step 1: 跑配乐 UI + DAW 全套**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_ui/daw/ tests/test_ui/test_track_mix.py \
  tests/test_ui/test_video_preview_volume.py \
  tests/test_ui/test_soundtrack_mix_wiring.py \
  tests/test_ui/test_soundtrack_play_mode.py tests/test_ui/test_overlay_audio.py \
  tests/test_ui/test_soundtrack_editor_daw_smoke.py \
  tests/test_ui/test_soundtrack_ai_wiring.py -q -p no:cacheprovider
```
Expected: 全绿

- [ ] **Step 2: 配乐 agent 未触碰确认**

Run: `python -m pytest tests/test_sound_track_agent/ -q -p no:cacheprovider`
Expected: 全绿（268 passed）

- [ ] **Step 3: 最终提交（若有零散修复）**

```bash
git add -A && git commit -m "test(soundtrack): 轨级混音子项目#2 全套回归绿

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review 记录

- **Spec 覆盖**：TrackMixState+持久化→T1；VideoPreview 音量→T2；TrackHeaderColumn→T3；DawTrackView 导出常量+去标签→T4；编辑器接线+_apply_audio_state→T5。✓
- **类型一致**：`TrackMixState`(set_muted/is_muted/set_soloed/is_soloed/set_volume/volume/audible/effective_volume/to_dict/from_dict) T1 定义、T3/T5 调用一致；`load_mix/save_mix(work_dir[,state])` T1 定义、T5 调用一致；`TrackHeaderColumn(muteToggled/soloToggled/volumeChanged/set_state/_rows)` T3 定义、T5 连接一致；`VideoPreviewWidget.set_volume/set_muted` T2 定义、T5 调用一致；`TRACK_ORDER/TRACK_H/AXIS_H` T4 导出、TrackHeaderColumn 用本地副本（一致值）。✓
- **无占位符**：所有步骤含完整代码。✓
- **既有 API**：`_apply_play_mode_tracks`、`_on_play_mode_changed`、`OverlayMixer.set_enabled/set_volume`、`_build_daw_main` 的 left_col 结构均现有（T5 Step4 基于现状改）。✓
- **风险点**：T5 Step4 假设 `left_col.addWidget(self._track_view, 1)` 这一行存在且独立；实现者须先读 `_build_daw_main` 确认（计划已注明）。
```
