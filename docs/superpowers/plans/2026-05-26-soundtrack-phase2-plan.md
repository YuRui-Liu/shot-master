# 配乐功能第二期 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 任务窗改 3 页签（配置生成 / 试听选优 / 卡点）+ QMediaPlayer 试听选优 + 时间轴卡点编辑 + 配乐设置对话框 + 输出路径可设 + 打开任务续跑。

**Architecture:** facade 加 3 个辅助函数（load_session/set_chosen/regenerate_segment，agent 内、不 import 宿主）。UI 新增 2 个 widget（SegmentReviewWidget/AccentEditorWidget）+ 1 个设置对话框，任务窗改造为 QTabWidget 编排三页共享 ScoringSession。config 加 4 个 soundtrack_* 标量字段。

**Tech Stack:** PySide6（QTabWidget/QMediaPlayer/QAudioOutput/自绘 widget）。**测试解释器统一用 conda：`QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest`**（它有 PySide6+QtMultimedia+agent 全套）。facade 测试 mock 重型；UI 用 offscreen 冒烟（构造+数据驱动，不测真实播放/交互）。

参考 spec：`docs/superpowers/specs/2026-05-26-soundtrack-phase2-design.md`。

## 已验证事实

- `facade.advance(session, work_dir, *, cfg, workflow_id, seeds_count=2, stop_after="mix", on_progress=None, stages=None)` 已存在。`prepare_session(mp4, style, work_dir, *, detect=...)`。`_build_real_stages(cfg, workflow_id, work_dir, global_style, seeds_count, video_path)`。
- `session.ScoringSession` 有 `save(path)`/`load(path)`/`segments`/`accent_points`；`SegmentScore` 有 `candidates: list[BGMCandidate]`/`chosen_candidate: Optional[int]`/`emotion`/`music_prompt`/`status`/`t_start`/`t_end`/`index`；`AccentPoint(t, intensity, confirmed)`。
- `Stages.generate(seg, sess) -> list[BGMCandidate]`。
- conda QtMultimedia 可用：`from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput`（WSL 无音频后端会 warn，不崩；真机 Windows 正常出声）。
- config 标量字段范式：`runninghub_workflow_id` 在 config.py 三处（字段定义 / update_settings 落盘 dict / load_config 读取）。
- 设置对话框范式：`ui/dialogs/runninghub_settings_dialog.py`（QDialog + QFormLayout + `_load_from_cfg` + `accept()` 调 `cfg.update_settings`）。
- 现有任务窗 `SoundtrackTaskWindow(task, cfg, work_root)`，含 mp4_edit/style_edit/workflow_edit/seeds_spin/stop_combo/seg_preview/进度/btn_open_dir/`closed` 信号。

---

## Task 1：config 加 4 个 soundtrack_* 字段

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 看 runninghub_workflow_id 的三处处理**

Run: `grep -n "runninghub_workflow_id" drama_shot_master/config.py`
镜像它的字段定义 / update_settings 落盘 / load_config 读取三处，给 4 个新标量字段照做。

- [ ] **Step 2: 追加失败测试**

在 `tests/test_config.py` 末尾追加：

```python
def test_config_default_soundtrack_settings(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.soundtrack_workflow_id == "2059090557116440578"
    assert cfg.soundtrack_output_dir == ""
    assert cfg.soundtrack_seeds_count == 2
    assert cfg.soundtrack_crossfade == 0.5


def test_config_soundtrack_settings_roundtrip(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(soundtrack_workflow_id="wf-x",
                        soundtrack_output_dir="/x/out",
                        soundtrack_seeds_count=3,
                        soundtrack_crossfade=0.8)
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.soundtrack_workflow_id == "wf-x"
    assert cfg2.soundtrack_output_dir == "/x/out"
    assert cfg2.soundtrack_seeds_count == 3
    assert cfg2.soundtrack_crossfade == 0.8
```

- [ ] **Step 3: 跑确认失败**

Run: `/usr/local/bin/pytest tests/test_config.py -k soundtrack_settings -q`
Expected: FAIL（AttributeError）

- [ ] **Step 4: 实现 4 个字段**

(a) `Config` dataclass 字段区（在 `soundtrack_tasks` 附近）加：
```python
    soundtrack_workflow_id: str = "2059090557116440578"
    soundtrack_output_dir: str = ""
    soundtrack_seeds_count: int = 2
    soundtrack_crossfade: float = 0.5
```
(b) `update_settings` 落盘 dict 加：
```python
                "soundtrack_workflow_id": self.soundtrack_workflow_id,
                "soundtrack_output_dir": self.soundtrack_output_dir,
                "soundtrack_seeds_count": self.soundtrack_seeds_count,
                "soundtrack_crossfade": self.soundtrack_crossfade,
```
(c) `load_config` 读取区加（类型各异，分别判型）：
```python
                if isinstance(data.get("soundtrack_workflow_id"), str):
                    cfg.soundtrack_workflow_id = data["soundtrack_workflow_id"]
                if isinstance(data.get("soundtrack_output_dir"), str):
                    cfg.soundtrack_output_dir = data["soundtrack_output_dir"]
                if isinstance(data.get("soundtrack_seeds_count"), int):
                    cfg.soundtrack_seeds_count = data["soundtrack_seeds_count"]
                if isinstance(data.get("soundtrack_crossfade"), (int, float)):
                    cfg.soundtrack_crossfade = float(data["soundtrack_crossfade"])
```

