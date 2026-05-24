# 时间轴刻度（Timeline Ruler）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `TimelineWidget` 顶部加一条自适应缩放的时间刻度尺，标签跟随 `display_mode`（frames / seconds）。仅视觉参考，不吸附。

**Architecture:** 在 `timeline_widget.py` 增加纯函数 `_pick_tick_interval()`（可单测）+ 在 `TimelineScene` 上重载 `drawBackground()`。把 `SEG_LANE_Y` 从 `0` 改到 `RULER_HEIGHT(=20)`，`AUDIO_LANE_Y` 跟随下移。

**Tech Stack:** Python stdlib + PySide6（QGraphicsScene、QPainter、QFont、QColor、QPen、QPointF、QRectF）；pytest 单测纯函数。

**Spec:** [docs/superpowers/specs/2026-05-24-timeline-ruler-design.md](../specs/2026-05-24-timeline-ruler-design.md)

---

## File Structure

修改文件（只动一个）：
- `drama_shot_master/ui/widgets/timeline_widget.py`
  - 新增模块级常量 `RULER_HEIGHT`、`TARGET_MAJOR_PX`、`MINOR_RATIO`、`SECONDS_CANDIDATES`、`FRAMES_CANDIDATES`
  - 新增纯函数 `_pick_tick_interval(ppf, frame_rate, display_mode) -> (major_frames, minor_frames)`
  - `SEG_LANE_Y` 从 `0` 改到 `RULER_HEIGHT`；`AUDIO_LANE_Y` 表达式跟着变
  - `TimelineScene` 增加 `drawBackground()` 重载
  - `TimelineScene.rebuild()` 中空场景提示的 `hint.setPos()` y 改成 `SEG_LANE_Y + SEG_HEIGHT/2 - 10`

新增文件：
- `tests/test_core/test_tick_picker.py` — 单测 `_pick_tick_interval`

---

## Task 1: 纯函数 `_pick_tick_interval`（TDD）

**Files:**
- Modify: `drama_shot_master/ui/widgets/timeline_widget.py`（新增常量 + 函数）
- Create: `tests/test_core/test_tick_picker.py`

- [ ] **Step 1.1: 写失败测试**

Create `tests/test_core/test_tick_picker.py`:

```python
"""Tests for _pick_tick_interval in timeline_widget."""
from __future__ import annotations

from drama_shot_master.ui.widgets.timeline_widget import _pick_tick_interval


def test_zoom_in_seconds_returns_half_second_major():
    # ppf=20, fr=24 → 0.5s=12f, 12*20=240px >= 80 → (12, 12//5=2)
    assert _pick_tick_interval(20.0, 24, "seconds") == (12, 2)


def test_mid_zoom_seconds_returns_1s_major():
    # ppf=5, fr=24 → 0.5s=12f, 12*5=60 < 80; 1s=24f, 24*5=120 >= 80 → (24, 4)
    assert _pick_tick_interval(5.0, 24, "seconds") == (24, 4)


def test_zoom_out_seconds_returns_10s_major():
    # ppf=0.5, fr=24 → 0.5/1/2/5s 全 <80px; 10s=240f, 240*0.5=120 >= 80
    assert _pick_tick_interval(0.5, 24, "seconds") == (240, 48)


def test_zoom_in_frames_returns_5f_major():
    # ppf=20, fr=24 → 1f=20<80; 5f=100>=80 → (5, 1)
    assert _pick_tick_interval(20.0, 24, "frames") == (5, 1)


def test_zoom_out_frames_returns_300f_major():
    # ppf=0.5, fr=24 → 1..120f 全 <80; 300f=150 >= 80 → (300, 60)
    assert _pick_tick_interval(0.5, 24, "frames") == (300, 60)


def test_max_zoom_frames_returns_5f_major():
    # ppf=50, fr=24 → 1f=50<80; 5f=250>=80 → (5, 1)
    assert _pick_tick_interval(50.0, 24, "frames") == (5, 1)


def test_zero_frame_rate_does_not_crash_seconds():
    # 内部 max(frame_rate, 1) 兜底 → 等价 fr=1
    # ppf=5, fr=0, mode=seconds: 0.5s=1f(round), 1*5=5<80; 1s=1f, 1*5=5<80; ...
    # 30s=30f, 30*5=150>=80 → (30, 6)
    assert _pick_tick_interval(5.0, 0, "seconds") == (30, 6)


def test_minor_at_least_1():
    # 任何返回，minor 都 >= 1（避免 zero-step 循环）
    cases = [
        (50.0, 24, "frames"),     # 5f major → minor = max(1, 1) = 1
        (50.0, 24, "seconds"),    # 0.5s=12f, 12*50=600 → major=12, minor=12//5=2
        (0.5, 1, "frames"),       # 1f=0.5<80 ... 300f=150 → major=300, minor=60
    ]
    for ppf, fr, mode in cases:
        major, minor = _pick_tick_interval(ppf, fr, mode)
        assert major >= 1
        assert minor >= 1
        assert minor <= major
```

