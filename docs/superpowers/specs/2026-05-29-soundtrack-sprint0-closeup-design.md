# 配乐 Sprint 0 闭环（音量 bug + 可配置抽帧数 + 4 项 GUI 缺口）设计

> 日期：2026-05-29 ｜ 模块：`drama_shot_master/ui/` + `sound_track_agent/` + `config`
> 来源：第 6 轮对话用户反馈的 3 件遗留 + Phase 2/3 已知 GUI 缺口
> 状态：设计已评审通过，待写实施计划

## 1. 背景与目标

Phase 1+2+3 后端能力已全部落地，但 GUI 链路仍有若干小缺口与用户可见 bug：

1. **音量滑条 bug**：`SegmentReviewWidget` 候选试听时拖滑条不当下生效（`seg.volume` 仅持久化、QMediaPlayer 输出音量未同步）
2. **抽帧数不可配**：`refine.refine_segments` 硬编码 3 帧／shot，用户无从在「质量 vs 成本」间权衡
3. **4 项 GUI 缺口**：
   - 后端 Phase 2 B「复用 TTS 对白干轨」已实现，但 `SoundtrackEditor` 调 `facade.prepare_session` 时**未传** `dialogue_segments` → mix 阶段仍走 Demucs 盲分离
   - 5 个 cfg 字段（`accent_max_stretch / refine_max_segments / refine_merge_threshold / soundtrack_max_concurrency / soundtrack_score_weights`）**无 UI 控件** → 用户只能改 settings.json
   - 没有「手动触发 refine 重排」按钮 → 重排必须改 session.json
   - 缺对应 smoke 测

**目标**：一个小 sprint（~7 任务、1-2 天）一次性闭环这 3 件事，让配乐 GUI 链路达到「Phase 1+2+3 后端能力全部曝光给用户」状态。**不动现有后端契约**。

## 2. 范围

**本期内**：上述 3 项 GUI 链路 + cfg 字段 + 测试。**不动**任何 sound_track_agent 后端核心（除 `refine.refine_segments` 增 1 个 kwarg 与 `facade._build_real_stages` 透传）。

**本期外**：Phase 4a（音乐选段 UX 大补强）、Phase 4b（SFX 音效层）—— 后续独立 phase。

## 3. 架构与模块边界

无新外部依赖。新增 1 个工具文件 + 改动若干现有文件：

| 文件 | 增量 |
|---|---|
| `drama_shot_master/ui/widgets/segment_review_widget.py` | `_on_volume` / `_on_candidate` 同步 `QAudioOutput.setVolume` |
| `drama_shot_master/config.py` | + 6 字段：`refine_frames_per_shot / refine_max_segments / refine_merge_threshold / accent_max_stretch / soundtrack_max_concurrency / soundtrack_score_weights` |
| `sound_track_agent/refine.py` | `refine_segments` + `_times_for_shot(shot, frames_per_shot)` helper；增 `frames_per_shot` kwarg（默认 3） |
| `sound_track_agent/stages_factory.py` | `build_stages` 增 `refine_frames_per_shot` kwarg 透传 |
| `sound_track_agent/facade.py` | `_build_real_stages` 读 `cfg.refine_frames_per_shot` 透传 |
| `drama_shot_master/ui/widgets/settings_sections/soundtrack_section.py` | + 6 个新控件 + load/apply |
| `drama_shot_master/ui/widgets/soundtrack_editor.py` | 调 facade 前派生 `dialogue_segments`；+「🔄 重排段落」按钮 + handler |
| **新** `drama_shot_master/core/dialogue_segment_deriver.py` | `derive_dialogue_segments(cfg, mp4_path)` 纯逻辑工具 |
| `tests/test_sound_track_agent/test_refine.py` | + `frames_per_shot` 透传/抽帧数/非法值测试 |
| `tests/test_ui/test_segment_review_smoke.py` | + 音量滑条同步 QAudioOutput 测试 |
| `tests/test_ui/test_soundtrack_section_smoke.py` | + 6 个新控件读写 cfg 测试 |
| **新** `tests/test_core/test_dialogue_segment_deriver.py` | mock cfg/timeline 派生测试 |
| `tests/test_ui/test_soundtrack_editor_smoke.py`（若存在） | + 重排按钮安全护栏 + dialogue_segments 接线测试 |

依赖方向：`SoundtrackEditor → dialogue_segment_deriver → cfg.video_tasks (read-only)`；新工具纯下行，无反向。

## 4. 数据结构变更

无新 dataclass。仅扩展 `config.Config`：

```python
# drama_shot_master/config.py
@dataclass
class Config:
    ...
    refine_frames_per_shot: int = 3              # 枚举 1/3/5
    refine_max_segments: int = 5
    refine_merge_threshold: float = 0.25
    accent_max_stretch: float = 0.10
    soundtrack_max_concurrency: int = 3
    soundtrack_score_weights: dict = field(
        default_factory=lambda: {"health": 0.5, "headroom": 0.3, "beat": 0.2})
```

