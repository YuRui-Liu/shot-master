# sound_track_agent Plan 5：集成（端到端串联）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把已完成的 7 个功能模块（P1-P4）串成端到端管线：丢一个成片 MP4 → 镜头切分 → 段落聚合 → 情绪 → ACE-Step 分段生成 → crossfade 拼接 → Demucs 分离对白 + ducking → 写回视频出片。

**Architecture:** 4 个 task。(1) `bgm_assembler`：按选定候选用 ffmpeg `acrossfade` 把分段 BGM 拼成整条（真跑）。(2) `mix` 完整链 `assemble_and_mix`：取成片音轨 → 拼 BGM → Demucs 分离对白 → duck_and_mix → 写回视频（重型服务 mock，ffmpeg 真跑）。(3) `stages_factory.build_stages`：用闭包把真实模块包成 `pipeline.Stages`（捕获 client/provider/workflow_id/work_dir/global_style/seeds）。(4) CLI `run` 接线 detect_shots→plan_segments→pipeline.run。

**Tech Stack:** 复用 P1-P4 全部模块 + ffmpeg(acrossfade/concat/amix/loudnorm)。测试 `/usr/bin/python3 -m pytest`。**编排/拼接真跑 ffmpeg；ACE-Step(RunningHub)/Demucs/豆包 mock。**

参考 spec：`docs/superpowers/specs/2026-05-25-sound-track-agent-design.md`。前置：Plan 1-4 全部完成（52 测试过）。

## 已验证事实（实测）

- ffmpeg `acrossfade=d=<秒>:c1=tri:c2=tri` 可拼两路音频（实测两段 1s + 重叠 0.3s → 1.7s）。多段需链式两两 crossfade。
- `acrossfade` 一次只吃 2 路；N 段要么链式（`[0][1]acrossfade[a01];[a01][2]acrossfade...`），要么用「无重叠直连」的 `concat`。本 Plan 用**链式 acrossfade**（N≤5 段，链不长）。
- 已有可复用：`shot_detector.detect_shots`、`segment_planner.plan_segments`、`emotion_tagger.tag_emotion`、`prompt_composer.compose_acestep_inputs`、`music_generator.generate_bgm`、`beat_aligner.extract_beats/snap_boundaries_to_beats`、`audio_mixer.separate_vocals/duck_and_mix`、`session.*`、`pipeline.Stages/run`。
- `pipeline.Stages` 回调签名：`tag_emotion(seg,sess)->EmotionTag`、`compose_prompt(seg,sess)->str`、`generate(seg,sess)->list[BGMCandidate]`、`align(sess)->None`、`mix(sess)->str`。真实实现需额外依赖（client/provider/...），用闭包捕获。
- `SegmentScore` 有 `chosen_candidate: Optional[int]`、`candidates: list[BGMCandidate]`、`music_prompt`、`emotion`、`t_start/t_end/duration`。

---

## Task 1：bgm_assembler（crossfade 拼接分段 BGM）

**Files:**
- Create: `sound_track_agent/bgm_assembler.py`
- Test: `tests/test_sound_track_agent/test_bgm_assembler.py`

**逻辑**：`assemble_bgm(bgm_paths, out_path, *, crossfade=0.5, runner=subprocess.run) -> Path`。1 段直接复制/转码到 out；≥2 段用链式 `acrossfade` 拼成整条。真跑 ffmpeg。

- [ ] **Step 1: 写测试（真跑 ffmpeg）**

`tests/test_sound_track_agent/test_bgm_assembler.py`:

```python
import numpy as np
import soundfile as sf
import pytest
from sound_track_agent.bgm_assembler import assemble_bgm


def _tone(path, freq, sr=22050, dur=1.0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr)


def test_assemble_single_segment(tmp_path):
    a = tmp_path / "a.wav"; _tone(a, 220, dur=1.0)
    out = tmp_path / "full.wav"
    res = assemble_bgm([a], out)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    assert abs(len(y) / sr - 1.0) < 0.2


def test_assemble_three_segments_crossfaded(tmp_path):
    paths = []
    for i, f in enumerate((220, 330, 440)):
        p = tmp_path / f"s{i}.wav"; _tone(p, f, dur=1.0); paths.append(p)
    out = tmp_path / "full.wav"
    res = assemble_bgm(paths, out, crossfade=0.3)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    # 3×1s 两次 0.3s 重叠 ≈ 3 - 2*0.3 = 2.4s
    assert abs(len(y) / sr - 2.4) < 0.3


def test_assemble_empty_raises(tmp_path):
    with pytest.raises(ValueError):
        assemble_bgm([], tmp_path / "x.wav")
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_bgm_assembler.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 bgm_assembler.py**

```python
"""分段 BGM → crossfade 拼接成整条（ffmpeg acrossfade 链式）。"""
from __future__ import annotations

