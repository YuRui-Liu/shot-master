# sound_track_agent Plan 4：对齐 + 混音（beat / 人声分离 / ducking）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 补齐出片最后一段——`beat_aligner` 提取真实音乐节拍（供卡点吸附），`audio_mixer` 用 Demucs 分离成片对白、FFmpeg sidechain ducking + loudnorm 把新 BGM 压在对白下方混出成片。

**Architecture:** 3 个 task。(1) `beat_aligner.extract_beats`（librosa，已装验证）。(2) `audio_mixer.separate_vocals`（Demucs CLI subprocess，分出 vocals/no_vocals）。(3) `audio_mixer.duck_and_mix` + `mix_bgm_to_video`（FFmpeg：BGM 跟随 vocals ducking → amix → loudnorm → 写回视频）。

**Tech Stack:** librosa 0.11、Demucs 4.0.1（CLI）、FFmpeg 4.4（sidechaincompress/amix/loudnorm/afade）、pyrubberband（可选 time-stretch）。测试用 `/usr/bin/python3 -m pytest`。

参考 spec：`docs/superpowers/specs/2026-05-25-sound-track-agent-design.md` §7。

## 已验证事实（实测）

- `librosa.beat.beat_track(y=, sr=)` → `(tempo, beats帧)`；`librosa.frames_to_time(beats, sr=)` → 秒数组。`librosa.load(path, sr=None)` → `(y, sr)`。
- **Demucs 4.0.1 无 `demucs.api`**，走 CLI：`python -m demucs --two-stems vocals -o OUT INPUT` → `OUT/htdemucs/<input_stem>/vocals.wav` + `OUT/htdemucs/<input_stem>/no_vocals.wav`（首次运行下载 ~300MB 权重）。
- FFmpeg 4.4 滤镜可用：`sidechaincompress`(AA->A)、`amix`、`loudnorm`、`afade`。
- `pyrubberband.time_stretch(y, sr, rate)` 可用（本 Plan 暂不强制用，留作后续段落级长度微调）。
- ffmpeg 命令存在于 `/usr/bin/ffmpeg`。

---

## Task 1：beat_aligner.extract_beats（librosa 提取节拍）

**Files:**
- Modify: `sound_track_agent/beat_aligner.py`（追加 `extract_beats`，保留现有纯算法 `snap_boundaries_to_beats`/`align_accents`）
- Test: `tests/test_sound_track_agent/test_beat_aligner.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_sound_track_agent/test_beat_aligner.py` 末尾追加：

```python
import numpy as np
import soundfile as sf
from sound_track_agent.beat_aligner import extract_beats


def _write_click_track(path, sr=22050, clicks_s=(0.5, 1.0, 1.5, 2.0, 2.5), dur_s=3.0):
    """每个 clicks_s 处放一个短脉冲，形成稳定节拍。"""
    y = np.zeros(int(sr * dur_s), dtype=np.float32)
    for t in clicks_s:
        i = int(t * sr)
        y[i:i + 200] = 1.0          # 短促 click
    sf.write(str(path), y, sr)


def test_extract_beats_returns_increasing_times(tmp_path):
    wav = tmp_path / "click.wav"
    _write_click_track(wav)
    beats = extract_beats(wav)
    assert isinstance(beats, list)
    assert len(beats) >= 3
    assert all(isinstance(b, float) for b in beats)
    # 单调递增、落在音频时长内
    assert beats == sorted(beats)
    assert 0.0 <= beats[0] and beats[-1] <= 3.0


def test_extract_beats_empty_on_silence(tmp_path):
    wav = tmp_path / "silence.wav"
    sf.write(str(wav), np.zeros(22050, dtype=np.float32), 22050)
    beats = extract_beats(wav)
    assert isinstance(beats, list)   # 静音可能返回空或极少，不报错即可
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_beat_aligner.py -q`
Expected: 2 新测试 FAIL（ImportError: extract_beats）

- [ ] **Step 3: 追加 extract_beats**

在 `sound_track_agent/beat_aligner.py` 末尾追加：

