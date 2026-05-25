# 刻度尺配色修复 + 红色拖拽游标 设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量（设计阶段）
**日期**：2026-05-25
**状态**：设计评审通过，待写实现 plan
**关联**：紧接 [2026-05-24-timeline-ruler-design.md] 已落地的刻度尺。

---

## 1. 背景与目标

### 1.1 问题

刚落地的刻度尺存在两个问题（用户手测反馈）：

1. **对比度太低**：背景带 `#262a30`（近黑），minor tick `#3a3f48` 几乎与背景同色看不清，major/label `#888` 在近黑背景上也偏暗。
2. **缺少拖拽时的精确定位反馈**：拖动/拉伸段时无法看出当前对齐到哪个时间/帧。

### 1.2 目标

1. 重配刻度尺颜色，建立清晰明暗层级。
2. 拖拽/调整时显示一条红色竖向游标线（跟随鼠标 x），顶部带当前帧/秒标签；松开消失。

### 1.3 非目标

- 不做 snap-to-grid（用户已两次拒绝）
- 不做悬停即显游标（仅拖拽时显）
- 红线不可点击、不持久化、无播放语义

---

## 2. 关键决策（来自评审 Q&A）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 游标出现时机 | 拖拽/拉伸/音频移动时 | 契合"拖动时看准位置"的初衷；不干扰静态浏览 |
| 游标标签 | 带标签，显示帧/秒 | 拖拽时能精确读出当前位置 |
| 游标-刻度关系 | 跟随鼠标的视觉参考，不吸附 | 延续既有"只画刻度作参考"原则 |
| 配色 | 暗 band → 中 minor → 亮 major/label | 清晰三级明暗层级 |

---

## 3. 配色方案

抽成模块级常量，便于后续调整：

| 常量 | 元素 | 值 | 说明 |
|---|---|---|---|
| `RULER_BAND_COLOR` | 背景带 | `#2b2f3a` | 略提亮，与场景背景 `#1e1e1e` 区分 |
| `TICK_MINOR_COLOR` | minor tick | `#7a8597` | 中灰，清晰可见 |
| `TICK_MAJOR_COLOR` | major tick | `#d4dae6` | 近白 |
| `TICK_LABEL_COLOR` | 标签文字 | `#e6ebf2` | 近白，清晰可读 |
| `CURSOR_LINE_COLOR` | 红色游标线 | `#ff4d4d` | 醒目红 |
| `CURSOR_LABEL_BG` | 游标标签底 | `#ff4d4d` | 红底 |
| `CURSOR_LABEL_FG` | 游标标签字 | `#ffffff` | 白字 |

---

## 4. 详细设计

### 4.1 纯函数 `_format_cursor_label`

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

Qt-free，可单测。

### 4.2 TimelineScene 状态 + API

```python
def __init__(self, model, pixels_per_frame, parent=None):
    super().__init__(parent)
    self.model = model
    self.pixels_per_frame = pixels_per_frame
    self._cursor_x: Optional[float] = None   # 新增

def set_cursor_x(self, x: Optional[float]) -> None:
    """设/清游标 x（scene 坐标）。None = 隐藏。"""
    if self._cursor_x == x:
        return
    self._cursor_x = x
    self.update()
```

### 4.3 drawForeground 渲染游标

```python
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

### 4.4 触发点

**SegmentItem.mouseMoveEvent**（resize 分支，已存在）末尾追加：
```python
        if self._press_mode == "resize":
            dx = event.pos().x() - self._press_x
            new_w = max(8.0, self._resize_start_w + dx)
            self.prepareGeometryChange()
            self._width = new_w
            self.update()
            self._set_scene_cursor(self.pos().x() + new_w)   # 新增
            event.accept()
            return
