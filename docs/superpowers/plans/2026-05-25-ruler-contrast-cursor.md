# 刻度尺配色修复 + 红色拖拽游标 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重配刻度尺颜色建立清晰明暗层级，并在拖拽/拉伸时显示一条跟随鼠标的红色游标线（带帧/秒标签），松开消失。

**Architecture:** 全部在 `timeline_widget.py`。颜色抽成模块级常量并替换进 `drawBackground`；新增纯函数 `_format_cursor_label`（可单测）；`TimelineScene` 增加 `_cursor_x` 状态 + `set_cursor_x()` + `drawForeground()`；`SegmentItem`/`AudioItem` 拖拽时调用 scene 设/清游标，`TimelineScene` 的 QDrag 事件也设/清游标。

**Tech Stack:** PySide6（QGraphicsScene drawForeground、QPainter、QPen、QColor、QFont、QFontMetrics、QPointF、QRectF）；pytest 单测纯函数。

**Spec:** [docs/superpowers/specs/2026-05-25-ruler-contrast-cursor-design.md](../specs/2026-05-25-ruler-contrast-cursor-design.md)

---

## File Structure

只改一个文件 + 一个新测试：
- Modify: `drama_shot_master/ui/widgets/timeline_widget.py`
  - 新增 7 个颜色常量 + 纯函数 `_format_cursor_label`
  - 改 `drawBackground` 用新常量（含 major tick / label 拆分用色）
  - `TimelineScene`：`_cursor_x` 字段、`set_cursor_x()`、`drawForeground()`、`dragMoveEvent`/`dropEvent`/`dragLeaveEvent` 设/清游标
  - `SegmentItem` / `AudioItem`：`_set_scene_cursor()` 工具方法 + 在 mouseMove/mouseRelease 调用
- Create: `tests/test_core/test_cursor_label.py`

---

## Task 1: 颜色常量 + `_format_cursor_label`（TDD）

**Files:**
- Modify: `drama_shot_master/ui/widgets/timeline_widget.py`
- Create: `tests/test_core/test_cursor_label.py`

- [ ] **Step 1.1: 写失败测试**

Create `tests/test_core/test_cursor_label.py`:

```python
"""Tests for _format_cursor_label in timeline_widget."""
from __future__ import annotations

from drama_shot_master.ui.widgets.timeline_widget import _format_cursor_label


def test_frames_basic():
    # x=100, ppf=5 → 20 frames → "20f"
    assert _format_cursor_label(100.0, 5.0, 24, "frames") == "20f"


def test_seconds_basic():
    # x=120, ppf=5 → 24 frames; 24/24 = 1.0 → "1.00s"
    assert _format_cursor_label(120.0, 5.0, 24, "seconds") == "1.00s"


def test_seconds_fractional():
    # x=100, ppf=5 → 20 frames; 20/24 ≈ 0.833 → "0.83s"
    assert _format_cursor_label(100.0, 5.0, 24, "seconds") == "0.83s"


def test_ppf_zero_guard():
    # ppf <= 0 → frame=0 → "0f"
    assert _format_cursor_label(100.0, 0.0, 24, "frames") == "0f"


def test_frame_rate_zero_guard():
    # x=120, ppf=5 → 24 frames; 24/max(0,1)=24 → "24.00s"
    assert _format_cursor_label(120.0, 5.0, 0, "seconds") == "24.00s"


def test_negative_x_clamped():
    # x=-50, ppf=5 → round(-10) → max(0,-10)=0 → "0f"
    assert _format_cursor_label(-50.0, 5.0, 24, "frames") == "0f"
```

- [ ] **Step 1.2: 运行测试，确认失败**

Run: `pytest tests/test_core/test_cursor_label.py -v`
Expected: `ImportError: cannot import name '_format_cursor_label'`.

- [ ] **Step 1.3: 加颜色常量**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 找到刻度尺常量区（line 36-41）：

```python
# ---------- 刻度尺常量 ----------

TARGET_MAJOR_PX = 80              # 相邻 major tick 目标间距（像素）
MINOR_RATIO = 5                   # minor = max(1, major // 5)
SECONDS_CANDIDATES = [0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]  # 秒
FRAMES_CANDIDATES = [1, 5, 10, 30, 60, 120, 300, 600]            # 帧
```

