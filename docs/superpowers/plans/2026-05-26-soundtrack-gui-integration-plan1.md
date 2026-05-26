# 配乐功能接入导演台 · 第一期（骨架）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 `sound_track_agent` 以顶部"配乐"tab 接入导演台：facade 两函数 + 任务列表面板 + 单集任务窗骨架 + main_window 一处 try-import 注册，保持 agent 可整包拆除。

**Architecture:** GUI 只依赖 `sound_track_agent/facade.py`（prepare_session/advance，鸭子类型读 cfg、不 import 宿主）。UI 复用视频生成的"任务列表+任务窗"范式 + `FunctionWorker` 后台线程。配乐任务以 `cfg.soundtrack_tasks`（list[dict]）持久化。main_window 用 try-import 注册，agent 缺失则跳过该 tab、宿主照常启动。

**Tech Stack:** facade 复用 agent 既有模块（detect_shots/plan_segments/build_stages/pipeline.run/mixdown/provider）；UI 用 PySide6 复用 BasePanel/FunctionWorker。facade 单测 mock 重型边界；UI 用 offscreen 冒烟。

参考 spec：`docs/superpowers/specs/2026-05-26-soundtrack-gui-integration-design.md`。

## 已验证事实

- `sound_track_agent` 全部模块已完成（63 测试过）。关键接口：`shot_detector.detect_shots(mp4)->list[Shot]`、`segment_planner.plan_segments(shots)->list[SegmentScore]`、`stages_factory.build_stages(*, provider, client, workflow_id, work_dir, global_style, seeds, frame_provider, mix_fn, align_fn)->Stages`、`pipeline.run(sess, stages, session_path, stop_after)->Optional[str]`、`mixdown.extract_segment_frame(video, seg, out_png)`、`mixdown.assemble_and_mix(sess, video, work_dir)->str`、`provider.build_soundtrack_provider(cfg)`、`session.ScoringSession/SegmentScore/hash_file`。
- 宿主：`BasePanel(state, cfg)` 子类，信号 `statusMessage`/`validityChanged`，方法 `select_mode/validate/execute`。`FunctionWorker(func,*a,**kw)` 发 `finished_with_result(object)`/`failed(str)`。`RunningHubClient(api_key, base_url=...)`。`cfg.update_settings(**kw)` 落盘。`VideoTaskManagerPanel(state,cfg,store,open_cb,close_cb,persist_cb)` 是范式参考。
- 测试：agent 测试用 `/usr/bin/python3 -m pytest`（cv2/scenedetect 在该解释器）。UI offscreen 冒烟用 `QT_QPA_PLATFORM=offscreen`。

## 文件结构（第一期）

```
sound_track_agent/facade.py                          ← 新增（prepare_session + advance + _read_fps）
tests/test_sound_track_agent/test_facade.py          ← 新增
drama_shot_master/config.py                          ← 改（加 soundtrack_tasks 字段）
tests/test_config.py                                 ← 改（加 soundtrack_tasks 断言）
drama_shot_master/ui/panels/soundtrack_panel.py      ← 新增（任务列表）
drama_shot_master/ui/windows/soundtrack_task_window.py ← 新增（单集任务窗骨架）
drama_shot_master/ui/main_window.py                  ← 改（FUNCS + try-import 注册）
```

---

## Task 1：facade.prepare_session（MP4 → 段落 session）

**Files:**
- Create: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_facade.py`

**逻辑**：`prepare_session(mp4, style, work_dir, *, detect=detect_shots) -> ScoringSession`。调 `detect`（可注入）切镜头 → `plan_segments` → 建 `ScoringSession`（source_hash=hash_file、frame_rate 由 `_read_fps` 读，失败默认 24.0）。不需要 cfg（不调豆包/ACE-Step），故签名不含 cfg。

- [ ] **Step 1: 写失败测试**

`tests/test_sound_track_agent/test_facade.py`:

```python
from pathlib import Path
from sound_track_agent.facade import prepare_session
from sound_track_agent.segment_planner import Shot
from sound_track_agent.session import ScoringSession


