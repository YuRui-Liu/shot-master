# 子项目 B · 视频生成面板 UI 设计

**项目**：shot-prompt-backwards
**版本**：v0.7 子项目 B（设计阶段）
**日期**：2026-05-24
**状态**：设计评审中（待用户复核）
**关联**：视频生成模块由 A/B/C 三个子项目组成；本文档覆盖 B（核心 UI）。
**前置依赖**：v0.6 子项目 A（RunningHub API 客户端 + LTX 提交器）已合并至 main（commit cf3f7ea）。

---

## 1. 背景与目标

### 1.1 问题

A 子项目交付了纯后端库（`app/providers/runninghub.py`），具备 `submit_ltx_task(client, spec, builder) → handle.wait_for_result() → mp4` 端到端 API，但**没有任何 UI**。用户无法在桌面应用里看到/操作"视频生成"功能。

### 1.2 目标

新增"视频生成"主功能 panel，与现有「反推 / 拆图 / 拼图 / 去白边」并列为第 5 项。面板覆盖：
- 时间轴可视化（DAW 比例条样式 + 滚轮等比缩放）
- 持久图片池 + 拖入时间轴
- per-seg 编辑（local_prompt / length / guide_strength）
- 全局参数（global_prompt / frame_rate / display_mode / 分辨率 / filename_prefix）
- 音频轨可选
- 「[+ Add Text]」「[+ Add Audio]」按钮
- 提交链路（调 A 后端）+ 状态/进度/取消/结果展示
- 关闭时缓存轨道状态，下次启动恢复
- 菜单栏「设置 → RunningHub…」弹 QDialog 改 api_key / 输出目录 / 提交模式

### 1.3 非目标

- 不做提示词智能反推（C 子项目）
- 不做多任务并行窗口（D，YAGNI 已 drop）
- 不做 webhook 接收（v0.7+）
- 不做时间刻度尺 / playhead / 在面板内播放预览
- 不做撤销/重做
- 不做多选段
- 不做 UI 自动化测试（项目无 pytest-qt，靠手工冒烟）

---

## 2. 需求决策记录

| # | 决策点 | 结果 |
|---|---|---|
| 1 | 主窗口布局 | 视频生成 panel **独占整个内容区**（隐藏中栏 thumb，左栏目录保留） |
| 2 | 轨道类型 | 主轨（image+text 混排）+ 可选音频轨 |
| 3 | 时间轴交互 | **DAW 比例条**（QGraphicsScene 自绘）+ **Ctrl+滚轮等比缩放** |
| 4 | 内部布局 | 全纵向 5 层：图片池 → 时间轴 → per-seg → 全局 → 状态/提交栏 |
| 5 | 素材入池 | 持久图片池 + 拖入；`[+ Add Text]` / `[+ Add Audio]` 按钮专门加非图段 |
| 6 | per-seg 编辑器 | 始终可见，未选中时灰化 |
| 7 | 长度输入 | 跟随全局 display_mode 切换单位；内部一律存帧数 |
| 8 | 提交进度展示 | 底部状态栏 + Cancel 按钮 |
| 9 | 完成提醒 | 状态栏变 "✓ 完成: path"（可点击 → 打开文件夹） |
| 10 | 缓存时机 | 关闭面板 / 退出时自动保存到 settings.json |
| 11 | 配置 surface | 菜单栏「设置 → RunningHub…」弹 QDialog |
| 12 | 实现结构 | **分层**：1 个 model（core）+ 5 个 widget + 1 个 dialog + 1 个 panel + MainWindow 集成 |

---

## 3. 架构

### 3.1 改动文件清单

```
app/
├── core/
│   └── video_timeline_model.py            # 新增 · 数据模型（零 Qt 依赖）
├── ui/
│   ├── widgets/
│   │   ├── timeline_widget.py             # 新增 · QGraphicsScene 自绘（~400 行）
│   │   ├── image_pool_widget.py           # 新增 · 持久图片池
│   │   ├── segment_editor.py              # 新增 · per-seg 编辑表单
│   │   ├── video_global_form.py           # 新增 · 全局参数表单
│   │   └── video_status_bar.py            # 新增 · 状态栏 + 提交/取消
│   ├── dialogs/                           # 新增目录
│   │   ├── __init__.py
│   │   └── runninghub_settings_dialog.py  # 新增 · 配置弹窗
│   ├── panels/
│   │   └── video_panel.py                 # 新增 · BasePanel 子类
│   └── main_window.py                     # 修改 · FUNCS + 菜单 + 布局切换 + closeEvent
├── config.py                              # 修改 · 加 video_timeline_cache 字段
docs/superpowers/specs/
└── 2026-05-24-video-panel-design.md       # 本文档
tests/
└── test_core/                             # 新增目录
    ├── __init__.py
    └── test_video_timeline_model.py       # 新增 · 纯 model 测试
```

