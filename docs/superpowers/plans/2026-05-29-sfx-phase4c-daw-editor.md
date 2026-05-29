# Phase 4c DAW 多轨编辑器 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SoundtrackEditor 主区从 "4 tab + 卡片" 改成 DAW 多轨时间轴 + Inspector + 撤销栈，体感对齐 Premiere/CapCut。

**Architecture:** 新建 `drama_shot_master/ui/widgets/daw/` 子包（7 文件），含 Selection / UndoStack / 7 Command 类 / DawTrackView 自绘 painted widget / DawMinimap / DawToolbar / 4 Inspector 模板。零后端改动；BGM/SFX session 仅加 `user_edited: bool=False` 标记字段。SoundtrackEditor `_build_ui` 大改：删 4 tab 体系，加 DAW 主区 + 右 Inspector + 弹窗 ConfigDialog/PromptEditDialog。

**Tech Stack:** PySide6 (QPainter / QMouseEvent / QShortcut / QScrollBar / QDialog / QTimer) / Python dataclasses Command 模式

**Spec:** `docs/superpowers/specs/2026-05-29-soundtrack-phase4c-daw-editor-design.md`

**Branch:** `feat/sfx-phase4c`（T0 开）

---

## File Map

```
drama_shot_master/ui/widgets/daw/                # NEW 子包
├── __init__.py                                   # T1
├── selection.py                                  # T2: _CueRef + Selection
├── undo_stack.py                                 # T3: UndoStack
├── commands.py                                   # T4a/T4b/T4c: 7 Command 类
├── daw_track_view.py                             # T5: 自绘主时间轴
├── daw_minimap.py                                # T6: 3 轨 minimap
├── daw_toolbar.py                                # T7: 工具栏
└── inspector/                                    # T8a/T8b
    ├── __init__.py
    ├── empty_inspector.py
    ├── dialogue_inspector.py
    ├── bgm_inspector.py
    └── sfx_inspector.py

drama_shot_master/ui/dialogs/                    # T9
├── config_dialog.py                              # mp4/风格/输出
└── prompt_edit_dialog.py                         # BGM/SFX prompt 编辑

drama_shot_master/ui/widgets/soundtrack_editor.py # T10: 大改
sound_track_agent/session.py                      # T1: SegmentScore + user_edited
sound_track_agent/sfx/session.py                  # T1: SFXShot + user_edited
```

---

### Task 0: 开 feat/sfx-phase4c 分支

- [ ] **Step 0.1: 从 main 开新分支**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
git branch --show-current     # 应在 main 或 feat/sfx-phase4b
git checkout main             # 确保从 main 出发（main 已含 4a 全部 + 4b T1-T3）
git checkout -b feat/sfx-phase4c
git branch --show-current     # feat/sfx-phase4c
```

后续所有 commit 必须落在 `feat/sfx-phase4c`，每 task 开始前 implementer 验证。

---

### Task 1: session 加 user_edited 字段 + sfx 子包骨架

**Files:**
- Modify: `sound_track_agent/session.py`（SegmentScore 加 user_edited）
- Modify: `sound_track_agent/sfx/session.py`（SFXShot 加 user_edited）
- Create: `drama_shot_master/ui/widgets/daw/__init__.py`（空）
- Create: `drama_shot_master/ui/widgets/daw/inspector/__init__.py`（空）
- Test: `tests/test_sound_track_agent/test_user_edited_field.py`

- [ ] **Step 1.1: 写失败测试** — 新建 `tests/test_sound_track_agent/test_user_edited_field.py`：

```python
"""SegmentScore + SFXShot 加 user_edited: bool = False 字段（4c 标记）。"""
from sound_track_agent.session import SegmentScore
from sound_track_agent.sfx.session import SFXShot


def test_segment_score_has_user_edited_default_false():
    seg = SegmentScore(0, 0.0, 5.0)
    assert seg.user_edited is False


def test_sfx_shot_has_user_edited_default_false():
    shot = SFXShot(0, 0.0, 3.0)
    assert shot.user_edited is False


def test_segment_score_roundtrip_preserves_user_edited(tmp_path):
    """from_dict 应当能读 user_edited 字段（旧 JSON 无此字段 → 默认 False）。"""
    from sound_track_agent.session import ScoringSession
    sess = ScoringSession(source_mp4="/a.mp4", source_hash="h",
                          global_style="x", frame_rate=24.0,
                          segments=[SegmentScore(0, 0.0, 5.0, user_edited=True)])
    p = tmp_path / "session.json"
    sess.save(p)
    loaded = ScoringSession.load(p)
    assert loaded is not None
    assert loaded.segments[0].user_edited is True


def test_sfx_shot_roundtrip_preserves_user_edited(tmp_path):
    from sound_track_agent.sfx.session import SFXSession
    sess = SFXSession(source_mp4="/a.mp4", source_hash="h", frame_rate=24.0,
                      shots=[SFXShot(0, 0.0, 3.0, user_edited=True)])
    p = tmp_path / "sfx_session.json"
    sess.save(p)
    loaded = SFXSession.load(p)
    assert loaded is not None
    assert loaded.shots[0].user_edited is True
```

- [ ] **Step 1.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_sound_track_agent/test_user_edited_field.py -q
```
Expected: 4 FAILED（TypeError: __init__ 不接受 user_edited）

- [ ] **Step 1.3: 加 SegmentScore.user_edited**

打开 `sound_track_agent/session.py`，找到 `SegmentScore` dataclass，在合适位置（其它带默认值的字段末尾）加：

```python
    user_edited: bool = False        # 4c: 用户在 DAW 里手动改过 t_start/t_end/prompt 时设 True
```

如果 SegmentScore 有 `from_dict` 方法（spec §3.x 提到），在其中加：

```python
            user_edited=bool(d.get("user_edited", False)),
```

- [ ] **Step 1.4: 加 SFXShot.user_edited**

打开 `sound_track_agent/sfx/session.py`，找到 `SFXShot` dataclass，在其它带默认值字段后追加：

```python
    user_edited: bool = False        # 4c: 用户在 DAW 里手动改过 t_start/duration/prompt 时设 True
```

SFXSession.load 走 `SFXShot(**s)` 解包，会自动接受 user_edited 字段。但要确保旧 JSON 无此字段时不抛——已通过 dataclass default 保证。

- [ ] **Step 1.5: 创建 daw 子包骨架**

```bash
mkdir -p drama_shot_master/ui/widgets/daw/inspector
touch drama_shot_master/ui/widgets/daw/__init__.py
touch drama_shot_master/ui/widgets/daw/inspector/__init__.py
```

- [ ] **Step 1.6: 跑测试确认 PASS**

```bash
python -m pytest tests/test_sound_track_agent/test_user_edited_field.py tests/test_sound_track_agent/test_sfx_session.py -q
```
Expected: 全绿（4 新 + SFXSession 既有测试零回归）

- [ ] **Step 1.7: 提交**

```bash
git branch --show-current     # feat/sfx-phase4c
git add sound_track_agent/session.py sound_track_agent/sfx/session.py \
        drama_shot_master/ui/widgets/daw/ \
        tests/test_sound_track_agent/test_user_edited_field.py
git commit -m "feat(4c): SegmentScore + SFXShot 加 user_edited 字段 + daw 子包骨架

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Selection model

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/selection.py`
- Test: `tests/test_ui/daw/test_selection.py`

- [ ] **Step 2.1: 写失败测试** — 新建 `tests/test_ui/daw/test_selection.py`：

```python
"""Selection model + _CueRef."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.selection import _CueRef, Selection


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_curref_equality_and_hash():
    a = _CueRef(track="bgm", seg_index=0)
    b = _CueRef(track="bgm", seg_index=0)
    c = _CueRef(track="sfx", seg_index=0)
    assert a == b and hash(a) == hash(b)
    assert a != c


def test_selection_set_get(app):
    s = Selection()
    refs = [_CueRef("bgm", 0), _CueRef("sfx", 1)]
    s.set(refs)
    assert sorted(s.get(), key=lambda r: (r.track, r.seg_index)) == sorted(refs, key=lambda r: (r.track, r.seg_index))


def test_selection_toggle(app):
    s = Selection()
    r = _CueRef("bgm", 0)
    s.toggle(r)
    assert r in s.get()
    s.toggle(r)
    assert r not in s.get()


def test_selection_clear(app):
    s = Selection()
    s.set([_CueRef("bgm", 0), _CueRef("sfx", 0)])
    s.clear()
    assert s.get() == []


def test_selection_by_track(app):
    s = Selection()
    s.set([_CueRef("bgm", 0), _CueRef("bgm", 2),
           _CueRef("sfx", 1)])
    bt = s.by_track()
    assert sorted(bt["bgm"]) == [0, 2]
    assert bt["sfx"] == [1]


def test_selection_changed_signal_emitted(app):
    s = Selection()
    received = {"n": 0}
    s.changed.connect(lambda: received.__setitem__("n", received["n"] + 1))
    s.set([_CueRef("bgm", 0)])
    s.add(_CueRef("sfx", 0))
    s.toggle(_CueRef("bgm", 0))     # 移除
    s.clear()
    assert received["n"] == 4
```

- [ ] **Step 2.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/daw/test_selection.py -q
```
Expected: 6 FAILED (ImportError)

- [ ] **Step 2.3: 创建 selection.py**

```python
"""选区 + 多选 model。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class _CueRef:
    """指向 BGM/SFX/对白 session 里 cue 的引用。"""
    track: Literal["video", "bgm", "sfx", "dialogue"]
    seg_index: int


class Selection(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._refs: set[_CueRef] = set()

    def get(self) -> list[_CueRef]:
        return sorted(self._refs, key=lambda r: (r.track, r.seg_index))

    def set(self, refs) -> None:
        new = set(refs)
        if new != self._refs:
            self._refs = new
            self.changed.emit()

    def add(self, ref: _CueRef) -> None:
        if ref not in self._refs:
            self._refs.add(ref)
            self.changed.emit()

    def toggle(self, ref: _CueRef) -> None:
        if ref in self._refs:
            self._refs.discard(ref)
        else:
            self._refs.add(ref)
        self.changed.emit()

    def clear(self) -> None:
        if self._refs:
            self._refs.clear()
            self.changed.emit()

    def by_track(self) -> dict:
        out: dict = {}
        for r in self._refs:
            out.setdefault(r.track, []).append(r.seg_index)
        return out
```

- [ ] **Step 2.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/daw/test_selection.py -q
```
Expected: 6 passed

- [ ] **Step 2.5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/selection.py \
        tests/test_ui/daw/test_selection.py
git commit -m "feat(4c): + Selection model (Ctrl+click 多选 + Shift+drag 选区)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: UndoStack

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/undo_stack.py`
- Test: `tests/test_ui/daw/test_undo_stack.py`

- [ ] **Step 3.1: 写失败测试** — 新建 `tests/test_ui/daw/test_undo_stack.py`：

```python
"""UndoStack：push 自动 execute + undo/redo + MAX_DEPTH 截断 + signals."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.undo_stack import UndoStack


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeCmd:
    """最简 Command 不依赖真 commands.py（避免循环）。"""
    def __init__(self, log, name):
        self.log = log
        self.name = name
        self.executed = False

    def execute(self):
        self.log.append(f"exec:{self.name}")
        self.executed = True

    def undo(self):
        self.log.append(f"undo:{self.name}")

    def redo(self):
        self.log.append(f"redo:{self.name}")
        self.executed = True

    def describe(self):
        return self.name


