# 配乐出片前试听 + 打开工作目录 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户出片前即可逐段试听 BGM/SFX 候选、整体叠加播放（视频原声+BGM+SFX），并能直接打开含 session.json 的工作目录载入任务。

**Architecture:** 视频为主时钟（VideoPreviewWidget 新增 playingChanged 信号），新增 OverlayMixer 管理 BGM/SFX 叠加音轨跟随主时钟同步（漂移>200ms 纠偏）；Inspector 候选行加 ▶/⏸ 本地试听；预览轨用 `build_accent_preview`/`assemble_sfx_track` 后台构建并按内容指纹缓存；SoundtrackPanel 加「打开」按钮反推任务字段。

**Tech Stack:** PySide6（QMediaPlayer/QAudioOutput/QObject/Signal/QFileDialog）、sound_track_agent.facade/mixdown、pytest（QT_QPA_PLATFORM=offscreen）

**Spec:** `docs/superpowers/specs/2026-05-30-soundtrack-preview-audition-design.md`

**Branch:** `main`（feat/sfx-phase4c 已合并）

---

## File Map

```
新增:
  drama_shot_master/ui/widgets/overlay_audio.py     # T2: OverlayMixer
  tests/test_ui/test_overlay_audio.py               # T2
  tests/test_ui/test_inspector_audition.py          # T3
  tests/test_ui/test_soundtrack_open_dir.py         # T4
  tests/test_ui/test_soundtrack_preview_fingerprint.py  # T5a

改:
  drama_shot_master/ui/widgets/video_preview_widget.py        # T1: playingChanged 信号
  drama_shot_master/ui/widgets/daw/inspector/bgm_inspector.py # T3: 候选 ▶
  drama_shot_master/ui/widgets/daw/inspector/sfx_inspector.py # T3: 候选 ▶
  drama_shot_master/ui/panels/soundtrack_panel.py             # T4: 打开按钮 + open_work_dir()
  drama_shot_master/ui/widgets/soundtrack_editor.py           # T5: 指纹+构建worker+模式映射+overlay 接线
  tests/test_ui/test_collapsible_task_bar.py                  # (不动，已是 main 上用户改造)
```

---

## Task 1: VideoPreviewWidget.playingChanged 信号

**Files:**
- Modify: `drama_shot_master/ui/widgets/video_preview_widget.py`
- Test: `tests/test_ui/test_video_preview_playing_signal.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_video_preview_playing_signal.py`：

```python
"""VideoPreviewWidget.playingChanged：播放状态变化时 emit bool。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_has_playing_changed_signal(app):
    assert hasattr(VideoPreviewWidget, "playingChanged")


def test_state_change_emits_playing_changed(app):
    w = VideoPreviewWidget()
    got = []
    w.playingChanged.connect(got.append)
    # 直接调状态回调（不依赖真实音视频后端）
    w._on_state_changed(None)   # 无 player → is_playing False
    assert got == [False]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_video_preview_playing_signal.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'playingChanged'`

- [ ] **Step 3: 加信号 + emit**

在 `drama_shot_master/ui/widgets/video_preview_widget.py` 的类信号区改：

```python
class VideoPreviewWidget(QWidget):
    positionChanged = Signal(float)   # 秒
    playingChanged = Signal(bool)     # 播放/暂停状态
    _SEEK_THROTTLE_MS = 33            # ~30Hz
```

改 `_on_state_changed`：