UI widget 不写单测（项目惯例）。

### 3.2 单元职责切片

1. **`TimelineModel`** — 纯数据 + 序列化 + `to_ltx_spec`。零 Qt 依赖。
2. **`TimelineWidget`** — QGraphicsScene 自绘双轨；外部信号契约清晰。
3. **`ImagePoolWidget`** — 持久图片池，3 种入池路径（文件对话框/当前目录/OS 拖入）。
4. **`SegmentEditor`** — per-seg 表单；`bind_to(seg)` 切换显示对象。
5. **`VideoGlobalForm`** — 全局参数；统一 `globalChanged` 信号。
6. **`VideoStatusBar`** — 状态机：idle / uploading / status / done / failed。
7. **`RunningHubSettingsDialog`** — 配置 QDialog，独立可单测（虽不测）。
8. **`VideoPanel`** — 唯一 model 写入者；编排所有 widget 信号。
9. **`MainWindow`**（修改）— FUNCS 加第 5 项；菜单加 RunningHub 设置；切换时动态布局。
10. **`Config`**（修改）— 加 `video_timeline_cache` 字段 + 持久化。

### 3.3 依赖图

```
TimelineModel (app/core, no Qt)
    ↑ 被读写
ImagePoolWidget · TimelineWidget · SegmentEditor · VideoGlobalForm · VideoStatusBar
    ↑ 装配
VideoPanel
    ↑ 装入 stack
MainWindow ← 启动 → RunningHubSettingsDialog（独立）
    ↓ 提交时
RunningHubClient / LTXTaskBuilder / submit_ltx_task / LTXTaskHandle (A 子项目)
```

---

## 4. 数据模型

### 4.1 核心 dataclasses (`app/core/video_timeline_model.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, Optional
from secrets import token_hex
import time

SegmentType = Literal["image", "text"]
DisplayMode = Literal["seconds", "frames"]


@dataclass(frozen=True)
class TimelineSegment:
    seg_id: str
    segment_type: SegmentType
    length_frames: int                       # 内部一律帧数
    local_prompt: str = ""
    image_path: Optional[Path] = None
    guide_strength: float = 1.0


@dataclass(frozen=True)
class TimelineAudio:
    audio_id: str
    audio_path: Path
    start_frame: int
    length_frames: int


@dataclass
class TimelineModel:
    segments: list[TimelineSegment] = field(default_factory=list)
    audios: list[TimelineAudio] = field(default_factory=list)
    pool: list[Path] = field(default_factory=list)

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

### 4.2 API 表面

```python
class TimelineModel:
    # 增删
    def add_image_segment(self, image_path, length_frames=24, local_prompt="") -> str
    def add_text_segment(self, length_frames=24, local_prompt="") -> str
    def add_audio(self, audio_path, start_frame=0, length_frames=24) -> str
    def remove_segment(self, seg_id) -> bool
    def remove_audio(self, audio_id) -> bool
    def reorder_segments(self, ordered_ids: list[str]) -> None

    # 更新（frozen → dataclasses.replace）
    def update_segment(self, seg_id, **fields) -> None
    def update_audio(self, audio_id, **fields) -> None

    # 图片池
    def add_to_pool(self, paths: list[Path]) -> int
    def clear_pool(self) -> None
    def pool_usage(self) -> dict[Path, int]

    # 转 A 的 spec
    def to_ltx_spec(self, output_dir: Path) -> LTXDirectorSpec

    # 序列化
    def to_dict(self) -> dict
    @classmethod
    def from_dict(cls, data: dict) -> TimelineModel

    # pre-flight 校验
    def validate(self) -> tuple[bool, str]
```

### 4.3 `to_ltx_spec` 映射

