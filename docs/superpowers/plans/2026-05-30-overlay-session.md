# 动态多轨叠加片段数据模型 实施计划 — 子项目 #3a

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 建 OverlaySession 数据模型——动态多子轨叠加片段 + 自动分轨 + overlay.json 持久化（纯逻辑，3b/3c/3d 的地基）。

**Architecture:** 独立 `sound_track_agent/overlay_session.py`，与现有 session 解耦。OverlaySegment(片段) + OverlaySession(add 自动分轨/remove/查询/持久化)。无 Qt。

**Tech Stack:** Python dataclass / json / pytest

**Spec:** `docs/superpowers/specs/2026-05-30-overlay-session-design.md`

**Branch:** main

---

## Task 1: OverlaySession 全部实现

**Files:**
- Create: `sound_track_agent/overlay_session.py`
- Test: `tests/test_sound_track_agent/test_overlay_session.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_sound_track_agent/test_overlay_session.py`：

```python
"""OverlaySession：叠加片段 + 自动分轨 + overlay.json 持久化。"""
from sound_track_agent.overlay_session import (
    OverlaySegment, OverlaySession, load_overlay, save_overlay)


def test_segment_roundtrip():
    s = OverlaySegment(id="x1", kind="bgm", lane=0, t_start=1.0, t_end=5.0,
                       prompt="史诗", audio_path="/a.mp3", volume=0.8, enabled=False)
    s2 = OverlaySegment.from_dict(s.to_dict())
    assert s2 == s


def test_segment_defaults():
    s = OverlaySegment(id="x", kind="sfx", lane=0, t_start=0.0, t_end=2.0, prompt="门")
    assert s.audio_path == "" and s.volume == 1.0 and s.enabled is True


def test_add_first_segment_lane0():
    sess = OverlaySession()
    seg = sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    assert seg.lane == 0 and seg.kind == "bgm"
    assert len(sess.segments) == 1


def test_add_non_overlapping_same_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    seg2 = sess.add("bgm", 5.0, 9.0, "b", seg_id="s2")   # 边界相接，不重叠
    assert seg2.lane == 0


def test_add_overlapping_new_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    seg2 = sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")   # 重叠
    assert seg2.lane == 1


def test_add_third_fills_lowest_free_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")          # lane0
    sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")          # lane1
    seg3 = sess.add("bgm", 6.0, 9.0, "c", seg_id="s3")   # 与lane0(0-5)不重叠 → lane0
    assert seg3.lane == 0


def test_bgm_sfx_independent_lanes():
    sess = OverlaySession()
    b = sess.add("bgm", 0.0, 5.0, "a", seg_id="b1")
    s = sess.add("sfx", 0.0, 5.0, "x", seg_id="s1")
    assert b.lane == 0 and s.lane == 0                   # 各自独立从 0


def test_lanes_for():
    sess = OverlaySession()
    assert sess.lanes_for("bgm") == 0
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")
    assert sess.lanes_for("bgm") == 2
    assert sess.lanes_for("sfx") == 0


def test_segments_in_lane():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    sess.add("bgm", 6.0, 9.0, "c", seg_id="s3")          # 同 lane0
    sess.add("bgm", 3.0, 8.0, "b", seg_id="s2")          # lane1
    lane0 = sess.segments_in_lane("bgm", 0)
    assert {s.id for s in lane0} == {"s1", "s3"}


def test_remove_and_get():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    assert sess.get("s1") is not None
    assert sess.remove("s1") is True
    assert sess.get("s1") is None
    assert sess.remove("nope") is False


def test_session_roundtrip():
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    sess.add("sfx", 1.0, 2.0, "x", seg_id="s2")
    sess2 = OverlaySession.from_dict(sess.to_dict())
    assert len(sess2.segments) == 2
    assert sess2.get("s1").prompt == "a"


def test_save_load_roundtrip(tmp_path):
    sess = OverlaySession()
    sess.add("bgm", 0.0, 5.0, "a", seg_id="s1")
    save_overlay(tmp_path, sess)
    sess2 = load_overlay(tmp_path)
    assert sess2.get("s1").t_end == 5.0


def test_load_missing_returns_empty(tmp_path):
    assert load_overlay(tmp_path).segments == []


def test_load_corrupt_returns_empty(tmp_path):
    (tmp_path / "overlay.json").write_text("{bad", encoding="utf-8")
    assert load_overlay(tmp_path).segments == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_overlay_session.py -q`