在其后追加：

```python
# ---------- 刻度尺 / 游标配色 ----------

RULER_BAND_COLOR = "#2b2f3a"      # 背景带（略亮于场景背景）
TICK_MINOR_COLOR = "#7a8597"      # minor tick（中灰）
TICK_MAJOR_COLOR = "#d4dae6"      # major tick（近白）
TICK_LABEL_COLOR = "#e6ebf2"      # 标签文字（近白）
CURSOR_LINE_COLOR = "#ff4d4d"     # 红色游标线
CURSOR_LABEL_BG = "#ff4d4d"       # 游标标签底（红）
CURSOR_LABEL_FG = "#ffffff"       # 游标标签字（白）
```

- [ ] **Step 1.4: 加纯函数 `_format_cursor_label`**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 紧接 `_pick_tick_interval` 函数之后（line 64 之后、`# MIME types` 之前）加：

```python
def _format_cursor_label(x: float, ppf: float, frame_rate: int,
                         display_mode: str) -> str:
    """游标 scene-x → 当前帧/秒的显示文本。"""
    if ppf <= 0:
        frame = 0
    else:
        frame = max(0, int(round(x / ppf)))
    if display_mode == "frames":
        return f"{frame}f"
    sec = frame / max(frame_rate, 1)
    return f"{sec:.2f}s"
```

- [ ] **Step 1.5: 替换 drawBackground 配色**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `drawBackground` 内的着色（line 388-427）：

```python
        # 1. 背景带
        band = QRectF(0, 0, scene_w, RULER_HEIGHT)
        painter.fillRect(band, QColor("#262a30"))
```
把 `QColor("#262a30")` 改为 `QColor(RULER_BAND_COLOR)`。

minor pen（line 404）：
```python
        painter.setPen(QPen(QColor("#3a3f48"), 1))
```
改为 `painter.setPen(QPen(QColor(TICK_MINOR_COLOR), 1))`。