```python
def to_ltx_spec(self, output_dir: Path) -> LTXDirectorSpec:
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
        use_custom_audio=len(self.audios) > 0,   # 自动推导
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

### 4.4 `validate()` 规则

- segments 非空
- 每段 `length_frames >= 1`
- image 段 `image_path != None` 且文件存在
- audio 段 `audio_path` 文件存在
- `1 <= frame_rate <= 120`

失败抛错（返 `(False, msg)`）由 panel 层在提交前用，与 A 的 `LTXTaskBuilder._validate` 解耦（两层独立校验）。

### 4.5 缓存 schema (`settings.json`)

```jsonc
{
  "video_timeline_cache": {
    "segments": [{seg_id, segment_type, length_frames, local_prompt,
                  image_path, guide_strength}, ...],
    "audios": [{audio_id, audio_path, start_frame, length_frames}, ...],
    "pool": ["<abs path>", ...],
    "global_prompt": "...",
    "use_global_prompt": true,
    "frame_rate": 24,
    "display_mode": "seconds",
    "resolution_preset": "...",
    "use_custom_resolution": false,
    "custom_width": 1024,
    "custom_height": 1024,
    "filename_prefix": "spb_video"
  }
}
```

### 4.6 `Config` 扩展

```python
@dataclass
class Config:
    # ... 现有字段
    video_timeline_cache: dict = field(default_factory=dict)
```

`update_settings` 白名单 + `load_config` 读取循环各加一行。

### 4.7 关键设计取舍

- **frozen `TimelineSegment` / `TimelineAudio`** + 容器 `TimelineModel` 可变：与 v0.5/v0.6 风格一致；更新走 `dataclasses.replace`。
- **内部一律存帧数**：`display_mode` 只影响 UI 显示，切换 mode 不动数据。
- **`use_custom_audio` 自动推导**：audios 非空 → True。UI 不暴露开关。
- **`from_dict` 容错**：stale 字段忽略、缺字段走默认。
- **不进 cache 的字段**：当前选中段 id（UI 状态）、widget zoom level（视图状态）。

---

## 5. TimelineWidget 设计

### 5.1 类结构

```python
class TimelineWidget(QGraphicsView): ...
class TimelineScene(QGraphicsScene): ...
class SegmentItem(QGraphicsItem): ...
class AudioItem(QGraphicsItem): ...
```

### 5.2 布局常量

```python
SEG_LANE_Y = 0
SEG_HEIGHT = 60
LANE_GAP = 10
AUDIO_LANE_Y = 70
AUDIO_HEIGHT = 30
RESIZE_HANDLE_W = 6
DEFAULT_PX_PER_FRAME = 5.0
MIN_PX_PER_FRAME = 0.5
MAX_PX_PER_FRAME = 50.0
```

- 主轨段 i 的 `x = sum(s.length for s in segments[:i]) * pixels_per_frame`
- 音频段 j 的 `x = audios[j].start_frame * pixels_per_frame`（绝对帧定位）

### 5.3 外部信号契约

```python
class TimelineWidget(QGraphicsView):
    segmentSelected = Signal(str)                # seg_id（None 时 emit ""）
    segmentChanged = Signal(str, int)            # (seg_id, new_length_frames)
    segmentReordered = Signal(list)              # 新顺序 [seg_id, ...]
    segmentDoubleClicked = Signal(str)
    segmentDeleteRequested = Signal(str)
    audioChanged = Signal(str, int, int)         # (audio_id, new_start_frame, new_length_frames)
    audioDeleteRequested = Signal(str)
    imageDroppedAt = Signal(object, int)         # (Path, insert_index)
    zoomChanged = Signal(float)                  # new pixels_per_frame
```

**TimelineWidget 不修改 model**——所有 model 写入由 VideoPanel 接收信号后做。消除双写。

### 5.4 鼠标交互状态机

| 触发 | 模式判定 | 行为 |
|---|---|---|
| Press on SegmentItem 右沿 6px | RESIZE | 实时改 item width（不动 model）；release → emit segmentChanged(seg_id, new_length) |
| Press 段中心 + 拖出 8px | MOVE | 启动 QDrag with MIME `application/x-spb-seg-id`；drop 后 emit segmentReordered(ordered_ids) |
| Press 段中心 + 原位释放 | SELECT | emit segmentSelected(seg_id) |
| 双击段 | — | emit segmentDoubleClicked(seg_id) |
| 选中段 + Delete 键 | — | emit segmentDeleteRequested(seg_id) |
| 拖 mime `x-spb-image-path` 进 view | — | dropEvent 算 insert_index → emit imageDroppedAt(path, idx) |

### 5.5 滚轮缩放

```python
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

Ctrl+wheel 等比缩放；纯 wheel 横向滚（默认行为）。

### 5.6 `SegmentItem.paint` 渲染层次

