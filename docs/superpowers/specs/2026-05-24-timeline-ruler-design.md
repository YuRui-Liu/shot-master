# 时间轴刻度（Timeline Ruler）设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量功能（设计阶段）
**日期**：2026-05-24
**状态**：设计评审通过，待写实现 plan
**关联**：v0.7 视频面板已落地的 `timeline_widget.py`。

---

## 1. 背景与目标

### 1.1 问题

`TimelineWidget` 当前是 DAW 比例条样式但**没有任何时间刻度**。用户拖动/调整段长度时只能凭长方形宽度估算，无法精确对齐到某个秒数或帧数。

### 1.2 目标

在时间轴顶部加一条自适应缩放的刻度尺，跟当前 `display_mode`（frames / seconds）联动显示数字标签。**只做视觉参考，不做吸附**。

### 1.3 非目标

- 不做 snap-to-grid（用户拒绝）
- 不做 playhead / 鼠标位置 tooltip
- 不做点击刻度跳转
- 不引入新 widget

---

## 2. 关键决策（来自评审 Q&A）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 吸附行为 | 不吸附，只画刻度 | 用户明确拒绝 snap；YAGNI |
| 渲染位置 | scene 坐标 y∈[0, 20]，drawBackground | 跟内容横向同步滚动，无新 widget |
| 刻度自适应 | 根据 `pixels_per_frame` 自动选间隔 | major tick 约 80px 间距，DAW 通用做法 |
| 标签单位 | 跟 `display_mode` 联动 | 与现有 length badge 一致 |
| 时间格式 | `"45f"` 或 `"1.5s"` | 已有 badge 用同样的格式 |

---

## 3. 架构

### 3.1 影响面

仅 `drama_shot_master/ui/widgets/timeline_widget.py` 一个文件改动：

| 改动 | 位置 |
|---|---|
| 新增常量 `RULER_HEIGHT = 20` | 布局常量区 |
| `SEG_LANE_Y = 0` → `SEG_LANE_Y = RULER_HEIGHT` | 同上 |
| `AUDIO_LANE_Y` 表达式更新 | 同上 |
| 新增纯函数 `_pick_tick_interval()` | 模块级 |
| 新增 `TimelineScene.drawBackground()` 重载 | TimelineScene 类内 |
| `setSceneRect()` 总高度 +RULER_HEIGHT | `TimelineScene.rebuild()` 末尾 |
| "拖一张图到这里开始"提示文本 y 坐标 +RULER_HEIGHT | 同上 |

### 3.2 边界

- `_pick_tick_interval(pixels_per_frame, frame_rate, display_mode) -> (major_frames, minor_frames)` 是纯函数 → 可单测，无 Qt 依赖
- `drawBackground` 只读 scene 的 `pixels_per_frame`、`model.display_mode`、`model.frame_rate`，不修改任何状态
- 刻度尺渲染区域 y∈[0, RULER_HEIGHT]，items 都在 y >= RULER_HEIGHT；不存在 z-order 冲突

---

## 4. 详细设计

### 4.1 tick 间隔选择算法

目标：让相邻 major tick 间距 ≈ 80px。

```python
TARGET_MAJOR_PX = 80
MINOR_RATIO = 5  # minor tick 是 major 的 1/5

SECONDS_CANDIDATES = [0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]
FRAMES_CANDIDATES = [1, 5, 10, 30, 60, 120, 300, 600]

def _pick_tick_interval(ppf: float, frame_rate: int, display_mode: str
                        ) -> tuple[int, int]:
    """返回 (major_frames, minor_frames)。"""
    fr = max(frame_rate, 1)
    if display_mode == "seconds":
        for sec in SECONDS_CANDIDATES:
            major_frames = max(1, int(round(sec * fr)))
            if major_frames * ppf >= TARGET_MAJOR_PX:
                return (major_frames, max(1, major_frames // MINOR_RATIO))
        # ppf 极小时回退到最大候选
        last = max(1, int(round(SECONDS_CANDIDATES[-1] * fr)))
        return (last, max(1, last // MINOR_RATIO))
    else:  # frames
        for f in FRAMES_CANDIDATES:
            if f * ppf >= TARGET_MAJOR_PX:
                return (f, max(1, f // MINOR_RATIO))
        last = FRAMES_CANDIDATES[-1]
        return (last, max(1, last // MINOR_RATIO))
```

### 4.2 drawBackground 渲染

```python
def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
    super().drawBackground(painter, rect)
    # 1. 背景带
    band = QRectF(0, 0, self.sceneRect().width(), RULER_HEIGHT)
    painter.fillRect(band, QColor("#262a30"))
    # 2. 选 tick 间隔
    major, minor = _pick_tick_interval(
        self.pixels_per_frame, self.model.frame_rate, self.model.display_mode)
    # 3. 计算可见 x 范围（rect 是脏区域）
    x_start = max(0.0, rect.left())
    x_end = min(self.sceneRect().width(), rect.right())
    # 4. 画 minor ticks
    painter.setPen(QPen(QColor("#3a3f48"), 1))
    frame = (int(x_start / self.pixels_per_frame) // minor) * minor
    while frame * self.pixels_per_frame <= x_end:
        if frame % major != 0:
            x = frame * self.pixels_per_frame
            painter.drawLine(QPointF(x, RULER_HEIGHT - 6),
                             QPointF(x, RULER_HEIGHT))
        frame += minor
    # 5. 画 major ticks + 标签
    painter.setPen(QPen(QColor("#888"), 1))
    f = QFont(); f.setPointSize(7); painter.setFont(f)
    frame = (int(x_start / self.pixels_per_frame) // major) * major
    while frame * self.pixels_per_frame <= x_end:
        x = frame * self.pixels_per_frame
        painter.drawLine(QPointF(x, RULER_HEIGHT - 12), QPointF(x, RULER_HEIGHT))
        if self.model.display_mode == "frames":
            label = f"{frame}f"
        else:
            sec = frame / max(self.model.frame_rate, 1)
            label = f"{sec:.1f}s" if sec != int(sec) else f"{int(sec)}s"
        painter.drawText(QPointF(x + 2, RULER_HEIGHT - 14), label)
        frame += major
```