major + 标签段（line 412-427）当前是：
```python
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

替换为（拆开 major tick 颜色与 label 颜色）：

```python
        # 5. major ticks + 标签
        major_pen = QPen(QColor(TICK_MAJOR_COLOR), 1)
        label_color = QColor(TICK_LABEL_COLOR)
        f = QFont(); f.setPointSize(7); painter.setFont(f)
        fr = max(self.model.frame_rate, 1)
        frame = (int(x_start / ppf) // major) * major
        while frame * ppf <= x_end:
            x = frame * ppf
            painter.setPen(major_pen)
            painter.drawLine(QPointF(x, RULER_HEIGHT - 12),
                             QPointF(x, RULER_HEIGHT))
            if self.model.display_mode == "frames":
                label = f"{frame}f"
            else:
                sec = frame / fr
                label = (f"{int(sec)}s" if sec == int(sec)
                         else f"{sec:.1f}s")
            painter.setPen(label_color)
            painter.drawText(QPointF(x + 2, RULER_HEIGHT - 14), label)
            frame += major
```

- [ ] **Step 1.6: 运行测试，确认通过**

Run: `pytest tests/test_core/test_cursor_label.py -v`
Expected: 6/6 PASS。

- [ ] **Step 1.7: 全量回归**

Run: `pytest -q`
Expected: 290 + 6 = 296 PASS（无回归）。

- [ ] **Step 1.8: 烟测 — 模块可导入**

Run:
```bash
python -c "from drama_shot_master.ui.widgets.timeline_widget import _format_cursor_label, TimelineScene; print('ok')"
```
Expected: `ok`。（若环境无 PySide6，import 会失败——回退用 `python -c "import ast; ast.parse(open('drama_shot_master/ui/widgets/timeline_widget.py').read()); print('syntax ok')"` 并如实报告。）

- [ ] **Step 1.9: 提交**

```bash
git add drama_shot_master/ui/widgets/timeline_widget.py tests/test_core/test_cursor_label.py
git commit -m "feat(timeline): recolor ruler for contrast + add _format_cursor_label

Ruler band/minor/major/label recolored into a clear dark→mid→light
hierarchy via named constants. Add Qt-free _format_cursor_label helper
(scene-x → frame/sec text) for the upcoming drag cursor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: scene 游标状态 + drawForeground + QDrag 钩子

**Files:**
- Modify: `drama_shot_master/ui/widgets/timeline_widget.py` — `TimelineScene` 类

- [ ] **Step 2.1: 在 TimelineScene.__init__ 加 `_cursor_x` 字段**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `TimelineScene.__init__`：

```python
    def __init__(self, model: TimelineModel, pixels_per_frame: float, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_frame = pixels_per_frame
```

在末尾追加一行：

```python
    def __init__(self, model: TimelineModel, pixels_per_frame: float, parent=None):
        super().__init__(parent)
        self.model = model
        self.pixels_per_frame = pixels_per_frame
        self._cursor_x: Optional[float] = None
```

- [ ] **Step 2.2: 加 set_cursor_x + drawForeground**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 在 `drawBackground` 方法之后、`dragEnterEvent` 之前插入两个方法：

```python
    def set_cursor_x(self, x: Optional[float]) -> None:
        """设/清游标 x（scene 坐标）。None = 隐藏。"""
        if self._cursor_x == x:
            return
        self._cursor_x = x
        self.update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._cursor_x is None:
            return
        x = self._cursor_x
        h = self.sceneRect().height()
        # 1. 红色竖线
        painter.setPen(QPen(QColor(CURSOR_LINE_COLOR), 1))
        painter.drawLine(QPointF(x, 0), QPointF(x, h))
        # 2. 顶部标签
        label = _format_cursor_label(
            x, self.pixels_per_frame, self.model.frame_rate,
            self.model.display_mode)
        f = QFont(); f.setPointSize(7); painter.setFont(f)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 6
        th = fm.height() + 2
        box = QRectF(x + 1, 0, tw, th)
        painter.fillRect(box, QColor(CURSOR_LABEL_BG))
        painter.setPen(QColor(CURSOR_LABEL_FG))
        painter.drawText(box, Qt.AlignCenter, label)
```

- [ ] **Step 2.3: dragMoveEvent 设游标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前：

```python
    def dragMoveEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)
```

改为（在 accept 分支里设游标）：

```python
    def dragMoveEvent(self, e):
        if (e.mimeData().hasFormat("application/x-spb-seg-id") or
                e.mimeData().hasFormat(MIME_IMG_PATH)):
            self.set_cursor_x(e.scenePos().x())
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)
```

- [ ] **Step 2.4: dropEvent 清游标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `dropEvent` 开头：

```python
    def dropEvent(self, e):
        view = self.views()[0] if self.views() else None
        if view is None:
            return super().dropEvent(e)
```

在第一行后插入清游标（确保任何 drop 路径都清）：

```python
    def dropEvent(self, e):
        self.set_cursor_x(None)
        view = self.views()[0] if self.views() else None
        if view is None:
            return super().dropEvent(e)
```

- [ ] **Step 2.5: 新增 dragLeaveEvent 清游标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 在 `dropEvent` 之后、`_find_seg_insert_index` 之前插入：

```python
    def dragLeaveEvent(self, e):
        self.set_cursor_x(None)
        super().dragLeaveEvent(e)
```

- [ ] **Step 2.6: 烟测 — 模块可导入**

Run:
```bash
python -c "from drama_shot_master.ui.widgets.timeline_widget import TimelineScene; print('ok')"
```
Expected: `ok`（或语法回退检查，如实报告）。

- [ ] **Step 2.7: 全量回归**

Run: `pytest -q`
Expected: 296 PASS（与 Task 1 后一致）。

- [ ] **Step 2.8: 提交**

```bash
git add drama_shot_master/ui/widgets/timeline_widget.py
git commit -m "feat(timeline): red drag cursor line via scene drawForeground

TimelineScene tracks _cursor_x + set_cursor_x(); drawForeground paints a
full-height red line with a frame/sec label box. QDrag reorder hooks
(dragMove sets, drop/dragLeave clear) drive it during segment reordering.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Item 拖拽触发点（SegmentItem + AudioItem）

**Files:**
- Modify: `drama_shot_master/ui/widgets/timeline_widget.py` — `SegmentItem` 与 `AudioItem` 类

- [ ] **Step 3.1: SegmentItem 加 `_set_scene_cursor` 工具方法**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 在 `SegmentItem._top_view` 方法之后（class 内最后一个方法之后）加：

```python
    def _set_scene_cursor(self, x: Optional[float]) -> None:
        scene = self.scene()
        if isinstance(scene, TimelineScene):
            scene.set_cursor_x(x)
```

- [ ] **Step 3.2: SegmentItem.mouseMoveEvent resize 分支报游标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `SegmentItem.mouseMoveEvent` 的 resize 分支：

```python
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            event.accept()
            return
```

在 `self.update()` 之后加一行 `self._set_scene_cursor(self.pos().x() + new_w)`：

```python
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            self._set_scene_cursor(self.pos().x() + new_w)
            event.accept()
            return
```

- [ ] **Step 3.3: SegmentItem.mouseReleaseEvent 两分支清游标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `SegmentItem.mouseReleaseEvent`：

```python
    def mouseReleaseEvent(self, event):
        if self._press_mode == "resize":
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
```

在两个分支的 `self._press_mode = "none"` 之前各加一行 `self._set_scene_cursor(None)`：

```python
    def mouseReleaseEvent(self, event):
        if self._press_mode == "resize":
            view = self._top_view()
            ppf = view.pixels_per_frame if view else 5.0
            new_len = max(1, int(round(self._width / ppf)))
            if view is not None:
                view.segmentChanged.emit(self.seg.seg_id, new_len)
            self._set_scene_cursor(None)
            self._press_mode = "none"
            event.accept()
            return
        if self._press_mode == "move":
            # 原位释放 = 仅选中
            view = self._top_view()
            if view is not None:
                view.segmentSelected.emit(self.seg.seg_id)
            self._set_scene_cursor(None)
            self._press_mode = "none"
            event.accept()
            return
        super().mouseReleaseEvent(event)
```

- [ ] **Step 3.4: AudioItem 加 `_set_scene_cursor` 工具方法**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 在 `AudioItem._top_view` 方法之后加（与 SegmentItem 同形）：

```python
    def _set_scene_cursor(self, x: Optional[float]) -> None:
        scene = self.scene()
        if isinstance(scene, TimelineScene):
            scene.set_cursor_x(x)
```

- [ ] **Step 3.5: AudioItem.mouseMoveEvent resize + move 分支报游标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `AudioItem.mouseMoveEvent`：

```python
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
```

改为（resize 报右沿、move 报左沿）：

```python
    def mouseMoveEvent(self, event):
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            self._set_scene_cursor(self.pos().x() + new_w)
            event.accept()
            return
        if self._press_mode == "move":
            scene_dx = event.scenePos().x() - (
                self._move_start_pos.x() + self._press_x)
            new_x = max(0, self._move_start_pos.x() + scene_dx)
            self.setPos(new_x, AUDIO_LANE_Y)
            self._set_scene_cursor(new_x)
            event.accept()
            return
        super().mouseMoveEvent(event)
```

- [ ] **Step 3.6: AudioItem.mouseReleaseEvent 两分支清游标**

Edit `drama_shot_master/ui/widgets/timeline_widget.py`. 当前 `AudioItem.mouseReleaseEvent`：

```python
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
```

在两个分支的 `self._press_mode = "none"` 之前各加 `self._set_scene_cursor(None)`：

```python
    def mouseReleaseEvent(self, event):
        view = self._top_view()
        if view is None:
            return super().mouseReleaseEvent(event)
        ppf = view.pixels_per_frame
        if self._press_mode == "resize":
            new_len = max(1, int(round(self._width / ppf)))
            view.audioChanged.emit(self.audio.audio_id,
                                    self.audio.start_frame, new_len)
            self._set_scene_cursor(None)
            self._press_mode = "none"
            event.accept()
            return
        if self._press_mode == "move":
            new_start = max(0, int(round(self.pos().x() / ppf)))
            view.audioChanged.emit(self.audio.audio_id,
                                    new_start, self.audio.length_frames)
            self._set_scene_cursor(None)
            self._press_mode = "none"
            event.accept()
            return
        super().mouseReleaseEvent(event)
```

- [ ] **Step 3.7: 烟测 — 模块可导入**

Run:
```bash
python -c "from drama_shot_master.ui.widgets.timeline_widget import SegmentItem, AudioItem, TimelineScene; print('ok')"
```
Expected: `ok`（或语法回退，如实报告）。

- [ ] **Step 3.8: 全量回归**

Run: `pytest -q`
Expected: 296 PASS。

- [ ] **Step 3.9: 提交**

```bash
git add drama_shot_master/ui/widgets/timeline_widget.py
git commit -m "feat(timeline): drive drag cursor from segment/audio item drags

SegmentItem resize and AudioItem resize/move now report the active edge x
to the scene cursor during mouseMove and clear it on release, so the red
cursor line tracks every drag interaction.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 手测清单（end-of-feature）

**Files:** 无代码变更。

- [ ] **Step 4.1: 把手测清单交回给用户**（参见 spec §6.2）

1. 启动应用打开视频面板：刻度带可见，minor（中灰）/major（近白）/label（近白）三级明暗清晰可读，不再是隐形蓝。
2. 拖段右沿拉伸：红色竖线跟随右沿，顶部红底白字标签实时显示帧/秒；松开后红线消失。
3. 拖音频段整体移动 + 拖右沿拉伸：同样出现红线 + 标签，松开消失。
4. 拖整张段卡重排：QDrag 期间红线跟随鼠标；drop 或拖出时消失。
5. 切 frames/seconds：拖拽时标签格式相应变化（`45f` ↔ `1.88s`）。
6. 红线贯穿刻度带 + 段轨 + 音频轨整个高度。

报告：全过报 DONE；任一异常报 DONE_WITH_CONCERNS + 具体哪步。

---

## Self-Review 记录

- **Spec coverage:**
  - §3 配色（7 常量） → Task 1.3
  - §4.1 `_format_cursor_label` → Task 1.4（TDD: Task 1.1 测试）
  - §4.2 `_cursor_x` + `set_cursor_x` → Task 2.1 / 2.2
  - §4.3 `drawForeground` → Task 2.2
  - §4.4 触发点：SegmentItem → Task 3.1-3.3；AudioItem → Task 3.4-3.6；Scene QDrag → Task 2.3-2.5
  - §4.5 drawBackground 配色替换（含 major/label 拆色） → Task 1.5
  - §5 数据流 → Task 2 + Task 3 合成
  - §6.1 单测 → Task 1.1（6 用例，含 spec 6 行全覆盖）
  - §6.2 手测 → Task 4.1
  - §7 依赖 → 仅 timeline_widget.py，无新增依赖
  - §8 YAGNI → 计划无 snap / 悬停显 / 点击 / 配置项

- **Placeholder scan:** 无 TBD / "similar to" / 抽象占位；每个代码 step 给完整代码块或精确 before/after。

- **Type consistency:**
  - `_format_cursor_label(x: float, ppf: float, frame_rate: int, display_mode: str) -> str` 在 Task 1 定义、Task 2.2 调用一致。
  - `set_cursor_x(x: Optional[float])` 在 Task 2.2 定义；`_set_scene_cursor(x)` 在 Task 3.1/3.4 调用它，类型一致（传 float 或 None）。
  - 颜色常量名 `RULER_BAND_COLOR / TICK_MINOR_COLOR / TICK_MAJOR_COLOR / TICK_LABEL_COLOR / CURSOR_LINE_COLOR / CURSOR_LABEL_BG / CURSOR_LABEL_FG` 在 Task 1 定义、后续引用一致。
  - `Optional` 已在文件顶部 `from typing import Optional` 导入（SegmentItem 已用）；`QFont`/`QColor`/`QPen`/`QPointF`/`QRectF`/`QPainter` 均已导入。
