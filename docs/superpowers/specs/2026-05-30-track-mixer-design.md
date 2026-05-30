# 轨级混音控件设计 — 子项目 #2

> 日期：2026-05-30　分支：main
> 5 个对标 ACE 子项目的第 2 个。#1 AI 对话面板已完成。

## 背景与定位

对标 ACE / 剪映 的左侧轨道头混音控件。当前 DawTrackView 左侧 60px 是 paintEvent 画的轨道名文字，无任何交互。本子项目把它换成真控件列：每条有音频的轨（原声/BGM/SFX）一行 = 名称 + M(静音) + S(独奏) + 音量条，实时作用于叠加播放（OverlayMixer 的 bgm/sfx + 视频原声）。

## 已锁定决策

- 控件：**M(静音) / S(独奏) / 音量（0–150%）**；**砍声像 pan**（QAudioOutput 不支持，短剧价值低）。
- 覆盖轨：**原声(视频音轨) / BGM / SFX** 三条有实际音频；**对白轨**目前无独立音频（混在视频原声里）→ 只读占位，不给控件。
- 布局：**方案 A** 左侧轨道头列（替换 60px 画字标签为 ~130px 真控件列，垂直与波形轨对齐）。
- 独奏：多轨可同时 S；**有任一轨 S 时只听 S 轨**（其余静音）；无 S 时按各自 M。
- 持久化：每轨 mute/solo/volume 存 `work_dir/mix.json`，重开还在。
- 实时：所有改动立刻作用于当前叠加播放，无需重生成。

## 数据模型

新增 `drama_shot_master/ui/widgets/daw/track_mix.py`：

```python
TRACKS = ("video", "bgm", "sfx")          # 有音频的三轨（dialogue 不含）

@dataclass
class _TrackState:
    muted: bool = False
    soloed: bool = False
    volume: float = 1.0                    # 0.0–1.5

class TrackMixState:
    """三轨 mute/solo/volume + 独奏解算 + JSON 持久化。纯逻辑，可单测。"""
    def __init__(self): self._st = {t: _TrackState() for t in TRACKS}
    def set_muted(self, track, on) / is_muted(track)
    def set_soloed(self, track, on) / is_soloed(track)
    def set_volume(self, track, v)  / volume(track)     # clamp 0–1.5
    def audible(self, track) -> bool:
        """有效可听：not muted 且（无任何 solo 或本轨 solo）。"""
    def effective_volume(self, track) -> float:          # audible? volume : 0
    def to_dict(self) / from_dict(cls, d)                # 持久化
```

## 持久化

新增 `drama_shot_master/ui/widgets/daw/track_mix.py` 内 or facade 小工具：
- `load_mix(work_dir) -> TrackMixState`（读 `work_dir/mix.json`，缺/坏 → 默认全可听）
- `save_mix(work_dir, state)`（写 `work_dir/mix.json`）
- 独立于 session.json，因为混音覆盖 video/sfx 不只 BGM。

## UI：TrackHeaderColumn

新增 `drama_shot_master/ui/widgets/daw/track_header_column.py`：

```python
class TrackHeaderColumn(QWidget):
    muteToggled = Signal(str, bool)      # (track, on)
    soloToggled = Signal(str, bool)
    volumeChanged = Signal(str, float)   # (track, 0–1.5)

    def __init__(self, parent=None)
    def set_state(self, mix: TrackMixState)   # 按状态刷新按钮高亮/滑块
```

- 固定宽 ~130px。垂直布局：顶部 `_AXIS_H`(14px) 空占位（对齐时间线轴），然后 video/bgm/sfx 各一行（行高 = 对应 `_TRACK_H`），最后 dialogue 只读行。
- 每行（video/bgm/sfx）：轨名 QLabel + M QPushButton(checkable) + S QPushButton(checkable) + 音量 QSlider(0–150)。
- dialogue 行：灰色「对白（只读）」标签，无控件。
- 行高/顺序常量从 DawTrackView 复用（见下，DawTrackView 导出 `TRACK_ORDER/TRACK_H/AXIS_H`）。
- M/S 按钮 QSS：M 选中红 `#e05252`，S 选中黄 `#f9e2af`。

## DawTrackView 改动（最小）

`drama_shot_master/ui/widgets/daw/daw_track_view.py`：
- 把模块级 `_TRACK_ORDER/_TRACK_H/_AXIS_H/_LABEL_W` 暴露为公开常量别名（`TRACK_ORDER = _TRACK_ORDER` 等），供 TrackHeaderColumn 对齐。
- paintEvent 里**移除轨道名文字绘制**（现 `painter.drawText(2, ty, _LABEL_W-4, ...)` 那两行），改为不画名字（名字移到外部 header 列）。lane 填充、cue、playhead 不变。
- `_LABEL_W` 保留作画布左边距（cue 坐标不变），值不动——header 列是 DawTrackView **左侧的独立 widget**，不占画布坐标。

> 说明：header 列与 track_view 在同一 HBox 内左右排列；track_view 内部仍保留 60px 左边距用于轴标，二者视觉上拼接。首版不强求像素级对齐零误差，行高一致即可（都用 `_TRACK_H`）。