```python
def extract_beats(audio_path) -> list[float]:
    """用 librosa 提取音乐节拍时间戳（秒，升序）。

    供 snap_boundaries_to_beats / align_accents 作为 beats 输入。
    提取失败/静音/异常 → 返回 []（降级为不卡点，不中断管线）。
    """
    import librosa
    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        if y is None or len(y) == 0:
            return []
        _tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        times = librosa.frames_to_time(beat_frames, sr=sr)
        return [float(t) for t in times]
    except Exception:
        return []
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_beat_aligner.py -q`
Expected: PASS（原 5 + 新 2 = 7 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/beat_aligner.py tests/test_sound_track_agent/test_beat_aligner.py
git commit -m "feat(sound_track_agent): beat_aligner.extract_beats（librosa 提取节拍）"
```

---

## Task 2：audio_mixer.separate_vocals（Demucs CLI 分离对白）

**Files:**
- Create: `sound_track_agent/audio_mixer.py`
- Test: `tests/test_sound_track_agent/test_audio_mixer.py`

**逻辑**：`separate_vocals(audio_path, out_dir, *, runner=subprocess.run) -> tuple[Path, Path]` 调 Demucs CLI（`--two-stems vocals`）分出 vocals/no_vocals，返回两者路径。`runner` 可注入便于 mock（真跑 Demucs 要下权重 + 慢，单测 mock）。命令与输出路径按实测约定。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_audio_mixer.py`:

```python
import sys
from pathlib import Path
import pytest

from sound_track_agent.audio_mixer import separate_vocals


def test_separate_vocals_builds_demucs_cmd_and_parses_paths(tmp_path):
    audio = tmp_path / "ep1.wav"
    audio.write_bytes(b"RIFF....")           # 占位，命令被 mock 不真读
    out = tmp_path / "sep"
    calls = []

    def fake_runner(cmd, **kw):
        calls.append(cmd)
        # 模拟 demucs 产出： out/htdemucs/ep1/{vocals,no_vocals}.wav
        d = out / "htdemucs" / "ep1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "vocals.wav").write_bytes(b"v")
        (d / "no_vocals.wav").write_bytes(b"n")
        class _R: returncode = 0
        return _R()

    vocals, rest = separate_vocals(audio, out, runner=fake_runner)
    assert vocals.name == "vocals.wav" and vocals.exists()
    assert rest.name == "no_vocals.wav" and rest.exists()
    # 命令含关键参数
    cmd = calls[0]
    assert sys.executable in cmd or "python" in cmd[0]
    assert "demucs" in cmd
    assert "--two-stems" in cmd and "vocals" in cmd
    assert "-o" in cmd
    assert str(audio) in cmd


def test_separate_vocals_raises_when_output_missing(tmp_path):
    audio = tmp_path / "ep.wav"; audio.write_bytes(b"x")
    def fake_runner(cmd, **kw):
        class _R: returncode = 0
        return _R()                          # 不产出文件
    with pytest.raises(FileNotFoundError):
        separate_vocals(audio, tmp_path / "o", runner=fake_runner)
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_audio_mixer.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 audio_mixer.py（分离部分）**

```python
"""成片音频处理：Demucs 分离对白 + FFmpeg ducking 混音。

Demucs 4.0.1 无 python api，走 CLI；FFmpeg 走子进程。所有外部命令经可注入的
runner，便于单测 mock（真跑 Demucs 需下载 ~300MB 权重）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DEMUCS_MODEL = "htdemucs"      # Demucs 默认模型，输出子目录名


def separate_vocals(audio_path, out_dir, *,
                    runner=subprocess.run) -> tuple[Path, Path]:
    """用 Demucs CLI 把音频分成 vocals(对白) / no_vocals(其余)。

    返回 (vocals_path, no_vocals_path)。命令失败或产物缺失抛错。
    """
    audio_path = Path(audio_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "--two-stems", "vocals",
           "-o", str(out_dir), str(audio_path)]
    result = runner(cmd)
    if getattr(result, "returncode", 0) != 0:
        raise RuntimeError(f"demucs 分离失败 (returncode={result.returncode})")
    stem = audio_path.stem
    base = out_dir / DEMUCS_MODEL / stem
    vocals = base / "vocals.wav"
    no_vocals = base / "no_vocals.wav"
    if not vocals.exists() or not no_vocals.exists():
        raise FileNotFoundError(
            f"demucs 未在 {base} 产出 vocals/no_vocals.wav")
    return vocals, no_vocals
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_audio_mixer.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/audio_mixer.py tests/test_sound_track_agent/test_audio_mixer.py
git commit -m "feat(sound_track_agent): audio_mixer.separate_vocals（Demucs CLI）"
```

---

## Task 3：audio_mixer ducking 混音（FFmpeg，真跑）

**Files:**
- Modify: `sound_track_agent/audio_mixer.py`（追加 `duck_and_mix`）
- Test: `tests/test_sound_track_agent/test_audio_mixer.py`（追加，真跑 ffmpeg）

**逻辑**：`duck_and_mix(vocals_path, bgm_path, out_path, *, target_lufs=-14.0) -> Path`，用 FFmpeg 把 BGM 以 vocals 为 sidechain 压低后与 vocals 混合并 loudnorm。真跑 ffmpeg（已装），测试造两个极小 wav 验证产物存在且可读。

- [ ] **Step 1: 追加真跑测试**

在 `tests/test_sound_track_agent/test_audio_mixer.py` 末尾追加：

```python
import numpy as np
import soundfile as sf
from sound_track_agent.audio_mixer import duck_and_mix


def _tone(path, freq, sr=22050, dur=1.0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr)


def test_duck_and_mix_produces_audio(tmp_path):
    voc = tmp_path / "voc.wav"; _tone(voc, 220)
    bgm = tmp_path / "bgm.wav"; _tone(bgm, 440)
    out = tmp_path / "mixed.wav"
    res = duck_and_mix(voc, bgm, out)
    assert res == out and out.exists()
    y, sr = sf.read(str(out))
    assert len(y) > 0                     # 真实产出了音频
    assert sr > 0
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_audio_mixer.py::test_duck_and_mix_produces_audio -q`
Expected: FAIL（ImportError: duck_and_mix）

- [ ] **Step 3: 追加 duck_and_mix**

在 `sound_track_agent/audio_mixer.py` 末尾追加：

```python
def duck_and_mix(vocals_path, bgm_path, out_path, *,
                 target_lufs: float = -14.0,
                 runner=subprocess.run) -> Path:
    """BGM 以 vocals 为 sidechain 自动 ducking，与 vocals 混合并响度归一化。

    [1=bgm] 被 [0=vocals] 压低 → 与 vocals amix → loudnorm。输出 out_path。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        "[1:a][0:a]sidechaincompress="
        "threshold=0.03:ratio=8:attack=20:release=300[bgmducked];"
        "[0:a][bgmducked]amix=inputs=2:duration=longest:dropout_transition=0[mix];"
        f"[mix]loudnorm=I={target_lufs}:TP=-1:LRA=11[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(vocals_path),
        "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        str(out_path),
    ]
    result = runner(cmd, capture_output=True)
    if getattr(result, "returncode", 0) != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "ignore")[-400:] if isinstance(err, bytes) else str(err)[-400:]
        raise RuntimeError(f"ffmpeg ducking 混音失败: {msg}")
    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg 未产出 {out_path}")
    return out_path