def test_prepare_session_builds_segments(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"fakemp4")
    fake_shots = [Shot(index=0, t_start=0.0, t_end=4.0),
                  Shot(index=1, t_start=4.0, t_end=8.0)]
    sess = prepare_session(mp4, "末日废土", tmp_path / "work",
                           detect=lambda p: fake_shots)
    assert isinstance(sess, ScoringSession)
    assert sess.global_style == "末日废土"
    assert sess.source_mp4 == str(mp4)
    assert len(sess.source_hash) == 16          # hash_file 前 16 hex
    assert len(sess.segments) >= 1
    assert sess.segments[0].t_start == 0.0


def test_prepare_session_frame_rate_defaults_when_unreadable(tmp_path):
    mp4 = tmp_path / "ep.mp4"; mp4.write_bytes(b"notavideo")
    sess = prepare_session(mp4, "x", tmp_path / "w",
                           detect=lambda p: [Shot(0, 0.0, 2.0)])
    assert sess.frame_rate == 24.0              # 读不出 fps → 默认 24
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 prepare_session + _read_fps**

`sound_track_agent/facade.py`:

```python
"""配乐 agent 对外门面：GUI 只依赖本模块。

不 import 任何 drama_shot_master；cfg 以鸭子类型读取（getattr）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sound_track_agent.shot_detector import detect_shots
from sound_track_agent.segment_planner import plan_segments
from sound_track_agent.session import ScoringSession, hash_file


def _read_fps(video_path) -> float:
    """读视频帧率；读不到返回 24.0。"""
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        cap.release()
        return float(fps) if fps and fps > 0 else 24.0
    except Exception:
        return 24.0


def prepare_session(mp4, style: str, work_dir, *,
                    detect: Callable = detect_shots) -> ScoringSession:
    """MP4 → 切镜头 → 段落聚合 → 新建 ScoringSession（快，不调豆包/ACE-Step）。"""
    mp4 = Path(mp4)
    shots = detect(mp4)
    segments = plan_segments(shots)
    return ScoringSession(
        source_mp4=str(mp4),
        source_hash=hash_file(mp4),
        global_style=style,
        frame_rate=_read_fps(mp4),
        segments=segments,
    )
```

- [ ] **Step 4: 跑确认通过**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: **2 passed**

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(sound_track_agent): facade.prepare_session（MP4→段落 session）"
```

---

## Task 2：facade.advance（推进 + 进度回调）

**Files:**
- Modify: `sound_track_agent/facade.py`（追加 advance + _build_real_stages）
- Test: `tests/test_sound_track_agent/test_facade.py`（追加）

**逻辑**：`advance(session, work_dir, *, cfg, workflow_id, seeds_count=2, stop_after="mix", on_progress=None, stages=None) -> ScoringSession`。`stages` 可注入（测试传 fake）；为 None 时内部 `_build_real_stages(cfg, workflow_id, work_dir, session.global_style, seeds_count, video_path=session.source_mp4)` 真实组装。用 progress 包装器把 `pipeline.run` 推进过程经 `on_progress` 报出，跑完返回 session。

- [ ] **Step 1: 追加失败测试**

在 `tests/test_sound_track_agent/test_facade.py` 末尾追加：

```python
from sound_track_agent.facade import advance
from sound_track_agent.pipeline import Stages
from sound_track_agent.session import SegmentScore, EmotionTag, BGMCandidate


def _sess(tmp_path):
    return ScoringSession(
        source_mp4=str(tmp_path / "ep.mp4"), source_hash="h",
        global_style="末日废土", frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])


def _fake_stages():
    return Stages(
        tag_emotion=lambda seg, s: EmotionTag(labels=["tense"], arousal=0.7),
        compose_prompt=lambda seg, s: f"tags-{seg.index}",
        generate=lambda seg, s: [BGMCandidate(path="/x/b.wav", seed=1, prompt="t")],
        align=lambda s: None,
        mix=lambda s: "/x/out.mp4",
    )


def test_advance_runs_with_injected_stages_and_reports_progress(tmp_path):
    sess = _sess(tmp_path)
    msgs = []
    out = advance(sess, tmp_path / "work", cfg=object(), workflow_id="wf",
                  stop_after="mix", stages=_fake_stages(),
                  on_progress=msgs.append)
    assert out.output == "/x/out.mp4"
    assert all(s.status == "aligned" for s in out.segments)
    assert len(msgs) >= 1                       # 进度有上报