```python
    def _on_state_changed(self, _state):
        playing = self.is_playing()
        self.btn_play.setText("⏸" if playing else "▶")
        self.playingChanged.emit(playing)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_video_preview_playing_signal.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/video_preview_widget.py tests/test_ui/test_video_preview_playing_signal.py
git commit -m "feat(preview): VideoPreviewWidget.playingChanged 信号（叠加轨主时钟）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: OverlayMixer

**Files:**
- Create: `drama_shot_master/ui/widgets/overlay_audio.py`
- Test: `tests/test_ui/test_overlay_audio.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_overlay_audio.py`：

```python
"""OverlayMixer：叠加音轨状态机 + 漂移纠偏阈值。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overlay_audio import OverlayMixer


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_should_resync_threshold():
    assert OverlayMixer._should_resync(0.0, 0.3) is True     # 漂移 0.3s > 0.2
    assert OverlayMixer._should_resync(1.0, 1.1) is False    # 漂移 0.1s < 0.2


def test_set_track_and_enabled(app, tmp_path):
    wav = tmp_path / "bgm.wav"; wav.write_bytes(b"x")
    m = OverlayMixer()
    m.set_track("bgm", str(wav))
    assert m.track_path("bgm") == str(wav)
    assert m.is_enabled("bgm") is False          # 默认不启用
    m.set_enabled("bgm", True)
    assert m.is_enabled("bgm") is True


def test_set_track_none_clears(app):
    m = OverlayMixer()
    m.set_track("sfx", None)
    assert m.track_path("sfx") is None


def test_volume_clamped(app, tmp_path):
    wav = tmp_path / "b.wav"; wav.write_bytes(b"x")
    m = OverlayMixer()
    m.set_track("bgm", str(wav))
    m.set_volume("bgm", 2.0)
    assert m.volume("bgm") == 1.5                # clamp 上限 1.5
    m.set_volume("bgm", -1.0)
    assert m.volume("bgm") == 0.0


def test_play_pause_does_not_crash_without_tracks(app):
    m = OverlayMixer()
    m.play(); m.pause(); m.stop(); m.seek(1.0); m.sync(1.0)   # 无轨不崩
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_overlay_audio.py -q`
Expected: FAIL — `ModuleNotFoundError: ... overlay_audio`

- [ ] **Step 3: 实现 OverlayMixer**

新建 `drama_shot_master/ui/widgets/overlay_audio.py`：

```python
"""OverlayMixer：管理 N 条 audio-only 叠加轨，跟随主时钟（VideoPreviewWidget）。

每轨一个懒建的 QMediaPlayer+QAudioOutput。主时钟通过 sync(t) 驱动，
漂移 > _DRIFT_SEC 才 setPosition 纠偏，避免频繁 seek 卡顿。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QObject, QUrl


class _Track:
    def __init__(self):
        self.path: str | None = None
        self.enabled: bool = False
        self.volume: float = 1.0
        self.player = None       # QMediaPlayer（懒建）
        self.audio = None        # QAudioOutput

    def ensure_player(self, parent):
        if self.player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self.player = QMediaPlayer(parent)
            self.audio = QAudioOutput(parent)
            self.player.setAudioOutput(self.audio)
            self.audio.setVolume(self.volume)
        return self.player


class OverlayMixer(QObject):
    _DRIFT_SEC = 0.2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: dict[str, _Track] = {}

    @staticmethod
    def _should_resync(track_sec: float, master_sec: float) -> bool:
        return abs(float(track_sec) - float(master_sec)) > OverlayMixer._DRIFT_SEC

    def _track(self, name: str) -> _Track:
        t = self._tracks.get(name)
        if t is None:
            t = _Track()
            self._tracks[name] = t
        return t

    def set_track(self, name: str, path: str | None) -> None:
        t = self._track(name)
        if not path or not Path(str(path)).exists():
            t.path = None
            if t.player is not None:
                t.player.stop()
            return
        t.path = str(path)
        p = t.ensure_player(self)
        p.stop()
        p.setSource(QUrl.fromLocalFile(str(path)))

    def track_path(self, name: str) -> str | None:
        return self._track(name).path

    def set_enabled(self, name: str, on: bool) -> None:
        t = self._track(name)
        t.enabled = bool(on)
        if t.player is not None and t.audio is not None:
            t.audio.setMuted(not t.enabled)

    def is_enabled(self, name: str) -> bool:
        return self._track(name).enabled

    def set_volume(self, name: str, vol: float) -> None:
        v = max(0.0, min(1.5, float(vol)))
        t = self._track(name)
        t.volume = v
        if t.audio is not None:
            t.audio.setVolume(v)

    def volume(self, name: str) -> float:
        return self._track(name).volume

    def play(self) -> None:
        for t in self._tracks.values():
            if t.enabled and t.path and t.player is not None:
                t.player.play()

    def pause(self) -> None:
        for t in self._tracks.values():
            if t.player is not None:
                t.player.pause()

    def stop(self) -> None:
        for t in self._tracks.values():
            if t.player is not None:
                t.player.stop()

    def seek(self, t_sec: float) -> None:
        ms = max(0, int(round(float(t_sec) * 1000)))
        for t in self._tracks.values():
            if t.player is not None:
                t.player.setPosition(ms)

    def sync(self, t_sec: float) -> None:
        for t in self._tracks.values():
            if not (t.enabled and t.path and t.player is not None):
                continue
            cur = t.player.position() / 1000.0
            if self._should_resync(cur, t_sec):
                t.player.setPosition(max(0, int(round(t_sec * 1000))))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_overlay_audio.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/overlay_audio.py tests/test_ui/test_overlay_audio.py
