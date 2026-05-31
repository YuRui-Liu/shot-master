# 动态叠加子轨渲染设计 — 子项目 #3c

> 日期：2026-05-30　分支：main
> #3「框选→生成→叠加多子轨」第 3 块（看得见）。地基已就绪：3a OverlaySession（数据模型）/ 3b MixStreamEngine（实时混音播放）。后续 3d 框选生成交互。
> 布局已经 `docs/explorer/3c-overlay-track-layout-confirm.html` 可视化确认：**方案 A**。

## 背景与定位

3a 把叠加片段存进 `overlay.json`，3b 能把它们采样级混音播放，但 DAW 时间轴上**还看不见**它们。本块只做**渲染 + 选中查看 + 每 lane 静音/音量**，让用户在固定 4 轨之外看到、定位、调整这些动态片段。**不做**框选生成（3d）、不做片段拖拽/缩放/双击编辑。

与现有 4 固定轨（video/bgm/sfx/dialogue，走 `_Cue`/`_CueRef`/command/undo）**解耦并存**：overlay 渲染与选中走独立路径，复用同一时间轴坐标系（zoom/scroll/duration）与 3b 的 `MixStreamEngine`。

## 已锁定决策

- **布局 A**：固定 4 轨布局（`_TRACK_Y`）**零改动**；其下挂一个独立「动态叠加区」——一个折叠头 + 先全部 bgm lane（lane 0,1,2…）、再全部 sfx lane。
- **可折叠 + 动态高度**：叠加区带折叠头（▼/▶ + “动态叠加区(N)”，N=lane 总数）。`DawTrackView`/header 列从固定高度改为**动态高度** = 固定区 + (折叠 或 空 ? 0 : 折叠头 + lane 行数×行高)。**overlay 为空 → 整区（含折叠头）不显示**，零视觉负担。
- **交互 = 只读渲染 + 可选中**：overlay 片段块渲染（斜纹/区分色 + label）；单击选中 → `OverlayInspector` 查看 kind/lane/时间/prompt/音量/启用/有无音频。本阶段**不**拖拽、不缩放、不双击编辑（留 3d）。
- **每 lane 头部 M + 音量**：叠加区每条 lane 头一个 mute 开关 + 音量滑条，作用于**该 lane 内所有 segment**（mute→全段 `enabled=False`；volume→全段 `volume`）。改动即时 `save_overlay` 写回 + `mix_engine.set_segments` 刷新 + 重绘。**不入 undo 栈**（与现有固定轨 mix 状态一致，非 command）。
- **选区互斥**：点 overlay 片段 → 清空固定轨 `Selection`；点固定轨 cue → 清空 overlay 选中。二者不同时选。
- **lane 行高常量** `_OV_LANE_H = 28`、折叠头 `_OV_HEAD_H = 18`（与确认稿一致）。kind 顺序固定 `["bgm", "sfx"]`。

## 组件

### 1. overlay_layout（纯函数，`drama_shot_master/ui/widgets/daw/overlay_layout.py`）

无 Qt、全单测。把 overlay 片段算成可绘制的行布局。

```python
_OV_LANE_H = 28
_OV_HEAD_H = 18
_OV_KIND_ORDER = ["bgm", "sfx"]

@dataclass
class OverlayRow:
    kind: str            # "bgm" | "sfx"
    lane: int            # 0,1,2…
    y: int               # 相对叠加区顶部（折叠头之下）的 y
    segments: list       # 该 (kind,lane) 内的 OverlaySegment（按 t_start 排序）

def overlay_rows(segments, *, base_y, collapsed) -> tuple[list[OverlayRow], int]:
    """返回 (rows, region_h)。
    collapsed 或 segments 空 → rows=[]，region_h = 0（空）或 _OV_HEAD_H（折叠但非空，只占头）。
    展开 → 按 kind(bgm→sfx)×lane 升序产出行，y 从 base_y+_OV_HEAD_H 起逐行 +_OV_LANE_H；
    region_h = _OV_HEAD_H + 行数×_OV_LANE_H。
    空 segments → region_h=0（连折叠头都不画）。"""

def lane_count(segments) -> int      # 总 lane 数（各 kind lanes 求和）
def lanes_of(segments, kind) -> int  # 某 kind 的 lane 数
```

- lane 划分复用 3a `OverlaySession` 语义：同 kind 内 `seg.lane` 去重计数。直接按 `seg.kind`/`seg.lane` 分组即可（不必反推）。