def test_advance_stop_after_generate_no_mix(tmp_path):
    sess = _sess(tmp_path)
    out = advance(sess, tmp_path / "work", cfg=object(), workflow_id="wf",
                  stop_after="generate", stages=_fake_stages())
    assert out.output is None
    assert all(s.status == "generated" for s in out.segments)
    assert (tmp_path / "work" / "session.json").exists()   # 落盘
```

- [ ] **Step 2: 跑确认失败**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: 2 新测试 FAIL（ImportError: advance）

- [ ] **Step 3: 追加实现**

在 `sound_track_agent/facade.py` 顶部 import 区追加：

```python
from functools import partial

from sound_track_agent.pipeline import Stages, run as _pipeline_run, STAGE_ORDER
```

文件末尾追加：

```python
def _build_real_stages(cfg, workflow_id, work_dir, global_style,
                       seeds_count, video_path) -> Stages:
    """组装真实 Stages（豆包 provider + RunningHub client + mixdown）。

    本函数是 facade 唯一碰宿主依赖的地方，仍只读 cfg 属性、不 import 宿主。
    """
    from drama_shot_master.providers.runninghub import RunningHubClient
    from sound_track_agent.provider import build_soundtrack_provider
    from sound_track_agent.stages_factory import build_stages
    from sound_track_agent.mixdown import extract_segment_frame, assemble_and_mix

    provider = build_soundtrack_provider(cfg)
    client = RunningHubClient(
        getattr(cfg, "runninghub_api_key", ""),
        base_url=getattr(cfg, "runninghub_base_url",
                         "https://www.runninghub.cn"))
    work_dir = Path(work_dir)
    frames_dir = work_dir / "frames"
    return build_stages(
        provider=provider, client=client, workflow_id=workflow_id,
        work_dir=work_dir, global_style=global_style,
        seeds=list(range(1, seeds_count + 1)),
        frame_provider=lambda seg: extract_segment_frame(
            video_path, seg, frames_dir / f"seg{seg.index}.png"),
        mix_fn=partial(assemble_and_mix, video_path=video_path,
                       work_dir=work_dir),
    )


def _wrap_progress(stages: Stages, on_progress) -> Stages:
    """包装 stages 的每段回调，调用前用 on_progress 报一句。"""
    if on_progress is None:
        return stages

    def wrap(fn, label):
        def inner(seg, sess):
            on_progress(f"{label} 段 {seg.index}…")
            return fn(seg, sess)
        return inner

    def wrap_whole(fn, label):
        def inner(sess):
            on_progress(f"{label}…")
            return fn(sess)
        return inner

    return Stages(
        tag_emotion=wrap(stages.tag_emotion, "情绪分析"),
        compose_prompt=wrap(stages.compose_prompt, "生成 prompt"),
        generate=wrap(stages.generate, "生成 BGM"),
        align=wrap_whole(stages.align, "对齐卡点"),
        mix=wrap_whole(stages.mix, "混音出片"),
    )


def advance(session: ScoringSession, work_dir, *, cfg, workflow_id: str,
            seeds_count: int = 2, stop_after: str = "mix",
            on_progress: Optional[Callable[[str], None]] = None,
            stages: Optional[Stages] = None) -> ScoringSession:
    """从 session 当前状态推进到 stop_after（可重复调用=续跑）。

    stages 可注入（测试用 fake）；为 None 时内部组装真实 stages。
    """
    if stop_after not in STAGE_ORDER:
        raise ValueError(f"未知 stop_after: {stop_after}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    real = stages or _build_real_stages(
        cfg, workflow_id, work_dir, session.global_style,
        seeds_count, session.source_mp4)
    real = _wrap_progress(real, on_progress)
    _pipeline_run(session, real,
                  session_path=work_dir / "session.json",
                  stop_after=stop_after)
    return session
```

- [ ] **Step 4: 跑确认通过 + 全量回归**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/test_facade.py -q`
Expected: **4 passed**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/ -q`
Expected: 全量通过（63 + facade 4 = 67）

- [ ] **Step 5: Commit**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_facade.py
git commit -m "feat(sound_track_agent): facade.advance（推进+进度回调，stages 可注入）"
```

---