- [ ] **Step 5: 跑确认通过**

Run: `/usr/local/bin/pytest tests/test_config.py -k soundtrack -q`
Expected: PASS（含本任务 2 个 + 第一期 2 个 soundtrack_tasks 测试）。再 `/usr/local/bin/pytest tests/test_config.py -q` 确认无回归。

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/config.py tests/test_config.py
git commit -m "feat(config): 加配乐设置字段(workflow_id/output_dir/seeds_count/crossfade)"
```

---

## Task 2：facade.load_session

**Files:**
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_sound_track_agent/test_facade.py` 末尾追加：

```python
from sound_track_agent.facade import load_session


def test_load_session_none_when_absent(tmp_path):
    assert load_session(tmp_path / "nope") is None


def test_load_session_roundtrip(tmp_path):
    work = tmp_path / "w"; work.mkdir()
    sess = ScoringSession(source_mp4="/x/ep.mp4", source_hash="h",
                          global_style="冷色调", frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])
    sess.save(work / "session.json")
    loaded = load_session(work)
    assert loaded is not None
    assert loaded.global_style == "冷色调"
    assert len(loaded.segments) == 1
```

- [ ] **Step 2: 跑确认失败**

Run: `/root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_sound_track_agent/test_facade.py -k load_session -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: 追加实现**

在 `sound_track_agent/facade.py` 末尾追加：

```python
def load_session(work_dir) -> Optional[ScoringSession]:
    """work_dir/session.json 存在则加载，否则 None（供打开任务续跑/缓存）。"""
    p = Path(work_dir) / "session.json"
    if not p.exists():
        return None
    return ScoringSession.load(p)
```

- [ ] **Step 4: 跑确认通过**

Run: `/root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_sound_track_agent/test_facade.py -k load_session -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(sound_track_agent): facade.load_session（续跑/缓存读取）"
```

---

## Task 3：facade.set_chosen

**Files:**
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

- [ ] **Step 1: 追加失败测试**

```python
from sound_track_agent.facade import set_chosen


def _seg_with_cands():
    seg = SegmentScore(index=0, t_start=0.0, t_end=4.0)
    seg.candidates = [BGMCandidate(path="/a.wav", seed=1, prompt="t"),
                      BGMCandidate(path="/b.wav", seed=2, prompt="t")]
    return ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=[seg])


def test_set_chosen_writes_index():
    sess = _seg_with_cands()
    set_chosen(sess, 0, 1)
    assert sess.segments[0].chosen_candidate == 1


def test_set_chosen_out_of_range_raises():
    sess = _seg_with_cands()
    import pytest
    with pytest.raises(ValueError):
        set_chosen(sess, 0, 5)
    with pytest.raises(ValueError):
        set_chosen(sess, 9, 0)
```

- [ ] **Step 2: 跑确认失败**

Run: `/root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_sound_track_agent/test_facade.py -k set_chosen -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: 追加实现**

```python
def set_chosen(session: ScoringSession, seg_index: int, cand_index: int) -> None:
    """写 SegmentScore.chosen_candidate；越界抛 ValueError。"""
    if not (0 <= seg_index < len(session.segments)):
        raise ValueError(f"seg_index 越界: {seg_index}")
    seg = session.segments[seg_index]
    if not (0 <= cand_index < len(seg.candidates)):
        raise ValueError(f"cand_index 越界: {cand_index}")
    seg.chosen_candidate = cand_index
```

- [ ] **Step 4: 跑确认通过**

Run: `/root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_sound_track_agent/test_facade.py -k set_chosen -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(sound_track_agent): facade.set_chosen（选定候选）"
```

---

## Task 4：facade.regenerate_segment

**Files:**
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

**逻辑**：对单段重跑 generate，替换该段 candidates、清 chosen、status→generated，落盘。stages 可注入（测试 fake）；为 None 时内部 `_build_real_stages`（真实路径的 seed 变化为实现细节，spec §9）。只动目标段。

- [ ] **Step 1: 追加失败测试**