git commit -m "feat(soundtrack): + OverlayMixer 叠加音轨（跟随主时钟，漂移>200ms纠偏）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Inspector 候选 ▶/⏸ 逐段试听

**Files:**
- Modify: `drama_shot_master/ui/widgets/daw/inspector/bgm_inspector.py`
- Modify: `drama_shot_master/ui/widgets/daw/inspector/sfx_inspector.py`
- Test: `tests/test_ui/test_inspector_audition.py`

说明：两个 Inspector 用同一套试听逻辑，抽到一个 mixin 避免重复。

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_inspector_audition.py`：

```python
"""Inspector 候选 ▶ 试听：每候选有播放按钮，点击切 ⏸ 并播放该候选 path。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
from drama_shot_master.ui.widgets.daw.selection import _CueRef


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_bgm_inspector_has_play_button_per_candidate(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector import BgmInspector
    mp3 = tmp_path / "a.mp3"; mp3.write_bytes(b"x")
    bgm = ScoringSession(source_mp4="", source_hash="", global_style="x",
                         frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0,
                             candidates=[BGMCandidate(path=str(mp3), seed=1, prompt="p")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    assert len(w._play_buttons) == 1
    assert w._play_buttons[0].text() == "▶"


def test_bgm_play_button_toggles_and_plays(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector import BgmInspector
    mp3 = tmp_path / "a.mp3"; mp3.write_bytes(b"x")
    bgm = ScoringSession(source_mp4="", source_hash="", global_style="x",
                         frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0,
                             candidates=[BGMCandidate(path=str(mp3), seed=1, prompt="p")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    played = []
    w._audition.set_track = lambda name, path: played.append(path)  # 截获
    w._audition.play = lambda: played.append("PLAY")
    w._play_buttons[0].click()
    assert str(mp3) in played and "PLAY" in played
    assert w._play_buttons[0].text() == "⏸"


def test_bgm_missing_file_disables_button(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector import BgmInspector
    bgm = ScoringSession(source_mp4="", source_hash="", global_style="x",
                         frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0,
                             candidates=[BGMCandidate(path="/no/such.mp3", seed=1, prompt="p")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    assert w._play_buttons[0].isEnabled() is False


def test_sfx_inspector_has_play_button_per_candidate(app, tmp_path):
    from drama_shot_master.ui.widgets.daw.inspector.sfx_inspector import SfxInspector
    mp3 = tmp_path / "s.mp3"; mp3.write_bytes(b"x")
    sfx = SFXSession(source_mp4="", source_hash="", frame_rate=24.0,
                     shots=[SFXShot(0, 0.0, 3.0, duration=3.0, prompt_short="门",
                            candidates=[SFXCandidate(path=str(mp3), seed=1, prompt="p")],
                            chosen_candidate=0)])
    w = SfxInspector()
    w.set_cue_ref(_CueRef("sfx", 0), sfx)
    assert len(w._play_buttons) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_inspector_audition.py -q`
Expected: FAIL — `AttributeError: ... '_play_buttons'`

- [ ] **Step 3: 实现试听 mixin** — 新建 `drama_shot_master/ui/widgets/daw/inspector/_audition.py`：

```python
"""候选试听 mixin：候选行加 ▶/⏸ 按钮，本地 Overlay 单轨播放。"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QPushButton


class CandidateAuditionMixin:
    """需宿主在 __init__ 调 self._init_audition()，并在重建候选时调
    self._reset_audition()，每候选用 self._make_play_button(path) 取按钮。"""

    def _init_audition(self):
        from drama_shot_master.ui.widgets.overlay_audio import OverlayMixer
        self._audition = OverlayMixer(self)
        self._play_buttons: list[QPushButton] = []
        self._playing_idx: int | None = None

    def _reset_audition(self):
        self._audition.stop()
        self._playing_idx = None
        self._play_buttons = []

    def _make_play_button(self, idx: int, path: str) -> QPushButton:
        btn = QPushButton("▶")
        btn.setMaximumWidth(28)
        exists = bool(path) and Path(str(path)).exists()
        btn.setEnabled(exists)
        if not exists:
            btn.setToolTip("候选文件缺失")
        btn.clicked.connect(lambda _=False, i=idx, p=path: self._on_audition(i, p))
        self._play_buttons.append(btn)
        return btn

    def _on_audition(self, idx: int, path: str):
        if self._playing_idx == idx:
            # 再点 → 停
            self._audition.pause()
            self._set_btn(idx, "▶")
            self._playing_idx = None
            return
        # 停上一个，播这个
        if self._playing_idx is not None:
            self._set_btn(self._playing_idx, "▶")
        self._audition.set_track("audition", path)
        self._audition.set_enabled("audition", True)
        self._audition.seek(0.0)
        self._audition.play()
        self._set_btn(idx, "⏸")
        self._playing_idx = idx

    def _set_btn(self, idx: int, text: str):
        if 0 <= idx < len(self._play_buttons):
            self._play_buttons[idx].setText(text)
