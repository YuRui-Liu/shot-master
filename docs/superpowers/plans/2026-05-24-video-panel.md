# 视频生成面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 PySide6 桌面应用里加第 5 个主功能 panel「视频生成」，含 DAW 时间轴 + 图片池 + per-seg 编辑 + 全局参数 + 提交链路（调子项目 A 的 RunningHub 后端），关闭时缓存轨道状态。

**Architecture:** `app/core/video_timeline_model.py` 是零 Qt 依赖的数据模型；5 个 widget + 1 个 dialog + 1 个 panel 在 `app/ui/`；MainWindow 加第 5 项 FUNCS + 菜单栏「设置 → RunningHub…」+ 切到视频生成时隐藏中栏。所有 model 写入只在 VideoPanel（单向数据流）。

**Tech Stack:** Python 3.10+, PySide6 ≥ 6.6（已用），httpx（A 已加），QGraphicsScene 自绘时间轴。测试用 pytest 测 TimelineModel；UI widget 不写自动测，靠手工冒烟。

**Spec:** `docs/superpowers/specs/2026-05-24-video-panel-design.md`

---

## File Structure

新增 / 修改文件清单：

| 文件 | 操作 | 职责 |
|---|---|---|
| `app/core/video_timeline_model.py` | 新增 | TimelineSegment / TimelineAudio / TimelineModel + 序列化 + 校验 |
| `app/ui/widgets/timeline_widget.py` | 新增 | QGraphicsScene 自绘时间轴 + 鼠标交互 + 滚轮缩放（~400 行） |
| `app/ui/widgets/image_pool_widget.py` | 新增 | 持久图片池 QListWidget |
| `app/ui/widgets/segment_editor.py` | 新增 | per-seg 编辑表单 |
| `app/ui/widgets/video_global_form.py` | 新增 | 全局参数表单 |
| `app/ui/widgets/video_status_bar.py` | 新增 | 状态栏 + 提交/取消按钮 |
| `app/ui/dialogs/__init__.py` | 新增 | 空 |
| `app/ui/dialogs/runninghub_settings_dialog.py` | 新增 | 配置弹窗 |
| `app/ui/panels/video_panel.py` | 新增 | BasePanel 子类，5 层装配 |
| `app/ui/main_window.py` | 修改 | FUNCS + 菜单 + 切换布局 + closeEvent |
| `app/config.py` | 修改 | 加 `video_timeline_cache` 字段 + 持久化 |
| `tests/test_core/__init__.py` | 新增 | 空 |
| `tests/test_core/test_video_timeline_model.py` | 新增 | TimelineModel ~22 个测试 |
| `tests/test_config.py` | 修改 | 加 video_timeline_cache 持久化用例 |

---

## Task 1: TimelineModel 数据类骨架 + 默认值测试

**Files:**
- Create: `tests/test_core/__init__.py` (empty)
- Create: `tests/test_core/test_video_timeline_model.py`
- Create: `app/core/video_timeline_model.py`

- [ ] **Step 1: 创建 tests/test_core/ 目录**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
mkdir -p tests/test_core
touch tests/test_core/__init__.py
```

- [ ] **Step 2: 写 failing tests**

新建 `tests/test_core/test_video_timeline_model.py`:

```python
"""TimelineModel 单测（纯数据，零 Qt 依赖）。"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.core.video_timeline_model import (
    TimelineSegment, TimelineAudio, TimelineModel,
)


# ---------- dataclass 基础 ----------

def test_timeline_segment_defaults_image():
    s = TimelineSegment(
        seg_id="abc", segment_type="image", length_frames=24,
        image_path=Path("/x.png"),
    )
    assert s.seg_id == "abc"
    assert s.segment_type == "image"
    assert s.length_frames == 24
    assert s.local_prompt == ""
    assert s.image_path == Path("/x.png")
    assert s.guide_strength == 1.0


def test_timeline_segment_defaults_text():
    s = TimelineSegment(seg_id="t1", segment_type="text", length_frames=12)
    assert s.image_path is None
    assert s.guide_strength == 1.0


def test_timeline_segment_is_frozen():
    s = TimelineSegment(seg_id="abc", segment_type="image", length_frames=24)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.length_frames = 48


def test_timeline_audio_basic():
    a = TimelineAudio(
        audio_id="aud1", audio_path=Path("/bgm.mp3"),
        start_frame=0, length_frames=96,
    )
    assert a.audio_id == "aud1"
    assert a.audio_path == Path("/bgm.mp3")
    assert a.start_frame == 0
    assert a.length_frames == 96


def test_timeline_audio_is_frozen():
    a = TimelineAudio(audio_id="x", audio_path=Path("/a.mp3"),
                       start_frame=0, length_frames=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.start_frame = 10


def test_timeline_model_defaults():
    m = TimelineModel()
    assert m.segments == []
    assert m.audios == []
    assert m.pool == []
    assert m.global_prompt == ""
    assert m.use_global_prompt is True
    assert m.frame_rate == 24
    assert m.display_mode == "seconds"
    assert m.resolution_preset == "1280x720 (16:9) (横屏)"
    assert m.use_custom_resolution is False
    assert m.custom_width == 1024
    assert m.custom_height == 1024
    assert m.filename_prefix == "spb_video"
```

- [ ] **Step 3: 运行验证 FAIL**

```bash
pytest tests/test_core/test_video_timeline_model.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.video_timeline_model'`

- [ ] **Step 4: 实现 dataclasses**

新建 `app/core/video_timeline_model.py`:

```python
"""TimelineModel：视频生成面板的数据模型。

零 Qt 依赖。提供时间轴段、音频段、图片池和全局参数；
支持转换到子项目 A 的 LTXDirectorSpec、序列化到 settings.json、校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


SegmentType = Literal["image", "text"]
DisplayMode = Literal["seconds", "frames"]


@dataclass(frozen=True)
class TimelineSegment:
    """主轨段（image | text）。内部长度一律帧数。"""
    seg_id: str
    segment_type: SegmentType
    length_frames: int
    local_prompt: str = ""
    image_path: Optional[Path] = None
    guide_strength: float = 1.0


@dataclass(frozen=True)
class TimelineAudio:
    """音频段：绝对帧定位。"""
    audio_id: str
    audio_path: Path
    start_frame: int
    length_frames: int


@dataclass
class TimelineModel:
    """时间轴 + 全局参数 + 图片池。可变容器。"""
    segments: list[TimelineSegment] = field(default_factory=list)
    audios: list[TimelineAudio] = field(default_factory=list)
    pool: list[Path] = field(default_factory=list)

    # 全局
    global_prompt: str = ""
    use_global_prompt: bool = True
    frame_rate: int = 24
    display_mode: DisplayMode = "seconds"
    resolution_preset: str = "1280x720 (16:9) (横屏)"
    use_custom_resolution: bool = False
    custom_width: int = 1024
    custom_height: int = 1024
    filename_prefix: str = "spb_video"
```

- [ ] **Step 5: 运行验证 PASS**

```bash
pytest tests/test_core/test_video_timeline_model.py -v
```

Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add tests/test_core/__init__.py tests/test_core/test_video_timeline_model.py app/core/video_timeline_model.py
git commit -m "feat(video-panel): scaffold TimelineModel dataclasses"
```

---

## Task 2: TimelineModel 增删 / 更新 / 池子方法

**Files:**
- Modify: `app/core/video_timeline_model.py`（追加 method）
- Modify: `tests/test_core/test_video_timeline_model.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_core/test_video_timeline_model.py` 末尾追加：

```python
# ---------- 增删段 ----------

def test_add_image_segment_returns_id_and_appends(tmp_path):
    m = TimelineModel()
    img = tmp_path / "a.png"
    sid = m.add_image_segment(img, length_frames=30, local_prompt="P")
    assert isinstance(sid, str) and len(sid) >= 13
    assert len(m.segments) == 1
    assert m.segments[0].seg_id == sid
    assert m.segments[0].image_path == img
    assert m.segments[0].length_frames == 30
    assert m.segments[0].local_prompt == "P"
    assert m.segments[0].segment_type == "image"


def test_add_text_segment_returns_id_no_image_path():
    m = TimelineModel()
    sid = m.add_text_segment(length_frames=10, local_prompt="X")
    assert len(m.segments) == 1
    assert m.segments[0].segment_type == "text"
    assert m.segments[0].image_path is None
    assert m.segments[0].seg_id == sid


def test_add_audio_returns_id(tmp_path):
    m = TimelineModel()
    p = tmp_path / "b.mp3"
    aid = m.add_audio(p, start_frame=12, length_frames=48)
    assert isinstance(aid, str)
    assert m.audios[0].audio_id == aid
    assert m.audios[0].audio_path == p
    assert m.audios[0].start_frame == 12


def test_remove_segment_existing(tmp_path):
    m = TimelineModel()
    sid = m.add_image_segment(tmp_path / "a.png")
    assert m.remove_segment(sid) is True
    assert m.segments == []


def test_remove_segment_unknown_returns_false():
    m = TimelineModel()
    assert m.remove_segment("never-existed") is False


def test_remove_audio_existing(tmp_path):
    m = TimelineModel()
    aid = m.add_audio(tmp_path / "x.mp3")
    assert m.remove_audio(aid) is True
    assert m.audios == []


def test_reorder_segments_reorders(tmp_path):
    m = TimelineModel()
    a = m.add_image_segment(tmp_path / "a.png")
    b = m.add_image_segment(tmp_path / "b.png")
    c = m.add_image_segment(tmp_path / "c.png")
    m.reorder_segments([c, a, b])
    assert [s.seg_id for s in m.segments] == [c, a, b]


def test_reorder_segments_drops_unknown_ids(tmp_path):
    m = TimelineModel()
    a = m.add_image_segment(tmp_path / "a.png")
    m.reorder_segments(["bogus", a])
    assert [s.seg_id for s in m.segments] == [a]


def test_update_segment_replaces_fields(tmp_path):
    m = TimelineModel()
    sid = m.add_image_segment(tmp_path / "a.png", length_frames=24)
    m.update_segment(sid, length_frames=72, local_prompt="new")
    assert m.segments[0].length_frames == 72
    assert m.segments[0].local_prompt == "new"
    # 未改字段保留
    assert m.segments[0].guide_strength == 1.0


def test_update_segment_unknown_id_silent(tmp_path):
    m = TimelineModel()
    m.add_image_segment(tmp_path / "a.png")
    # 不应抛错
    m.update_segment("bogus", length_frames=99)


def test_update_audio_replaces_fields(tmp_path):
    m = TimelineModel()
    aid = m.add_audio(tmp_path / "a.mp3", start_frame=0, length_frames=10)
    m.update_audio(aid, length_frames=50)
    assert m.audios[0].length_frames == 50
    assert m.audios[0].start_frame == 0


# ---------- 图片池 ----------

def test_add_to_pool_deduplicates(tmp_path):
    m = TimelineModel()
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    assert m.add_to_pool([p1, p2, p1]) == 2  # p1 重复算 1 次
    assert m.pool == [p1, p2]
    # 再加重复路径
    assert m.add_to_pool([p1]) == 0
    assert m.pool == [p1, p2]


def test_clear_pool_empties(tmp_path):
    m = TimelineModel()
    m.add_to_pool([tmp_path / "a.png"])
    m.clear_pool()
    assert m.pool == []


def test_pool_usage_counts_segments(tmp_path):
    m = TimelineModel()
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    p3 = tmp_path / "c.png"
    m.add_to_pool([p1, p2, p3])
    m.add_image_segment(p1)
    m.add_image_segment(p1)
    m.add_image_segment(p2)
    # p3 未引用
    usage = m.pool_usage()
    assert usage == {p1: 2, p2: 1, p3: 0}


def test_pool_usage_empty_when_pool_empty():
    assert TimelineModel().pool_usage() == {}
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_core/test_video_timeline_model.py -v
```

Expected: 多项失败（method 未实现）

- [ ] **Step 3: 实现方法**

在 `app/core/video_timeline_model.py` 末尾追加（先加 imports + helper，再加 method）：

```python
from dataclasses import replace
from secrets import token_hex
import time


def _gen_id() -> str:
    """模仿 LTX timeline_data 里的 id 格式：13 位毫秒戳 + 5 位 hex 随机。"""
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"
```

