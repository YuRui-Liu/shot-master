# 成片合成 · 转场拼接 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「视频后期」新增「成片」tab：导入 RunningHub 产出的 mp4 片段 → 看片剔除/拖拽排序/头尾 trim → 一键 ffmpeg `xfade`(视频)+`acrossfade`(音频，保留原音)拼接成一条成片 mp4 → 可送去配乐。

**Architecture:** 纯逻辑层（`CompositionModel`/`ComposeTaskStore`/`transition_render`/`ffmpeg_locate`，零 Qt、可单测）+ UI 层（`compose_panel` 复用 `TaskWorkspacePage`/`VideoPreviewWidget`/`FunctionWorker`，新增 3 个 compose 子控件）。本期**不含 CV**（v2 再加），转场用默认/逐切口手动选。

**Tech Stack:** Python 3.10+，PySide6，ffmpeg(随包) `xfade`/`acrossfade`/`ffprobe`，pytest（`QT_QPA_PLATFORM=offscreen`）。

参考：设计规范 `docs/superpowers/specs/2026-05-31-compose-transition-design.md`；UI mockup `docs/explorer/成片合成-layout.html`。

> **运行/测试约定（本仓库）**：启动 `python drama_shot_master/main.py`；UI 测试前置 `QT_QPA_PLATFORM=offscreen`。真机外观渲染用 PowerShell（Bash 侧 Qt 无字体/非 windows11 style）。

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `drama_shot_master/core/composition_model.py` | `ReelClip`/`CompositionModel` 数据模型 |
| 新建 | `drama_shot_master/core/compose_task_store.py` | `ComposeTask`/`ComposeTaskStore`（镜像 `video_task_store`）|
| 新建 | `drama_shot_master/core/ffmpeg_locate.py` | 解析随包 ffmpeg/ffprobe 绝对路径 + 时长探测 |
| 新建 | `drama_shot_master/core/transition_render.py` | `XFADE_EFFECTS` 常量 + filter_complex 构建 + 渲染执行 |
| 修改 | `drama_shot_master/config.py` | 新增 `compose_tasks`（3 处）|
| 修改 | `drama_shot_master/ui/nav_config.py` | `VIDEOPOST_TABS`/`FUNCS`/`TASK_KEYS`/`ICONS` 加 compose |
| 新建 | `drama_shot_master/ui/widgets/compose/clip_strip.py` | 片段走马灯（卡片+保留切换+排序+切口圆点）|
| 新建 | `drama_shot_master/ui/widgets/compose/trim_bar.py` | 缩略图刷条 + 双手柄入/出点 |
| 新建 | `drama_shot_master/ui/widgets/compose/transition_inspector.py` | 切口转场编辑器 |
| 新建 | `drama_shot_master/ui/panels/compose_panel.py` | 成片编辑器（组装上面 3 件 + 预览 + 渲染条）|
| 新建 | `drama_shot_master/ui/panels/compose_task_manager_panel.py` | 成片任务列表（镜像 `video_task_manager_panel`）|
| 修改 | `drama_shot_master/ui/app_shell.py` | `_make_compose_page` + builders + 信号接线 |
| 修改 | `build/drama_shot_master.spec` | 随包 ffmpeg/ffprobe |
| 新建 | `tests/test_core/test_composition_model.py` | 模型单测 |
| 新建 | `tests/test_core/test_compose_task_store.py` | 存储单测 |
| 新建 | `tests/test_core/test_ffmpeg_locate.py` | 定位单测 |
| 新建 | `tests/test_core/test_transition_render.py` | filter_complex/offset 单测 |
| 新建 | `tests/test_ui/test_compose_widgets.py` | UI offscreen 冒烟 |
| 修改 | `tests/test_ui/test_nav_config.py` | nav 回归 |

---

## Task 1: CompositionModel / ReelClip

**Files:**
- Create: `drama_shot_master/core/composition_model.py`
- Test: `tests/test_core/test_composition_model.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_core/test_composition_model.py
from drama_shot_master.core.composition_model import ReelClip, CompositionModel


def _clip(**kw):
    d = dict(path="/a.mp4", duration=8.0)
    d.update(kw)
    return ReelClip.new(**d)


def test_new_clip_has_id_and_defaults():
    c = _clip()
    assert c.clip_id
    assert c.keep is True
    assert c.in_point is None and c.out_point is None
    assert c.locked is False
    assert c.cv_scores == {}


def test_effective_prefers_user_then_auto_then_default():
    c = _clip(auto_transition="smoothleft", auto_duration=0.6)
    assert c.effective_transition() == "smoothleft"
    assert c.effective_duration() == 0.6
    c.user_transition = "dissolve"
    c.user_duration = 0.9
    assert c.effective_transition() == "dissolve"
    assert c.effective_duration() == 0.9
    d = _clip()  # 无 auto/user
    assert d.effective_transition() == "dissolve"
    assert d.effective_duration() == 0.5


def test_trimmed_duration():
    c = _clip(duration=10.0, in_point=1.5, out_point=8.0)
    assert c.trimmed_duration() == 6.5
    assert _clip(duration=10.0).trimmed_duration() == 10.0


def test_kept_clips_preserves_order_and_filters_dropped():
    m = CompositionModel(clips=[_clip(path="/0.mp4"), _clip(path="/1.mp4"), _clip(path="/2.mp4")])
    m.clips[1].keep = False
    kept = m.kept_clips()
    assert [c.path for c in kept] == ["/0.mp4", "/2.mp4"]


def test_reorder_clips():
    m = CompositionModel(clips=[_clip(path="/0.mp4"), _clip(path="/1.mp4")])
    ids = [m.clips[1].clip_id, m.clips[0].clip_id]
    m.reorder_clips(ids)
    assert [c.path for c in m.clips] == ["/1.mp4", "/0.mp4"]


def test_update_clip():
    m = CompositionModel(clips=[_clip()])
    cid = m.clips[0].clip_id
    m.update_clip(cid, keep=False, user_transition="fade")
    assert m.clips[0].keep is False
    assert m.clips[0].user_transition == "fade"


def test_validate_requires_at_least_one_kept():
    m = CompositionModel(clips=[_clip()])
    m.clips[0].keep = False
    ok, msg = m.validate()
    assert ok is False and "保留" in msg


def test_validate_flags_segment_shorter_than_transition():
    a = _clip(path="/0.mp4", duration=0.4, user_transition="dissolve", user_duration=0.5)
    b = _clip(path="/1.mp4", duration=5.0)
    m = CompositionModel(clips=[a, b])
    ok, msg = m.validate()
    # 不阻断（返回 ok=True）但 msg 含降级提示
    assert ok is True
    assert "硬切" in msg or "降级" in msg


def test_to_from_dict_roundtrip():
    m = CompositionModel(clips=[_clip(in_point=1.0), _clip(path="/1.mp4")], fps=30, width=1920, height=1080)
    m.clips[0].user_transition = "wipeleft"
    d = m.to_dict()
    m2 = CompositionModel.from_dict(d)
    assert m2.fps == 30 and m2.width == 1920
    assert [c.path for c in m2.clips] == ["/a.mp4", "/1.mp4"]
    assert m2.clips[0].in_point == 1.0
    assert m2.clips[0].user_transition == "wipeleft"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_core/test_composition_model.py -q`
Expected: ERROR `ModuleNotFoundError: ... composition_model`

- [ ] **Step 3: 实现**