```

- [ ] **Step 4: 接入 BgmInspector** — 改 `drama_shot_master/ui/widgets/daw/inspector/bgm_inspector.py`：

类声明加 mixin + import：

```python
from drama_shot_master.ui.widgets.daw.inspector._audition import CandidateAuditionMixin


class BgmInspector(CandidateAuditionMixin, QWidget):
```

`__init__` 末尾（`self._build_ui()` 之后）加：

```python
        self._init_audition()
```

`set_cue_ref` 里候选构建段——把原来的：

```python
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
```

替换为（候选行 = radio + ▶，并复位试听）：

```python
        for btn in list(self.cand_group.buttons()):
            self.cand_group.removeButton(btn)
            btn.deleteLater()
        while self.cand_layout.count():
            item = self.cand_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._reset_audition()
        from PySide6.QtWidgets import QHBoxLayout, QWidget as _QW
        for i, c in enumerate(seg.candidates):
            row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
            rb = QRadioButton(f"seed={c.seed}")
            self.cand_group.addButton(rb, i)
            if i == seg.chosen_candidate:
                rb.setChecked(True)
            rb.toggled.connect(
                lambda checked, idx=i:
                    checked and self._ref
                    and self.candidateChosen.emit(self._ref, idx))
            row.addWidget(rb, 1)
            row.addWidget(self._make_play_button(i, c.path))
            holder = _QW(); holder.setLayout(row)
            self.cand_layout.addWidget(holder)
```

- [ ] **Step 5: 接入 SfxInspector** — 改 `drama_shot_master/ui/widgets/daw/inspector/sfx_inspector.py`，同 Step 4：

类声明：

```python
from drama_shot_master.ui.widgets.daw.inspector._audition import CandidateAuditionMixin


class SfxInspector(CandidateAuditionMixin, QWidget):
```

`__init__` 的 `self._build_ui()` 之后加 `self._init_audition()`。

`set_cue_ref` 候选段（操作对象是 `shot.candidates` / `shot.chosen_candidate`）替换为与 BgmInspector 同结构：

```python
        for btn in list(self.cand_group.buttons()):
            self.cand_group.removeButton(btn)
            btn.deleteLater()
        while self.cand_layout.count():
            item = self.cand_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._reset_audition()
        from PySide6.QtWidgets import QHBoxLayout, QWidget as _QW
        for i, c in enumerate(shot.candidates):
            row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
            rb = QRadioButton(f"seed={c.seed}")
            self.cand_group.addButton(rb, i)
            if i == shot.chosen_candidate:
                rb.setChecked(True)
            rb.toggled.connect(
                lambda checked, idx=i:
                    checked and self._ref
                    and self.candidateChosen.emit(self._ref, idx))
            row.addWidget(rb, 1)
            row.addWidget(self._make_play_button(i, c.path))
            holder = _QW(); holder.setLayout(row)
            self.cand_layout.addWidget(holder)
```

- [ ] **Step 6: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_inspector_audition.py tests/test_ui/daw/test_inspector_smoke.py -q`
Expected: PASS（4 新 + 既有 inspector smoke 全绿）

- [ ] **Step 7: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/inspector/_audition.py \
        drama_shot_master/ui/widgets/daw/inspector/bgm_inspector.py \
        drama_shot_master/ui/widgets/daw/inspector/sfx_inspector.py \
        tests/test_ui/test_inspector_audition.py
git commit -m "feat(soundtrack): Inspector 候选 ▶/⏸ 逐段试听

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: SoundtrackPanel「打开」工作目录

**Files:**
- Modify: `drama_shot_master/ui/panels/soundtrack_panel.py`
- Test: `tests/test_ui/test_soundtrack_open_dir.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_soundtrack_open_dir.py`：