1. 背景色（image: `#3a4a5f` 蓝灰；text: `#4a3a3a` 红灰；选中加 `#ffaa00` 边）
2. 缩略图（仅 image 段，QPixmapCache 缓存，40×30 px）
3. length badge（display_mode=frames → `"33f"`；=seconds → `f"{frames/fr:.2f}s"`）
4. prompt 前 16 字符

### 5.7 `AudioItem` 关键差异

- 颜色 `#3a4a3a`（绿灰）
- 整体拖动改 `start_frame`；右沿拖动改 `length`
- 左沿拖动 v0.7+ 再做（一期简化）

### 5.8 `TimelineWidget.rebuild()`

```python
def rebuild(self):
    selected_id = self._current_selected_id()
    self.scene().clear()
    x = 0
    for seg in self.model.segments:
        w = seg.length_frames * self.pixels_per_frame
        item = SegmentItem(seg, x, w,
                           self.model.display_mode, self.model.frame_rate)
        if seg.seg_id == selected_id:
            item.setSelected(True)
        self.scene().addItem(item)
        x += w
    for audio in self.model.audios:
        ax = audio.start_frame * self.pixels_per_frame
        aw = audio.length_frames * self.pixels_per_frame
        self.scene().addItem(
            AudioItem(audio, ax, aw,
                      self.model.display_mode, self.model.frame_rate))
    total_w = max(x, 200) + 100
    self.scene().setSceneRect(0, 0, total_w, AUDIO_LANE_Y + AUDIO_HEIGHT + 20)
    if not self.model.segments and not self.model.audios:
        self._draw_empty_hint()
```

全清重建（30-50 段 <16ms，足够）。

### 5.9 关键设计取舍

- **`TimelineWidget` 不改 model**：所有 model 写入由 VideoPanel 完成。
- **rebuild 全清 vs 增量**：选全清。30-50 段下 <16ms。v0.7+ 可优化为增量 diff。
- **resize 实时视觉，release 改 model**：避免高频 IO。
- **不画时间刻度尺 / playhead / 播放预览**：scope cut，v0.7+。
- **多选不做**：v0.6 单选。

---

## 6. 周边 widgets

### 6.1 `ImagePoolWidget`

`QListWidget` IconMode 横向 + drag enabled。

**toolbar（在父容器里）：** `[+ 批量导入图片]` `[+ 当前目录全部]` `[🗑 清空池]`

**信号：**
```python
imagesAdded = Signal(list)        # list[Path]
clearRequested = Signal()
```

**已用 / 未用着色：**
```python
def refresh_usage(self, usage: dict[Path, int]):
    for i in range(self.count()):
        item = self.item(i)
        used = usage.get(item.data(Qt.UserRole), 0) > 0
        item.setForeground(QBrush(Qt.white if used else Qt.gray))
```

**Drag 启动：** mime type `application/x-spb-image-path`，QDrag.setPixmap(64×48 thumb)。

**接受 OS 文件拖入：** dragEnter/drop 检测 mime.hasUrls 过滤 `.png/.jpg/.jpeg/.webp`。

### 6.2 `SegmentEditor`

`QGroupBox`。三控件：`local_prompt`（QPlainTextEdit）+ `length_spin`（QSpinBox 1-9999）+ `guide_spin`（QDoubleSpinBox 0.0-1.0）。

**信号：**
```python
segmentEdited = Signal(str, str, object)   # (seg_id, field, value)
```

**API：**
```python
def bind_to(self, seg: TimelineSegment | None,
            display_mode: str, frame_rate: int) -> None:
    """seg=None → 全部 setEnabled(False)。"""
```

**length 显示策略**（统一存帧数，suffix 显示秒预览）：
```python
if display_mode == "frames":
    spin.setSuffix(" f"); spin.setValue(frames)
else:
    seconds = frames / frame_rate
    spin.setSuffix(f" f (≈{seconds:.2f}s)"); spin.setValue(frames)
```

**`_suspend_signals` 标志**：bind_to 时设 True，避免 setValue 触发 emit 循环。

### 6.3 `VideoGlobalForm`

`QGroupBox`。控件：
- `global_prompt` QPlainTextEdit + `use_global_prompt` QCheckBox
- `frame_rate` QSpinBox 1-120
- `display_mode` 2 个 QRadioButton（秒 / 帧）
- `resolution_preset` QComboBox + `custom_width` / `custom_height` QSpinBox（仅 "自定义..." 时可见）
- `filename_prefix` QLineEdit

