# 配乐：卡点试听 play/pause+进度条 + 各段音量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** (1) ③卡点页「🎧 试听卡点效果」支持再点暂停 + 进度条拖拽(任意时点起听);(2) ②试听选优页每段卡片加「🔊 音量」滑块(0–150%),同时作用于试听预览与最终出片。

**Architecture:** 各段音量存 `SegmentScore.volume`(线性,1.0=100%),在 `assemble_bgm` 的预处理 pass 里用 ffmpeg `volume=` 应用(与已有的 trim pass 合并),`assemble_and_mix` 和 `build_accent_preview` 都传 `clip_gains`。③卡点页移植 ②试听页已有的 懒播放器 + 底部 play/pause+seek 条;🎧 按钮:无/脏则后台合成预览再播,已合成则切换 播放/暂停;编辑卡点/音量/泵感后标脏触发重合成。

**Tech Stack:** PySide6 (QMediaPlayer/QAudioOutput 懒创建, QSlider), ffmpeg `volume` 滤镜, 复用 segment_review 的 seek 条范式。

**测试解释器:** `/root/miniconda3/envs/UniRig/bin/python`(记作 `$PY`);UI 测试前缀 `QT_QPA_PLATFORM=offscreen`。

**关键约束:** 绝不 `git add -A`/`.`;只 add 各任务列出文件;工作树有用户并行 imggen/dubbing 改动,绝不触碰/提交。offscreen:QMediaPlayer/QAudioOutput 必须懒创建(首次播放才建),禁止 modal `exec()`,模态 QMessageBox 在测试里 monkeypatch 成 no-op,播放在测试里 monkeypatch `_play_path` 不真播。

---

## File Structure

| 文件 | 角色 | 改动 |
|------|------|------|
| `sound_track_agent/session.py` | `SegmentScore.volume: float = 1.0` + 序列化 | Modify |
| `sound_track_agent/bgm_assembler.py` | `assemble_bgm` 增 `clip_gains`(与 clip_durations 合并预处理) | Modify |
| `sound_track_agent/mixdown.py` | `assemble_and_mix` 两个分支都传 clip_gains | Modify |
| `sound_track_agent/facade.py` | `build_accent_preview` 传 clip_gains | Modify |
| `drama_shot_master/ui/widgets/segment_review_widget.py` | 每段卡片加音量滑块 + `segmentVolumeChanged` 信号 | Modify |
| `drama_shot_master/ui/windows/soundtrack_task_window.py` | 连接 segmentVolumeChanged→落盘 | Modify |
| `drama_shot_master/ui/widgets/accent_editor_widget.py` | 🎧 toggle + 底部 play/pause+seek 条 | Modify |

---

## Task 1: SegmentScore.volume 字段 + 序列化

**Files:** Modify `sound_track_agent/session.py`; Test `tests/test_sound_track_agent/test_session.py`.

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_sound_track_agent/test_session.py`:

```python
def test_segment_volume_default_and_roundtrip():
    from sound_track_agent.session import SegmentScore
    s = SegmentScore(index=0, t_start=0.0, t_end=1.0)
    assert abs(s.volume - 1.0) < 1e-9
    d = s.to_dict()
    assert d["volume"] == 1.0
    s2 = SegmentScore.from_dict(d)
    assert abs(s2.volume - 1.0) < 1e-9


def test_segment_from_dict_missing_volume_defaults():
    from sound_track_agent.session import SegmentScore
    d = {"index": 0, "t_start": 0.0, "t_end": 2.0}
    s = SegmentScore.from_dict(d)
    assert abs(s.volume - 1.0) < 1e-9
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_session.py -k volume -v`
Expected: FAIL(字段不存在)

- [ ] **Step 3: 实现** — 在 `sound_track_agent/session.py` 的 `SegmentScore` dataclass:
- 在 `status: Status = "pending"` 字段后加:
```python
    volume: float = 1.0
```
- `to_dict` 返回 dict 里(`"status": self.status,` 后)加:
```python
            "volume": self.volume,
```
- `from_dict` 的 `cls(...)`(`status=d.get("status", "pending"),` 后)加:
```python
            volume=float(d.get("volume", 1.0)),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_session.py -v`
Expected: PASS(原有 + 2 新增)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/session.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(soundtrack): per-segment volume field on SegmentScore"
```

---

## Task 2: assemble_bgm 支持 clip_gains（与 clip_durations 合并预处理）

**Files:** Modify `sound_track_agent/bgm_assembler.py`; Test `tests/test_sound_track_agent/test_bgm_assembler.py`.