```python
"""SoundtrackPanel.open_work_dir：含 session.json 的目录 → 反推任务字段。"""
import os, json
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    def __init__(self):
        self.soundtrack_tasks = []
        self.soundtrack_status_colors = {}


def _panel(app):
    return SoundtrackPanel(state=None, cfg=_Cfg(),
                           open_window_cb=None, persist_cb=lambda: None)


def _make_workdir(tmp_path):
    proj = tmp_path / "02_女剑客归山"
    wd = proj / "17797915850335bf1e"
    wd.mkdir(parents=True)
    (wd / "session.json").write_text(json.dumps({
        "source_mp4": str(proj / "vedio" / "x.mp4"),
        "global_style": "末日",
        "output": str(wd / "scored.mp4"),
    }), encoding="utf-8")
    return wd


def test_open_valid_workdir_appends_task(app, tmp_path):
    p = _panel(app)
    wd = _make_workdir(tmp_path)
    ok = p.open_work_dir(str(wd))
    assert ok is True
    tasks = p._tasks()
    assert len(tasks) == 1
    t = tasks[0]
    assert t["id"] == "17797915850335bf1e"
    assert t["output_dir"] == str(wd.parent)
    assert t["name"] == "02_女剑客归山"
    assert t["mp4"] == str(wd.parent / "vedio" / "x.mp4")
    assert t["style"] == "末日"


def test_open_invalid_dir_returns_false(app, tmp_path):
    p = _panel(app)
    empty = tmp_path / "empty"; empty.mkdir()
    assert p.open_work_dir(str(empty)) is False
    assert p._tasks() == []


def test_open_duplicate_id_no_double_add(app, tmp_path):
    p = _panel(app)
    wd = _make_workdir(tmp_path)
    p.open_work_dir(str(wd))
    p.open_work_dir(str(wd))
    assert len(p._tasks()) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_open_dir.py -q`
Expected: FAIL — `AttributeError: ... 'open_work_dir'`

- [ ] **Step 3: 加「打开」按钮 + open_work_dir()**

改 `drama_shot_master/ui/panels/soundtrack_panel.py`。

`_build_ui` 的按钮栏（现有 `self.btn_new` / `self.btn_del`）之间加：

```python
        self.btn_new = QPushButton("新建")
        self.btn_open = QPushButton("打开")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_del):
            bar.addWidget(b)
```

`_build_ui` 末尾按钮接线处加：

```python
        self.btn_open.clicked.connect(self._on_open)
```

新增方法（放在 `_on_new` 附近）：

```python
    def _on_open(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "打开配乐工作目录（含 session.json）")
        if d:
            if not self.open_work_dir(d):
                QMessageBox.warning(self, "打开失败",
                                    "该目录不是有效的配乐工作目录（缺 session.json）")

    def open_work_dir(self, work_dir: str) -> bool:
        """载入含 session.json 的工作目录为任务。成功 True，无效 False。"""
        import json
        from pathlib import Path
        wd = Path(work_dir)
        sj = wd / "session.json"
        if not sj.is_file():
            return False
        try:
            sess = json.loads(sj.read_text(encoding="utf-8"))
        except Exception:
            return False
        tid = wd.name
        if any(t.get("id") == tid for t in self._tasks()):
            self.refresh(); self._select_task(tid)
            return True
        task = {
            "id": tid,
            "name": wd.parent.name or tid,
            "mp4": sess.get("source_mp4", "") or "",
            "style": sess.get("global_style", "") or "",
            "workflow_id": "",
            "status": "完成" if sess.get("output") else "空闲",
            "output": sess.get("output", "") or "",
            "output_dir": str(wd.parent),
        }
        self._tasks().append(task)
        self._persist_cb()
        self.refresh()
        self._select_task(tid)
        return True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_open_dir.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/panels/soundtrack_panel.py tests/test_ui/test_soundtrack_open_dir.py
git commit -m "feat(soundtrack): 配乐面板「打开」载入工作目录（反推任务字段）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5a: SoundtrackEditor 预览指纹（纯函数）

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_soundtrack_preview_fingerprint.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_soundtrack_preview_fingerprint.py`：