def test_push_executes_and_marks_can_undo(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    assert log == ["exec:A"]
    assert stk.can_undo() is True
    assert stk.can_redo() is False


def test_undo_redo_cycle(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    stk.undo()
    assert log == ["exec:A", "undo:A"]
    assert stk.can_undo() is False and stk.can_redo() is True
    stk.redo()
    assert log == ["exec:A", "undo:A", "redo:A"]


def test_push_clears_redo_stack(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    stk.undo()
    assert stk.can_redo() is True
    stk.push(_FakeCmd(log, "B"))
    assert stk.can_redo() is False


def test_max_depth_truncates_oldest(app):
    stk = UndoStack()
    stk.MAX_DEPTH = 3
    log = []
    for i in range(5):
        stk.push(_FakeCmd(log, str(i)))
    # 应保留最后 3 条 (2/3/4)，最早 2 条 (0/1) 被截
    for _ in range(3):
        stk.undo()
    assert log[-3:] == ["undo:4", "undo:3", "undo:2"]
    assert stk.can_undo() is False


def test_clear(app):
    stk = UndoStack()
    log = []
    stk.push(_FakeCmd(log, "A"))
    stk.push(_FakeCmd(log, "B"))
    stk.clear()
    assert stk.can_undo() is False and stk.can_redo() is False


def test_signals_emitted(app):
    stk = UndoStack()
    can_undo_events, can_redo_events = [], []
    stk.canUndoChanged.connect(can_undo_events.append)
    stk.canRedoChanged.connect(can_redo_events.append)
    log = []
    stk.push(_FakeCmd(log, "A"))
    assert can_undo_events[-1] is True
    stk.undo()
    assert can_undo_events[-1] is False
    assert can_redo_events[-1] is True
```

- [ ] **Step 3.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/daw/test_undo_stack.py -q
```
Expected: 6 FAILED

- [ ] **Step 3.3: 创建 undo_stack.py**

```python
"""撤销栈：max depth 100；每 push 自动 execute。"""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal


class UndoStack(QObject):
    canUndoChanged = Signal(bool)
    canRedoChanged = Signal(bool)
    MAX_DEPTH = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._past: list = []
        self._future: list = []

    def push(self, cmd) -> None:
        cmd.execute()
        self._past.append(cmd)
        if len(self._past) > self.MAX_DEPTH:
            self._past.pop(0)
        self._future.clear()
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def undo(self) -> None:
        if not self._past:
            return
        cmd = self._past.pop()
        cmd.undo()
        self._future.append(cmd)
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def redo(self) -> None:
        if not self._future:
            return
        cmd = self._future.pop()
        cmd.redo()
        self._past.append(cmd)
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def can_undo(self) -> bool:
        return bool(self._past)

    def can_redo(self) -> bool:
        return bool(self._future)

    def clear(self) -> None:
        self._past.clear()
        self._future.clear()
        self.canUndoChanged.emit(False)
        self.canRedoChanged.emit(False)
```

- [ ] **Step 3.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/daw/test_undo_stack.py -q
```
Expected: 6 passed

- [ ] **Step 3.5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/undo_stack.py \
        tests/test_ui/daw/test_undo_stack.py
git commit -m "feat(4c): + UndoStack (max depth 100, push 自动 execute)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 7 Command 类

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/commands.py`
- Test: `tests/test_ui/daw/test_commands.py`

合并 7 个 Command 一起（保持原子单 commit；每个 Command 测试约 2-4 用例，总 ~22 用例）。

- [ ] **Step 4.1: 写完整失败测试** — 新建 `tests/test_ui/daw/test_commands.py`：

```python
"""7 Command 类 execute / undo 测试。"""
from dataclasses import dataclass
from sound_track_agent.session import SegmentScore, ScoringSession, BGMCandidate
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
from drama_shot_master.ui.widgets.daw.selection import _CueRef
from drama_shot_master.ui.widgets.daw.commands import (
    MoveCue, ResizeCue, DeleteCue, SplitCue, DuplicateCue,
    ChangePrompt, ChooseCandidate,
)


def _bgm_sess():
    return ScoringSession(
        source_mp4="/m.mp4", source_hash="h", global_style="x", frame_rate=24.0,
        segments=[
            SegmentScore(0, 0.0, 5.0, music_prompt="末日",
                         candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="末日")],
                         chosen_candidate=0, status="generated"),
            SegmentScore(1, 5.0, 10.0, music_prompt="紧张"),
        ])


def _sfx_sess():
    return SFXSession(
        source_mp4="/m.mp4", source_hash="h", frame_rate=24.0,
        shots=[
            SFXShot(0, 0.0, 3.0, duration=3.0, prompt_short="门",
                    candidates=[SFXCandidate(path="/a.mp3", seed=1, prompt="门")],
                    chosen_candidate=0, status="generated"),
            SFXShot(1, 3.0, 6.0, duration=3.0, prompt_short="脚步"),
        ])


# ------- MoveCue (4 tests) -------

def test_move_cue_bgm_shifts_both_t_start_t_end():
    bgm = _bgm_sess()
    cmd = MoveCue(bgm, None, [_CueRef("bgm", 0)], dt_sec=2.0)
    cmd.execute()
    assert bgm.segments[0].t_start == 2.0
    assert bgm.segments[0].t_end == 7.0
    assert bgm.segments[0].user_edited is True


def test_move_cue_sfx_shifts_only_t_start():
    sfx = _sfx_sess()
    cmd = MoveCue(None, sfx, [_CueRef("sfx", 0)], dt_sec=1.5)
    cmd.execute()
    assert sfx.shots[0].t_start == 1.5
    # SFX duration 不变
    assert sfx.shots[0].duration == 3.0


def test_move_cue_undo_reverses():
    bgm = _bgm_sess()
    cmd = MoveCue(bgm, None, [_CueRef("bgm", 0)], dt_sec=2.0)
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].t_start == 0.0
    assert bgm.segments[0].t_end == 5.0


def test_move_cue_multiple_refs():
    bgm = _bgm_sess()
    cmd = MoveCue(bgm, None,
                  [_CueRef("bgm", 0), _CueRef("bgm", 1)], dt_sec=1.0)
    cmd.execute()
    assert bgm.segments[0].t_start == 1.0
    assert bgm.segments[1].t_start == 6.0


# ------- ResizeCue (4 tests) -------

def test_resize_bgm_start_changes_t_start():
    bgm = _bgm_sess()
    cmd = ResizeCue(bgm, None, _CueRef("bgm", 0), side="start", dt_sec=1.0)
    cmd.execute()
    assert bgm.segments[0].t_start == 1.0
    assert bgm.segments[0].t_end == 5.0


def test_resize_bgm_end_changes_t_end():
    bgm = _bgm_sess()
    cmd = ResizeCue(bgm, None, _CueRef("bgm", 0), side="end", dt_sec=2.0)
    cmd.execute()
    assert bgm.segments[0].t_end == 7.0


def test_resize_sfx_end_changes_duration():
    sfx = _sfx_sess()
    cmd = ResizeCue(None, sfx, _CueRef("sfx", 0), side="end", dt_sec=1.0)
    cmd.execute()
    assert sfx.shots[0].duration == 4.0


def test_resize_undo_reverses():
    bgm = _bgm_sess()
    cmd = ResizeCue(bgm, None, _CueRef("bgm", 0), side="end", dt_sec=2.0)
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].t_end == 5.0


# ------- DeleteCue (3 tests) -------

def test_delete_bgm_sets_chosen_none_and_disabled():
    bgm = _bgm_sess()
    cmd = DeleteCue(bgm, None, [_CueRef("bgm", 0)])
    cmd.execute()
    assert bgm.segments[0].chosen_candidate is None
    assert getattr(bgm.segments[0], "disabled", False) is True


def test_delete_sfx_sets_enabled_false():
    sfx = _sfx_sess()
    cmd = DeleteCue(None, sfx, [_CueRef("sfx", 0)])
    cmd.execute()
    assert sfx.shots[0].enabled is False


def test_delete_undo_restores():
    bgm = _bgm_sess()
    cmd = DeleteCue(bgm, None, [_CueRef("bgm", 0)])
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].chosen_candidate == 0
    assert getattr(bgm.segments[0], "disabled", False) is False


# ------- ChangePrompt (3 tests) -------

def test_change_prompt_bgm_clears_candidates():
    bgm = _bgm_sess()
    cmd = ChangePrompt(bgm, None, _CueRef("bgm", 0), new_prompt="赛博")
    cmd.execute()
    assert bgm.segments[0].music_prompt == "赛博"
    assert bgm.segments[0].candidates == []
    assert bgm.segments[0].chosen_candidate is None
    assert bgm.segments[0].status == "prompted"


def test_change_prompt_sfx_clears_candidates():
    sfx = _sfx_sess()
    cmd = ChangePrompt(None, sfx, _CueRef("sfx", 0), new_prompt="开窗")
    cmd.execute()
    assert sfx.shots[0].prompt_short == "开窗"
    assert sfx.shots[0].candidates == []
    assert sfx.shots[0].status == "planned"


def test_change_prompt_undo_restores_all():
    bgm = _bgm_sess()
    cmd = ChangePrompt(bgm, None, _CueRef("bgm", 0), new_prompt="赛博")
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].music_prompt == "末日"
    assert len(bgm.segments[0].candidates) == 1
    assert bgm.segments[0].chosen_candidate == 0
    assert bgm.segments[0].status == "generated"


# ------- ChooseCandidate (2 tests) -------

def test_choose_candidate_changes_chosen():
    bgm = _bgm_sess()
    bgm.segments[0].candidates.append(
        BGMCandidate(path="/b.mp3", seed=2, prompt="末日"))
    cmd = ChooseCandidate(bgm, None, _CueRef("bgm", 0), new_idx=1)
    cmd.execute()
    assert bgm.segments[0].chosen_candidate == 1


def test_choose_candidate_undo_restores():
    bgm = _bgm_sess()
    bgm.segments[0].candidates.append(
        BGMCandidate(path="/b.mp3", seed=2, prompt="末日"))
    cmd = ChooseCandidate(bgm, None, _CueRef("bgm", 0), new_idx=1)
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].chosen_candidate == 0


# ------- SplitCue (3 tests) -------

def test_split_bgm_inserts_new_after():
    bgm = _bgm_sess()
    cmd = SplitCue(bgm, None, _CueRef("bgm", 0), at_t=3.0)
    cmd.execute()
    assert len(bgm.segments) == 3
    assert bgm.segments[0].t_end == 3.0
    assert bgm.segments[1].t_start == 3.0
    assert bgm.segments[1].t_end == 5.0
    assert bgm.segments[1].status == "prompted"
    assert bgm.segments[1].candidates == []


def test_split_sfx_changes_duration():
    sfx = _sfx_sess()
    cmd = SplitCue(None, sfx, _CueRef("sfx", 0), at_t=2.0)
    cmd.execute()
    assert len(sfx.shots) == 3
    assert sfx.shots[0].duration == 2.0
    assert sfx.shots[1].t_start == 2.0
    assert sfx.shots[1].duration == 1.0
    assert sfx.shots[1].status == "planned"


def test_split_undo_restores():
    bgm = _bgm_sess()
    orig_t_end = bgm.segments[0].t_end
    cmd = SplitCue(bgm, None, _CueRef("bgm", 0), at_t=3.0)
    cmd.execute()
    cmd.undo()
    assert len(bgm.segments) == 2
    assert bgm.segments[0].t_end == orig_t_end


# ------- DuplicateCue (2 tests) -------

def test_duplicate_bgm_inserts_after():
    bgm = _bgm_sess()
    cmd = DuplicateCue(bgm, None, _CueRef("bgm", 0))
    cmd.execute()
    assert len(bgm.segments) == 3
    # 新 cue 在 idx=1
    assert bgm.segments[1].t_start == 5.0
    assert bgm.segments[1].t_end == 10.0


def test_duplicate_undo_removes():
    sfx = _sfx_sess()
    cmd = DuplicateCue(None, sfx, _CueRef("sfx", 0))
    cmd.execute()
    cmd.undo()
    assert len(sfx.shots) == 2
```

- [ ] **Step 4.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/daw/test_commands.py -q
```
Expected: 21 FAILED (ImportError)

- [ ] **Step 4.3: 创建 commands.py** —— 完整代码：

```python
"""7 类 Command + 撤销/重做。每个 Command 持有 (before, after) 状态。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional


class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...
    @abstractmethod
    def undo(self) -> None: ...
    def redo(self) -> None:
        self.execute()
    @abstractmethod
    def describe(self) -> str: ...


def _get_cue_obj(bgm_session, sfx_session, ref):
    """根据 _CueRef 拿到实际 SegmentScore / SFXShot 对象。"""
    if ref.track == "bgm":
        return bgm_session.segments[ref.seg_index] if bgm_session else None
    if ref.track == "sfx":
        return sfx_session.shots[ref.seg_index] if sfx_session else None
    return None


@dataclass
class MoveCue(Command):
    bgm_session: object
    sfx_session: object
    refs: list
    dt_sec: float

    def execute(self):
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            cue.t_start += self.dt_sec
            if r.track == "bgm":
                cue.t_end += self.dt_sec
            cue.user_edited = True

    def undo(self):
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            cue.t_start -= self.dt_sec
            if r.track == "bgm":
                cue.t_end -= self.dt_sec

    def describe(self):
        return f"Move {len(self.refs)} cue(s) by {self.dt_sec:.2f}s"


@dataclass
class ResizeCue(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    side: str          # "start" or "end"
    dt_sec: float

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            if self.side == "start":
                cue.t_start += self.dt_sec
            else:
                cue.t_end += self.dt_sec
        else:
            if self.side == "start":
                cue.t_start += self.dt_sec
                cue.duration -= self.dt_sec
            else:
                cue.duration += self.dt_sec
        cue.user_edited = True

    def undo(self):
        # 反向 dt 重做一次
        original_dt = self.dt_sec
        self.dt_sec = -self.dt_sec
        self.execute()
        self.dt_sec = original_dt

    def describe(self):
        return f"Resize {self.ref.track} cue {self.side} by {self.dt_sec:.2f}s"


@dataclass
class DeleteCue(Command):
    bgm_session: object
    sfx_session: object
    refs: list
    _backup: list = field(default_factory=list)

    def execute(self):
        self._backup = []
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            if r.track == "bgm":
                self._backup.append((r, cue.chosen_candidate,
                                     getattr(cue, "disabled", False)))
                cue.chosen_candidate = None
                cue.disabled = True
            else:
                self._backup.append((r, None, cue.enabled))
                cue.enabled = False

    def undo(self):
        for r, prev_chosen, prev_flag in self._backup:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            if r.track == "bgm":
                cue.chosen_candidate = prev_chosen
                cue.disabled = prev_flag
            else:
                cue.enabled = prev_flag

    def describe(self):
        return f"Delete {len(self.refs)} cue(s)"


@dataclass
class ChangePrompt(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    new_prompt: str
    _old_prompt: str = ""
    _old_candidates: list = field(default_factory=list)
    _old_chosen: Optional[int] = None
    _old_status: str = ""

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            self._old_prompt = getattr(cue, "music_prompt", "")
            self._old_candidates = list(cue.candidates)
            self._old_chosen = cue.chosen_candidate
            self._old_status = cue.status
            cue.music_prompt = self.new_prompt
            cue.candidates = []
            cue.chosen_candidate = None
            cue.status = "prompted"
        else:
            self._old_prompt = cue.prompt_short
            self._old_candidates = list(cue.candidates)
            self._old_chosen = cue.chosen_candidate
            self._old_status = cue.status
            cue.prompt_short = self.new_prompt
            cue.candidates = []
            cue.chosen_candidate = None
            cue.status = "planned"
        cue.user_edited = True

    def undo(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            cue.music_prompt = self._old_prompt
        else:
            cue.prompt_short = self._old_prompt
        cue.candidates = self._old_candidates
        cue.chosen_candidate = self._old_chosen
        cue.status = self._old_status

    def describe(self):
        return f"Change {self.ref.track} prompt"


@dataclass
class ChooseCandidate(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    new_idx: int
    _old_idx: Optional[int] = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        self._old_idx = cue.chosen_candidate
        cue.chosen_candidate = self.new_idx

    def undo(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        cue.chosen_candidate = self._old_idx

    def describe(self):
        return f"Choose candidate {self.new_idx} for {self.ref.track}"


@dataclass
class SplitCue(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    at_t: float
    _inserted_idx: Optional[int] = None
    _old_t_end: Optional[float] = None
    _old_duration: Optional[float] = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        new_cue = deepcopy(cue)
        if self.ref.track == "bgm":
            self._old_t_end = cue.t_end
            new_cue.t_start = self.at_t
            cue.t_end = self.at_t
            new_cue.candidates = []
            new_cue.chosen_candidate = None
            new_cue.status = "prompted"
            self.bgm_session.segments.insert(self.ref.seg_index + 1, new_cue)
        else:
            self._old_duration = cue.duration
            new_dur = (cue.t_start + cue.duration) - self.at_t
            cue.duration = self.at_t - cue.t_start
            new_cue.t_start = self.at_t
            new_cue.duration = new_dur
            new_cue.candidates = []
            new_cue.chosen_candidate = None
            new_cue.status = "planned"
            self.sfx_session.shots.insert(self.ref.seg_index + 1, new_cue)
        cue.user_edited = True
        new_cue.user_edited = True
        self._inserted_idx = self.ref.seg_index + 1

    def undo(self):
        if self._inserted_idx is None:
            return
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            cue.t_end = self._old_t_end
            del self.bgm_session.segments[self._inserted_idx]
        else:
            cue.duration = self._old_duration
            del self.sfx_session.shots[self._inserted_idx]

    def describe(self):
        return f"Split {self.ref.track} at {self.at_t:.2f}s"


@dataclass
class DuplicateCue(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    _inserted_idx: Optional[int] = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        new_cue = deepcopy(cue)
        if self.ref.track == "bgm":
            dur = cue.t_end - cue.t_start
            new_cue.t_start = cue.t_end
            new_cue.t_end = cue.t_end + dur
            self.bgm_session.segments.insert(self.ref.seg_index + 1, new_cue)
        else:
            new_cue.t_start = cue.t_start + cue.duration
            self.sfx_session.shots.insert(self.ref.seg_index + 1, new_cue)
        new_cue.user_edited = True
        self._inserted_idx = self.ref.seg_index + 1

    def undo(self):
        if self._inserted_idx is None:
            return
        if self.ref.track == "bgm":
            del self.bgm_session.segments[self._inserted_idx]
        else:
            del self.sfx_session.shots[self._inserted_idx]

    def describe(self):
        return "Duplicate cue"
```

- [ ] **Step 4.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/daw/test_commands.py -q
```
Expected: 21 passed（注：SegmentScore 应当支持 `disabled` 字段访问，但 dataclass 无该字段会 AttributeError；如果 SegmentScore 没 disabled 字段，需要先加，或 DeleteCue 用 setattr 动态加（已用 setattr 兼容））

> **如 disabled 字段缺**：检查 `bgm.segments[0].disabled` 抛 AttributeError 时，在 `sound_track_agent/session.py` SegmentScore dataclass 加 `disabled: bool = False`（同 user_edited 模式），并加 from_dict 兼容。

- [ ] **Step 4.5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/commands.py \
        tests/test_ui/daw/test_commands.py \
        sound_track_agent/session.py 2>/dev/null || true
git commit -m "feat(4c): + 7 Command 类 (Move/Resize/Delete/Split/Duplicate/ChangePrompt/ChooseCandidate)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: DawTrackView 自绘主时间轴

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/daw_track_view.py`
- Test: `tests/test_ui/daw/test_daw_track_view_smoke.py`

参考 4b `OverviewTimeline` 实现（`drama_shot_master/ui/widgets/overview_timeline.py`），但升级：

- 轨道高度: video 36px, BGM 40px, SFX 36px, dialogue 36px（4b 是 18-22px）
- 加 `zoom: float`（默认 1.0）+ `scroll_offset: float`（0.0 to 1.0 of total）
- 加 `selection: Selection` 引用，paintEvent 中选中 cue 画白边框 +外 2px 红框
- 加 `rubber_band: QRect | None`，mouseMove Shift 拖动时画矩形
- mousePressEvent 优先级：边界 ±4px → resize；cue 中心 → 选中/拖动；空白 → 拖播放头 / Shift+drag rubber band
- 信号：
  - `cueClicked(_CueRef, modifier)` — modifier 是 Qt.KeyboardModifier（Ctrl/Shift/None）
  - `cueDoubleClicked(_CueRef)`
  - `dragCommandIssued(Command)` — 内部 build + emit，让 SoundtrackEditor push 栈
  - `rubberBandReleased(QRect, modifier)`
  - `contextMenuRequested(_CueRef, QPoint)`
  - `playheadDragged(float)` — 同 4b
  - `playheadDropped(float)` — release 终点

**因代码量大（约 350 行），plan 中此 task 不展开完整代码骨架。Implementer 应：**

1. 完整 Read `drama_shot_master/ui/widgets/overview_timeline.py`（4b 现有 OverviewTimeline，~210 行）
2. 复制为 daw_track_view.py 作为起点
3. 改 `_TRACK_HEIGHTS = {"video": 36, "bgm": 40, "sfx": 36, "dialogue": 36}`
4. 加 zoom/scroll 状态 + `_t_to_x` / `_x_to_t` 考虑 zoom 与 scroll_offset
5. 加 `set_selection(selection: Selection)` 接 changed signal → repaint
6. mousePressEvent 加边界 ±4px 判定（决定 resize side）+ Shift modifier 判定（rubber band）
7. mouseMove 时 if dragging cue → 计算 dt 实时更新 cue（不入栈，release 时入栈）
8. mouseReleaseEvent → build MoveCue / ResizeCue / 无变化跳过 → emit dragCommandIssued
9. mouseDoubleClickEvent → emit cueDoubleClicked
10. contextMenuEvent → emit contextMenuRequested

- [ ] **Step 5.1: 写 smoke 测试 (12 测试)** — 新建 `tests/test_ui/daw/test_daw_track_view_smoke.py`：

```python
"""DawTrackView smoke: 构造 / 选中 / 拖动 / 边界 resize / 双击 / Shift rubber band."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue
from drama_shot_master.ui.widgets.daw.daw_track_view import DawTrackView
from drama_shot_master.ui.widgets.daw.selection import Selection, _CueRef


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _press(w, x, y, mod=Qt.NoModifier):
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(x, y),
                     Qt.LeftButton, Qt.LeftButton, mod)
    w.mousePressEvent(ev)


def _move(w, x, y, mod=Qt.NoModifier):
    ev = QMouseEvent(QMouseEvent.MouseMove, QPoint(x, y),
                     Qt.NoButton, Qt.LeftButton, mod)
    w.mouseMoveEvent(ev)


def _release(w, x, y, mod=Qt.NoModifier):
    ev = QMouseEvent(QMouseEvent.MouseButtonRelease, QPoint(x, y),
                     Qt.LeftButton, Qt.NoButton, mod)
    w.mouseReleaseEvent(ev)


def test_construct(app):
    w = DawTrackView(Selection())
    assert w.minimumHeight() > 100


def test_set_cues_and_paint(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "末日", 0)])
    w.grab()    # paintEvent 不崩


