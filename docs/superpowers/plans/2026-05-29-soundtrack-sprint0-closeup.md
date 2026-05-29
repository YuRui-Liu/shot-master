# 配乐 Sprint 0 闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 1+2+3 已落地的 6 个 cfg + dialogue_segments 复用 + 抽帧数可配 全部曝光到 GUI；修 segment_review 拖音量滑条不立即生效 bug；加重排段落按钮。

**Architecture:** 沿用 Phase 1/2/3 的「纯逻辑 + 薄 IO + 注入」分层。新增 1 个工具文件 `dialogue_segment_deriver.py`（纯函数），其余都是已有模块的小增量。`SoundtrackEditor` 调 `facade.prepare_session` 前派生 `dialogue_segments` 让 mix 跳 Demucs。`SoundtrackSection` 加 6 个 cfg 控件。`SegmentReviewWidget` 把音量滑条事件同步到 `QAudioOutput.setVolume`。

**Tech Stack:** Python 3.10+、PySide6（QMediaPlayer/QAudioOutput/QSpinBox/QComboBox/QDoubleSpinBox/QMessageBox）、`pytest`、`unittest.mock`。**无新外部依赖**。

参考 spec：`docs/superpowers/specs/2026-05-29-soundtrack-sprint0-closeup-design.md`

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `drama_shot_master/config.py` | + 6 个 cfg 字段 + 持久化 | 改 |
| `sound_track_agent/refine.py` | + `_times_for_shot(shot, frames_per_shot)` 纯函数；`refine_segments` 增 `frames_per_shot` kwarg | 改 |
| `sound_track_agent/stages_factory.py` | `build_stages` 增 `refine_frames_per_shot` kwarg 透传 | 改 |
| `sound_track_agent/facade.py` | `_build_real_stages` 读 cfg `refine_frames_per_shot` 透传 | 改 |
| **新** `drama_shot_master/core/dialogue_segment_deriver.py` | `derive_dialogue_segments(cfg, mp4_path)` 纯函数 | 建 |
| `drama_shot_master/ui/widgets/segment_review_widget.py` | `_on_volume` / `_on_candidate` 同步 `QAudioOutput.setVolume` | 改 |
| `drama_shot_master/ui/widgets/settings_sections/soundtrack_section.py` | + 6 个新控件 + load/apply | 改 |
| `drama_shot_master/ui/widgets/soundtrack_editor.py` | 调 facade 前派生 `dialogue_segments`；+ 重排按钮 | 改 |
| `tests/test_config/test_config_soundtrack_fields.py` | 新增 6 字段默认 + 持久化 | 建 |
| `tests/test_sound_track_agent/test_refine.py` | + frames_per_shot 系列测试 | 改 |
| `tests/test_sound_track_agent/test_stages_factory.py` | + 透传测试 | 改 |
| `tests/test_sound_track_agent/test_facade.py` | + cfg → build_stages 透传测试 | 改 |
| **新** `tests/test_core/test_dialogue_segment_deriver.py` | 派生工具测试 | 建 |
| `tests/test_ui/test_segment_review_smoke.py` | + 音量同步 QAudioOutput 测试 | 改 |
| `tests/test_ui/test_soundtrack_section_smoke.py`（**新**） | 6 个新控件 load/apply 测试 | 建 |
| `tests/test_ui/test_soundtrack_editor_smoke.py` | + dialogue_segments 接线 + 重排按钮测试 | 改 |

实现顺序按依赖：cfg → refine 纯逻辑 → 透传链 → dialogue_segment_deriver → volume bug → SoundtrackSection 控件 → SoundtrackEditor 接线。

---

## Task 1: `config.py` — 6 个新 cfg 字段

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_config/test_config_soundtrack_fields.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_config/test_config_soundtrack_fields.py`：

```python
"""验证 Sprint 0 新增的 6 个 cfg 字段默认值 + 持久化往返。"""
import json
from pathlib import Path

from drama_shot_master.config import Config, load_config


def test_new_fields_default_values():
    cfg = Config()
    assert cfg.refine_frames_per_shot == 3
    assert cfg.refine_max_segments == 5
    assert cfg.refine_merge_threshold == 0.25
    assert cfg.accent_max_stretch == 0.10
    assert cfg.soundtrack_max_concurrency == 3
    assert cfg.soundtrack_score_weights == {
        "health": 0.5, "headroom": 0.3, "beat": 0.2}


def test_load_config_returns_defaults_when_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=settings_path)
    assert cfg.refine_frames_per_shot == 3
    assert cfg.soundtrack_score_weights["health"] == 0.5


def test_load_config_reads_persisted_values(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "refine_frames_per_shot": 5,
        "refine_max_segments": 7,
        "refine_merge_threshold": 0.40,
        "accent_max_stretch": 0.15,
        "soundtrack_max_concurrency": 6,
        "soundtrack_score_weights": {"health": 0.6, "headroom": 0.2, "beat": 0.2},
    }), encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=settings_path)
    assert cfg.refine_frames_per_shot == 5
    assert cfg.refine_max_segments == 7
    assert cfg.refine_merge_threshold == 0.40
    assert cfg.accent_max_stretch == 0.15
    assert cfg.soundtrack_max_concurrency == 6
    assert cfg.soundtrack_score_weights == {"health": 0.6, "headroom": 0.2, "beat": 0.2}
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_config/test_config_soundtrack_fields.py -q`
Expected: FAIL（`Config` 无这些字段）

- [ ] **Step 3: 给 `Config` dataclass 加 6 个字段**

打开 `drama_shot_master/config.py`，在 `Config` 数据类末尾（最后一个 `field(default_factory=...)` 之后或所有 `: type = default` 之后）追加：

```python
    # Sprint 0：曝光 Phase 1+2+3 后端能力
    refine_frames_per_shot: int = 3                  # 1 / 3 / 5
    refine_max_segments: int = 5
    refine_merge_threshold: float = 0.25
    accent_max_stretch: float = 0.10
    soundtrack_max_concurrency: int = 3
    soundtrack_score_weights: dict = field(
        default_factory=lambda: {"health": 0.5, "headroom": 0.3, "beat": 0.2})