然后在 TimelineModel 类内（紧贴现有字段定义之后）追加：

```python
    # ---------- 增删段 ----------

    def add_image_segment(self, image_path: Path,
                           length_frames: int = 24,
                           local_prompt: str = "") -> str:
        seg = TimelineSegment(
            seg_id=_gen_id(), segment_type="image",
            length_frames=length_frames, local_prompt=local_prompt,
            image_path=image_path,
        )
        self.segments.append(seg)
        return seg.seg_id

    def add_text_segment(self, length_frames: int = 24,
                          local_prompt: str = "") -> str:
        seg = TimelineSegment(
            seg_id=_gen_id(), segment_type="text",
            length_frames=length_frames, local_prompt=local_prompt,
        )
        self.segments.append(seg)
        return seg.seg_id

    def add_audio(self, audio_path: Path,
                   start_frame: int = 0,
                   length_frames: int = 24) -> str:
        a = TimelineAudio(
            audio_id=_gen_id(), audio_path=audio_path,
            start_frame=start_frame, length_frames=length_frames,
        )
        self.audios.append(a)
        return a.audio_id

    def remove_segment(self, seg_id: str) -> bool:
        for i, s in enumerate(self.segments):
            if s.seg_id == seg_id:
                del self.segments[i]
                return True
        return False

    def remove_audio(self, audio_id: str) -> bool:
        for i, a in enumerate(self.audios):
            if a.audio_id == audio_id:
                del self.audios[i]
                return True
        return False

    def reorder_segments(self, ordered_ids: list[str]) -> None:
        by_id = {s.seg_id: s for s in self.segments}
        self.segments = [by_id[i] for i in ordered_ids if i in by_id]

    # ---------- 更新段字段 ----------

    def update_segment(self, seg_id: str, **fields) -> None:
        for i, s in enumerate(self.segments):
            if s.seg_id == seg_id:
                self.segments[i] = replace(s, **fields)
                return

    def update_audio(self, audio_id: str, **fields) -> None:
        for i, a in enumerate(self.audios):
            if a.audio_id == audio_id:
                self.audios[i] = replace(a, **fields)
                return

    # ---------- 图片池 ----------

    def add_to_pool(self, paths: list[Path]) -> int:
        added = 0
        for p in paths:
            if p not in self.pool:
                self.pool.append(p)
                added += 1
        return added

    def clear_pool(self) -> None:
        self.pool.clear()

    def pool_usage(self) -> dict[Path, int]:
        usage: dict[Path, int] = {p: 0 for p in self.pool}
        for s in self.segments:
            if s.image_path and s.image_path in usage:
                usage[s.image_path] += 1
        return usage
```

- [ ] **Step 4: 验证 PASS**

```bash
pytest tests/test_core/test_video_timeline_model.py -v
```

Expected: 21 passed (6 + 15 new)

- [ ] **Step 5: Commit**

```bash
git add app/core/video_timeline_model.py tests/test_core/test_video_timeline_model.py
git commit -m "feat(video-panel): TimelineModel mutation methods and pool"
```

---

## Task 3: TimelineModel.to_ltx_spec

**Files:**
- Modify: `app/core/video_timeline_model.py`
- Modify: `tests/test_core/test_video_timeline_model.py`

- [ ] **Step 1: 写 failing tests**

末尾追加：

```python
# ---------- to_ltx_spec ----------

def test_to_ltx_spec_basic_field_mapping(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    m = TimelineModel(
        global_prompt="G", use_global_prompt=True,
        frame_rate=30, display_mode="frames",
        filename_prefix="myvid",
    )
    m.add_image_segment(img, length_frames=33, local_prompt="P1")
    out = tmp_path / "out"
    spec = m.to_ltx_spec(out)
    assert spec.global_prompt == "G"
    assert spec.use_global_prompt is True
    assert spec.frame_rate == 30
    assert spec.display_mode == "frames"
    assert spec.filename_prefix == "myvid"
    assert spec.output_dir == out
    assert len(spec.segments) == 1
    assert spec.segments[0].local_prompt == "P1"
    assert spec.segments[0].length == 33
    assert spec.segments[0].image_path == img


def test_to_ltx_spec_use_custom_audio_auto_derived(tmp_path):
    img = tmp_path / "a.png"
    m = TimelineModel()
    m.add_image_segment(img)
    spec_no_audio = m.to_ltx_spec(tmp_path)
    assert spec_no_audio.use_custom_audio is False

    m.add_audio(tmp_path / "x.mp3")
    spec_with_audio = m.to_ltx_spec(tmp_path)
    assert spec_with_audio.use_custom_audio is True


def test_to_ltx_spec_audio_segments_mapping(tmp_path):
    m = TimelineModel()
    m.add_image_segment(tmp_path / "a.png")
    m.add_audio(tmp_path / "x.mp3", start_frame=24, length_frames=72)
    spec = m.to_ltx_spec(tmp_path)
    assert len(spec.audio_segments) == 1
    assert spec.audio_segments[0].audio_path == tmp_path / "x.mp3"
    assert spec.audio_segments[0].start_frame == 24
    assert spec.audio_segments[0].length_frames == 72


def test_to_ltx_spec_custom_resolution_passed(tmp_path):
    m = TimelineModel(
        use_custom_resolution=True,
        custom_width=720, custom_height=1280,
    )
    m.add_image_segment(tmp_path / "a.png")
    spec = m.to_ltx_spec(tmp_path)
    assert spec.use_custom_resolution is True
    assert spec.custom_width == 720
    assert spec.custom_height == 1280
```

- [ ] **Step 2: 验证 FAIL**

```bash
pytest tests/test_core/test_video_timeline_model.py -v -k to_ltx_spec
```

Expected: `AttributeError: 'TimelineModel' object has no attribute 'to_ltx_spec'`

- [ ] **Step 3: 实现 to_ltx_spec**

在 TimelineModel 类内追加（紧贴 pool_usage 之后）：

```python
    # ---------- 转 A 的 LTXDirectorSpec ----------

    def to_ltx_spec(self, output_dir: Path):
        """转成子项目 A 的契约对象。use_custom_audio 自动推导。"""
        from app.providers.runninghub import (
            LTXDirectorSpec, LTXSegment, LTXAudioSegment,
        )
        return LTXDirectorSpec(
            global_prompt=self.global_prompt,
            use_global_prompt=self.use_global_prompt,
            segments=tuple(
                LTXSegment(
                    local_prompt=s.local_prompt,
                    length=s.length_frames,
                    image_path=s.image_path,
                    segment_type=s.segment_type,
                    guide_strength=s.guide_strength,
                    seg_id=s.seg_id,
                ) for s in self.segments
            ),
            audio_segments=tuple(
                LTXAudioSegment(
                    audio_path=a.audio_path,
                    start_frame=a.start_frame,
                    length_frames=a.length_frames,
                ) for a in self.audios
            ),
            use_custom_audio=len(self.audios) > 0,
            display_mode=self.display_mode,
            frame_rate=self.frame_rate,
            resolution_preset=self.resolution_preset,
            use_custom_resolution=self.use_custom_resolution,
            custom_width=self.custom_width,
            custom_height=self.custom_height,
            filename_prefix=self.filename_prefix,
            output_dir=output_dir,
        )
```

> 注：`from ... import` 放方法内部，避免 `app.core` 反向依赖 `app.providers`。

- [ ] **Step 4: 验证 PASS**

```bash
pytest tests/test_core/test_video_timeline_model.py -v
```

Expected: 25 passed (21 + 4 new)

- [ ] **Step 5: Commit**

```bash
git add app/core/video_timeline_model.py tests/test_core/test_video_timeline_model.py
git commit -m "feat(video-panel): TimelineModel.to_ltx_spec mapping"
```

---

## Task 4: TimelineModel.to_dict / from_dict

**Files:**
- Modify: `app/core/video_timeline_model.py`
- Modify: `tests/test_core/test_video_timeline_model.py`

- [ ] **Step 1: 写 failing tests**

末尾追加：

```python
# ---------- 序列化 ----------

def test_to_dict_path_to_str(tmp_path):
    m = TimelineModel()
    p = tmp_path / "a.png"
    m.add_image_segment(p, length_frames=20, local_prompt="P")
    m.add_audio(tmp_path / "x.mp3", start_frame=5, length_frames=15)
    m.add_to_pool([tmp_path / "img1.png", tmp_path / "img2.png"])
    d = m.to_dict()
    assert isinstance(d["segments"][0]["image_path"], str)
    assert d["segments"][0]["image_path"] == str(p)
    assert d["segments"][0]["length_frames"] == 20
    assert d["audios"][0]["audio_path"] == str(tmp_path / "x.mp3")
    assert all(isinstance(p, str) for p in d["pool"])


def test_to_dict_text_segment_image_path_none(tmp_path):
    m = TimelineModel()
    m.add_text_segment(length_frames=10, local_prompt="text")
    d = m.to_dict()
    assert d["segments"][0]["image_path"] is None
    assert d["segments"][0]["segment_type"] == "text"


def test_round_trip_to_from_dict(tmp_path):
    m1 = TimelineModel(
        global_prompt="GP", use_global_prompt=True,
        frame_rate=30, display_mode="frames",
        resolution_preset="720x1280 (9:16) (竖屏)",
        use_custom_resolution=True,
        custom_width=720, custom_height=1280,
        filename_prefix="vid",
    )
    img = tmp_path / "img.png"
    sid = m1.add_image_segment(img, length_frames=42, local_prompt="seg")
    m1.add_text_segment(length_frames=8)
    m1.add_audio(tmp_path / "a.mp3", start_frame=10, length_frames=50)
    m1.add_to_pool([tmp_path / "p1.png"])

    m2 = TimelineModel.from_dict(m1.to_dict())
    assert len(m2.segments) == 2
    assert m2.segments[0].seg_id == sid
    assert m2.segments[0].image_path == img
    assert m2.segments[0].length_frames == 42
    assert m2.segments[1].segment_type == "text"
    assert len(m2.audios) == 1
    assert m2.audios[0].start_frame == 10
    assert m2.pool == [tmp_path / "p1.png"]
    assert m2.global_prompt == "GP"
    assert m2.frame_rate == 30
    assert m2.display_mode == "frames"
    assert m2.use_custom_resolution is True
    assert m2.custom_width == 720


def test_from_dict_empty_uses_defaults():
    m = TimelineModel.from_dict({})
    assert m.segments == []
    assert m.audios == []
    assert m.pool == []
    assert m.frame_rate == 24
    assert m.display_mode == "seconds"


def test_from_dict_missing_seg_id_generated():
    import re
    m = TimelineModel.from_dict({"segments": [
        {"segment_type": "image", "length_frames": 10,
         "image_path": "/x.png", "local_prompt": "p"},
    ]})
    assert len(m.segments) == 1
    assert re.match(r"^\d{13}[0-9a-f]{1,5}$", m.segments[0].seg_id)


def test_from_dict_skips_audio_without_path():
    m = TimelineModel.from_dict({"audios": [{"start_frame": 0}]})
    assert m.audios == []
```

- [ ] **Step 2: 验证 FAIL**

```bash
pytest tests/test_core/test_video_timeline_model.py -v -k "to_dict or from_dict or round_trip"
```

Expected: `AttributeError: ... has no attribute 'to_dict'`

- [ ] **Step 3: 实现 to_dict / from_dict**

在 TimelineModel 类内追加（紧贴 to_ltx_spec 之后）：