**信号：单一 `globalChanged()`**——所有字段任意变化触发；VideoPanel 收到后调 `get_state()` 一次性写回 model。

**API：**
```python
def get_state(self) -> dict
def set_state(self, model: TimelineModel) -> None
```

### 6.4 `VideoStatusBar`

横向 `QWidget`：左 QLabel（rich text，含 `<a>` 链接）+ 中 QProgressBar（可选）+ 右 `[取消]` `[🎬 提交]` 按钮。

**信号：**
```python
submitRequested = Signal()
cancelRequested = Signal()
openFolderRequested = Signal(object)   # Path
```

**状态机 API：**
```python
def set_idle(self) -> None
def set_uploading(self, done: int, total: int, current_name: str) -> None
def set_status(self, status: str) -> None
def set_done(self, mp4_path: Path) -> None       # rich text 含 <a href="open:..."> 可点击
def set_failed(self, reason: str) -> None
```

**链接处理：** `_on_link_clicked` 解析 `open:<path>` → emit `openFolderRequested(Path.parent)`。

---

## 7. `RunningHubSettingsDialog`

`QDialog` 模态。表单（QFormLayout）：

| 字段 | 控件 | 对应 cfg 字段 |
|---|---|---|
| API Key | QLineEdit Password + 👁 按钮 | `runninghub_api_key` |
| Base URL | QLineEdit | `runninghub_base_url` |
| 视频输出目录 | QLineEdit + 浏览 | `video_output_dir` |
| 提交模式 | ● Inline ○ ID（QButtonGroup） | `runninghub_submit_mode` |
| Workflow ID | QLineEdit（仅 ID 模式 enabled） | `runninghub_workflow_id` |
| 工作流模板 | QCheckBox「使用内置」+ QLineEdit + 浏览 | `runninghub_template_path` |
| 测试连接 | 「🔌 测试连接」按钮 + 结果 QLabel | — |

**底部：** `[取消]` `[保存]`

### 7.1 测试连接策略

```python
def _on_test_connection(self):
    api_key = self.api_key_edit.text().strip()
    if not api_key:
        return self._show_result(False, "未填 API Key")
    self._show_result(None, "测试中…")
    def task():
        try:
            with RunningHubClient(api_key,
                                   base_url=self.base_url_edit.text().strip()) as c:
                c.query_task("__spb_probe__")
            return True, "✓ 鉴权通过"
        except RunningHubUnavailable as e:
            return False, f"✗ 不可达：{e}"
    self._worker = FunctionWorker(task)
    self._worker.finished_with_result.connect(
        lambda r: self._show_result(*r))
    self._worker.start()
```

走 `FunctionWorker` worker 线程，不阻塞 UI。`query_task("__spb_probe__")` 任意不存在的 task_id 触发 V2 API；如 Key 错走 Unavailable，否则返回 `{status:"UNKNOWN",...}` 不抛错——"不抛即通过"。

### 7.2 保存逻辑

```python
def accept(self):
    if mode == "id" and not workflow_id:
        return QMessageBox.warning(self, "校验失败",
                                    "提交模式 = ID 时必须填 workflow_id")
    self.cfg.update_settings(
        runninghub_api_key=...,
        runninghub_base_url=...,
        runninghub_submit_mode=...,
        runninghub_workflow_id=...,
        runninghub_template_path=...,
        video_output_dir=...,
    )
    super().accept()
```

---

## 8. `VideoPanel` 装配 + MainWindow 集成

### 8.1 VideoPanel 5 层布局

```python
class VideoPanel(BasePanel):
    def _build_ui(self):
        root = QVBoxLayout(self)
        # 1. 图片池 + toolbar（fixed 140 px）
        # 2. timeline（stretch=3）
        # 3. seg_editor（fixed 140 px）
        # 4. global_form（fixed 180 px）
        # 5. status_bar_widget
```

### 8.2 信号路由表（唯一真值源）

