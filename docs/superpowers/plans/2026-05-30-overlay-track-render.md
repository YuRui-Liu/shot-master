# 实施计划 — 动态叠加子轨渲染 #3c

> Spec：`docs/superpowers/specs/2026-05-30-overlay-track-render-design.md`
> 布局确认：`docs/explorer/3c-overlay-track-layout-confirm.html`（方案 A）
> 方法：TDD（先测后码）。Task 1–4 文件互不重叠可并行，Task 5 整合接线。

## 依赖图

```
T1 overlay_layout (纯函数)  ─┐
T2 OverlayInspector (纯widget)─┼─▶ T5 editor 接线（整合）
T3 OverlayHeaderSection ─────┤
T4 DawTrackView 扩展 ────────┘
T1 是 T3/T4 的依赖（lane 分组），但 T3/T4 可各自先写自己的测试桩并行推进。
```

## Task 1 — overlay_layout 纯函数

**新增** `drama_shot_master/ui/widgets/daw/overlay_layout.py`、`tests/test_ui/daw/test_overlay_layout.py`

- RED：写 `test_overlay_layout.py`：
  - 空 → `overlay_rows([], base_y=0, collapsed=False) == ([], 0)`；`lane_count([])==0`。
  - 构造假 seg（具 `.kind/.lane/.t_start`，可用 3a `OverlaySegment` 或 SimpleNamespace）：2 bgm lane(0,1)+1 sfx lane(0) → 3 行，顺序 [bgm0,bgm1,sfx0]，y= `_OV_HEAD_H, _OV_HEAD_H+28, _OV_HEAD_H+56`（base_y=0），region_h=`_OV_HEAD_H+3*_OV_LANE_H`。
  - collapsed=True 非空 → `([], _OV_HEAD_H)`。
  - 同 (kind,lane) 多段 → 聚一行，`row.segments` 按 t_start 升序。
  - `lanes_of(segs,"bgm")==2`、`lanes_of(segs,"sfx")==1`。
- GREEN：实现 `OverlayRow` dataclass + `overlay_rows` / `lane_count` / `lanes_of` + 常量 `_OV_LANE_H=28 / _OV_HEAD_H=18 / _OV_KIND_ORDER=["bgm","sfx"]`。
- 验证：`pytest tests/test_ui/daw/test_overlay_layout.py -q`。

## Task 2 — OverlayInspector

**新增** `drama_shot_master/ui/widgets/daw/inspector/overlay_inspector.py`、`tests/test_ui/daw/test_overlay_inspector_smoke.py`
**改** `daw/inspector/__init__.py`（导出 `OverlayInspector`）

- RED：smoke 测试（`qtbot`/`QApplication` fixture，参考 `test_inspector_smoke.py`）：
  - 构造 `OverlayInspector()`；`set_segment(seg)`（seg：kind=bgm,lane=0,t_start=5,t_end=10,prompt="紧张配乐",volume=0.8,enabled=True,audio_path="x.mp3"）→ 标题含 "BGM"、时间 label 含 "5"、prompt label 文本含 "紧张配乐"、音频显示“已生成”。
  - `audio_path=""` → 显示“未生成”。
- GREEN：纯只读 `QWidget`，`_build_ui` + `set_segment`（QLabel 字段，wrap prompt）。参考 `sfx_inspector.py` 结构但去掉所有编辑控件。
- 验证：`pytest tests/test_ui/daw/test_overlay_inspector_smoke.py -q`。

## Task 3 — OverlayHeaderSection

**新增** `drama_shot_master/ui/widgets/daw/overlay_header.py`、`tests/test_ui/daw/test_overlay_header_smoke.py`
依赖 Task 1（`overlay_rows`/`lanes_of` 做分组）。

- RED：smoke：
  - `set_overlay(2bgm+1sfx, collapsed=False)` → 3 个 lane 行（`self._lane_rows` 长度 3）+ 折叠头可见。
  - `collapsed=True` → lane 行 hidden，仅折叠头。
  - 空 segments → 整体 `isVisible()` False。
  - 用 `QSignalSpy` 或回调：点折叠头 → `collapseToggled`；某 lane M.click → `laneMuteToggled("bgm",0,True)`；slider.setValue → `laneVolumeChanged("bgm",0,v)`。
  - 初值聚合：lane 内有 `enabled=False` 段 → 该行 M 初始 checked；音量取首段 volume。