```python
"""SoundtrackEditor 预览轨指纹：影响产物的字段变化 → 指纹变。"""
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


def test_bgm_fingerprint_changes_with_chosen(tmp_path):
    _app()
    from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="x",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0,
            candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="p"),
                        BGMCandidate(path="/b.mp3", seed=2, prompt="p")],
            chosen_candidate=0)])
    fp1 = ed._preview_fingerprint("bgm")
    ed._session.segments[0].chosen_candidate = 1
    fp2 = ed._preview_fingerprint("bgm")
    assert fp1 != fp2


def test_bgm_fingerprint_stable_when_unchanged(tmp_path):
    _app()
    from sound_track_agent.session import ScoringSession, SegmentScore
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="x",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0)])
    assert ed._preview_fingerprint("bgm") == ed._preview_fingerprint("bgm")


def test_sfx_fingerprint_changes_with_enabled(tmp_path):
    _app()
    from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
    ed = _ed(tmp_path)
    ed._sfx_session = SFXSession(source_mp4="", source_hash="", frame_rate=24.0,
        shots=[SFXShot(0, 0.0, 3.0, duration=3.0,
            candidates=[SFXCandidate(path="/s.mp3", seed=1, prompt="p")],
            chosen_candidate=0, enabled=True)])
    fp1 = ed._preview_fingerprint("sfx")
    ed._sfx_session.shots[0].enabled = False
    fp2 = ed._preview_fingerprint("sfx")
    assert fp1 != fp2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_preview_fingerprint.py -q`
Expected: FAIL — `AttributeError: ... '_preview_fingerprint'`

- [ ] **Step 3: 实现 _preview_fingerprint**

在 `drama_shot_master/ui/widgets/soundtrack_editor.py` 加方法（放在 `_resolve_video_source` 附近）：

```python
    def _preview_fingerprint(self, kind: str) -> str:
        """预览轨内容指纹：影响 build 产物的字段变 → 指纹变 → 触发重建。"""
        import hashlib, json
        if kind == "bgm":
            sess = self._session
            if sess is None:
                return ""
            data = {
                "segs": [(getattr(s, "chosen_candidate", None),
                          float(getattr(s, "volume", 1.0)))
                         for s in sess.segments],
                "accents": list(getattr(sess, "accent_points", []) or []),
                "accent_on": bool(getattr(sess, "accent_mix_enabled", True)),
                "pump": float(getattr(sess, "pump_strength", 0.6)),
            }
        else:  # sfx
            sess = self._sfx_session
            if sess is None:
                return ""
            data = {"shots": [
                (bool(getattr(s, "enabled", True)),
                 getattr(s, "chosen_candidate", None),
                 float(getattr(s, "volume", 1.0)),
                 (s.candidates[s.chosen_candidate].path
                  if s.chosen_candidate is not None
                  and 0 <= s.chosen_candidate < len(s.candidates) else None))
                for s in sess.shots]}
        blob = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return hashlib.blake2b(blob.encode("utf-8"), digest_size=8).hexdigest()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_preview_fingerprint.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py tests/test_ui/test_soundtrack_preview_fingerprint.py
git commit -m "feat(soundtrack): + _preview_fingerprint 预览轨内容指纹

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5b: SoundtrackEditor 叠加播放接线 + 模式映射

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_soundtrack_play_mode.py`（适配）

- [ ] **Step 1: 改写播放模式测试** — 替换 `tests/test_ui/test_soundtrack_play_mode.py` 全文：

```python
"""SoundtrackEditor 叠加播放模式：原声/配乐/混音 → OverlayMixer enable 映射。"""
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


def test_has_overlay_mixer(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._overlay is not None


def test_raw_mode_disables_overlays(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._apply_play_mode_tracks("raw")
    assert ed._overlay.is_enabled("bgm") is False
    assert ed._overlay.is_enabled("sfx") is False


def test_bgm_mode_enables_bgm_only(tmp_path):
    _app()
    ed = _ed(tmp_path)
    # 伪造已构建好的 bgm 轨
    ed._overlay.set_track("bgm", str(tmp_path / "raw.mp4"))
    ed._apply_play_mode_tracks("bgm")
    assert ed._overlay.is_enabled("bgm") is True
    assert ed._overlay.is_enabled("sfx") is False


def test_mix_mode_enables_both(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._overlay.set_track("bgm", str(tmp_path / "raw.mp4"))
    ed._overlay.set_track("sfx", str(tmp_path / "raw.mp4"))
    ed._apply_play_mode_tracks("mix")
    assert ed._overlay.is_enabled("bgm") is True
    assert ed._overlay.is_enabled("sfx") is True


def test_raw_mode_video_source_is_original_mp4(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._play_mode = "raw"
    assert ed._resolve_video_source() == ed._task["mp4"]


def test_scored_mp4_helper_prefers_session_then_task(tmp_path):
    _app()
    sess_out = tmp_path / "s.mp4"; sess_out.write_bytes(b"v")
    ed = _ed(tmp_path)
    ed._session = type("S", (), {"output": str(sess_out)})()
    assert ed._scored_mp4() == str(sess_out)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_play_mode.py -q`