`to_dict / from_dict` 同步加 6 项；旧 settings.json 缺字段全部走默认（**零回归**）。

> 这 6 个字段在 `sound_track_agent` 里早就以 `getattr(cfg, ..., default)` 形式被读取（Phase 1/2/3 已写入）。本期只是把它们正式加进 `Config` 类型并露出 UI。

## 5. #1 · Volume Bug 修复（`segment_review_widget.py`）

QMediaPlayer/QAudioOutput 是独立的 OS 级音频通路，不读 `seg.volume`。Bug 根因是滑条只更新数据模型、未同步播放器。两处微改即可：

```python
def _on_volume(self, seg, val: int, label):
    seg.volume = val / 100.0
    label.setText(f"{val}%")
    self.segmentVolumeChanged.emit()
    # 拖滑条时如果正在播这段候选 → 立即更新 QAudioOutput
    if (self._player is not None and self._playing_key is not None
            and self._playing_key[0] == seg.index):
        self._audio.setVolume(min(1.0, max(0.0, float(seg.volume))))


def _on_candidate(self, seg_index: int, cand_index: int):
    # ...（existing 逻辑不变直到 player.setSource(...)）
    player.setSource(QUrl.fromLocalFile(path))
    # 开播前按当前 seg.volume 初始化一次
    self._audio.setVolume(min(1.0, max(0.0, float(getattr(seg, "volume", 1.0)))))
    self._playing_key = (seg_index, cand_index)
    player.play()
```

**注**：QAudioOutput 用 0–1 线性，截到 1.0；`seg.volume` 持久值最高 1.5（留给 ffmpeg 增益）维持不变。

## 6. #3 · `refine_frames_per_shot` 可配置

**cfg 字段**：`refine_frames_per_shot: int = 3`（UI 限 1/3/5）

**`refine.refine_segments` 改造** —— 提取 `_times_for_shot` 纯函数：

```python
def _times_for_shot(shot, frames_per_shot: int) -> list[float]:
    """按 frames_per_shot 出抽帧时间点；duration ≤ 0.1s 永远退化单帧 mid。"""
    duration = shot.t_end - shot.t_start
    mid = (shot.t_start + shot.t_end) / 2.0
    if duration <= _MIN_MULTIFRAME_DUR or frames_per_shot == 1:
        return [mid]
    if frames_per_shot == 3:
        return [shot.t_start + 0.05, mid, shot.t_end - 0.05]
    if frames_per_shot == 5:
        q = (mid - shot.t_start) / 2.0
        return [shot.t_start + 0.05, mid - q, mid, mid + q, shot.t_end - 0.05]
    raise ValueError(f"frames_per_shot 必须为 1/3/5（收到 {frames_per_shot}）")
```

`refine_segments` 签名加 `frames_per_shot: int = 3` kwarg，循环里调 `_times_for_shot`。

**透传链**：
- `stages_factory.build_stages` 增 `refine_frames_per_shot: int = 3` kwarg → 传入 `refine_segments_fn` 闭包
- `facade._build_real_stages` 读 `int(getattr(cfg, "refine_frames_per_shot", 3))` 传入 `build_stages`

**默认值与边界**：1（仅 mid，省成本）/ 3（现状） / 5（提升信号、~67% 额外成本）。极短 shot（< 0.1s）永远退化单帧 mid（不变）。

## 7. §2 GUI Gaps（4 子项）

### 7.1 dialogue_segments 派生 + 接线（**关键**）

**新工具** `drama_shot_master/core/dialogue_segment_deriver.py`（纯逻辑）：

```python
"""把 cfg.video_tasks 里匹配的 VideoTask.timeline.audios 派生成 DialogueSegment 列表。

供 SoundtrackEditor 在调 facade.prepare_session 前调用，让 mix 阶段跳过 Demucs 盲分离。
找不到匹配（用户手工导入 MP4 / VideoTask 无 audio）→ 返回 []，caller 不传 dialogue_segments，
mix 阶段按原回退路径走 Demucs（零回归）。
"""
from __future__ import annotations

from sound_track_agent.session import DialogueSegment


def derive_dialogue_segments(cfg, mp4_path: str) -> list[DialogueSegment]:
    """扫 cfg.video_tasks，找 last_result == mp4_path 的 task，
    从其 timeline.audios 派生 DialogueSegment（frame → 秒）。"""
    for task in getattr(cfg, "video_tasks", []) or []:
        if str(task.get("last_result", "")) != str(mp4_path):
            continue
        timeline = task.get("timeline") or {}
        fps = float(timeline.get("frame_rate", 24.0)) or 24.0
        audios = timeline.get("audios") or []
        return [
            DialogueSegment(
                audio_path=str(a["audio_path"]),
                t_start=float(a["start_frame"]) / fps,
                duration=float(a["length_frames"]) / fps,
            )
            for a in audios if a.get("audio_path")
        ]
    return []
```