Expected: FAIL — `ModuleNotFoundError: ... overlay_session`

- [ ] **Step 3: 实现** — 新建 `sound_track_agent/overlay_session.py`：

```python
"""动态多子轨叠加片段模型：框选生成的 BGM/SFX 片段，与固定轨整段配乐并存。

独立 overlay.json，纯逻辑无 Qt。自动分轨：新片段放入同 kind 内第一条无时间
重叠的 lane，否则新建 lane。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class OverlaySegment:
    id: str
    kind: str                # "bgm" | "sfx"
    lane: int
    t_start: float
    t_end: float
    prompt: str
    audio_path: str = ""
    volume: float = 1.0
    enabled: bool = True

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "lane": self.lane,
                "t_start": self.t_start, "t_end": self.t_end,
                "prompt": self.prompt, "audio_path": self.audio_path,
                "volume": self.volume, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "OverlaySegment":
        return cls(
            id=d["id"], kind=d["kind"], lane=int(d["lane"]),
            t_start=float(d["t_start"]), t_end=float(d["t_end"]),
            prompt=d.get("prompt", ""), audio_path=d.get("audio_path", ""),
            volume=float(d.get("volume", 1.0)),
            enabled=bool(d.get("enabled", True)))


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1


class OverlaySession:
    def __init__(self, segments: Optional[list] = None):
        self.segments: list[OverlaySegment] = list(segments or [])

    def _assign_lane(self, kind: str, t_start: float, t_end: float) -> int:
        same = [s for s in self.segments if s.kind == kind]
        max_lane = max((s.lane for s in same), default=-1)
        for lane in range(max_lane + 1):
            clash = any(_overlaps(t_start, t_end, s.t_start, s.t_end)
                        for s in same if s.lane == lane)
            if not clash:
                return lane
        return max_lane + 1

    def add(self, kind: str, t_start: float, t_end: float, prompt: str,
            *, seg_id: str) -> OverlaySegment:
        lane = self._assign_lane(kind, t_start, t_end)
        seg = OverlaySegment(id=seg_id, kind=kind, lane=lane,
                             t_start=float(t_start), t_end=float(t_end),
                             prompt=prompt)
        self.segments.append(seg)
        return seg

    def remove(self, seg_id: str) -> bool:
        for i, s in enumerate(self.segments):
            if s.id == seg_id:
                del self.segments[i]
                return True
        return False

    def get(self, seg_id: str) -> Optional[OverlaySegment]:
        return next((s for s in self.segments if s.id == seg_id), None)

    def lanes_for(self, kind: str) -> int:
        lanes = [s.lane for s in self.segments if s.kind == kind]
        return (max(lanes) + 1) if lanes else 0

    def segments_in_lane(self, kind: str, lane: int) -> list:
        return [s for s in self.segments if s.kind == kind and s.lane == lane]

    def to_dict(self) -> dict:
        return {"segments": [s.to_dict() for s in self.segments]}

    @classmethod
    def from_dict(cls, d: dict) -> "OverlaySession":
        return cls([OverlaySegment.from_dict(s)
                    for s in (d or {}).get("segments", [])])


def _overlay_path(work_dir) -> Path:
    return Path(work_dir) / "overlay.json"


def load_overlay(work_dir) -> OverlaySession:
    p = _overlay_path(work_dir)
    if not p.is_file():
        return OverlaySession()
    try:
        return OverlaySession.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return OverlaySession()


def save_overlay(work_dir, session: OverlaySession) -> None:
    p = _overlay_path(work_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
                 encoding="utf-8")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_overlay_session.py -q`
Expected: PASS（14 passed）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/overlay_session.py tests/test_sound_track_agent/test_overlay_session.py
git commit -m "feat(soundtrack): + OverlaySession 动态多子轨叠加片段模型（自动分轨+持久化）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec 覆盖**：OverlaySegment/OverlaySession/add 自动分轨/remove/get/lanes_for/segments_in_lane/持久化 → 全在 Task 1。✓
- **类型一致**：`add(kind,t_start,t_end,prompt,*,seg_id)` 签名与测试一致；`_overlaps` 边界相接（t_end==t_start）返回 False（`a0<b1 and b0<a1`，5.0<9.0 and 5.0<5.0→False）→ 同 lane 测试正确。✓
- **无占位符**：完整代码。✓
- 单 task（范围小、纯逻辑），无需拆分。
```