```python
from sound_track_agent.facade import regenerate_segment


def test_regenerate_segment_replaces_only_target(tmp_path):
    s0 = SegmentScore(index=0, t_start=0.0, t_end=4.0)
    s0.candidates = [BGMCandidate(path="/old0.wav", seed=1, prompt="t")]
    s0.chosen_candidate = 0
    s1 = SegmentScore(index=1, t_start=4.0, t_end=8.0)
    s1.candidates = [BGMCandidate(path="/old1.wav", seed=1, prompt="t")]
    s1.chosen_candidate = 0
    sess = ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=[s0, s1])

    class _Stages:  # 只用到 generate
        def __init__(self):
            self.generate = lambda seg, ss: [
                BGMCandidate(path=f"/new{seg.index}.wav", seed=9, prompt="t")]
            self.tag_emotion = self.compose_prompt = self.align = self.mix = None

    out = regenerate_segment(sess, 1, tmp_path / "w", cfg=object(),
                             workflow_id="wf", stages=_Stages())
    # 仅段1被替换+清选定
    assert out.segments[1].candidates[0].path == "/new1.wav"
    assert out.segments[1].chosen_candidate is None
    assert out.segments[1].status == "generated"
    # 段0 不动
    assert out.segments[0].candidates[0].path == "/old0.wav"
    assert out.segments[0].chosen_candidate == 0
    assert (tmp_path / "w" / "session.json").exists()


def test_regenerate_segment_out_of_range_raises(tmp_path):
    sess = ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])
    import pytest
    class _S:
        generate = staticmethod(lambda seg, ss: [])
    with pytest.raises(ValueError):
        regenerate_segment(sess, 9, tmp_path / "w", cfg=object(),
                           workflow_id="wf", stages=_S())
```

- [ ] **Step 2: 跑确认失败**

Run: `/root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_sound_track_agent/test_facade.py -k regenerate -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: 追加实现**

```python
def regenerate_segment(session: ScoringSession, seg_index: int, work_dir, *,
                       cfg, workflow_id: str, seeds_count: int = 2,
                       stages: Optional[Stages] = None) -> ScoringSession:
    """对单段重跑 generate（换候选、清选定），不动其它段。落盘并返回 session。"""
    if not (0 <= seg_index < len(session.segments)):
        raise ValueError(f"seg_index 越界: {seg_index}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    real = stages or _build_real_stages(
        cfg, workflow_id, work_dir, session.global_style,
        seeds_count, session.source_mp4)
    seg = session.segments[seg_index]
    seg.candidates = real.generate(seg, session)
    seg.chosen_candidate = None
    seg.status = "generated"
    session.save(work_dir / "session.json")
    return session
```

- [ ] **Step 4: 跑确认通过 + facade 全量**

Run: `/root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: PASS（第一期 4 + 本期 load_session 2 + set_chosen 2 + regenerate 2 = 10）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(sound_track_agent): facade.regenerate_segment（单段重生成）"
```

---

## Task 5：SoundtrackSettingsDialog（需求2）

**Files:**
- Create: `drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py`
- Test: `tests/test_ui/test_soundtrack_settings_smoke.py`

- [ ] **Step 1: 写 offscreen 冒烟测试**

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.dialogs.soundtrack_settings_dialog import (
    SoundtrackSettingsDialog)


def _app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    soundtrack_workflow_id = "wf-old"
    soundtrack_output_dir = "/x/out"
    soundtrack_seeds_count = 2
    soundtrack_crossfade = 0.5
    def update_settings(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_dialog_loads_and_saves():
    _app()
    cfg = _Cfg()
    dlg = SoundtrackSettingsDialog(cfg)
    assert dlg.workflow_edit.text() == "wf-old"
    assert dlg.seeds_spin.value() == 2
    dlg.workflow_edit.setText("wf-new")
    dlg.seeds_spin.setValue(3)
    dlg.accept()
    assert cfg.soundtrack_workflow_id == "wf-new"
    assert cfg.soundtrack_seeds_count == 3
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_soundtrack_settings_smoke.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 soundtrack_settings_dialog.py**

```python
"""配乐设置对话框：WorkflowID/默认输出目录/候选数/crossfade 等不常改项。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QSpinBox, QDoubleSpinBox, QWidget, QFileDialog, QDialogButtonBox,
)

from drama_shot_master.config import Config


class SoundtrackSettingsDialog(QDialog):
    """菜单栏「设置 → 配乐…」打开。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("配乐设置")
        self.setModal(True)
        self.resize(520, 240)
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.workflow_edit = QLineEdit()
        form.addRow("ACE-Step Workflow ID", self.workflow_edit)

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("空=用 视频输出目录/soundtrack")
        b = QPushButton("浏览…"); b.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1); out_row.addWidget(b)
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        form.addRow("默认输出目录", out_wrap)

        self.seeds_spin = QSpinBox(); self.seeds_spin.setRange(1, 4)
        form.addRow("默认候选数", self.seeds_spin)

        self.crossfade_spin = QDoubleSpinBox()
        self.crossfade_spin.setRange(0.0, 3.0); self.crossfade_spin.setSingleStep(0.1)
        self.crossfade_spin.setDecimals(1); self.crossfade_spin.setSuffix(" s")
        form.addRow("crossfade 时长", self.crossfade_spin)

        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_from_cfg(self):
        self.workflow_edit.setText(
            getattr(self.cfg, "soundtrack_workflow_id", ""))
        self.out_edit.setText(getattr(self.cfg, "soundtrack_output_dir", ""))
        self.seeds_spin.setValue(
            int(getattr(self.cfg, "soundtrack_seeds_count", 2)))
        self.crossfade_spin.setValue(
            float(getattr(self.cfg, "soundtrack_crossfade", 0.5)))

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择默认输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def accept(self):
        self.cfg.update_settings(
            soundtrack_workflow_id=self.workflow_edit.text().strip(),
            soundtrack_output_dir=self.out_edit.text().strip(),
            soundtrack_seeds_count=self.seeds_spin.value(),
            soundtrack_crossfade=self.crossfade_spin.value(),
        )
        super().accept()