| 来源 | 信号 | VideoPanel slot | 写入 model | 后续 |
|---|---|---|---|---|
| ImagePool | imagesAdded | `_on_pool_images_added` | `add_to_pool` | refresh pool |
| Timeline | imageDroppedAt | `_on_image_dropped` | `add_image_segment` + reorder | `rebuild` + refresh pool |
| Timeline | segmentSelected | `_on_segment_selected` | — | `seg_editor.bind_to` |
| Timeline | segmentChanged(id,len) | `_on_segment_resized` | `update_segment(length_frames)` | `rebuild` |
| Timeline | segmentReordered(ids) | `_on_segments_reordered` | `reorder_segments` | `rebuild` |
| Timeline | segmentDeleteRequested | `_on_segment_delete` | `remove_segment` | `rebuild` + clear sel |
| Timeline | audioChanged(id,s,len) | `_on_audio_changed` | `update_audio` | `rebuild` |
| Timeline | audioDeleteRequested | `_on_audio_delete` | `remove_audio` | `rebuild` |
| SegmentEditor | segmentEdited(id,field,val) | `_on_segment_edited` | `update_segment(**{field:val})` | `rebuild` |
| GlobalForm | globalChanged | `_on_global_changed` | 写所有全局字段 | `rebuild` + `seg_editor.bind_to(cur,new_mode,new_fr)` |
| Toolbar | btn_add_text clicked | `_on_add_text` | `add_text_segment` | `rebuild` |
| Toolbar | btn_add_audio clicked | `_on_add_audio` | QFileDialog → `add_audio` | `rebuild` |
| StatusBar | submitRequested | `_on_submit` | — | 启动 worker |
| StatusBar | cancelRequested | `_on_cancel` | — | 置 cancel_flag |
| StatusBar | openFolderRequested | `_on_open_folder` | — | QDesktopServices |

**唯一原则**：所有 model 写入只在 VideoPanel；widget 之间不互通。

### 8.3 frame_rate 变化的级联

```
GlobalForm.fr_spin.valueChanged
  → VideoGlobalForm.globalChanged.emit()
  → VideoPanel._on_global_changed:
      model.frame_rate = new_fr
      timeline.rebuild()                      # 卡片宽度 / badge 重算
      cur = find_selected_seg()
      seg_editor.bind_to(cur, mode, new_fr)   # length suffix 重算
```

### 8.4 提交链路

```python
def _on_submit(self):
    ok, msg = self.model.validate()
    if not ok:
        return QMessageBox.warning(self, "校验失败", msg)
    try:
        api_key = resolve_api_key(self.cfg)
        tpl = resolve_template_path(self.cfg)
        out = resolve_video_output_dir(self.cfg, self.state.output_dir)
    except (RunningHubUnavailable, RunningHubInvalidSpec) as e:
        return QMessageBox.warning(self, "配置缺失",
            f"{e}\n\n请在「设置 → RunningHub…」补充。")
    spec = self.model.to_ltx_spec(out)
    self._cancel_flag["v"] = False

    def task():
        with RunningHubClient(api_key,
                               base_url=self.cfg.runninghub_base_url) as client:
            builder = LTXTaskBuilder(tpl)
            handle = submit_ltx_task(
                client, spec, builder,
                mode=self.cfg.runninghub_submit_mode,
                workflow_id=self.cfg.runninghub_workflow_id,
                upload_progress_cb=lambda d,t,p: self._post(
                    "upload", (d,t,p.name)),
            )
            return handle.wait_for_result(
                timeout=1800, poll_interval=8,
                progress_cb=lambda s: self._post("status", s),
                cancel_check=lambda: self._cancel_flag["v"],
            )

    self.status_bar_widget.set_status("提交中…")
    self._worker = FunctionWorker(task)
    self._worker.finished_with_result.connect(self._on_submit_done)
    self._worker.failed.connect(self._on_submit_failed)
    self._worker.start()

def _post(self, kind: str, payload):
    """worker 线程往 UI 调度小回调（QTimer.singleShot marshal 到 UI 线程）。"""
    QTimer.singleShot(0, lambda: self._apply_status(kind, payload))
```

### 8.5 缓存

```python
def save_cache(self):
    self.cfg.update_settings(video_timeline_cache=self.model.to_dict())

def _restore_model(self) -> TimelineModel:
    data = getattr(self.cfg, "video_timeline_cache", None) or {}
    if data:
        try:
            return TimelineModel.from_dict(data)
        except Exception as e:
            log.warning("cache 解析失败，走空 model: %s", e)
    return TimelineModel()
```

### 8.6 MainWindow 修改