**说明:** 现有预处理 pass 仅在 `clip_durations is not None` 时跑、按 `-t` 裁剪。改成:`clip_durations` 或 `clip_gains` 任一非 None 即跑;每段 clip 按需附加 `-t {dur}`(裁剪)和/或 `-af volume={gain}`(音量),都不需要则用原片;处理失败降级用原片。

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_sound_track_agent/test_bgm_assembler.py`:

```python
def test_assemble_bgm_clip_gains_attenuates(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent.bgm_assembler import assemble_bgm

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.5 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    out_loud = tmp_path / "loud.wav"; out_quiet = tmp_path / "quiet.wav"
    assemble_bgm([b0], out_loud, crossfade=0.1)                       # 原音量
    assemble_bgm([b0], out_quiet, crossfade=0.1, clip_gains=[0.25])   # 1/4 音量
    a, _ = sf.read(str(out_loud)); b, _ = sf.read(str(out_quiet))
    assert float(np.abs(b).max()) < float(np.abs(a).max()) * 0.5      # 明显更小


def test_assemble_bgm_clip_gains_length_mismatch_raises(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent.bgm_assembler import assemble_bgm
    import pytest
    b0 = tmp_path / "b0.wav"
    t = np.linspace(0, 1.0, 22050, endpoint=False)
    sf.write(str(b0), (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), 22050)
    with pytest.raises(ValueError):
        assemble_bgm([b0], tmp_path / "o.wav", clip_gains=[1.0, 0.5])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_bgm_assembler.py -k clip_gains -v`
Expected: FAIL(`assemble_bgm` 无 `clip_gains` 参数)

- [ ] **Step 3: 实现** — 在 `sound_track_agent/bgm_assembler.py` 把签名与预处理 pass 改为(其余 acrossfade 逻辑不变):

```python
def assemble_bgm(bgm_paths: list, out_path, *,
                 crossfade: float = 0.5,
                 clip_durations: list | None = None,
                 clip_gains: list | None = None,
                 runner=subprocess.run) -> Path:
    """把分段 BGM 按顺序 crossfade 拼成整条。

    clip_durations / clip_gains(可选,长度需 == bgm_paths):分别把对应 clip 先裁到
    目标秒数(trim-only)、按线性倍数调音量(ffmpeg volume=)。二者可同时给;某段都不需要
    则用原片。处理失败降级用原片。
    """
    if not bgm_paths:
        raise ValueError("assemble_bgm 需要至少 1 段 BGM")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    paths = [str(p) for p in bgm_paths]
    if clip_durations is not None and len(clip_durations) != len(paths):
        raise ValueError("clip_durations 长度需与 bgm_paths 一致")
    if clip_gains is not None and len(clip_gains) != len(paths):
        raise ValueError("clip_gains 长度需与 bgm_paths 一致")

    if clip_durations is not None or clip_gains is not None:
        resolved = []
        for i, p in enumerate(paths):
            dur = clip_durations[i] if clip_durations is not None else None
            gain = clip_gains[i] if clip_gains is not None else None
            need_trim = dur is not None
            need_gain = gain is not None and abs(float(gain) - 1.0) > 1e-6
            if not need_trim and not need_gain:
                resolved.append(p)
                continue
            tp = str(out_path.parent / f"_proc{i}.wav")
            cmd = ["ffmpeg", "-y", "-i", p]
            if need_trim:
                cmd += ["-t", f"{float(dur):.3f}"]
            if need_gain:
                cmd += ["-af", f"volume={float(gain):.4f}"]
            cmd += ["-c:a", "pcm_s16le", tp]
            r = runner(cmd, capture_output=True)
            resolved.append(tp if getattr(r, "returncode", 0) == 0
                            and Path(tp).exists() else p)
        paths = resolved
```
然后 KEEP 原文件从 `cmd = ["ffmpeg", "-y"]`(构造拼接命令)起的全部逻辑不变。

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_bgm_assembler.py -v`
Expected: PASS(原有 trim 测试仍过 + 2 新增)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/bgm_assembler.py tests/test_sound_track_agent/test_bgm_assembler.py
git commit -m "feat(soundtrack): assemble_bgm clip_gains (per-clip volume via ffmpeg)"
```

---

## Task 3: assemble_and_mix + build_accent_preview 应用各段音量

**Files:** Modify `sound_track_agent/mixdown.py`; Modify `sound_track_agent/facade.py`; Test `tests/test_sound_track_agent/test_mixdown.py`.

**说明:** 两处都按 `[getattr(s,'volume',1.0) for s in segments]` 组装 `clip_gains`,传给 `assemble_bgm`。音量与卡点无关,所以 `assemble_and_mix` 的**两个分支**(开/关卡点)都要传;`build_accent_preview` 同理。

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_sound_track_agent/test_mixdown.py`(复用文件已有的 `_make_video_with_audio`/`_tone`/`_fake_separate` 等;若无 `_fake_separate` 用内联):

```python
def test_assemble_and_mix_passes_clip_gains(tmp_path, monkeypatch):
    import sound_track_agent.mixdown as m
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate)
    v = tmp_path / "clip.mp4"; _make_video_with_audio(v, dur=2.0)
    b0 = tmp_path / "b0.wav"; _tone(b0, 440, dur=2.0)
    seen = {}
    real_assemble = m.assemble_bgm
    def spy(paths, out, **kw):
        seen["gains"] = kw.get("clip_gains")
        return real_assemble(paths, out, **kw)
    monkeypatch.setattr(m, "assemble_bgm", spy)
    sess = ScoringSession(
        source_mp4=str(v), source_hash="h", global_style="x", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=2.0,
                  candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                  chosen_candidate=0)])
    sess.segments[0].volume = 0.5
    sess.accent_mix_enabled = False        # 关卡点,走 else 分支也要带 gains
    def _sep(a, o, **k):
        from pathlib import Path
        return Path(a), Path(a)
    out = m.assemble_and_mix(sess, v, tmp_path / "w", separate=_sep)
    from pathlib import Path
    assert Path(out).exists()
    assert seen.get("gains") == [0.5]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_mixdown.py -k clip_gains -v`
Expected: FAIL(`seen["gains"]` 为 None / KeyError —— 还没传 clip_gains)

- [ ] **Step 3: 实现**

(a) `sound_track_agent/mixdown.py` `assemble_and_mix`:在算完 `seg_bgms`/`accents`/`use_accent` 后,加一行:
```python
        gains = [float(getattr(s, "volume", 1.0)) for s in sess.segments]
```
然后两个分支的 `assemble_bgm(...)` 都加 `clip_gains=gains`:
```python
        full_bgm = assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                crossfade=crossfade, clip_durations=targets,
                                clip_gains=gains)
```
```python
        full_bgm = assemble_bgm(seg_bgms, work_dir / "full_bgm.wav",
                                crossfade=crossfade, clip_gains=gains)
```
(READ 现有 `assemble_and_mix` 精确插入。`gains` 计算放在 `if use_accent:` 之前,两分支共用。)

(b) `sound_track_agent/facade.py` `build_accent_preview`:同样加
```python
    gains = [float(getattr(s, "volume", 1.0)) for s in session.segments]
```
并给两个 `assemble_bgm(...)` 调用加 `clip_gains=gains`。

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_mixdown.py tests/test_sound_track_agent/test_facade.py -v`
Expected: PASS(原有 + 新增)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/mixdown.py sound_track_agent/facade.py tests/test_sound_track_agent/test_mixdown.py
git commit -m "feat(soundtrack): apply per-segment volume (clip_gains) in mix + preview"
```

---

## Task 4: ②试听选优 每段卡片音量滑块

**Files:** Modify `drama_shot_master/ui/widgets/segment_review_widget.py`; Modify `drama_shot_master/ui/windows/soundtrack_task_window.py`; Test `tests/test_ui/test_segment_review_smoke.py`.

**说明:** `_make_card(seg)` 加一行音量:`🔊 [QSlider 0–150] {pct}%`,初值 `int(round(seg.volume*100))`。改动写 `seg.volume = v/100` 并更新百分比标签、发新信号 `segmentVolumeChanged`。任务窗把该信号连到落盘。

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_ui/test_segment_review_smoke.py`:

```python
def test_segment_volume_slider_writes_session():
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    seen = []
    w.segmentVolumeChanged.connect(lambda: seen.append(1))
    assert hasattr(w, "_vol_sliders") and len(w._vol_sliders) == 2
    w._vol_sliders[0].setValue(50)
    assert abs(sess.segments[0].volume - 0.5) < 1e-6 and seen
```
(`_sess()` 已在该测试文件定义,返回 2 段。)

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_segment_review_smoke.py -k volume -v`
Expected: FAIL(`segmentVolumeChanged` / `_vol_sliders` 不存在)

- [ ] **Step 3: 实现** — 在 `segment_review_widget.py`:

(a) 类信号区(`chosenChanged = Signal()` 附近)加:
```python
    segmentVolumeChanged = Signal()
```
(b) `__init__` 里(`self._cards: list[dict] = []` 附近)加:
```python
        self._vol_sliders: list = []
```
确保顶部已 import `QSlider`、`Qt`(文件已 import QSlider/Qt — 确认)。
(c) `_make_card(seg)` 里,在 `v.addLayout(row)` 之后、`self._cards.append(...)`/`return card` 之前,加音量行:
```python
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("🔊 音量"))
        vslider = QSlider(Qt.Horizontal)
        vslider.setRange(0, 150)
        vslider.setValue(int(round(float(getattr(seg, "volume", 1.0)) * 100)))
        vlabel = QLabel(f"{vslider.value()}%")
        vslider.valueChanged.connect(
            lambda val, s=seg, lb=vlabel: self._on_volume(s, val, lb))
        vol_row.addWidget(vslider, 1); vol_row.addWidget(vlabel)
        v.addLayout(vol_row)
        self._vol_sliders.append(vslider)
```
(d) 加槽:
```python
    def _on_volume(self, seg, val: int, label):
        seg.volume = val / 100.0
        label.setText(f"{val}%")
        self.segmentVolumeChanged.emit()
```

然后在 `soundtrack_task_window.py` 的 `_mount_session_tabs`,在连接 `self._review.chosenChanged...` 那几行附近加:
```python
        self._review.segmentVolumeChanged.connect(self._persist_session)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_segment_review_smoke.py -v`
Expected: PASS(原有 + 新增)

- [ ] **Step 5: 任务窗冒烟回归**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_window_smoke.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/widgets/segment_review_widget.py drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_segment_review_smoke.py
git commit -m "feat(soundtrack): per-segment volume slider on ②试听 cards"
```

---

## Task 5: ③卡点 试听 play/pause toggle + 进度条

**Files:** Modify `drama_shot_master/ui/widgets/accent_editor_widget.py`; Test `tests/test_ui/test_accent_editor_smoke.py`.

**说明:** 移植 ②试听页底部 seek 条范式到 ③卡点页:底部加 ▶/⏸ 按钮 + 进度条(QSlider) + 时间标签,接懒播放器的 positionChanged/durationChanged/playbackStateChanged。🎧 试听卡点效果:无预览或已脏 → 后台合成再播;已有预览 → 切换 播放/暂停。编辑卡点/泵感/开关(均发 accentsChanged)后标脏,下次 🎧 重新合成。

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_ui/test_accent_editor_smoke.py`:

```python
def test_accent_has_seekbar_and_toggle():
    _app()
    w = AccentEditorWidget(_sess(), work_dir="/tmp/none", crossfade=0.5,
                           snap_window=0.6, big_threshold=0.7)
    assert hasattr(w, "play_btn") and hasattr(w, "seek")
    assert w._player is None                 # 懒创建


def test_accent_preview_replay_toggles_when_not_dirty(tmp_path, monkeypatch):
    _app()
    w = AccentEditorWidget(_sess(), work_dir=str(tmp_path), crossfade=0.5,
                           snap_window=0.6, big_threshold=0.7)
    toggled = []
    monkeypatch.setattr(w, "_play_path", lambda p: None)
    monkeypatch.setattr(w, "_toggle_play", lambda: toggled.append(1))
    fake = tmp_path / "preview_accent_bgm.wav"; fake.write_bytes(b"x")
    w._on_preview_done(str(fake))            # 首次合成完成 → 记录预览路径、非脏
    w._on_preview_mix()                      # 再点:非脏 → 应走 toggle 而非重合成
    assert toggled == [1]


def test_accent_edit_marks_preview_dirty(tmp_path):
    _app()
    w = AccentEditorWidget(_sess(), work_dir=str(tmp_path))
    w._preview_path = "x"; w._preview_dirty = False
    w.add_accent(1.23)                       # 任何编辑(发 accentsChanged)应标脏
    assert w._preview_dirty is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_accent_editor_smoke.py -k "seekbar or replay or dirty" -v`
Expected: FAIL(`play_btn`/`_toggle_play`/`_preview_dirty` 不存在)

- [ ] **Step 3: 实现** — 在 `accent_editor_widget.py`:

(a) 顶部加模块级 helper(在 `_SEG_COLORS` 附近):
```python
def _fmt(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"
```
(b) `AccentEditorWidget.__init__`:在 `self._preview_worker = None` 后加:
```python
        self._preview_path = None
        self._preview_dirty = True
        self._user_seeking = False
        self.accentsChanged.connect(self._mark_preview_dirty)
```
(c) `_build_ui` 末尾(`root.addWidget(self.status_label)` 之后)加底部播放条:
```python
        bar = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setMaximumWidth(40)
        self.play_btn.clicked.connect(self._toggle_play)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_user_seeking", True))
        self.seek.sliderReleased.connect(self._on_seek_released)
        self.time_label = QLabel("0:00 / 0:00")
        bar.addWidget(self.play_btn); bar.addWidget(self.seek, 1)
        bar.addWidget(self.time_label)
        root.addLayout(bar)
```
(d) 改 `_ensure_player` 接上信号(若已存在 `_ensure_player`,在创建 player 后补三条 connect):
```python
    def _ensure_player(self):
        if self._player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.playbackStateChanged.connect(self._on_state)
        return self._player
```
(e) `_mark_preview_dirty` + 播放控制 + 改 `_on_preview_mix`/`_on_preview_done`:
```python
    def _mark_preview_dirty(self):
        self._preview_dirty = True

    def _toggle_play(self):
        if self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_position(self, ms: int):
        if not self._user_seeking:
            self.seek.setValue(ms)
        self.time_label.setText(f"{_fmt(ms)} / {_fmt(self.seek.maximum())}")

    def _on_duration(self, ms: int):
        self.seek.setRange(0, ms)

    def _on_state(self, _state):
        from PySide6.QtMultimedia import QMediaPlayer
        playing = (self._player is not None
                   and self._player.playbackState() == QMediaPlayer.PlayingState)
        self.play_btn.setText("⏸" if playing else "▶")

    def _on_seek_released(self):
        self._user_seeking = False
        if self._player is not None:
            self._player.setPosition(self.seek.value())
```
把现有 `_on_preview_mix` 改为(无/脏才合成,否则 toggle):
```python
    def _on_preview_mix(self):
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return
        if not self._work_dir:
            QMessageBox.information(self, "试听卡点", "无工作目录,无法试听"); return
        if not self._session.segments:
            QMessageBox.information(self, "试听卡点", "还没有段落/候选,先在①生成"); return
        if self._preview_path and not self._preview_dirty:
            self._toggle_play(); return           # 已合成且未改 → 播放/暂停
        self.btn_preview_mix.setEnabled(False)
        self.status_label.setText("正在合成卡点试听…")
        sess = self._session
        work = str(self._work_dir); cf = self._crossfade
        bt = self._big_threshold; sw = self._snap_window

        def task():
            from sound_track_agent import facade
            return facade.build_accent_preview(
                sess, work, crossfade=cf, big_threshold=bt, snap_window=sw)

        self._preview_worker = FunctionWorker(task)
        self._preview_worker.finished_with_result.connect(self._on_preview_done)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.start()
```
把现有 `_on_preview_done` 改为记录路径 + 清脏 + 播放:
```python
    def _on_preview_done(self, path: str):
        self.btn_preview_mix.setEnabled(True)
        self._preview_path = path
        self._preview_dirty = False
        self.status_label.setText("▶ 卡点试听")
        self._play_path(path)
```
(`_on_preview_failed`、`_play_path` 保持;`_play_path` 仍用懒 `_ensure_player`。`QSlider`/`Qt` 已在 Task(此前)import,确认顶部有 `from PySide6.QtCore import ... Qt` 与 `QSlider`。)

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_accent_editor_smoke.py -v`
Expected: PASS(原有 11 + 3 新增)

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/accent_editor_widget.py tests/test_ui/test_accent_editor_smoke.py
git commit -m "feat(soundtrack): ③卡点 试听 play/pause toggle + seek bar"
```

---

## Self-Review

**需求覆盖:** 需求1(再点暂停 + 进度条任意起点)→ Task 5(🎧 toggle + seek 条 + 脏标记重合成);需求2(各段音量,作用于试听与出片)→ Task 1(数据)+Task 2(assemble_bgm 应用)+Task 3(mix+preview 传入)+Task 4(②卡片滑块 UI)。

**占位符:** 无;每步给完整代码或精确 READ-then-edit。Task 2 复用原 acrossfade 后半段(已指明边界)。

**类型一致性:** `SegmentScore.volume`(Task1)→ `[s.volume for s]`(Task3)→ `assemble_bgm(clip_gains=)`(Task2)一致;`segmentVolumeChanged`(Task4)与窗口连接一致;`_preview_path/_preview_dirty/_mark_preview_dirty/_toggle_play/play_btn/seek/_fmt`(Task5)各自定义与测试断言一致;`build_accent_preview` 的 clip_gains 传入(Task3)与其已有签名兼容(内部新增 gains,不改签名)。

**风险:** 各段音量经 ffmpeg `volume=` re-encode(temp `_proc{i}.wav`),与 trim 合并同一 pass;`volume=1.0` 的段跳过处理用原片(零开销)。③试听真实音频/拖拽体验需用户在 Windows 验证;offscreen 仅验 toggle 分支与控件存在(monkeypatch `_play_path`/`_toggle_play`)。
