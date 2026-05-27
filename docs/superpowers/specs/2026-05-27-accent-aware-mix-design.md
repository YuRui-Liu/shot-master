# 卡点感知混音 (Accent-Aware Mix) 设计

**目标:** 让 ③卡点页收集的 `accent_points` 真正影响出片——音乐在视频动作爆点处产生同步的听感变化("卡上点"),而不再是只检测、不消费的装饰。

**架构:** 双层卡点系统,作用在已拼好的整条 BGM 上(时间轴 = 视频时间,卡点秒数直接映射采样位置)。主力是 sidechain 泵感强调层(纯 numpy 增益包络),辅助是段切对齐(把 BGM 段接缝吸附到大卡点)。新增纯逻辑模块 `accent_mixer.py`,在 `mixdown.assemble_and_mix` 中按开关接入,关闭即完全等同现状。

**技术栈:** numpy(已用) + soundfile(env 已装,加进 requirements);ffmpeg/Demucs 沿用现有 `audio_mixer`/`bgm_assembler`。不引入 librosa(本期不做 onset 检测/time-warp)。

---

## 1. 范围与行为模型

双层卡点,都作用在拼接后的整条 BGM(其时间轴等于视频时间):

- **主力·强调层 (sidechain 泵感):** 对**每个**卡点,把 BGM 音量瞬时下压再回弹(快 attack、慢 release 的增益包络)。单点泵深 = `pump_strength`(任务级) × 该卡点 `intensity`。小卡点小泵、大卡点大泵。纯增益包络,不改音色。
- **辅助·段切对齐:** 把相邻段 BGM 交叉淡入的**接缝**吸附到附近的**大卡点**(`intensity ≥ accent_big_threshold`),让转场/段落切换落在大卡点上。
- **大卡点 = 两者叠加**:既有强泵感,接缝又落在它上面。
- **time-warp(对齐音乐自带重音):本期不做。** 设计预留位置,后续可作高级开关。

**门控:** 当 `session.accent_mix_enabled` 为 True **且** `session.accent_points` 非空时启用;否则 `assemble_and_mix` 走与今天完全相同的逻辑(零回归)。

## 2. 段切对齐的安全规则

每段 BGM 时长 ≈ `seg.duration`(generate 阶段按 `seg.duration` 生成),所以自然接缝 ≈ `seg[i].t_end`。对每个内部接缝 `b = seg[i].t_end`:

- 若 `[b − window, b]` 区间内存在大卡点 `t`(卡点在接缝**当前或之前**),把接缝挪到 `t`——通过**裁掉 clip i 的尾部**实现(只缩短、永不拉长,零音质风险)。
- 卡点在接缝之后(`t > b`)需把 clip 拉长 → **v1 跳过**(留给未来的 time-warp)。
- 多个候选大卡点取**最近**的;调整后接缝必须**单调递增**且不越过相邻段(夹在 `(boundary[i-1], seg[i+1] 的自然末尾)` 内)。

实现为纯函数,易单测,不碰 ffmpeg。

## 3. 新模块 `sound_track_agent/accent_mixer.py`(纯逻辑,可单测)

```python
def build_pump_envelope(n_samples: int, sr: int, accents: list[AccentPoint],
                        *, strength: float, attack: float = 0.012,
                        release: float = 0.35) -> "np.ndarray":
    """基线 1.0。每个卡点在其采样位置处下压到 (1 - strength*intensity),
    attack 秒内快速下压、release 秒内线性回升到 1.0。多卡点重叠取逐样本 min。
    强度夹紧到 [0,1],包络夹紧 >= 0。"""

def apply_pump(bgm_in, bgm_out, accents, *, strength: float,
               attack: float = 0.012, release: float = 0.35) -> Path:
    """soundfile 读 wav -> 构建包络(按文件 sr/length) -> 逐通道相乘 -> 写出。"""

def snap_boundaries(seg_durations: list[float], accents: list[AccentPoint],
                    *, big_threshold: float, window: float) -> list[float]:
    """输入各段时长(累加得内部接缝)与卡点。对每个内部接缝,在
    [b-window, b] 内找最近的大卡点(intensity >= big_threshold)则吸附;
    否则保持原接缝。返回 len = 段数-1 的新接缝时间(绝对秒,单调)。"""
```

- 依赖:`numpy`(已用)+ `soundfile`(加进 requirements)。**不需要 librosa**。
- 设计点:`build_pump_envelope` / `snap_boundaries` 为零 I/O 纯函数,直接断言数值;`apply_pump` 为薄 I/O 包装。

## 4. 接入 `mixdown.assemble_and_mix`

新增可选参数 `accents`、`pump_strength`、`accent_mix_enabled`、`big_threshold`、`snap_window`(由 facade 从 session/cfg 注入)。流程:

```
若 accent_mix_enabled 且 accents 非空:
    boundaries = snap_boundaries(seg_durations, accents,
                                 big_threshold=..., window=...)   # 方案3
    按 boundaries 裁剪各 clip 尾部 -> assemble_bgm(crossfade)
    full_bgm = apply_pump(full_bgm, accents, strength=pump_strength)  # 方案1
否则:
    full_bgm = assemble_bgm(seg_bgms, crossfade)                  # 现状
-> extract_audio -> separate_vocals -> duck_and_mix -> replace_video_audio
```

裁剪用 ffmpeg `-t`/`atrim`(或在 `bgm_assembler` 内按目标时长裁);只缩短。关闭开关或无卡点时这段完全不执行。

## 5. 数据模型 + 控制面

**任务级(持久化进 `session.json`,由 ③卡点页控制):**
- `ScoringSession.accent_mix_enabled: bool = True` — 「卡点混音」开关
- `ScoringSession.pump_strength: float = 0.6` — 「泵感强度」滑块(0–100% 映射 0.0–1.0)

两字段进 `to_dict`/`from_dict`,旧 session 缺字段时用默认值(向后兼容读取)。

**全局(`设置→配乐` 对话框,cfg / settings.json):**
- `accent_big_threshold: float = 0.7` — 大卡点强度阈值
- `accent_snap_window: float = 0.6`(秒) — 段切吸附窗口

facade 在组装 mix_fn 时,从 session 读任务级参数、从 cfg 读全局参数(鸭子类型 `getattr` + 默认值,保持 facade 不在顶层 import 宿主)。

## 6. UI 改动

- **③卡点页 `AccentEditorWidget`:** 顶部工具行加「卡点混音」复选框 + 「泵感强度」滑块;改动即写 `session.accent_mix_enabled`/`pump_strength` 并触发落盘(沿用现有 `accentsChanged`→`_persist_session` 通道或新增等价信号)。时间轴上 `intensity ≥ accent_big_threshold` 的大卡点用**更大的菱形**区分(从 cfg 读阈值,读不到回退 0.7)。
- **设置→配乐对话框:** 加两个数值字段(大卡点阈值、吸附窗口秒数),读写 cfg/settings.json。

## 7. 错误处理

- `apply_pump`:wav 读失败/采样率异常 → 抛 `RuntimeError`,由 `assemble_and_mix` 向上传(出片失败提示),不静默吞。
- `snap_boundaries`:卡点为空或无大卡点 → 原样返回自然接缝(降级为纯方案1)。
- 段切裁剪后某 clip 时长 ≤ 0 或 < crossfade → 跳过该次吸附,保留自然接缝(防越界)。
- 整体门控:任一异常不应使关闭状态(现状路径)受影响。

## 8. 测试

- **`accent_mixer` 纯函数单测:** 包络在卡点处的下压量 = `1 - strength*intensity`、attack/release 形状、基线 1.0、多点重叠取 min、intensity 与 strength 夹紧;`snap_boundaries` 的窗口内吸附、`big_threshold` 过滤小卡点、单调性、trim-only 不拉长(`t > b` 跳过)、空/无大卡点降级。
- **`apply_pump` 往返:** soundfile 生成小 wav → 应用 → 断言卡点邻域采样被压低、远处采样基本不变。
- **`mixdown` 集成:** 注入 fake runner/假 `apply_pump`,验证开关开时 snap+pump 被调用、关时或无卡点时被旁路且等价现状。
- **UI smoke(offscreen):** 复选框/滑块写 session 字段并落盘;设置对话框读写两个全局字段。避免模态阻塞。
- **自包含验证:** 全部新增落在 `sound_track_agent`(逻辑)+ `drama_shot_master`(UI/设置),无外部音频资源、无 sibling-project import。

## 9. 文件清单

- 新增 `sound_track_agent/accent_mixer.py`
- 改 `sound_track_agent/session.py`(2 个字段 + 序列化)
- 改 `sound_track_agent/mixdown.py`(`assemble_and_mix` 接入,新增参数)
- 改 `sound_track_agent/bgm_assembler.py`(支持按目标时长裁剪 clip,或在 mixdown 内裁)
- 改 `sound_track_agent/facade.py`(`_build_real_stages` 注入 session/cfg 参数到 mix_fn)
- 改 `drama_shot_master/ui/widgets/accent_editor_widget.py`(开关 + 滑块 + 大卡点标记)
- 改 设置→配乐对话框(两个全局字段)
- 新增/改对应测试

## 10. 默认值

| 参数 | 默认 | 位置 |
|------|------|------|
| `pump_strength` | 0.6 | session(任务级) |
| `accent_mix_enabled` | True | session(任务级) |
| `accent_big_threshold` | 0.7 | cfg(全局) |
| `accent_snap_window` | 0.6 s | cfg(全局) |
| pump attack / release | 0.012 s / 0.35 s | 代码常量 |