```python
# drama_shot_master/core/composition_model.py
"""成片合成数据模型：有序片段 + 切口转场参数。Qt-free，可单测。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from secrets import token_hex

_DEFAULT_TRANSITION = "dissolve"
_DEFAULT_DURATION = 0.5
_DUR_MIN, _DUR_MAX = 0.3, 2.0


def _gen_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


@dataclass
class ReelClip:
    clip_id: str
    path: str
    keep: bool = True
    in_point: float | None = None
    out_point: float | None = None
    duration: float = 0.0                 # ffprobe 实测原时长（只读缓存）
    auto_transition: str | None = None    # v2 CV 推荐
    auto_duration: float | None = None
    user_transition: str | None = None    # 手动覆盖
    user_duration: float | None = None
    locked: bool = False
    cv_scores: dict = field(default_factory=dict)

    @classmethod
    def new(cls, path: str, duration: float = 0.0, **kw) -> "ReelClip":
        return cls(clip_id=_gen_id(), path=str(path), duration=float(duration), **kw)

    def effective_transition(self) -> str:
        return self.user_transition or self.auto_transition or _DEFAULT_TRANSITION

    def effective_duration(self) -> float:
        d = self.user_duration if self.user_duration is not None else self.auto_duration
        if d is None:
            d = _DEFAULT_DURATION
        return max(_DUR_MIN, min(_DUR_MAX, float(d)))

    def trimmed_duration(self) -> float:
        start = self.in_point or 0.0
        end = self.out_point if self.out_point is not None else self.duration
        return max(0.0, end - start)

    def to_dict(self) -> dict:
        return {
            "clip_id": self.clip_id, "path": self.path, "keep": self.keep,
            "in_point": self.in_point, "out_point": self.out_point,
            "duration": self.duration,
            "auto_transition": self.auto_transition, "auto_duration": self.auto_duration,
            "user_transition": self.user_transition, "user_duration": self.user_duration,
            "locked": self.locked, "cv_scores": self.cv_scores,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReelClip":
        return cls(
            clip_id=str(d.get("clip_id") or _gen_id()),
            path=str(d.get("path") or ""),
            keep=bool(d.get("keep", True)),
            in_point=d.get("in_point"),
            out_point=d.get("out_point"),
            duration=float(d.get("duration") or 0.0),
            auto_transition=d.get("auto_transition"),
            auto_duration=d.get("auto_duration"),
            user_transition=d.get("user_transition"),
            user_duration=d.get("user_duration"),
            locked=bool(d.get("locked", False)),
            cv_scores=d.get("cv_scores") or {},
        )


@dataclass
class CompositionModel:
    clips: list[ReelClip] = field(default_factory=list)
    fps: int = 30
    width: int = 1920
    height: int = 1080
    pix_fmt: str = "yuv420p"
    output_prefix: str = "compose"

    def kept_clips(self) -> list[ReelClip]:
        return [c for c in self.clips if c.keep]

    def get(self, clip_id: str) -> ReelClip | None:
        return next((c for c in self.clips if c.clip_id == clip_id), None)

    def reorder_clips(self, ordered_ids: list[str]) -> None:
        index = {c.clip_id: c for c in self.clips}
        self.clips = [index[i] for i in ordered_ids if i in index] + \
                     [c for c in self.clips if c.clip_id not in set(ordered_ids)]

    def update_clip(self, clip_id: str, **fields) -> None:
        c = self.get(clip_id)
        if c is None:
            return
        for k, v in fields.items():
            if hasattr(c, k):
                setattr(c, k, v)

    def validate(self) -> tuple[bool, str]:
        kept = self.kept_clips()
        if not kept:
            return False, "至少需要保留 1 个片段"
        warns = []
        for i, c in enumerate(kept[:-1]):  # 末段无切口
            if c.trimmed_duration() < c.effective_duration():
                warns.append(f"片段#{i+1} 时长不足转场时长，将降级为硬切")
        return True, ("；".join(warns) if warns else "ok")

    def to_dict(self) -> dict:
        return {
            "clips": [c.to_dict() for c in self.clips],
            "fps": self.fps, "width": self.width, "height": self.height,
            "pix_fmt": self.pix_fmt, "output_prefix": self.output_prefix,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CompositionModel":
        d = d or {}
        return cls(
            clips=[ReelClip.from_dict(x) for x in (d.get("clips") or [])],
            fps=int(d.get("fps") or 30),
            width=int(d.get("width") or 1920),
            height=int(d.get("height") or 1080),
            pix_fmt=str(d.get("pix_fmt") or "yuv420p"),
            output_prefix=str(d.get("output_prefix") or "compose"),
        )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_core/test_composition_model.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/composition_model.py tests/test_core/test_composition_model.py
git commit -m "feat(compose): CompositionModel/ReelClip 数据模型"
```

---

## Task 2: ComposeTaskStore

**Files:**
- Create: `drama_shot_master/core/compose_task_store.py`
- Test: `tests/test_core/test_compose_task_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_core/test_compose_task_store.py
from drama_shot_master.core.compose_task_store import ComposeTask, ComposeTaskStore


def test_add_get_update_remove():
    s = ComposeTaskStore()
    t = s.add("第一集 · 成片", {"clips": []})
    assert s.get(t.id) is t
    s.update(t.id, output_mp4="/out/compose_x.mp4", name="改名")
    assert s.get(t.id).output_mp4.endswith("compose_x.mp4")
    assert s.get(t.id).name == "改名"
    s.remove(t.id)
    assert s.get(t.id) is None


def test_to_from_list_roundtrip():
    s = ComposeTaskStore()
    s.add("A", {"clips": [{"clip_id": "1", "path": "/a.mp4"}]})
    data = s.to_list()
    s2 = ComposeTaskStore.from_list(data)
    assert s2.all()[0].name == "A"
    assert s2.all()[0].composition["clips"][0]["path"] == "/a.mp4"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_core/test_compose_task_store.py -q`
Expected: ERROR ModuleNotFoundError

- [ ] **Step 3: 实现**（镜像 `video_task_store.py`，字段换为 `composition`/`output_mp4`/`status`）

```python
# drama_shot_master/core/compose_task_store.py
"""成片任务数据模型 + 列表存储。Qt-free，镜像 video_task_store。"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from secrets import token_hex
from typing import Optional


def _gen_task_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


@dataclass
class ComposeTask:
    id: str
    name: str
    composition: dict          # CompositionModel.to_dict()
    status: str = "空闲"
    output_mp4: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "composition": self.composition,
                "status": self.status, "output_mp4": self.output_mp4,
                "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict) -> "ComposeTask":
        return cls(
            id=str(d.get("id") or _gen_task_id()),
            name=str(d.get("name") or "未命名成片"),
            composition=d.get("composition") or {},
            status=str(d.get("status") or "空闲"),
            output_mp4=str(d.get("output_mp4") or ""),
            updated_at=float(d.get("updated_at") or 0.0),
        )


class ComposeTaskStore:
    def __init__(self, tasks: Optional[list[ComposeTask]] = None):
        self._tasks: list[ComposeTask] = list(tasks or [])

    def all(self) -> list[ComposeTask]:
        return list(self._tasks)

    def get(self, task_id: str) -> Optional[ComposeTask]:
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, composition: dict) -> ComposeTask:
        t = ComposeTask(id=_gen_task_id(), name=name,
                        composition=copy.deepcopy(composition), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id: str, *, name: Optional[str] = None,
               composition: Optional[dict] = None, status: Optional[str] = None,
               output_mp4: Optional[str] = None) -> None:
        t = self.get(task_id)
        if t is None:
            return
        if name is not None:
            t.name = name
        if composition is not None:
            t.composition = copy.deepcopy(composition)
        if status is not None:
            t.status = status
        if output_mp4 is not None:
            t.output_mp4 = output_mp4
        t.updated_at = time.time()

    def remove(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def to_list(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks]

    @classmethod
    def from_list(cls, data: list[dict]) -> "ComposeTaskStore":
        return cls([ComposeTask.from_dict(d) for d in (data or [])])
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_core/test_compose_task_store.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/compose_task_store.py tests/test_core/test_compose_task_store.py
git commit -m "feat(compose): ComposeTaskStore 任务存储"
```

---

## Task 3: config.compose_tasks 持久化

**Files:**
- Modify: `drama_shot_master/config.py:54`（字段）、`:160`（to_dict）、`:345`（load）

- [ ] **Step 1: 加字段**（在 `video_tasks: list = field(default_factory=list)` 之后）

```python
    compose_tasks: list = field(default_factory=list)
```

- [ ] **Step 2: 加入 to_dict 落盘块**（在 `"video_tasks": self.video_tasks,` 之后）

```python
                "compose_tasks": self.compose_tasks,
```

- [ ] **Step 3: 加入 load 反序列化**（在 video_tasks 的 load 分支之后）

```python
                if "compose_tasks" in data and isinstance(data["compose_tasks"], list):
                    cfg.compose_tasks = data["compose_tasks"]
```

- [ ] **Step 4: 验证**

Run: `python -c "from drama_shot_master.config import Config; print(hasattr(Config(), 'compose_tasks'))"`
Expected: `True`

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/config.py
git commit -m "feat(compose): config 持久化 compose_tasks"
```

---

## Task 4: ffmpeg_locate（随包 ffmpeg 定位 + 时长探测）

**Files:**
- Create: `drama_shot_master/core/ffmpeg_locate.py`
- Test: `tests/test_core/test_ffmpeg_locate.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_core/test_ffmpeg_locate.py
import shutil
import pytest
from drama_shot_master.core import ffmpeg_locate as fl


