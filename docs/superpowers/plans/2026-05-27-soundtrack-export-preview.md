# 配乐交付 UX：导出成片 + 成片预览 + 卡点试听 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** 让用户能一键导出带卡点的成片、出片后用系统播放器预览、并在 ③卡点页快速试听卡点效果(不必整片出完)。

**Architecture:** 出片/预览按钮加在 ①配置页(复用已有 mix 管线,抽出 `_run_pipeline` 辅助);卡点试听是新的轻量 facade 函数 `build_accent_preview`(只做 段切+BGM拼接+泵感,跳过 demucs/ducking/视频混流),由 ③卡点页用 worker 跑、用懒创建的 QMediaPlayer 播放。

**Tech Stack:** PySide6 (QMediaPlayer/QAudioOutput, QDesktopServices), 复用 `sound_track_agent` 的 assemble_bgm/accent_mixer/_chosen_bgm。

**测试解释器:** `/root/miniconda3/envs/UniRig/bin/python`(记作 `$PY`);UI 测试前缀 `QT_QPA_PLATFORM=offscreen`。

**关键约束:** 绝不 `git add -A`/`.`;只 add 各任务列出的文件;工作树有用户并行的 imggen/dubbing 改动,绝不触碰/提交。offscreen 测试禁止 modal `exec()`、QAudioOutput 懒创建(避免 headless segfault),模态 QMessageBox 在测试里 monkeypatch 成 no-op。

---

## File Structure

| 文件 | 角色 | 改动 |
|------|------|------|
| `sound_track_agent/facade.py` | 加 `build_accent_preview`(轻量卡点 BGM 预览,无 demucs/视频) | Modify |
| `drama_shot_master/ui/windows/soundtrack_task_window.py` | 抽 `_run_pipeline`;加「导出成片」「预览成片」按钮 + 槽;构造 ③页时传 work_dir/crossfade/snap_window | Modify |
| `drama_shot_master/ui/widgets/accent_editor_widget.py` | 加「🎧 试听卡点效果」按钮 + 懒 QMediaPlayer + worker | Modify |
| `tests/test_sound_track_agent/test_facade.py` | build_accent_preview 测试 | Modify |
| `tests/test_ui/test_soundtrack_window_smoke.py` | 导出/预览按钮 smoke | Modify |
| `tests/test_ui/test_accent_editor_smoke.py` | 试听按钮 smoke | Modify |

---

## Task 1: facade.build_accent_preview（轻量卡点 BGM 预览）

**Files:** Modify `sound_track_agent/facade.py`; Test `tests/test_sound_track_agent/test_facade.py`.

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_sound_track_agent/test_facade.py`:

```python
def test_build_accent_preview_outputs_wav(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent import facade
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate, AccentPoint)

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    b1 = tmp_path / "b1.wav"; _tone(b1, 550)
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="g", frame_rate=24.0,
        segments=[
            SegmentScore(index=0, t_start=0.0, t_end=1.0,
                         candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                         chosen_candidate=0),
            SegmentScore(index=1, t_start=1.0, t_end=2.0,
                         candidates=[BGMCandidate(path=str(b1), seed=1, prompt="t")],
                         chosen_candidate=None)],   # 未选 → 用候选0
        accent_points=[AccentPoint(t=0.5, intensity=0.9)])
    out = facade.build_accent_preview(sess, tmp_path / "w", crossfade=0.1)
    from pathlib import Path
    assert Path(out).exists() and Path(out).stat().st_size > 0


def test_build_accent_preview_disabled_still_outputs(tmp_path):
    import numpy as np, soundfile as sf
    from sound_track_agent import facade
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, BGMCandidate)

    def _tone(p, f, dur=1.0, sr=22050):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sf.write(str(p), (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)

    b0 = tmp_path / "b0.wav"; _tone(b0, 440)
    sess = ScoringSession(
        source_mp4="x", source_hash="h", global_style="g", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0,
                  candidates=[BGMCandidate(path=str(b0), seed=1, prompt="t")],
                  chosen_candidate=0)])
    sess.accent_mix_enabled = False
    out = facade.build_accent_preview(sess, tmp_path / "w2", crossfade=0.1)
    from pathlib import Path
    assert Path(out).exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `$PY -m pytest tests/test_sound_track_agent/test_facade.py -k build_accent_preview -v`