### 2. DawTrackView 扩展（`daw_track_view.py`）

- 新状态：`self._overlay_segs = []`、`self._overlay_collapsed = False`。
- 新 API：
  - `set_overlay(segments, *, collapsed)`：存 + 重算 `setMinimumHeight(固定_MIN_H_no_pad + region_h)` + `update()`。
  - 现有 `_MIN_H` 拆成固定区高度常量；总高 = 固定区 + `overlay_rows(...)` 的 region_h。
- 新信号：
  - `overlayCollapseToggled = Signal()`
  - `overlaySegmentClicked = Signal(str, object)`  # seg_id, modifiers
- `paintEvent` 末尾追加：固定区照旧后，画折叠头（▼/▶ + 文本，y=固定区底），展开则按 `overlay_rows` 画 lane 背景行（`#202024`）+ 片段块。片段块用 `_t_to_x` 定位；选中 seg → 高亮描边；斜纹用 `QBrush(color, Qt.BDiagPattern)` 或 lighter 区分（避免与固定 bgm/sfx 纯色混淆）。
- `playhead` 竖线高度改用 `self.height()`（已是全高，自动覆盖叠加区）。
- 命中：在 `mousePressEvent` 最前面加 overlay 区判定（y ≥ 固定区底）：点折叠头 → emit `overlayCollapseToggled`；点片段 → emit `overlaySegmentClicked(seg.id, mod)` 并 `return`（不进入固定轨/playhead 分支）。空白叠加区 → 吞掉（不拖 playhead）。
- 纯逻辑 `_overlay_seg_at(x,y)->seg_id|None` 抽出便于测。

### 3. OverlayHeaderSection（`daw/overlay_header.py`）

固定宽 130（与 `TrackHeaderColumn` 对齐），放在 header 列容器中 `TrackHeaderColumn` **下方**。行高/顺序与 DawTrackView 叠加区严格对齐。

```python
class OverlayHeaderSection(QWidget):
    collapseToggled = Signal()
    laneMuteToggled = Signal(str, int, bool)    # kind, lane, muted
    laneVolumeChanged = Signal(str, int, float) # kind, lane, volume
    def set_overlay(self, segments, *, collapsed) -> None:
        """重建：折叠头行（点击 emit collapseToggled）+ 展开时每 lane 一行
        （标签 'bgm·0' + M 按钮 + 音量 slider）。空 segments → 整体隐藏。
        M/vol 初值取该 lane 内 segment 聚合（任一 enabled=False→该 lane 视为 mute；
        音量取 lane 内首段 volume）。"""
```

- M QSS 复用 `track_header_column` 的 `_MUTE_QSS`；slider range 0–150。

### 4. OverlayInspector（`daw/inspector/overlay_inspector.py`）

只读为主，与现有 empty/bgm/sfx/dialogue inspector 并列。

```python
class OverlayInspector(QWidget):
    def set_segment(self, seg) -> None:
        """显示：标题 'BGM·lane0' / 'SFX·lane1'、时间 't_start–t_end (时长)'、
        prompt（只读 wrap）、音量（只读 label '80%'）、启用状态、音频('已生成'/'未生成')。"""
```

- 本阶段不放编辑控件（音量/启用编辑走 header lane 或留 3d）。

### 5. SoundtrackEditor 接线（`soundtrack_editor.py`）

- 新状态：`self._overlay_collapsed = False`、`self._overlay_sel_id = None`。
- header 列容器：`tv_row` 左侧由 `TrackHeaderColumn` 改为「`TrackHeaderColumn` + `OverlayHeaderSection`」垂直堆叠的小 QWidget。
- 新 `_refresh_overlay_view()`：把 `self._overlay_session.segments` 推给 `track_view.set_overlay(segs, collapsed=...)` 与 `overlay_header.set_overlay(...)`。在 `_refresh_track_view()` 末尾调用一次。
- 信号接线：
  - `track_view.overlayCollapseToggled` / `overlay_header.collapseToggled` → 翻 `_overlay_collapsed` + `_refresh_overlay_view()`。
  - `track_view.overlaySegmentClicked(seg_id, mod)` → `self._selection.clear()`；`_overlay_sel_id=seg_id`；切 `OverlayInspector`（`set_segment(self._overlay_session.get(seg_id))`）。
  - `overlay_header.laneMuteToggled(kind,lane,muted)` / `laneVolumeChanged(...)` → 改该 lane 内全段 `enabled`/`volume` → `save_overlay(work_dir, session)` → `mix_engine.set_segments(session.segments)` → `_refresh_overlay_view()`。
  - 现有 `self._selection.changed`（固定轨）→ 在 `_refresh_inspector` 里：若有固定选区则 `_overlay_sel_id=None`（互斥）。