```python
FUNCS = [("反推", "inference"), ("拆图", "split"),
         ("拼图", "combine"), ("去白边", "trim"),
         ("视频生成", "video_gen")]    # 第 5 项

class MainWindow(QMainWindow):
    def _build_ui(self):
        # ... 现有 splitter
        # 加菜单栏
        menu = self.menuBar()
        settings_menu = menu.addMenu("设置(&S)")
        act = QAction("RunningHub 配置…", self)
        act.triggered.connect(self._open_runninghub_settings)
        settings_menu.addAction(act)
        # ... panel 注册循环加 VideoPanel

    def _on_func_changed(self, idx: int):
        # ... 现有逻辑
        is_video = (FUNCS[idx][1] == "video_gen")
        self.thumb.setVisible(not is_video)
        self.btn_preview.setVisible(not is_video)
        self.btn_exec.setVisible(not is_video)
        self.exec_hint.setVisible(not is_video)
        if is_video:
            self.splitter.setSizes([180, 0, 1180])

    def _open_runninghub_settings(self):
        RunningHubSettingsDialog(self.cfg, parent=self).exec()

    def closeEvent(self, e):
        for i in range(self.stack.count()):
            w = self.stack.widget(i)
            if isinstance(w, VideoPanel):
                w.save_cache()
                break
        # ... 现有保存
        super().closeEvent(e)
```

### 8.7 关键设计取舍