import subprocess
from pathlib import Path


def assemble_bgm(bgm_paths: list, out_path, *,
                 crossfade: float = 0.5,
                 runner=subprocess.run) -> Path:
    """把分段 BGM 按顺序 crossfade 拼成整条。

    1 段：直接转码到 out。≥2 段：链式 acrossfade（每对重叠 crossfade 秒）。
    """
    if not bgm_paths:
        raise ValueError("assemble_bgm 需要至少 1 段 BGM")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    paths = [str(p) for p in bgm_paths]

    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd += ["-i", p]

    if len(paths) == 1:
        cmd += ["-c:a", "pcm_s16le", str(out_path)]
    else:
        # 链式：[0][1]acrossfade[a1]; [a1][2]acrossfade[a2]; ...
        parts = []
        prev = "[0]"
        for i in range(1, len(paths)):
            label = f"[a{i}]" if i < len(paths) - 1 else "[out]"
            parts.append(
                f"{prev}[{i}]acrossfade=d={crossfade}:c1=tri:c2=tri{label}")
            prev = label
        filter_complex = ";".join(parts)
        cmd += ["-filter_complex", filter_complex, "-map", "[out]",
                str(out_path)]

    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) else str(err)[-400:]
        raise RuntimeError(f"ffmpeg acrossfade 拼接失败: {msg}")
    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg 未产出 {out_path}")
    return out_path
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_bgm_assembler.py -q`
Expected: **3 passed**

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/bgm_assembler.py tests/test_sound_track_agent/test_bgm_assembler.py
git commit -m "feat(sound_track_agent): bgm_assembler crossfade 拼接分段 BGM"
```

---

## Task 2：audio_mixer 视频音轨提取 + 写回

**Files:**
- Modify: `sound_track_agent/audio_mixer.py`（追加 `extract_audio` + `replace_video_audio`）
- Test: `tests/test_sound_track_agent/test_audio_mixer.py`（追加，真跑 ffmpeg）

**逻辑**：`extract_audio(video, out_wav)` 用 ffmpeg 抽出视频音轨为 wav。`replace_video_audio(video, audio, out_video)` 用 ffmpeg 把视频的音轨换成 audio（`-map 0:v -map 1:a -c:v copy`）。真跑 ffmpeg，测试造带音轨的小 mp4。

- [ ] **Step 1: 追加测试**

在 `tests/test_sound_track_agent/test_audio_mixer.py` 末尾追加：

```python
import numpy as np
import soundfile as sf
import subprocess
from sound_track_agent.audio_mixer import extract_audio, replace_video_audio


def _make_video_with_audio(path, sr=22050, dur=1.0, fps=24):
    """造一个带音轨的小 mp4（纯色视频 + 正弦音）。"""
    import cv2
    apath = str(path) + ".a.wav"
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(apath, (0.3 * np.sin(2 * np.pi * 330 * t)).astype(np.float32), sr)
    vtmp = str(path) + ".v.mp4"
    vw = cv2.VideoWriter(vtmp, cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (64, 64))
    for _ in range(int(fps * dur)):
        vw.write(np.full((64, 64, 3), 128, np.uint8))
    vw.release()
    subprocess.run(["ffmpeg", "-y", "-i", vtmp, "-i", apath,
                    "-c:v", "copy", "-c:a", "aac", "-shortest", str(path)],
                   capture_output=True, check=True)


def test_extract_audio(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v)
    out = tmp_path / "a.wav"
    res = extract_audio(v, out)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    assert len(y) > 0


def test_replace_video_audio(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v)
    newa = tmp_path / "new.wav"
    t = np.linspace(0, 1.0, 22050, endpoint=False)
    sf.write(str(newa), (0.2 * np.sin(2 * np.pi * 660 * t)).astype(np.float32), 22050)
    out = tmp_path / "out.mp4"
    res = replace_video_audio(v, newa, out)
    assert res == out and out.exists()
    assert out.stat().st_size > 0
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_audio_mixer.py -k "extract_audio or replace_video" -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: 追加实现**

在 `sound_track_agent/audio_mixer.py` 末尾追加：

```python
def extract_audio(video_path, out_wav, *, runner=subprocess.run) -> Path:
    """抽出视频音轨为 wav（pcm）。"""
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(video_path),
           "-vn", "-c:a", "pcm_s16le", str(out_wav)]
    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) else str(err)[-400:]
        raise RuntimeError(f"ffmpeg 抽音轨失败: {msg}")
    if not out_wav.exists():
        raise FileNotFoundError(f"ffmpeg 未产出 {out_wav}")
    return out_wav


