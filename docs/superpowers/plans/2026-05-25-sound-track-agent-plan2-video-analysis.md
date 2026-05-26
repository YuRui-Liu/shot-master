# sound_track_agent Plan 2：视频分析（镜头切分 + 爆点检测）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 从成片 MP4 恢复时间结构——`shot_detector` 用 PySceneDetect 切镜头，`accent_detector` 用 OpenCV 光流检测动作爆点；二者输出可直接喂 Plan 1 的 `segment_planner`（Shot）和 `session`（AccentPoint）。

**Architecture:** 两个新模块。`shot_detector.detect_shots(mp4) -> list[Shot]`。`accent_detector` 拆成纯逻辑峰值检测 `find_accent_peaks(motion, fps) -> list[AccentPoint]`（可严格 TDD）+ 光流序列提取 `_motion_series(mp4)`（cv2 集成）+ 组合 `detect_accents(mp4)`。

**Tech Stack:** scenedetect 0.7、opencv-python-headless 4.13（cv2）。复用 Plan 1 的 `Shot`（segment_planner）、`AccentPoint`（session）。

参考 spec：`docs/superpowers/specs/2026-05-25-sound-track-agent-design.md`；前置 Plan：`...-plan1-skeleton.md`。

---

## 已验证的真实库行为（实测，非猜测）

- `from scenedetect import detect, ContentDetector`；`detect(str(path), ContentDetector(threshold=27.0)) -> list[(FrameTimecode, FrameTimecode)]`；用 **`.seconds` 属性**取秒（`get_seconds()` 已废弃）。无切点视频返回**空列表**。
- `cv2.VideoCapture(str(path))`；`cap.get(cv2.CAP_PROP_FPS)` / `cv2.CAP_PROP_FRAME_COUNT`；`cap.read() -> (ok, frame_BGR)`。
- `cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)`；`cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5,3,15,3,5,1.2,0) -> flow(H,W,2)`；运动强度 `sqrt((flow**2).sum(-1)).mean()`。
- **陷阱**：Farneback 对**纯色帧**输出 0（无纹理梯度）。合成 accent 测试必须用**移动的纹理**（平移噪声图），不能用纯色。shot 测试可用纯色硬切（scenedetect 基于内容差，纯色硬切能检出）。
- `cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w,h))` 在本环境可写 mp4（已验证）。

## 前置依赖（本会话已装）

`scenedetect`、`opencv-python-headless` 已装到测试用的 `/usr/bin/python3`（官方源 `-i https://pypi.org/simple`，因默认清华镜像经本地代理 7897 会 SSL 握手失败）。
建议把它们记入 `pyproject.toml` 的 `[project.optional-dependencies]`（如 `soundtrack = ["scenedetect>=0.7", "opencv-python-headless>=4.9"]`）——可在 Task 1 顺带做，或人工补；不阻塞实现。

---

## Task 1：shot_detector（镜头切分）

**Files:**
- Create: `sound_track_agent/shot_detector.py`
- Test: `tests/test_sound_track_agent/test_shot_detector.py`

- [ ] **Step 1: 写测试（含合成视频 helper）**

`tests/test_sound_track_agent/test_shot_detector.py`:

```python
from unittest.mock import patch
import numpy as np
import cv2
import pytest

from sound_track_agent.shot_detector import detect_shots, _video_duration_seconds
from sound_track_agent.segment_planner import Shot


def _write_hardcut_video(path, fps=24, seconds_each=1, colors=(0, 255, 128)):
    """造一个每 `seconds_each` 秒硬切一次纯色的视频（scenedetect 能检出切点）。"""
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         float(fps), (64, 64))
    assert vw.isOpened()
    for c in colors:
        for _ in range(fps * seconds_each):
            vw.write(np.full((64, 64, 3), c, np.uint8))
    vw.release()


def test_detect_shots_finds_cuts(tmp_path):
    v = tmp_path / "hc.mp4"
    _write_hardcut_video(v, fps=24, seconds_each=1, colors=(0, 255, 128))
    shots = detect_shots(v)
    assert len(shots) == 3
    assert all(isinstance(s, Shot) for s in shots)
    assert shots[0].t_start == 0.0
    # 切点约在 1s、2s（允许 ±0.1s 容差）
    assert abs(shots[0].t_end - 1.0) < 0.15
    assert abs(shots[1].t_start - 1.0) < 0.15
    assert shots[-1].t_end > 2.5
    assert [s.index for s in shots] == [0, 1, 2]


def test_detect_shots_falls_back_to_single_when_no_cuts(tmp_path):
    v = tmp_path / "x.mp4"
    _write_hardcut_video(v, fps=24, seconds_each=1, colors=(0,))  # 单色，无切点
    # mock scenedetect 返回空，验证回退逻辑（与真实"单色可能也返回1段"解耦）
    with patch("sound_track_agent.shot_detector.detect", return_value=[]):
        shots = detect_shots(v)
    assert len(shots) == 1
    assert shots[0].index == 0
    assert shots[0].t_start == 0.0
    assert shots[0].t_end > 0.5          # 时长来自真实视频


def test_video_duration_seconds(tmp_path):
    v = tmp_path / "d.mp4"
    _write_hardcut_video(v, fps=24, seconds_each=1, colors=(0, 255))  # 2s
    dur = _video_duration_seconds(v)
    assert abs(dur - 2.0) < 0.15
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_shot_detector.py -q`
Expected: FAIL（`ModuleNotFoundError: sound_track_agent.shot_detector`）

注意：本 Plan 测试要用装了 cv2/scenedetect 的解释器。本仓库 `/usr/local/bin/pytest` 与 `/usr/bin/python3` 指向同一环境（Python 3.10），两种写法皆可；统一用 `/usr/bin/python3 -m pytest` 更稳。

- [ ] **Step 3: 实现 shot_detector.py**

`sound_track_agent/shot_detector.py`:

```python
"""成片 MP4 → 镜头切点（PySceneDetect）。输出 Shot 列表喂 segment_planner。"""
from __future__ import annotations

from pathlib import Path

from scenedetect import detect, ContentDetector

from sound_track_agent.segment_planner import Shot


def _video_duration_seconds(video_path) -> float:
    """用 cv2 读出视频时长（秒）。读不到则返回 0.0。"""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    return float(n / fps) if fps else 0.0


def detect_shots(video_path, threshold: float = 27.0) -> list[Shot]:
    """检测镜头切点 → Shot 列表（index 从 0、t_start/t_end 单位秒）。

    无切点（单镜头）时回退为整段一个 Shot。
    """
    scenes = detect(str(video_path), ContentDetector(threshold=threshold))
    if not scenes:
        return [Shot(index=0, t_start=0.0,
                     t_end=_video_duration_seconds(video_path))]
    return [
        Shot(index=i, t_start=float(start.seconds), t_end=float(end.seconds))
        for i, (start, end) in enumerate(scenes)
    ]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_shot_detector.py -q`
Expected: PASS（3 passed）。若 `test_detect_shots_finds_cuts` 的段数因 scenedetect 版本默认参数略有出入，**不要**放宽到无意义；先核对 `ContentDetector(threshold=27.0)`，仍不符再把容差/阈值按实测微调并在报告中说明。

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/shot_detector.py tests/test_sound_track_agent/test_shot_detector.py
git commit -m "feat(sound_track_agent): shot_detector 镜头切分（PySceneDetect）"
```

---

## Task 2：find_accent_peaks（爆点峰值检测，纯逻辑）

**Files:**
- Create: `sound_track_agent/accent_detector.py`（先只放纯逻辑函数）
- Test: `tests/test_sound_track_agent/test_accent_detector.py`

**逻辑**：输入逐帧运动强度序列 `motion`（`motion[i]` 是第 i→i+1 帧的运动量，对应时间约 `(i+1)/fps`）。检测"显著局部极大"作为爆点：高于 `mean + k*std` 的局部峰，且相邻爆点间隔 ≥ `min_gap_s`（冲突保留更强者）。`intensity` 归一化到 0-1（除以序列最大值）。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_accent_detector.py`:

```python
import pytest
from sound_track_agent.accent_detector import find_accent_peaks
from sound_track_agent.session import AccentPoint


def test_find_peaks_basic():
    # 两个明显尖峰：index2(=5) 与 index5(=4)，背景全 0
    # （背景为 0 + 峰值足够高，确保两者都超 mean+1*std 阈值）
    motion = [0.0, 0.0, 5.0, 0.0, 0.0, 4.0, 0.0]
    pts = find_accent_peaks(motion, fps=10.0, k=1.0, min_gap_s=0.05)
    assert all(isinstance(p, AccentPoint) for p in pts)
    ts = [round(p.t, 3) for p in pts]
    # motion[i] 对应 t=(i+1)/fps → index2→0.3s, index5→0.6s
    assert ts == [0.3, 0.6]
    # intensity 归一化：最强峰=1.0
    assert max(p.intensity for p in pts) == 1.0
    assert all(0.0 <= p.intensity <= 1.0 for p in pts)
    assert all(p.confirmed is False for p in pts)


def test_find_peaks_respects_min_gap():
    # 两个局部极大 index1(=5)、index3(=4)，间隔 2 帧 < min_gap(=0.3s*10fps=3 帧)
    # → 只保留更强的 index1
    motion = [0.0, 5.0, 0.0, 4.0, 0.0]
    pts = find_accent_peaks(motion, fps=10.0, k=0.5, min_gap_s=0.3)
    assert len(pts) == 1
    assert round(pts[0].t, 3) == 0.2        # index1 → (1+1)/10


def test_find_peaks_empty_or_flat():
    assert find_accent_peaks([], fps=24.0) == []
    assert find_accent_peaks([1.0, 1.0, 1.0, 1.0], fps=24.0, k=1.0) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_accent_detector.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 accent_detector.py（纯逻辑部分）**

`sound_track_agent/accent_detector.py`:

```python
"""动作爆点检测：光流运动序列 → 显著峰值 → AccentPoint。

find_accent_peaks 是纯逻辑（可单测）；_motion_series/detect_accents 接 cv2（Task 3）。
"""
from __future__ import annotations

from statistics import mean, pstdev

from sound_track_agent.session import AccentPoint


def find_accent_peaks(motion: list[float],
                      fps: float,
                      *,
                      k: float = 1.0,
                      min_gap_s: float = 0.3) -> list[AccentPoint]:
    """从逐帧运动强度序列中找显著爆点。

    motion[i] = 第 i→i+1 帧运动量，时间约 (i+1)/fps。
    判据：motion[i] 是局部极大且 > mean + k*std。相邻爆点间隔 < min_gap_s
    时只保留更强者。intensity = motion[i] / max(motion)（0-1）。
    """
    n = len(motion)
    if n == 0 or fps <= 0:
        return []
    mu = mean(motion)
    sd = pstdev(motion)
    thresh = mu + k * sd
    peak_max = max(motion)
    if peak_max <= 0:
        return []

    # 1) 候选：严格局部极大且超阈值
    cands: list[tuple[int, float]] = []
    for i in range(n):
        left = motion[i - 1] if i > 0 else float("-inf")
        right = motion[i + 1] if i < n - 1 else float("-inf")
        if motion[i] > thresh and motion[i] >= left and motion[i] >= right:
            cands.append((i, motion[i]))

    # 2) min_gap：按强度降序贪心选，拒绝与已选过近者
    min_gap_frames = min_gap_s * fps
    chosen: list[int] = []
    for i, _v in sorted(cands, key=lambda c: c[1], reverse=True):
        if all(abs(i - j) >= min_gap_frames for j in chosen):
            chosen.append(i)

    # 3) 输出，按时间排序
    pts = [
        AccentPoint(t=(i + 1) / fps, intensity=motion[i] / peak_max,
                    confirmed=False)
        for i in sorted(chosen)
    ]
    return pts
```

- [ ] **Step 4: 跑测试确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_accent_detector.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/accent_detector.py tests/test_sound_track_agent/test_accent_detector.py
git commit -m "feat(sound_track_agent): find_accent_peaks 爆点峰值检测（纯逻辑）"
```

---

## Task 3：_motion_series + detect_accents（cv2 光流集成）

**Files:**
- Modify: `sound_track_agent/accent_detector.py`（追加 `_motion_series` + `detect_accents`）
- Test: `tests/test_sound_track_agent/test_accent_detector.py`（追加集成测试）