```python
    # ---------- 序列化 ----------

    def to_dict(self) -> dict:
        """序列化到可写入 settings.json 的 dict（Path 转 str）。"""
        return {
            "segments": [
                {
                    "seg_id": s.seg_id,
                    "segment_type": s.segment_type,
                    "length_frames": s.length_frames,
                    "local_prompt": s.local_prompt,
                    "image_path": str(s.image_path) if s.image_path else None,
                    "guide_strength": s.guide_strength,
                } for s in self.segments
            ],
            "audios": [
                {
                    "audio_id": a.audio_id,
                    "audio_path": str(a.audio_path),
                    "start_frame": a.start_frame,
                    "length_frames": a.length_frames,
                } for a in self.audios
            ],
            "pool": [str(p) for p in self.pool],
            "global_prompt": self.global_prompt,
            "use_global_prompt": self.use_global_prompt,
            "frame_rate": self.frame_rate,
            "display_mode": self.display_mode,
            "resolution_preset": self.resolution_preset,
            "use_custom_resolution": self.use_custom_resolution,
            "custom_width": self.custom_width,
            "custom_height": self.custom_height,
            "filename_prefix": self.filename_prefix,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TimelineModel":
        """从 settings.json 缓存恢复。缺字段走默认，stale audio 跳过。"""
        m = cls()
        m.segments = [
            TimelineSegment(
                seg_id=s.get("seg_id") or _gen_id(),
                segment_type=s.get("segment_type", "image"),
                length_frames=int(s.get("length_frames", 24)),
                local_prompt=s.get("local_prompt", ""),
                image_path=(Path(s["image_path"])
                            if s.get("image_path") else None),
                guide_strength=float(s.get("guide_strength", 1.0)),
            ) for s in data.get("segments", [])
        ]
        m.audios = [
            TimelineAudio(
                audio_id=a.get("audio_id") or _gen_id(),
                audio_path=Path(a["audio_path"]),
                start_frame=int(a.get("start_frame", 0)),
                length_frames=int(a.get("length_frames", 24)),
            ) for a in data.get("audios", []) if a.get("audio_path")
        ]
        m.pool = [Path(p) for p in data.get("pool", [])]
        m.global_prompt = data.get("global_prompt", "")
        m.use_global_prompt = bool(data.get("use_global_prompt", True))
        m.frame_rate = int(data.get("frame_rate", 24))
        m.display_mode = data.get("display_mode", "seconds")
        m.resolution_preset = data.get(
            "resolution_preset", "1280x720 (16:9) (横屏)")
        m.use_custom_resolution = bool(data.get("use_custom_resolution", False))
        m.custom_width = int(data.get("custom_width", 1024))
        m.custom_height = int(data.get("custom_height", 1024))
        m.filename_prefix = data.get("filename_prefix", "spb_video")
        return m
```

- [ ] **Step 4: 验证 PASS**

```bash
pytest tests/test_core/test_video_timeline_model.py -v
```

Expected: 31 passed (25 + 6 new)

- [ ] **Step 5: Commit**

```bash
git add app/core/video_timeline_model.py tests/test_core/test_video_timeline_model.py
git commit -m "feat(video-panel): TimelineModel to_dict/from_dict serialization"
```

---

## Task 5: TimelineModel.validate（pre-flight 校验）

**Files:**
- Modify: `app/core/video_timeline_model.py`
- Modify: `tests/test_core/test_video_timeline_model.py`

- [ ] **Step 1: 写 failing tests**

末尾追加：

```python
# ---------- validate ----------

def test_validate_rejects_empty_segments():
    m = TimelineModel()
    ok, msg = m.validate()
    assert ok is False
    assert "至少需要 1 段" in msg


def test_validate_rejects_length_lt_1(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    m = TimelineModel()
    m.add_image_segment(img, length_frames=0)
    ok, msg = m.validate()
    assert ok is False
    assert "长度" in msg


def test_validate_rejects_image_segment_without_path(tmp_path):
    m = TimelineModel()
    # 用 update_segment 把已有段的 image_path 改成 None
    sid = m.add_image_segment(tmp_path / "a.png")
    m.update_segment(sid, image_path=None)
    ok, msg = m.validate()
    assert ok is False
    assert "图片" in msg


def test_validate_rejects_missing_image_file(tmp_path):
    m = TimelineModel()
    m.add_image_segment(tmp_path / "nonexistent.png")
    ok, msg = m.validate()
    assert ok is False
    assert "不存在" in msg


def test_validate_rejects_invalid_frame_rate(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for bad_fr in (0, 200):
        m = TimelineModel(frame_rate=bad_fr)
        m.add_image_segment(img)
        ok, msg = m.validate()
        assert ok is False
        assert "frame_rate" in msg or "帧率" in msg


def test_validate_rejects_missing_audio_file(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    m = TimelineModel()
    m.add_image_segment(img)
    m.add_audio(tmp_path / "no.mp3")
    ok, msg = m.validate()
    assert ok is False
    assert "音频" in msg


def test_validate_passes_text_segment_without_image(tmp_path):
    m = TimelineModel()
    m.add_text_segment(length_frames=10, local_prompt="p")
    ok, msg = m.validate()
    assert ok is True
    assert msg == ""


def test_validate_passes_complete_spec(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
    m = TimelineModel()
    m.add_image_segment(img, length_frames=24)
    m.add_audio(aud, start_frame=0, length_frames=24)
    ok, msg = m.validate()
    assert ok is True
    assert msg == ""
```

- [ ] **Step 2: 验证 FAIL**

```bash
pytest tests/test_core/test_video_timeline_model.py -v -k validate
```

Expected: 多项失败

- [ ] **Step 3: 实现 validate**

在 TimelineModel 类内追加（紧贴 from_dict 之后）：

```python
    # ---------- pre-flight 校验 ----------

    def validate(self) -> tuple[bool, str]:
        """提交前校验。返回 (ok, error_msg)。"""
        if not self.segments:
            return False, "至少需要 1 段画面"
        if not (1 <= self.frame_rate <= 120):
            return False, f"frame_rate（帧率）越界（当前 {self.frame_rate}，需 1-120）"
        for i, s in enumerate(self.segments, start=1):
            if s.length_frames < 1:
                return False, f"段 {i} 长度不合法（{s.length_frames}）"
            if s.segment_type == "image":
                if s.image_path is None:
                    return False, f"段 {i} 是图片段但未绑定图片"
                if not s.image_path.exists():
                    return False, f"段 {i} 图片不存在：{s.image_path}"
            if not (0.0 <= s.guide_strength <= 1.0):
                return False, f"段 {i} guide_strength 越界（{s.guide_strength}）"
        for j, a in enumerate(self.audios, start=1):
            if not a.audio_path.exists():
                return False, f"音频段 {j} 文件不存在：{a.audio_path}"
        return True, ""
```

- [ ] **Step 4: 验证 PASS**

```bash
pytest tests/test_core/test_video_timeline_model.py -v
```

Expected: 39 passed (31 + 8 new)

- [ ] **Step 5: Commit**

```bash
git add app/core/video_timeline_model.py tests/test_core/test_video_timeline_model.py
git commit -m "feat(video-panel): TimelineModel.validate pre-flight checks"
```

---

## Task 6: Config 扩展 `video_timeline_cache`

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_config.py` 末尾追加：

```python
# ---------- video_timeline_cache ----------