- **VideoPanel 是唯一 model 写入者**：所有 widget 信号 → slot → model → rebuild。
- **`segmentChanged(seg_id, new_length)` 携带新值**：避免 VideoPanel 反查 widget state。
- **Worker 线程跑全部 RunningHub IO**：client + builder + handle 全在 worker 里；UI 零阻塞。
- **`_cancel_flag` 用 dict 而非 bool**：可变容器跨闭包共享。
- **`_post` 走 QTimer.singleShot(0, ...)`**：marshal worker 线程 callback 到 UI 线程。
- **提交期间不禁 timeline / 编辑器**：用户可继续编辑（下次提交用最新 model）；只 disabled 提交按钮。
- **`closeEvent` 遍历 stack 找 VideoPanel**：FUNCS 重排时不破。
- **video_gen 切换时隐藏中栏 + 底部 preview/execute**：视觉确认"独占内容区"。左栏保留（视频输出目录等仍可用）。

---

## 9. 错误处理矩阵

| 错误类别 | 行为 | 来源 |
|---|---|---|
| `model.validate()` 失败 | QMessageBox.warning，不进 worker | submit 入口 |
| `resolve_api_key` 抛 RunningHubUnavailable | QMessageBox 提示「请在设置中配置」 | submit 入口 |
| `resolve_template_path` 抛 RunningHubInvalidSpec | 同上 | submit 入口 |
| `submit_ltx_task` 抛 RunningHubUploadError | StatusBar.set_failed | worker.failed 信号 |
| `wait_for_result` 抛 RunningHubTaskFailed | StatusBar.set_failed | worker.failed |
| 任意未捕获异常 | StatusBar.set_failed("内部错误: ...") | worker.failed |
| cancel_check 触发 | StatusBar.set_failed("cancelled") | wait_for_result 内 |
| timeout (1800s) 触发 | StatusBar.set_failed("timeout ...") | wait_for_result 内 |
| widget 内部 setValue 触发 emit 死循环 | `_suspend_signals` 标志拦截 | SegmentEditor / GlobalForm |
| cache 反序列化失败 | log.warning + 走空 model | `_restore_model` |
| settings.json 编码错 / JSON 错 | 现有 Config 已处理（吞 UnicodeDecodeError / JSONDecodeError） | load_config |

---

## 10. 测试策略

### 10.1 自动测试：`tests/test_core/test_video_timeline_model.py`

约 22 个用例，~350 行。覆盖：

- dataclass defaults
- add/remove/update/reorder 各 1-2 用例
- `pool_usage` 计数
- `to_ltx_spec` 字段映射 + `use_custom_audio` 自动推导 + `output_dir` 透传
- `to_dict` / `from_dict` round-trip
- `from_dict` 容错（缺字段、stale image_path、错误类型）
- `validate` 各失败路径（空段 / length<1 / image 无 path / 文件不存在 / fr 越界）

### 10.2 不自动测的

- TimelineWidget（自绘 + 鼠标交互）—— 手工冒烟
- ImagePool / SegmentEditor / VideoGlobalForm / VideoStatusBar —— 手工冒烟
- RunningHubSettingsDialog —— 手工冒烟
- VideoPanel 信号编排 —— 集成层，手工冒烟
- MainWindow 切 panel 时布局切换 —— 手工冒烟
- A 的 `submit_ltx_task` / handle —— 已在 A 阶段测过 27 用例

### 10.3 手工冒烟清单（12 项 · 用户跑）

1. 启动 → 切「视频生成」→ 中栏 thumb 隐藏，VideoPanel 占满；空时间轴
2. 批量导入 5 张图 → 图片池横排显示，全标"未用"
3. 拖一张图到时间轴 → 出现 1 个段（24f），图片变"已用"
4. 拖 3 张图，单击第 2 段 → seg_editor 启用 + 字段填入
5. 拖第 3 段右沿到加倍宽度 → 实时变宽，松手后 length 翻倍
6. Ctrl+滚轮 → 时间轴等比缩放，所有段+badge 同步；纯 wheel 横向滚
7. 「+ Add Text」→ 末尾出现红灰文本段
8. 「+ Add Audio」→ 音频轨绿灰段，拖右沿改长度
9. 「设置 → RunningHub…」→ 测试连接 ✓ 鉴权通过；保存关闭
10. 「🎬 提交」→ 上传 → 提交中 → QUEUED → RUNNING → ✓ 完成: path；点路径打开 explorer
11. 关闭重启 → 自动恢复段/池/参数
12. 重新提交，途中点「取消」→ 状态栏"取消中…"，几秒后 set_failed("cancelled")

### 10.4 总测试数

- v0.5 split-resample 基线: 102
- v0.6 RunningHub: +98 + 配置 +9 = +107（实际 209 total）
- v0.7 B: +22 → 预期 **231**

---

## 11. 验收标准

B 子项目完成的标志：

- [ ] `app/core/video_timeline_model.py` 含 3 个 dataclass + ~12 个 method + 序列化
- [ ] 5 个 widget 文件 + 1 个 dialog 文件 + 1 个 panel 文件全部存在
- [ ] `app/ui/main_window.py` FUNCS 加第 5 项 + 菜单栏「设置 → RunningHub…」+ 切换时布局切换
- [ ] `app/config.py` 加 `video_timeline_cache` 字段 + 持久化
- [ ] 22 个 TimelineModel 单测全过 (231 total)
- [ ] 12 项手工冒烟全过
- [ ] 真实 RunningHub API 端到端跑通至少 1 次（同时验证 A 的端到端，与子项目 A Task 12 合并）

---

## 12. 风险与开放问题

| 风险 | 影响 | 应对 |
|---|---|---|
| QGraphicsScene 自绘性能（30+ 段 + 频繁 resize） | 卡顿 | 测试 ≤50 段下 rebuild 时间；超阈值再做增量 diff |
| QPixmapCache 命中失败 / 缓存爆 | 每次 paint 重新解 PNG | key 含完整路径，cache 默认 10MB 上限够用；vide 拷贝大文件时清空 |
| display_mode 切换中段编辑器 length spin 显示不刷新 | 视觉跟不上 | `_on_global_changed` 强制调 `seg_editor.bind_to(cur, mode, fr)` |
| `from_dict` 时 image_path 指向已删除文件 | 段保留但提交时校验失败 | validate 阶段拦截，提示用户 |
| MainWindow 现有 closeEvent 已有 last_dir 保存 | 与 VideoPanel.save_cache 冲突 | 在 super().closeEvent 之前调，顺序明确 |
| QGraphicsView 在大缩放下渲染性能（pixels_per_frame=50） | 单段宽度极大，绘制慢 | clamp 上限 50；横向滚动条性能 Qt 自管 |
| 用户拖图到空时间轴 | drop_x 计算的 insert_index = 0，OK | 已覆盖 |
| audio 段 start_frame 与主轨段时长不匹配 | 用户疑惑 | v0.6 不强制对齐；v0.7 可加吸附 |
| LTX backend 对 segment_type="text" 的实际行为未验证 | 文本段提交失败 | 冒烟阶段验证；如有 issue 则 v0.6.1 移除 text 段或降级处理 |

**开放问题（v0.7+）：**

- 顶部时间刻度尺 / playhead
- 段卡上 mini-preview（hover 显示完整 prompt）
- 段拷贝复用（右键菜单 "复制到末尾"）
- 多选段批量操作
- 撤销/重做（QUndoStack）
- ComfyUI 节点版（与 Web App 并存）

---

## 13. 下一步

1. 用户复核本设计文档
2. 通过后调用 `superpowers:writing-plans` 生成实现计划
3. 实现计划按 milestone 切分 → 编码 → 测试 → 集成
4. B 完成后，子项目 C（提示词智能优化）启动 brainstorming

---

**文档负责人**：项目作者
**最近更新**：2026-05-24