```

**确保 `field` 已在文件顶部 from dataclasses 导入**（如未导入，加 `from dataclasses import dataclass, field`）。

- [ ] **Step 4: 给 `load_config` / `save_config` 读写新字段**

在 `drama_shot_master/config.py` 的 `load_config` 函数体里，找到现有 `if "video_tasks" in data:` 那类 setattr 模式，在其后追加（与现有字段同位置同风格）：

```python
                # Sprint 0 新字段
                for fld, caster in [
                    ("refine_frames_per_shot", int),
                    ("refine_max_segments", int),
                    ("refine_merge_threshold", float),
                    ("accent_max_stretch", float),
                    ("soundtrack_max_concurrency", int),
                ]:
                    if fld in data:
                        try:
                            setattr(cfg, fld, caster(data[fld]))
                        except (TypeError, ValueError):
                            pass
                if "soundtrack_score_weights" in data \
                        and isinstance(data["soundtrack_score_weights"], dict):
                    cfg.soundtrack_score_weights = dict(data["soundtrack_score_weights"])
```

在 `save_config`（如有）或 `to_dict` 序列化路径（找到现有 `"video_tasks": self.video_tasks` 那段）追加同级：

```python
                "refine_frames_per_shot": self.refine_frames_per_shot,
                "refine_max_segments": self.refine_max_segments,
                "refine_merge_threshold": self.refine_merge_threshold,
                "accent_max_stretch": self.accent_max_stretch,
                "soundtrack_max_concurrency": self.soundtrack_max_concurrency,
                "soundtrack_score_weights": dict(self.soundtrack_score_weights),
```

> 注：先 Read `drama_shot_master/config.py` 找到现有持久化路径的真实结构，按其实际模式追加（变量名可能是 `data`/`settings`/`raw`）。

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_config/test_config_soundtrack_fields.py -q`
Expected: PASS（3 个用例）

- [ ] **Step 6: 跑整套 config 测试零回归**

Run: `python -m pytest tests/test_config/ -q`
Expected: 全绿

- [ ] **Step 7: 提交**

```bash
git add drama_shot_master/config.py tests/test_config/test_config_soundtrack_fields.py
git commit -m "feat(config): + 6 个 Sprint 0 cfg 字段（refine_*/accent_max_stretch/soundtrack_*）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `refine.py` — `_times_for_shot` 纯函数 + `frames_per_shot` kwarg

**Files:**
- Modify: `sound_track_agent/refine.py`
- Test: `tests/test_sound_track_agent/test_refine.py`

- [ ] **Step 1: 写失败测试** — 追加到 `tests/test_sound_track_agent/test_refine.py`：

```python
from sound_track_agent.refine import _times_for_shot, refine_segments
from sound_track_agent.segment_planner import Shot


def test_times_for_shot_short_shot_returns_single_mid():
    """duration ≤ 0.1s 永远退化单帧，无论 frames_per_shot 是几。"""
    shot = Shot(index=0, t_start=1.000, t_end=1.050)   # 50ms
    assert _times_for_shot(shot, frames_per_shot=3) == [1.025]
    assert _times_for_shot(shot, frames_per_shot=5) == [1.025]


def test_times_for_shot_one_returns_mid_only():
    shot = Shot(index=0, t_start=0.0, t_end=4.0)
    assert _times_for_shot(shot, frames_per_shot=1) == [2.0]


def test_times_for_shot_three_returns_start_mid_end():
    shot = Shot(index=0, t_start=0.0, t_end=4.0)
    times = _times_for_shot(shot, frames_per_shot=3)
    assert times == [0.05, 2.0, 3.95]


def test_times_for_shot_five_returns_start_q_mid_q_end():
    shot = Shot(index=0, t_start=0.0, t_end=4.0)
    times = _times_for_shot(shot, frames_per_shot=5)
    # mid=2.0, q=(2.0-0.0)/2=1.0
    assert times == [0.05, 1.0, 2.0, 3.0, 3.95]


def test_times_for_shot_invalid_raises():
    import pytest
    shot = Shot(index=0, t_start=0.0, t_end=4.0)
    with pytest.raises(ValueError):
        _times_for_shot(shot, frames_per_shot=2)
    with pytest.raises(ValueError):
        _times_for_shot(shot, frames_per_shot=0)


def test_refine_segments_passes_frames_per_shot_to_extract(tmp_path):
    """注入 frames_per_shot=5，断言 extract_frames 收到 5 个时间点。"""
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, EmotionTag,
    )
    sess = ScoringSession(source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
                          global_style="末日", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0)])
    captured = {"times_lens": []}

    def fake_extract(v, times, out_dir):
        captured["times_lens"].append(len(times))
        from pathlib import Path
        return [Path(out_dir) / f"f{i}.png" for i in range(len(times))]

    refine_segments(
        sess, video_path=tmp_path / "ep.mp4", work_dir=tmp_path / "w",
        provider=None, global_style="末日",
        frames_per_shot=5,
        detect=lambda v: [Shot(0, 0.0, 4.0)],
        extract_frames=fake_extract,
        tag_fn=lambda paths: EmotionTag())
    assert captured["times_lens"] == [5]
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_refine.py -q`
Expected: FAIL（`_times_for_shot` 不存在 / `refine_segments` 不接受 `frames_per_shot`）

- [ ] **Step 3: 实现 `_times_for_shot`**

在 `sound_track_agent/refine.py` 顶部、`_MIN_MULTIFRAME_DUR` 常量之后，**新增**：

```python
def _times_for_shot(shot, frames_per_shot: int) -> list[float]:
    """按 frames_per_shot 出抽帧时间点；duration ≤ _MIN_MULTIFRAME_DUR 永远退化单帧 mid。

    frames_per_shot 必须 ∈ {1, 3, 5}，否则抛 ValueError。
    """
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