def replace_video_audio(video_path, audio_path, out_video, *,
                        runner=subprocess.run) -> Path:
    """把视频音轨替换为 audio_path（视频流直拷，不重编码）。"""
    out_video = Path(out_video)
    out_video.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
           "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_video)]
    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) else str(err)[-400:]
        raise RuntimeError(f"ffmpeg 写回音轨失败: {msg}")
    if not out_video.exists():
        raise FileNotFoundError(f"ffmpeg 未产出 {out_video}")
    return out_video
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_audio_mixer.py -q`
Expected: **5 passed**（原 3 + 新 2）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/audio_mixer.py tests/test_sound_track_agent/test_audio_mixer.py
git commit -m "feat(sound_track_agent): audio_mixer 抽音轨 + 写回视频音轨"
```

---

## Task 3：stages_factory（把真实模块包成 pipeline.Stages）

**Files:**
- Create: `sound_track_agent/stages_factory.py`
- Test: `tests/test_sound_track_agent/test_stages_factory.py`

**逻辑**：`build_stages(*, provider, client, workflow_id, work_dir, global_style, seeds) -> Stages`。用闭包把真实模块接进 `pipeline.Stages` 的 5 个回调：
- `tag_emotion(seg,sess)` → `emotion_tagger.tag_emotion(provider, frame_for(seg), global_style)`（帧由 `frame_extractor` 抽，见下）
- `compose_prompt(seg,sess)` → `prompt_composer.compose_acestep_inputs(global_style, seg.emotion, seg.duration)`，把 `tags` 存进 `seg.music_prompt` 返回（bpm/duration 不入 session，generate 时重算）
- `generate(seg,sess)` → 重算 `(tags,bpm,duration)` → `music_generator.generate_bgm(client, workflow_id, tags=, bpm=, duration=, out_dir=work_dir/seg, seeds=seeds)`
- `align(sess)` → 暂为 no-op 占位（卡点已由 accent_detector 在 session.accent_points，beat 对齐在 mix 内做；本 task 不接 mix）
- `mix(sess)` → 由 Task 4 的 `assemble_and_mix` 注入

本 task 用 mock 的 provider/client 测 4 个回调接线正确（帧抽取也 mock）。`mix` 留到 Task 4。为隔离"代表帧从哪来"，定义注入点 `frame_provider(seg)->Path`，默认实现 Task 4 给（抽 segment 中点帧）；本 task 测试传 mock。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_stages_factory.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock
from sound_track_agent.stages_factory import build_stages
from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate)


def _sess():
    return ScoringSession(
        source_mp4="/x/ep.mp4", source_hash="h", global_style="末日废土",
        frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])


def test_tag_emotion_stage_uses_provider(tmp_path):
    prov = MagicMock()
    prov.generate.return_value = '{"labels":["tense"],"valence":-0.5,"arousal":0.7}'
    stages = build_stages(provider=prov, client=MagicMock(), workflow_id="wf",
                          work_dir=tmp_path, global_style="末日废土", seeds=[1],
                          frame_provider=lambda seg: tmp_path / "f.png")
    sess = _sess()
    emo = stages.tag_emotion(sess.segments[0], sess)
    assert emo.labels == ["tense"]
    assert prov.generate.called