Expected: FAIL — `AttributeError: ... '_overlay'` / `_apply_play_mode_tracks`

- [ ] **Step 3: __init__ 加 OverlayMixer + 接线**

`drama_shot_master/ui/widgets/soundtrack_editor.py` 的 `__init__`，在 `self._play_mode = "raw"` 之后加：

```python
        from drama_shot_master.ui.widgets.overlay_audio import OverlayMixer
        self._overlay = OverlayMixer(self)
        self._preview_fp = {"bgm": None, "sfx": None}   # 已构建轨的指纹
        self._preview_worker = None
```

`_build_ui` 里 video_preview 接线处（现有 `self._video_preview.positionChanged.connect(self._on_video_position_changed)`）后加：

```python
        self._video_preview.playingChanged.connect(self._on_video_playing_changed)
```

- [ ] **Step 4: 实现 _apply_play_mode_tracks + 同步回调 + 重构 _on_play_mode_changed**

把现有 `_on_play_mode_changed` / `_resolve_video_source` 段替换为：

```python
    def _on_play_mode_changed(self, mode: str) -> None:
        self._play_mode = mode
        # 视频源始终用原始 mp4（保留画面+原声），配乐/混音靠叠加轨
        src = self._resolve_video_source()
        if src and self._video_preview:
            self._video_preview.set_source(src)
        if mode == "raw":
            self._apply_play_mode_tracks("raw")
            self.progress_label.setText("")
            return
        # 配乐/混音：确保预览轨已构建（指纹缓存），再 enable
        self._ensure_preview_tracks(mode)

    def _apply_play_mode_tracks(self, mode: str) -> None:
        self._overlay.set_enabled("bgm", mode in ("bgm", "mix"))
        self._overlay.set_enabled("sfx", mode == "mix")

    def _ensure_preview_tracks(self, mode: str) -> None:
        """按需后台构建 BGM/(SFX) 预览轨；指纹未变则直接启用。"""
        if self._session is None:
            self.progress_label.setText("尚无 BGM 候选，请先「开始配乐」生成。")
            return
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return
        need_sfx = (mode == "mix")
        bgm_fp = self._preview_fingerprint("bgm")
        sfx_fp = self._preview_fingerprint("sfx") if need_sfx else None
        bgm_ready = (self._preview_fp["bgm"] == bgm_fp
                     and self._overlay.track_path("bgm"))
        sfx_ready = (not need_sfx) or (self._preview_fp["sfx"] == sfx_fp
                                       and self._overlay.track_path("sfx"))
        if bgm_ready and sfx_ready:
            self._apply_play_mode_tracks(mode)
            self.progress_label.setText("")
            return

        work_dir = self._work_dir()
        sess = self._session
        sfx_sess = self._sfx_session

        def task():
            from sound_track_agent import facade
            from sound_track_agent.mixdown import assemble_sfx_track
            bgm_wav = facade.build_accent_preview(sess, work_dir)
            sfx_wav = None
            if need_sfx and sfx_sess is not None:
                sfx_wav = assemble_sfx_track(
                    sfx_sess.shots, work_dir / "sfx_track.wav")
            return {"bgm": str(bgm_wav) if bgm_wav else None,
                    "sfx": str(sfx_wav) if sfx_wav else None,
                    "bgm_fp": bgm_fp, "sfx_fp": sfx_fp, "mode": mode}

        self.progress_label.setText("正在生成配乐预览…")
        self._preview_worker = FunctionWorker(task)
        self._preview_worker.finished_with_result.connect(self._on_preview_built)
        self._preview_worker.failed.connect(
            lambda err: self.progress_label.setText(f"配乐预览生成失败：{err}"))
        self._preview_worker.start()

    def _on_preview_built(self, res: dict):
        if res.get("bgm"):
            self._overlay.set_track("bgm", res["bgm"])
            self._preview_fp["bgm"] = res["bgm_fp"]
        if res.get("sfx"):
            self._overlay.set_track("sfx", res["sfx"])
            self._preview_fp["sfx"] = res["sfx_fp"]
        self._apply_play_mode_tracks(res.get("mode", self._play_mode))
        # 与当前视频位置对齐后按播放态联动
        if self._video_preview is not None:
            self._overlay.seek(0.0)
            if self._video_preview.is_playing():
                self._overlay.play()
        self.progress_label.setText("")

    def _on_video_playing_changed(self, playing: bool) -> None:
        if playing:
            self._overlay.play()
        else:
            self._overlay.pause()

    def _scored_mp4(self):
        """已生成的 scored MP4：session.output 优先，回退 task['output']。供「预览成片」用。"""
        if self._session is not None:
            out = getattr(self._session, "output", None)
            if out and Path(out).exists():
                return out
        task_out = (self._task.get("output") or "").strip()
        if task_out and Path(task_out).exists():
            return task_out
        return None

    def _resolve_video_source(self):
        """叠加预览：所有模式都用原始 mp4（保留画面+原声）。"""
        mp4 = (self._task.get("mp4") or "").strip()
        return mp4 if mp4 and Path(mp4).exists() else None
```