def test_config_default_video_timeline_cache(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.video_timeline_cache == {}


def test_config_loads_video_timeline_cache(tmp_path):
    sp = tmp_path / "settings.json"
    sp.write_text(
        '{"video_timeline_cache": {"frame_rate": 30, "segments": []}}',
        encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.video_timeline_cache == {"frame_rate": 30, "segments": []}


def test_config_update_settings_persists_video_timeline_cache(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(
        video_timeline_cache={"frame_rate": 30, "filename_prefix": "v1"})
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["video_timeline_cache"]["frame_rate"] == 30
    assert data["video_timeline_cache"]["filename_prefix"] == "v1"


def test_config_loads_invalid_video_timeline_cache_falls_back(tmp_path):
    sp = tmp_path / "settings.json"
    # value 是 list 而非 dict —— 应被静默忽略走默认
    sp.write_text('{"video_timeline_cache": ["bad"]}', encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.video_timeline_cache == {}
```

- [ ] **Step 2: 验证 FAIL**

```bash
pytest tests/test_config.py -v -k video_timeline_cache
```

Expected: `AttributeError: 'Config' object has no attribute 'video_timeline_cache'`

- [ ] **Step 3: 加 Config 字段**

打开 `app/config.py`。在 `Config` 数据类的字段列表末尾（紧贴现有 `video_output_dir` 之后）追加：

```python
    video_timeline_cache: dict = field(default_factory=dict)
```

- [ ] **Step 4: 扩展 update_settings 白名单**

找到 `update_settings` 方法里的 `data = {...}` dict（已有 `runninghub_*` 字段）。在末尾追加：

```python
                "video_timeline_cache": self.video_timeline_cache,
```

- [ ] **Step 5: 扩展 load_config 读 settings.json**

找到 `load_config` 函数里现有的 runninghub_* 循环之后。追加：

```python
                if "video_timeline_cache" in data and isinstance(
                        data["video_timeline_cache"], dict):
                    cfg.video_timeline_cache = data["video_timeline_cache"]
```

- [ ] **Step 6: 验证 PASS**

```bash
pytest tests/test_config.py -v -k video_timeline_cache
```

Expected: 4 passed

```bash
pytest tests/test_config.py -v
```

Expected: 25 passed（21 prior + 4 new）

- [ ] **Step 7: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): persist video_timeline_cache field"
```

---

## Task 7: TimelineWidget 基础（场景 + SegmentItem 渲染 + 滚轮缩放）

**Files:**
- Create: `app/ui/widgets/timeline_widget.py`

> **测试豁免：** UI widget 不写自动测，靠手工冒烟。每个 widget task 的 step = py_compile + import smoke + commit。本任务结束时**可启动主程序，目前 timeline 还没接入 MainWindow，所以仅靠下面的 smoke harness 验证。**

- [ ] **Step 1: 新建 `app/ui/widgets/timeline_widget.py`**

```python
"""TimelineWidget：DAW 比例条样式的时间轴（QGraphicsScene 自绘）。

外部信号契约：所有 model 修改都由信号触发，外部 panel 负责写回 model + 调 rebuild()。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QRectF, QSize, QPointF, QMimeData
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QPixmapCache, QDrag, QFont,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsScene, QGraphicsView, QGraphicsTextItem,
)

from app.core.video_timeline_model import (
    TimelineModel, TimelineSegment, TimelineAudio,
)


# ---------- 布局常量 ----------

SEG_LANE_Y = 0
SEG_HEIGHT = 60
LANE_GAP = 10
AUDIO_LANE_Y = SEG_HEIGHT + LANE_GAP   # 70
AUDIO_HEIGHT = 30
RESIZE_HANDLE_W = 6
DEFAULT_PX_PER_FRAME = 5.0
MIN_PX_PER_FRAME = 0.5
MAX_PX_PER_FRAME = 50.0

# MIME types
MIME_IMG_PATH = "application/x-spb-image-path"


# ---------- 缩略图缓存 ----------

def _cached_thumb(path: Path, w: int = 40, h: int = 30) -> QPixmap:
    key = f"spb_seg_thumb::{path}"
    pix = QPixmapCache.find(key)
    if pix:
        return pix
    pix = QPixmap(str(path))
    if pix.isNull():
        pix = QPixmap(w, h); pix.fill(QColor("#444"))
    else:
        pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    QPixmapCache.insert(key, pix)
    return pix


# ---------- Segment Item ----------

class SegmentItem(QGraphicsItem):
    """主轨段卡：宽度 ∝ length_frames。仅渲染；不改 model。"""

    def __init__(self, seg: TimelineSegment, x: float, width: float,
                 display_mode: str, frame_rate: int):
        super().__init__()
        self.seg = seg
        self._width = max(width, 8.0)
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self.setPos(x, SEG_LANE_Y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, SEG_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        # 1. 背景
        bg = (QColor("#3a4a5f") if self.seg.segment_type == "image"
              else QColor("#4a3a3a"))
        painter.fillRect(rect, bg)
        # 2. 边框（选中时高亮）
        if self.isSelected():
            painter.setPen(QPen(QColor("#ffaa00"), 2))
        else:
            painter.setPen(QPen(QColor("#5577aa")
                                 if self.seg.segment_type == "image"
                                 else QColor("#aa6677"), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        # 3. 缩略图（仅 image 段）
        thumb_w = 40
        if self.seg.image_path:
            thumb = _cached_thumb(self.seg.image_path, thumb_w, 30)
            painter.drawPixmap(QRectF(4, 4, thumb_w, 30), thumb, thumb.rect())
        # 4. length badge
        if self._display_mode == "frames":
            badge = f"{self.seg.length_frames}f"
        else:
            sec = self.seg.length_frames / max(self._frame_rate, 1)
            badge = f"{sec:.2f}s"
        painter.setPen(QColor("#ffcc66"))
        f = QFont(); f.setPointSize(8); painter.setFont(f)
        painter.drawText(
            QRectF(4, SEG_HEIGHT - 16, self._width - 8, 12),
            Qt.AlignLeft, badge)
        # 5. prompt 前缀
        if self.seg.local_prompt:
            painter.setPen(QColor("#dddddd"))
            preview = self.seg.local_prompt[:18]
            text_x = thumb_w + 8 if self.seg.image_path else 4
            painter.drawText(
                QRectF(text_x, 4, max(self._width - text_x - 4, 0), SEG_HEIGHT - 20),
                Qt.AlignLeft | Qt.TextWordWrap, preview)


# ---------- Audio Item（Task 9 实现，先占位） ----------

class AudioItem(QGraphicsItem):
    """音频段卡。Task 9 实现完整交互；本任务仅渲染。"""

    def __init__(self, audio: TimelineAudio, x: float, width: float,
                 display_mode: str, frame_rate: int):
        super().__init__()
        self.audio = audio
        self._width = max(width, 8.0)
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self.setPos(x, AUDIO_LANE_Y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, AUDIO_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        painter.fillRect(rect, QColor("#3a4a3a"))
        painter.setPen(QPen(QColor("#66aa77"), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QColor("#ddffdd"))
        f = QFont(); f.setPointSize(8); painter.setFont(f)
        if self._display_mode == "frames":
            badge = f"♪ {self.audio.length_frames}f @{self.audio.start_frame}f"
        else:
            sec_len = self.audio.length_frames / max(self._frame_rate, 1)
            sec_start = self.audio.start_frame / max(self._frame_rate, 1)
            badge = f"♪ {sec_len:.2f}s @{sec_start:.2f}s"
        painter.drawText(rect.adjusted(4, 0, -4, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, badge)


# ---------- Scene ----------

class TimelineScene(QGraphicsScene):
    """场景管理：从 model 重建 items。"""

    def __init__(self, model: TimelineModel, pixels_per_frame: float, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_frame = pixels_per_frame

    def rebuild(self):
        self.clear()
        x = 0.0
        for seg in self.model.segments:
            w = seg.length_frames * self.pixels_per_frame
            item = SegmentItem(seg, x, w,
                                self.model.display_mode, self.model.frame_rate)
            self.addItem(item)
            x += w
        for audio in self.model.audios:
            ax = audio.start_frame * self.pixels_per_frame
            aw = audio.length_frames * self.pixels_per_frame
            self.addItem(
                AudioItem(audio, ax, aw,
                          self.model.display_mode, self.model.frame_rate))
        total_w = max(x, 200) + 100
        self.setSceneRect(0, 0, total_w, AUDIO_LANE_Y + AUDIO_HEIGHT + 20)
        if not self.model.segments and not self.model.audios:
            hint = QGraphicsTextItem("拖一张图到这里开始")
            hint.setDefaultTextColor(QColor("#666"))
            hint.setPos(20, SEG_HEIGHT / 2 - 10)
            self.addItem(hint)


# ---------- View ----------

class TimelineWidget(QGraphicsView):
    """DAW 时间轴 widget。Ctrl+wheel 等比缩放，纯 wheel 横向滚。"""

    # Task 8 / 9 会启用更多信号；本任务先定义全部契约（emit 调用方占位）
    segmentSelected = Signal(str)
    segmentChanged = Signal(str, int)           # (seg_id, new_length_frames)
    segmentReordered = Signal(list)             # [seg_id, ...]
    segmentDoubleClicked = Signal(str)
    segmentDeleteRequested = Signal(str)
    audioChanged = Signal(str, int, int)        # (audio_id, new_start, new_length)
    audioDeleteRequested = Signal(str)
    imageDroppedAt = Signal(object, int)        # (Path, insert_index)
    zoomChanged = Signal(float)

    def __init__(self, model: TimelineModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_frame = DEFAULT_PX_PER_FRAME
        self._scene = TimelineScene(model, self.pixels_per_frame)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setAcceptDrops(True)
        self.rebuild()

    def rebuild(self):
        self._scene.pixels_per_frame = self.pixels_per_frame
        self._scene.rebuild()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
            new_ppf = self.pixels_per_frame * factor
            self.pixels_per_frame = max(MIN_PX_PER_FRAME,
                                         min(MAX_PX_PER_FRAME, new_ppf))
            self.rebuild()
            self.zoomChanged.emit(self.pixels_per_frame)
        else:
            super().wheelEvent(e)
```

- [ ] **Step 2: 语法检查**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
python -m py_compile app/ui/widgets/timeline_widget.py && echo "parsed OK"
```

Expected: `parsed OK`

- [ ] **Step 3: 导入冒烟（用 conda python 因有 PySide6）**

```bash
/root/miniconda3/envs/UniRig/bin/python -c "
from app.core.video_timeline_model import TimelineModel
from app.ui.widgets.timeline_widget import (
    TimelineWidget, TimelineScene, SegmentItem, AudioItem,
    DEFAULT_PX_PER_FRAME, MIN_PX_PER_FRAME, MAX_PX_PER_FRAME, MIME_IMG_PATH,
)
print('imports OK')
"
```

Expected: `imports OK`

如 PySide6 导入失败请用项目实际 Python 解释器（Windows 上为 `python`，conda env 为 `python`）。

- [ ] **Step 4: 现有测试不应回归**

```bash
pytest tests/ 2>&1 | tail -3
```

Expected: 已有测试全过（B-T1..6 + split-resample + runninghub）

- [ ] **Step 5: Commit**

```bash
git add app/ui/widgets/timeline_widget.py
git commit -m "feat(video-panel): TimelineWidget scaffold with paint + wheel zoom"
```

---

## Task 8: TimelineWidget 鼠标交互（拖排序 / 拖右沿 resize / Delete / 选中）

**Files:**
- Modify: `app/ui/widgets/timeline_widget.py`

- [ ] **Step 1: 给 SegmentItem 加交互**

修改 `SegmentItem` 类，加 hover / mousePress / mouseMove / mouseRelease 方法。在类内追加：

```python
    def __init__(self, seg: TimelineSegment, x: float, width: float,
                 display_mode: str, frame_rate: int):
        super().__init__()
        self.seg = seg
        self._width = max(width, 8.0)
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self.setPos(x, SEG_LANE_Y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        # 交互状态
        self._press_x: Optional[float] = None
        self._press_mode: str = "none"     # "resize" | "move" | "none"
        self._resize_start_w: float = 0.0
```

> 这是替换现有 `__init__`。已有字段保留，新增 3 个交互状态。

然后在 `paint` 之后追加方法：

```python
    def hoverMoveEvent(self, event):
        local_x = event.pos().x()
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        local_x = event.pos().x()
        self._press_x = local_x
        self._resize_start_w = self._width
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self._press_mode = "resize"
        else:
            self._press_mode = "move"
        self.setSelected(True)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            event.accept()
            return
        if self._press_mode == "move":
            # 启动 QDrag 一旦移动超过 8px
            if abs(event.pos().x() - self._press_x) > 8:
                self._start_drag()
                self._press_mode = "none"   # drag 启动后状态机重置
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press_mode == "resize":
            # 计算新 length_frames，emit segmentChanged
            view = self._top_view()
            ppf = view.pixels_per_frame if view else 5.0
            new_len = max(1, int(round(self._width / ppf)))
            if view is not None:
                view.segmentChanged.emit(self.seg.seg_id, new_len)
            self._press_mode = "none"
            event.accept()
            return
        if self._press_mode == "move":
            # 原位释放 = 仅选中
            view = self._top_view()
            if view is not None:
                view.segmentSelected.emit(self.seg.seg_id)
            self._press_mode = "none"
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        view = self._top_view()
        if view is not None:
            view.segmentDoubleClicked.emit(self.seg.seg_id)
        event.accept()

    def _start_drag(self):
        view = self._top_view()
        if view is None:
            return
        mime = QMimeData()
        mime.setData("application/x-spb-seg-id",
                     self.seg.seg_id.encode("utf-8"))
        drag = QDrag(view)
        drag.setMimeData(mime)
        # 拖动时候 setPixmap 用空 pixmap 避免视觉残影；落点由 scene 处理
        drag.exec(Qt.MoveAction)

    def _top_view(self) -> Optional["TimelineWidget"]:
        scene = self.scene()
        if scene is None:
            return None
        views = scene.views()
        return views[0] if views else None
```

- [ ] **Step 2: 给 TimelineScene 加拖排序 drop 处理**

修改 `TimelineScene` 类，加 dragEnter / dragMove / dropEvent。在 `rebuild` 方法之后追加：

```python
    def dragEnterEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        view = self.views()[0] if self.views() else None
        if view is None:
            return super().dropEvent(e)
        drop_x = e.scenePos().x()
        insert_idx = self._find_seg_insert_index(drop_x)
        if e.mimeData().hasFormat("application/x-spb-seg-id"):
            seg_id = e.mimeData().data(
                "application/x-spb-seg-id").data().decode("utf-8")
            # 计算新顺序：移除原 seg_id 后在 insert_idx 插入
            ids = [s.seg_id for s in self.model.segments]
            if seg_id in ids:
                ids.remove(seg_id)
                ids.insert(min(insert_idx, len(ids)), seg_id)
                view.segmentReordered.emit(ids)
            e.acceptProposedAction()
            return
        # MIME_IMG_PATH: Task 9 处理；本任务先占位
        super().dropEvent(e)

    def _find_seg_insert_index(self, drop_x: float) -> int:
        x = 0.0
        for i, s in enumerate(self.model.segments):
            w = s.length_frames * self.pixels_per_frame
            if drop_x < x + w / 2:
                return i
            x += w
        return len(self.model.segments)
```

- [ ] **Step 3: 给 TimelineWidget 加 Delete 键支持**

修改 `TimelineWidget.__init__` 中 `setRenderHint(...)` 这两行之后追加：

```python
        self.setFocusPolicy(Qt.StrongFocus)
```

在类末尾追加 keyPressEvent：

```python
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            items = self._scene.selectedItems()
            for item in items:
                if isinstance(item, SegmentItem):
                    self.segmentDeleteRequested.emit(item.seg.seg_id)
                    return
                if isinstance(item, AudioItem):
                    self.audioDeleteRequested.emit(item.audio.audio_id)
                    return
        super().keyPressEvent(e)

    def _current_selected_seg_id(self) -> str:
        for item in self._scene.selectedItems():
            if isinstance(item, SegmentItem):
                return item.seg.seg_id
        return ""

    def currently_selected_seg_id(self) -> str:
        """公共 API 给 VideoPanel 调（display_mode 切换时获取当前段）。"""
        return self._current_selected_seg_id()
```

- [ ] **Step 4: 把现有 rebuild 改成保留选中**

替换 `TimelineWidget.rebuild`：

```python
    def rebuild(self):
        selected_id = self._current_selected_seg_id() if hasattr(self, "_scene") else ""
        self._scene.pixels_per_frame = self.pixels_per_frame
        self._scene.rebuild()
        if selected_id:
            for item in self._scene.items():
                if isinstance(item, SegmentItem) and item.seg.seg_id == selected_id:
                    item.setSelected(True)
                    break
```

- [ ] **Step 5: 语法 + 导入冒烟**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
python -m py_compile app/ui/widgets/timeline_widget.py && echo "parsed OK"
/root/miniconda3/envs/UniRig/bin/python -c "
from app.ui.widgets.timeline_widget import TimelineWidget, SegmentItem, TimelineScene
print('imports OK')
"
```

Expected: `parsed OK` + `imports OK`

- [ ] **Step 6: 全量回归**

```bash
pytest 2>&1 | tail -3
```

Expected: 无 regression

- [ ] **Step 7: Commit**

```bash
git add app/ui/widgets/timeline_widget.py
git commit -m "feat(video-panel): TimelineWidget mouse interactions and signals"
```

---

## Task 9: TimelineWidget — AudioItem 交互 + 图片 drop

**Files:**
- Modify: `app/ui/widgets/timeline_widget.py`

- [ ] **Step 1: AudioItem 加拖动 / resize 交互**

替换 `AudioItem` 类整体：

```python
class AudioItem(QGraphicsItem):
    """音频段卡：整体拖动改 start_frame；右沿拖动改 length。"""

    def __init__(self, audio: TimelineAudio, x: float, width: float,
                 display_mode: str, frame_rate: int):
        super().__init__()
        self.audio = audio
        self._width = max(width, 8.0)
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self.setPos(x, AUDIO_LANE_Y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._press_x: Optional[float] = None
        self._press_mode: str = "none"
        self._resize_start_w: float = 0.0
        self._move_start_pos: Optional[QPointF] = None

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, AUDIO_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        painter.fillRect(rect, QColor("#3a4a3a"))
        if self.isSelected():
            painter.setPen(QPen(QColor("#ffaa00"), 2))
        else:
            painter.setPen(QPen(QColor("#66aa77"), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QColor("#ddffdd"))
        f = QFont(); f.setPointSize(8); painter.setFont(f)
        if self._display_mode == "frames":
            badge = f"♪ {self.audio.length_frames}f @{self.audio.start_frame}f"
        else:
            sec_len = self.audio.length_frames / max(self._frame_rate, 1)
            sec_start = self.audio.start_frame / max(self._frame_rate, 1)
            badge = f"♪ {sec_len:.2f}s @{sec_start:.2f}s"
        painter.drawText(rect.adjusted(4, 0, -4, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, badge)

    def hoverMoveEvent(self, event):
        local_x = event.pos().x()
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        local_x = event.pos().x()
        self._press_x = local_x
        self._resize_start_w = self._width
        self._move_start_pos = QPointF(self.pos())
        if self._width - RESIZE_HANDLE_W <= local_x <= self._width:
            self._press_mode = "resize"
        else:
            self._press_mode = "move"
        self.setSelected(True)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            event.accept()
            return
        if self._press_mode == "move":
            scene_dx = event.scenePos().x() - (
                self._move_start_pos.x() + self._press_x)
            new_x = max(0, self._move_start_pos.x() + scene_dx)
            self.setPos(new_x, AUDIO_LANE_Y)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        view = self._top_view()
        if view is None:
            return super().mouseReleaseEvent(event)
        ppf = view.pixels_per_frame
        if self._press_mode == "resize":
            new_len = max(1, int(round(self._width / ppf)))
            view.audioChanged.emit(self.audio.audio_id,
                                    self.audio.start_frame, new_len)
            self._press_mode = "none"
            event.accept()
            return
        if self._press_mode == "move":
            new_start = max(0, int(round(self.pos().x() / ppf)))
            view.audioChanged.emit(self.audio.audio_id,
                                    new_start, self.audio.length_frames)
            self._press_mode = "none"
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _top_view(self) -> Optional["TimelineWidget"]:
        scene = self.scene()
        if scene is None:
            return None
        views = scene.views()
        return views[0] if views else None
```

- [ ] **Step 2: TimelineScene.dropEvent 加图片 MIME 处理**

修改 `TimelineScene.dropEvent`（已有 seg-id 分支保留），把 `super().dropEvent(e)` 之前替换为：

```python
        if e.mimeData().hasFormat(MIME_IMG_PATH):
            raw = e.mimeData().data(MIME_IMG_PATH).data().decode("utf-8")
            path = Path(raw)
            view.imageDroppedAt.emit(path, insert_idx)
            e.acceptProposedAction()
            return
        super().dropEvent(e)
```

> 最终 dropEvent 完整内容里 seg-id 分支已存在；MIME_IMG_PATH 分支放它之后、super 之前。

- [ ] **Step 3: 语法 + 导入冒烟**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
python -m py_compile app/ui/widgets/timeline_widget.py && echo "parsed OK"
/root/miniconda3/envs/UniRig/bin/python -c "
from app.ui.widgets.timeline_widget import AudioItem
print('imports OK')
"
```

Expected: `parsed OK` + `imports OK`

- [ ] **Step 4: 全量回归**

```bash
pytest 2>&1 | tail -3
```

Expected: 无 regression

- [ ] **Step 5: Commit**

```bash
git add app/ui/widgets/timeline_widget.py
git commit -m "feat(video-panel): TimelineWidget AudioItem interactions and image drop"
```

---

## Task 10: ImagePoolWidget

**Files:**
- Create: `app/ui/widgets/image_pool_widget.py`

- [ ] **Step 1: 新建文件**

```python
"""ImagePoolWidget：持久图片池。横向 IconMode + 拖出到 TimelineWidget。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal, QMimeData
from PySide6.QtGui import QBrush, QColor, QDrag, QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem


MIME_IMG_PATH = "application/x-spb-image-path"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
THUMB_SIZE = QSize(64, 48)


class ImagePoolWidget(QListWidget):
    """图片池：拖出到时间轴；显示已用/未用着色。"""

    imagesAdded = Signal(list)              # list[Path]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Static)
        self.setResizeMode(QListWidget.Adjust)
        self.setIconSize(THUMB_SIZE)
        self.setSpacing(4)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QListWidget.SingleSelection)

    # ---------- 外部 API ----------

    def set_paths(self, paths: list[Path]):
        """重建池子里的 items（VideoPanel 在 model.pool 变化后调）。"""
        self.clear()
        for p in paths:
            item = QListWidgetItem(self._make_icon(p), p.name)
            item.setData(Qt.UserRole, p)
            item.setToolTip(str(p))
            self.addItem(item)

    def refresh_usage(self, usage: dict[Path, int]):
        """根据 model.pool_usage() 给已用/未用着色。"""
        for i in range(self.count()):
            item = self.item(i)
            p = item.data(Qt.UserRole)
            used = usage.get(p, 0) > 0
            item.setForeground(QBrush(QColor("#ffffff") if used
                                        else QColor("#666666")))
            item.setToolTip(f"{p}\n被引用 {usage.get(p, 0)} 次")

    # ---------- 拖出（→ TimelineWidget） ----------

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        path: Path = item.data(Qt.UserRole)
        mime = QMimeData()
        mime.setData(MIME_IMG_PATH, str(path).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(item.icon().pixmap(THUMB_SIZE))
        drag.exec(Qt.CopyAction)

    # ---------- 拖入（OS 文件 → 池） ----------

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not e.mimeData().hasUrls():
            return super().dropEvent(e)
        paths = []
        for url in e.mimeData().urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in IMG_EXTS:
                paths.append(Path(local))
        if paths:
            self.imagesAdded.emit(paths)
            e.acceptProposedAction()

    # ---------- 私有 ----------

    def _make_icon(self, path: Path) -> QIcon:
        pix = QPixmap(str(path))
        if pix.isNull():
            pix = QPixmap(THUMB_SIZE); pix.fill(QColor("#444"))
        else:
            pix = pix.scaled(THUMB_SIZE, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
        return QIcon(pix)
```

- [ ] **Step 2: 语法 + 导入**

```bash
python -m py_compile app/ui/widgets/image_pool_widget.py && echo "parsed OK"
/root/miniconda3/envs/UniRig/bin/python -c "
from app.ui.widgets.image_pool_widget import ImagePoolWidget, MIME_IMG_PATH, IMG_EXTS, THUMB_SIZE
print('imports OK')
"
```

Expected: `parsed OK` + `imports OK`

- [ ] **Step 3: 全量回归**

```bash
pytest 2>&1 | tail -3
```

Expected: 无 regression

- [ ] **Step 4: Commit**

```bash
git add app/ui/widgets/image_pool_widget.py
git commit -m "feat(video-panel): ImagePoolWidget with drag-out and OS drop"
```

---

## Task 11: 3 个小 widget（SegmentEditor + VideoGlobalForm + VideoStatusBar）

**Files:**
- Create: `app/ui/widgets/segment_editor.py`
- Create: `app/ui/widgets/video_global_form.py`
- Create: `app/ui/widgets/video_status_bar.py`

3 个简单 widget 一次性建。

- [ ] **Step 1: 新建 SegmentEditor**

```python
# app/ui/widgets/segment_editor.py
"""SegmentEditor：per-seg 编辑表单。始终可见，未选中时灰化。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QFormLayout, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
    QWidget,
)

from app.core.video_timeline_model import TimelineSegment


class SegmentEditor(QGroupBox):
    """per-seg 编辑：local_prompt + length（按 display_mode 切单位）+ guide_strength。

    所有控件未绑定时 disabled；bind_to 切换显示对象。
    每次字段变化 emit segmentEdited(seg_id, field_name, new_value)。
    """

    segmentEdited = Signal(str, str, object)   # (seg_id, field, value)

    def __init__(self, parent=None):
        super().__init__("当前段（点时间轴选中编辑）", parent)
        self._bound_seg_id = ""
        self._display_mode = "seconds"
        self._frame_rate = 24
        self._suspend = False

        form = QFormLayout(self)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setPlaceholderText("本段 prompt（仅作用于此段）")
        form.addRow("Prompt", self.prompt_edit)

        self.length_spin = QSpinBox()
        self.length_spin.setRange(1, 99999)
        self.length_spin.setValue(24)
        form.addRow("长度", self.length_spin)

        self.guide_spin = QDoubleSpinBox()
        self.guide_spin.setRange(0.0, 1.0)
        self.guide_spin.setSingleStep(0.05)
        self.guide_spin.setDecimals(2)
        self.guide_spin.setValue(1.0)
        form.addRow("Guide", self.guide_spin)

        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.length_spin.valueChanged.connect(self._on_length_changed)
        self.guide_spin.valueChanged.connect(self._on_guide_changed)

        self._set_enabled_all(False)

    # ---------- 公共 API ----------

    def bind_to(self, seg: Optional[TimelineSegment],
                display_mode: str, frame_rate: int) -> None:
        self._display_mode = display_mode
        self._frame_rate = frame_rate
        self._suspend = True
        if seg is None:
            self._bound_seg_id = ""
            self.prompt_edit.clear()
            self.length_spin.setValue(1)
            self.guide_spin.setValue(1.0)
            self._set_enabled_all(False)
        else:
            self._bound_seg_id = seg.seg_id
            self.prompt_edit.setPlainText(seg.local_prompt)
            self.length_spin.setValue(seg.length_frames)
            self.guide_spin.setValue(seg.guide_strength)
            self._update_length_suffix(seg.length_frames)
            self._set_enabled_all(True)
        self._suspend = False

    # ---------- 内部 ----------

    def _set_enabled_all(self, on: bool):
        for w in (self.prompt_edit, self.length_spin, self.guide_spin):
            w.setEnabled(on)

    def _update_length_suffix(self, frames: int):
        if self._display_mode == "frames":
            self.length_spin.setSuffix(" f")
        else:
            sec = frames / max(self._frame_rate, 1)
            self.length_spin.setSuffix(f" f (≈{sec:.2f}s)")

    def _on_prompt_changed(self):
        if self._suspend or not self._bound_seg_id:
            return
        self.segmentEdited.emit(self._bound_seg_id, "local_prompt",
                                 self.prompt_edit.toPlainText())

    def _on_length_changed(self, value: int):
        if self._suspend or not self._bound_seg_id:
            return
        self._update_length_suffix(value)
        self.segmentEdited.emit(self._bound_seg_id, "length_frames", value)

    def _on_guide_changed(self, value: float):
        if self._suspend or not self._bound_seg_id:
            return
        self.segmentEdited.emit(self._bound_seg_id, "guide_strength", value)
```

- [ ] **Step 2: 新建 VideoGlobalForm**

```python
# app/ui/widgets/video_global_form.py
"""VideoGlobalForm：全局参数表单。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QFormLayout, QPlainTextEdit, QCheckBox, QSpinBox,
    QComboBox, QLineEdit, QHBoxLayout, QWidget, QRadioButton, QButtonGroup,
    QLabel,
)

from app.core.video_timeline_model import TimelineModel


RESOLUTION_PRESETS = [
    "1280x720 (16:9) (横屏)",
    "720x1280 (9:16) (竖屏)",
    "1024x1024 (1:1)",
    "自定义...",
]


class VideoGlobalForm(QGroupBox):
    """全局：global_prompt / frame_rate / display_mode / 分辨率 / filename_prefix。

    单一 globalChanged 信号；外部用 get_state() 一次性读所有字段。
    """

    globalChanged = Signal()

    def __init__(self, parent=None):
        super().__init__("全局参数", parent)
        self._suspend = False
        self._build_ui()
        self._wire()

    def _build_ui(self):
        form = QFormLayout(self)

        # global_prompt
        self.use_global_cb = QCheckBox("启用 global_prompt")
        self.use_global_cb.setChecked(True)
        form.addRow(self.use_global_cb)

        self.global_prompt_edit = QPlainTextEdit()
        self.global_prompt_edit.setMaximumHeight(60)
        self.global_prompt_edit.setPlaceholderText("全片统一风格/角色描述…")
        form.addRow("Global prompt", self.global_prompt_edit)

        # frame_rate
        self.fr_spin = QSpinBox()
        self.fr_spin.setRange(1, 120)
        self.fr_spin.setValue(24)
        self.fr_spin.setSuffix(" fps")
        form.addRow("帧率", self.fr_spin)

        # display_mode
        mode_row = QHBoxLayout()
        self.mode_seconds_btn = QRadioButton("秒")
        self.mode_frames_btn = QRadioButton("帧")
        self.mode_seconds_btn.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.mode_seconds_btn)
        self._mode_group.addButton(self.mode_frames_btn)
        mode_row.addWidget(self.mode_seconds_btn)
        mode_row.addWidget(self.mode_frames_btn)
        mode_row.addStretch(1)
        mode_wrap = QWidget(); mode_wrap.setLayout(mode_row)
        form.addRow("时间显示", mode_wrap)

        # 分辨率
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTION_PRESETS)
        form.addRow("分辨率", self.resolution_combo)

        custom_row = QHBoxLayout()
        self.custom_w_spin = QSpinBox()
        self.custom_w_spin.setRange(64, 4096); self.custom_w_spin.setValue(1024)
        self.custom_h_spin = QSpinBox()
        self.custom_h_spin.setRange(64, 4096); self.custom_h_spin.setValue(1024)
        custom_row.addWidget(self.custom_w_spin)
        custom_row.addWidget(QLabel("×"))
        custom_row.addWidget(self.custom_h_spin)
        custom_row.addStretch(1)
        self.custom_wrap = QWidget(); self.custom_wrap.setLayout(custom_row)
        self.custom_wrap.setVisible(False)
        form.addRow("自定义 W×H", self.custom_wrap)

        # filename_prefix
        self.filename_prefix_edit = QLineEdit("spb_video")
        form.addRow("输出文件名前缀", self.filename_prefix_edit)

    def _wire(self):
        self.use_global_cb.toggled.connect(self._emit)
        self.global_prompt_edit.textChanged.connect(self._emit)
        self.fr_spin.valueChanged.connect(self._emit)
        self.mode_seconds_btn.toggled.connect(self._emit)
        self.resolution_combo.currentTextChanged.connect(self._on_res_changed)
        self.custom_w_spin.valueChanged.connect(self._emit)
        self.custom_h_spin.valueChanged.connect(self._emit)
        self.filename_prefix_edit.textChanged.connect(self._emit)

    def _on_res_changed(self, text: str):
        self.custom_wrap.setVisible(text == "自定义...")
        self._emit()

    def _emit(self, *_args):
        if self._suspend:
            return
        self.globalChanged.emit()

    # ---------- 公共 API ----------

    def get_state(self) -> dict:
        is_custom = self.resolution_combo.currentText() == "自定义..."
        return {
            "global_prompt": self.global_prompt_edit.toPlainText(),
            "use_global_prompt": self.use_global_cb.isChecked(),
            "frame_rate": self.fr_spin.value(),
            "display_mode": "seconds" if self.mode_seconds_btn.isChecked() else "frames",
            "resolution_preset": (self.resolution_combo.currentText()
                                   if not is_custom
                                   else "1280x720 (16:9) (横屏)"),
            "use_custom_resolution": is_custom,
            "custom_width": self.custom_w_spin.value(),
            "custom_height": self.custom_h_spin.value(),
            "filename_prefix": self.filename_prefix_edit.text().strip()
                                or "spb_video",
        }

    def set_state(self, m: TimelineModel) -> None:
        self._suspend = True
        self.use_global_cb.setChecked(m.use_global_prompt)
        self.global_prompt_edit.setPlainText(m.global_prompt)
        self.fr_spin.setValue(m.frame_rate)
        if m.display_mode == "seconds":
            self.mode_seconds_btn.setChecked(True)
        else:
            self.mode_frames_btn.setChecked(True)
        if m.use_custom_resolution:
            self.resolution_combo.setCurrentText("自定义...")
            self.custom_w_spin.setValue(m.custom_width)
            self.custom_h_spin.setValue(m.custom_height)
        else:
            idx = self.resolution_combo.findText(m.resolution_preset)
            if idx >= 0:
                self.resolution_combo.setCurrentIndex(idx)
        self.filename_prefix_edit.setText(m.filename_prefix)
        self.custom_wrap.setVisible(m.use_custom_resolution)
        self._suspend = False
```

- [ ] **Step 3: 新建 VideoStatusBar**

```python
# app/ui/widgets/video_status_bar.py
"""VideoStatusBar：底部状态栏 + 提交/取消按钮。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class VideoStatusBar(QWidget):
    """状态机：idle / uploading / status / done / failed。"""

    submitRequested = Signal()
    cancelRequested = Signal()
    openFolderRequested = Signal(object)   # Path

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.status_label = QLabel("空闲")
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setOpenExternalLinks(False)
        self.status_label.linkActivated.connect(self._on_link)
        layout.addWidget(self.status_label, 1)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancelRequested)
        layout.addWidget(self.cancel_btn)

        self.submit_btn = QPushButton("🎬 提交")
        self.submit_btn.clicked.connect(self.submitRequested)
        layout.addWidget(self.submit_btn)

    # ---------- 状态机 API ----------

    def set_idle(self):
        self.status_label.setText("空闲")
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    def set_uploading(self, done: int, total: int, name: str):
        self.status_label.setText(f"上传 {done}/{total}：{name}")
        self.submit_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

    def set_status(self, status: str):
        self.status_label.setText(f"任务状态：{status}")
        self.submit_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

    def set_done(self, mp4_path: Path):
        self.status_label.setText(
            f'<span style="color:#5fa">✓ 完成：'
            f'<a href="open:{mp4_path}" '
            f'style="color:#7fc">{mp4_path.name}</a></span>')
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    def set_failed(self, reason: str):
        msg = reason[:120] + ("…" if len(reason) > 120 else "")
        self.status_label.setText(
            f'<span style="color:#f66">✗ 失败：{msg}</span>')
        self.submit_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    # ---------- 内部 ----------

    def _on_link(self, link: str):
        if link.startswith("open:"):
            self.openFolderRequested.emit(Path(link[5:]).parent)
```

- [ ] **Step 4: 语法 + 导入**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
for f in app/ui/widgets/segment_editor.py app/ui/widgets/video_global_form.py app/ui/widgets/video_status_bar.py; do
    python -m py_compile "$f" && echo "$f parsed OK"
done
/root/miniconda3/envs/UniRig/bin/python -c "
from app.ui.widgets.segment_editor import SegmentEditor
from app.ui.widgets.video_global_form import VideoGlobalForm, RESOLUTION_PRESETS
from app.ui.widgets.video_status_bar import VideoStatusBar
print('imports OK')
"
```

Expected: 3 个 parsed OK + 1 个 imports OK

- [ ] **Step 5: 全量回归**

```bash
pytest 2>&1 | tail -3
```

Expected: 无 regression

- [ ] **Step 6: Commit**

```bash
git add app/ui/widgets/segment_editor.py app/ui/widgets/video_global_form.py app/ui/widgets/video_status_bar.py
git commit -m "feat(video-panel): SegmentEditor, VideoGlobalForm, VideoStatusBar"
```

---

## Task 12: RunningHubSettingsDialog

**Files:**
- Create: `app/ui/dialogs/__init__.py`
- Create: `app/ui/dialogs/runninghub_settings_dialog.py`

- [ ] **Step 1: 新建 dialogs 目录**

```bash
mkdir -p app/ui/dialogs
touch app/ui/dialogs/__init__.py
```

- [ ] **Step 2: 新建 dialog 文件**

```python
# app/ui/dialogs/runninghub_settings_dialog.py
"""RunningHubSettingsDialog：菜单栏「设置 → RunningHub…」打开。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QFileDialog, QRadioButton, QButtonGroup, QCheckBox, QWidget,
    QDialogButtonBox, QMessageBox, QFrame,
)

from app.config import Config
from app.providers.runninghub import (
    RunningHubClient, RunningHubUnavailable, RunningHubTaskFailed,
)
from app.ui.worker import FunctionWorker


class RunningHubSettingsDialog(QDialog):
    """配置 api_key / 输出目录 / 提交模式 / base_url / 模板。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker: FunctionWorker | None = None
        self.setWindowTitle("RunningHub 配置")
        self.setModal(True)
        self.resize(560, 460)
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        # API Key
        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setMaximumWidth(40)
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self.api_key_edit, 1)
        key_row.addWidget(self.show_key_btn)
        key_wrap = QWidget(); key_wrap.setLayout(key_row)
        form.addRow("API Key", key_wrap)

        # Base URL
        self.base_url_edit = QLineEdit()
        form.addRow("Base URL", self.base_url_edit)

        # 视频输出目录
        out_row = QHBoxLayout()
        self.video_out_edit = QLineEdit()
        self.video_out_edit.setPlaceholderText("空=用 state.output_dir")
        b = QPushButton("浏览…")
        b.clicked.connect(self._browse_video_out)
        out_row.addWidget(self.video_out_edit, 1)
        out_row.addWidget(b)
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        form.addRow("视频输出目录", out_wrap)

        # 提交模式
        mode_row = QHBoxLayout()
        self.mode_inline_btn = QRadioButton("Inline（推荐）")
        self.mode_id_btn = QRadioButton("ID + nodeInfoList")
        self.mode_inline_btn.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.mode_inline_btn)
        self._mode_group.addButton(self.mode_id_btn)
        self.mode_inline_btn.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_inline_btn)
        mode_row.addWidget(self.mode_id_btn)
        mode_row.addStretch(1)
        mode_wrap = QWidget(); mode_wrap.setLayout(mode_row)
        form.addRow("提交模式", mode_wrap)

        # Workflow ID
        self.workflow_id_edit = QLineEdit()
        self.workflow_id_edit.setPlaceholderText("仅 ID 模式需要")
        self.workflow_id_edit.setEnabled(False)
        form.addRow("Workflow ID", self.workflow_id_edit)

        # 工作流模板
        tpl_row = QHBoxLayout()
        self.use_builtin_cb = QCheckBox("使用内置模板")
        self.use_builtin_cb.setChecked(True)
        self.use_builtin_cb.toggled.connect(self._on_builtin_toggled)
        tpl_row.addWidget(self.use_builtin_cb)
        tpl_wrap = QWidget(); tpl_wrap.setLayout(tpl_row)
        form.addRow(tpl_wrap)

        tpl_path_row = QHBoxLayout()
        self.template_path_edit = QLineEdit()
        self.template_path_edit.setEnabled(False)
        self.template_browse_btn = QPushButton("浏览…")
        self.template_browse_btn.setEnabled(False)
        self.template_browse_btn.clicked.connect(self._browse_template)
        tpl_path_row.addWidget(self.template_path_edit, 1)
        tpl_path_row.addWidget(self.template_browse_btn)
        tpl_path_wrap = QWidget(); tpl_path_wrap.setLayout(tpl_path_row)
        form.addRow("自定义模板路径", tpl_path_wrap)

        root.addLayout(form)

        # 分割线
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        # 测试连接
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test_connection)
        self.test_result_label = QLabel("")
        self.test_result_label.setTextFormat(Qt.RichText)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result_label, 1)
        root.addLayout(test_row)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_from_cfg(self):
        self.api_key_edit.setText(self.cfg.runninghub_api_key)
        self.base_url_edit.setText(
            self.cfg.runninghub_base_url or "https://www.runninghub.cn")
        self.video_out_edit.setText(self.cfg.video_output_dir)
        if self.cfg.runninghub_submit_mode == "id":
            self.mode_id_btn.setChecked(True)
        else:
            self.mode_inline_btn.setChecked(True)
        self.workflow_id_edit.setText(self.cfg.runninghub_workflow_id)
        custom_tpl = self.cfg.runninghub_template_path
        if custom_tpl:
            self.use_builtin_cb.setChecked(False)
            self.template_path_edit.setText(custom_tpl)
        else:
            self.use_builtin_cb.setChecked(True)

    # ---------- 槽 ----------

    def _toggle_key_visibility(self, on: bool):
        self.api_key_edit.setEchoMode(
            QLineEdit.Normal if on else QLineEdit.Password)

    def _on_mode_changed(self):
        self.workflow_id_edit.setEnabled(self.mode_id_btn.isChecked())

    def _on_builtin_toggled(self, on: bool):
        self.template_path_edit.setEnabled(not on)
        self.template_browse_btn.setEnabled(not on)
        if on:
            self.template_path_edit.clear()

    def _browse_video_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择视频输出目录", self.video_out_edit.text() or "")
        if d:
            self.video_out_edit.setText(d)

    def _browse_template(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择工作流模板", "", "JSON (*.json)")
        if p:
            self.template_path_edit.setText(p)

    def _on_test_connection(self):
        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://www.runninghub.cn"
        if not api_key:
            self.test_result_label.setText(
                '<span style="color:#f66">未填 API Key</span>')
            return
        self.test_result_label.setText("测试中…")
        self.test_btn.setEnabled(False)

        def task():
            try:
                with RunningHubClient(api_key, base_url=base_url) as c:
                    c.query_task("__spb_probe__")
                return True, "✓ 鉴权通过（API Key 可用）"
            except RunningHubUnavailable as e:
                return False, f"✗ 不可达：{e}"
            except Exception as e:
                return False, f"⚠ 未知错误：{type(e).__name__}: {e}"

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_test_done)
        self._worker.failed.connect(
            lambda e: self._on_test_done((False, f"⚠ 内部错：{e}")))
        self._worker.start()

    def _on_test_done(self, result):
        ok, msg = result
        color = "#5fa" if ok else "#f66"
        self.test_result_label.setText(f'<span style="color:{color}">{msg}</span>')
        self.test_btn.setEnabled(True)

    def accept(self):
        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://www.runninghub.cn"
        mode = "id" if self.mode_id_btn.isChecked() else "inline"
        wf_id = self.workflow_id_edit.text().strip()
        if mode == "id" and not wf_id:
            QMessageBox.warning(
                self, "校验失败",
                "提交模式 = ID 时必须填 Workflow ID")
            return
        template_path = ("" if self.use_builtin_cb.isChecked()
                         else self.template_path_edit.text().strip())
        video_out = self.video_out_edit.text().strip()
        self.cfg.update_settings(
            runninghub_api_key=api_key,
            runninghub_base_url=base_url,
            runninghub_submit_mode=mode,
            runninghub_workflow_id=wf_id,
            runninghub_template_path=template_path,
            video_output_dir=video_out,
        )
        super().accept()
```

- [ ] **Step 3: 语法 + 导入**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
python -m py_compile app/ui/dialogs/runninghub_settings_dialog.py && echo "parsed OK"
/root/miniconda3/envs/UniRig/bin/python -c "
from app.ui.dialogs.runninghub_settings_dialog import RunningHubSettingsDialog
print('imports OK')
"
```

Expected: `parsed OK` + `imports OK`

- [ ] **Step 4: 全量回归**

```bash
pytest 2>&1 | tail -3
```

Expected: 无 regression

- [ ] **Step 5: Commit**

```bash
git add app/ui/dialogs/__init__.py app/ui/dialogs/runninghub_settings_dialog.py
git commit -m "feat(video-panel): RunningHubSettingsDialog"
```

---

## Task 13: VideoPanel 装配（5 层布局 + 信号编排 + 缓存 + 提交链路）

**Files:**
- Create: `app/ui/panels/video_panel.py`

- [ ] **Step 1: 新建 VideoPanel**

```python
# app/ui/panels/video_panel.py
"""VideoPanel：视频生成主面板。BasePanel 子类，独占主窗口内容区。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
    QListWidget, QWidget,
)

from app.config import Config
from app.core.video_timeline_model import TimelineModel
from app.providers.runninghub import (
    RunningHubClient, LTXTaskBuilder, submit_ltx_task,
    RunningHubUnavailable, RunningHubInvalidSpec,
    RunningHubUploadError, RunningHubTaskFailed,
    resolve_api_key, resolve_template_path, resolve_video_output_dir,
)
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.widgets.image_pool_widget import ImagePoolWidget
from app.ui.widgets.segment_editor import SegmentEditor
from app.ui.widgets.timeline_widget import TimelineWidget
from app.ui.widgets.video_global_form import VideoGlobalForm
from app.ui.widgets.video_status_bar import VideoStatusBar
from app.ui.worker import FunctionWorker


log = logging.getLogger(__name__)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class VideoPanel(BasePanel):
    """视频生成主面板。

    5 层纵向：图片池 + toolbar / TimelineWidget / SegmentEditor / VideoGlobalForm / VideoStatusBar。
    所有 model 写入只在本类。
    """

    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self.model = self._restore_model()
        self._worker: Optional[FunctionWorker] = None
        self._cancel_flag = {"v": False}
        self._build_ui()
        self._wire()
        self._refresh_all()

    # ---------- BasePanel override ----------

    def select_mode(self) -> str:
        return "none"

    def validate(self) -> tuple[bool, str]:
        return False, "请使用面板内「🎬 提交」按钮"

    def execute(self):
        raise NotImplementedError("video panel uses internal submit button")

    # ---------- UI ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # 1. 图片池 + toolbar
        pool_wrapper = QWidget()
        pw = QVBoxLayout(pool_wrapper)
        pw.setContentsMargins(0, 0, 0, 0)
        pool_toolbar = QHBoxLayout()
        self.btn_import = QPushButton("+ 批量导入图片")
        self.btn_import_dir = QPushButton("+ 当前目录全部")
        self.btn_clear_pool = QPushButton("🗑 清空池")
        self.btn_add_text = QPushButton("+ Add Text")
        self.btn_add_audio = QPushButton("+ Add Audio")
        for b in (self.btn_import, self.btn_import_dir, self.btn_clear_pool):
            pool_toolbar.addWidget(b)
        pool_toolbar.addStretch(1)
        pool_toolbar.addWidget(self.btn_add_text)
        pool_toolbar.addWidget(self.btn_add_audio)
        pw.addLayout(pool_toolbar)
        self.image_pool = ImagePoolWidget()
        self.image_pool.setMaximumHeight(80)
        pw.addWidget(self.image_pool, 1)
        pool_wrapper.setMinimumHeight(130)
        pool_wrapper.setMaximumHeight(140)
        root.addWidget(pool_wrapper)

        # 2. 时间轴
        self.timeline = TimelineWidget(self.model)
        self.timeline.setMinimumHeight(160)
        root.addWidget(self.timeline, 3)

        # 3. per-seg 编辑器
        self.seg_editor = SegmentEditor()
        self.seg_editor.setMaximumHeight(180)
        root.addWidget(self.seg_editor)

        # 4. 全局参数
        self.global_form = VideoGlobalForm()
        self.global_form.setMaximumHeight(260)
        root.addWidget(self.global_form)

        # 5. 状态栏
        self.video_status_bar = VideoStatusBar()
        root.addWidget(self.video_status_bar)

    def _wire(self):
        # toolbar
        self.btn_import.clicked.connect(self._on_import_images)
        self.btn_import_dir.clicked.connect(self._on_import_current_dir)
        self.btn_clear_pool.clicked.connect(self._on_clear_pool)
        self.btn_add_text.clicked.connect(self._on_add_text)
        self.btn_add_audio.clicked.connect(self._on_add_audio)

        # image pool（OS 拖入 → 加池）
        self.image_pool.imagesAdded.connect(self._on_pool_images_added)

        # timeline
        self.timeline.imageDroppedAt.connect(self._on_image_dropped_at)
        self.timeline.segmentSelected.connect(self._on_segment_selected)
        self.timeline.segmentChanged.connect(self._on_segment_resized)
        self.timeline.segmentReordered.connect(self._on_segments_reordered)
        self.timeline.segmentDeleteRequested.connect(self._on_segment_delete)
        self.timeline.audioChanged.connect(self._on_audio_changed)
        self.timeline.audioDeleteRequested.connect(self._on_audio_delete)

        # seg editor
        self.seg_editor.segmentEdited.connect(self._on_segment_edited)

        # global form
        self.global_form.globalChanged.connect(self._on_global_changed)

        # status bar
        self.video_status_bar.submitRequested.connect(self._on_submit)
        self.video_status_bar.cancelRequested.connect(self._on_cancel)
        self.video_status_bar.openFolderRequested.connect(self._on_open_folder)

    def _refresh_all(self):
        self._refresh_pool()
        self.global_form.set_state(self.model)
        self.timeline.rebuild()
        self.seg_editor.bind_to(None,
                                 self.model.display_mode, self.model.frame_rate)
        self.video_status_bar.set_idle()

    def _refresh_pool(self):
        self.image_pool.set_paths(self.model.pool)
        self.image_pool.refresh_usage(self.model.pool_usage())

    # ---------- slots: toolbar ----------

    def _on_import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "批量导入图片",
            str(self.state.current_dir or Path.home()),
            "图片 (*.png *.jpg *.jpeg *.webp)")
        if not paths:
            return
        added = self.model.add_to_pool([Path(p) for p in paths])
        self._refresh_pool()
        self.statusMessage.emit(f"图片池新增 {added} 张")

    def _on_import_current_dir(self):
        if not self.state.current_dir:
            QMessageBox.information(self, "无当前目录",
                                     "先用「文件 → 打开目录」选一个目录")
            return
        paths = [p for p in sorted(self.state.current_dir.iterdir())
                 if p.suffix.lower() in IMG_EXTS]
        added = self.model.add_to_pool(paths)
        self._refresh_pool()
        self.statusMessage.emit(f"从当前目录加入 {added} 张")

    def _on_clear_pool(self):
        if QMessageBox.question(
                self, "清空池", "确定清空图片池？时间轴上的段不受影响。",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.model.clear_pool()
        self._refresh_pool()

    def _on_add_text(self):
        self.model.add_text_segment(length_frames=12, local_prompt="")
        self.timeline.rebuild()

    def _on_add_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频", str(self.state.current_dir or Path.home()),
            "音频 (*.mp3 *.wav *.flac)")
        if not path:
            return
        self.model.add_audio(Path(path), start_frame=0, length_frames=24)
        self.timeline.rebuild()

    # ---------- slots: image pool ----------

    def _on_pool_images_added(self, paths: list[Path]):
        added = self.model.add_to_pool(paths)
        self._refresh_pool()
        self.statusMessage.emit(f"图片池新增 {added} 张")

    # ---------- slots: timeline ----------

    def _on_image_dropped_at(self, path, insert_idx: int):
        path = Path(path)
        if path not in self.model.pool:
            self.model.add_to_pool([path])
        seg_id = self.model.add_image_segment(path, length_frames=24)
        # 新段被 append 到末尾，需要移到 insert_idx
        if insert_idx < len(self.model.segments) - 1:
            seg = self.model.segments.pop()
            self.model.segments.insert(insert_idx, seg)
        self.timeline.rebuild()
        self._refresh_pool()

    def _on_segment_selected(self, seg_id: str):
        seg = next((s for s in self.model.segments if s.seg_id == seg_id), None)
        self.seg_editor.bind_to(seg,
                                  self.model.display_mode, self.model.frame_rate)

    def _on_segment_resized(self, seg_id: str, new_length: int):
        self.model.update_segment(seg_id, length_frames=new_length)
        self.timeline.rebuild()
        # 重新绑定编辑器（length 文案也要刷）
        seg = next((s for s in self.model.segments if s.seg_id == seg_id), None)
        self.seg_editor.bind_to(seg,
                                  self.model.display_mode, self.model.frame_rate)

    def _on_segments_reordered(self, ordered_ids: list):
        self.model.reorder_segments(ordered_ids)
        self.timeline.rebuild()

    def _on_segment_delete(self, seg_id: str):
        self.model.remove_segment(seg_id)
        self.timeline.rebuild()
        self.seg_editor.bind_to(None,
                                  self.model.display_mode, self.model.frame_rate)
        self._refresh_pool()

    def _on_audio_changed(self, audio_id: str, start: int, length: int):
        self.model.update_audio(
            audio_id, start_frame=start, length_frames=length)
        self.timeline.rebuild()

    def _on_audio_delete(self, audio_id: str):
        self.model.remove_audio(audio_id)
        self.timeline.rebuild()

    # ---------- slots: editor & global ----------

    def _on_segment_edited(self, seg_id: str, field: str, value):
        self.model.update_segment(seg_id, **{field: value})
        self.timeline.rebuild()

    def _on_global_changed(self):
        st = self.global_form.get_state()
        for key, val in st.items():
            setattr(self.model, key, val)
        # display_mode / frame_rate 影响 timeline + seg_editor
        cur_seg_id = self.timeline.currently_selected_seg_id()
        cur = next((s for s in self.model.segments
                    if s.seg_id == cur_seg_id), None)
        self.seg_editor.bind_to(cur,
                                  self.model.display_mode, self.model.frame_rate)
        self.timeline.rebuild()

    # ---------- slots: status bar / 提交链路 ----------

    def _on_submit(self):
        ok, msg = self.model.validate()
        if not ok:
            QMessageBox.warning(self, "校验失败", msg)
            return
        try:
            api_key = resolve_api_key(self.cfg)
            template_path = resolve_template_path(self.cfg)
            out_dir = resolve_video_output_dir(self.cfg, self.state.output_dir)
        except (RunningHubUnavailable, RunningHubInvalidSpec) as e:
            QMessageBox.warning(
                self, "配置缺失",
                f"{e}\n\n请在「设置 → RunningHub…」补充。")
            return

        spec = self.model.to_ltx_spec(out_dir)
        self._cancel_flag["v"] = False

        cancel_flag = self._cancel_flag
        cfg = self.cfg

        def task():
            with RunningHubClient(api_key,
                                    base_url=cfg.runninghub_base_url) as client:
                builder = LTXTaskBuilder(template_path)
                handle = submit_ltx_task(
                    client, spec, builder,
                    mode=cfg.runninghub_submit_mode,
                    workflow_id=cfg.runninghub_workflow_id,
                    upload_progress_cb=lambda d, t, p: self._post(
                        "upload", (d, t, p.name)),
                )
                return handle.wait_for_result(
                    timeout=1800, poll_interval=8,
                    progress_cb=lambda s: self._post("status", s),
                    cancel_check=lambda: cancel_flag["v"],
                )

        self.video_status_bar.set_status("提交中…")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_submit_done)
        self._worker.failed.connect(self._on_submit_failed)
        self._worker.start()

    def _post(self, kind: str, payload):
        """worker 线程 → UI 线程的回调转发。"""
        QTimer.singleShot(0, lambda: self._apply_status(kind, payload))

    def _apply_status(self, kind: str, payload):
        if kind == "upload":
            d, t, name = payload
            self.video_status_bar.set_uploading(d, t, name)
        elif kind == "status":
            self.video_status_bar.set_status(payload)

    def _on_submit_done(self, mp4_path):
        self.video_status_bar.set_done(Path(mp4_path))
        self.statusMessage.emit(f"视频已保存：{mp4_path}")

    def _on_submit_failed(self, err_msg: str):
        self.video_status_bar.set_failed(err_msg)

    def _on_cancel(self):
        self._cancel_flag["v"] = True
        self.video_status_bar.set_status("取消中…")

    def _on_open_folder(self, folder):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---------- 缓存 ----------

    def save_cache(self):
        """MainWindow.closeEvent 调用。"""
        try:
            self.cfg.update_settings(
                video_timeline_cache=self.model.to_dict())
        except Exception as e:
            log.warning("video_timeline_cache 保存失败：%s", e)

    def _restore_model(self) -> TimelineModel:
        data = getattr(self.cfg, "video_timeline_cache", None) or {}
        if data:
            try:
                return TimelineModel.from_dict(data)
            except Exception as e:
                log.warning("video_timeline_cache 解析失败，走空 model：%s", e)
        return TimelineModel()
```

- [ ] **Step 2: 语法 + 导入**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
python -m py_compile app/ui/panels/video_panel.py && echo "parsed OK"
/root/miniconda3/envs/UniRig/bin/python -c "
from app.ui.panels.video_panel import VideoPanel
print('imports OK')
"
```

Expected: `parsed OK` + `imports OK`

- [ ] **Step 3: 全量回归**

```bash
pytest 2>&1 | tail -3
```

Expected: 无 regression

- [ ] **Step 4: Commit**

```bash
git add app/ui/panels/video_panel.py
git commit -m "feat(video-panel): VideoPanel assembly with submit chain"
```

---

## Task 14: MainWindow 集成 + 手工冒烟

**Files:**
- Modify: `app/ui/main_window.py`

- [ ] **Step 1: 加 import**

打开 `app/ui/main_window.py`。在 import 区追加：

```python
from app.ui.panels.video_panel import VideoPanel
from app.ui.dialogs.runninghub_settings_dialog import RunningHubSettingsDialog
```

- [ ] **Step 2: FUNCS 加第 5 项**

找到 `FUNCS = [("反推", "inference"), ...]` 这一行。改成：

```python
FUNCS = [("反推", "inference"), ("拆图", "split"),
         ("拼图", "combine"), ("去白边", "trim"),
         ("视频生成", "video_gen")]
```

- [ ] **Step 3: panels 列表加 VideoPanel**

找到 `self.panels = [...]`，把列表末尾改成：

```python
        self.panels = [
            InferencePanel(self.state, self.cfg),
            SplitPanel(self.state, self.cfg),
            CombinePanel(self.state, self.cfg),
            TrimPanel(self.state, self.cfg),
            VideoPanel(self.state, self.cfg),
        ]
```

- [ ] **Step 4: 加菜单栏「设置 → RunningHub…」**

找到 `_build_ui` 方法里现有的 `fm = menu.addMenu("文件")` 块（含 a_open / a_out / a_quit）。在 `fm.addAction(a_quit)` 之后追加：

```python
        sm = menu.addMenu("设置")
        a_rh = QAction("RunningHub 配置…", self)
        a_rh.triggered.connect(self._open_runninghub_settings)
        sm.addAction(a_rh)
```

- [ ] **Step 5: 加 _open_runninghub_settings 方法**

在类内任意空白处（建议放 `_set_out_dir` 方法之后）追加：

```python
    def _open_runninghub_settings(self):
        RunningHubSettingsDialog(self.cfg, parent=self).exec()
```

- [ ] **Step 6: 改 _on_func_changed 处理 video_gen**

找到 `_on_func_changed` 方法。替换整个方法：

```python
    def _on_func_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.state.active_function = FUNCS[idx][1]
        panel = self.panels[idx]
        self.thumb.set_mode(panel.select_mode())
        is_video = (FUNCS[idx][1] == "video_gen")
        # 视频生成时：隐藏中栏 thumb + 隐藏底部 preview/execute 控制
        self.thumb.setVisible(not is_video)
        self.btn_preview.setVisible(not is_video and (
            panel.has_preview() or FUNCS[idx][1] == "split"))
        self.btn_exec.setVisible(not is_video)
        self.exec_hint.setVisible(not is_video)
        # 视频生成模式下让右栏拓宽（取消 maxWidth）
        right_widget = self.btn_exec.parentWidget()
        if right_widget:
            if is_video:
                right_widget.setMaximumWidth(16777215)
                right_widget.setMinimumWidth(800)
            else:
                right_widget.setMaximumWidth(420)
                right_widget.setMinimumWidth(340)
        self._refresh_validity()
```

- [ ] **Step 7: closeEvent 保存 VideoPanel 缓存**

如果 `MainWindow` 已有 `closeEvent`，在它的 `super().closeEvent(e)` 之前追加保存逻辑；如果没有该方法，新增：

```python
    def closeEvent(self, e):
        for w in self.panels:
            if isinstance(w, VideoPanel):
                w.save_cache()
                break
        super().closeEvent(e)
```

放在类末尾（在所有现有方法之后）。

- [ ] **Step 8: 语法 + 导入 + 启动应用冒烟（你自己跑）**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
python -m py_compile app/ui/main_window.py && echo "parsed OK"
/root/miniconda3/envs/UniRig/bin/python -c "
from app.ui.main_window import MainWindow
print('imports OK')
"
```

Expected: `parsed OK` + `imports OK`

```bash
# 启动应用：
python -m app.main
# 切到「视频生成」→ 看到 5 层布局 → 不报 traceback
```

- [ ] **Step 9: 全量回归**

```bash
pytest 2>&1 | tail -3
```

Expected: 全部通过，无 regression。预期总数 ≈ 252（209 prior + 39 model + 4 config）。

- [ ] **Step 10: Commit**

```bash
git add app/ui/main_window.py
git commit -m "feat(video-panel): MainWindow integration with FUNCS + settings menu + cache"
```

- [ ] **Step 11: 12 项手工冒烟（**必须由你执行**）**

启动 `python -m app.main` 后按顺序跑下面 12 项，全过才算 B 完成：

1. **默认布局**：启动 → 切「视频生成」→ 中栏 thumb 隐藏，VideoPanel 占满；时间轴显示「拖一张图到这里开始」
2. **批量导入**：点「+ 批量导入图片」选 5 张 → 图片池横排显示，未用状态（灰）
3. **拖图入轨**：从池拖一张图到时间轴 → 出现 1 个段（默认 24 帧），图片池中该图变白（已用）
4. **选段编辑**：拖 3 张图 → 单击第 2 段 → seg_editor 启用，显示该段 prompt/length/guide
5. **拖右沿改长度**：拖第 3 段右沿到加倍宽度 → 实时变宽；松手后 length_frames 翻倍，badge 更新
6. **滚轮缩放**：Ctrl+滚轮 → 时间轴等比缩放，所有段+badge 同步；纯滚轮横向滚动
7. **Add Text**：「+ Add Text」按钮 → 末尾出现红灰文本段，可拖动改长度
8. **Add Audio**：「+ Add Audio」选 mp3 → 音频轨出现绿灰段；拖右沿改长度
9. **设置对话框**：菜单「设置 → RunningHub…」→ 填 API Key → 点「测试连接」→ 显示「✓ 鉴权通过」→ 保存关闭
10. **完整提交**：「🎬 提交」→ 状态栏依次显示「上传 N/M」→「提交中…」→「QUEUED」→「RUNNING」→「✓ 完成：path」→ 点链接打开 explorer 看到 mp4
11. **缓存恢复**：关闭程序 → 重启 → 切「视频生成」→ 段/池/参数全部恢复
12. **取消**：重新提交一次，「QUEUED」/「RUNNING」期间点「取消」→ 状态变「取消中…」→ 几秒后「✗ 失败：cancelled by user」

冒烟过完，把 task_id + mp4 路径 + 总耗时报回。

---

## Self-Review

完成 Tasks 1–14 后做最终 review：

- [ ] `pytest -v` 全部通过（预期 ~252，含 39 个新 model 测试 + 4 个 config 测试）
- [ ] 设计 spec §2 所有 12 条决策都有对应 task 实现
- [ ] 设计 spec §11 验收 7 条全部满足
- [ ] `git log --oneline main..feat/video-panel` 看到 ≥14 commits
- [ ] 12 项手工冒烟全过
- [ ] `app/core/video_timeline_model.py` 零 Qt 依赖（grep 一下确认）
- [ ] 所有 widget 都能独立 import 不报错
- [ ] 切回非视频 panel 时 thumb 中栏正常显示，video 模式 layout 正确切回