**`SoundtrackEditor` 接线**（仅改 1 处）—— 调 `facade.prepare_session` 前派生：

```python
from drama_shot_master.core.dialogue_segment_deriver import derive_dialogue_segments

# 替换原 sess = facade.load_session(work_dir) or facade.prepare_session(mp4, style, work_dir)
sess = facade.load_session(work_dir)
if sess is None:
    dialogue_segs = derive_dialogue_segments(self.cfg, mp4) or None
    sess = facade.prepare_session(mp4, style, work_dir,
                                  dialogue_segments=dialogue_segs)
```

> `dialogue_segs = ... or None`：空列表也传 None，让 facade 走「未指定」默认值，与现有契约对齐。

### 7.2 6 个 cfg 控件（合并 §3 的 frames_per_shot）

`SoundtrackSection._build_ui` form 末尾加：

```python
# 精排抽帧数
self.frames_combo = QComboBox()
self.frames_combo.addItems(["1", "3", "5"])
form.addRow("精排抽帧数 (1/3/5)", self.frames_combo)

# 邻接合并段数上限
self.refine_max_spin = QSpinBox()
self.refine_max_spin.setRange(1, 10)
form.addRow("邻接合并段数上限", self.refine_max_spin)

# 邻接合并相似阈值
self.refine_thresh_spin = QDoubleSpinBox()
self.refine_thresh_spin.setRange(0.0, 1.0); self.refine_thresh_spin.setSingleStep(0.05)
form.addRow("邻接合并相似阈值", self.refine_thresh_spin)

# 真·卡点拉伸上限
self.stretch_spin = QDoubleSpinBox()
self.stretch_spin.setRange(0.0, 0.5); self.stretch_spin.setSingleStep(0.01)
form.addRow("真·卡点拉伸上限 (±)", self.stretch_spin)

# 生成并发上限
self.concurrency_spin = QSpinBox()
self.concurrency_spin.setRange(1, 10)
form.addRow("生成并发上限", self.concurrency_spin)

# 候选打分权重（3 个 QDoubleSpinBox）
weights_row = QHBoxLayout()
self.w_health = QDoubleSpinBox();   self.w_health.setRange(0.0, 1.0);   self.w_health.setSingleStep(0.05)
self.w_headroom = QDoubleSpinBox(); self.w_headroom.setRange(0.0, 1.0); self.w_headroom.setSingleStep(0.05)
self.w_beat = QDoubleSpinBox();     self.w_beat.setRange(0.0, 1.0);     self.w_beat.setSingleStep(0.05)
weights_row.addWidget(QLabel("health")); weights_row.addWidget(self.w_health)
weights_row.addWidget(QLabel("headroom")); weights_row.addWidget(self.w_headroom)
weights_row.addWidget(QLabel("beat")); weights_row.addWidget(self.w_beat)
weights_wrap = QWidget(); weights_wrap.setLayout(weights_row)
form.addRow("候选打分权重", weights_wrap)
```

`load_from(cfg)` / `apply_to(cfg)`：读 `getattr(cfg, name, default)`、写回 `setattr(cfg, name, value)`；`soundtrack_score_weights` 读 dict → 三个 spin / 写三个 spin → dict（保留键名 `health/headroom/beat`）。

### 7.3 「🔄 重排段落」按钮

`SoundtrackEditor` 在「🎬 开始配乐」按钮旁加：

```python
self.btn_resegment = QPushButton("🔄 重排段落")
self.btn_resegment.clicked.connect(self._on_resegment)
# ...

def _on_resegment(self):
    if not self._session:
        QMessageBox.warning(self, "无法重排", "请先开始配乐生成 session")
        return
    # 安全护栏：有候选 → 二次确认 + 清理候选/prompt/emotion
    if any(s.candidates for s in self._session.segments):
        if QMessageBox.warning(self, "重排会清空候选",
                "已有 BGM 候选会被清空丢弃，确定重排？",
                QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
            return
        for s in self._session.segments:
            s.candidates = []; s.chosen_candidate = None
            s.music_prompt = ""; s.status = "pending"; s.emotion = None
    self._session.segments_refined = False
    self._session.save(self._work_dir() / "session.json")
    self._run_pipeline("refine_segments")
```

### 7.4 测试