### 4.3 布局常量调整

```python
RULER_HEIGHT = 20
SEG_LANE_Y = RULER_HEIGHT          # 改自 0
SEG_HEIGHT = 60                    # 不变
LANE_GAP = 10                      # 不变
AUDIO_LANE_Y = SEG_LANE_Y + SEG_HEIGHT + LANE_GAP   # = 90，改自 70
AUDIO_HEIGHT = 30                  # 不变
```

### 4.4 sceneRect 高度

`TimelineScene.rebuild()` 末尾：
```python
self.setSceneRect(0, 0, total_w,
                  AUDIO_LANE_Y + AUDIO_HEIGHT + 20)  # 已经包含 RULER_HEIGHT
```
因 `AUDIO_LANE_Y` 已上调，此行表达式不变，自然吃到 ruler 高度。

### 4.5 空场景提示文本

```python
hint.setPos(20, SEG_LANE_Y + SEG_HEIGHT / 2 - 10)
```
改自 `(20, SEG_HEIGHT / 2 - 10)`，跟随 SEG_LANE_Y 偏移。

---

## 5. 数据流

```
[user Ctrl+wheel 缩放 / 切换 display_mode]
        ↓
[TimelineWidget.pixels_per_frame 改变 或 model.display_mode 改变]
        ↓
[rebuild() 触发，scene.update() 隐式触发 drawBackground]
        ↓
[_pick_tick_interval(ppf, fr, mode) → (major, minor)]
        ↓
[在 y∈[0, RULER_HEIGHT] 画 minor ticks + major ticks + 标签]
```

---

## 6. 测试

### 6.1 单元测试 `tests/test_core/test_tick_picker.py`

针对 `_pick_tick_interval` 纯函数。期望值按 `TARGET_MAJOR_PX=80` + `MINOR_RATIO=5` 精确推导：

| 用例 | 输入 | 期望 (major, minor) | 推导 |
|---|---|---|---|
| zoom_in_seconds | ppf=20, fr=24, mode="seconds" | (12, 2) | 0.5s=12f, 12·20=240px≥80 → 12f / 12//5=2 |
| mid_seconds | ppf=5, fr=24, mode="seconds" | (24, 4) | 0.5s→60<80；1s=24f, 24·5=120≥80 → 24f / 24//5=4 |
| zoom_out_seconds | ppf=0.5, fr=24, mode="seconds" | (240, 48) | 0.5/1/2/5s 均<80px；10s=240f, 240·0.5=120≥80 → 240f / 48 |
| zoom_in_frames | ppf=20, fr=24, mode="frames" | (5, 1) | 1f=20<80；5f=100≥80 → 5f / 1 |
| zoom_out_frames | ppf=0.5, fr=24, mode="frames" | (300, 60) | 1..120f 均<80；300f=150≥80 → 300f / 60 |
| max_zoom_frames | ppf=50, fr=24, mode="frames" | (5, 1) | 1f=50<80；5f=250≥80 → 5f / 1 |
| zero_frame_rate | ppf=5, fr=0, mode="seconds" | 不崩，等价 fr=1 | 内部 `max(frame_rate,1)` 兜底 |
| minor_at_least_1 | 任意 | minor≥1 | `max(1, major//5)` |

### 6.2 手测清单

- 启动应用打开视频面板
- 默认视图：能看到顶部 20px 刻度带
- Ctrl+滚轮放大：刻度从 5s/10s 逐渐细化到 1s → 1f
- Ctrl+滚轮缩小：刻度从 1s 粗化到 5s、10s、30s
- 切换 frames ↔ seconds：标签格式立即变化
- 拖动段后：段的左/右边缘大致对齐到看得见的刻度
- 空场景"拖一张图到这里开始"提示位置正确（在刻度下方）

---

## 7. 依赖与影响面

- 零新增 pip 依赖
- 仅 `drama_shot_master/ui/widgets/timeline_widget.py` 一个文件
- 向后兼容：所有现有信号、API、坐标计算都基于 `pixels_per_frame`，仅 y 坐标整体下移
- 影响的其他文件：无（VideoPanel 等使用方不感知 y 坐标变化）

---

## 8. 不做的事（YAGNI 清单）

- ❌ Snap-to-grid 拖动吸附
- ❌ Playhead / current-frame 指示器
- ❌ 鼠标位置实时显示当前帧/秒 tooltip
- ❌ 点击刻度跳转
- ❌ 标签格式可配置
- ❌ 用单独 QWidget 实现 ruler（增加 layout 耦合）
- ❌ 刻度颜色、字号、高度可配置