- [ ] **Step 1.2: 运行测试，确认全部失败**

Run: `pytest tests/test_core/test_tick_picker.py -v`
Expected: `ImportError: cannot import name '_pick_tick_interval'` 或类似（函数不存在）。

- [ ] **Step 1.3: 实现常量 + 函数**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 找到布局常量区（line 23-33）：

```python
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
```

替换为：

```python
# ---------- 布局常量 ----------

RULER_HEIGHT = 20
SEG_LANE_Y = RULER_HEIGHT
SEG_HEIGHT = 60
LANE_GAP = 10
AUDIO_LANE_Y = SEG_LANE_Y + SEG_HEIGHT + LANE_GAP   # 20 + 60 + 10 = 90
AUDIO_HEIGHT = 30
RESIZE_HANDLE_W = 6
DEFAULT_PX_PER_FRAME = 5.0
MIN_PX_PER_FRAME = 0.5
MAX_PX_PER_FRAME = 50.0

# ---------- 刻度尺常量 ----------

TARGET_MAJOR_PX = 80              # 相邻 major tick 目标间距（像素）
MINOR_RATIO = 5                   # minor = max(1, major // 5)
SECONDS_CANDIDATES = [0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]  # 秒
FRAMES_CANDIDATES = [1, 5, 10, 30, 60, 120, 300, 600]            # 帧
```

紧接其后（在 `# MIME types` 之前）加入函数：

```python
def _pick_tick_interval(ppf: float, frame_rate: int, display_mode: str
                        ) -> tuple[int, int]:
    """选 (major_frames, minor_frames) 使相邻 major tick 间距 >= TARGET_MAJOR_PX。

    遍历候选间隔（升序），返回首个满足像素阈值的；都不满足则取最大候选。
    minor_frames = max(1, major_frames // MINOR_RATIO)。
    """
    fr = max(frame_rate, 1)
    if display_mode == "seconds":
        for sec in SECONDS_CANDIDATES:
            major_frames = max(1, int(round(sec * fr)))
            if major_frames * ppf >= TARGET_MAJOR_PX:
                return (major_frames, max(1, major_frames // MINOR_RATIO))
        last = max(1, int(round(SECONDS_CANDIDATES[-1] * fr)))
        return (last, max(1, last // MINOR_RATIO))
    # frames
    for f in FRAMES_CANDIDATES:
        if f * ppf >= TARGET_MAJOR_PX:
            return (f, max(1, f // MINOR_RATIO))
    last = FRAMES_CANDIDATES[-1]
    return (last, max(1, last // MINOR_RATIO))
```

- [ ] **Step 1.4: 运行测试，确认全部通过**

Run: `pytest tests/test_core/test_tick_picker.py -v`
Expected: 8/8 PASS。