```

- [ ] **Step 4: 跑确认通过**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_soundtrack_settings_smoke.py -q`
Expected: **1 passed**

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py tests/test_ui/test_soundtrack_settings_smoke.py
git commit -m "feat(ui): SoundtrackSettingsDialog 配乐设置对话框"
```

---

## Task 6：SegmentReviewWidget（②试听选优）

**Files:**
- Create: `drama_shot_master/ui/widgets/segment_review_widget.py`
- Test: `tests/test_ui/test_segment_review_smoke.py`

**逻辑**：按 session 每段渲染一卡片（候选按钮+播放进度+重生成）。选候选→`facade.set_chosen`+发 `chosenChanged`。重生成→发 `regenerateRequested(seg_index)`。单一 QMediaPlayer。

- [ ] **Step 1: 写 offscreen 冒烟测试**

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
from sound_track_agent.session import ScoringSession, SegmentScore, BGMCandidate


def _app():
    return QApplication.instance() or QApplication([])


def _sess():
    s0 = SegmentScore(index=0, t_start=0.0, t_end=4.0)
    s0.candidates = [BGMCandidate(path="/a.wav", seed=1, prompt="t"),
                     BGMCandidate(path="/b.wav", seed=2, prompt="t")]
    s1 = SegmentScore(index=1, t_start=4.0, t_end=8.0)
    s1.candidates = [BGMCandidate(path="/c.wav", seed=1, prompt="t")]
    return ScoringSession(source_mp4="/x", source_hash="h", global_style="s",
                          frame_rate=24.0, segments=[s0, s1])


def test_review_renders_one_card_per_segment():
    _app()
    w = SegmentReviewWidget(_sess())
    assert w.segment_card_count() == 2


def test_review_choose_sets_chosen_and_emits():
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    seen = []
    w.chosenChanged.connect(lambda: seen.append(1))
    w.choose(0, 1)                       # 选段0的候选1
    assert sess.segments[0].chosen_candidate == 1
    assert seen                          # 信号发了


def test_review_all_chosen_flag():
    _app()
    sess = _sess()
    w = SegmentReviewWidget(sess)
    assert w.all_chosen() is False
    w.choose(0, 0); w.choose(1, 0)
    assert w.all_chosen() is True


def test_review_regenerate_emits_index():
    _app()
    w = SegmentReviewWidget(_sess())
    seen = []
    w.regenerateRequested.connect(seen.append)
    w.request_regenerate(1)
    assert seen == [1]
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_segment_review_smoke.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 segment_review_widget.py**

```python
"""②试听选优：每段候选试听 + 选定 + 重生成。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from sound_track_agent import facade


class SegmentReviewWidget(QWidget):
    """按 session 渲染每段候选卡片。选定写 session、重生成发信号给任务窗。"""

    chosenChanged = Signal()
    regenerateRequested = Signal(int)        # seg_index

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._cards: list[dict] = []          # 每段：{"buttons":[QPushButton]}
        self._build_ui()

    def segment_card_count(self) -> int:
        return len(self._cards)

    def all_chosen(self) -> bool:
        return all(s.chosen_candidate is not None
                   for s in self._session.segments)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); col = QVBoxLayout(inner)
        for seg in self._session.segments:
            col.addWidget(self._make_card(seg))
        col.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _make_card(self, seg) -> QWidget:
        card = QWidget()
        v = QVBoxLayout(card)
        labels = ", ".join(seg.emotion.labels) if seg.emotion else ""
        v.addWidget(QLabel(f"段 {seg.index}  {seg.t_start:.1f}–{seg.t_end:.1f}s  {labels}"))
        row = QHBoxLayout()
        buttons = []
        for ci, cand in enumerate(seg.candidates):
            btn = QPushButton(f"▶ 候选{ci + 1}")
            btn.setCheckable(True)
            if seg.chosen_candidate == ci:
                btn.setChecked(True)
            btn.clicked.connect(
                lambda _c=False, si=seg.index, c=ci: self._on_candidate(si, c))
            row.addWidget(btn)
            buttons.append(btn)
        regen = QPushButton("↻ 重生成")
        regen.clicked.connect(lambda _c=False, si=seg.index: self.request_regenerate(si))
        row.addStretch(1); row.addWidget(regen)
        v.addLayout(row)
        self._cards.append({"buttons": buttons})
        return card

    def _on_candidate(self, seg_index: int, cand_index: int):
        # 播放该候选 + 选定
        seg = self._session.segments[seg_index]
        path = seg.candidates[cand_index].path
        if Path(path).exists():
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()
        self.choose(seg_index, cand_index)

    def choose(self, seg_index: int, cand_index: int):
        facade.set_chosen(self._session, seg_index, cand_index)
        # 单选高亮：同段其它按钮取消选中
        for ci, btn in enumerate(self._cards[seg_index]["buttons"]):
            btn.setChecked(ci == cand_index)
        self.chosenChanged.emit()

    def request_regenerate(self, seg_index: int):
        self.regenerateRequested.emit(seg_index)
```

- [ ] **Step 4: 跑确认通过**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_segment_review_smoke.py -q`
Expected: **4 passed**

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/segment_review_widget.py tests/test_ui/test_segment_review_smoke.py
git commit -m "feat(ui): SegmentReviewWidget 试听选优"
```

---

## Task 7：AccentEditorWidget（③卡点）

**Files:**
- Create: `drama_shot_master/ui/widgets/accent_editor_widget.py`
- Test: `tests/test_ui/test_accent_editor_smoke.py`

**逻辑**：列出 session.accent_points（带自绘时间轴 paintEvent 做参照，但交互走按钮/数值，第一版务实）。选中爆点 → 微调/删除；新增。改写 session.accent_points（confirmed=True），发 `accentsChanged`。

- [ ] **Step 1: 写 offscreen 冒烟测试**

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.accent_editor_widget import AccentEditorWidget
from sound_track_agent.session import ScoringSession, SegmentScore, AccentPoint


def _app():
    return QApplication.instance() or QApplication([])


def _sess():
    return ScoringSession(
        source_mp4="/x", source_hash="h", global_style="s", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=8.0)],
        accent_points=[AccentPoint(t=2.4, intensity=0.9),
                       AccentPoint(t=6.7, intensity=0.8)])


def test_accent_lists_existing():
    _app()
    w = AccentEditorWidget(_sess())
    assert w.accent_count() == 2


def test_accent_add_and_delete():
    _app()
    sess = _sess()
    w = AccentEditorWidget(sess)
    seen = []
    w.accentsChanged.connect(lambda: seen.append(1))
    w.add_accent(5.0)
    assert w.accent_count() == 3
    assert any(abs(a.t - 5.0) < 1e-6 and a.confirmed for a in sess.accent_points)
    w.delete_accent(0)               # 删第一个（按时间排序后）
    assert w.accent_count() == 2
    assert len(seen) >= 2            # add + delete 各发一次


def test_accent_nudge():
    _app()
    sess = _sess()
    w = AccentEditorWidget(sess)
    w.nudge_accent(0, 0.1)           # 第一个 +0.1
    ts = sorted(a.t for a in sess.accent_points)
    assert abs(ts[0] - 2.5) < 1e-6
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_accent_editor_smoke.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 accent_editor_widget.py**

```python
"""③卡点：列出/增删/微调 session.accent_points（第一版按钮+数值交互）。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QDoubleSpinBox,
)