- [ ] **Step 4: 给 `refine_segments` 加 `frames_per_shot` kwarg + 调用 `_times_for_shot`**

把 `refine_segments` 函数签名改为（加 `frames_per_shot: int = 3` 在 `merge_threshold` 之后）：

```python
def refine_segments(session: ScoringSession, *, video_path, work_dir,
                    provider, global_style: str,
                    max_segments: int = 5,
                    merge_threshold: float = 0.25,
                    frames_per_shot: int = 3,
                    detect: Optional[Callable] = None,
                    extract_frames: Optional[Callable] = None,
                    tag_fn: Optional[Callable] = None) -> bool:
```

把函数体里原本计算 `times` 的那段（约第 64-67 行）：

```python
            mid = (shot.t_start + shot.t_end) / 2.0
            duration = shot.t_end - shot.t_start
            if duration <= _MIN_MULTIFRAME_DUR:
                times = [mid]
            else:
                times = [shot.t_start + 0.05, mid, shot.t_end - 0.05]
```

替换为单行调用：

```python
            times = _times_for_shot(shot, frames_per_shot)
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_refine.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 提交**

```bash
git add sound_track_agent/refine.py tests/test_sound_track_agent/test_refine.py
git commit -m "feat(soundtrack): refine 加 _times_for_shot + frames_per_shot kwarg（可配 1/3/5）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `stages_factory` + `facade` 透传 `refine_frames_per_shot`

**Files:**
- Modify: `sound_track_agent/stages_factory.py`
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_stages_factory.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

- [ ] **Step 1: 写失败测试** — 追加到 `tests/test_sound_track_agent/test_stages_factory.py`：

```python
def test_build_stages_threads_refine_frames_per_shot(tmp_path, monkeypatch):
    """build_stages 收到 refine_frames_per_shot=5 → refine 闭包调 refine_segments 时也用 5。"""
    captured = {"frames_per_shot": None}

    def fake_refine_segments(sess, **kwargs):
        captured["frames_per_shot"] = kwargs.get("frames_per_shot")
        return True

    import sound_track_agent.refine as refine_mod
    monkeypatch.setattr(refine_mod, "refine_segments", fake_refine_segments)

    stages = build_stages(
        provider=None, client=None, workflow_id="wf", work_dir=tmp_path,
        global_style="末日", seeds=[1],
        frame_provider=lambda seg: tmp_path / "f.png",
        video_path=tmp_path / "ep.mp4",
        refine_frames_per_shot=5)
    assert stages.refine_segments is not None
    stages.refine_segments(None)        # 触发闭包
    assert captured["frames_per_shot"] == 5
```

追加到 `tests/test_sound_track_agent/test_facade.py`：

```python
def test_build_real_stages_reads_refine_frames_per_shot_from_cfg(tmp_path, monkeypatch):
    """facade._build_real_stages 把 cfg.refine_frames_per_shot 透传给 build_stages。"""
    captured = {"frames_per_shot": None}

    def fake_build_stages(**kwargs):
        captured["frames_per_shot"] = kwargs.get("refine_frames_per_shot")
        from sound_track_agent.pipeline import Stages
        return Stages(
            tag_emotion=lambda seg, s: None,
            compose_prompt=lambda seg, s: "",
            generate=lambda seg, s: [],
            align=lambda s: None, mix=lambda s: "")

    import sound_track_agent.facade as fac
    monkeypatch.setattr(fac, "build_stages", fake_build_stages)

    class _Cfg:
        refine_frames_per_shot = 5
        soundtrack_score_weights = None      # 走 default

    fac._build_real_stages(_Cfg(), workflow_id="wf",
                            work_dir=tmp_path, global_style="x",
                            seeds_count=2, video_path=str(tmp_path / "ep.mp4"))
    assert captured["frames_per_shot"] == 5
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_stages_factory.py tests/test_sound_track_agent/test_facade.py -q -k "frames_per_shot"`
Expected: FAIL（`build_stages` 不接受 `refine_frames_per_shot` / `_build_real_stages` 没传）

- [ ] **Step 3: 改 `stages_factory.build_stages` 接收并透传 `refine_frames_per_shot`**

在 `sound_track_agent/stages_factory.py` 的 `build_stages` 签名末尾加：

```python
                 refine_frames_per_shot: int = 3,        # 新
                 ) -> Stages:
```

在 `refine_segments_fn` 闭包里加传：

```python
    def refine_segments_fn(sess):
        from sound_track_agent import refine
        return refine.refine_segments(
            sess, video_path=video_path, work_dir=work_dir,
            provider=provider, global_style=global_style,
            max_segments=refine_max_segments,
            merge_threshold=refine_merge_threshold,
            frames_per_shot=refine_frames_per_shot)
```

- [ ] **Step 4: 改 `facade._build_real_stages` 从 cfg 读 + 传**

在 `sound_track_agent/facade.py` 的 `_build_real_stages` 末尾 `build_stages(...)` 调用里追加一行（与 `refine_max_segments / refine_merge_threshold` 同级）：

```python
        refine_frames_per_shot=int(getattr(cfg, "refine_frames_per_shot", 3)),
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_stages_factory.py tests/test_sound_track_agent/test_facade.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 跑整套 sound_track_agent 测试零回归**

Run: `python -m pytest tests/test_sound_track_agent/ -q`
Expected: 全绿

- [ ] **Step 7: 提交**

```bash
git add sound_track_agent/stages_factory.py sound_track_agent/facade.py \
    tests/test_sound_track_agent/test_stages_factory.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(soundtrack): stages_factory + facade 透传 refine_frames_per_shot

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `dialogue_segment_deriver.py` — 派生工具（新模块）