def test_resolve_prefers_bundled(monkeypatch, tmp_path):
    exe = tmp_path / ("ffmpeg.exe")
    exe.write_text("x")
    monkeypatch.setattr(fl, "_bundled_dir", lambda: tmp_path)
    assert fl.ffmpeg_path() == str(exe)


def test_resolve_falls_back_to_which(monkeypatch, tmp_path):
    monkeypatch.setattr(fl, "_bundled_dir", lambda: tmp_path)  # 无 exe
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert fl.ffmpeg_path() == "/usr/bin/ffmpeg"


def test_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(fl, "_bundled_dir", lambda: tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        fl.ffmpeg_path()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_core/test_ffmpeg_locate.py -q`
Expected: ERROR ModuleNotFoundError

- [ ] **Step 3: 实现**

```python
# drama_shot_master/core/ffmpeg_locate.py
"""定位 ffmpeg/ffprobe：优先随包目录，回退系统 PATH，缺失抛错（不静默）。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _bundled_dir() -> Path:
    """随包二进制目录：PyInstaller(_MEIPASS)/Nuitka/源码态均落到 assets/bin。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets" / "bin"
    return Path(__file__).resolve().parent.parent / "assets" / "bin"


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _resolve(name: str) -> str:
    cand = _bundled_dir() / _exe(name)
    if cand.exists():
        return str(cand)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"未找到 {name}。请确认随包 assets/bin/{_exe(name)} 存在，或系统 PATH 中已安装 ffmpeg。")


def ffmpeg_path() -> str:
    return _resolve("ffmpeg")


def ffprobe_path() -> str:
    return _resolve("ffprobe")