- [ ] **Step 1.5: 全量回归**

Run: `pytest -q`
Expected: 281 + 8 = 289 PASS（无回归）。

- [ ] **Step 1.6: 提交**

```bash
git add drama_shot_master/ui/widgets/timeline_widget.py tests/test_core/test_tick_picker.py
git commit -m "feat(timeline): add _pick_tick_interval + ruler constants

Pure function selects major/minor tick interval so adjacent major ticks
sit ~80px apart. RULER_HEIGHT/SEG_LANE_Y/AUDIO_LANE_Y constants updated;
no behavior change yet — drawBackground override comes in next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: drawBackground 实现刻度尺

**Files:**
- Modify: `drama_shot_master/ui/widgets/timeline_widget.py` — `TimelineScene` 类内

- [ ] **Step 2.1: 在 TimelineScene 内新增 drawBackground 方法**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `TimelineScene` 类的方法顺序大致是 `__init__` → `rebuild` → `dragEnterEvent` → `dragMoveEvent` → `dropEvent` → `_find_seg_insert_index`。

在 `rebuild` 方法之后、`dragEnterEvent` 之前插入一个新方法：

```python
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        scene_w = self.sceneRect().width()
        # 1. 背景带
        band = QRectF(0, 0, scene_w, RULER_HEIGHT)
        painter.fillRect(band, QColor("#262a30"))
        # 2. 选刻度间隔
        major, minor = _pick_tick_interval(
            self.pixels_per_frame,
            self.model.frame_rate,
            self.model.display_mode,
        )
        ppf = self.pixels_per_frame
        if ppf <= 0:
            return
        # 3. 可见 x 范围（rect 是脏区域；裁掉负数和超出 sceneRect）
        x_start = max(0.0, rect.left())
        x_end = min(scene_w, rect.right())
        # 4. minor ticks
        painter.setPen(QPen(QColor("#3a3f48"), 1))
        frame = (int(x_start / ppf) // minor) * minor
        while frame * ppf <= x_end:
            if frame % major != 0:
                x = frame * ppf
                painter.drawLine(QPointF(x, RULER_HEIGHT - 6),
                                 QPointF(x, RULER_HEIGHT))
            frame += minor
        # 5. major ticks + 标签
        painter.setPen(QPen(QColor("#888"), 1))
        f = QFont(); f.setPointSize(7); painter.setFont(f)
        fr = max(self.model.frame_rate, 1)
        frame = (int(x_start / ppf) // major) * major
        while frame * ppf <= x_end:
            x = frame * ppf
            painter.drawLine(QPointF(x, RULER_HEIGHT - 12),
                             QPointF(x, RULER_HEIGHT))
            if self.model.display_mode == "frames":
                label = f"{frame}f"
            else:
                sec = frame / fr
                label = (f"{int(sec)}s" if sec == int(sec)
                         else f"{sec:.1f}s")
            painter.drawText(QPointF(x + 2, RULER_HEIGHT - 14), label)
            frame += major
```

- [ ] **Step 2.2: 更新空场景提示的 y 坐标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 找到 `TimelineScene.rebuild()` 末尾这两行：

```python
            hint = QGraphicsTextItem("拖一张图到这里开始")
            hint.setDefaultTextColor(QColor("#666"))
            hint.setPos(20, SEG_HEIGHT / 2 - 10)
            self.addItem(hint)
```

把 `hint.setPos` 那行改为：

```python
            hint.setPos(20, SEG_LANE_Y + SEG_HEIGHT / 2 - 10)
```

- [ ] **Step 2.3: 烟测 — 模块可导入**

Run:
```bash
python -c "from drama_shot_master.ui.widgets.timeline_widget import TimelineWidget, TimelineScene, _pick_tick_interval; print('ok')"
```
Expected: 输出 `ok`，无异常。

- [ ] **Step 2.4: 全量回归**

Run: `pytest -q`
Expected: 289 PASS（与 Task 1 后基线一致）。

- [ ] **Step 2.5: 提交**

```bash
git add drama_shot_master/ui/widgets/timeline_widget.py
git commit -m "feat(timeline): render auto-scaling ruler in scene background

drawBackground paints a 20px band at the top of TimelineScene with
adaptive minor/major ticks and labels following display_mode. Empty-scene
hint shifted down to SEG_LANE_Y + SEG_HEIGHT/2 - 10.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 手测清单（end-of-feature）

**Files:** 无代码变更。

- [ ] **Step 3.1: 列出手测清单（给用户）**

把以下用例发回给协调者，由用户手动执行（参见 spec §6.2）：

1. 启动应用打开视频面板。
2. 默认视图（ppf=5）：能看到顶部 20px 灰色刻度带，应该是 1s major（每 120px 一根高刻度 + 标签 "1s/2s/3s"）+ 0.2s minor（每 24px 一根矮刻度，无标签）。
3. Ctrl+滚轮放大若干次（ppf 增加）：major 间隔逐渐变细 → 0.5s → 5f → 1f（注意 5f 是 ppf=50 的极限）。
4. Ctrl+滚轮缩小若干次（ppf 减小）：major 间隔逐渐变粗 → 2s/5s/10s/30s。
5. 视频面板切换"时间显示"为"帧"：刻度标签立即变为 `"15f / 30f / 45f"` 这样的格式。
6. 切回"秒"：标签变回 `"1s / 1.5s / 2s"`。
7. 拖一张图到时间轴：段卡左上角应与某个刻度大致重合（视觉对齐，不是严格 snap）。
8. 空场景"拖一张图到这里开始"提示出现在刻度带下方，不与刻度重叠。
9. 横向滚动时刻度跟随场景移动，与下方段保持坐标对齐。

报告应说明：所有测试通过的话报 DONE；任一项异常报 DONE_WITH_CONCERNS + 具体哪一步出问题。

---

## Self-Review 记录

- **Spec coverage:**
  - §3.1 影响面所有 7 行改动 → Task 1（常量、新函数、SEG_LANE_Y、AUDIO_LANE_Y）+ Task 2（drawBackground、setSceneRect 因 AUDIO_LANE_Y 增大自动包含 ruler、空场景提示 y 调整）
  - §4.1 算法 → Task 1.3
  - §4.2 drawBackground 渲染 → Task 2.1
  - §4.3 布局常量调整 → Task 1.3
  - §4.4 sceneRect 高度 → 无显式 Task（spec 说"表达式不变，自然吃到 ruler 高度"，已在 §3.1 表中说明，验证由 Task 3 手测覆盖）
  - §4.5 空场景提示 y → Task 2.2
  - §5 数据流 → Task 2 实现
  - §6.1 单测 → Task 1.1（8 个测试用例，含 spec 7 项 + minor_at_least_1）
  - §6.2 手测 → Task 3.1
  - §7 依赖 → 无新增；唯一文件 timeline_widget.py
  - §8 YAGNI → 自动满足（计划里没有任何 snap / playhead / tooltip / 点击交互）

- **Placeholder scan:** 无 TBD / TODO / "similar to" / 抽象的 "handle X" 占位。每个代码 step 都给出完整代码块或精确的 Edit 指令。

- **Type consistency:**
  - `_pick_tick_interval(ppf: float, frame_rate: int, display_mode: str) -> tuple[int, int]` 签名在 Task 1 定义、Task 2 使用一致。
  - 常量名 `RULER_HEIGHT / TARGET_MAJOR_PX / MINOR_RATIO / SECONDS_CANDIDATES / FRAMES_CANDIDATES` 在两个 Task 内引用名一致。
  - `display_mode` 字符串值 `"seconds"` / `"frames"` 与现有 `video_global_form.py` / `segment_editor.py` 一致。