**Files:**
- Create: `drama_shot_master/core/dialogue_segment_deriver.py`
- Test: `tests/test_core/test_dialogue_segment_deriver.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_core/test_dialogue_segment_deriver.py`：

```python
"""验证 derive_dialogue_segments：从 cfg.video_tasks 按 mp4 路径匹配派生 DialogueSegment。"""
from drama_shot_master.core.dialogue_segment_deriver import derive_dialogue_segments
from sound_track_agent.session import DialogueSegment


class _FakeCfg:
    def __init__(self, video_tasks):
        self.video_tasks = video_tasks


def test_derive_returns_empty_when_no_match():
    cfg = _FakeCfg([{"last_result": "/x/other.mp4", "timeline": {}}])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []


def test_derive_returns_empty_when_no_video_tasks():
    cfg = _FakeCfg([])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []


def test_derive_returns_empty_when_cfg_has_no_attr():
    """cfg 没 video_tasks 属性也不抛。"""
    class _Bare: pass
    assert derive_dialogue_segments(_Bare(), "/x/ep.mp4") == []


def test_derive_matches_by_last_result_and_converts_frames():
    cfg = _FakeCfg([{
        "last_result": "/x/ep.mp4",
        "timeline": {
            "frame_rate": 24.0,
            "audios": [
                {"audio_id": "a1", "audio_path": "/x/d1.flac",
                 "start_frame": 0, "length_frames": 24},
                {"audio_id": "a2", "audio_path": "/x/d2.flac",
                 "start_frame": 48, "length_frames": 36},
            ],
        },
    }])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert len(segs) == 2
    assert segs[0] == DialogueSegment(audio_path="/x/d1.flac",
                                       t_start=0.0, duration=1.0)
    assert segs[1] == DialogueSegment(audio_path="/x/d2.flac",
                                       t_start=2.0, duration=1.5)


def test_derive_first_match_wins_when_multiple_tasks():
    cfg = _FakeCfg([
        {"last_result": "/x/other.mp4", "timeline": {}},
        {"last_result": "/x/ep.mp4", "timeline": {
            "frame_rate": 30.0,
            "audios": [{"audio_path": "/x/d.flac",
                        "start_frame": 30, "length_frames": 60}]}},
        {"last_result": "/x/ep.mp4", "timeline": {}},   # 不应被命中
    ])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert len(segs) == 1
    assert segs[0].t_start == 1.0
    assert segs[0].duration == 2.0


def test_derive_skips_audios_missing_audio_path():
    cfg = _FakeCfg([{
        "last_result": "/x/ep.mp4",
        "timeline": {"frame_rate": 24.0, "audios": [
            {"audio_path": "/x/d1.flac", "start_frame": 0, "length_frames": 24},
            {"audio_path": "", "start_frame": 24, "length_frames": 24},   # 跳过
            {"start_frame": 48, "length_frames": 24},                    # 跳过
        ]},
    }])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert len(segs) == 1
    assert segs[0].audio_path == "/x/d1.flac"


def test_derive_handles_zero_or_missing_frame_rate():
    """frame_rate=0 或缺 → fallback 24.0。"""
    cfg = _FakeCfg([{
        "last_result": "/x/ep.mp4",
        "timeline": {
            # 无 frame_rate
            "audios": [{"audio_path": "/x/d.flac",
                        "start_frame": 24, "length_frames": 48}],
        },
    }])
    segs = derive_dialogue_segments(cfg, "/x/ep.mp4")
    assert segs[0].t_start == 1.0       # 24/24
    assert segs[0].duration == 2.0      # 48/24


def test_derive_handles_missing_timeline_or_audios():
    cfg = _FakeCfg([
        {"last_result": "/x/ep.mp4"},                         # 无 timeline
    ])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []

    cfg = _FakeCfg([
        {"last_result": "/x/ep.mp4", "timeline": {}},         # timeline 无 audios
    ])
    assert derive_dialogue_segments(cfg, "/x/ep.mp4") == []
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_core/test_dialogue_segment_deriver.py -q`
Expected: FAIL（`dialogue_segment_deriver` 模块不存在）

- [ ] **Step 3: 实现 `dialogue_segment_deriver.py`**

新建 `drama_shot_master/core/dialogue_segment_deriver.py`：

