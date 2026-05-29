# Phase 4c DAW 多轨编辑器（Inspector + 撤销栈 + 多选 + 9 快捷键）设计

**日期**：2026-05-29
**作者**：sound_track_agent 维护者
**状态**：设计稿，待用户确认

> 路线图位置：Phase 4a（SFX 后端+P1 卡片）✅ → Phase 4b（顶部预览 VideoPreview+OverviewTimeline）✅ → **本 4c**（主区改 DAW 多轨编辑器，3-4 周）
> 上游 spec：
> - `docs/superpowers/specs/2026-05-29-soundtrack-phase4-sfx-daw-roadmap-design.md` §0.3 4c 验收
> - `docs/superpowers/specs/2026-05-29-soundtrack-phase4b-overview-timeline-design.md` §1-§3（4b 顶部预览，4c 保留不变）

---

## §1 架构 + 组件

### §1.1 整体布局（全 DAW 替换）

```
SoundtrackEditor (浮出窗，全屏推荐)
├── 顶部预览区 (~320px，4b 保留)
│   ├── VideoPreviewWidget
│   └── OverviewTimeline (4b minimap 作用)
├── 工具栏 (~32px，新建 DawToolbar)
│   ┌────────────────────────────────────────────────────────────────┐
│   │ [▶][⏮][⏭] [00:12.4/00:30] zoom[+ - ━●━ 35% FIT] [↶][↷] [⚙ 配置] │
│   └────────────────────────────────────────────────────────────────┘
├── 主时间轴 (flex 撑满，新建 DawTrackView)
│   ├── 时间刻度行
│   ├── 视频轨 (~36px)
│   ├── BGM 轨   (~40px)
│   ├── SFX 轨   (~36px)
│   ├── 对白轨   (~36px)
│   ├── 选区 RubberBand 透明高亮
│   ├── 多选 cue 边框高亮
│   └── 红色播放头
├── 横向 Scrollbar (~10px)
├── 3 轨 minimap (~30px，BGM/SFX/对白 + 蓝色窗口框)
└── 右侧 Inspector (~280px，模板按 cue 类型切换)
    └── BgmInspector / SfxInspector / DialogueInspector / EmptyInspector
```

### §1.2 新建 / 改动文件

```
drama_shot_master/ui/widgets/daw/                # NEW 子包
├── __init__.py
├── selection.py                                 # _CueRef + Selection model
├── commands.py                                  # 7 Command 类
├── undo_stack.py                                # UndoStack (max depth 100)
├── daw_track_view.py                            # 主 painted widget（4b OverviewTimeline 升级）
├── daw_minimap.py                               # 3 轨 minimap + 蓝窗（painted）
├── daw_toolbar.py                               # 工具栏 (播放/zoom/撤销/配置)
└── inspector/
    ├── __init__.py
    ├── empty_inspector.py                        # 无选中时的 placeholder
    ├── bgm_inspector.py
    ├── sfx_inspector.py
    └── dialogue_inspector.py                     # 只读

drama_shot_master/ui/widgets/soundtrack_editor.py # CHANGED 大改：删 4 tab，加 DAW 主区
drama_shot_master/ui/dialogs/config_dialog.py     # NEW: mp4 路径/风格/输出目录 弹窗
drama_shot_master/ui/dialogs/prompt_edit_dialog.py # NEW: BGM/SFX prompt 编辑弹窗（双击 cue 触发）

sound_track_agent/session.py                      # CHANGED 微小: SegmentScore 加 user_edited: bool = False
sound_track_agent/sfx/session.py                  # CHANGED 微小: SFXShot 加 user_edited: bool = False
```

退役（这些 widget 仍保留代码但不再用于 SoundtrackEditor 主区，留作其他场景或单测）：
- `SegmentReviewWidget`（BGM 试听卡片）
- `AccentEditorWidget`（卡点编辑）
- `SfxReviewWidget`（SFX 试听卡片）
- `_build_config_tab` / `_build_sfx_tab` / `_mount_session_tabs` 等

### §1.3 数据流核心约束