from sound_track_agent.session import AccentPoint


class AccentEditorWidget(QWidget):
    """爆点编辑：增删微调，写回 session.accent_points。"""

    accentsChanged = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._build_ui()
        self._refresh()

    def accent_count(self) -> int:
        return len(self._session.accent_points)

    def _sorted_points(self) -> list:
        return sorted(self._session.accent_points, key=lambda a: a.t)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("爆点（出片时音乐重音吸附到这些时间点）："))
        self.listw = QListWidget()
        root.addWidget(self.listw, 1)

        row = QHBoxLayout()
        self.new_spin = QDoubleSpinBox()
        self.new_spin.setRange(0.0, 36000.0); self.new_spin.setDecimals(2)
        self.new_spin.setSuffix(" s")
        btn_add = QPushButton("+ 新增")
        btn_add.clicked.connect(lambda: self.add_accent(self.new_spin.value()))
        btn_del = QPushButton("🗑 删除选中")
        btn_del.clicked.connect(self._delete_selected)
        btn_minus = QPushButton("−0.1s")
        btn_minus.clicked.connect(lambda: self._nudge_selected(-0.1))
        btn_plus = QPushButton("+0.1s")
        btn_plus.clicked.connect(lambda: self._nudge_selected(0.1))
        for wdg in (self.new_spin, btn_add, btn_del, btn_minus, btn_plus):
            row.addWidget(wdg)
        row.addStretch(1)
        root.addLayout(row)

    def _refresh(self):
        self.listw.clear()
        for a in self._sorted_points():
            self.listw.addItem(f"{a.t:.2f}s  (强度 {a.intensity:.2f})")

    def add_accent(self, t: float):
        self._session.accent_points.append(
            AccentPoint(t=float(t), intensity=1.0, confirmed=True))
        self._refresh()
        self.accentsChanged.emit()

    def delete_accent(self, sorted_index: int):
        pts = self._sorted_points()
        if not (0 <= sorted_index < len(pts)):
            return
        target = pts[sorted_index]
        self._session.accent_points.remove(target)
        self._refresh()
        self.accentsChanged.emit()

    def nudge_accent(self, sorted_index: int, delta: float):
        pts = self._sorted_points()
        if not (0 <= sorted_index < len(pts)):
            return
        target = pts[sorted_index]
        target.t = max(0.0, target.t + delta)
        target.confirmed = True
        self._refresh()
        self.accentsChanged.emit()

    def _delete_selected(self):
        self.delete_accent(self.listw.currentRow())

    def _nudge_selected(self, delta: float):
        self.nudge_accent(self.listw.currentRow(), delta)