```python
"""按 mp4 路径匹配 cfg.video_tasks 派生 DialogueSegment 列表。

供 SoundtrackEditor 在调 facade.prepare_session 前调用，让 mix 阶段跳过 Demucs 盲分离。
匹配不到（用户手工导入 MP4 / VideoTask 无 audio / 字段缺失）→ 返回 []，
caller 不传 dialogue_segments → mix 阶段按原回退路径走 Demucs（零回归）。

零外部依赖（除 DialogueSegment），可单测。
"""
from __future__ import annotations

from sound_track_agent.session import DialogueSegment


def derive_dialogue_segments(cfg, mp4_path: str) -> list[DialogueSegment]:
    """扫 cfg.video_tasks，找 last_result == mp4_path 的第一个 task，
    从其 timeline.audios 派生 DialogueSegment（frame → 秒）。

    所有失败路径（无 video_tasks / 无匹配 / 缺字段 / fps=0）都安全返回空列表，不抛。
    """
    video_tasks = getattr(cfg, "video_tasks", None) or []
    for task in video_tasks:
        if str(task.get("last_result", "")) != str(mp4_path):
            continue
        timeline = task.get("timeline") or {}
        try:
            fps = float(timeline.get("frame_rate", 24.0)) or 24.0
        except (TypeError, ValueError):
            fps = 24.0
        audios = timeline.get("audios") or []
        result: list[DialogueSegment] = []
        for a in audios:
            audio_path = a.get("audio_path") if isinstance(a, dict) else None
            if not audio_path:
                continue
            try:
                result.append(DialogueSegment(
                    audio_path=str(audio_path),
                    t_start=float(a["start_frame"]) / fps,
                    duration=float(a["length_frames"]) / fps,
                ))
            except (TypeError, ValueError, KeyError):
                continue
        return result
    return []
```

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_core/test_dialogue_segment_deriver.py -q`
Expected: PASS（8 个用例）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/dialogue_segment_deriver.py tests/test_core/test_dialogue_segment_deriver.py
git commit -m "feat(core): + dialogue_segment_deriver（按 mp4 路径派生 DialogueSegment）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `segment_review_widget.py` — Volume Bug 修复

**Files:**
- Modify: `drama_shot_master/ui/widgets/segment_review_widget.py`
- Test: `tests/test_ui/test_segment_review_smoke.py`

- [ ] **Step 1: 写失败测试** — 追加到 `tests/test_ui/test_segment_review_smoke.py`：

```python
def test_volume_slider_syncs_to_audio_output(app, tmp_path):
    """拖音量滑条时，如果正在播该段候选，QAudioOutput.setVolume 应被同步调用。"""
    from unittest.mock import MagicMock
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate,
    )
    from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget

    bgm = tmp_path / "b.mp3"; bgm.write_bytes(b"BGM")
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(
                              index=0, t_start=0.0, t_end=2.0,
                              candidates=[BGMCandidate(
                                  path=str(bgm), seed=1, prompt="t")])])
    w = SegmentReviewWidget(sess)
    # 模拟"当前正在播 seg0 候选 0"
    w._playing_key = (0, 0)
    w._audio = MagicMock()
    w._player = MagicMock()

    # 拖滑条到 50%
    w._on_volume(sess.segments[0], 50, MagicMock())
    w._audio.setVolume.assert_called_once_with(0.5)
    assert sess.segments[0].volume == 0.5


def test_volume_slider_not_called_when_not_playing_that_segment(app, tmp_path):
    """没在播该段时滑条事件不调 setVolume（避免影响其它段的播放）。"""
    from unittest.mock import MagicMock
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate,
    )
    from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget

    bgm = tmp_path / "b.mp3"; bgm.write_bytes(b"BGM")
    seg0 = SegmentScore(index=0, t_start=0.0, t_end=2.0,
                        candidates=[BGMCandidate(path=str(bgm), seed=1, prompt="t")])
    seg1 = SegmentScore(index=1, t_start=2.0, t_end=4.0,
                        candidates=[BGMCandidate(path=str(bgm), seed=2, prompt="t")])
    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=[seg0, seg1])
    w = SegmentReviewWidget(sess)
    w._playing_key = (0, 0)              # 正在播 seg0
    w._audio = MagicMock()
    w._player = MagicMock()

    # 拖 seg1 的滑条
    w._on_volume(seg1, 80, MagicMock())
    w._audio.setVolume.assert_not_called()
    assert seg1.volume == 0.8            # 但 seg.volume 仍持久化
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_ui/test_segment_review_smoke.py::test_volume_slider_syncs_to_audio_output -v`
Expected: FAIL（`_on_volume` 没调 `_audio.setVolume`）

- [ ] **Step 3: 改 `_on_volume` 同步播放器**

在 `drama_shot_master/ui/widgets/segment_review_widget.py` 的 `_on_volume` 方法末尾追加：

```python
    def _on_volume(self, seg, val: int, label):
        seg.volume = val / 100.0
        label.setText(f"{val}%")
        self.segmentVolumeChanged.emit()
        # 拖滑条时如果正在播这段的候选 → 立即更新 QAudioOutput
        if (self._player is not None and self._playing_key is not None
                and self._playing_key[0] == seg.index):
            self._audio.setVolume(min(1.0, max(0.0, float(seg.volume))))
```

- [ ] **Step 4: 改 `_on_candidate` 开播时初始化音量**

在 `_on_candidate` 中 `player.setSource(...)` 之后、`player.play()` 之前插入：

```python
        player.setSource(QUrl.fromLocalFile(path))
        # 开播前按当前 seg.volume 初始化一次
        self._audio.setVolume(
            min(1.0, max(0.0, float(getattr(seg, "volume", 1.0)))))
        self._playing_key = (seg_index, cand_index)
        player.play()
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_ui/test_segment_review_smoke.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/widgets/segment_review_widget.py tests/test_ui/test_segment_review_smoke.py
git commit -m "fix(ui): segment_review 拖音量滑条立即同步 QAudioOutput（修候选试听音量 bug）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `SoundtrackSection` — 6 个新控件

**Files:**
- Modify: `drama_shot_master/ui/widgets/settings_sections/soundtrack_section.py`
- Test: `tests/test_ui/test_soundtrack_section_smoke.py`（新建）

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_soundtrack_section_smoke.py`：

```python
"""SoundtrackSection 6 个新控件存在 + load/apply cfg 往返。"""
import pytest
from PySide6.QtWidgets import QApplication

from drama_shot_master.config import Config
from drama_shot_master.ui.widgets.settings_sections.soundtrack_section \
    import SoundtrackSection


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_section_has_all_six_new_controls(app):
    cfg = Config()
    section = SoundtrackSection(cfg)
    # 6 个新控件名称（实现里要用这些 attribute 名）
    for attr in ["frames_combo", "refine_max_spin", "refine_thresh_spin",
                 "stretch_spin", "concurrency_spin",
                 "w_health", "w_headroom", "w_beat"]:
        assert hasattr(section, attr), f"缺控件 {attr}"