```

**SegmentItem.mouseReleaseEvent**（resize 分支 + move 分支）：在 `self._press_mode = "none"` 之前加 `self._set_scene_cursor(None)`。

**AudioItem.mouseMoveEvent**：
- resize 分支 → `self._set_scene_cursor(self.pos().x() + new_w)`
- move 分支 → `self._set_scene_cursor(new_x)`

**AudioItem.mouseReleaseEvent**：两个分支都在结束前 `self._set_scene_cursor(None)`。

两个 Item 各加一个小工具方法：
```python
    def _set_scene_cursor(self, x: Optional[float]) -> None:
        scene = self.scene()
        if isinstance(scene, TimelineScene):
            scene.set_cursor_x(x)
```

**TimelineScene.dragMoveEvent**（段 reorder 的 QDrag）：在已有的 accept 逻辑里追加 `self.set_cursor_x(e.scenePos().x())`。

**TimelineScene.dropEvent** 和 **dragLeaveEvent**：调 `self.set_cursor_x(None)`。
（`dragLeaveEvent` 当前不存在，需新增一个仅清游标的重载。）

### 4.5 drawBackground 配色替换

把 §3 的四个常量替换进现有 `drawBackground`：
- `painter.fillRect(band, QColor("#262a30"))` → `QColor(RULER_BAND_COLOR)`
- minor pen `QColor("#3a3f48")` → `QColor(TICK_MINOR_COLOR)`
- major pen `QColor("#888")` → `QColor(TICK_MAJOR_COLOR)`
- 标签 `painter.setPen(QColor("#888"))`……当前 major 与标签共用一个 pen。拆开：major tick 用 `TICK_MAJOR_COLOR` 画线，画标签前 `painter.setPen(QColor(TICK_LABEL_COLOR))`。

---

## 5. 数据流

```
[用户按下段右沿并拖动 / 拖动音频 / QDrag 重排]
        ↓
[Item.mouseMoveEvent 或 Scene.dragMoveEvent 计算当前 x]
        ↓
[scene.set_cursor_x(x) → self.update()]
        ↓
[drawForeground 画红线 + _format_cursor_label 标签]
        ↓
[释放 / drop / dragLeave → set_cursor_x(None) → 红线消失]
```

---

## 6. 测试

### 6.1 单元测试 `tests/test_core/test_cursor_label.py`

针对 `_format_cursor_label`：

| 用例 | 输入 (x, ppf, fr, mode) | 期望 |
|---|---|---|
| frames_basic | (100, 5, 24, "frames") | "20f"（100/5=20） |
| seconds_basic | (120, 5, 24, "seconds") | "1.00s"（24f/24=1.0） |
| seconds_fractional | (100, 5, 24, "seconds") | "0.83s"（20f/24≈0.833） |
| ppf_zero_guard | (100, 0, 24, "frames") | "0f"（ppf<=0 → frame=0） |
| frame_rate_zero_guard | (120, 5, 0, "seconds") | "24.00s"（24f/max(0,1)=24） |
| negative_x_clamped | (-50, 5, 24, "frames") | "0f"（max(0, …)） |

### 6.2 手测清单

1. 启动应用打开视频面板：刻度带可见，minor/major/label 三级明暗清晰可读（不再是隐形蓝）。
2. 拖动段右沿拉伸：出现红色竖线跟随右沿，顶部标签实时显示帧/秒；松开后红线消失。
3. 拖动音频段（整体移动 + 右沿拉伸）：同样出现红线 + 标签。
4. 拖动段重排（拖整张卡到别处）：QDrag 期间红线跟随鼠标；drop 后消失。
5. 切 frames/seconds：拖拽时标签格式相应变化。
6. 红线贯穿刻度带 + 段轨 + 音频轨整个高度。

---

## 7. 依赖与影响面

- 零新增 pip 依赖
- 仅 `drama_shot_master/ui/widgets/timeline_widget.py`
- 向后兼容：仅新增渲染/状态，不改任何信号契约或坐标计算

---

## 8. 不做的事（YAGNI 清单）

- ❌ Snap-to-grid
- ❌ 悬停即显游标
- ❌ 红线点击 / 持久化 / 播放语义
- ❌ 配色用户可配置（仅抽成常量，硬编码值）
- ❌ 游标标签精度可配置（frames 整数、seconds 两位小数固定）