1. **复用 4a/4b 后端**：BGM ScoringSession / SFX SFXSession 数据模型零改动，除了加 `user_edited: bool = False` 字段（标记 cue 被用户手编辑过，用于将来"重新检测"时保留用户编辑）。mixdown / facade API / video_tasks 都不动。
2. **直接改 session 字段**：用户拖动 / 改 prompt → 直接改 `seg.t_start / seg.t_end / seg.music_prompt`（BGM）或 `shot.t_start / shot.duration / shot.prompt_short`（SFX）。**不引入 override layer**。改完 set `user_edited=True`。
3. **撤销栈是 UI 层概念**：每个 Command 记 (before_state, after_state) 序列化，**撤销时改回 in-memory 字段 + 立即落盘**。重启 SoundtrackEditor 时撤销栈清空（不持久化）。
4. **重生触发**：用户改 prompt / duration 后**不自动重生**；用户按 R 或 Inspector 点重生才触发。改 prompt 自动把该 cue 候选清空 + status="planned"，让用户主动重生。

---

## §2 数据流：12 个核心交互场景

| # | 用户操作 | 路径 | 是否进撤销栈 |
|---|----------|------|---|
| 1 | 单击 cue | `mousePressEvent → cue_at(x,y) → selection.set([cue])` → Inspector 切换类型 | 否 |
| 2 | Ctrl+click cue | `selection.toggle(cue)` | 否 |
| 3 | Shift+drag 空白 | RubberBand 模式 → release 时 `selection.set(cues_in_rect)` | 否 |
| 4 | Esc | `selection.clear()` | 否 |
| 5 | 拖动 cue 中心（≥4px 内非边界） | `MoveCue([cues], dt_sec)` → release 时 push 栈 | 是 |
| 6 | 拖动 cue 边界（±4px） | `ResizeCue(cue, side, dt_sec)` → release 时 push 栈 | 是 |
| 7 | 双击 cue | 弹 `BgmPromptDialog` / `SfxPromptDialog` → OK → `ChangePrompt(cue, new_prompt)` | 是 |
| 8 | 右键 cue → 重生 | `RegenerateCue(cue)` — 同 Inspector ↻ 按钮 → spawn worker | **否（worker 非可逆）** |
| 9 | 右键 cue → 拆分 | `SplitCue(cue, at_t=playhead)` → 拆为两段，新段 status="planned"，无候选 | 是 |
| 10 | 右键 cue → 复制 | `DuplicateCue(cue, offset=cue.duration)` → 在 cue 之后插一段（候选共享，seed 沿用） | 是 |
| 11 | Del 键 / 右键删除 | `DeleteCue([cues])` — 软删（设 `enabled=False` for SFX；BGM 设 `chosen_candidate=None` 且加 `disabled=True` 字段） | 是 |
| 12 | R 键（选中状态） | 选中 cue 全部进 batch worker，并发重生（max_concurrency 由 cfg.sfx_max_concurrency / cfg.soundtrack_max_concurrency 控制） | 否 |
| 13 | Ctrl-A | `selection.set_all_visible_cues()` | 否 |
| 14 | Home / End | 播放头跳 0 / total_duration | 否 |
| 15 | +/- 键 | zoom in/out × 1.5 倍 | 否 |
| 16 | Ctrl-Z / Y | `undo_stack.undo() / redo()` | — |

**跨轨拖动规则**：BGM cue 只能在 BGM 轨内移动；鼠标 Y 离开当前轨范围时 cue 卡在轨内。

---

## §3 模块设计（完整代码骨架）

### §3.1 Selection model (`daw/selection.py`)

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

    def __eq__(self, other) -> bool:
        return (isinstance(other, _CueRef)
                and self.track == other.track and self.seg_index == other.seg_index)

    def __hash__(self) -> int:
        return hash((self.track, self.seg_index))