在 `_on_video_position_changed` 末尾加叠加轨同步：

```python
    def _on_video_position_changed(self, t: float):
        if self._overview_timeline is not None:
            self._overview_timeline.set_playhead(t)
        if self._daw_toolbar is not None:
            total = self._track_view._duration if self._track_view else 0
            self._daw_toolbar.set_time(t, total)
        self._overlay.sync(t)
```

在 `_on_track_playhead_dragged` 与 `_on_overview_playhead_dragged` 内 `seek` 后加 `self._overlay.seek(t)`：

```python
    def _on_track_playhead_dragged(self, t: float):
        if self._video_preview:
            self._video_preview.seek(t)
        self._overlay.seek(t)
```
```python
    def _on_overview_playhead_dragged(self, t: float):
        if self._video_preview is not None:
            self._video_preview.seek(t)
        self._overlay.seek(t)
```

删除上一轮遗留的 `_PLAY_MODE_HINTS` 字典（已不再静默回退、改为叠加；若存在则移除其定义与引用）。

- [ ] **Step 5: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_play_mode.py tests/test_ui/test_soundtrack_editor_daw_smoke.py -q`
Expected: PASS（6 新 play_mode + 既有 daw smoke 全绿）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py tests/test_ui/test_soundtrack_play_mode.py
git commit -m "feat(soundtrack): 出片前叠加播放（原声+BGM+SFX，指纹缓存预览轨）

- 视频为主时钟，OverlayMixer 跟随 positionChanged/playingChanged
- 配乐/混音模式后台构建 build_accent_preview/assemble_sfx_track 并缓存
- _resolve_video_source 改为始终原始 mp4；scored 留给「预览成片」

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 全套回归

- [ ] **Step 1: 跑配乐 + DAW + Inspector 相关测试**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_ui/test_overlay_audio.py \
  tests/test_ui/test_inspector_audition.py \
  tests/test_ui/test_soundtrack_open_dir.py \
  tests/test_ui/test_soundtrack_preview_fingerprint.py \
  tests/test_ui/test_soundtrack_play_mode.py \
  tests/test_ui/test_video_preview_playing_signal.py \
  tests/test_ui/daw/ tests/test_ui/test_soundtrack_editor_daw_smoke.py -q
```
Expected: 全绿

- [ ] **Step 2: 跑 SFX agent 回归（确认未触碰）**

Run: `python -m pytest tests/test_sound_track_agent/ -q -p no:cacheprovider`
Expected: 全绿

- [ ] **Step 3: 最终提交（若有零散修复）**

```bash
git add -A && git commit -m "test(soundtrack): 出片前试听 + 打开目录 全套回归绿

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review 记录

- **Spec 覆盖**：1a→T3；1b→T1+T2+T5a+T5b；2→T4。✓ 全覆盖。
- **类型一致**：OverlayMixer 方法名 `set_track/set_enabled/set_volume/is_enabled/track_path/volume/play/pause/stop/seek/sync/_should_resync` 在 T2 定义、T3/T5b 调用一致；`_preview_fingerprint(kind)` T5a 定义、T5b 调用一致；`playingChanged` T1 定义、T5b 连接一致。✓
- **无占位符**：所有代码步骤含完整代码。✓
- **既有契约**：`build_accent_preview(session, work_dir)`、`assemble_sfx_track(shots, out_path)`（返回 Path 或 None）、`FunctionWorker(task).finished_with_result/failed` 均为现有 API。✓
```