def test_load_from_populates_controls(app):
    cfg = Config()
    cfg.refine_frames_per_shot = 5
    cfg.refine_max_segments = 8
    cfg.refine_merge_threshold = 0.30
    cfg.accent_max_stretch = 0.20
    cfg.soundtrack_max_concurrency = 6
    cfg.soundtrack_score_weights = {"health": 0.7, "headroom": 0.2, "beat": 0.1}
    section = SoundtrackSection(cfg)
    section.load_from(cfg)
    assert section.frames_combo.currentText() == "5"
    assert section.refine_max_spin.value() == 8
    assert abs(section.refine_thresh_spin.value() - 0.30) < 1e-6
    assert abs(section.stretch_spin.value() - 0.20) < 1e-6
    assert section.concurrency_spin.value() == 6
    assert abs(section.w_health.value() - 0.7) < 1e-6
    assert abs(section.w_headroom.value() - 0.2) < 1e-6
    assert abs(section.w_beat.value() - 0.1) < 1e-6


def test_apply_to_writes_back_to_cfg(app):
    cfg = Config()
    section = SoundtrackSection(cfg)
    section.frames_combo.setCurrentText("5")
    section.refine_max_spin.setValue(7)
    section.refine_thresh_spin.setValue(0.40)
    section.stretch_spin.setValue(0.15)
    section.concurrency_spin.setValue(4)
    section.w_health.setValue(0.6)
    section.w_headroom.setValue(0.3)
    section.w_beat.setValue(0.1)
    section.apply_to(cfg)
    assert cfg.refine_frames_per_shot == 5
    assert cfg.refine_max_segments == 7
    assert abs(cfg.refine_merge_threshold - 0.40) < 1e-6
    assert abs(cfg.accent_max_stretch - 0.15) < 1e-6
    assert cfg.soundtrack_max_concurrency == 4
    assert cfg.soundtrack_score_weights == {
        "health": 0.6, "headroom": 0.3, "beat": 0.1}
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_ui/test_soundtrack_section_smoke.py -q`
Expected: FAIL（控件不存在 / load_from/apply_to 不支持新字段）

- [ ] **Step 3: 在 `SoundtrackSection._build_ui` 末尾追加 6 个控件**

打开 `drama_shot_master/ui/widgets/settings_sections/soundtrack_section.py`。

先在顶部 import 加：

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QSpinBox,
    QDoubleSpinBox, QHBoxLayout, QFileDialog, QComboBox, QLabel,
)
```

在 `_build_ui` 方法尾部（`form` 已 addRow 完原有字段、`big_thresh_spin` 之后），追加：

```python
        # === Sprint 0：曝光 Phase 1+2+3 后端能力 ===

        self.frames_combo = QComboBox()
        self.frames_combo.addItems(["1", "3", "5"])
        form.addRow("精排抽帧数 (1/3/5)", self.frames_combo)

        self.refine_max_spin = QSpinBox()
        self.refine_max_spin.setRange(1, 10)
        form.addRow("邻接合并段数上限", self.refine_max_spin)

        self.refine_thresh_spin = QDoubleSpinBox()
        self.refine_thresh_spin.setRange(0.0, 1.0)
        self.refine_thresh_spin.setSingleStep(0.05)
        self.refine_thresh_spin.setDecimals(2)
        form.addRow("邻接合并相似阈值", self.refine_thresh_spin)

        self.stretch_spin = QDoubleSpinBox()
        self.stretch_spin.setRange(0.0, 0.5)
        self.stretch_spin.setSingleStep(0.01)
        self.stretch_spin.setDecimals(2)
        form.addRow("真·卡点拉伸上限 (±)", self.stretch_spin)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 10)
        form.addRow("生成并发上限", self.concurrency_spin)

        # 打分权重三轴
        weights_row = QHBoxLayout()
        self.w_health = QDoubleSpinBox()
        self.w_health.setRange(0.0, 1.0); self.w_health.setSingleStep(0.05); self.w_health.setDecimals(2)
        self.w_headroom = QDoubleSpinBox()
        self.w_headroom.setRange(0.0, 1.0); self.w_headroom.setSingleStep(0.05); self.w_headroom.setDecimals(2)
        self.w_beat = QDoubleSpinBox()
        self.w_beat.setRange(0.0, 1.0); self.w_beat.setSingleStep(0.05); self.w_beat.setDecimals(2)
        weights_row.addWidget(QLabel("health"))
        weights_row.addWidget(self.w_health)
        weights_row.addWidget(QLabel("headroom"))
        weights_row.addWidget(self.w_headroom)
        weights_row.addWidget(QLabel("beat"))
        weights_row.addWidget(self.w_beat)
        weights_wrap = QWidget()
        weights_wrap.setLayout(weights_row)
        form.addRow("候选打分权重", weights_wrap)
```

- [ ] **Step 4: 改 `load_from` 同步读 cfg 6 项**

找到现有 `load_from` 方法，在末尾追加：

```python
        self.frames_combo.setCurrentText(
            str(int(getattr(cfg, "refine_frames_per_shot", 3))))
        self.refine_max_spin.setValue(int(getattr(cfg, "refine_max_segments", 5)))
        self.refine_thresh_spin.setValue(
            float(getattr(cfg, "refine_merge_threshold", 0.25)))
        self.stretch_spin.setValue(float(getattr(cfg, "accent_max_stretch", 0.10)))
        self.concurrency_spin.setValue(
            int(getattr(cfg, "soundtrack_max_concurrency", 3)))
        w = getattr(cfg, "soundtrack_score_weights", None) \
            or {"health": 0.5, "headroom": 0.3, "beat": 0.2}
        self.w_health.setValue(float(w.get("health", 0.5)))
        self.w_headroom.setValue(float(w.get("headroom", 0.3)))
        self.w_beat.setValue(float(w.get("beat", 0.2)))
```

- [ ] **Step 5: 改 `apply_to` 写回 cfg 6 项**

找到现有 `apply_to` 方法（如缺，新增；与 `load_from` 对称），在末尾追加：