- **`test_dialogue_segment_deriver.py`**（纯逻辑）：
  - 匹配命中（cfg.video_tasks 有匹配 last_result）→ 返回正确 DialogueSegment 列表
  - 匹配不上 → `[]`
  - 多 task 只匹配第一个命中
  - 缺 `timeline.audios` → `[]`
  - 缺 `audio_path` 字段的 audio → 跳过
  - `frame_rate=0` 或缺 → fallback 24.0
- **`test_segment_review_smoke.py`**：mock `_audio.setVolume`，断言滑条 valueChanged 触发 setVolume；`_on_candidate` 开播前也调一次
- **`test_soundtrack_section_smoke.py`**：6 个新控件存在 + load/apply 往返；`soundtrack_score_weights` dict 正确分发到三个 spin
- **`test_refine.py`**：
  - `frames_per_shot=1` → 抽 1 帧（仅 mid）
  - `frames_per_shot=3` → 3 帧（现状）
  - `frames_per_shot=5` → 5 帧
  - 非法值（如 2）→ `ValueError`
- **`test_soundtrack_editor_smoke.py`**：mock cfg.video_tasks 含匹配 task，断言 `prepare_session` 收到非空 `dialogue_segments`；重排按钮在无候选时直接重置，在有候选时弹确认（mock QMessageBox.warning 返回 Cancel → 不动）

## 8. 错误处理 / 续跑

| 失败点 | 行为 |
|---|---|
| QAudioOutput.setVolume 异常 | 静默忽略（不阻塞 UI；播放器本身故障会另行抛错） |
| `derive_dialogue_segments` cfg.video_tasks 结构异常（缺键/类型错） | 函数内 `try/except` 捕获、返回 `[]` → mix 走 Demucs 回退 |
| 重排按钮在 session 不存在时点击 | 弹 warning 提示先开始配乐 |
| 重排时 ffmpeg / vision 失败（refine 内部异常） | refine 已有 try/except 降级（Phase 3 已设计），返回 False，session.segments_refined 保持 False，下次再点重排会重试 |
| 用户从 settings.json 手改非法 cfg 值 | 控件 range 边界保护 + facade 的 `getattr` 默认值兜底 |

## 9. 配置项总表（新增）

| 字段 | 默认 | 用途 |
|---|---|---|
| `refine_frames_per_shot` | `3` | 精排每 shot 抽帧数（1/3/5） |
| `refine_max_segments` | `5` | 邻接合并段数硬上限 |
| `refine_merge_threshold` | `0.25` | 邻接合并相似距离阈值 |
| `accent_max_stretch` | `0.10` | 真·卡点局部拉伸因子上限（±） |
| `soundtrack_max_concurrency` | `3` | 生成阶段并发任务上限 |
| `soundtrack_score_weights` | `{health:.5, headroom:.3, beat:.2}` | 候选打分权重 |

## 10. 测试策略

沿用「纯逻辑 + 注入 fake + Qt smoke」分层：

- `dialogue_segment_deriver`：纯函数 → 多 case 覆盖
- `_times_for_shot`：纯函数 → 4 case（1/3/5/非法）
- `segment_review_widget`：Qt smoke，mock QAudioOutput.setVolume
- `soundtrack_section`：Qt smoke，构造控件 + load/apply 往返
- `soundtrack_editor`：Qt smoke，注入 fake cfg.video_tasks + mock facade.prepare_session 验入参；mock QMessageBox 验重排路径

无新 vision/ffmpeg/Demucs 真调用。

## 11. 验收标准

1. **#1 修复**：拖动 segment_review 的音量滑条，**当下听到**音量变化（QAudioOutput 同步生效）
2. **#3 可配**：cfg `refine_frames_per_shot=1` → refine 每 shot 抽 1 帧；`=5` → 5 帧；非法值（如 2）raise
3. **§2-a**：`SoundtrackEditor` 调 `prepare_session` 时传非空 `dialogue_segments`（cfg.video_tasks 含匹配）；mix 阶段 Demucs `separate_vocals` 调用计数 = 0
4. **§2-b**：6 个 cfg 控件从 UI 可读写，cfg 字段值同步
5. **§2-c**：「🔄 重排段落」按钮：无候选时直接 `segments_refined=False`+ advance；有候选时弹二次确认；session.json 同步落盘
6. **§2-d**：全部新测试 + 现有 ~213 测试**零回归**

## 12. 范围边界

**本期不做**：
- Phase 4a「音乐选段 UX 大补强」（自定义段切 / per-segment style 覆写 / per-segment prompt 编辑）
- Phase 4b「SFX 音效层」（HunyuanVideo-Foley / MOSS-SoundEffect-v2.0 / AudioLCM 等）
- ACE Studio 风格的 Generative AI Kits（Inspire Me / Music Enhancer / Add a Layer）
- VST3 / DAW 插件

这些都是后续独立 phase，本期 Sprint 0 只是「把已交付后端能力曝光给 GUI 用户 + 修一个 bug」。