```

注：spec §2 图示含自绘时间轴；第一版用列表+按钮交互（已满足增删微调需求），自绘时间轴可视化作为后续打磨（不阻塞功能）。

- [ ] **Step 4: 跑确认通过**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_accent_editor_smoke.py -q`
Expected: **3 passed**

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/accent_editor_widget.py tests/test_ui/test_accent_editor_smoke.py
git commit -m "feat(ui): AccentEditorWidget 卡点增删微调"
```

---

## Task 8：任务窗改造（3 页签 + 精简①页 + 输出路径 + 续跑）

**Files:**
- Modify: `drama_shot_master/ui/windows/soundtrack_task_window.py`
- Test: `tests/test_ui/test_soundtrack_window_smoke.py`（改/追加）

**逻辑**：QTabWidget 三页（①现有表单精简：去 workflow/seeds 输入，从 cfg 读；② SegmentReviewWidget；③ AccentEditorWidget）。构造时 `facade.load_session(work_dir)` 续跑。输出路径解析（任务 output_dir → cfg.soundtrack_output_dir → cfg.video_output_dir/soundtrack）。重生成接 review 信号。

- [ ] **Step 1: 改冒烟测试**

把 `tests/test_ui/test_soundtrack_window_smoke.py` 改为（cfg 提供 soundtrack_* 字段；验证 3 页签 + 输出路径解析）：

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.windows.soundtrack_task_window import (
    SoundtrackTaskWindow)


def _app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    soundtrack_workflow_id = "wf-default"
    soundtrack_output_dir = ""
    soundtrack_seeds_count = 2
    soundtrack_crossfade = 0.5
    video_output_dir = "/tmp/vout"


def _task():
    return {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
            "style": "末日废土", "output_dir": "", "status": "空闲", "output": ""}


def test_window_has_three_tabs():
    _app()
    win = SoundtrackTaskWindow(_task(), cfg=_Cfg(), work_root="/tmp/stk")
    assert win.tabs.count() == 3
    assert win.style_edit.toPlainText() == "末日废土"


def test_window_emits_closed_on_close():
    _app()
    win = SoundtrackTaskWindow(_task(), cfg=_Cfg(), work_root="/tmp/stk")
    seen = []
    win.closed.connect(seen.append)
    win.close()
    assert seen == ["t1"]


def test_output_dir_resolution_falls_back():
    _app()
    win = SoundtrackTaskWindow(_task(), cfg=_Cfg(), work_root="/tmp/stk")
    # 任务无 output_dir、cfg.soundtrack_output_dir 空 → 用 video_output_dir/soundtrack
    base = win._resolve_output_base()
    assert str(base).replace("\\", "/").endswith("/tmp/vout/soundtrack") or \
           "soundtrack" in str(base)
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_soundtrack_window_smoke.py -q`
Expected: FAIL（无 tabs 属性 / 无 _resolve_output_base）

- [ ] **Step 3: 改写 soundtrack_task_window.py**

完整替换为下面内容（在第一期基础上引入 QTabWidget + 两个 widget + 路径解析 + 续跑；workflow/seeds 从 cfg 读不再放表单）：