## Task 3：config 加 soundtrack_tasks 字段

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_config.py`（追加）

**逻辑**：`Config` 加 `soundtrack_tasks: list = field(default_factory=list)`，`update_settings` 落盘 dict 加该键，`load_config` 从 settings.json 读（list 类型）。参考现有 `video_tasks` 字段的处理方式。

- [ ] **Step 1: 先确认 video_tasks 的现有处理**

Run: `grep -n "video_tasks" drama_shot_master/config.py`
Expected: 看到 video_tasks 在字段定义、update_settings 落盘 dict、load_config 读取三处。soundtrack_tasks 照抄这三处。

- [ ] **Step 2: 追加失败测试**

在 `tests/test_config.py` 末尾追加：

```python
def test_config_default_soundtrack_tasks_empty(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.soundtrack_tasks == []


def test_config_soundtrack_tasks_roundtrip(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(soundtrack_tasks=[{"id": "t1", "name": "EP01",
                                           "mp4": "/x/ep1.mp4", "style": "冷色调"}])
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["soundtrack_tasks"][0]["name"] == "EP01"
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.soundtrack_tasks[0]["mp4"] == "/x/ep1.mp4"
```

- [ ] **Step 3: 跑确认失败**

Run: `/usr/local/bin/pytest tests/test_config.py -k soundtrack -q`
Expected: FAIL（AttributeError: soundtrack_tasks 或断言失败）

- [ ] **Step 4: 实现（仿 video_tasks 三处）**

(a) `Config` 字段区加（在 `video_tasks` 附近）：
```python
    soundtrack_tasks: list = field(default_factory=list)
```
(b) `update_settings` 的落盘 dict 加一行（在 video_tasks 附近）：
```python
                "soundtrack_tasks": self.soundtrack_tasks,
```
(c) `load_config` 读取区加（在 video_tasks 读取附近，按其写法）：
```python
                if "soundtrack_tasks" in data and isinstance(
                        data["soundtrack_tasks"], list):
                    cfg.soundtrack_tasks = data["soundtrack_tasks"]
```
注意：若 `video_tasks` 不在 config.py（而在别处管理），则按 config.py 实际的 list 字段处理惯例照做；务必让两个测试通过。

- [ ] **Step 5: 跑确认通过**

Run: `/usr/local/bin/pytest tests/test_config.py -k soundtrack -q`
Expected: **2 passed**。再跑 `/usr/local/bin/pytest tests/test_config.py -q` 确认无回归。

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/config.py tests/test_config.py
git commit -m "feat(config): 加 soundtrack_tasks 持久化字段"
```

---

## Task 4：SoundtrackPanel（任务列表面板）

**Files:**
- Create: `drama_shot_master/ui/panels/soundtrack_panel.py`
- Test: `tests/test_ui/test_soundtrack_panel_smoke.py`

**逻辑**：BasePanel 子类，QTableWidget 任务列表（名称/MP4/状态/输出 + 状态色标）+ 新建/打开/删除按钮。任务以 `list[dict]` 维护，经 `persist_cb` 落盘。开窗经 `open_window_cb(task_dict)`。无 GUI 交互单测，只 offscreen 冒烟（构造不崩 + 新建任务进列表）。

- [ ] **Step 1: 写 offscreen 冒烟测试**

`tests/test_ui/test_soundtrack_panel_smoke.py`（若 `tests/test_ui/` 无 `__init__.py` 则一并建空文件）:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_panel_constructs_and_lists_tasks():
    _app()
    opened = []
    panel = SoundtrackPanel(
        state=None,
        cfg=type("C", (), {"soundtrack_tasks": [
            {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
             "style": "冷色调", "status": "空闲", "output": ""}]})(),
        open_window_cb=lambda t: opened.append(t),
        persist_cb=lambda: None,
    )
    assert panel.table.rowCount() == 1
    assert panel.select_mode() == "none"
    ok, _why = panel.validate()
    assert ok is False
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/test_ui/test_soundtrack_panel_smoke.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 soundtrack_panel.py**

```python
"""SoundtrackPanel：配乐任务列表（顶部"配乐"tab 内容）。

任务以 list[dict] 维护，结构：{id,name,mp4,style,workflow_id,status,output}。
状态色标同视频任务。开窗/持久化由 main_window 经回调注入。
"""
from __future__ import annotations

import time
from secrets import token_hex

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView,
)

from drama_shot_master.ui.panels.base_panel import BasePanel

_STATUS_COLORS = {
    "空闲": "#9aa0a6", "生成中": "#4a9eff", "完成": "#4ec98f", "失败": "#ff5c5c",
}


def _gen_id() -> str:
    return f"{int(time.time() * 1000)}{token_hex(3)[:5]}"


class SoundtrackPanel(BasePanel):
    """配乐任务列表。开窗与持久化由回调交给 main_window。"""

    def __init__(self, state, cfg, open_window_cb, persist_cb, parent=None):
        super().__init__(state, cfg, parent)
        self._open_window_cb = open_window_cb
        self._persist_cb = persist_cb
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self) -> tuple[bool, str]:
        return False, "请用列表内按钮管理配乐任务"

    def execute(self):
        raise NotImplementedError

    def _tasks(self) -> list:
        return getattr(self.cfg, "soundtrack_tasks", [])

    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_new = QPushButton("+ 新建配乐任务")
        self.btn_open = QPushButton("打开")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "成片 MP4", "状态", "输出"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemDoubleClicked.connect(lambda _it: self._on_open())
        root.addWidget(self.table, 1)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_del.clicked.connect(self._on_del)

    @staticmethod
    def _ro(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    def _status_item(self, status: str) -> QTableWidgetItem:
        it = self._ro(status)
        color = _STATUS_COLORS.get(status)
        if color:
            it.setForeground(QColor(color))
            if status in ("生成中", "失败"):
                f = QFont(); f.setBold(True); it.setFont(f)
        return it

    def refresh(self):
        self.table.setRowCount(0)
        for t in self._tasks():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = self._ro(t.get("name", "未命名"))
            name_item.setData(Qt.UserRole, t.get("id"))
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, self._ro(t.get("mp4", "")))
            self.table.setItem(r, 2, self._status_item(t.get("status", "空闲")))
            self.table.setItem(r, 3, self._ro(t.get("output") or "—"))

    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        tid = item.data(Qt.UserRole) if item else None
        return next((t for t in self._tasks() if t.get("id") == tid), None)

    def _on_new(self):
        n = len(self._tasks()) + 1
        task = {"id": _gen_id(), "name": f"配乐任务 {n}", "mp4": "",
                "style": "", "workflow_id": "", "status": "空闲", "output": ""}
        self._tasks().append(task)
        self._persist_cb()
        self.refresh()
        self._open_window_cb(task)

    def _on_open(self):
        t = self._selected()
        if not t:
            QMessageBox.information(self, "打开", "请先选一个任务")
            return
        self._open_window_cb(t)

    def _on_del(self):
        t = self._selected()
        if not t:
            return
        if QMessageBox.question(self, "删除", "确定删除该配乐任务？",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._tasks().remove(t)
        self._persist_cb()
        self.refresh()
```

- [ ] **Step 4: 跑确认通过**

Run: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/test_ui/test_soundtrack_panel_smoke.py -q`
Expected: **1 passed**

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/soundtrack_panel.py tests/test_ui/test_soundtrack_panel_smoke.py
git commit -m "feat(ui): SoundtrackPanel 配乐任务列表面板"
```

---

## Task 5：SoundtrackTaskWindow（单集任务窗骨架）

**Files:**
- Create: `drama_shot_master/ui/windows/soundtrack_task_window.py`
- Test: `tests/test_ui/test_soundtrack_window_smoke.py`

**逻辑**：QMainWindow，表单（MP4/风格/Workflow ID/候选数/停在）+ 段落预览 + 开始/取消 + 进度。「开始」用 `FunctionWorker` 跑 `facade.prepare_session` + `facade.advance`，进度经 `QTimer.singleShot(0,...)` 回主线程。完成发 `statusChanged(task_id, status)` 给 panel。offscreen 冒烟只验证构造 + 表单默认值（不真跑配乐）。

- [ ] **Step 1: 写 offscreen 冒烟测试**

`tests/test_ui/test_soundtrack_window_smoke.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.windows.soundtrack_task_window import (
    SoundtrackTaskWindow, DEFAULT_WORKFLOW_ID)


def _app():
    return QApplication.instance() or QApplication([])


def test_window_constructs_with_task_defaults():
    _app()
    task = {"id": "t1", "name": "EP01", "mp4": "/x/ep1.mp4",
            "style": "末日废土", "workflow_id": "", "status": "空闲", "output": ""}
    win = SoundtrackTaskWindow(task, cfg=type("C", (), {})(), work_root="/tmp/stk")
    assert win.task_id == "t1"
    assert win.style_edit.toPlainText() == "末日废土"
    assert win.mp4_edit.text() == "/x/ep1.mp4"
    # 空 workflow_id → 回落默认
    assert win.workflow_edit.text() == DEFAULT_WORKFLOW_ID
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/test_ui/test_soundtrack_window_smoke.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 soundtrack_task_window.py**

```python
"""SoundtrackTaskWindow：单集配乐任务窗（第一期骨架）。

表单 + 段落预览 + 进度。开始 → FunctionWorker 跑 facade.prepare_session + advance。
试听选优/卡点编辑留第二期。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QComboBox, QProgressBar,
    QFileDialog, QMessageBox,
)

from drama_shot_master.ui.worker import FunctionWorker

DEFAULT_WORKFLOW_ID = "2059090557116440578"
_STAGES = ["tag_emotion", "compose_prompt", "generate", "align", "mix"]
_STAGE_LABELS = {"tag_emotion": "切段+情绪", "compose_prompt": "prompt",
                 "generate": "生成(选优点)", "align": "对齐", "mix": "出片"}


class SoundtrackTaskWindow(QMainWindow):
    """单集配乐任务窗。"""

    statusChanged = Signal(str, str)        # (task_id, status_text)
    resultReady = Signal(str, str)          # (task_id, output_path)

    def __init__(self, task: dict, cfg, work_root, parent=None):
        super().__init__(parent)
        self._task = task
        self.cfg = cfg
        self._work_root = Path(work_root)
        self._worker = None
        self.setWindowTitle(f"配乐 · {task.get('name', '')}")
        self.resize(680, 560)
        self._build_ui()

    @property
    def task_id(self) -> str:
        return self._task.get("id", "")

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)

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

        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("Workflow ID:"))
        self.workflow_edit = QLineEdit(
            self._task.get("workflow_id") or DEFAULT_WORKFLOW_ID)
        cfg_row.addWidget(self.workflow_edit, 1)
        cfg_row.addWidget(QLabel("候选数:"))
        self.seeds_spin = QSpinBox(); self.seeds_spin.setRange(1, 4)
        self.seeds_spin.setValue(2)
        cfg_row.addWidget(self.seeds_spin)
        cfg_row.addWidget(QLabel("停在:"))
        self.stop_combo = QComboBox()
        for s in _STAGES:
            self.stop_combo.addItem(_STAGE_LABELS[s], s)
        self.stop_combo.setCurrentIndex(_STAGES.index("generate"))
        cfg_row.addWidget(self.stop_combo)
        root.addLayout(cfg_row)

        root.addWidget(QLabel("段落预览:"))
        self.seg_preview = QPlainTextEdit(); self.seg_preview.setReadOnly(True)
        self.seg_preview.setMaximumHeight(160)
        root.addWidget(self.seg_preview, 1)

        act = QHBoxLayout()
        self.btn_start = QPushButton("🎬 开始配乐")
        self.btn_start.setObjectName("AccentButton")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel = QPushButton("取消"); self.btn_cancel.setEnabled(False)
        act.addWidget(self.btn_start); act.addWidget(self.btn_cancel)
        act.addStretch(1)
        root.addLayout(act)

        self.progress = QProgressBar(); self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress_label = QLabel("")
        root.addWidget(self.progress); root.addWidget(self.progress_label)

    def _browse_mp4(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择成片 MP4", self.mp4_edit.text() or "", "视频 (*.mp4 *.mov)")
        if p:
            self.mp4_edit.setText(p)

    def _post_progress(self, msg: str):
        QTimer.singleShot(0, lambda: self.progress_label.setText(msg))

    def _on_start(self):
        mp4 = self.mp4_edit.text().strip()
        style = self.style_edit.toPlainText().strip()
        if not mp4 or not Path(mp4).exists():
            QMessageBox.warning(self, "无法开始", "请选择存在的成片 MP4")
            return
        if not style:
            QMessageBox.warning(self, "无法开始", "请填写总风格")
            return
        workflow_id = self.workflow_edit.text().strip() or DEFAULT_WORKFLOW_ID
        seeds = self.seeds_spin.value()
        stop_after = self.stop_combo.currentData()
        work_dir = self._work_root / self.task_id
        cfg = self.cfg

        def task():
            from sound_track_agent import facade
            sess = facade.prepare_session(mp4, style, work_dir)
            self._post_seg_preview(sess)
            return facade.advance(
                sess, work_dir, cfg=cfg, workflow_id=workflow_id,
                seeds_count=seeds, stop_after=stop_after,
                on_progress=self._post_progress)

        self.btn_start.setEnabled(False)
        self.progress.show()
        self.statusChanged.emit(self.task_id, "生成中")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _post_seg_preview(self, sess):
        lines = [f"段{s.index}  {s.t_start:.1f}–{s.t_end:.1f}s" for s in sess.segments]
        QTimer.singleShot(0, lambda: self.seg_preview.setPlainText("\n".join(lines)))

    def _on_done(self, sess):
        self.progress.hide()
        self.btn_start.setEnabled(True)
        out = getattr(sess, "output", None)
        if out:
            self.statusChanged.emit(self.task_id, "完成")
            self.resultReady.emit(self.task_id, out)
            self.progress_label.setText(f"完成：{out}")
        else:
            self.statusChanged.emit(self.task_id, "空闲")
            self.progress_label.setText("已停在选优点（候选已生成）")

    def _on_failed(self, err: str):
        self.progress.hide()
        self.btn_start.setEnabled(True)
        self.statusChanged.emit(self.task_id, "失败")
        QMessageBox.critical(self, "配乐失败", err)
```

- [ ] **Step 4: 跑确认通过**

Run: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/test_ui/test_soundtrack_window_smoke.py -q`
Expected: **1 passed**

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/windows/soundtrack_task_window.py tests/test_ui/test_soundtrack_window_smoke.py
git commit -m "feat(ui): SoundtrackTaskWindow 单集配乐任务窗骨架"
```

---

## Task 6：main_window 接线（FUNCS + try-import 注册）

**Files:**
- Modify: `drama_shot_master/ui/main_window.py`
- Test: `tests/test_ui/test_main_window_soundtrack_smoke.py`

**逻辑**：FUNCS 加 `("配乐","soundtrack")`；panels 列表用 `_try_make_soundtrack_panel()`（try-import 降级，agent/面板缺失则返回占位空面板并打日志）；加 `_open_soundtrack_window`/`_persist_soundtrack` 回调 + 窗口状态同步。offscreen 冒烟：主窗口能构造 + 含"配乐"tab。

- [ ] **Step 1: 写 offscreen 冒烟测试**

`tests/test_ui/test_main_window_soundtrack_smoke.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.main_window import MainWindow, FUNCS


def test_main_window_has_soundtrack_tab():
    app = QApplication.instance() or QApplication([])
    keys = [key for _label, key in FUNCS]
    assert "soundtrack" in keys
    w = MainWindow()
    w.show(); app.processEvents()
    # panels 数与 FUNCS 等长（配乐 tab 已注册，或降级占位）
    assert len(w.panels) == len(FUNCS)
```

- [ ] **Step 2: 跑确认失败**

Run: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/test_ui/test_main_window_soundtrack_smoke.py -q`
Expected: FAIL（"soundtrack" not in keys）

- [ ] **Step 3: 改 main_window.py**

(a) `FUNCS` 末尾加一项：
```python
FUNCS = [("反推", "inference"), ("拆图", "split"),
         ("拼图", "combine"), ("去白边", "trim"),
         ("视频生成", "video_gen"), ("配乐", "soundtrack")]
```
(b) 在 `_build_ui` 的 `self.panels = [...]` 列表末尾追加：
```python
            self._try_make_soundtrack_panel(),
```
(c) 在 MainWindow 加方法（try-import 降级；soundtrack 任务窗实例字典）：
```python
    def _try_make_soundtrack_panel(self):
        """try-import 注册配乐面板；agent/面板缺失则返回占位空面板，宿主照常启动。"""
        try:
            from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("配乐面板不可用，已跳过: %s", e)
            from PySide6.QtWidgets import QWidget
            return QWidget()        # 占位，保证 panels 与 FUNCS 等长、索引对齐
        self._soundtrack_windows = {}
        return SoundtrackPanel(
            self.state, self.cfg,
            open_window_cb=self._open_soundtrack_window,
            persist_cb=self._persist_soundtrack)

    def _persist_soundtrack(self):
        try:
            self.cfg.update_settings(soundtrack_tasks=self.cfg.soundtrack_tasks)
        except Exception:
            pass

    def _open_soundtrack_window(self, task: dict):
        from drama_shot_master.ui.windows.soundtrack_task_window import (
            SoundtrackTaskWindow)
        wins = getattr(self, "_soundtrack_windows", None)
        if wins is None:
            wins = self._soundtrack_windows = {}
        tid = task.get("id")
        existing = wins.get(tid)
        if existing is not None:
            existing.raise_(); existing.activateWindow(); return
        from pathlib import Path
        work_root = Path(
            getattr(self.cfg, "video_output_dir", "") or ".") / "soundtrack"
        win = SoundtrackTaskWindow(task, self.cfg, work_root=work_root)
        win.statusChanged.connect(self._on_soundtrack_status)
        win.resultReady.connect(self._on_soundtrack_result)
        wins[tid] = win
        win.show()

    def _soundtrack_panel(self):
        idx = next((i for i, (_l, k) in enumerate(FUNCS) if k == "soundtrack"), -1)
        return self.panels[idx] if idx >= 0 else None

    def _on_soundtrack_status(self, task_id: str, status: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["status"] = status
        p = self._soundtrack_panel()
        if hasattr(p, "refresh"):
            p.refresh()

    def _on_soundtrack_result(self, task_id: str, output: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["output"] = output
        self._persist_soundtrack()
        p = self._soundtrack_panel()
        if hasattr(p, "refresh"):
            p.refresh()
```

注意：`_try_make_soundtrack_panel` 返回占位 `QWidget()` 时，它没有 `validityChanged`/`statusMessage` 信号——`_wire()` 里若对所有 panel 连这些信号会 AttributeError。**实现时检查 `_wire()`**：对 panel 连接信号处加 `hasattr` 守卫，或仅对 `isinstance(p, BasePanel)` 的 panel 连接。改 `_wire()` 的 panel 循环为：
```python
        for p in self.panels:
            if hasattr(p, "validityChanged"):
                p.validityChanged.connect(self._refresh_validity)
            if hasattr(p, "statusMessage"):
                p.statusMessage.connect(self.status.setText)
```

- [ ] **Step 4: 跑确认通过 + UI 全量冒烟**

Run: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/test_ui/ -q`
Expected: 全部通过（panel/window/main_window 三个冒烟）

- [ ] **Step 5: 可拆性验证（手动确认描述）**

确认拆除路径成立（不实际删，只核对）：删 `sound_track_agent/` 后，`_try_make_soundtrack_panel` 的 import 抛错 → 占位面板 → 主窗口仍启动、其余 tab 正常。在测试中模拟：
```python
# 追加到 test_main_window_soundtrack_smoke.py
def test_soundtrack_degrades_when_agent_import_fails(monkeypatch):
    import builtins, importlib
    real_import = builtins.__import__
    def fake_import(name, *a, **k):
        if name.startswith("drama_shot_master.ui.panels.soundtrack_panel"):
            raise ImportError("simulated missing")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    from drama_shot_master.ui import main_window as mw
    importlib.reload(mw)
    app = QApplication.instance() or QApplication([])
    w = mw.MainWindow(); w.show(); app.processEvents()
    assert len(w.panels) == len(mw.FUNCS)   # 占位面板补位，不崩
```
（若 reload 在测试环境不稳定，此步可改为人工核对 try-except 逻辑，并在报告中说明。）

- [ ] **Step 6: 全量回归 + Commit**

Run: `/usr/bin/python3 -m pytest tests/test_sound_track_agent/ -q` （67 passed）
Run: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/test_ui/ tests/test_config.py -q`

```bash
git add drama_shot_master/ui/main_window.py tests/test_ui/test_main_window_soundtrack_smoke.py
git commit -m "feat(ui): main_window 注册配乐 tab（try-import 降级，可拆）"
```

---

## 第二期预告（不在本 Plan）

在 SoundtrackTaskWindow 内追加：
- **试听选优区**：每段 2-4 候选，QMediaPlayer 内嵌播放 + 波形；选定写 `SegmentScore.chosen_candidate` 后 `advance(stop_after="mix")`。
- **卡点编辑区**：可视化 `session.accent_points`，增删/微调时间戳。
- facade 可加 `set_chosen(session, seg_index, cand_index)` 辅助 + cancel_check 贯穿。
- 端到端冒烟（真实成片 + ACE-Step）后回写实测笔记。