def test_set_zoom_and_scroll(app):
    w = DawTrackView(Selection())
    w.set_zoom(2.0)
    w.set_scroll_offset(0.3)
    assert w._zoom == 2.0
    assert w._scroll_offset == 0.3
    # _t_to_x 应考虑 zoom + scroll
    # cue at t=5, total=30, label=60, width=800, track_w=740, zoom=2 → x = 60 + 740 * 2 * (5/30) - 740 * 2 * 0.3 ...


def test_click_on_cue_emits_cueClicked(app):
    sel = Selection()
    w = DawTrackView(sel)
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "末日", 0)])
    received = []
    w.cueClicked.connect(lambda r, m: received.append((r, m)))
    # BGM 轨 y ≈ axis(14) + video(36) + gap(2) + bgm 中段(20) ≈ 72
    _press(w, 200, 72)
    assert len(received) == 1
    assert received[0][0].track == "bgm"
    assert received[0][0].seg_index == 0


def test_ctrl_click_on_cue_modifier_pass_through(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    received = []
    w.cueClicked.connect(lambda r, m: received.append(m))
    _press(w, 200, 72, Qt.ControlModifier)
    assert received and (received[0] & Qt.ControlModifier)


def test_shift_drag_creates_rubber_band(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    released = []
    w.rubberBandReleased.connect(lambda rect, mod: released.append(rect))
    _press(w, 300, 200, Qt.ShiftModifier)  # 空白起拖
    _move(w, 500, 250, Qt.ShiftModifier)
    _release(w, 500, 250, Qt.ShiftModifier)
    assert len(released) == 1


def test_drag_cue_center_emits_MoveCue_on_release(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    cmds = []
    w.dragCommandIssued.connect(lambda c: cmds.append(c))
    # 在 cue 中心拖：press at 200,72 → move to 280,72 → release
    _press(w, 200, 72)
    _move(w, 280, 72)
    _release(w, 280, 72)
    # release 应 emit MoveCue（dt > 0）
    from drama_shot_master.ui.widgets.daw.commands import MoveCue
    assert len(cmds) == 1
    assert isinstance(cmds[0], MoveCue)


def test_resize_at_cue_boundary_emits_ResizeCue(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    # cue 占 [0, 10s]，宽度 740*10/30 ≈ 246，end_x ≈ 60+246=306
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    cmds = []
    w.dragCommandIssued.connect(lambda c: cmds.append(c))
    # 在 cue end 边界（306 ± 4）拖：
    _press(w, 306, 72)
    _move(w, 350, 72)
    _release(w, 350, 72)
    from drama_shot_master.ui.widgets.daw.commands import ResizeCue
    assert len(cmds) == 1
    assert isinstance(cmds[0], ResizeCue)
    assert cmds[0].side == "end"


def test_double_click_emits_cueDoubleClicked(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    received = []
    w.cueDoubleClicked.connect(lambda r: received.append(r))
    # 模拟 double click
    ev = QMouseEvent(QMouseEvent.MouseButtonDblClick, QPoint(200, 72),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    w.mouseDoubleClickEvent(ev)
    assert len(received) == 1


def test_cross_track_drag_limited_to_origin_track(app):
    """BGM cue 拖到 SFX 轨 y 范围应仍认为是 BGM 轨内移动。"""
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    cmds = []
    w.dragCommandIssued.connect(lambda c: cmds.append(c))
    # BGM 轨 ~72；SFX 轨 ~ 14+36+2+40+2+18 ~112
    _press(w, 200, 72)
    _move(w, 280, 112)  # 鼠标拖到 SFX 轨 y
    _release(w, 280, 112)
    # 仍应是 MoveCue（不跨轨）
    if cmds:
        for r in cmds[0].refs:
            assert r.track == "bgm"


def test_selection_paint_updates(app):
    sel = Selection()
    w = DawTrackView(sel)
    w.resize(800, 200)
    w.set_duration(30.0)
    w.set_cues([_Cue("bgm", 0.0, 10.0, "x", 0)])
    sel.set([_CueRef("bgm", 0)])
    w.grab()    # 选中后 paintEvent 不崩


def test_playhead_drag_on_empty_track(app):
    w = DawTrackView(Selection())
    w.resize(800, 200)
    w.set_duration(30.0)
    received = []
    w.playheadDragged.connect(lambda t: received.append(t))
    # 在空白处拖（无 cue 区域）
    _press(w, 400, 250)
    _move(w, 500, 250)
    _release(w, 500, 250)
    # 至少 emit 1 次 playheadDragged
    assert len(received) >= 1
```

- [ ] **Step 5.2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ui/daw/test_daw_track_view_smoke.py -q
```

- [ ] **Step 5.3: 实现 DawTrackView**

Implementer 按上文要点 1-10 实现，复用 `overview_timeline.py` 的 paintEvent 框架。完整 ~400 行代码。

**核心数据成员**：
```python
class DawTrackView(QWidget):
    cueClicked = Signal(object, int)            # _CueRef, modifier
    cueDoubleClicked = Signal(object)
    dragCommandIssued = Signal(object)          # Command
    rubberBandReleased = Signal(object, int)    # QRect, modifier
    contextMenuRequested = Signal(object, object)   # _CueRef, QPoint
    playheadDragged = Signal(float)
    playheadDropped = Signal(float)

    _TRACK_HEIGHTS = {"video": 36, "bgm": 40, "sfx": 36, "dialogue": 36}
    _RESIZE_HOTSPOT_PX = 4
```

**核心算法**（伪代码）：

```python
def mousePressEvent(self, ev):
    pos = ev.pos(); mod = ev.modifiers()
    cue = self._cue_at(pos.x(), pos.y())
    if cue is not None and cue.track != "video":
        # 判定 resize 边界（cue end_x 或 start_x ± 4px）
        x_start = self._t_to_x(cue.t_start)
        x_end = self._t_to_x(cue.t_end if cue.track == "bgm"
                              else cue.t_start + cue.duration)
        if abs(pos.x() - x_start) <= self._RESIZE_HOTSPOT_PX:
            self._mode = "resize_start"; self._drag_cue = cue
            self._press_x = pos.x()
            return
        if abs(pos.x() - x_end) <= self._RESIZE_HOTSPOT_PX:
            self._mode = "resize_end"; self._drag_cue = cue
            self._press_x = pos.x()
            return
        # cue 中心 → 拖 cue（或 click 选择）
        self.cueClicked.emit(_CueRef(cue.track, cue.seg_index), int(mod))
        self._mode = "drag_cue"; self._drag_cue = cue
        self._press_x = pos.x()
        return
    # 空白：Shift modifier → rubber band；否则 → 拖播放头
    if mod & Qt.ShiftModifier:
        self._mode = "rubber_band"
        self._rubber_band_start = pos
    else:
        self._mode = "playhead"
        self._emit_playhead(self._x_to_t(pos.x()))

def mouseMoveEvent(self, ev):
    if self._mode == "drag_cue":
        dt = self._x_to_t(ev.pos().x()) - self._x_to_t(self._press_x)
        # 实时移动 cue（不入栈）
        self._drag_cue.t_start = self._drag_orig_t_start + dt
        if self._drag_cue.track == "bgm":
            self._drag_cue.t_end = self._drag_orig_t_end + dt
        self.update()
    elif self._mode in ("resize_start", "resize_end"):
        # 实时改边界
        dt = self._x_to_t(ev.pos().x()) - self._x_to_t(self._press_x)
        # ...
    elif self._mode == "rubber_band":
        self._rubber_band_rect = QRect(...)
        self.update()
    elif self._mode == "playhead":
        t = self._x_to_t(ev.pos().x())
        self._emit_playhead(t)
    # 边界附近改 cursor → SizeHor

def mouseReleaseEvent(self, ev):
    if self._mode == "drag_cue":
        dt = total dt; if dt != 0: emit MoveCue
    elif "resize_start": emit ResizeCue(side="start", dt)
    elif "resize_end": emit ResizeCue(side="end", dt)
    elif "rubber_band": emit rubberBandReleased(rect, modifier)
    self._mode = None
```

- [ ] **Step 5.4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ui/daw/test_daw_track_view_smoke.py -q
```
Expected: 12 passed

- [ ] **Step 5.5: 提交**

```bash
git add drama_shot_master/ui/widgets/daw/daw_track_view.py \
        tests/test_ui/daw/test_daw_track_view_smoke.py
git commit -m "feat(4c): + DawTrackView 自绘主时间轴 (拖动/边界 resize/双击/Ctrl+click/Shift+drag)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: DawMinimap

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/daw_minimap.py`
- Test: `tests/test_ui/daw/test_daw_minimap_smoke.py`

3 轨简化 minimap + 蓝窗口框（显示 viewport），拖窗口框 → emit viewportRequested(scroll_offset)。

- [ ] **Step 6.1: 写失败测试** — 新建 `tests/test_ui/daw/test_daw_minimap_smoke.py`：

```python
"""DawMinimap smoke: paint / 拖窗口 / 点击 seek。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue
from drama_shot_master.ui.widgets.daw.daw_minimap import DawMinimap


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _press(w, x, y):
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(x, y),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    w.mousePressEvent(ev)


def test_construct_and_paint(app):
    w = DawMinimap()
    w.resize(600, 30)
    w.set_duration(30.0)
    w.set_cues([
        _Cue("bgm", 0.0, 10.0, "", 0),
        _Cue("sfx", 5.0, 6.0, "", 0),
        _Cue("dialogue", 0.0, 3.0, "", 0),
    ])
    w.grab()


def test_set_viewport_window(app):
    w = DawMinimap()
    w.resize(600, 30)
    w.set_viewport(scroll_offset=0.3, viewport_fraction=0.4)
    assert abs(w._scroll_offset - 0.3) < 1e-6
    assert abs(w._viewport_fraction - 0.4) < 1e-6


def test_click_emits_viewportRequested(app):
    w = DawMinimap()
    w.resize(600, 30)
    received = []
    w.viewportRequested.connect(lambda offset: received.append(offset))
    _press(w, 300, 15)   # 中间位置
    assert len(received) == 1
    # 点中间应当 scroll_offset 大约 0.5（center 0.5 - viewport/2）
    # 验证至少 emit 了


def test_set_cues_does_not_crash_empty(app):
    w = DawMinimap()
    w.resize(600, 30)
    w.set_cues([])
    w.grab()
```

- [ ] **Step 6.2: 跑测试确认 FAIL**

- [ ] **Step 6.3: 实现 DawMinimap**

```python
"""3 轨 minimap + 蓝色窗口框。viewportRequested(offset) 信号让 DawTrackView 跟随。"""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt, QRect
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget


_TRACK_COLORS = {
    "bgm": QColor("#4a7eb8"),
    "sfx": QColor("#c2884c"),
    "dialogue": QColor("#5a9f5a"),
}


class DawMinimap(QWidget):
    viewportRequested = Signal(float)    # scroll_offset 0.0-1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cues = []
        self._duration = 30.0
        self._scroll_offset = 0.0
        self._viewport_fraction = 1.0    # 默认 100%（FIT）
        self.setMinimumHeight(28)
        self.setMaximumHeight(40)
        self.setMouseTracking(True)

    def set_cues(self, cues) -> None:
        self._cues = list(cues)
        self.update()

    def set_duration(self, total_sec: float) -> None:
        self._duration = max(0.001, float(total_sec))
        self.update()

    def set_viewport(self, scroll_offset: float, viewport_fraction: float) -> None:
        self._scroll_offset = max(0.0, min(1.0, float(scroll_offset)))
        self._viewport_fraction = max(0.01, min(1.0, float(viewport_fraction)))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor("#1a1a1a"))
            # 3 轨各占 1/3 高度
            h_per = max(2, self.height() // 3 - 1)
            for i, track in enumerate(["bgm", "sfx", "dialogue"]):
                y = i * (h_per + 1) + 1
                p.fillRect(0, y, self.width(), h_per, QColor("#2a2a2a"))
                color = _TRACK_COLORS[track]
                for c in self._cues:
                    if c.track != track:
                        continue
                    x_a = int(self.width() * c.t_start / self._duration)
                    x_b = int(self.width() * c.t_end / self._duration)
                    p.fillRect(x_a, y, max(1, x_b - x_a), h_per, color)
            # 蓝色 viewport 窗口
            win_x = int(self.width() * self._scroll_offset)
            win_w = int(self.width() * self._viewport_fraction)
            p.setPen(QColor("#4a7eb8"))
            p.fillRect(QRect(win_x, 0, win_w, self.height()),
                       QColor(74, 126, 184, 50))
            p.drawRect(win_x, 0, win_w, self.height() - 1)
        finally:
            p.end()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        x = ev.pos().x()
        # 点击 → 把窗口中心移到该位置
        target_center = x / max(1, self.width())
        new_offset = max(0.0, target_center - self._viewport_fraction / 2)
        new_offset = min(new_offset, 1.0 - self._viewport_fraction)
        self.viewportRequested.emit(new_offset)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            self.mousePressEvent(ev)    # 拖动同点击逻辑
```

- [ ] **Step 6.4: PASS + 提交**

```bash
python -m pytest tests/test_ui/daw/test_daw_minimap_smoke.py -q
git add drama_shot_master/ui/widgets/daw/daw_minimap.py \
        tests/test_ui/daw/test_daw_minimap_smoke.py
git commit -m "feat(4c): + DawMinimap 3 轨 minimap + 蓝色 viewport 窗口

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: DawToolbar

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/daw_toolbar.py`
- Test: `tests/test_ui/daw/test_daw_toolbar_smoke.py`

- [ ] **Step 7.1: 写失败测试**：

```python
"""DawToolbar smoke."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.daw.undo_stack import UndoStack
from drama_shot_master.ui.widgets.daw.daw_toolbar import DawToolbar


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct_and_widgets_exist(app):
    tb = DawToolbar(UndoStack())
    for attr in ("btn_play", "time_label", "btn_zoom_in", "btn_zoom_out",
                 "zoom_slider", "btn_fit", "btn_undo", "btn_redo",
                 "btn_config"):
        assert hasattr(tb, attr), f"missing {attr}"


def test_play_button_emits(app):
    tb = DawToolbar(UndoStack())
    received = []
    tb.playPauseRequested.connect(lambda: received.append(True))
    tb.btn_play.click()
    assert received == [True]


def test_config_button_emits(app):
    tb = DawToolbar(UndoStack())
    received = []
    tb.configRequested.connect(lambda: received.append(True))
    tb.btn_config.click()
    assert received == [True]


def test_undo_redo_button_state_from_stack(app):
    stk = UndoStack()
    tb = DawToolbar(stk)
    # 初始 stack 空 → 按钮 disabled
    assert tb.btn_undo.isEnabled() is False
    assert tb.btn_redo.isEnabled() is False
    # 模拟 stack 信号
    stk.canUndoChanged.emit(True)
    assert tb.btn_undo.isEnabled() is True
```

- [ ] **Step 7.2: 实现 DawToolbar**

```python
"""DAW 工具栏: 播放 / zoom / 撤销 / 配置 + 信号。"""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QSlider,
)


class DawToolbar(QWidget):
    playPauseRequested = Signal()
    zoomInRequested = Signal()
    zoomOutRequested = Signal()
    zoomChanged = Signal(float)     # 0.0-1.0 slider value
    fitRequested = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    configRequested = Signal()

    def __init__(self, undo_stack, parent=None):
        super().__init__(parent)
        self._undo_stack = undo_stack
        self._build_ui()
        undo_stack.canUndoChanged.connect(self.btn_undo.setEnabled)
        undo_stack.canRedoChanged.connect(self.btn_redo.setEnabled)
        self.btn_undo.setEnabled(undo_stack.can_undo())
        self.btn_redo.setEnabled(undo_stack.can_redo())

    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        self.btn_play = QPushButton("▶")
        self.btn_play.setMaximumWidth(32)
        self.btn_play.clicked.connect(self.playPauseRequested.emit)
        self.time_label = QLabel("0:00 / 0:00")
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setMaximumWidth(28)
        self.btn_zoom_out.clicked.connect(self.zoomOutRequested.emit)
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setMaximumWidth(28)
        self.btn_zoom_in.clicked.connect(self.zoomInRequested.emit)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setValue(0)         # 0 = FIT (zoom=1), 100 = zoom=50
        self.zoom_slider.setMaximumWidth(180)
        self.zoom_slider.valueChanged.connect(
            lambda v: self.zoomChanged.emit(v / 100.0))
        self.btn_fit = QPushButton("FIT")
        self.btn_fit.setMaximumWidth(40)
        self.btn_fit.clicked.connect(self.fitRequested.emit)
        self.btn_undo = QPushButton("↶")
        self.btn_undo.setMaximumWidth(32)
        self.btn_undo.clicked.connect(self.undoRequested.emit)
        self.btn_redo = QPushButton("↷")
        self.btn_redo.setMaximumWidth(32)
        self.btn_redo.clicked.connect(self.redoRequested.emit)
        self.btn_config = QPushButton("⚙")
        self.btn_config.setMaximumWidth(32)
        self.btn_config.clicked.connect(self.configRequested.emit)
        for w in (self.btn_play, self.time_label,
                  QLabel("zoom"), self.btn_zoom_out, self.zoom_slider,
                  self.btn_zoom_in, self.btn_fit,
                  self.btn_undo, self.btn_redo):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(self.btn_config)

    def set_time(self, current_sec: float, total_sec: float):
        def _fmt(s):
            s = max(0, int(s)); return f"{s // 60}:{s % 60:02d}"
        self.time_label.setText(f"{_fmt(current_sec)} / {_fmt(total_sec)}")

    def set_playing(self, playing: bool):
        self.btn_play.setText("⏸" if playing else "▶")
```

- [ ] **Step 7.3: PASS + 提交**

```bash
python -m pytest tests/test_ui/daw/test_daw_toolbar_smoke.py -q
git add drama_shot_master/ui/widgets/daw/daw_toolbar.py \
        tests/test_ui/daw/test_daw_toolbar_smoke.py
git commit -m "feat(4c): + DawToolbar (播放/zoom/撤销/配置)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 4 Inspector 模板

**Files:**
- Create: `drama_shot_master/ui/widgets/daw/inspector/{empty,dialogue,bgm,sfx}_inspector.py`
- Test: `tests/test_ui/daw/test_inspector_smoke.py`

合并 4 个 inspector 一起做（每个 ~80 行，总 ~320 行）。

- [ ] **Step 8.1: 写失败测试**：

```python
"""4 Inspector 模板 smoke: 字段齐 + 信号 emit."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.session import SegmentScore, ScoringSession, BGMCandidate
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
from drama_shot_master.ui.widgets.daw.selection import _CueRef


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_empty_inspector_construct(app):
    from drama_shot_master.ui.widgets.daw.inspector.empty_inspector \
        import EmptyInspector
    w = EmptyInspector()
    assert w is not None


def test_bgm_inspector_displays_cue_fields(app):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector \
        import BgmInspector
    bgm = ScoringSession(source_mp4="/m.mp4", source_hash="h",
                         global_style="末日", frame_rate=24.0,
                         segments=[SegmentScore(
                             0, 0.0, 5.0, music_prompt="末日废土",
                             candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="x")],
                             chosen_candidate=0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    # 应当显示时间 / prompt 截断 / 候选 radio / 音量 slider / 重生按钮
    text = w.findChildren(type(w))   # 简单存在性
    # 不深查具体文本，只验证不崩 + 关键 widget 存在
    assert hasattr(w, "btn_regen")
    assert hasattr(w, "btn_edit_prompt")


def test_bgm_inspector_regenerate_signal(app):
    from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector \
        import BgmInspector
    bgm = ScoringSession(source_mp4="/m.mp4", source_hash="h",
                         global_style="末日", frame_rate=24.0,
                         segments=[SegmentScore(0, 0.0, 5.0)])
    w = BgmInspector()
    w.set_cue_ref(_CueRef("bgm", 0), bgm)
    received = []
    w.regenerateRequested.connect(lambda ref: received.append(ref))
    w.btn_regen.click()
    assert len(received) == 1


def test_sfx_inspector_duration_spin_changes_emit_resize_command(app):
    from drama_shot_master.ui.widgets.daw.inspector.sfx_inspector \
        import SfxInspector
    sfx = SFXSession(source_mp4="/m.mp4", source_hash="h", frame_rate=24.0,
                     shots=[SFXShot(0, 0.0, 3.0, duration=3.0,
                                     prompt_short="门")])
    w = SfxInspector()
    w.set_cue_ref(_CueRef("sfx", 0), sfx)
    cmds = []
    w.commandIssued.connect(lambda c: cmds.append(c))
    w.duration_spin.setValue(5.0)     # 3.0 → 5.0，dt = +2.0
    # 应当发 ResizeCue
    from drama_shot_master.ui.widgets.daw.commands import ResizeCue
    assert any(isinstance(c, ResizeCue) for c in cmds)


def test_dialogue_inspector_is_readonly(app):
    from drama_shot_master.ui.widgets.daw.inspector.dialogue_inspector \
        import DialogueInspector
    audios = [{
        "audio_path": "/x/voice_charA_01.flac",
        "start_frame": 0, "length_frames": 72,
    }]
    timeline = {"frame_rate": 24.0, "audios": audios}
    w = DialogueInspector()
    w.set_cue_ref(_CueRef("dialogue", 0), timeline)
    # 无任何 editable 控件（QLineEdit/QSpinBox 都不允许编辑或不存在）
    from PySide6.QtWidgets import QLineEdit
    edits = w.findChildren(QLineEdit)
    for e in edits:
        assert e.isReadOnly()
```

- [ ] **Step 8.2: 实现 4 Inspector**

`drama_shot_master/ui/widgets/daw/inspector/__init__.py` 已存在（T1）。逐个创建：

`empty_inspector.py`:
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class EmptyInspector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("无选中。点 cue 查看属性，Ctrl+click 多选。"))
        lay.addStretch(1)
```

`bgm_inspector.py`:
```python
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QButtonGroup, QRadioButton,
)
from drama_shot_master.ui.widgets.daw.selection import _CueRef


class BgmInspector(QWidget):
    promptEditRequested = Signal(object)    # _CueRef
    candidateChosen = Signal(object, int)   # _CueRef, new_idx
    regenerateRequested = Signal(object)
    volumeChanged = Signal(object, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ref = None
        self._session = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("BGM 段"); lay.addWidget(self.title)
        self.time_label = QLabel("0:00 → 0:00"); lay.addWidget(self.time_label)
        lay.addWidget(QLabel("风格 prompt:"))
        self.prompt_label = QLabel(""); self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            "background:#1a1a1a;padding:4px;border-radius:2px;")
        lay.addWidget(self.prompt_label)
        self.btn_edit_prompt = QPushButton("✎ 编辑 prompt")
        self.btn_edit_prompt.clicked.connect(
            lambda: self._ref and self.promptEditRequested.emit(self._ref))
        lay.addWidget(self.btn_edit_prompt)
        lay.addWidget(QLabel("候选:"))
        self.cand_group = QButtonGroup(self)
        self.cand_layout = QVBoxLayout(); lay.addLayout(self.cand_layout)
        lay.addWidget(QLabel("音量:"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150); self.vol_slider.setValue(100)
        self.vol_slider.valueChanged.connect(self._on_volume)
        lay.addWidget(self.vol_slider)
        self.btn_regen = QPushButton("↻ 重生成")
        self.btn_regen.clicked.connect(
            lambda: self._ref and self.regenerateRequested.emit(self._ref))
        lay.addWidget(self.btn_regen)
        lay.addStretch(1)

    def set_cue_ref(self, ref, session):
        self._ref = ref; self._session = session
        seg = session.segments[ref.seg_index] if session else None
        if seg is None: return
        self.title.setText(f"BGM 段 {ref.seg_index}")
        self.time_label.setText(f"{seg.t_start:.1f}s → {seg.t_end:.1f}s")
        prompt = getattr(seg, "music_prompt", "") or "(空)"
        self.prompt_label.setText(prompt[:80] + ("..." if len(prompt) > 80 else ""))
        self.vol_slider.setValue(int(getattr(seg, "volume", 1.0) * 100))
        # 候选 radio
        for btn in list(self.cand_group.buttons()):
            self.cand_group.removeButton(btn); btn.deleteLater()
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
```

`sfx_inspector.py`（结构同 BgmInspector，加 duration_spin）:
```python
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QSlider, QButtonGroup,
    QRadioButton, QDoubleSpinBox, QCheckBox,
)
from drama_shot_master.ui.widgets.daw.commands import ResizeCue


class SfxInspector(QWidget):
    promptEditRequested = Signal(object)
    candidateChosen = Signal(object, int)
    regenerateRequested = Signal(object)
    volumeChanged = Signal(object, float)
    enabledChanged = Signal(object, bool)
    commandIssued = Signal(object)    # 发 ResizeCue（duration_spin 改）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ref = None; self._session = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("SFX 镜"); lay.addWidget(self.title)
        self.time_label = QLabel("0:00 (3.0s)"); lay.addWidget(self.time_label)
        lay.addWidget(QLabel("时长 (s):"))
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(1.0, 15.0); self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setDecimals(1); self.duration_spin.setSuffix(" s")
        self.duration_spin.valueChanged.connect(self._on_duration)
        lay.addWidget(self.duration_spin)
        lay.addWidget(QLabel("短描述:"))
        self.prompt_label = QLabel(""); self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            "background:#1a1a1a;padding:4px;border-radius:2px;")
        lay.addWidget(self.prompt_label)
        self.btn_edit_prompt = QPushButton("✎ 编辑 prompt")
        self.btn_edit_prompt.clicked.connect(
            lambda: self._ref and self.promptEditRequested.emit(self._ref))
        lay.addWidget(self.btn_edit_prompt)
        lay.addWidget(QLabel("候选:"))
        self.cand_group = QButtonGroup(self)
        self.cand_layout = QVBoxLayout(); lay.addLayout(self.cand_layout)
        lay.addWidget(QLabel("音量:"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150); self.vol_slider.setValue(80)
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
        self._suppress_dur = False
        self._old_duration = 0.0

    def set_cue_ref(self, ref, session):
        self._ref = ref; self._session = session
        shot = session.shots[ref.seg_index] if session else None
        if shot is None: return
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
            self.cand_group.removeButton(btn); btn.deleteLater()
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
        cmd = ResizeCue(None, self._session, self._ref,
                        side="end", dt_sec=dt)
        self.commandIssued.emit(cmd)

    def _on_volume(self, val: int):
        if self._ref:
            self.volumeChanged.emit(self._ref, val / 100.0)

    def _on_enabled(self, checked: bool):
        if self._ref:
            self.enabledChanged.emit(self._ref, checked)
```

`dialogue_inspector.py`（全只读）:
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit
from drama_shot_master.ui.widgets.daw.selection import _CueRef


class DialogueInspector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("对白片段"); lay.addWidget(self.title)
        lay.addWidget(QLabel("文件:"))
        self.path_edit = QLineEdit(); self.path_edit.setReadOnly(True)
        lay.addWidget(self.path_edit)
        lay.addWidget(QLabel("时间:"))
        self.time_label = QLabel("0:00 → 0:00"); lay.addWidget(self.time_label)
        lay.addWidget(QLabel("角色:"))
        self.role_edit = QLineEdit(); self.role_edit.setReadOnly(True)
        lay.addWidget(self.role_edit)
        lay.addWidget(QLabel("来源: 配音智能体（只读）"))
        lay.addStretch(1)

    def set_cue_ref(self, ref, timeline_dict):
        if not timeline_dict: return
        audios = timeline_dict.get("audios") or []
        if not (0 <= ref.seg_index < len(audios)): return
        a = audios[ref.seg_index]
        fps = float(timeline_dict.get("frame_rate", 24.0)) or 24.0
        t_start = float(a.get("start_frame", 0)) / fps
        t_end = t_start + float(a.get("length_frames", 0)) / fps
        path = a.get("audio_path") or ""
        self.title.setText(f"对白 {ref.seg_index}")
        self.path_edit.setText(path)
        self.time_label.setText(f"{t_start:.2f}s → {t_end:.2f}s")
        # 从文件名推断角色（split by '_'）
        basename = path.rsplit("/", 1)[-1]
        parts = basename.split("_")
        self.role_edit.setText(parts[1] if len(parts) > 1 else "(未知)")
```

`__init__.py` 暴露：
```python
from drama_shot_master.ui.widgets.daw.inspector.empty_inspector import EmptyInspector
from drama_shot_master.ui.widgets.daw.inspector.bgm_inspector import BgmInspector
from drama_shot_master.ui.widgets.daw.inspector.sfx_inspector import SfxInspector
from drama_shot_master.ui.widgets.daw.inspector.dialogue_inspector import DialogueInspector

__all__ = ["EmptyInspector", "BgmInspector", "SfxInspector", "DialogueInspector"]
```

- [ ] **Step 8.3: PASS + 提交**

```bash
python -m pytest tests/test_ui/daw/test_inspector_smoke.py -q
git add drama_shot_master/ui/widgets/daw/inspector/ \
        tests/test_ui/daw/test_inspector_smoke.py
git commit -m "feat(4c): + 4 Inspector 模板 (Empty/Dialogue 只读 / BGM / SFX)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: 2 个 Dialog（ConfigDialog + PromptEditDialog）

**Files:**
- Create: `drama_shot_master/ui/dialogs/config_dialog.py`
- Create: `drama_shot_master/ui/dialogs/prompt_edit_dialog.py`
- Test: `tests/test_ui/dialogs/test_config_dialog_smoke.py`
- Test: `tests/test_ui/dialogs/test_prompt_edit_dialog_smoke.py`

- [ ] **Step 9.1: 写失败测试** (5 测试)：

```python
# tests/test_ui/dialogs/test_config_dialog_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_config_dialog_construct_and_field_roundtrip(app):
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    initial = {"mp4": "/a.mp4", "style": "末日", "output_dir": "/out"}
    dlg = ConfigDialog(initial)
    assert dlg.mp4_edit.text() == "/a.mp4"
    assert dlg.style_edit.toPlainText() == "末日"
    assert dlg.out_edit.text() == "/out"
    dlg.mp4_edit.setText("/b.mp4")
    dlg.style_edit.setPlainText("古风")
    dlg.out_edit.setText("/out2")
    payload = dlg.to_payload()
    assert payload == {"mp4": "/b.mp4", "style": "古风", "output_dir": "/out2"}


def test_config_dialog_browse_mp4_does_not_crash(app, monkeypatch):
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    dlg = ConfigDialog({"mp4": "", "style": "", "output_dir": ""})
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **k: ("/picked.mp4", "*"))
    dlg._browse_mp4()
    assert dlg.mp4_edit.text() == "/picked.mp4"


def test_config_dialog_browse_output_dir_does_not_crash(app, monkeypatch):
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    dlg = ConfigDialog({"mp4": "", "style": "", "output_dir": ""})
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *a, **k: "/picked_dir")
    dlg._browse_out()
    assert dlg.out_edit.text() == "/picked_dir"
```

```python
# tests/test_ui/dialogs/test_prompt_edit_dialog_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_prompt_edit_bgm_mode(app):
    from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
    dlg = PromptEditDialog(initial_prompt="末日", title="BGM 段 0")
    dlg.prompt_edit.setPlainText("末日新版")
    assert dlg.to_payload() == "末日新版"


def test_prompt_edit_sfx_mode(app):
    from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
    dlg = PromptEditDialog(initial_prompt="门吱呀", title="SFX 镜 0")
    dlg.prompt_edit.setPlainText("门吱呀打开")
    assert dlg.to_payload() == "门吱呀打开"


def test_prompt_edit_empty_strips_whitespace(app):
    from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
    dlg = PromptEditDialog(initial_prompt="x", title="x")
    dlg.prompt_edit.setPlainText("   text  ")
    assert dlg.to_payload() == "text"
```

- [ ] **Step 9.2: 实现 2 个 Dialog**

`config_dialog.py`:
```python
"""mp4 路径 / 风格 / 输出目录 编辑弹窗（从 SoundtrackEditor _build_config_tab 抽出）。"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QFileDialog, QDialogButtonBox,
)


class ConfigDialog(QDialog):
    def __init__(self, initial: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("任务配置")
        self.setMinimumWidth(450)
        self._build_ui(initial)

    def _build_ui(self, initial: dict):
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("成片 MP4:"))
        mp4_row = QHBoxLayout()
        self.mp4_edit = QLineEdit(initial.get("mp4", ""))
        b1 = QPushButton("浏览…"); b1.clicked.connect(self._browse_mp4)
        mp4_row.addWidget(self.mp4_edit, 1); mp4_row.addWidget(b1)
        lay.addLayout(mp4_row)
        lay.addWidget(QLabel("总风格:"))
        self.style_edit = QPlainTextEdit(initial.get("style", ""))
        self.style_edit.setMaximumHeight(80)
        lay.addWidget(self.style_edit)
        lay.addWidget(QLabel("本任务输出目录 (空=用全局默认):"))
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit(initial.get("output_dir", ""))
        b2 = QPushButton("浏览…"); b2.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1); out_row.addWidget(b2)
        lay.addLayout(out_row)
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _browse_mp4(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择成片 MP4", self.mp4_edit.text() or "",
            "视频 (*.mp4 *.mov)")
        if p:
            self.mp4_edit.setText(p)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def to_payload(self) -> dict:
        return {
            "mp4": self.mp4_edit.text().strip(),
            "style": self.style_edit.toPlainText().strip(),
            "output_dir": self.out_edit.text().strip(),
        }
```

`prompt_edit_dialog.py`:
```python
"""BGM/SFX prompt 编辑弹窗。双击 cue 触发；OK 后由调用方 build ChangePrompt 命令。"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QLabel,
)