- GREEN：`OverlayHeaderSection(QWidget)`，固定宽 130，QVBoxLayout。`set_overlay` 清空重建：折叠头按钮行 + 每 lane 行（标签 `f"{kind}·{lane}"` + M(`_MUTE_QSS`) + QSlider 0–150）。信号按 spec。
- 验证：`pytest tests/test_ui/daw/test_overlay_header_smoke.py -q`。

## Task 4 — DawTrackView 扩展

**改** `drama_shot_master/ui/widgets/daw/daw_track_view.py`
依赖 Task 1。新测试加进 `tests/test_ui/daw/test_daw_track_view_smoke.py`（或新文件 `test_daw_track_view_overlay.py`）。

- RED：
  - `set_overlay([2bgm+1sfx], collapsed=False)` 后 `minimumHeight()` > 空 overlay 时；`collapsed=True` 后高度回落（只含折叠头）；`set_overlay([], ...)` 高度 == 纯固定区基线。
  - `_overlay_seg_at(x,y)`：给定一个 overlay 片段（已知 t/lane → 反算屏幕 x,y），命中返回 seg.id；折叠头 y / 空白返回 None。
  - handler 级：模拟点折叠头 → `overlayCollapseToggled` 发；点片段 → `overlaySegmentClicked(id, mod)` 发。
- GREEN：
  - 把 `_MIN_H` 拆为 `_FIXED_H`（固定区）；加 `_overlay_segs/_overlay_collapsed`；`set_overlay` 调用 `overlay_rows` 重算 `setMinimumHeight(_FIXED_H + region_h)`。
  - 新增信号 `overlayCollapseToggled` / `overlaySegmentClicked(str, object)`。
  - `paintEvent` 末尾绘叠加区（折叠头 + lane 背景 + 片段块，斜纹 `Qt.BDiagPattern` 区分；选中描边）。playhead 改 `self.height()` 全高。
  - `mousePressEvent` 开头插 overlay 命中分支（y≥`_FIXED_H`）：折叠头→emit toggled+return；片段→emit clicked+return；空白叠加区→return（吞掉）。
  - 抽 `_overlay_seg_at` 纯逻辑便于测。
- 验证：`pytest tests/test_ui/daw/ -q`（含原有 smoke 不回归）。

## Task 5 — SoundtrackEditor 接线（整合）

**改** `drama_shot_master/ui/widgets/soundtrack_editor.py`
**新增** `tests/test_ui/test_soundtrack_overlay_render_wiring.py`
依赖 Task 1–4 全绿。

- RED：接线 smoke（mock 重组件 / tmp work_dir）：
  - 构造 editor（已有测试夹具风格），`_refresh_overlay_view()` 把 `_overlay_session.segments` 推给 `_track_view.set_overlay` 与 `_overlay_header.set_overlay`（mock/spy 验证）。
  - overlay 片段点击 handler → `_selection` 被 clear；`_current_inspector` 是 `OverlayInspector`。
  - lane mute handler(`"bgm",0,True`) → 该 lane 全段 `enabled=False` + `save_overlay` 被调（tmp 落盘可断言文件）+ `_mix_engine.set_segments` 被调。
  - overlay 空 → `_refresh_overlay_view` 不抛。
  - 固定轨选中后 `_overlay_sel_id` 被清（互斥）。
- GREEN：
  - header 列容器：`TrackHeaderColumn` + `OverlayHeaderSection` 垂直堆叠成一个 QWidget 放进 `tv_row` 左侧。
  - 加 `_overlay_collapsed=False`、`_overlay_sel_id=None`。
  - `_refresh_overlay_view()`；在 `_refresh_track_view()` 末尾调它。
  - 连 `overlayCollapseToggled`/`collapseToggled`、`overlaySegmentClicked`、`laneMuteToggled`、`laneVolumeChanged`（按 spec 接线：改段→save_overlay→mix_engine.set_segments→刷新）。
  - `_refresh_inspector`：固定选区存在时清 `_overlay_sel_id`。
- 验证：
  - `pytest tests/test_ui/test_soundtrack_overlay_render_wiring.py -q`
  - 回归：`pytest tests/test_ui/ -q`（确保固定轨、minimap、inspector 不回归）。

## 收尾

- 全量 `pytest tests/test_ui/daw tests/test_ui/test_soundtrack_overlay_render_wiring.py -q` 绿。
- 提交：spec+plan 一次 `docs(...)`；T1–T5 各一次 `feat(soundtrack): ... 子项目#3c-N`，遵循现有 commit 风格。
- 手动确认：`docs/explorer/3c-overlay-track-layout-confirm.html` 视觉与实现一致（折叠头、斜纹、lane 头控件）。
```