```

- [ ] **Step 4: 跑确认通过 + 全量回归**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_audio_mixer.py -q`
Expected: PASS（3 passed）

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/ -q`
Expected: 全量通过（Plan1-3 的 47 + beat_aligner 新增 2 + audio_mixer 3 = 52）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/audio_mixer.py tests/test_sound_track_agent/test_audio_mixer.py
git commit -m "feat(sound_track_agent): audio_mixer.duck_and_mix（FFmpeg sidechain + loudnorm）"
```

---

## 后续：集成（不在本 Plan）

所有功能模块（P1 数据/会话、P2 视频分析、P3 理解/生成、P4 对齐/混音）齐备后，做最后的**集成**：
- 把 `pipeline.Stages` 的 stub 换成真实实现：`tag_emotion`=emotion_tagger、`compose_prompt`+`generate`=prompt_composer 三元组 + music_generator、`align`=extract_beats+snap/align、`mix`=separate_vocals+duck_and_mix。
- `mix` 完整链：取成片音轨 → `separate_vocals` 得对白 → 段落 BGM 按 segment 边界拼接（crossfade）→ `duck_and_mix`(对白, 拼接BGM) → 写回视频音轨（ffmpeg `-map 0:v -map [mixedaudio]`）。
- CLI `run` 接线：detect_shots→plan_segments→（每段）tag→compose→generate→人工选优→align→mix。
- 接线注意（承 Plan 3）：bpm/duration 三元组与 pipeline 现有 `compose_prompt:(seg,sess)->str` 的差异——在 generate 阶段用 emotion+段时长现算 (tags,bpm,duration)，SegmentScore.music_prompt 存 tags 即可，不改 session schema。
- demucs 首次真跑会下载 ~300MB 权重；audio_mixer 的 demucs 单测是 mock，集成/端到端冒烟时才真跑。