- 已有 3b 接线（`load_overlay`→`mix_engine.set_segments`）保持；本块新增渲染刷新 + lane 控件刷新调用点。

## 错误处理 / 降级

- overlay 为空 / `overlay.json` 缺失 → `overlay_rows` 返回 region_h=0，叠加区与 header 段都隐藏，固定轨与现有行为零变化。
- 选中的 seg_id 在 session 中已不存在（并发删改）→ `get` 返回 None → 切回 `EmptyInspector`，不崩。
- lane mute/volume 时 `save_overlay` 抛（磁盘问题）→ 捕获记日志，UI 不崩（内存态已改，下次刷新重试）。

## 测试策略

**overlay_layout（纯函数全单测）**
- 空 segments → `overlay_rows` 返回 `([], 0)`；`lane_count`=0。
- 2 bgm lane（lane0/lane1）+ 1 sfx lane → 3 行，顺序 bgm0,bgm1,sfx0；y 递增 `_OV_HEAD_H, +_OV_LANE_H…`；region_h=`_OV_HEAD_H+3*_OV_LANE_H`。
- collapsed=True 且非空 → `([], _OV_HEAD_H)`。
- `lanes_of(segs,"bgm")` / `lanes_of(segs,"sfx")` 计数正确；同 lane 多段聚到一行并按 t_start 排序。

**DawTrackView overlay（smoke + 纯逻辑）**
- `set_overlay([...], collapsed=False)` → `minimumHeight()` 比空时增大；`collapsed=True` → 高度回落到只含折叠头。
- `set_overlay([], ...)` → 高度等于纯固定区。
- `_overlay_seg_at(x,y)`：命中片段返回其 id；命中折叠头/空白返回 None。
- 模拟点击折叠头 → `overlayCollapseToggled` 发射；点片段 → `overlaySegmentClicked(seg_id, mod)` 发射（用 QSignalSpy / 直接调 handler）。

**OverlayHeaderSection（smoke）**
- `set_overlay(2bgm+1sfx, collapsed=False)` → 3 个 lane 行 + 折叠头；`collapsed=True` → 仅折叠头可见。
- 点折叠头 → `collapseToggled`；点某 lane M → `laneMuteToggled("bgm",0,True)`；拖 slider → `laneVolumeChanged("bgm",0,值)`。
- 空 segments → 整体 hidden。

**OverlayInspector（smoke）**
- `set_segment(seg)` 显示 kind/lane/时间/prompt/音量/启用/音频字段；`audio_path=""` → 显示“未生成”。

**editor 接线（smoke，mock 重组件）**
- `_refresh_overlay_view` 把 segments 推给 track_view + header（mock 验证调用）。
- overlay 片段点击 → 固定 `Selection` 被清；inspector 切 `OverlayInspector`。
- lane mute → 对应 lane 全段 `enabled` 改 + `save_overlay`（mock/tmp）被调 + `mix_engine.set_segments` 被调。
- overlay 空时 `_refresh_overlay_view` 不崩。

## 文件清单

```
新增:
  drama_shot_master/ui/widgets/daw/overlay_layout.py
  drama_shot_master/ui/widgets/daw/overlay_header.py
  drama_shot_master/ui/widgets/daw/inspector/overlay_inspector.py
  tests/test_ui/daw/test_overlay_layout.py
  tests/test_ui/daw/test_overlay_header_smoke.py
  tests/test_ui/daw/test_overlay_inspector_smoke.py
  tests/test_ui/test_soundtrack_overlay_render_wiring.py
改:
  drama_shot_master/ui/widgets/daw/daw_track_view.py     # overlay 渲染 + 折叠 + hit-test + 动态高度
  drama_shot_master/ui/widgets/daw/inspector/__init__.py # 导出 OverlayInspector
  drama_shot_master/ui/widgets/soundtrack_editor.py      # 接线（header 堆叠 + 刷新 + 信号）
```

## 范围

- ✅ overlay 片段渲染（方案 A 折叠叠加区）+ 选中查看 + 每 lane 静音/音量。
- ❌ 框选生成（3d）、片段拖拽/缩放/双击编辑、overlay undo/redo、solo。
- 复用 3a 数据 + 3b 播放；与 4 固定轨解耦并存。