Expected: FAIL — `AttributeError: module 'sound_track_agent.facade' has no attribute 'build_accent_preview'`

- [ ] **Step 3: 实现** — append 到 `sound_track_agent/facade.py`:

```python
def build_accent_preview(session: ScoringSession, work_dir, *,
                         crossfade: float = 0.5,
                         big_threshold: float = 0.7,
                         snap_window: float = 0.6) -> str:
    """轻量卡点试听：段切对齐 + BGM 拼接 + 泵感,产出一条 BGM wav(不含 demucs/
    ducking/视频混流),供 ③卡点页出片前快速听卡点效果。返回 wav 路径。

    各段用选定候选,未选则用候选0(_chosen_bgm 行为)。enabled 关或无卡点 → 仅拼接。
    """
    from sound_track_agent.mixdown import _chosen_bgm
    from sound_track_agent.bgm_assembler import assemble_bgm
    from sound_track_agent.accent_mixer import clip_targets, apply_pump

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    seg_bgms = [_chosen_bgm(s) for s in session.segments]
    accents = list(getattr(session, "accent_points", []) or [])
    out = work_dir / "preview_accent_bgm.wav"

    if bool(getattr(session, "accent_mix_enabled", True)) and accents:
        targets = clip_targets([s.duration for s in session.segments], accents,
                               big_threshold=big_threshold, window=snap_window,
                               min_clip=crossfade)
        raw = assemble_bgm(seg_bgms, work_dir / "_preview_raw.wav",
                           crossfade=crossfade, clip_durations=targets)
        out = apply_pump(raw, out, accents,
                         strength=float(getattr(session, "pump_strength", 0.6)))
    else:
        out = assemble_bgm(seg_bgms, out, crossfade=crossfade)
    return str(out)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `$PY -m pytest tests/test_sound_track_agent/test_facade.py -v`
Expected: PASS(原有 facade 测试 + 2 新增)

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(soundtrack): facade.build_accent_preview (lightweight accent BGM audition)"
```

---

## Task 2: ①页「导出成片」按钮（抽 _run_pipeline）

**Files:** Modify `drama_shot_master/ui/windows/soundtrack_task_window.py`; Test `tests/test_ui/test_soundtrack_window_smoke.py`.