class Selection(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._refs: set[_CueRef] = set()

    def get(self) -> list[_CueRef]:
        return sorted(self._refs, key=lambda r: (r.track, r.seg_index))

    def set(self, refs: list[_CueRef]) -> None:
        new = set(refs)
        if new != self._refs:
            self._refs = new
            self.changed.emit()

    def add(self, ref: _CueRef) -> None:
        if ref not in self._refs:
            self._refs.add(ref); self.changed.emit()

    def toggle(self, ref: _CueRef) -> None:
        if ref in self._refs:
            self._refs.discard(ref)
        else:
            self._refs.add(ref)
        self.changed.emit()

    def clear(self) -> None:
        if self._refs:
            self._refs.clear(); self.changed.emit()

    def by_track(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for r in self._refs:
            out.setdefault(r.track, []).append(r.seg_index)
        return out
```

### §3.2 Commands (`daw/commands.py`)

```python
"""7 类 Command + 撤销/重做。每个 Command 持有 (before, after) 状态。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


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
    """整体平移一组 cue（dt_sec 秒）。"""
    bgm_session: object
    sfx_session: object
    refs: list
    dt_sec: float

    def execute(self):
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None: continue
            cue.t_start += self.dt_sec
            if r.track == "bgm":
                cue.t_end += self.dt_sec
            cue.user_edited = True

    def undo(self):
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None: continue
            cue.t_start -= self.dt_sec
            if r.track == "bgm":
                cue.t_end -= self.dt_sec

    def describe(self):
        return f"Move {len(self.refs)} cue(s) by {self.dt_sec:.2f}s"


@dataclass
class ResizeCue(Command):
    """单 cue 改 边界（side='start' or 'end'，dt_sec 秒）。"""
    bgm_session: object
    sfx_session: object
    ref: object
    side: str
    dt_sec: float

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None: return
        if self.ref.track == "bgm":
            if self.side == "start":
                cue.t_start += self.dt_sec
            else:
                cue.t_end += self.dt_sec
        else:    # sfx: 改 duration
            if self.side == "start":
                cue.t_start += self.dt_sec
                cue.duration -= self.dt_sec
            else:
                cue.duration += self.dt_sec
        cue.user_edited = True

    def undo(self):
        # 反向 dt 重做一次
        self.dt_sec = -self.dt_sec
        self.execute()
        self.dt_sec = -self.dt_sec

    def describe(self):
        return f"Resize {self.ref.track} cue {self.side} by {self.dt_sec:.2f}s"


@dataclass
class DeleteCue(Command):
    """软删一组 cue：BGM 设 chosen_candidate=None + disabled=True；SFX 设 enabled=False。"""
    bgm_session: object
    sfx_session: object
    refs: list
    _backup: list = None

    def execute(self):
        self._backup = []
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None: continue
            if r.track == "bgm":
                self._backup.append((r, cue.chosen_candidate, getattr(cue, "disabled", False)))
                cue.chosen_candidate = None
                cue.disabled = True
            else:
                self._backup.append((r, None, cue.enabled))
                cue.enabled = False

    def undo(self):
        for r, prev_chosen, prev_disabled_or_enabled in (self._backup or []):
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None: continue
            if r.track == "bgm":
                cue.chosen_candidate = prev_chosen
                cue.disabled = prev_disabled_or_enabled
            else:
                cue.enabled = prev_disabled_or_enabled

    def describe(self):
        return f"Delete {len(self.refs)} cue(s)"


@dataclass
class ChangePrompt(Command):
    """改 cue 的 prompt 字段。自动清候选（重生前提）。"""
    bgm_session: object
    sfx_session: object
    ref: object
    new_prompt: str
    _old_prompt: str = ""
    _old_candidates: list = None
    _old_chosen: int = None
    _old_status: str = ""

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None: return
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
        if cue is None: return
        if self.ref.track == "bgm":
            cue.music_prompt = self._old_prompt
        else:
            cue.prompt_short = self._old_prompt
        cue.candidates = self._old_candidates or []
        cue.chosen_candidate = self._old_chosen
        cue.status = self._old_status

    def describe(self):
        return f"Change {self.ref.track} prompt"


@dataclass
class ChooseCandidate(Command):
    """改 cue.chosen_candidate."""
    bgm_session: object
    sfx_session: object
    ref: object
    new_idx: int
    _old_idx: int = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None: return
        self._old_idx = cue.chosen_candidate
        cue.chosen_candidate = self.new_idx

    def undo(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None: return
        cue.chosen_candidate = self._old_idx

    def describe(self):
        return f"Choose candidate {self.new_idx} for {self.ref.track}"


@dataclass
class SplitCue(Command):
    """在 at_t 处拆分 cue 为两段。新段（右半）清候选，status=planned/prompted。"""
    bgm_session: object
    sfx_session: object
    ref: object
    at_t: float
    _inserted_idx: int = None
    _old_t_end: float = None        # BGM 原 t_end
    _old_duration: float = None     # SFX 原 duration

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None: return
        from copy import deepcopy
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
        if self._inserted_idx is None: return
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None: return
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
    """复制 cue 在 cue 之后（偏移 cue.duration）。候选共享。"""
    bgm_session: object
    sfx_session: object
    ref: object
    _inserted_idx: int = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None: return
        from copy import deepcopy
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
        if self._inserted_idx is None: return
        if self.ref.track == "bgm":
            del self.bgm_session.segments[self._inserted_idx]
        else:
            del self.sfx_session.shots[self._inserted_idx]

    def describe(self):
        return "Duplicate cue"
```

### §3.3 UndoStack (`daw/undo_stack.py`)

```python
"""撤销栈：max depth 100；每 push 自动 execute。"""
from PySide6.QtCore import QObject, Signal
from drama_shot_master.ui.widgets.daw.commands import Command


class UndoStack(QObject):
    canUndoChanged = Signal(bool)
    canRedoChanged = Signal(bool)
    MAX_DEPTH = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._past: list[Command] = []
        self._future: list[Command] = []

    def push(self, cmd: Command) -> None:
        cmd.execute()
        self._past.append(cmd)
        if len(self._past) > self.MAX_DEPTH:
            self._past.pop(0)
        self._future.clear()
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def undo(self) -> None:
        if not self._past: return
        cmd = self._past.pop()
        cmd.undo()
        self._future.append(cmd)
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())

    def redo(self) -> None:
        if not self._future: return
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
        self._past.clear(); self._future.clear()
        self.canUndoChanged.emit(False); self.canRedoChanged.emit(False)
```

### §3.4 DawTrackView (`daw/daw_track_view.py`)

复用 4b OverviewTimeline 的 paintEvent 结构但**升级**：
- 轨道高度从 22px → 40px（BGM）/ 36px（其它）
- 加 `zoom: float` 字段（1.0=FIT，>1=放大）+ `scroll_offset: float`（0~1 of total_duration）
- 加 `selection` 字段引用 Selection 对象；选中 cue 边框白色 +外 2px 红框
- 加 `rubber_band: Optional[QRect]` 字段；mouseMove Shift 拖动时画矩形
- mousePressEvent 多识别一层"边界 ±4px → SizeHor cursor → resize mode"
- 信号：
  - `cueClicked(_CueRef, modifier=Qt.KeyboardModifier)` — Inspector 切换
  - `cueDoubleClicked(_CueRef)` — 触发 prompt dialog
  - `selectionRectChanged(QRect)` — RubberBand 拖动中
  - `selectionRectReleased(QRect, modifier)` — 释放
  - `dragCommandPending(Command)` — release 时 push 栈
  - `contextMenuRequested(_CueRef, QPoint)` — 右键

### §3.5 DawMinimap (`daw/daw_minimap.py`)

3 轨简化版（无文字，纯色块）：
- BGM/SFX/对白 各占 4px 高，色块全宽对应全片
- 蓝色窗口框 = current viewport（zoom + scroll 决定）
- 拖窗口框 → emit `viewportRequested(scroll_offset)` → DawTrackView 跟随
- 直接点 minimap → 同上

### §3.6 DawToolbar (`daw/daw_toolbar.py`)

```python
class DawToolbar(QWidget):
    playPauseRequested = Signal()
    stepBackRequested = Signal()
    stepForwardRequested = Signal()
    zoomRequested = Signal(float)        # 新 zoom 倍数
    fitRequested = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    configRequested = Signal()           # ⚙ 配置按钮 → 弹 ConfigDialog
    # widget: btn_play/btn_back/btn_fwd/time_label/btn_zoom_in/btn_zoom_out/zoom_slider/btn_fit/btn_undo/btn_redo/btn_config
```

### §3.7 Inspector 模板 (`daw/inspector/`)

每个 Inspector 是独立 QWidget，由 SoundtrackEditor 监听 `selection.changed` 切换。

```python
class EmptyInspector(QWidget):
    """显示 'No selection' 灰色文本。"""

class BgmInspector(QWidget):
    promptEditRequested = Signal()       # 点 prompt 区或双击 → 触发 dialog
    candidateChosen = Signal(int)        # 用户点候选按钮 → ChooseCandidate
    regenerateRequested = Signal()       # ↻ 按钮 → 触发 worker
    volumeChanged = Signal(float)        # 实时改 cue.volume，不入栈

    # widgets: time_label / prompt_label (truncated) / btn_edit_prompt
    #   / candidate_list (radio) / volume_slider / btn_regen
    def set_cue_ref(self, ref: _CueRef, bgm_session): ...

class SfxInspector(QWidget):
    # 同 BgmInspector 但加 duration_spin (1-15s)
    # 注：duration_spin.valueChanged → ResizeCue 命令（入栈）

class DialogueInspector(QWidget):
    """完全只读。显 audio_path / 时间 / 角色 (从文件名前缀派生) / 来源 = 配音智能体."""
```

### §3.8 SoundtrackEditor 大改

```python
class SoundtrackEditor(QWidget):
    def __init__(self, task, cfg, work_root, parent=None):
        super().__init__(parent)
        self._task = task; self.cfg = cfg; self._work_root = Path(work_root)
        self._worker = None
        self._sfx_worker = None
        self._session = None             # BGM ScoringSession
        self._sfx_session = None
        # 4b 已有
        self._video_preview = None
        self._overview_timeline = None
        # 4c 新
        self._toolbar = None
        self._track_view = None
        self._minimap = None
        self._inspector_container = None
        self._current_inspector = None
        self._selection = Selection(self)
        self._undo = UndoStack(self)
        self._build_ui()
        self._try_load_existing()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        # 顶部预览（4b 保留）
        from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget
        from drama_shot_master.ui.widgets.overview_timeline import OverviewTimeline
        self._video_preview = VideoPreviewWidget()
        self._overview_timeline = OverviewTimeline()
        root.addWidget(self._video_preview)
        root.addWidget(self._overview_timeline)
        # 工具栏
        from drama_shot_master.ui.widgets.daw.daw_toolbar import DawToolbar
        self._toolbar = DawToolbar(self._undo)
        self._toolbar.configRequested.connect(self._open_config_dialog)
        self._toolbar.undoRequested.connect(self._undo.undo)
        self._toolbar.redoRequested.connect(self._undo.redo)
        # ... 其它 toolbar signals
        root.addWidget(self._toolbar)
        # 主区 + Inspector 水平布局
        from drama_shot_master.ui.widgets.daw.daw_track_view import DawTrackView
        from drama_shot_master.ui.widgets.daw.daw_minimap import DawMinimap
        main_h = QHBoxLayout(); main_h.setContentsMargins(0,0,0,0); main_h.setSpacing(0)
        left_col = QVBoxLayout(); left_col.setContentsMargins(0,0,0,0); left_col.setSpacing(0)
        self._track_view = DawTrackView(self._selection)
        self._minimap = DawMinimap()
        scrollbar = QScrollBar(Qt.Horizontal)
        left_col.addWidget(self._track_view, 1)
        left_col.addWidget(scrollbar)
        left_col.addWidget(self._minimap)
        left_w = QWidget(); left_w.setLayout(left_col)
        main_h.addWidget(left_w, 1)
        # Inspector 区
        self._inspector_container = QWidget()
        self._inspector_container.setFixedWidth(280)
        ic_lay = QVBoxLayout(self._inspector_container)
        ic_lay.setContentsMargins(0,0,0,0)
        from drama_shot_master.ui.widgets.daw.inspector import EmptyInspector
        self._current_inspector = EmptyInspector()
        ic_lay.addWidget(self._current_inspector)
        main_h.addWidget(self._inspector_container)
        root.addLayout(main_h, 1)
        # 连 signals
        self._selection.changed.connect(self._refresh_inspector)
        # 接 4b 现有信号 (video_preview <-> overview_timeline 已在 4b 实现)
        # ...

    def _refresh_inspector(self):
        refs = self._selection.get()
        if len(refs) != 1:
            new_insp = EmptyInspector()
        else:
            ref = refs[0]
            if ref.track == "bgm":
                from drama_shot_master.ui.widgets.daw.inspector import BgmInspector
                new_insp = BgmInspector()
                new_insp.set_cue_ref(ref, self._session)
            elif ref.track == "sfx":
                from drama_shot_master.ui.widgets.daw.inspector import SfxInspector
                new_insp = SfxInspector()
                new_insp.set_cue_ref(ref, self._sfx_session)
            elif ref.track == "dialogue":
                from drama_shot_master.ui.widgets.daw.inspector import DialogueInspector
                new_insp = DialogueInspector()
                new_insp.set_cue_ref(ref, self.cfg.video_tasks, self.mp4_path)
            else:
                new_insp = EmptyInspector()
        self._swap_inspector(new_insp)

    # ... 大量 method 略
```

---

## §4 错误处理

| 风险 | 缓解 |
|------|------|
| 撤销栈 vs session.json 不一致（外部进程改 json） | 启动时 `session.load → undo_stack.clear()`；切换任务时也 clear |
| 用户拖 cue 与 worker 重生竞争 | worker 期间 `daw_track_view.setEnabled(False)` + 状态条提示 |
| 跨轨拖动 cue 类型不匹配 | DawTrackView 限制 Y 到当前轨；mouseMove 时 cue ghost 留在原轨 |
| painted widget 长视频 zoom 卡顿 | 只画可视窗口 cue（viewport culling）；zoom 上限 50x |
| 改 prompt 后旧缓存指错 | `ChangePrompt.execute()` 自动清 candidates + status="planned"/"prompted"；用户必须 R 重生 |
| SplitCue undo 复杂（要还原边界 + 删插入元素） | 备份原 cue.t_end / duration + 备份 inserted_idx；undo 时还原 + del |
| Inspector 弹 dialog 时用户拖 cue | dialog 非 modal，但 modal 关闭前 timeline 仍可操作（Premiere 风格） |
| 多选包含 dialogue cue（对白只读） | R 键时 skip dialogue refs；Del 键也 skip |
| 候选下载到一半改 prompt | worker 写候选时检查 `cue.user_edited and cue.status != "generated"` → 丢弃下载结果 |

---

## §5 测试策略

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_ui/daw/test_selection.py` | 6 | _CueRef 相等性 / set/add/toggle/clear / by_track / changed signal |
| `tests/test_ui/daw/test_undo_stack.py` | 6 | push execute / undo / redo / MAX_DEPTH 截断 / clear / signals |
| `tests/test_ui/daw/test_commands_move.py` | 4 | MoveCue 单/多 cue / BGM vs SFX 字段差异 / undo 还原 |
| `tests/test_ui/daw/test_commands_resize.py` | 4 | start/end 边界 / BGM (t_start/t_end) vs SFX (t_start/duration) / undo |
| `tests/test_ui/daw/test_commands_delete.py` | 3 | 软删 BGM (chosen=None+disabled) / SFX (enabled=False) / undo |
| `tests/test_ui/daw/test_commands_split.py` | 3 | BGM split / SFX split / 边界检查 |
| `tests/test_ui/daw/test_commands_duplicate.py` | 2 | BGM / SFX 复制 + undo 删插入 |
| `tests/test_ui/daw/test_commands_change_prompt.py` | 3 | BGM/SFX prompt 改 + 清候选 + status 变 + undo 还原 |
| `tests/test_ui/daw/test_commands_choose_candidate.py` | 2 | 改 chosen + undo |
| `tests/test_ui/daw/test_daw_track_view_smoke.py` | 12 | 构造不崩 / paintEvent / 单击 / Ctrl+click / Shift+drag rubber band / cue 拖 / 边界 resize / 双击 / 右键 / 跨轨限制 / zoom / scroll |
| `tests/test_ui/daw/test_daw_minimap_smoke.py` | 4 | paintEvent / 拖窗口框 / 点击 seek / 窗口框跟随 viewport |
| `tests/test_ui/daw/test_daw_toolbar_smoke.py` | 4 | 各按钮 emit / zoom slider / 配置按钮 → emit configRequested |
| `tests/test_ui/daw/test_inspector_bgm_smoke.py` | 3 | 控件齐 / candidateChosen emit / regenerateRequested emit |
| `tests/test_ui/daw/test_inspector_sfx_smoke.py` | 3 | 同 + duration_spin → ResizeCue |
| `tests/test_ui/daw/test_inspector_dialogue_smoke.py` | 2 | 只读 / 控件无编辑 widget |
| `tests/test_ui/test_soundtrack_editor_daw_smoke.py` | 6 | DAW 主区构造 / selection → Inspector 切换 / 撤销栈接线 / 9 快捷键各触发对应路径（精简到关键 4 个：space/R/Del/Ctrl-Z）/ 配置 dialog 弹出 |
| `tests/test_ui/dialogs/test_prompt_edit_dialog_smoke.py` | 3 | BGM 模式 / SFX 模式 / OK 触发 ChangePrompt |
| `tests/test_ui/dialogs/test_config_dialog_smoke.py` | 3 | mp4 路径 / 风格 / 输出目录 字段往返 |

**总估计 ~70 用例**。

---

## §6 验收标准（对照 spec §0.3 4c）

1. **主区是多轨时间轴** ✅ DawTrackView 替换原 tab+卡片，4 tab 消失
2. **拖动 BGM/SFX cue 边界改时长、整体平移** ✅ MoveCue + ResizeCue
3. **双击 cue 在 inspector 改 prompt** ✅ 双击弹 PromptEditDialog（非 inspector 内联 — 因 Inspector 显示截断 prompt + 编辑按钮路径更清晰）
4. **右键 cue 菜单含 split/duplicate/delete** ✅ 3 个 Command 全覆盖
5. **Ctrl-Z/Y 撤销重做覆盖所有 7 类命令** ✅ Move/Resize/Delete/Split/Duplicate/ChangePrompt/ChooseCandidate
6. **keyboard mapping 9 个快捷键** ✅ Space/R/Del/Ctrl-Z/Y/Ctrl-A/Esc/Home/End/+/-（顺带把 Home/End/+/- 也加上）
7. **多选**：Ctrl+click 单 cue 多选 + Shift+drag 拖框选区
8. **回归零**：4a/4b 现有测试 100% pass；BGM/SFX/对白 数据模型仅加 `user_edited: bool=False`（向后兼容默认）
9. **测试**：~70 新用例全绿
10. **手工 e2e**：拿一段已跑完 4a/4b 的视频打开新 SoundtrackEditor，确认能：选中 cue / 拖动 / 边界 resize / 双击改 prompt / R 重生 / Del 删 / Ctrl-Z 撤销 / 撤销栈深度 100 截断不崩

---

## §App A：Inspector 字段映射表

| Inspector | 字段 | 来源 | 编辑路径 |
|---|---|---|---|
| BgmInspector | 时间 (read) | `seg.t_start/t_end` | 拖 cue 改时间 |
| | prompt 截断显示 | `seg.music_prompt` | 双击 cue 弹 dialog |
| | 候选列表（radio） | `seg.candidates / chosen_candidate` | radio click → ChooseCandidate |
| | 音量 slider | `seg.volume` | 实时改不入栈 |
| | ↻ 重生按钮 | — | spawn batch_generator.generate_one |
| SfxInspector | 时间 + 时长 spin | `shot.t_start / shot.duration` | spin valueChanged → ResizeCue |
| | prompt_short 截断显示 | `shot.prompt_short` | 双击 cue 弹 dialog |
| | 候选列表 | `shot.candidates / chosen_candidate` | radio → ChooseCandidate |
| | 音量 slider | `shot.volume` | 实时改不入栈 |
| | 启用 checkbox | `shot.enabled` | toggle → DeleteCue / 反向 |
| | ↻ 重生按钮 | — | spawn sfx.batch_generator.generate_one |
| DialogueInspector | 文件名 (read) | `audio_path` | 不可改 |
| | 时间 (read) | `start_frame/fps / length_frames/fps` | 不可改 |
| | 角色 (read) | `audio_path basename split('_')[1]` 推断 | 不可改 |
| | 来源标签 | "配音智能体" | 不可改 |

## §App B：与 4a / 4b 的关系

**与 4a**：复用所有后端（BGM facade / SFX facade / mixdown / RunningHub）。数据模型加 1 字段 `user_edited: bool = False`（dataclass 默认值，向后兼容旧 session.json）。

**与 4b**：顶部预览区（VideoPreviewWidget + OverviewTimeline）**完全保留**。OverviewTimeline 在 4c 里**同时作为 minimap 使用**（4c 的 3 轨 minimap 与之共享相同的"概览"语义；如果觉得功能重复，4c 可以**省略底部 minimap**，让顶部 OverviewTimeline 作为唯一 minimap）。这是 implementer 在 plan 阶段可以做的简化决策。

**与可能的 Phase 4d**（如有）：4c 终态已经达到 ACE Studio / Premiere 的核心 SFX 操作能力。后续可考虑：
- AI 自动卡点（detect_accents 集成到 timeline 上画 marker）
- 音波形显示（cue 内画 waveform 而不是色块）
- 多 take 候选试听（A/B 对比模式）
- 自动导出多版本（不同候选组合）