def probe_duration(video_path: str) -> float:
    """ffprobe 取时长（秒）；失败返回 0.0（不抛，交由上层校验）。"""
    cmd = [ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
           "-of", "json", str(video_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
        data = json.loads(proc.stdout or b"{}")
        return float(data.get("format", {}).get("duration") or 0.0)
    except Exception:
        return 0.0
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_core/test_ffmpeg_locate.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/ffmpeg_locate.py tests/test_core/test_ffmpeg_locate.py
git commit -m "feat(compose): ffmpeg/ffprobe 定位与时长探测"
```

---

## Task 5: transition_render（XFADE_EFFECTS + filter_complex 构建 + 渲染）

**Files:**
- Create: `drama_shot_master/core/transition_render.py`
- Test: `tests/test_core/test_transition_render.py`

- [ ] **Step 1: 写失败测试**（聚焦纯函数：效果库 + filter_complex/offset；渲染执行不在单测内跑真 ffmpeg）

```python
# tests/test_core/test_transition_render.py
from drama_shot_master.core.composition_model import ReelClip, CompositionModel
from drama_shot_master.core import transition_render as tr


def _comp(durs, trans="dissolve", tdur=0.5):
    clips = []
    for i, d in enumerate(durs):
        clips.append(ReelClip.new(path=f"/c{i}.mp4", duration=d,
                                  user_transition=trans, user_duration=tdur))
    return CompositionModel(clips=clips, fps=30, width=1920, height=1080)


def test_effects_library_grouped_and_has_none():
    keys = {e["name"] for e in tr.XFADE_EFFECTS}
    assert "dissolve" in keys and "smoothleft" in keys and "none" in keys
    cats = {e["category"] for e in tr.XFADE_EFFECTS}
    assert {"universal", "directional", "creative", "cut"} <= cats


def test_offsets_use_measured_durations():
    # 三段 8/10/6，转场 0.5 → off0 = 8-0.5 = 7.5；off1 = (8+10)-2*0.5 = 17.0
    offs = tr.compute_offsets([8.0, 10.0, 6.0], [0.5, 0.5])
    assert offs == [7.5, 17.0]


def test_build_args_contains_xfade_and_acrossfade():
    comp = _comp([8.0, 6.0], trans="smoothleft", tdur=0.6)
    args = tr.build_ffmpeg_args(comp, out_path="/out/x.mp4",
                                ffmpeg="ffmpeg", probe=lambda p: 8.0)
    fc = " ".join(args)
    assert "xfade=transition=smoothleft:duration=0.6" in fc
    assert "acrossfade=d=0.6" in fc
    assert "scale=1920:1080" in fc and "fps=30" in fc and "format=yuv420p" in fc
    assert args[0] == "ffmpeg" and args[-1] == "/out/x.mp4"


def test_single_kept_clip_no_transition_just_normalize():
    comp = _comp([8.0])
    args = tr.build_ffmpeg_args(comp, out_path="/out/x.mp4",
                               ffmpeg="ffmpeg", probe=lambda p: 8.0)
    fc = " ".join(args)
    assert "xfade" not in fc        # 单段无切口
    assert "scale=1920:1080" in fc  # 仍归一化


def test_none_transition_degrades_to_cut():
    comp = _comp([8.0, 6.0], trans="none", tdur=0.5)
    args = tr.build_ffmpeg_args(comp, out_path="/out/x.mp4",
                               ffmpeg="ffmpeg", probe=lambda p: 8.0)
    fc = " ".join(args)
    assert "xfade" not in fc        # 硬切走 concat，不用 xfade
    assert "concat" in fc
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_core/test_transition_render.py -q`
Expected: ERROR ModuleNotFoundError

- [ ] **Step 3: 实现**

```python
# drama_shot_master/core/transition_render.py
"""成片渲染：由 CompositionModel 构建 ffmpeg(xfade+acrossfade) 参数并执行。Qt-free。

转场效果库 XFADE_EFFECTS 为 UI/渲染共用事实源（含类别 + 中文显示名）。
"""
from __future__ import annotations

import subprocess
from typing import Callable

from drama_shot_master.core.composition_model import CompositionModel

# 分类精选集（spec §6.2）。category: universal/directional/creative/cut
XFADE_EFFECTS = [
    {"name": "fade", "label": "淡入淡出", "category": "universal"},
    {"name": "fadeblack", "label": "黑场过渡", "category": "universal"},
    {"name": "fadewhite", "label": "白场过渡", "category": "universal"},
    {"name": "dissolve", "label": "叠化", "category": "universal"},
    {"name": "distance", "label": "距离溶解", "category": "universal"},
    {"name": "smoothleft", "label": "推进 ←", "category": "directional"},
    {"name": "smoothright", "label": "推进 →", "category": "directional"},
    {"name": "smoothup", "label": "推进 ↑", "category": "directional"},
    {"name": "smoothdown", "label": "推进 ↓", "category": "directional"},
    {"name": "slideleft", "label": "滑动 ←", "category": "directional"},
    {"name": "slideright", "label": "滑动 →", "category": "directional"},
    {"name": "wipeleft", "label": "擦除 ←", "category": "directional"},
    {"name": "wiperight", "label": "擦除 →", "category": "directional"},
    {"name": "circleopen", "label": "圆形展开", "category": "creative"},
    {"name": "circleclose", "label": "圆形收拢", "category": "creative"},
    {"name": "radial", "label": "径向", "category": "creative"},
    {"name": "zoomin", "label": "推近", "category": "creative"},
    {"name": "pixelize", "label": "像素化", "category": "creative"},
    {"name": "squeezev", "label": "纵向挤压", "category": "creative"},
    {"name": "none", "label": "硬切", "category": "cut"},
]


def compute_offsets(durations: list[float], trans_durs: list[float]) -> list[float]:
    """xfade 各切口 offset：off_i = Σdur[0..i] - Σt[0..i]。len = len(durations)-1。"""
    offs = []
    cum_d = 0.0
    cum_t = 0.0
    for i in range(len(durations) - 1):
        cum_d += durations[i]
        cum_t += trans_durs[i]
        offs.append(round(cum_d - cum_t, 3))
    return offs


def _norm_chain(idx: int, w: int, h: int, fps: int, pix: str) -> tuple[str, str]:
    """单段视频/音频归一化 filter 片段，返回 (video_label, audio_label) 表达式串。"""
    v = (f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},format={pix},setsar=1[v{idx}]")
    a = (f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo[a{idx}]")
    return v, a


def build_ffmpeg_args(comp: CompositionModel, out_path: str,
                      ffmpeg: str, probe: Callable[[str], float]) -> list[str]:
    """构建 ffmpeg 参数列表。probe(path)->秒 用于实测时长（注入便于单测）。

    - 视频 xfade + 音频 acrossfade 链；offset 用实测(trim 后)时长。
    - effective_transition == 'none' → 该切口硬切（整体降级为 concat，见下）。
    - 单段 → 仅归一化输出。
    """
    kept = comp.kept_clips()
    inputs: list[str] = []
    for c in kept:
        inputs += ["-i", c.path]

    # trim 后实测时长（无 in/out 用 probe 原时长）
    durs = []
    for c in kept:
        base = probe(c.path) or c.duration
        start = c.in_point or 0.0
        end = c.out_point if c.out_point is not None else base
        durs.append(max(0.01, end - start))

    w, h, fps, pix = comp.width, comp.height, comp.fps, comp.pix_fmt
    parts: list[str] = []
    vlabels, alabels = [], []
    for i, c in enumerate(kept):
        vexpr, aexpr = _norm_chain(i, w, h, fps, pix)
        # 注入 trim
        if c.in_point is not None or c.out_point is not None:
            ss = c.in_point or 0.0
            to = c.out_point if c.out_point is not None else durs[i] + ss
            vexpr = vexpr.replace(f"[{i}:v]", f"[{i}:v]trim=start={ss}:end={to},setpts=PTS-STARTPTS,")
            aexpr = aexpr.replace(f"[{i}:a]", f"[{i}:a]atrim=start={ss}:end={to},asetpts=PTS-STARTPTS,")
        parts.append(vexpr)
        parts.append(aexpr)
        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")

    n = len(kept)
    trans = [c.effective_transition() for c in kept[:-1]]
    tdurs = [c.effective_duration() for c in kept[:-1]]

    if n == 1:
        filter_complex = ";".join(parts)
        vmap, amap = "[v0]", "[a0]"
    elif all(t == "none" for t in trans):
        # 全硬切 → concat（仍保留归一化与原音）
        concat_in = "".join(vlabels[i] + alabels[i] for i in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=1[vout][aout]")
        filter_complex = ";".join(parts)
        vmap, amap = "[vout]", "[aout]"
    else:
        offs = compute_offsets(durs, tdurs)
        vcur, acur = vlabels[0], alabels[0]
        for i in range(1, n):
            t = trans[i - 1] if trans[i - 1] != "none" else "fade"
            d = tdurs[i - 1]
            off = offs[i - 1]
            vout = f"[vx{i}]" if i < n - 1 else "[vout]"
            aout = f"[ax{i}]" if i < n - 1 else "[aout]"
            parts.append(f"{vcur}{vlabels[i]}xfade=transition={t}:duration={d}:offset={off}{vout}")
            parts.append(f"{acur}{alabels[i]}acrossfade=d={d}{aout}")
            vcur, acur = vout, aout
        filter_complex = ";".join(parts)
        vmap, amap = "[vout]", "[aout]"

    return [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", vmap, "-map", amap,
        "-c:v", "libx264", "-pix_fmt", pix, "-c:a", "aac",
        out_path,
    ]


def render(comp: CompositionModel, out_path: str) -> str:
    """执行渲染（真调 ffmpeg）。成功返回 out_path，失败抛 RuntimeError。"""
    from drama_shot_master.core.ffmpeg_locate import ffmpeg_path, probe_duration
    args = build_ffmpeg_args(comp, out_path, ffmpeg=ffmpeg_path(), probe=probe_duration)
    proc = subprocess.run(args, capture_output=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode("utf-8", "ignore")[-800:]
        raise RuntimeError(f"ffmpeg 渲染失败：\n{tail}")
    return out_path
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_core/test_transition_render.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/transition_render.py tests/test_core/test_transition_render.py
git commit -m "feat(compose): transition_render — XFADE_EFFECTS + xfade/acrossfade filter_complex"
```

---

## Task 6: nav_config 接入 + 回归

**Files:**
- Modify: `drama_shot_master/ui/nav_config.py`
- Test: `tests/test_ui/test_nav_config.py`

- [ ] **Step 1: 写/改测试**（末尾追加）

```python
def test_compose_tab_in_videopost_first():
    from drama_shot_master.ui import nav_config as nc
    keys = [k for k, _ in nc.VIDEOPOST_TABS]
    assert keys[0] == "compose"
    assert "compose" in dict(nc.FUNCS).values()
    assert "compose" in nc.TASK_KEYS
    assert nc.stage_of("compose") in ("production", None) or "compose" in nc.PHASE_GATES
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ui/test_nav_config.py::test_compose_tab_in_videopost_first -q`
Expected: FAIL

- [ ] **Step 3: 改 nav_config**

`VIDEOPOST_TABS` 改为：
```python
VIDEOPOST_TABS = [
    ("compose", "成片"),
    ("dubbing", "配音"),
    ("soundtrack", "配乐"),
]
```
`FUNCS` 末尾加 `("成片", "compose")`。
`PHASES` 第 4 项改为 `("③ 视频出片", ["video_gen", "compose", "dubbing", "soundtrack"])`。
`TASK_KEYS` 改为含 `"compose"`：`TASK_KEYS = {"imggen", "video_gen", "soundtrack", "dubbing", "screenwriter", "compose"}`。
`ICONS` 加 `"compose": "video.svg"`。

- [ ] **Step 4: 运行确认通过（含既有 nav 测试不破）**

Run: `python -m pytest tests/test_ui/test_nav_config.py -q`
Expected: PASS（若既有 `test_screenwriter_in_phases_drama_prep` 仍是历史失败项，单独确认与本改动无关）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/nav_config.py tests/test_ui/test_nav_config.py
git commit -m "feat(compose): nav 接入「视频后期/成片」tab"
```

---

## Task 7: clip_strip 走马灯控件

**Files:**
- Create: `drama_shot_master/ui/widgets/compose/__init__.py`（空）
- Create: `drama_shot_master/ui/widgets/compose/clip_strip.py`
- Test: `tests/test_ui/test_compose_widgets.py`（本任务先建文件 + clip_strip 部分）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_compose_widgets.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def test_clip_strip_emits_signals():
    _app()
    from drama_shot_master.core.composition_model import ReelClip, CompositionModel
    from drama_shot_master.ui.widgets.compose.clip_strip import ClipStrip
    m = CompositionModel(clips=[ReelClip.new(path="/0.mp4", duration=8),
                                ReelClip.new(path="/1.mp4", duration=6)])
    strip = ClipStrip()
    strip.set_model(m)
    got = []
    strip.clipSelected.connect(lambda cid: got.append(("clip", cid)))
    strip.connectorSelected.connect(lambda i: got.append(("conn", i)))
    strip.keepToggled.connect(lambda cid, k: got.append(("keep", cid, k)))
    # 程序化触发（控件内部应提供这些方法供测试/交互复用）
    strip.select_clip(m.clips[0].clip_id)
    strip.select_connector(0)
    strip.toggle_keep(m.clips[1].clip_id)
    assert ("clip", m.clips[0].clip_id) in got
    assert ("conn", 0) in got
    assert ("keep", m.clips[1].clip_id, False) in got
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_clip_strip_emits_signals -q`
Expected: ERROR ModuleNotFoundError

- [ ] **Step 3: 实现**（横向滚动区：卡片 + 切口圆点；卡片可拖拽排序用 `QListWidget` 的 `InternalMove` 或自绘 + 拖放。v1 用 `QHBoxLayout` 容器 + 卡片控件，排序用「左移/右移」按钮或拖放；下面给出可工作骨架，布局对照 mockup）

```python
# drama_shot_master/ui/widgets/compose/clip_strip.py
"""片段走马灯：缩略图卡（保留切换/选中）+ 卡间转场切口圆点。

对照 docs/explorer/成片合成-layout.html。封面缩略图由外部 set_thumb(clip_id, QPixmap)
注入（抽帧在 panel 的后台线程做），本控件只负责布局与交互信号。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QScrollArea, QFrame, QVBoxLayout, QLabel, QToolButton,
)


class _ClipCard(QFrame):
    def __init__(self, clip, on_click, on_keep, on_grip_drag=None):
        super().__init__()
        self.clip = clip
        self.setObjectName("ComposeClipCard")
        self.setFixedWidth(128)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.thumb = QLabel(); self.thumb.setFixedHeight(152)
        self.thumb.setObjectName("ComposeClipThumb"); self.thumb.setAlignment(Qt.AlignCenter)
        self.keep_btn = QToolButton(self.thumb); self.keep_btn.setText("✓")
        self.keep_btn.setObjectName("ComposeKeepBtn"); self.keep_btn.move(6, 6)
        self.keep_btn.clicked.connect(lambda: on_keep(self.clip.clip_id))
        lay.addWidget(self.thumb)
        self.name = QLabel(clip.path.rsplit("/", 1)[-1]); self.name.setObjectName("ComposeClipName")
        lay.addWidget(self.name)
        self.mousePressEvent = lambda e: on_click(self.clip.clip_id)

    def set_selected(self, on: bool):
        self.setProperty("selected", on); self.style().unpolish(self); self.style().polish(self)

    def set_dropped(self, on: bool):
        self.setProperty("dropped", on); self.style().unpolish(self); self.style().polish(self)

    def set_thumb(self, pixmap):
        self.thumb.setPixmap(pixmap)


class _Connector(QToolButton):
    def __init__(self, index, label, on_click):
        super().__init__()
        self.index = index
        self.setObjectName("ComposeConnector")
        self.setText(label)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda: on_click(self.index))

    def set_selected(self, on: bool):
        self.setProperty("selected", on); self.style().unpolish(self); self.style().polish(self)


class ClipStrip(QWidget):
    clipSelected = Signal(str)       # clip_id
    connectorSelected = Signal(int)  # 切口 index（kept 序）
    keepToggled = Signal(str, bool)  # clip_id, new_keep
    orderChanged = Signal(list)      # 新的 clip_id 顺序（全量）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self._cards: dict[str, _ClipCard] = {}
        self._connectors: list[_Connector] = []
        self._sel_clip = None
        self._sel_conn = None
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        self._inner = QWidget(); self._row = QHBoxLayout(self._inner)
        self._row.setContentsMargins(4, 4, 4, 4); self._row.setSpacing(0)
        scroll.setWidget(self._inner)
        outer = QHBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)

    def set_model(self, model):
        self._model = model
        self._rebuild()

    def _rebuild(self):
        while self._row.count():
            it = self._row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._cards.clear(); self._connectors.clear()
        if not self._model:
            return
        kept = self._model.kept_clips()
        clips = self._model.clips
        # 卡片按全量顺序渲染（剔除卡变灰）；切口只在相邻保留片段间
        kept_index = {c.clip_id: i for i, c in enumerate(kept)}
        for ci, c in enumerate(clips):
            card = _ClipCard(c, self._emit_clip, self._emit_keep)
            card.set_dropped(not c.keep)
            self._cards[c.clip_id] = card
            self._row.addWidget(card)
            # 若该卡与下一个「保留卡」构成切口，加连接圆点
            if c.keep and c.clip_id in kept_index and kept_index[c.clip_id] < len(kept) - 1:
                idx = kept_index[c.clip_id]
                lbl = self._conn_label(kept[idx])
                conn = _Connector(idx, lbl, self._emit_conn)
                self._connectors.append(conn)
                self._row.addWidget(conn)
        self._row.addStretch(1)

    @staticmethod
    def _conn_label(clip) -> str:
        from drama_shot_master.core.transition_render import XFADE_EFFECTS
        name = clip.effective_transition()
        label = next((e["label"] for e in XFADE_EFFECTS if e["name"] == name), name)
        if name == "none":
            return "▭"
        return f"{label}\n{clip.effective_duration()}s"

    # —— 交互（也供测试程序化触发）——
    def select_clip(self, clip_id: str):
        self._set_sel_clip(clip_id); self.clipSelected.emit(clip_id)

    def select_connector(self, index: int):
        self._set_sel_conn(index); self.connectorSelected.emit(index)

    def toggle_keep(self, clip_id: str):
        if not self._model:
            return
        c = self._model.get(clip_id)
        if c is None:
            return
        c.keep = not c.keep
        self._rebuild()
        self.keepToggled.emit(clip_id, c.keep)

    def refresh(self):
        self._rebuild()

    def set_thumb(self, clip_id, pixmap):
        card = self._cards.get(clip_id)
        if card:
            card.set_thumb(pixmap)

    def _emit_clip(self, cid): self.select_clip(cid)
    def _emit_conn(self, idx): self.select_connector(idx)
    def _emit_keep(self, cid): self.toggle_keep(cid)

    def _set_sel_clip(self, cid):
        if self._sel_clip in self._cards:
            self._cards[self._sel_clip].set_selected(False)
        self._sel_clip = cid
        if cid in self._cards:
            self._cards[cid].set_selected(True)

    def _set_sel_conn(self, idx):
        for c in self._connectors:
            c.set_selected(c.index == idx)
        self._sel_conn = idx
```

> 说明：v1 排序可先用拖放（`orderChanged`）后续接；本骨架已暴露 `orderChanged` 信号，panel 接到后调 `model.reorder_clips` + `set_model` 刷新。QSS（`#ComposeClipCard[selected="true"]` 等）随 Task 10 一起加进 `theme.qss.tpl`。

- [ ] **Step 4: 运行确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_clip_strip_emits_signals -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/compose/__init__.py drama_shot_master/ui/widgets/compose/clip_strip.py tests/test_ui/test_compose_widgets.py
git commit -m "feat(compose): ClipStrip 片段走马灯控件"
```

---

## Task 8: trim_bar 控件

**Files:**
- Create: `drama_shot_master/ui/widgets/compose/trim_bar.py`
- Test: `tests/test_ui/test_compose_widgets.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
def test_trim_bar_emits_in_out():
    _app()
    from drama_shot_master.ui.widgets.compose.trim_bar import TrimBar
    bar = TrimBar()
    bar.set_clip(duration=10.0, in_point=None, out_point=None)
    got = []
    bar.trimChanged.connect(lambda i, o: got.append((i, o)))
    bar.set_in(1.5)
    bar.set_out(8.0)
    assert got[-1] == (1.5, 8.0)
    # 约束：in < out，且夹在 [0, duration]
    bar.set_in(9.0)         # 超过 out → 被夹到 out 之前
    assert bar.in_point() < bar.out_point()
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_trim_bar_emits_in_out -q`
Expected: ERROR ModuleNotFoundError

- [ ] **Step 3: 实现**（缩略图刷条 v1 可先用纯色背景 + 双手柄；缩略图填充留 hook `set_strip_pixmaps`）

```python
# drama_shot_master/ui/widgets/compose/trim_bar.py
"""Trim 条：双手柄设入/出点（秒）。缩略图刷条背景可后填，逻辑独立可测。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout


class TrimBar(QWidget):
    trimChanged = Signal(float, float)   # in_point, out_point（秒）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dur = 0.0
        self._in = 0.0
        self._out = 0.0
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("—"); self._label.setObjectName("ComposeTrimLabel")
        lay.addWidget(self._label)
        # 可视刷条占位（绘制/手柄交互在 _ScrubBar 内；此处省略像素细节）
        self._scrub = _ScrubBar(self)
        self._scrub.handleMoved.connect(self._on_handle)
        lay.addWidget(self._scrub)

    def set_clip(self, duration: float, in_point, out_point):
        self._dur = max(0.0, float(duration))
        self._in = float(in_point) if in_point is not None else 0.0
        self._out = float(out_point) if out_point is not None else self._dur
        self._scrub.set_range(self._dur, self._in, self._out)
        self._update_label()

    def in_point(self) -> float: return self._in
    def out_point(self) -> float: return self._out

    def set_in(self, v: float):
        self._in = max(0.0, min(float(v), self._out - 0.1))
        self._scrub.set_range(self._dur, self._in, self._out)
        self._update_label(); self.trimChanged.emit(self._in, self._out)

    def set_out(self, v: float):
        self._out = min(self._dur, max(float(v), self._in + 0.1))
        self._scrub.set_range(self._dur, self._in, self._out)
        self._update_label(); self.trimChanged.emit(self._in, self._out)

    def _on_handle(self, which: str, t: float):
        self.set_in(t) if which == "in" else self.set_out(t)

    def _update_label(self):
        self._label.setText(f"入点 {self._in:.1f}s — 出点 {self._out:.1f}s（保留 {self._out - self._in:.1f}s）")


class _ScrubBar(QWidget):
    """刷条 + 双手柄。v1 用鼠标拖拽换算时间；缩略图背景可后填。"""
    handleMoved = Signal(str, float)   # which("in"/"out"), seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40); self._dur = 0.0; self._in = 0.0; self._out = 0.0
        self._drag = None

    def set_range(self, dur, i, o):
        self._dur, self._in, self._out = dur, i, o; self.update()

    def _x_to_t(self, x: int) -> float:
        if self.width() <= 0 or self._dur <= 0:
            return 0.0
        return max(0.0, min(self._dur, x / self.width() * self._dur))

    def mousePressEvent(self, e):
        if self._dur <= 0:
            return
        t = self._x_to_t(int(e.position().x()))
        self._drag = "in" if abs(t - self._in) <= abs(t - self._out) else "out"
        self.handleMoved.emit(self._drag, t)

    def mouseMoveEvent(self, e):
        if self._drag:
            self.handleMoved.emit(self._drag, self._x_to_t(int(e.position().x())))

    def mouseReleaseEvent(self, e):
        self._drag = None

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(self); w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#1a2848"))
        if self._dur > 0:
            xi = int(self._in / self._dur * w); xo = int(self._out / self._dur * w)
            p.fillRect(xi, 0, xo - xi, h, QColor(74, 158, 255, 60))
            p.fillRect(xi, 0, 4, h, QColor("#4a9eff")); p.fillRect(xo - 4, 0, 4, h, QColor("#4a9eff"))
        p.end()
```

- [ ] **Step 4: 运行确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_trim_bar_emits_in_out -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/compose/trim_bar.py tests/test_ui/test_compose_widgets.py
git commit -m "feat(compose): TrimBar 双手柄裁剪条"
```

---

## Task 9: transition_inspector 控件

**Files:**
- Create: `drama_shot_master/ui/widgets/compose/transition_inspector.py`
- Test: `tests/test_ui/test_compose_widgets.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
def test_inspector_emits_override_and_lock():
    _app()
    from drama_shot_master.ui.widgets.compose.transition_inspector import TransitionInspector
    insp = TransitionInspector()
    insp.set_connector(index=0, effect="dissolve", duration=0.5, source="auto", locked=False)
    got = []
    insp.changed.connect(lambda idx, eff, dur, locked: got.append((idx, eff, dur, locked)))
    insp.set_effect("smoothleft")     # 手动覆盖
    insp.set_duration(0.8)
    insp.set_locked(True)
    assert got[-1][0] == 0
    assert got[-1][1] == "smoothleft"
    assert got[-1][2] == 0.8
    assert got[-1][3] is True
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_inspector_emits_override_and_lock -q`
Expected: ERROR

- [ ] **Step 3: 实现**（下拉按 `XFADE_EFFECTS` 分类填充；时长 0.3–2.0；锁定/重置）

```python
# drama_shot_master/ui/widgets/compose/transition_inspector.py
"""切口转场编辑器：效果下拉(分类) + 时长 + 锁定。发 changed(index, effect, duration, locked)。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QPushButton,
)

from drama_shot_master.core.transition_render import XFADE_EFFECTS

_CAT_LABEL = {"universal": "万能适配", "directional": "方向推进", "creative": "创意", "cut": "硬切"}


class TransitionInspector(QWidget):
    changed = Signal(int, str, float, bool)   # index, effect, duration, locked
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
```

- [ ] **Step 4: 运行确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_inspector_emits_override_and_lock -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/compose/transition_inspector.py tests/test_ui/test_compose_widgets.py
git commit -m "feat(compose): TransitionInspector 切口转场编辑器"
```

---

## Task 10: compose_panel 组装

**Files:**
- Create: `drama_shot_master/ui/panels/compose_panel.py`
- Modify: `drama_shot_master/ui/styles/theme.qss.tpl`（compose QSS）
- Test: `tests/test_ui/test_compose_widgets.py`（追加 panel 冒烟）

- [ ] **Step 1: 追加失败测试**

```python
def test_compose_panel_instantiates_and_loads_dir(tmp_path):
    _app()
    from drama_shot_master.config import load_config
    from drama_shot_master.ui.panels.compose_panel import ComposePanel
    cfg = load_config()
    panel = ComposePanel(cfg, payload={"clips": []})
    # 注入两个假 mp4（不真渲染），断言能加进模型
    f1 = tmp_path / "a.mp4"; f1.write_bytes(b"x")
    f2 = tmp_path / "b.mp4"; f2.write_bytes(b"x")
    panel.add_clips([str(f1), str(f2)])
    assert len(panel.model().clips) == 2
    # 信号面：renderRequested / sendToSoundtrack 存在
    assert hasattr(panel, "renderRequested")
    assert hasattr(panel, "sendToSoundtrack")
    assert hasattr(panel, "dirty")
    assert hasattr(panel, "to_payload")
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_compose_panel_instantiates_and_loads_dir -q`
Expected: ERROR

- [ ] **Step 3: 实现**（组装 toolbar + ClipStrip + VideoPreviewWidget + TrimBar + TransitionInspector + 渲染条；后台抽帧 + 渲染用 FunctionWorker）

```python
# drama_shot_master/ui/panels/compose_panel.py
"""成片编辑器：看片剔除/排序/trim + 一键 xfade 拼接。对照 成片合成-layout.html。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSplitter,
    QProgressBar, QFileDialog,
)

from drama_shot_master.core.composition_model import CompositionModel, ReelClip
from drama_shot_master.core.ffmpeg_locate import probe_duration
from drama_shot_master.core import transition_render as tr
from drama_shot_master.ui.widgets.video_preview_widget import VideoPreviewWidget
from drama_shot_master.ui.widgets.compose.clip_strip import ClipStrip
from drama_shot_master.ui.widgets.compose.trim_bar import TrimBar
from drama_shot_master.ui.widgets.compose.transition_inspector import TransitionInspector
from drama_shot_master.ui.worker import FunctionWorker

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}


class ComposePanel(QWidget):
    statusMessage = Signal(str)
    dirty = Signal()
    renderRequested = Signal()
    sendToSoundtrack = Signal(str)   # output mp4 path

    def __init__(self, cfg, payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._model = CompositionModel.from_dict(payload or {"clips": []})
        self._worker = None
        self._build_ui()
        self._reload()

    # —— public ——
    def model(self) -> CompositionModel:
        return self._model

    def to_payload(self) -> dict:
        return self._model.to_dict()

    def add_clips(self, paths: list[str]):
        for p in paths:
            dur = probe_duration(p)
            self._model.clips.append(ReelClip.new(path=p, duration=dur))
        self._reload(); self.dirty.emit()

    # —— build ——
    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        # toolbar
        tb = QHBoxLayout(); tb.setContentsMargins(12, 10, 12, 10)
        self._title = QLabel("成片"); self._title.setObjectName("ComposeTitle")
        tb.addWidget(self._title); tb.addStretch(1)
        b_listdir = QPushButton("⟳ 列出生成目录"); b_listdir.clicked.connect(self._list_output_dir)
        b_add = QPushButton("＋ 添加片段"); b_add.clicked.connect(self._pick_files)
        self._b_render = QPushButton("✦ 一键智能转场"); self._b_render.setObjectName("ComposePrimary")
        self._b_render.clicked.connect(self._on_render)
        for b in (b_listdir, b_add, self._b_render):
            tb.addWidget(b)
        root.addLayout(tb)

        # strip
        self._strip = ClipStrip()
        self._strip.clipSelected.connect(self._on_clip_selected)
        self._strip.connectorSelected.connect(self._on_conn_selected)
        self._strip.keepToggled.connect(lambda *_: self.dirty.emit())
        self._strip.orderChanged.connect(self._on_reorder)
        root.addWidget(self._strip)

        # lower split: preview+trim | inspector
        lower = QSplitter(Qt.Horizontal)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(12, 8, 12, 8)
        self._preview = VideoPreviewWidget()
        self._trim = TrimBar(); self._trim.trimChanged.connect(self._on_trim)
        lv.addWidget(self._preview, 1); lv.addWidget(self._trim)
        lower.addWidget(left)
        self._inspector = TransitionInspector()
        self._inspector.changed.connect(self._on_transition_changed)
        self._inspector.resetToAuto.connect(self._on_reset_auto)
        self._inspector.applyToAll.connect(self._on_apply_all)
        lower.addWidget(self._inspector)
        lower.setSizes([700, 248])
        root.addWidget(lower, 1)

        # render bar
        rb = QHBoxLayout(); rb.setContentsMargins(12, 8, 12, 8)
        self._progress = QProgressBar(); self._progress.setVisible(False)
        self._status = QLabel("")
        self._b_send = QPushButton("送去配乐 ›"); self._b_send.setEnabled(False)
        self._b_send.clicked.connect(lambda: self.sendToSoundtrack.emit(self._model_output))
        rb.addWidget(self._status); rb.addWidget(self._progress, 1); rb.addWidget(self._b_send)
        root.addLayout(rb)
        self._model_output = ""

    def _reload(self):
        self._strip.set_model(self._model)

    # —— interactions ——
    def _list_output_dir(self):
        d = getattr(self.cfg, "video_output_dir", "") or ""
        if not d or not Path(d).is_dir():
            self.statusMessage.emit("未设置视频输出目录"); return
        found = [str(p) for p in sorted(Path(d).glob("*")) if p.suffix.lower() in _VIDEO_EXTS]
        existing = {c.path for c in self._model.clips}
        self.add_clips([p for p in found if p not in existing])

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "添加片段", "", "视频 (*.mp4 *.mov *.mkv *.webm)")
        if files:
            self.add_clips(files)

    def _on_clip_selected(self, cid):
        c = self._model.get(cid)
        if c is None:
            return
        self._preview.set_source(c.path)
        self._trim.set_clip(c.duration, c.in_point, c.out_point)
        self._sel_clip = cid

    def _on_trim(self, i, o):
        if getattr(self, "_sel_clip", None):
            self._model.update_clip(self._sel_clip, in_point=i, out_point=o); self.dirty.emit()

    def _on_conn_selected(self, idx):
        kept = self._model.kept_clips()
        if idx >= len(kept) - 1:
            return
        c = kept[idx]
        src = "user" if c.user_transition else "auto"
        self._inspector.set_connector(idx, c.effective_transition(), c.effective_duration(), src, c.locked)

    def _on_transition_changed(self, idx, eff, dur, locked):
        kept = self._model.kept_clips()
        if idx < len(kept) - 1:
            kept[idx].user_transition = eff; kept[idx].user_duration = dur; kept[idx].locked = locked
            self._strip.refresh(); self.dirty.emit()

    def _on_reset_auto(self, idx):
        kept = self._model.kept_clips()
        if idx < len(kept) - 1:
            kept[idx].user_transition = None; kept[idx].user_duration = None
            self._strip.refresh(); self.dirty.emit()

    def _on_apply_all(self, eff, dur):
        for c in self._model.kept_clips()[:-1]:
            if not c.locked:
                c.user_transition = eff; c.user_duration = dur
        self._strip.refresh(); self.dirty.emit()

    def _on_reorder(self, ordered_ids):
        self._model.reorder_clips(ordered_ids); self._reload(); self.dirty.emit()

    # —— render ——
    def _on_render(self):
        ok, msg = self._model.validate()
        if not ok:
            self.statusMessage.emit(msg); return
        if msg != "ok":
            self.statusMessage.emit(msg)   # 降级提示，不阻断
        out_dir = getattr(self.cfg, "video_output_dir", "") or "."
        out = str(Path(out_dir) / f"{self._model.output_prefix}_{id(self):x}.mp4")
        self._progress.setVisible(True); self._progress.setRange(0, 0)
        self._status.setText("渲染中…"); self._b_render.setEnabled(False)
        comp = CompositionModel.from_dict(self._model.to_dict())  # 快照
        self._worker = FunctionWorker(tr.render, comp, out)
        self._worker.finished_with_result.connect(self._on_render_done)
        self._worker.failed.connect(self._on_render_failed)
        self._worker.start(); self.renderRequested.emit()

    def _on_render_done(self, out_path):
        self._model_output = out_path
        self._progress.setVisible(False); self._b_render.setEnabled(True)
        self._b_send.setEnabled(True); self._status.setText("成片完成")
        self._preview.set_source(out_path)
        self.statusMessage.emit(f"成片完成：{out_path}")

    def _on_render_failed(self, err):
        self._progress.setVisible(False); self._b_render.setEnabled(True)
        self._status.setText("渲染失败")
        self.statusMessage.emit(err)
```

- [ ] **Step 4: 追加 compose QSS** 到 `drama_shot_master/ui/styles/theme.qss.tpl` 末尾（卡片选中/剔除/切口/主按钮，复用现有 token 风格）

```css
#ComposeClipCard {{ background:#12122a; border:1px solid #252540; border-radius:9px; }}
#ComposeClipCard[selected="true"] {{ border:1px solid {accent}; }}
#ComposeClipCard[dropped="true"] {{ background:#0e0e1c; }}
#ComposeClipThumb {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #1a3060, stop:1 #2a1850); border-radius:8px; }}
#ComposeConnector {{ border:1px dashed #3a3a5a; border-radius:15px; min-width:30px; min-height:30px; color:#7a8aaa; background:#10122a; }}
#ComposeConnector[selected="true"] {{ border:2px solid {accent}; color:#a0c8ff; }}
#ComposeTitle {{ font-size:15px; font-weight:700; color:{fg}; }}
#ComposePrimary {{ color:#fff; border:none; border-radius:18px; padding:8px 18px; font-weight:700;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {accent}, stop:1 #a06cff); }}
```

- [ ] **Step 5: 运行确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/panels/compose_panel.py drama_shot_master/ui/styles/theme.qss.tpl tests/test_ui/test_compose_widgets.py
git commit -m "feat(compose): ComposePanel 组装看片/trim/转场/渲染"
```

---

## Task 11: compose_task_manager_panel（任务列表）

**Files:**
- Create: `drama_shot_master/ui/panels/compose_task_manager_panel.py`

镜像 `drama_shot_master/ui/panels/video_task_manager_panel.py` 的最小子集：表格(名称/状态/更新时间) + 新建/删除/重命名按钮；信号 `taskSelected(ComposeTask)`、`taskDeleted(str)`、`taskRenamed(str, str)`；方法 `get_status(task_id)->str`、`refresh()`、`set_task_status(id, status)`。

- [ ] **Step 1: 阅读参考实现**

Run: `sed -n '1,120p' drama_shot_master/ui/panels/video_task_manager_panel.py`（照其结构改 store 类型为 `ComposeTaskStore`、task 字段 `composition/output_mp4/status`）

- [ ] **Step 2: 写冒烟测试**（`tests/test_ui/test_compose_widgets.py` 追加）

```python
def test_compose_manager_smoke():
    _app()
    from drama_shot_master.core.compose_task_store import ComposeTaskStore
    from drama_shot_master.ui.panels.compose_task_manager_panel import ComposeTaskManagerPanel
    store = ComposeTaskStore()
    store.add("A", {"clips": []})
    mgr = ComposeTaskManagerPanel(store, on_persist=lambda: None)
    assert hasattr(mgr, "taskSelected")
    assert mgr.get_status(store.all()[0].id) in ("空闲", "生成中", "完成", "失败")
```

- [ ] **Step 3: 实现** 镜像参考面板（保持信号/方法名一致；构造签名 `(store, on_persist)`）。

- [ ] **Step 4: 运行**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_compose_manager_smoke -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/panels/compose_task_manager_panel.py tests/test_ui/test_compose_widgets.py
git commit -m "feat(compose): ComposeTaskManagerPanel 任务列表"
```

---

## Task 12: app_shell 接线 + 视频后期 tab 装配

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: `_build_pages` 构造 compose store + page**

在 `self.video_store = ...` 附近加：
```python
        from drama_shot_master.core.compose_task_store import ComposeTaskStore
        self.compose_store = ComposeTaskStore.from_list(getattr(self.cfg, "compose_tasks", []))
```
在 `builders` 字典加：
```python
            "compose": self._make_compose_page,
```
（注意：`_func_pages` 的构造循环遍历 `FUNCS`，Task 6 已把 `compose` 加入 `FUNCS`，故会自动构造并经 `VIDEOPOST_TABS` 装进视频后期容器页。）

- [ ] **Step 2: 加 `_make_compose_page`（复用 TaskWorkspacePage，镜像 `_make_soundtrack_page`）**

```python
    def _make_compose_page(self):
        from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        from drama_shot_master.ui.panels.compose_task_manager_panel import ComposeTaskManagerPanel
        from drama_shot_master.ui.panels.compose_panel import ComposePanel

        manager = ComposeTaskManagerPanel(self.compose_store, self._persist_compose)

        def editor_factory(task):
            return ComposePanel(self.cfg, payload=task.composition)

        def wire_editor(editor, task):
            tid = task.id
            editor.sendToSoundtrack.connect(self._on_compose_send_soundtrack)
            editor.statusMessage.connect(self._set_status)

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.to_payload(),
            on_persist=self._on_compose_dirty,
            title_for=lambda task: f"成片 · {task.name}",
        )
        manager.taskRenamed.connect(self._on_compose_renamed)
        manager.taskDeleted.connect(page.discard_editor)
        return page

    def _compose_manager(self):
        return self._func_pages["compose"].manager

    def _persist_compose(self):
        try:
            self.cfg.update_settings(compose_tasks=self.compose_store.to_list())
        except Exception:
            pass

    def _on_compose_dirty(self, task_id: str, payload: dict):
        self.compose_store.update(task_id, composition=payload)
        self._persist_compose()

    def _on_compose_renamed(self, task_id, name):
        self._func_pages["compose"].update_task_name(task_id, name)

    def _on_compose_send_soundtrack(self, mp4_path: str):
        """成片 → 预填新建配乐任务的 mp4 字段（手动交接）。"""
        try:
            self.cfg.soundtrack_tasks = list(getattr(self.cfg, "soundtrack_tasks", [])) + [{
                "id": "", "name": Path(mp4_path).stem, "mp4": mp4_path, "status": "空闲"}]
            self.cfg.update_settings(soundtrack_tasks=self.cfg.soundtrack_tasks)
            self._set_status(f"已送去配乐：{mp4_path}")
            sp = self._soundtrack_panel()
            if sp is not None and hasattr(sp, "refresh"):
                sp.refresh()
        except Exception:
            pass
```

- [ ] **Step 3: closeEvent 落盘 compose**（在现有 `_persist_soundtrack()` 附近加）

```python
        cp = self._func_pages.get("compose")
        if cp is not None and hasattr(cp, "flush_all"):
            cp.flush_all()
        self._persist_compose()
```

- [ ] **Step 4: 冒烟测试（AppShell 构造 + 视频后期含成片 tab）**

```bash
QT_QPA_PLATFORM=offscreen python -c "
from PySide6.QtWidgets import QApplication
app=QApplication([])
from drama_shot_master.config import load_config
from drama_shot_master.ui.theme import apply_theme, current_theme
cfg=load_config(); apply_theme(app, current_theme(cfg))
from drama_shot_master.ui.app_shell import AppShell
s=AppShell(); app.processEvents()
assert 'compose' in s._func_pages
vp = s.pages['video_post']
assert vp.current_key() in ('compose','dubbing','soundtrack')
print('compose tab wired OK')
"
```
Expected: `compose tab wired OK`（过滤掉 screenwriter 子进程日志）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/app_shell.py
git commit -m "feat(compose): app_shell 接线成片页 + 视频后期 tab + 送去配乐"
```

---

## Task 13: 随包 ffmpeg（打包）

**Files:**
- Modify: `build/drama_shot_master.spec`
- 放置：`drama_shot_master/assets/bin/ffmpeg.exe`、`ffprobe.exe`（标准版，开发者本地放入；不提交大二进制到 git，加 `.gitignore`）

- [ ] **Step 1: 放二进制 + gitignore**

把标准版 `ffmpeg.exe`/`ffprobe.exe` 放入 `drama_shot_master/assets/bin/`。在仓库根 `.gitignore` 追加：
```
drama_shot_master/assets/bin/ffmpeg.exe
drama_shot_master/assets/bin/ffprobe.exe
```

- [ ] **Step 2: spec 收集 assets/bin**

在 `build/drama_shot_master.spec` 的 `datas`/`binaries` 中加入（参考其现有 `datas` 写法）：
```python
binaries += [
    ("drama_shot_master/assets/bin/ffmpeg.exe", "assets/bin"),
    ("drama_shot_master/assets/bin/ffprobe.exe", "assets/bin"),
]
```
（v1 **不动** `excludes` 里的 `cv2` —— 那是 v2 才需要的改动。）

- [ ] **Step 3: 源码态验证定位**

Run: `python -c "from drama_shot_master.core.ffmpeg_locate import ffmpeg_path; print(ffmpeg_path())"`
Expected: 打印 `…/assets/bin/ffmpeg.exe`（已放入）或系统 PATH 路径（未放入时回退）。

- [ ] **Step 4: 提交（不含二进制）**

```bash
git add build/drama_shot_master.spec .gitignore
git commit -m "build(compose): 随包 ffmpeg/ffprobe（assets/bin）"
```

---

## Task 14: 集成冒烟 + 全量回归

**Files:** 无新增（验证）

- [ ] **Step 1: 真渲染冒烟（需本地有 ffmpeg + 2 个短 mp4）**

```bash
python -c "
from drama_shot_master.core.composition_model import ReelClip, CompositionModel
from drama_shot_master.core import transition_render as tr
m=CompositionModel(clips=[ReelClip.new('clipA.mp4'), ReelClip.new('clipB.mp4')])
print(tr.render(m, '_compose_smoke.mp4'))
"
```
Expected: 打印输出路径；用播放器确认转场+保留原音、总时长 ≈ Σ时长 − Σ转场。删除 `_compose_smoke.mp4`。

- [ ] **Step 2: 全量回归**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`
Expected: 仅既有历史失败（如 `test_nav_config.py::test_screenwriter_in_phases_drama_prep`，与本功能无关）外全绿。

- [ ] **Step 3: 真机外观确认（PowerShell 渲染成片页）**

按 `docs/explorer/成片合成-layout.html` 比对 ComposePanel 实际渲染（PowerShell 原生 windows11 style + 字体）。

- [ ] **Step 4: 最终提交（如有微调）**

```bash
git add -A && git commit -m "test(compose): v1 集成冒烟 + 回归"
```

---

## 自我审查

### Spec 覆盖
| Spec 节 | 覆盖任务 |
|---------|---------|
| §2 接入（视频后期 tab/复用 TaskWorkspacePage） | Task 6, 12 |
| §3 数据模型（ReelClip/CompositionModel/effective/validate） | Task 1 |
| §3 持久化（compose_tasks/ComposeTaskStore） | Task 2, 3 |
| §4 渲染（xfade+acrossfade/offset/归一化/trim/降级） | Task 5 |
| §4 ffmpeg 定位 | Task 4, 13 |
| §6 UI（走马灯/trim/inspector/预览/渲染条） | Task 7-10 |
| §6.2 转场精选集（XFADE_EFFECTS 分类） | Task 5（常量）+ Task 9（下拉） |
| §7 v1 范围（无 CV、保留原音、送去配乐） | Task 10, 12 |
| §8 打包（v1 仅随包 ffmpeg，不动 cv2 exclude） | Task 13 |
| §9 测试 | Task 1-11, 14 |

### 类型/方法一致性
- `ReelClip.effective_transition()/effective_duration()/trimmed_duration()` — Task 1 定义，Task 5/10 调用 ✓
- `CompositionModel.kept_clips()/reorder_clips()/update_clip()/validate()/to_dict/from_dict` — Task 1 定义，Task 5/10 调用 ✓
- `transition_render.XFADE_EFFECTS/compute_offsets/build_ffmpeg_args/render` — Task 5 定义，Task 9/10 调用 ✓
- `ffmpeg_locate.ffmpeg_path/ffprobe_path/probe_duration` — Task 4 定义，Task 5/10 调用 ✓
- `ComposeTaskStore(store).add/update/to_list/from_list` — Task 2 定义，Task 11/12 调用 ✓
- `ComposePanel.to_payload()/add_clips()/model()` + 信号 `dirty/statusMessage/sendToSoundtrack` — Task 10 定义，Task 12 接线 ✓
- `TaskWorkspacePage(manager, editor_factory, wire_editor, payload_of, on_persist, title_for)` — 既有签名，Task 12 调用 ✓
- `VideoPreviewWidget.set_source()` — 既有 API，Task 10 调用 ✓

### Placeholder 扫描：无 TBD/TODO；核心任务均含完整代码与命令。UI 任务（7-11）给出可工作骨架 + offscreen 冒烟测试；像素级 QSS 细节随 Task 10 落地，布局以 mockup 为准。
```