def test_generate_stage_calls_music_generator(tmp_path):
    client = MagicMock()
    client.create_task.return_value = "tid"
    client.query_task.return_value = {"status": "SUCCESS",
                                      "results": [{"url": "https://x/b.mp3"}]}
    client.download_file.side_effect = lambda url, dest: Path(dest)
    stages = build_stages(provider=MagicMock(), client=client, workflow_id="wf-9",
                          work_dir=tmp_path, global_style="末日废土", seeds=[1, 2],
                          frame_provider=lambda seg: tmp_path / "f.png")
    sess = _sess()
    seg = sess.segments[0]
    seg.emotion = EmotionTag(labels=["tense"], arousal=0.8)
    seg.music_prompt = "Instrumental, tense"
    cands = stages.generate(seg, sess)
    assert all(isinstance(c, BGMCandidate) for c in cands)
    assert [c.seed for c in cands] == [1, 2]
    assert client.create_task.call_args.kwargs["workflow_id"] == "wf-9"


def test_compose_prompt_stage_sets_tags(tmp_path):
    stages = build_stages(provider=MagicMock(), client=MagicMock(), workflow_id="wf",
                          work_dir=tmp_path, global_style="古风", seeds=[1],
                          frame_provider=lambda seg: tmp_path / "f.png")
    sess = _sess()
    seg = sess.segments[0]
    seg.emotion = EmotionTag(labels=["calm"], arousal=0.2)
    tags = stages.compose_prompt(seg, sess)
    assert "古风" in tags and "calm" in tags
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_stages_factory.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 stages_factory.py**

```python
"""把真实功能模块用闭包包成 pipeline.Stages（注入 client/provider/配置）。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.pipeline import Stages
from sound_track_agent.session import SegmentScore, ScoringSession, EmotionTag
from sound_track_agent import emotion_tagger, prompt_composer, music_generator


def build_stages(*, provider, client, workflow_id: str,
                 work_dir, global_style: str, seeds: list,
                 frame_provider: Callable[[SegmentScore], Path],
                 mix_fn: Optional[Callable[[ScoringSession], str]] = None,
                 align_fn: Optional[Callable[[ScoringSession], None]] = None
                 ) -> Stages:
    """组装 Stages：每个回调闭包捕获外部依赖。

    frame_provider(seg)->代表帧路径；mix_fn/align_fn 由调用方（CLI/Task4）注入，
    缺省 align 为 no-op、mix 抛未配置错误。
    """
    work_dir = Path(work_dir)

    def tag_emotion(seg: SegmentScore, sess: ScoringSession) -> EmotionTag:
        return emotion_tagger.tag_emotion(
            provider, frame_provider(seg), global_style)

    def compose_prompt(seg: SegmentScore, sess: ScoringSession) -> str:
        tags, _bpm, _dur = prompt_composer.compose_acestep_inputs(
            global_style, seg.emotion, seg.duration)
        return tags

    def generate(seg: SegmentScore, sess: ScoringSession):
        tags, bpm, dur = prompt_composer.compose_acestep_inputs(
            global_style, seg.emotion, seg.duration)
        seg_dir = work_dir / f"seg{seg.index}"
        return music_generator.generate_bgm(
            client, workflow_id, tags=tags, bpm=bpm, duration=dur,
            out_dir=seg_dir, seeds=list(seeds))

    def _noop_align(sess: ScoringSession) -> None:
        return None

    def _unconfigured_mix(sess: ScoringSession) -> str:
        raise RuntimeError("mix_fn 未注入（见 Task 4 assemble_and_mix）")

    return Stages(
        tag_emotion=tag_emotion,
        compose_prompt=compose_prompt,
        generate=generate,
        align=align_fn or _noop_align,
        mix=mix_fn or _unconfigured_mix,
    )
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_stages_factory.py -q`
Expected: **3 passed**

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/stages_factory.py tests/test_sound_track_agent/test_stages_factory.py
git commit -m "feat(sound_track_agent): stages_factory 把真实模块包成 pipeline.Stages"
```

---

## Task 4：mix 完整链 + CLI run 接线

**Files:**
- Create: `sound_track_agent/mixdown.py`（`assemble_and_mix` + `extract_segment_frame`）
- Modify: `sound_track_agent/cli.py`（`run` 接线）
- Test: `tests/test_sound_track_agent/test_mixdown.py`、`tests/test_sound_track_agent/test_cli.py`（追加 1）

**逻辑**：
- `extract_segment_frame(video, seg, out_png, *, runner)`：ffmpeg 抽 segment 中点帧为 png（`-ss <mid> -frames:v 1`）。
- `assemble_and_mix(sess, video_path, work_dir, *, separate=separate_vocals, ...) -> str`：①取每段 chosen 候选（无则取 candidates[0]）路径 → `bgm_assembler.assemble_bgm` 拼成整条；②`extract_audio(video)` 取成片音轨 → `separate_vocals` 分出对白（mock 注入）；③`duck_and_mix(vocals, full_bgm)` → ④`replace_video_audio(video, mixed)` 出片。返回成片路径。重型步骤（separate）经注入参数 mock。
- CLI `run`：`detect_shots(mp4)` → `plan_segments` → 建 `ScoringSession`（source_hash=hash_file）→ `build_stages`（frame_provider=extract_segment_frame 偏函数，mix_fn=assemble_and_mix 偏函数）→ `pipeline.run(stop_after=...)`。

- [ ] **Step 1: 写 mixdown 测试（编排真跑 ffmpeg，separate mock）**

`tests/test_sound_track_agent/test_mixdown.py`:

```python
import numpy as np, soundfile as sf, subprocess
from pathlib import Path
from sound_track_agent.mixdown import assemble_and_mix, extract_segment_frame
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate


def _make_video_with_audio(path, dur=2.0, sr=22050, fps=24):
    import cv2
    apath = str(path) + ".a.wav"
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(apath, (0.3 * np.sin(2 * np.pi * 330 * t)).astype(np.float32), sr)
    vtmp = str(path) + ".v.mp4"
    vw = cv2.VideoWriter(vtmp, cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (64, 64))
    for _ in range(int(fps * dur)):
        vw.write(np.full((64, 64, 3), 128, np.uint8))
    vw.release()
    subprocess.run(["ffmpeg", "-y", "-i", vtmp, "-i", apath, "-c:v", "copy",
                    "-c:a", "aac", "-shortest", str(path)], capture_output=True, check=True)


def _tone(path, freq, sr=22050, dur=1.0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr)


def test_extract_segment_frame(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v)
    out = tmp_path / "f.png"
    seg = SegmentScore(index=0, t_start=0.0, t_end=2.0)
    res = extract_segment_frame(v, seg, out)
    assert res == out and out.exists() and out.stat().st_size > 0


def test_assemble_and_mix_end_to_end(tmp_path):
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    # 两段，各有一个候选 BGM
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=1.0)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550, dur=1.0)
    sess = ScoringSession(
        source_mp4=str(v), source_hash="h", global_style="x", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=0),
        ])

    # mock Demucs 分离：返回 (vocals=成片抽出的音轨, no_vocals=同一份)
    def fake_separate(audio_path, out_dir, **kw):
        # 直接拿原音轨当 vocals（真跑 demucs 太重）
        return Path(audio_path), Path(audio_path)

    out = assemble_and_mix(sess, v, tmp_path / "work", separate=fake_separate)
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_mixdown.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 mixdown.py**

```python
"""mix 完整链：抽帧 / 取段 BGM 拼接 / 分离对白 / ducking / 写回视频。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from sound_track_agent.session import ScoringSession, SegmentScore
from sound_track_agent.bgm_assembler import assemble_bgm
from sound_track_agent.audio_mixer import (
    separate_vocals, duck_and_mix, extract_audio, replace_video_audio)


def extract_segment_frame(video_path, seg: SegmentScore, out_png, *,
                          runner=subprocess.run) -> Path:
    """抽 segment 中点帧为 png（供情绪分析）。"""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    mid = (seg.t_start + seg.t_end) / 2.0
    cmd = ["ffmpeg", "-y", "-ss", f"{mid:.3f}", "-i", str(video_path),
           "-frames:v", "1", str(out_png)]
    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0 or not out_png.exists():
        raise RuntimeError(f"ffmpeg 抽帧失败 @ {mid:.3f}s")
    return out_png


def _chosen_bgm(seg: SegmentScore) -> str:
    """段的选定候选；未选则取首个。无候选抛错。"""
    if not seg.candidates:
        raise RuntimeError(f"段 {seg.index} 无 BGM 候选")
    idx = seg.chosen_candidate if seg.chosen_candidate is not None else 0
    return seg.candidates[idx].path


def assemble_and_mix(sess: ScoringSession, video_path, work_dir, *,
                     crossfade: float = 0.5,
                     separate=separate_vocals,
                     target_lufs: float = -14.0) -> str:
    """段 BGM 拼接 → 分离对白 → ducking → 写回视频。返回成片路径。"""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1) 段 BGM 按时间序拼成整条
    seg_bgms = [_chosen_bgm(s) for s in sess.segments]
    full_bgm = assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                            crossfade=crossfade)

    # 2) 取成片音轨 → 分离对白
    src_audio = extract_audio(video_path, work_dir / "src_audio.wav")
    vocals, _rest = separate(src_audio, work_dir / "sep")

    # 3) ducking 混音
    mixed = duck_and_mix(vocals, full_bgm, work_dir / "mixed.wav",
                         target_lufs=target_lufs)

    # 4) 写回视频
    out_video = work_dir / (Path(video_path).stem + "_scored.mp4")
    replace_video_audio(video_path, mixed, out_video)
    return str(out_video)
```

