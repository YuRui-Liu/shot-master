# 动态多轨叠加片段数据模型设计 — 子项目 #3a

> 日期：2026-05-30　分支：main
> #3「框选→生成→叠加多子轨」的第 1 块（地基）。后续 3b 播放引擎 / 3c 动态轨渲染 / 3d 框选生成交互。

## 背景与定位

把固定 4 轨配乐器升级为"在固定轨之外，叠加一层动态多子轨"。用户框选视频区间 + prompt 生成的 BGM/SFX 片段，**不覆盖**现有整段配乐，而是落到独立的叠加子轨。本块只做**数据模型**（纯逻辑、无 Qt、无播放、无渲染），是 3b/3c/3d 的地基。

与现有 ScoringSession（按镜头切的整段 BGM）/ SFXSession **并存且解耦**——独立 `overlay.json`，互不污染。

## 已锁定决策

- **独立存储**：新文件 `sound_track_agent/overlay_session.py` + `overlay.json`（与 session.json/sfx_session.json/mix.json 平级）。
- **单结果无候选**：一个 prompt 出一个音频片段，不做多 seed 选优（区别于整段 BGM 的 candidates）。
- **标准自动分轨**：新片段按 kind 找第一条无时间重叠的 lane，放不下则新建 lane。

## 数据结构

```python
@dataclass
class OverlaySegment:
    id: str                  # 唯一 id（调用方传入；通常 时间戳+随机）
    kind: str                # "bgm" | "sfx"
    lane: int                # 同 kind 内子轨序号 0,1,2…
    t_start: float
    t_end: float
    prompt: str              # 生成提示词
    audio_path: str = ""     # 生成结果路径（""=未生成）
    volume: float = 1.0      # 0.0–1.5
    enabled: bool = True
    def to_dict(self) -> dict
    @classmethod from_dict(cls, d) -> OverlaySegment


class OverlaySession:
    segments: list[OverlaySegment]

    def add(self, kind, t_start, t_end, prompt, *, seg_id) -> OverlaySegment:
        """自动分配 lane（同 kind 内第一条无重叠的 lane，否则新建）后追加并返回。"""
    def remove(self, seg_id) -> bool
    def get(self, seg_id) -> OverlaySegment | None
    def lanes_for(self, kind) -> int                # 该 kind 当前 lane 数（max_lane+1，无则 0）
    def segments_in_lane(self, kind, lane) -> list[OverlaySegment]
    def to_dict(self) -> dict
    @classmethod from_dict(cls, d) -> OverlaySession


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end

def load_overlay(work_dir) -> OverlaySession      # 读 overlay.json；缺/坏 → 空
def save_overlay(work_dir, session) -> None       # 写 overlay.json
```

### 自动分轨算法（`add`）

按 `kind` 取同类型片段，从 `lane = 0` 递增：该 lane 内所有片段都与新 `[t_start,t_end)` 无重叠 → 用此 lane；否则试下一 lane；都冲突 → `lane = lanes_for(kind)`（新建）。重叠判定 `_overlaps`（边界相接 t_end==t_start 视为不重叠）。

## 持久化

- `work_dir/overlay.json`：`{"segments": [seg.to_dict(), ...]}`。
- `load_overlay`：文件不存在或 JSON 解析失败 → 返回空 `OverlaySession`（不崩）。
- `save_overlay`：mkdir parents + 写 UTF-8 indent=2。

## 范围

- ✅ OverlaySegment / OverlaySession（add 自动分轨 / remove / get / lanes_for / segments_in_lane）+ 持久化。
- ❌ 不碰播放（3b）、渲染（3c）、生成交互（3d）、UI。
- 纯逻辑、无 Qt 依赖、全可单测。

## 测试策略

- OverlaySegment to_dict/from_dict round-trip（含默认值）。
- `add` 空 session → lane 0；时间不重叠两段(同 kind) → 同 lane 0；时间重叠 → 新 lane 1；边界相接(t_end==下一 t_start) → 同 lane；bgm 与 sfx 各自独立编号（都从 0）。
- `remove` 存在→True+移除，不存在→False；`get`。
- `lanes_for` 空→0；建到 lane 1 后→2。
- `segments_in_lane`。
- `save_overlay`/`load_overlay` round-trip；缺文件→空；坏 JSON→空。

## 文件清单

```
新增:
  sound_track_agent/overlay_session.py
  tests/test_sound_track_agent/test_overlay_session.py
```