```python
        cfg.refine_frames_per_shot = int(self.frames_combo.currentText())
        cfg.refine_max_segments = self.refine_max_spin.value()
        cfg.refine_merge_threshold = float(self.refine_thresh_spin.value())
        cfg.accent_max_stretch = float(self.stretch_spin.value())
        cfg.soundtrack_max_concurrency = self.concurrency_spin.value()
        cfg.soundtrack_score_weights = {
            "health": float(self.w_health.value()),
            "headroom": float(self.w_headroom.value()),
            "beat": float(self.w_beat.value()),
        }
```

> 若文件里没有 `apply_to`，先 Read 文件确认现有方法名（可能叫 `save_to_cfg` / `write_back` 等）；按其真名追加同样逻辑。

- [ ] **Step 6: 运行，确认通过**

Run: `python -m pytest tests/test_ui/test_soundtrack_section_smoke.py -q`
Expected: PASS（3 个用例）

- [ ] **Step 7: 跑 UI smoke 测试零回归**

Run: `python -m pytest tests/test_ui/ -q`
Expected: 全绿

- [ ] **Step 8: 提交**

```bash
git add drama_shot_master/ui/widgets/settings_sections/soundtrack_section.py \
    tests/test_ui/test_soundtrack_section_smoke.py
git commit -m "feat(ui): SoundtrackSection 加 6 个 cfg 控件（精排/卡点/并发/打分权重）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `SoundtrackEditor` — dialogue_segments 接线 + 重排按钮

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_soundtrack_editor_smoke.py`

- [ ] **Step 1: 写失败测试** — 追加到 `tests/test_ui/test_soundtrack_editor_smoke.py`：

```python
def test_editor_passes_derived_dialogue_segments_to_prepare(app, tmp_path, monkeypatch):
    """SoundtrackEditor 第一次跑 pipeline 时，应从 cfg.video_tasks 派生 dialogue_segments 并传给 prepare_session。"""
    from unittest.mock import MagicMock
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from drama_shot_master.config import Config
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, DialogueSegment,
    )

    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    cfg = Config()
    cfg.video_tasks = [{
        "last_result": str(mp4),
        "timeline": {
            "frame_rate": 24.0,
            "audios": [{"audio_path": "/x/d.flac",
                        "start_frame": 0, "length_frames": 24}],
        }
    }]

    captured = {"dialogue_segments": None}
    fake_sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                                global_style="末日", frame_rate=24.0,
                                segments=[SegmentScore(0, 0.0, 2.0)])

    def fake_prepare_session(mp4_arg, style, work_dir, **kwargs):
        captured["dialogue_segments"] = kwargs.get("dialogue_segments")
        return fake_sess

    import sound_track_agent.facade as fac
    monkeypatch.setattr(fac, "load_session", lambda wd: None)
    monkeypatch.setattr(fac, "prepare_session", fake_prepare_session)
    monkeypatch.setattr(fac, "advance",
                        lambda sess, wd, **kw: sess)

    task = {"id": "t1", "name": "测试", "mp4": str(mp4), "style": "末日",
            "workflow_id": "wf"}
    editor = SoundtrackEditor(task, cfg, None)
    editor._run_pipeline("refine_segments")

    assert captured["dialogue_segments"] is not None
    assert len(captured["dialogue_segments"]) == 1
    assert captured["dialogue_segments"][0] == DialogueSegment(
        audio_path="/x/d.flac", t_start=0.0, duration=1.0)


def test_editor_no_dialogue_segments_when_no_match(app, tmp_path, monkeypatch):
    """cfg.video_tasks 无匹配时不应传 dialogue_segments（=None，走 Demucs 回退）。"""
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from drama_shot_master.config import Config
    from sound_track_agent.session import ScoringSession, SegmentScore

    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    cfg = Config()
    cfg.video_tasks = [{"last_result": "/x/other.mp4", "timeline": {}}]

    captured = {"dialogue_segments": "<unset>"}
    fake_sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                                global_style="末日", frame_rate=24.0,
                                segments=[SegmentScore(0, 0.0, 2.0)])

    def fake_prepare_session(mp4_arg, style, work_dir, **kwargs):
        captured["dialogue_segments"] = kwargs.get("dialogue_segments", "<unset>")
        return fake_sess

    import sound_track_agent.facade as fac
    monkeypatch.setattr(fac, "load_session", lambda wd: None)
    monkeypatch.setattr(fac, "prepare_session", fake_prepare_session)
    monkeypatch.setattr(fac, "advance",
                        lambda sess, wd, **kw: sess)

    task = {"id": "t1", "name": "测试", "mp4": str(mp4), "style": "末日",
            "workflow_id": "wf"}
    editor = SoundtrackEditor(task, cfg, None)
    editor._run_pipeline("refine_segments")
    # caller 传 None（兼容 Phase 2 接口默认值），不强制传空 list
    assert captured["dialogue_segments"] is None


def test_resegment_button_resets_flag_and_runs_refine(app, tmp_path, monkeypatch):
    """重排按钮：有候选 → 弹确认 + 清空候选 + segments_refined=False + 跑 refine。"""
    from unittest.mock import MagicMock
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from drama_shot_master.config import Config
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate, EmotionTag,
    )
    from PySide6.QtWidgets import QMessageBox

    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"x")
    cfg = Config()
    task = {"id": "t1", "name": "测试", "mp4": str(mp4), "style": "末日",
            "workflow_id": "wf"}
    editor = SoundtrackEditor(task, cfg, None)

    sess = ScoringSession(source_mp4=str(mp4), source_hash="h",
                          global_style="末日", frame_rate=24.0,
                          segments=[SegmentScore(
                              0, 0.0, 2.0, status="generated",
                              candidates=[BGMCandidate(path="/b.mp3", seed=1, prompt="t")],
                              chosen_candidate=0, music_prompt="x",
                              emotion=EmotionTag())])
    sess.segments_refined = True
    editor._session = sess

    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: QMessageBox.Yes)
    captured = {"stop_after": None}
    monkeypatch.setattr(editor, "_run_pipeline",
                        lambda stop_after: captured.__setitem__("stop_after", stop_after))

    editor._on_resegment()

    assert sess.segments_refined is False
    assert sess.segments[0].candidates == []
    assert sess.segments[0].chosen_candidate is None
    assert sess.segments[0].music_prompt == ""
    assert sess.segments[0].emotion is None
    assert sess.segments[0].status == "pending"
    assert captured["stop_after"] == "refine_segments"


def test_resegment_button_warns_when_no_session(app, tmp_path):
    """没 session 时点重排按钮 → 提示，不抛。"""
    from unittest.mock import MagicMock, patch
    from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
    from drama_shot_master.config import Config

    cfg = Config()
    task = {"id": "t1", "name": "测试", "mp4": str(tmp_path / "ep.mp4"),
            "style": "末日", "workflow_id": "wf"}
    editor = SoundtrackEditor(task, cfg, None)
    editor._session = None

    from PySide6.QtWidgets import QMessageBox
    with patch.object(QMessageBox, "warning") as warn:
        editor._on_resegment()
        warn.assert_called_once()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_ui/test_soundtrack_editor_smoke.py -q -k "dialogue_segments or resegment"`