- [ ] **Step 4: 跑 mixdown 测试通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_mixdown.py -q`
Expected: **2 passed**

- [ ] **Step 5: CLI run 接线 + 测试**

在 `tests/test_sound_track_agent/test_cli.py` 末尾追加（仍只测参数解析层，不真跑管线）：

```python
def test_run_parse_includes_seeds_default():
    p = build_parser()
    ns = p.parse_args(["run", "ep.mp4", "--style", "x"])
    assert ns.workflow_id is None or isinstance(ns.workflow_id, str)
    assert ns.seeds_count >= 1
```

改 `sound_track_agent/cli.py`：给 `run` 子命令加 `--workflow-id`（默认从环境/None）与 `--seeds-count`（默认 2），并把 `main` 的 run 分支接线（真实管线；解析层测试不触发真实调用，因为接线逻辑放在 `_run_pipeline` 内、仅在有 client/key 时执行）：

```python
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sound_track_agent", description="漫剧成片后期配乐 agent")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="对成片 MP4 新建配乐会话并推进")
    pr.add_argument("mp4")
    pr.add_argument("--style", required=True)
    pr.add_argument("--work-dir", default="sound_track_out")
    pr.add_argument("--stop-after", choices=STAGE_ORDER, default="mix")
    pr.add_argument("--workflow-id", default=None,
                    help="ACE-Step workflowId（默认 2059090557116440578）")
    pr.add_argument("--seeds-count", type=int, default=2,
                    help="每段生成候选数")

    ps = sub.add_parser("resume", help="从已存 session.json 续跑")
    ps.add_argument("session")
    ps.add_argument("--stop-after", choices=STAGE_ORDER, default="mix")
    return p
```

`main` 的 run 分支调用一个新函数 `run_pipeline(args)`（放 cli.py 内），其中：load_config → build_soundtrack_provider → RunningHubClient → detect_shots → plan_segments → ScoringSession → build_stages(frame_provider=partial(extract_segment_frame, mp4), mix_fn=partial(assemble_and_mix, video_path=mp4, work_dir=...)) → pipeline.run。这段不写单测（依赖真实成片 + ACE-Step），靠端到端冒烟验证；保留 `build_parser` 的解析测试。

- [ ] **Step 6: 跑全量回归**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/ -q`
Expected: 全量通过（52 + bgm_assembler 3 + audio_mixer 新增 2 + stages_factory 3 + mixdown 2 + cli 新增 1 = 63）

- [ ] **Step 7: Commit**

```bash
git add sound_track_agent/mixdown.py sound_track_agent/cli.py tests/test_sound_track_agent/test_mixdown.py tests/test_sound_track_agent/test_cli.py
git commit -m "feat(sound_track_agent): mixdown 完整链 + CLI run 端到端接线"
```

---

## 端到端冒烟（人工，非自动测试）

集成完成后，用真实成片 + ACE-Step workflowId 跑一次（消耗 RunningHub 积分 + 首次下载 Demucs 权重 ~300MB）：

```bash
/usr/bin/python3 -m sound_track_agent.cli run <真实成片.mp4> \
  --style "末日废土，冷色调低饱和，器乐 BGM" \
  --workflow-id 2059090557116440578 \
  --work-dir /tmp/stk_smoke --stop-after generate
# 检查 /tmp/stk_smoke 下各段候选 mp3 → 人工选优 → resume 到 mix
```

冒烟通过后回写"实测笔记"。这一步不入自动化测试（需真实积分/权重/成片）。