class PromptEditDialog(QDialog):
    def __init__(self, initial_prompt: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Prompt（短描述/风格）:"))
        self.prompt_edit = QPlainTextEdit(initial_prompt or "")
        self.prompt_edit.setMinimumHeight(120)
        lay.addWidget(self.prompt_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def to_payload(self) -> str:
        return self.prompt_edit.toPlainText().strip()
```

- [ ] **Step 9.3: PASS + 提交**

```bash
mkdir -p tests/test_ui/dialogs
python -m pytest tests/test_ui/dialogs/ -q
git add drama_shot_master/ui/dialogs/config_dialog.py \
        drama_shot_master/ui/dialogs/prompt_edit_dialog.py \
        tests/test_ui/dialogs/
git commit -m "feat(4c): + ConfigDialog + PromptEditDialog 弹窗

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: SoundtrackEditor 大改 — 主区改 DAW

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py` (~大改)
- Test: `tests/test_ui/test_soundtrack_editor_daw_smoke.py`

**这是最大的 task**。Implementer 应：

1. **先备份当前文件结构**：`cp soundtrack_editor.py soundtrack_editor_pre4c.py.bak`（commit 前删掉）
2. **保留**：
   - `__init__` 的 `self._task / self.cfg / self._work_root / self._worker / self._session / self._sfx_session / self._sfx_worker / self._video_preview / self._overview_timeline` 全部
   - `_work_dir / _resolve_output_base` 完整保留
   - `_try_load_existing` 保留但 `_mount_session_tabs` 改名 `_mount_daw_main`
   - 所有 worker 启动方法保留：`_run_pipeline / _on_done / _on_regenerate / _on_failed / _on_export / _on_resegment / _on_sfx_plan_clicked / _on_sfx_generate_clicked / _on_sfx_plan_done / _on_sfx_generate_done / _on_sfx_regenerate_one`
3. **删除（替换）**：
   - `self.tabs` / `self._review / self._accent / self._sfx_review_*` 字段
   - `_build_ui` 的 tab 构造逻辑（保留顶部预览）
   - `_build_config_tab / _build_sfx_tab / _mount_session_tabs / _rebuild_sfx_review` 全删
   - `_on_overview_cue_clicked` 里基于 tab index 的跳转改成 selection 设置
4. **新增**：
   - `self._daw_toolbar / self._track_view / self._minimap / self._inspector_container / self._current_inspector / self._undo / self._selection / self._scrollbar`
   - `_build_daw_main()` 方法
   - `_refresh_inspector()` 方法（按 selection 变化切 inspector）
   - `_on_undo_redo()` / `_on_zoom_*()` / `_on_fit()` / `_on_open_config_dialog()`
   - 键盘快捷键: 用 `QShortcut`（9 个）
   - `_on_track_view_drag_command(cmd)` → `self._undo.push(cmd)` + 持久化
   - `_on_inspector_command(cmd)` → 同上
   - `_on_open_prompt_edit_dialog(ref)` → 弹 PromptEditDialog → OK → build ChangePrompt + push

代码量约 ~600 行（含改动 + 新增）。下面给关键骨架：

- [ ] **Step 10.1: 写失败测试**：

```python
"""SoundtrackEditor DAW 主区 smoke：DAW widget 存在 + selection → inspector 切换 + 快捷键。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QKeyEvent
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _task(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    return {"id": "t1", "name": "test", "mp4": str(mp4),
            "style": "末日", "workflow_id": "wf", "output_dir": ""}


def test_daw_widgets_exist(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    assert ed._daw_toolbar is not None
    assert ed._track_view is not None
    assert ed._minimap is not None
    assert ed._inspector_container is not None
    assert ed._undo is not None
    assert ed._selection is not None


def test_no_tabs_attribute(tmp_path):
    """4 tab 完全消失（self.tabs 不再存在）。"""
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    assert not hasattr(ed, "tabs")


def test_selection_change_swaps_inspector(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    from drama_shot_master.ui.widgets.daw.inspector import (
        EmptyInspector, BgmInspector,
    )
    # 初始: empty
    assert isinstance(ed._current_inspector, EmptyInspector)
    # 加 bgm session + 选 cue 0 → BgmInspector
    from sound_track_agent.session import ScoringSession, SegmentScore
    ed._session = ScoringSession(
        source_mp4="", source_hash="", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(0, 0.0, 5.0)])
    ed._selection.set([_CueRef("bgm", 0)])
    assert isinstance(ed._current_inspector, BgmInspector)
    # 清选 → Empty
    ed._selection.clear()
    assert isinstance(ed._current_inspector, EmptyInspector)


def test_config_button_opens_dialog(tmp_path, monkeypatch):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    opened = {"n": 0}
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    orig_exec = ConfigDialog.exec
    monkeypatch.setattr(ConfigDialog, "exec",
                        lambda self: opened.__setitem__("n", opened["n"] + 1)
                                     or ConfigDialog.Rejected)
    ed._on_open_config_dialog()
    assert opened["n"] == 1


def test_undo_via_toolbar(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from drama_shot_master.ui.widgets.daw.commands import MoveCue
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    from sound_track_agent.session import ScoringSession, SegmentScore
    ed._session = ScoringSession(
        source_mp4="", source_hash="", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(0, 0.0, 5.0)])
    cmd = MoveCue(ed._session, ed._sfx_session, [_CueRef("bgm", 0)], 2.0)
    ed._undo.push(cmd)
    assert ed._session.segments[0].t_start == 2.0
    ed._daw_toolbar.btn_undo.click()
    assert ed._session.segments[0].t_start == 0.0


def test_delete_key_removes_selected(tmp_path):
    _app()
    ed = SoundtrackEditor(_task(tmp_path), _cfg(tmp_path), tmp_path)
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate
    ed._session = ScoringSession(
        source_mp4="", source_hash="", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(0, 0.0, 5.0,
                                 candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="x")],
                                 chosen_candidate=0)])
    ed._selection.set([_CueRef("bgm", 0)])
    # 模拟 Delete 键事件
    ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
    ed.keyPressEvent(ev)
    # BGM 软删 chosen=None
    assert ed._session.segments[0].chosen_candidate is None
```

- [ ] **Step 10.2-10.5: 跑测试 → 实现 → PASS → 提交**

实现要点：

**`__init__`**:
```python
def __init__(self, task, cfg, work_root, parent=None):
    super().__init__(parent)
    self._task = task; self.cfg = cfg; self._work_root = Path(work_root)
    self._worker = None; self._sfx_worker = None
    self._session = None; self._sfx_session = None
    self._video_preview = None; self._overview_timeline = None
    # 4c 新
    self._daw_toolbar = None; self._track_view = None
    self._minimap = None; self._inspector_container = None
    self._current_inspector = None
    from drama_shot_master.ui.widgets.daw.selection import Selection
    from drama_shot_master.ui.widgets.daw.undo_stack import UndoStack
    self._selection = Selection(self)
    self._undo = UndoStack(self)
    self._build_ui()
    self._setup_shortcuts()
    self._try_load_existing()
```

**`_build_ui`** 完全重写（删 tabs，加 DAW）：

```python
def _build_ui(self):
    root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
    from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget
    from drama_shot_master.ui.widgets.overview_timeline import OverviewTimeline
    self._video_preview = VideoPreviewWidget()
    self._overview_timeline = OverviewTimeline()
    self._video_preview.positionChanged.connect(self._on_video_position_changed)
    self._overview_timeline.playheadDragged.connect(self._on_overview_playhead_dragged)
    root.addWidget(self._video_preview)
    root.addWidget(self._overview_timeline)
    self._build_daw_main(root)

def _build_daw_main(self, root):
    from drama_shot_master.ui.widgets.daw.daw_toolbar import DawToolbar
    from drama_shot_master.ui.widgets.daw.daw_track_view import DawTrackView
    from drama_shot_master.ui.widgets.daw.daw_minimap import DawMinimap
    from drama_shot_master.ui.widgets.daw.inspector import EmptyInspector
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QScrollBar
    self._daw_toolbar = DawToolbar(self._undo)
    self._daw_toolbar.undoRequested.connect(self._undo.undo)
    self._daw_toolbar.redoRequested.connect(self._undo.redo)
    self._daw_toolbar.configRequested.connect(self._on_open_config_dialog)
    self._daw_toolbar.playPauseRequested.connect(self._on_toolbar_play)
    self._daw_toolbar.fitRequested.connect(self._on_fit)
    self._daw_toolbar.zoomInRequested.connect(lambda: self._on_zoom_step(1.5))
    self._daw_toolbar.zoomOutRequested.connect(lambda: self._on_zoom_step(1/1.5))
    root.addWidget(self._daw_toolbar)
    main_h = QHBoxLayout(); main_h.setContentsMargins(0,0,0,0); main_h.setSpacing(0)
    left_col = QVBoxLayout(); left_col.setContentsMargins(0,0,0,0); left_col.setSpacing(0)
    self._track_view = DawTrackView(self._selection)
    self._track_view.cueClicked.connect(self._on_cue_clicked)
    self._track_view.cueDoubleClicked.connect(self._on_open_prompt_edit_dialog)
    self._track_view.dragCommandIssued.connect(self._on_command_from_widget)
    self._track_view.rubberBandReleased.connect(self._on_rubber_band)
    self._track_view.contextMenuRequested.connect(self._on_context_menu)
    self._track_view.playheadDragged.connect(self._on_track_playhead_dragged)
    self._scrollbar = QScrollBar(Qt.Horizontal)
    self._scrollbar.setRange(0, 1000)
    self._scrollbar.valueChanged.connect(
        lambda v: self._track_view.set_scroll_offset(v / 1000.0))
    self._minimap = DawMinimap()
    self._minimap.viewportRequested.connect(
        lambda off: self._scrollbar.setValue(int(off * 1000)))
    left_col.addWidget(self._track_view, 1)
    left_col.addWidget(self._scrollbar)
    left_col.addWidget(self._minimap)
    from PySide6.QtWidgets import QWidget
    left_w = QWidget(); left_w.setLayout(left_col)
    main_h.addWidget(left_w, 1)
    self._inspector_container = QWidget()
    self._inspector_container.setFixedWidth(280)
    ic_lay = QVBoxLayout(self._inspector_container); ic_lay.setContentsMargins(0,0,0,0)
    self._current_inspector = EmptyInspector()
    ic_lay.addWidget(self._current_inspector)
    main_h.addWidget(self._inspector_container)
    main_w = QWidget(); main_w.setLayout(main_h)
    root.addWidget(main_w, 1)
    self._selection.changed.connect(self._refresh_inspector)
```

**`_setup_shortcuts`** (9 个快捷键):
```python
def _setup_shortcuts(self):
    from PySide6.QtGui import QShortcut, QKeySequence
    QShortcut(QKeySequence(Qt.Key_Space), self, self._on_toolbar_play)
    QShortcut(QKeySequence(Qt.Key_R), self, self._on_regen_selected)
    QShortcut(QKeySequence(Qt.Key_Delete), self, self._on_delete_selected)
    QShortcut(QKeySequence(QKeySequence.Undo), self, self._undo.undo)
    QShortcut(QKeySequence(QKeySequence.Redo), self, self._undo.redo)
    QShortcut(QKeySequence(QKeySequence.SelectAll), self, self._on_select_all)
    QShortcut(QKeySequence(Qt.Key_Escape), self, self._selection.clear)
    QShortcut(QKeySequence(Qt.Key_Home), self,
              lambda: self._video_preview.seek(0.0))
    QShortcut(QKeySequence(Qt.Key_End), self,
              lambda: self._video_preview.seek(
                  self._track_view._duration if self._track_view else 0))
    QShortcut(QKeySequence("+"), self, lambda: self._on_zoom_step(1.5))
    QShortcut(QKeySequence("-"), self, lambda: self._on_zoom_step(1/1.5))
```

**`_refresh_inspector`**:
```python
def _refresh_inspector(self):
    from drama_shot_master.ui.widgets.daw.inspector import (
        EmptyInspector, BgmInspector, SfxInspector, DialogueInspector,
    )
    refs = self._selection.get()
    new_insp = None
    if len(refs) != 1:
        new_insp = EmptyInspector()
    else:
        ref = refs[0]
        if ref.track == "bgm":
            insp = BgmInspector()
            insp.set_cue_ref(ref, self._session)
            insp.regenerateRequested.connect(self._on_regen_one)
            insp.promptEditRequested.connect(self._on_open_prompt_edit_dialog)
            insp.candidateChosen.connect(self._on_inspector_candidate_chosen)
            new_insp = insp
        elif ref.track == "sfx":
            insp = SfxInspector()
            insp.set_cue_ref(ref, self._sfx_session)
            insp.regenerateRequested.connect(self._on_sfx_regen_one_inspector)
            insp.promptEditRequested.connect(self._on_open_prompt_edit_dialog)
            insp.candidateChosen.connect(self._on_inspector_candidate_chosen)
            insp.commandIssued.connect(self._on_command_from_widget)
            new_insp = insp
        elif ref.track == "dialogue":
            insp = DialogueInspector()
            timeline = self._dialogue_timeline_for_current_mp4()
            insp.set_cue_ref(ref, timeline)
            new_insp = insp
        else:
            new_insp = EmptyInspector()
    self._swap_inspector(new_insp)

def _swap_inspector(self, new):
    lay = self._inspector_container.layout()
    while lay.count():
        old = lay.takeAt(0).widget()
        if old: old.deleteLater()
    self._current_inspector = new
    lay.addWidget(new)
```

**键盘 + 命令路径**:
```python
def keyPressEvent(self, ev):
    # 让 QShortcut 处理；同时支持 widget 内部局部键（如果需要）
    super().keyPressEvent(ev)

def _on_command_from_widget(self, cmd):
    self._undo.push(cmd)
    self._persist_session()
    self._refresh_track_view()    # 重画

def _on_delete_selected(self):
    refs = self._selection.get()
    if not refs: return
    from drama_shot_master.ui.widgets.daw.commands import DeleteCue
    # skip dialogue refs
    refs = [r for r in refs if r.track in ("bgm", "sfx")]
    if not refs: return
    cmd = DeleteCue(self._session, self._sfx_session, refs)
    self._undo.push(cmd)
    self._persist_session(); self._refresh_track_view()

def _on_select_all(self):
    from drama_shot_master.ui.widgets.daw.selection import _CueRef
    refs = []
    if self._session:
        refs += [_CueRef("bgm", i) for i, _ in enumerate(self._session.segments)]
    if self._sfx_session:
        refs += [_CueRef("sfx", i)
                 for i, s in enumerate(self._sfx_session.shots)
                 if getattr(s, "enabled", True) and s.status == "generated"]
    self._selection.set(refs)

def _on_regen_selected(self):
    # 多 cue 并发重生：按 track 分组 → 调对应 facade
    by_track = self._selection.by_track()
    for idx in by_track.get("bgm", []):
        self._on_regenerate(idx)
    for idx in by_track.get("sfx", []):
        self._on_sfx_regenerate_one(idx)

def _on_open_prompt_edit_dialog(self, ref):
    from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
    from drama_shot_master.ui.widgets.daw.commands import ChangePrompt
    initial = ""
    if ref.track == "bgm" and self._session:
        initial = getattr(self._session.segments[ref.seg_index],
                          "music_prompt", "") or ""
    elif ref.track == "sfx" and self._sfx_session:
        initial = self._sfx_session.shots[ref.seg_index].prompt_short or ""
    title = f"{ref.track.upper()} 段 {ref.seg_index} prompt"
    dlg = PromptEditDialog(initial, title, self)
    if dlg.exec() == dlg.Accepted:
        new_prompt = dlg.to_payload()
        if new_prompt != initial:
            cmd = ChangePrompt(self._session, self._sfx_session, ref, new_prompt)
            self._undo.push(cmd)
            self._persist_session(); self._refresh_inspector()
            self._refresh_track_view()

def _on_open_config_dialog(self):
    from drama_shot_master.ui.dialogs.config_dialog import ConfigDialog
    initial = {"mp4": self._task.get("mp4", ""),
               "style": self._task.get("style", ""),
               "output_dir": self._task.get("output_dir", "")}
    dlg = ConfigDialog(initial, self)
    if dlg.exec() == dlg.Accepted:
        p = dlg.to_payload()
        self._task.update(p)
        # 重 set_source
        src = self._resolve_video_source()
        if src and self._video_preview:
            self._video_preview.set_source(src)

def _persist_session(self):
    if self._session is not None:
        self._session.save(self._work_dir() / "session.json")
    if self._sfx_session is not None:
        self._sfx_session.save(self._work_dir() / "sfx_session.json")

def _refresh_track_view(self):
    # rebuild cues 并刷 track_view 和 minimap
    from drama_shot_master.ui.widgets.overview_timeline_model import (
        derive_video_cues, derive_bgm_cues, derive_sfx_cues,
        derive_dialogue_cues, derive_total_duration,
    )
    bgm_cues = derive_bgm_cues(self._session)
    sfx_cues = derive_sfx_cues(self._sfx_session)
    timeline = self._dialogue_timeline_for_current_mp4()
    dial_cues = derive_dialogue_cues(timeline)
    shot_bounds = []
    if self._session:
        shot_bounds = [float(s.t_end) for s in (self._session.segments or [])]
    video_dur = self._video_preview.duration() if self._video_preview else 0
    total = derive_total_duration(
        bgm_session=self._session, sfx_session=self._sfx_session,
        dialogue_audios=timeline, video_duration=video_dur)
    video_cues = derive_video_cues(shot_bounds, total)
    cues = video_cues + bgm_cues + sfx_cues + dial_cues
    self._track_view.set_duration(total)
    self._track_view.set_cues(cues)
    self._minimap.set_duration(total)
    self._minimap.set_cues(cues)

def _dialogue_timeline_for_current_mp4(self):
    mp4 = str(self._task.get("mp4", "")).strip()
    for t in (getattr(self.cfg, "video_tasks", []) or []):
        if str(t.get("last_result", "")) == mp4:
            return t.get("timeline")
    return None
```

**`_try_load_existing`** 适配:
```python
def _try_load_existing(self):
    from sound_track_agent import facade
    sess = facade.load_session(self._work_dir())
    if sess is not None:
        self._session = sess
    from sound_track_agent.sfx import facade as sfx_fac
    try:
        sfx_sess = sfx_fac.load_sfx_session(self._work_dir())
    except Exception:
        sfx_sess = None
    if sfx_sess is not None:
        self._sfx_session = sfx_sess
    src = self._resolve_video_source()
    if src and self._video_preview:
        self._video_preview.set_source(src)
    self._refresh_track_view()
```

工作时切记保留 worker 接线：`_on_done` / `_on_sfx_generate_done` 等末尾调 `self._refresh_track_view()`（不再用 `_mount_session_tabs` / `_rebuild_sfx_review`）。

- [ ] **Step 10.6: 删退役方法 + 提交**

退役（删除）：`_build_config_tab` / `_build_sfx_tab` / `_mount_session_tabs` / `_rebuild_sfx_review` / `_on_chosen_changed` (替换为 inspector) / 原 `_on_overview_cue_clicked` 的 tab 切换部分

```bash
python -m pytest tests/test_ui/test_soundtrack_editor_daw_smoke.py -q
git add drama_shot_master/ui/widgets/soundtrack_editor.py \
        tests/test_ui/test_soundtrack_editor_daw_smoke.py
git commit -m "feat(4c): SoundtrackEditor 主区改 DAW (4 tab 消失 + Inspector + 撤销栈 + 9 快捷键)

- 删 4 tab 体系（_build_config_tab/_build_sfx_tab/_mount_session_tabs 等）
- 加 DawToolbar / DawTrackView / DawMinimap / Inspector 容器
- 9 快捷键 (Space/R/Del/Ctrl-Z/Y/Ctrl-A/Esc/Home/End/+/-)
- ConfigDialog 弹窗（替代原 配置 tab）
- PromptEditDialog 弹窗（双击 cue 改 prompt）
- selection.changed → Inspector 模板切换
- _on_done / _on_sfx_generate_done 末尾 _refresh_track_view 替代 mount

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: 收尾验证 + 退役文件清理

- [ ] **Step 11.1: 全套回归**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
python -m pytest tests/test_sound_track_agent/ tests/test_ui/ tests/test_config/ \
                 tests/test_core/ -q -p no:faulthandler 2>&1 | tail -8
```
Expected: 全绿（~430+ 用例：Sprint 0 + 4a + 4b + 4c 新增 ~70 个）

**注**：旧 `tests/test_ui/test_soundtrack_editor_smoke.py` 等基于 tab 的测试**预期会大量 FAIL**（4 tab 消失了）。这是预期。对这些测试**逐个 audit**：

- 与 4 tab 强耦合的测试（如 `test_editor_is_qwidget_with_three_tabs` / `_mount_session_tabs` / SFX tab smoke）**标记为 xfail 或删除**
- 与具体功能逻辑相关的测试（如 export 流程 / preview 启用切换 / volume bug）保留

具体处理（implementer 决定）：
- `tests/test_ui/test_soundtrack_editor_smoke.py` 部分用例 xfail 或 mark @pytest.mark.skip with reason "Phase 4c: 主区改 DAW"
- `tests/test_ui/test_soundtrack_editor_sfx_tab_smoke.py` 全文件 xfail（SFX tab 不存在了）
- `tests/test_ui/test_soundtrack_editor_overview_smoke.py` 保留（顶部预览 4b 未动）
- `tests/test_ui/test_overview_preview_mutex.py` 适配（review widget 不再 mount，preview 互斥需通过 inspector 或别的路径）

- [ ] **Step 11.2: 退役测试标记 + 提交**

```bash
# 示例：把 SFX tab smoke 全文件标 skip
sed -i '1i import pytest\npytestmark = pytest.mark.skip(reason="Phase 4c: SFX tab 已退役")\n' \
    tests/test_ui/test_soundtrack_editor_sfx_tab_smoke.py
# 其它逐文件 audit ...
git add tests/test_ui/
git commit -m "chore(4c): 退役测试标记 (4 tab 体系已被 DAW 替换)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 11.3: 手工 e2e 验证**（按 spec §6 验收 1-10 逐条）

1. SoundtrackEditor 打开，主区是多轨时间轴 ✓
2. 拖 BGM cue 边界改时长 ✓
3. 拖 BGM cue 中心整体平移 ✓
4. 双击 cue 弹 PromptEditDialog 改 prompt ✓
5. 右键 cue 弹菜单含 split / duplicate / delete ✓
6. Ctrl-Z 撤销 / Ctrl-Y 重做 ✓
7. 多选：Ctrl+click 逐个选 + Shift+drag 选区 ✓
8. 9 快捷键全部触发对应路径 ✓
9. 撤销栈深度 100 截断不崩 ✓
10. BGM/SFX 生成完成 → timeline 更新 ✓
11. 试听互斥（4b 行为保留）✓

如有任一项不通过，回到对应 Task 修复。

- [ ] **Step 11.4: 路线图归档**

更新 `docs/superpowers/specs/2026-05-29-soundtrack-phase4-sfx-daw-roadmap-design.md` §0.3 验收表，标 4c 完成 ✓：

```bash
sed -i 's/| \*\*4c 完成\*\*/| **4c 完成** ✅/' \
    docs/superpowers/specs/2026-05-29-soundtrack-phase4-sfx-daw-roadmap-design.md
git add docs/superpowers/specs/2026-05-29-soundtrack-phase4-sfx-daw-roadmap-design.md
git commit -m "docs: Phase 4 路线图 4c 完成标记 ✅

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 11.5: 走 finishing-a-development-branch**

按用户既往习惯（Sprint 0 / 4a / 4b 各自选项）询问：merge 到 main / 推 origin / 保留本地 / discard。

---

## 收尾验证（全部任务完成后）

按 spec §6 验收 10 条逐项 ✓。