Expected: FAIL（`_run_pipeline` 没派生/没传 dialogue_segments；`_on_resegment` 方法不存在）

- [ ] **Step 3: 改 `_run_pipeline` 派生 + 传 dialogue_segments**

打开 `drama_shot_master/ui/widgets/soundtrack_editor.py`。在文件顶部 import 区加：

```python
from drama_shot_master.core.dialogue_segment_deriver import derive_dialogue_segments
```

找到 `_run_pipeline` 方法（约 207 行附近），找到这段：

```python
            sess = facade.load_session(work_dir) or facade.prepare_session(
                mp4, style, work_dir)
```

替换为：

```python
            sess = facade.load_session(work_dir)
            if sess is None:
                dialogue_segs = derive_dialogue_segments(self.cfg, mp4) or None
                sess = facade.prepare_session(
                    mp4, style, work_dir, dialogue_segments=dialogue_segs)
```

- [ ] **Step 4: 加重排按钮 + `_on_resegment` handler**

在 `_build_ui` 中找到「🎬 开始配乐」按钮（`self.btn_start`）那行，在其后插入：

```python
        self.btn_resegment = QPushButton("🔄 重排段落")
        self.btn_resegment.clicked.connect(self._on_resegment)
```

并把 `btn_resegment` addWidget 到包含 `btn_start` 的同一 layout（查上下文确认 layout 变量名）：

```python
        # 与现有 btn_start.addWidget(...) 的同一 layout
        <same_layout>.addWidget(self.btn_resegment)
```

在 class 末尾（其他 `def _on_*` 方法附近）新增 `_on_resegment` 方法：

```python
    def _on_resegment(self):
        """🔄 重排段落：清空已有候选/prompt/emotion，重置 segments_refined，重跑 refine 阶段。"""
        if not self._session:
            QMessageBox.warning(self, "无法重排", "请先开始配乐生成 session")
            return
        # 安全护栏：已有候选 → 二次确认
        if any(s.candidates for s in self._session.segments):
            if QMessageBox.warning(
                    self, "重排会清空候选",
                    "已有 BGM 候选会被清空丢弃，确定重排？",
                    QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
                return
        # 清空候选/prompt/emotion/status
        for s in self._session.segments:
            s.candidates = []
            s.chosen_candidate = None
            s.music_prompt = ""
            s.status = "pending"
            s.emotion = None
        self._session.segments_refined = False
        self._session.save(self._work_dir() / "session.json")
        # 重跑 refine 阶段
        self._run_pipeline("refine_segments")
```

确认 `QMessageBox` 已在 import 区导入；若无则：

```python
from PySide6.QtWidgets import QMessageBox
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_ui/test_soundtrack_editor_smoke.py -q`
Expected: PASS（含原有用例）

- [ ] **Step 6: 跑整套 UI + agent + config 测试零回归**

Run: `python -m pytest tests/test_sound_track_agent/ tests/test_ui/ tests/test_core/test_dialogue_segment_deriver.py tests/test_config/ -q`
Expected: 全绿

- [ ] **Step 7: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py \
    tests/test_ui/test_soundtrack_editor_smoke.py
git commit -m "feat(ui): SoundtrackEditor 派生 dialogue_segments + 加重排段落按钮

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 收尾验证（全部任务完成后）

- [ ] **回归全测**

Run: `python -m pytest tests/test_sound_track_agent/ tests/test_ui/ tests/test_core/test_dialogue_segment_deriver.py tests/test_config/ -q`
Expected: 全绿

- [ ] **对照验收标准（spec §11）逐条确认**

1. 音量滑条 bug 修复 → `test_volume_slider_syncs_to_audio_output`（Task 5）
2. refine_frames_per_shot 1/5/非法值 → `test_times_for_shot_*`（Task 2） + `test_build_stages_threads_refine_frames_per_shot`（Task 3）
3. dialogue_segments 派生与传入 → `test_editor_passes_derived_dialogue_segments_to_prepare`（Task 7） + 8 个 deriver 单测（Task 4）
4. 6 个 cfg 控件读写 → `test_load_from_populates_controls` + `test_apply_to_writes_back_to_cfg`（Task 6）
5. 重排按钮安全护栏 → `test_resegment_button_resets_flag_and_runs_refine` + `test_resegment_button_warns_when_no_session`（Task 7）
6. 零回归 → 整套 ~213+ 测试全绿