**逻辑**：`_motion_series(mp4)` 用 cv2 逐帧转灰度、算相邻帧 Farneback 光流的平均幅值序列，返回 `(motion, fps)`。`detect_accents(mp4)` = `_motion_series` + `find_accent_peaks`。集成测试用**平移噪声纹理**视频（纯色对 Farneback 无效）。

- [ ] **Step 1: 追加集成测试**

在 `tests/test_sound_track_agent/test_accent_detector.py` 末尾追加：

```python
import numpy as np
import cv2
from sound_track_agent.accent_detector import _motion_series, detect_accents


def _write_motion_video(path, fps=24):
    """平移噪声纹理：前后静止、中间某帧突然大平移 → 该处运动峰值。

    Farneback 需纹理梯度，纯色无效，故用随机噪声底图。
    """
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    # 前 20 帧静止(shift 0)，第 20 帧突然平移 10px，其后静止在新位置
    shifts = [0] * 20 + [10] + [0] * 19
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         float(fps), (64, 64))
    assert vw.isOpened()
    pos = 0
    for s in shifts:
        pos += s
        vw.write(np.roll(base, pos, axis=1))
    vw.release()


def test_motion_series_shape(tmp_path):
    v = tmp_path / "m.mp4"
    _write_motion_video(v, fps=24)
    motion, fps = _motion_series(v)
    assert fps == 24.0
    assert len(motion) == 39            # 40 帧 → 39 个相邻对
    assert max(motion) > 0.0            # 噪声平移产生非零光流


def test_detect_accents_finds_motion_spike(tmp_path):
    v = tmp_path / "m.mp4"
    _write_motion_video(v, fps=24)
    pts = detect_accents(v, k=1.0, min_gap_s=0.2)
    assert len(pts) >= 1
    # 平移发生在 frame19→frame20（pos 0→10），即 motion index 19 → t≈20/24≈0.833s
    assert any(abs(p.t - 20 / 24) < 0.2 for p in pts)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_accent_detector.py -q`
Expected: 2 新测试 FAIL（`ImportError: cannot import name '_motion_series'`）

- [ ] **Step 3: 追加实现**

在 `sound_track_agent/accent_detector.py` 末尾追加：

```python
def _motion_series(video_path) -> tuple[list[float], float]:
    """逐帧 Farneback 光流的平均幅值序列。返回 (motion, fps)。

    motion[i] = 第 i 帧到第 i+1 帧的平均运动幅值。
    """
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    motion: list[float] = []
    prev = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.sqrt((flow ** 2).sum(-1)).mean()
            motion.append(float(mag))
        prev = gray
    cap.release()
    return motion, float(fps)


def detect_accents(video_path,
                   *,
                   k: float = 1.0,
                   min_gap_s: float = 0.3) -> list:
    """成片 MP4 → 动作爆点 AccentPoint 列表。"""
    motion, fps = _motion_series(video_path)
    return find_accent_peaks(motion, fps, k=k, min_gap_s=min_gap_s)
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_accent_detector.py -q`
Expected: PASS（5 passed：3 纯逻辑 + 2 集成）

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/ -q`
Expected: PASS（全量，Plan 1 的 27 + 本 Plan 的 shot 3 + accent 5 = 35）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/accent_detector.py tests/test_sound_track_agent/test_accent_detector.py
git commit -m "feat(sound_track_agent): _motion_series + detect_accents（cv2 光流集成）"
```

---

## 后续 Plan 预告

- **Plan 3 理解+生成**：`emotion_tagger`（豆包 lite vision，需先验证 doubao-seed-2-0-lite 是否支持图像输入）、`prompt_composer` 豆包润色（可选）、`music_generator`（ACE-Step）。
- **Plan 4 对齐+混音**：`beat_aligner` 接 `librosa.beat.beat_track` 取真实 beat（已验证 API）+ pyrubberband time-stretch、`audio_mixer`（Demucs 分离 + FFmpeg sidechain ducking + loudnorm）。
- **集成**：把 `pipeline.Stages` 的 stub 换成真实实现（detect_shots→plan_segments→tag→prompt→generate→align→mix）；CLI `run` 接线。
- **回填 Plan 1 注意项**：BGMCandidate/AccentPoint to_dict（已在 558fe06 修）、mid-pipeline resume 补测试、pipeline mix 阶段加 `if limit >=` guard 统一结构。
