# 实时混音输出引擎设计 — 子项目 #3b-3

> 日期：2026-05-30　分支：main
> #3b 真并发播放引擎的第三块（临门一脚）。地基已就绪：3a OverlaySession / 3b-1 PcmCache / 3b-2 mix_frame。

## 背景与定位

把前几块串成一个能**真采样级同时播放**叠加片段的引擎。同步 b：视频主时钟，音频引擎跟随。本块 = `MixStreamEngine`（纯逻辑拉帧，全单测）+ 薄 sounddevice 输出适配层（回调只调拉帧，无设备不测）。

## 环境约束（决定设计）

- **sounddevice 尚未安装** + **开发环境 WSL 无声卡**（真实运行在 Windows）。→ 实时输出**无法在开发环境端到端测**，必须把可测的纯逻辑与设备层彻底分离。
- sounddevice：BSD 许可（非 GPL，合规）。本块加进 requirements.txt。

## 已锁定决策

- **a 两层架构**：`MixStreamEngine`（纯逻辑：PcmCache + 当前片段 + 播放头基准 + `pull(n)→ndarray`）+ `_SoundDeviceOutput`（sounddevice OutputStream 适配，回调只调 `engine.pull`）。
- **优雅降级**：sounddevice 没装 / 开流失败 / 无设备 → 引擎 `available=False`，叠加播放静默失效（视频原声照常），不崩，记一次状态/日志。
- **播放头驱动**：视频 `positionChanged` → `set_playhead(t)` 更新基准；音频回调按"基准 + 自上次基准以来已输出帧数"自走推进，不被 30Hz 阻塞。play/pause/seek 改基准。

## 组件

### MixStreamEngine（纯逻辑，`drama_shot_master/ui/widgets/daw/mix_stream_engine.py`）

```python
class MixStreamEngine:
    """实时混音拉帧引擎（纯逻辑，无设备）。设备层通过 pull(n) 取混音帧。"""
    def __init__(self, pcm_cache=None, sample_rate=48000):
        # pcm_cache 缺省自建 PcmCache
        self._segments: list = []      # 当前 overlay 片段 (含 t_start/t_end/audio_path/volume/enabled)
        self._playhead = 0.0           # 基准播放头（秒），由视频驱动
        self._frames_since = 0         # 自上次 set_playhead 以来已输出帧数
        self._playing = False

    def set_segments(self, segs) -> None:
        """传入 OverlaySegment 列表（或等价具 audio_path/t_start/t_end/volume/enabled 的对象）。
        预解码各片段 PCM（PcmCache.get），构建内部 ActiveClip 列表。enabled=False / 空 audio_path 跳过。"""

    def set_playhead(self, t_sec: float) -> None:
        self._playhead = float(t_sec); self._frames_since = 0

    def play(self) -> None / pause(self) -> None    # 改 _playing

    def current_playhead(self) -> float:
        """基准 + 已输出帧数/sr（回调推进后的真实位置）。"""
        return self._playhead + self._frames_since / self._sr

    def pull(self, n_frames: int) -> np.ndarray:
        """供音频回调：返回 (n_frames, 2) float32。
        not playing → 返回 zeros（静音但流不停）。
        playing → mix_frame(self._clips, current_playhead, n) 后 _frames_since += n。"""
```

- `set_segments` 把 OverlaySegment → `ActiveClip(pcm=cache.get(audio_path), t_start, volume)`，过滤 `enabled and audio_path`。
- `pull` 是回调热路径：只做 numpy 切片叠加（mix_frame），不解码（解码在 set_segments 预热）、不碰磁盘。
- 全部可单测：构造 engine、set_segments（用真 ffmpeg 生成的小 mp3 或直接塞假 PcmCache）、set_playhead、pull → 断言波形。

### _SoundDeviceOutput（设备适配，同文件或 `mix_stream_output.py`）

```python
class MixStreamOutput:
    """sounddevice OutputStream 包装。import/开流失败 → available=False 优雅降级。"""
    def __init__(self, engine, sample_rate=48000, channels=2):
        self.available = False
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(samplerate=..., channels=2,
                dtype="float32", callback=self._cb)
            self.available = True
        except Exception:
            self._stream = None    # 降级

    def _cb(self, outdata, frames, time_info, status):
        outdata[:] = self._engine.pull(frames)

    def start(self) / stop(self) / close(self):  # 都 guard available
```

- 不单测（无设备）；逻辑极薄，回调只一行 `outdata[:] = engine.pull(frames)`。

## 与编辑器集成（最小，本块只接线不做框选）

`SoundtrackEditor`：
- `__init__`：`self._mix_engine = MixStreamEngine()`；`self._mix_output = MixStreamOutput(self._mix_engine)`（降级安全）。
- 载入时 `load_overlay(work_dir)` → `engine.set_segments(overlay.segments)`。
- `_on_video_position_changed(t)` 末尾：`self._mix_engine.set_playhead(t)`。
- `_on_video_playing_changed(on)`：`on ? (engine.play(); output.start()) : (engine.pause())`。
- 这样：overlay 片段（3d 生成后）即可随视频实时叠加播放。本块若 overlay 为空则引擎输出静音（无副作用）。

> 注：现有 OverlayMixer（固定轨 bgm/sfx 调度播放）保持不动并存。MixStreamEngine 专门负责 overlay 动态片段。二者都跟随视频主时钟。

## 错误处理 / 降级

- sounddevice ImportError / OutputStream 构造异常 / 无设备 → `MixStreamOutput.available=False`，start/stop/close 全 no-op，引擎仍可 pull（被谁调用都安全），叠加播放静默失效，视频与固定轨照常。
- pull 中 segment PCM 为空 → mix_frame 自然贡献 0。
- set_segments 中解码失败的片段 → PcmCache 返回空数组 → 跳过。

## 测试策略

**MixStreamEngine（全单测，用假 PcmCache 或 ffmpeg 小 mp3）：**
- 构造默认；`set_segments` 用一个具 audio_path 的 OverlaySegment（指向 ffmpeg 生成的 1s 正弦 mp3）→ 内部 clip 数 == 1；enabled=False 或空 audio_path → 跳过（clip 数 0）。
- `pull` not playing → 全 0。
- `set_playhead(0)` + `play()` + `pull(n)` → 非全 0（片段在 0 处）。
- `current_playhead`：set_playhead(2.0) 后连续 pull 推进 → playhead 增加 frames/sr。
- 注入假 PcmCache（`get` 返回构造的常量数组）避免依赖 ffmpeg：set_segments 两个重叠片段 → pull 得叠加值。

**MixStreamOutput（降级测试，无设备）：**
- 构造时 sounddevice 不可用 → `available is False`，start()/stop()/close() 不抛。
- （用 monkeypatch 让 import sounddevice 抛 → 验证降级路径。）

**编辑器接线 smoke：**
- editor 有 `_mix_engine`/`_mix_output`；`_on_video_position_changed` 调 `set_playhead`（mock engine 验证）；overlay 空时不崩。

## 文件清单

```
新增:
  drama_shot_master/ui/widgets/daw/mix_stream_engine.py   # MixStreamEngine + MixStreamOutput
  tests/test_ui/daw/test_mix_stream_engine.py
  tests/test_ui/test_soundtrack_mix_engine_wiring.py
改:
  drama_shot_master/ui/widgets/soundtrack_editor.py        # 引擎接线（set_playhead/play/pause + load_overlay）
  requirements.txt                                          # + sounddevice
```