```python
"""SoundtrackTaskWindow：单集配乐任务窗（第二期，3 页签）。

① 配置+生成（精简：去 workflow/seeds，从 cfg 读） ② 试听选优 ③ 卡点。
构造时 load_session 续跑。输出路径：任务 output_dir → cfg.soundtrack_output_dir
→ cfg.video_output_dir/soundtrack。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QComboBox, QProgressBar, QTabWidget,
    QFileDialog, QMessageBox,
)

from drama_shot_master.ui.worker import FunctionWorker
from drama_shot_master.ui.widgets.segment_review_widget import SegmentReviewWidget
from drama_shot_master.ui.widgets.accent_editor_widget import AccentEditorWidget

_STAGES = ["tag_emotion", "compose_prompt", "generate", "align", "mix"]
_STAGE_LABELS = {"tag_emotion": "切段+情绪", "compose_prompt": "prompt",
                 "generate": "生成(选优点)", "align": "对齐", "mix": "出片"}


class SoundtrackTaskWindow(QMainWindow):
    statusChanged = Signal(str, str)
    resultReady = Signal(str, str)
    closed = Signal(str)

    def __init__(self, task: dict, cfg, work_root, parent=None):
        super().__init__(parent)
        self._task = task
        self.cfg = cfg
        self._work_root = Path(work_root)
        self._worker = None
        self._session = None
        self._review = None
        self._accent = None
        self.setWindowTitle(f"配乐 · {task.get('name', '')}")
        self.resize(820, 640)
        self._build_ui()
        self._try_load_existing()

    @property
    def task_id(self) -> str:
        return self._task.get("id", "")

    def _work_dir(self) -> Path:
        return self._resolve_output_base() / self.task_id

    def _resolve_output_base(self) -> Path:
        task_out = (self._task.get("output_dir") or "").strip()
        if task_out:
            return Path(task_out)
        cfg_out = (getattr(self.cfg, "soundtrack_output_dir", "") or "").strip()
        if cfg_out:
            return Path(cfg_out)
        vout = getattr(self.cfg, "video_output_dir", "") or "."
        return Path(vout) / "soundtrack"

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._build_config_tab(), "① 配置+生成")
        self._review_holder = QWidget(); QVBoxLayout(self._review_holder)
        self.tabs.addTab(self._review_holder, "② 试听选优")
        self._accent_holder = QWidget(); QVBoxLayout(self._accent_holder)
        self.tabs.addTab(self._accent_holder, "③ 卡点")

    def _build_config_tab(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page)

        mp4_row = QHBoxLayout()
        mp4_row.addWidget(QLabel("成片 MP4:"))
        self.mp4_edit = QLineEdit(self._task.get("mp4", ""))
        b = QPushButton("浏览…"); b.clicked.connect(self._browse_mp4)
        mp4_row.addWidget(self.mp4_edit, 1); mp4_row.addWidget(b)
        root.addLayout(mp4_row)

        root.addWidget(QLabel("总风格:"))
        self.style_edit = QPlainTextEdit(self._task.get("style", ""))
        self.style_edit.setMaximumHeight(70)
        root.addWidget(self.style_edit)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("本任务输出目录(可空=用全局默认):"))
        self.out_edit = QLineEdit(self._task.get("output_dir", ""))
        ob = QPushButton("浏览…"); ob.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit, 1); out_row.addWidget(ob)
        root.addLayout(out_row)

        stop_row = QHBoxLayout()
        stop_row.addWidget(QLabel("停在:"))
        self.stop_combo = QComboBox()
        for s in _STAGES:
            self.stop_combo.addItem(_STAGE_LABELS[s], s)
        self.stop_combo.setCurrentIndex(_STAGES.index("generate"))
        stop_row.addWidget(self.stop_combo); stop_row.addStretch(1)
        root.addLayout(stop_row)

        root.addWidget(QLabel("段落预览:"))
        self.seg_preview = QPlainTextEdit(); self.seg_preview.setReadOnly(True)
        self.seg_preview.setMaximumHeight(140)
        root.addWidget(self.seg_preview, 1)

        act = QHBoxLayout()
        self.btn_start = QPushButton("🎬 开始配乐")
        self.btn_start.setObjectName("AccentButton")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_open_dir = QPushButton("📂 打开输出目录")
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        act.addWidget(self.btn_start); act.addWidget(self.btn_open_dir)
        act.addStretch(1)
        root.addLayout(act)

        self.progress = QProgressBar(); self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress_label = QLabel(""); self.progress_label.setWordWrap(True)
        root.addWidget(self.progress); root.addWidget(self.progress_label)
        return page

    def _try_load_existing(self):
        from sound_track_agent import facade
        sess = facade.load_session(self._work_dir())
        if sess is not None:
            self._session = sess
            self._mount_session_tabs()
            self._post_seg_preview(sess)
            self.progress_label.setText("已加载上次进度（可续跑/选优/编辑卡点）")

    def _mount_session_tabs(self):
        # ② 试听选优
        lay = self._review_holder.layout()
        while lay.count():
            old = lay.takeAt(0).widget()
            if old: old.deleteLater()
        self._review = SegmentReviewWidget(self._session)
        self._review.regenerateRequested.connect(self._on_regenerate)
        lay.addWidget(self._review)
        # ③ 卡点
        lay2 = self._accent_holder.layout()
        while lay2.count():
            old = lay2.takeAt(0).widget()
            if old: old.deleteLater()
        self._accent = AccentEditorWidget(self._session)
        self._accent.accentsChanged.connect(self._persist_session)
        lay2.addWidget(self._accent)

    def _persist_session(self):
        if self._session is not None:
            self._session.save(self._work_dir() / "session.json")

    def _browse_mp4(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择成片 MP4", self.mp4_edit.text() or "", "视频 (*.mp4 *.mov)")
        if p:
            self.mp4_edit.setText(p)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(
            self, "本任务输出目录", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def _post_progress(self, msg: str):
        QTimer.singleShot(0, lambda: self.progress_label.setText(msg))

    def _on_start(self):
        mp4 = self.mp4_edit.text().strip()
        style = self.style_edit.toPlainText().strip()
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无法开始", "请选择存在的成片 MP4"); return
        if not style:
            QMessageBox.warning(self, "无法开始", "请填写总风格"); return
        self._task["output_dir"] = self.out_edit.text().strip()
        self._task["mp4"] = mp4
        self._task["style"] = style
        workflow_id = getattr(self.cfg, "soundtrack_workflow_id", "")
        seeds = int(getattr(self.cfg, "soundtrack_seeds_count", 2))
        stop_after = self.stop_combo.currentData()
        work_dir = self._work_dir()
        cfg = self.cfg

        def task():
            from sound_track_agent import facade
            sess = facade.load_session(work_dir) or facade.prepare_session(
                mp4, style, work_dir)
            self._post_seg_preview(sess)
            facade.advance(sess, work_dir, cfg=cfg, workflow_id=workflow_id,
                           seeds_count=seeds, stop_after=stop_after,
                           on_progress=self._post_progress)
            return sess

        self.btn_start.setEnabled(False); self.progress.show()
        self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_regenerate(self, seg_index: int):
        if self._session is None:
            return
        workflow_id = getattr(self.cfg, "soundtrack_workflow_id", "")
        seeds = int(getattr(self.cfg, "soundtrack_seeds_count", 2))
        work_dir = self._work_dir(); cfg = self.cfg; sess = self._session

        def task():
            from sound_track_agent import facade
            facade.regenerate_segment(sess, seg_index, work_dir, cfg=cfg,
                                      workflow_id=workflow_id, seeds_count=seeds)
            return sess

        self.progress.show(); self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_regen_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _post_seg_preview(self, sess):
        lines = [f"段{s.index}  {s.t_start:.1f}–{s.t_end:.1f}s" for s in sess.segments]
        QTimer.singleShot(0, lambda: self.seg_preview.setPlainText("\n".join(lines)))

    def _on_done(self, sess):
        self.progress.hide(); self.btn_start.setEnabled(True)
        self._session = sess
        self._mount_session_tabs()
        out = getattr(sess, "output", None)
        if out:
            self.statusChanged.emit(self.task_id, "完成")
            self.resultReady.emit(self.task_id, out)
            self.progress_label.setText(f"完成：{out}")
        else:
            self.statusChanged.emit(self.task_id, "空闲")
            self.progress_label.setText(
                f"已停在选优点：候选已生成在 {self._work_dir()}（切到「② 试听选优」试听选定）")
            self.tabs.setCurrentIndex(1)

    def _on_regen_done(self, sess):
        self.progress.hide()
        self._mount_session_tabs()
        self.tabs.setCurrentIndex(1)
        self.statusChanged.emit(self.task_id, "空闲")

    def _on_failed(self, err: str):
        self.progress.hide(); self.btn_start.setEnabled(True)
        self.statusChanged.emit(self.task_id, "失败")
        QMessageBox.critical(self, "配乐失败", err)

    def _open_output_dir(self):
        wd = self._work_dir()
        if wd.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(wd)))
        else:
            QMessageBox.information(self, "打开输出目录", "还没有输出（先运行一次）")

    def closeEvent(self, event):
        self.closed.emit(self.task_id)
        super().closeEvent(event)
```