## UI：SoundtrackEditor 接线

`drama_shot_master/ui/widgets/soundtrack_editor.py` 的 `_build_daw_main`：
- `left_col` 里 track_view 外包一层 HBox：`[TrackHeaderColumn | track_view]`，header 在左。scrollbar/minimap 仍在下方（可加与 header 等宽的左空白，非必须）。
- `__init__` 建 `self._mix = load_mix(self._work_dir())`，`self._track_header = TrackHeaderColumn()`，`set_state(self._mix)`，接三个信号到 `_on_mix_changed`。
- 新方法：

```python
def _on_mute_toggled(self, track, on):
    self._mix.set_muted(track, on); self._after_mix_change()
def _on_solo_toggled(self, track, on):
    self._mix.set_soloed(track, on); self._after_mix_change()
def _on_volume_changed(self, track, v):
    self._mix.set_volume(track, v); self._after_mix_change()

def _after_mix_change(self):
    self._track_header.set_state(self._mix)   # solo 改变会影响其它轨高亮
    self._apply_audio_state()
    save_mix(self._work_dir(), self._mix)

def _apply_audio_state(self):
    """把 play_mode + mix 合成每轨最终音频状态。"""
    # 原声(video)：视频播放器音量/静音
    self._video_preview.set_muted(not self._mix.audible("video"))
    self._video_preview.set_volume(self._mix.volume("video"))
    # bgm/sfx：play_mode 决定该轨是否参与 + mix 决定可听
    for trk in ("bgm", "sfx"):
        mode_on = (trk == "bgm" and self._play_mode in ("bgm", "mix")) \
                  or (trk == "sfx" and self._play_mode == "mix")
        self._overlay.set_enabled(trk, mode_on and self._mix.audible(trk))
        self._overlay.set_volume(trk, self._mix.volume(trk))
```

- `_apply_play_mode_tracks` 末尾改为调用 `self._apply_audio_state()`（统一入口，避免 play_mode 与 mix 互相覆盖）。

## VideoPreviewWidget 改动（原声轨控制）

`drama_shot_master/ui/widgets/video_preview_widget.py` 新增公开方法：

```python
def set_volume(self, v: float) -> None:   # 0–1.5，作用于 _audio（懒建则记录待应用）
def set_muted(self, on: bool) -> None:    # _audio.setMuted
```

- `_ensure_player` 建 audio 后应用已记录的 volume/muted。

## 数据流

```
点 M/S / 拖音量 ─→ TrackHeaderColumn 信号 ─→ editor 更新 TrackMixState
   ─→ _after_mix_change：刷新 header 高亮（solo 影响全体）
                        + _apply_audio_state（video 音量/静音 + OverlayMixer enable/volume）
                        + save_mix(work_dir/mix.json)
启动 ─→ load_mix → set_state → _apply_audio_state
```

## 错误处理

- mix.json 缺/坏 → load_mix 返回默认（全可听）。
- 无 video player（懒建）→ set_volume/set_muted 记录待应用，建后生效。
- OverlayMixer 无对应轨（未建表）→ set_enabled/set_volume 对懒建 track 安全（已有空判）。

## 测试策略

- `TrackMixState` 纯逻辑单测：mute/solo/volume clamp；audible 解算（无 solo→按 mute；有 solo→只 solo 轨可听）；effective_volume；to_dict/from_dict round-trip。
- `load_mix/save_mix`：往返；缺文件→默认；坏 JSON→默认不崩。
- `TrackHeaderColumn`（offscreen）：构造；3 行有 M/S/slider，dialogue 行无；点 M emit (track,True)；set_state 反映高亮。
- `VideoPreviewWidget.set_volume/set_muted`：懒建前后都不崩、值正确。
- 编辑器接线 smoke：`_apply_audio_state` 在 raw/bgm/mix + 各 mute/solo 组合下对 OverlayMixer/video 调用正确（mock）；`_on_*_toggled` 落盘 mix.json。

## 不做（YAGNI）

- 声像 pan（Qt 限制）。
- 锁定/隐藏轨（ACE 有，短剧低价值）。
- 自定义新增音频轨（后续子项目可选）。
- 轨道分组。
- 对白轨独立音频分离（混在原声里，只读）。

## 文件清单

```
新增:
  drama_shot_master/ui/widgets/daw/track_mix.py            # TrackMixState + load/save
  drama_shot_master/ui/widgets/daw/track_header_column.py  # TrackHeaderColumn
  tests/test_ui/daw/test_track_mix.py
  tests/test_ui/daw/test_track_header_column.py
  tests/test_ui/test_video_preview_volume.py
  tests/test_ui/test_soundtrack_mix_wiring.py
改:
  drama_shot_master/ui/widgets/daw/daw_track_view.py       # 导出常量 + 去画字标签
  drama_shot_master/ui/widgets/video_preview_widget.py     # set_volume/set_muted
  drama_shot_master/ui/widgets/soundtrack_editor.py        # header 列接线 + _apply_audio_state
```
