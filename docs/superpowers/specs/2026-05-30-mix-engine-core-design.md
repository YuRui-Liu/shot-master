# 实时混音引擎 — PCM 缓存 + 混音核 设计（子项目 #3b-1 / #3b-2）

> 日期：2026-05-30　分支：main
> #3b 真并发播放引擎的前两块（纯逻辑地基）。第三块 3b-3（sounddevice 实时输出流）单独立项。

## 背景与定位

#3b 目标：动态多子轨叠加片段**真采样级同时播放**（像剪映/ACE）。方案 B = 实时软件混音（soundfile/ffmpeg 解码 → numpy 叠加 → sounddevice 输出）。同步采用 b：视频主时钟，音频引擎跟随。

本设计只做**纯逻辑地基**（无音频设备、无线程、全可单测）：
- **3b-1 PCM 片段缓存** `PcmCache`：把 overlay 片段音频文件解码成统一格式 numpy 数组并缓存。
- **3b-2 混音核** `mix_frame`：给定播放头 + 活跃片段 → 算出该时刻输出缓冲（纯函数）。

3b-3（OutputStream 回调 + 视频 positionChanged 驱动 + play/pause/seek）依赖这两块，单独做。

## 已锁定决策

- 统一格式：**立体声 2ch + 48000Hz + float32**（匹配测试视频音轨；超出 [-1,1] hard clip）。
- 解码：**ffmpeg → f32le stereo 48k**（一步含重采样，已验证管线 mp3→48000帧/2ch 正确）。项目已重度用 ffmpeg。
- overlay 片段首版按各自 `volume/enabled` 混（3a 字段），**不纳入全局 solo/mute**（简化首版）。
- 混音核纯函数，不碰设备/线程。

## 3b-1：PcmCache

新文件 `drama_shot_master/ui/widgets/daw/pcm_cache.py`（放 UI 层因为是播放预览用；纯 numpy/subprocess 无 Qt）：

```python
SAMPLE_RATE = 48000
CHANNELS = 2

def decode_to_pcm(audio_path: str) -> np.ndarray:
    """ffmpeg 解码任意音频 → float32 ndarray shape (frames, 2)，48k 立体声。
    解码失败 / 空文件 → 返回 shape (0, 2) 空数组（不抛）。"""

class PcmCache:
    """audio_path → 解码后的 PCM ndarray 缓存（懒解码 + 复用）。"""
    def get(self, audio_path: str) -> np.ndarray   # 命中返回缓存；未命中 decode 并存
    def clear(self) -> None
    def __len__(self) -> int                        # 缓存条目数
```

- `decode_to_pcm`：`ffmpeg -i <path> -f f32le -acodec pcm_f32le -ac 2 -ar 48000 -` → 读 stdout bytes → `np.frombuffer(.., float32).reshape(-1, 2)`。文件不存在/ffmpeg 非零退出/空输出 → `np.zeros((0,2), float32)`。
- `PcmCache.get`：dict 缓存 keyed by path；缺则 decode。空数组也缓存（避免反复重试坏文件）。

## 3b-2：mix_frame

新文件 `drama_shot_master/ui/widgets/daw/mix_core.py`（纯 numpy 无 Qt）：

```python
@dataclass
class ActiveClip:
    pcm: np.ndarray      # (frames, 2) float32，来自 PcmCache
    t_start: float       # 片段在时间线上的起点（秒）
    volume: float        # 0.0–1.5

def mix_frame(clips: list[ActiveClip], playhead_sec: float,
              n_frames: int, sample_rate: int = 48000) -> np.ndarray:
    """混出从 playhead_sec 起 n_frames 帧的立体声输出 (n_frames, 2) float32。

    对每个 clip：算它在本窗口内的覆盖范围，把对应 PCM 切片 * volume 叠加进输出。
    窗口外/已结束的 clip 自动贡献 0。最后 hard clip 到 [-1, 1]。
    空 clips → 全 0。"""
```

算法：
- 输出 `out = zeros((n_frames, 2))`。
- 窗口时间区间 `[playhead, playhead + n_frames/sr)`。
- 每个 clip：它的 PCM 覆盖时间线 `[t_start, t_start + len(pcm)/sr)`。求与窗口交集 → 交集内每帧的 clip 内偏移 = `round((win_t - t_start)*sr)`，切 `pcm[off : off+k]`，写入 out 对应位置，乘 volume 累加。
- `np.clip(out, -1.0, 1.0, out=out)`。

边界：clip 早于/晚于窗口 → 无交集贡献 0；clip PCM 比交集短 → 只叠可用部分。

## 范围

- ✅ decode_to_pcm / PcmCache / ActiveClip / mix_frame（纯逻辑，全单测）。
- ❌ 不碰 sounddevice / 线程 / 视频同步 / OverlaySession 集成（都在 3b-3）。

## 测试策略

**PcmCache**（用 ffmpeg 生成临时 mp3 测真实解码，CI 有 ffmpeg）：
- decode_to_pcm 正常 mp3 → shape (~N, 2) float32，N≈duration*48000（容差）。
- 不存在路径 → (0,2)。
- 空/坏文件 → (0,2) 不抛。
- PcmCache.get 同 path 二次命中不重复解码（mock decode 计数 或 len 检查）；空数组也缓存。

**mix_frame**（纯 numpy，构造 ActiveClip 不依赖 ffmpeg）：
- 空 clips → zeros(n,2)。
- 单 clip 完全在窗口内 → 输出 = pcm * volume。
- volume 缩放正确。
- 两 clip 重叠 → 逐样本相加。
- clip t_start 在窗口中间 → 前半 0、后半为 pcm 前段。
- clip 早于窗口（已播完）→ 贡献 0。
- 叠加超 1.0 → hard clip 到 1.0。
- clip PCM 比窗口短 → 只叠可用帧，其余 0。

## 文件清单

```
新增:
  drama_shot_master/ui/widgets/daw/pcm_cache.py
  drama_shot_master/ui/widgets/daw/mix_core.py
  tests/test_ui/daw/test_pcm_cache.py
  tests/test_ui/daw/test_mix_core.py
```

> sounddevice 依赖留到 3b-3（实际 import 时）再加进 requirements.txt——本块纯 numpy/ffmpeg，不依赖 sounddevice，避免登记未用依赖。