- [ ] **Step 4: 跑确认通过**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_soundtrack_window_smoke.py -q`
Expected: **3 passed**

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_soundtrack_window_smoke.py
git commit -m "feat(ui): 配乐任务窗 3 页签(试听选优+卡点)+输出路径+续跑"
```

---

## Task 9：main_window [设置]→[配乐…] 入口

**Files:**
- Modify: `drama_shot_master/ui/main_window.py`
- Test: `tests/test_ui/test_main_window_soundtrack_smoke.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_ui/test_main_window_soundtrack_smoke.py` 末尾追加：

```python
def test_main_window_has_soundtrack_settings_method():
    app = QApplication.instance() or QApplication([])
    from drama_shot_master.ui.main_window import MainWindow
    w = MainWindow()
    assert hasattr(w, "_open_soundtrack_settings")
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/test_main_window_soundtrack_smoke.py -q`
Expected: 新测试 FAIL（无 _open_soundtrack_settings）

- [ ] **Step 3: 改 main_window.py**

(a) 在 `_build_ui` 的「设置」菜单（`sm.addAction` 那几行附近，提示词优化配置之后）加：
```python
        a_st = QAction("配乐…", self)
        a_st.triggered.connect(self._open_soundtrack_settings)
        sm.addAction(a_st)
```
(b) 加方法（放在 `_open_refine_settings` 附近）：
```python
    def _open_soundtrack_settings(self):
        from drama_shot_master.ui.dialogs.soundtrack_settings_dialog import (
            SoundtrackSettingsDialog)
        SoundtrackSettingsDialog(self.cfg, parent=self).exec()
```

- [ ] **Step 4: 跑确认通过 + 全 UI 回归**

Run: `QT_QPA_PLATFORM=offscreen /root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_ui/ -q`
Expected: 全 UI 冒烟通过（settings 1 + review 4 + accent 3 + window 3 + main_window 原2+新1 + panel 1）

Run: `/root/miniconda3/envs/UniRig/bin/python -m pytest tests/test_sound_track_agent/ -q`
Expected: agent 全量通过（67 + facade 本期 6 = 73）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/main_window.py tests/test_ui/test_main_window_soundtrack_smoke.py
git commit -m "feat(ui): [设置]→[配乐…] 入口"
```

---

## 端到端冒烟（人工，非自动）

第二期完成后，真机验证（conda python 启动）：
1. [设置]→[配乐…] 设 WorkflowID / 默认输出目录 / 候选数。
2. 配乐 tab → 新建任务 → ①页填 MP4+风格 → 停在"生成" → 开始。
3. 跑完自动跳「② 试听选优」→ 每段试听候选、选定，不满意「↻ 重生成」。
4. 「③ 卡点」→ 增删/微调爆点。
5. 回①页"停在"改"出片"→ 开始（续跑，幂等跳过已生成）→ 出成片。
6. 关窗重开任务 → 应加载上次进度（续跑）。
QMediaPlayer 真实播放、出片音画需真机验证（WSL 无音频后端）。
```