**说明:** 现状出片靠把「停在」选成「出片」再点「开始配乐」。新增独立「🎬 导出成片」按钮,内部强制 `stop_after="mix"`、复用同一 worker 路径。先把 `_on_start` 里组装并启动 worker 的部分抽成 `_run_pipeline(stop_after)`,`_on_start` 用 combo 值调用它,新 `_on_export` 用 `"mix"` 调用它。

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_ui/test_soundtrack_window_smoke.py`(复用文件已有的构造方式;若没有现成 helper,用下面自带的):

```python
def test_window_has_export_button(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from drama_shot_master.ui.windows.soundtrack_task_window import SoundtrackTaskWindow
    QApplication.instance() or QApplication([])
    cfg = type("C", (), {"soundtrack_workflow_id": "", "soundtrack_seeds_count": 2,
                         "soundtrack_output_dir": "", "video_output_dir": str(tmp_path),
                         "soundtrack_crossfade": 0.5, "accent_big_threshold": 0.7,
                         "accent_snap_window": 0.6})()
    w = SoundtrackTaskWindow({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                             cfg, tmp_path)
    assert hasattr(w, "btn_export")
    # 导出按钮内部强制 mix：调用 _on_export 不应抛(无 session 时给出提示即可)
    w._on_export()    # 无 session/未选定 → 走门控提示,不崩
```

(若该测试文件用 `_app()`/工厂 helper 构造 window,请沿用其风格;关键是断言 `w.btn_export` 存在且 `_on_export()` 可安全调用。构造 cfg 时务必带上述属性,window 的 `_resolve_output_base`/③页需要它们。)

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_window_smoke.py -k export -v`
Expected: FAIL — `AttributeError: 'SoundtrackTaskWindow' object has no attribute 'btn_export'`

- [ ] **Step 3: 实现** — 在 `soundtrack_task_window.py`:

(a) `_build_config_tab` 的 `act` 行(`self.btn_start`/`self.btn_open_dir` 那段)加导出按钮,放在 `btn_start` 之后:

```python
        self.btn_export = QPushButton("🎬 导出成片")
        self.btn_export.setObjectName("AccentButton")
        self.btn_export.clicked.connect(self._on_export)
        act.addWidget(self.btn_start); act.addWidget(self.btn_export)
        act.addWidget(self.btn_open_dir)
        act.addStretch(1)
```
(替换原来只 add btn_start/btn_open_dir 的两行;保持 addStretch 在最后)

(b) 把 `_on_start` 里"组装 task() 闭包并启动 FunctionWorker"的部分抽成新方法 `_run_pipeline(self, stop_after)`。READ 现有 `_on_start`,把它现在用 `self.stop_combo.currentData()` 得到 `stop_after` 之后的逻辑(校验 mp4/style、出片门控、写 task、组装 task()、启动 worker)整体移入 `_run_pipeline(stop_after)`,其中:
- mp4/style 校验、`self._task["output_dir"/"mp4"/"style"]` 赋值、worker 组装与启动保持原样;
- 出片门控判断 `if stop_after == "mix" ...` 保持;
- `_on_start` 改为:

```python
    def _on_start(self):
        self._run_pipeline(self.stop_combo.currentData())
```
- 新增:

```python
    def _on_export(self):
        self._run_pipeline("mix")
```

确保 `_run_pipeline` 开头仍有 `if self._worker_busy(): QMessageBox.information(...); return` 的并发保护(原 `_on_start` 第一句)。

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_window_smoke.py -v`
Expected: PASS(原有 + 新增)。注意:`_on_export()` 在无 session 且 mp4 为空时,`_run_pipeline("mix")` 会因 mp4 不存在弹 `QMessageBox.warning` 并 return——offscreen 下直接调用方法不会阻塞(未 exec modal);若该 warning 用了会阻塞的形式,测试里 monkeypatch `m.QMessageBox.warning` 为 no-op。

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_soundtrack_window_smoke.py
git commit -m "feat(soundtrack): dedicated 导出成片 button (forces mix via _run_pipeline)"
```

---

## Task 3: ①页「预览成片」按钮（系统播放器打开）

**Files:** Modify `drama_shot_master/ui/windows/soundtrack_task_window.py`; Test `tests/test_ui/test_soundtrack_window_smoke.py`.

**说明:** 出片完成后,`self._session.output` 是 `*_scored.mp4`。加「▶ 预览成片」按钮:初始禁用,出片完成(`_on_done` 里 output 非空)或加载已有带 output 的 session 时启用;点击用 `QDesktopServices.openUrl(QUrl.fromLocalFile(output))` 调系统播放器。

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_ui/test_soundtrack_window_smoke.py`:

```python
def test_preview_button_enabled_after_output(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import drama_shot_master.ui.windows.soundtrack_task_window as m
    QApplication.instance() or QApplication([])
    cfg = type("C", (), {"soundtrack_workflow_id": "", "soundtrack_seeds_count": 2,
                         "soundtrack_output_dir": "", "video_output_dir": str(tmp_path),
                         "soundtrack_crossfade": 0.5, "accent_big_threshold": 0.7,
                         "accent_snap_window": 0.6})()
    w = m.SoundtrackTaskWindow({"id": "t1", "name": "EP1", "mp4": "", "style": ""},
                               cfg, tmp_path)
    assert hasattr(w, "btn_preview")
    assert w.btn_preview.isEnabled() is False        # 还没出片 → 禁用
    # 模拟出片完成
    opened = []
    monkeypatch.setattr(m.QDesktopServices, "openUrl", lambda url: opened.append(url))
    fake = tmp_path / "clip_scored.mp4"; fake.write_bytes(b"x")
    sess = type("S", (), {"output": str(fake)})()
    w._session = sess
    w._update_preview_enabled()
    assert w.btn_preview.isEnabled() is True
    w._on_preview()
    assert opened                                     # 调了系统打开
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_window_smoke.py -k preview_button -v`
Expected: FAIL — `AttributeError: ... has no attribute 'btn_preview'`

- [ ] **Step 3: 实现** — 在 `soundtrack_task_window.py`:

(a) `act` 行再加预览按钮(在 btn_export 之后、btn_open_dir 之前或之后均可):

```python
        self.btn_preview = QPushButton("▶ 预览成片")
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_preview.setEnabled(False)
        act.addWidget(self.btn_preview)
```
(放进 `act` 布局,顺序自定,确保在 addStretch 之前)

(b) 加方法:

```python
    def _update_preview_enabled(self):
        out = getattr(self._session, "output", None) if self._session else None
        self.btn_preview.setEnabled(bool(out) and Path(out).exists())

    def _on_preview(self):
        out = getattr(self._session, "output", None) if self._session else None
        if out and Path(out).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
        else:
            QMessageBox.information(self, "预览成片", "还没有成片,请先导出成片")
```

(c) 在 `_on_done` 末尾(设置完 self._session/output 之后)和 `_try_load_existing` 成功加载后,调用 `self._update_preview_enabled()`。READ 这两处,把调用加在合适位置(`_on_done` 中 output 分支处理之后;`_try_load_existing` 的 `if sess is not None:` 块内 `_mount_session_tabs()` 之后)。

`QDesktopServices` / `QUrl` 已在文件顶部 import(确认;若缺则补 `from PySide6.QtGui import QDesktopServices`、`QUrl` 来自 `PySide6.QtCore`)。

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_window_smoke.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_soundtrack_window_smoke.py
git commit -m "feat(soundtrack): 预览成片 button opens scored mp4 in system player"
```

---

## Task 4: ③卡点页「🎧 试听卡点效果」（懒播放器 + worker）

**Files:** Modify `drama_shot_master/ui/widgets/accent_editor_widget.py`; Modify `drama_shot_master/ui/windows/soundtrack_task_window.py`(构造 ③页传 work_dir/crossfade/snap_window); Test `tests/test_ui/test_accent_editor_smoke.py`.

**说明:** ③页加「🎧 试听卡点效果」按钮。点击 → 用 FunctionWorker 跑 `facade.build_accent_preview(session, work_dir, crossfade, big_threshold, snap_window)` 产一条 BGM wav → 用懒创建的 QMediaPlayer 播放(再点切换 播放/暂停)。AccentEditorWidget 需要 work_dir/crossfade/snap_window(big_threshold 已有),由任务窗构造时传入;缺 work_dir 时按钮禁用。

- [ ] **Step 1: 写失败测试** — append 到 `tests/test_ui/test_accent_editor_smoke.py`:

```python
def test_accent_preview_button_present_and_lazy_player():
    _app()
    w = AccentEditorWidget(_sess(), work_dir="/tmp/none", crossfade=0.5,
                           snap_window=0.6, big_threshold=0.7)
    assert hasattr(w, "btn_preview_mix")
    assert w._player is None                 # 懒创建:构造时不碰音频后端


def test_accent_preview_apply_plays(tmp_path, monkeypatch):
    _app()
    import drama_shot_master.ui.widgets.accent_editor_widget as m
    # 屏蔽真实播放(headless 无音频后端);只验证产物路径被交给播放器
    played = {}
    w = AccentEditorWidget(_sess(), work_dir=str(tmp_path), crossfade=0.5,
                           snap_window=0.6, big_threshold=0.7)
    monkeypatch.setattr(w, "_play_path", lambda p: played.setdefault("p", p))
    fake_wav = tmp_path / "preview_accent_bgm.wav"; fake_wav.write_bytes(b"x")
    w._on_preview_done(str(fake_wav))
    assert played.get("p") == str(fake_wav)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_accent_editor_smoke.py -k "preview" -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'work_dir'`

- [ ] **Step 3: 实现** — 在 `accent_editor_widget.py`:

(a) `AccentEditorWidget.__init__` 增参(keyword-only),保留已有 big_threshold:
```python
    def __init__(self, session, parent=None, *, big_threshold: float = 0.7,
                 work_dir=None, crossfade: float = 0.5, snap_window: float = 0.6):
        super().__init__(parent)
        self._session = session
        self._worker = None
        self._big_threshold = big_threshold
        self._work_dir = work_dir
        self._crossfade = crossfade
        self._snap_window = snap_window
        self._player = None
        self._audio = None
        self._preview_worker = None
        self._build_ui()
        self._refresh()
```

(b) 顶部 `top` 行在 btn_detect 之后加试听按钮:
```python
        self.btn_preview_mix = QPushButton("🎧 试听卡点效果")
        self.btn_preview_mix.setEnabled(bool(self._work_dir))
        self.btn_preview_mix.clicked.connect(self._on_preview_mix)
        top.addWidget(self.btn_preview_mix)
```

(c) 懒播放器 + 槽(放在类内合适处):
```python
    def _ensure_player(self):
        if self._player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
        return self._player

    def _play_path(self, path: str):
        from PySide6.QtCore import QUrl
        player = self._ensure_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(path))
        player.play()

    def _on_preview_mix(self):
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return
        if not self._work_dir:
            QMessageBox.information(self, "试听卡点", "无工作目录,无法试听"); return
        if not self._session.segments:
            QMessageBox.information(self, "试听卡点", "还没有段落/候选,先在①生成"); return
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

    def _on_preview_done(self, path: str):
        self.btn_preview_mix.setEnabled(True)
        self.status_label.setText("▶ 卡点试听播放中")
        self._play_path(path)

    def _on_preview_failed(self, err: str):
        self.btn_preview_mix.setEnabled(True)
        self.status_label.setText("试听失败")
        QMessageBox.critical(self, "试听失败", err)
```

(d) 顶部 import 补 `QUrl` 已在 `_play_path` 内局部 import,无需改顶部。`FunctionWorker` 已 import。

然后在 `soundtrack_task_window.py` 的 `_mount_session_tabs` 构造 ③页处,补传上下文:
```python
        self._accent = AccentEditorWidget(
            self._session,
            big_threshold=float(getattr(self.cfg, "accent_big_threshold", 0.7)),
            work_dir=str(self._work_dir()),
            crossfade=float(getattr(self.cfg, "soundtrack_crossfade", 0.5)),
            snap_window=float(getattr(self.cfg, "accent_snap_window", 0.6)))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_accent_editor_smoke.py -v`
Expected: PASS(原有 9 + 2 新增)。注意现有测试 `AccentEditorWidget(_sess())` 不传 work_dir → btn 禁用,仍可构造。

- [ ] **Step 5: 任务窗冒烟回归**

Run: `QT_QPA_PLATFORM=offscreen $PY -m pytest tests/test_ui/test_soundtrack_window_smoke.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/widgets/accent_editor_widget.py drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_accent_editor_smoke.py
git commit -m "feat(soundtrack): ③卡点 试听卡点效果 (assemble+pump BGM preview, lazy player)"
```

---

## Self-Review

**Spec 覆盖:** 导出按钮 → Task 2;成片预览(系统播放器)→ Task 3;卡点试听 → Task 1(引擎)+Task 4(UI)。三项全覆盖。

**占位符:** 无;每步给了完整代码或精确的 READ-then-edit 说明(Task 2 的 `_run_pipeline` 抽取、Task 3 的 `_on_done`/`_try_load_existing` 插入点要求先 READ 再改)。

**类型一致性:** `build_accent_preview(session, work_dir, *, crossfade, big_threshold, snap_window)` 在 Task 1 定义、Task 4 调用一致;`AccentEditorWidget(..., work_dir=, crossfade=, snap_window=, big_threshold=)` 在 Task 4 定义并由任务窗传参一致;`btn_export/_on_export/_run_pipeline/btn_preview/_on_preview/_update_preview_enabled/btn_preview_mix/_play_path/_on_preview_done` 各自定义处与测试断言一致。

**风险:** offscreen 下 QMediaPlayer/QAudioOutput 懒创建(仅试听点击时才碰音频后端),与 segment_review 既有做法一致,避免 headless segfault;测试用 monkeypatch `_play_path` 不真播。导出/预览的真实效果(系统播放器、真音频)需用户在 Windows 机器验证。
