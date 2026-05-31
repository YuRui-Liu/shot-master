# 成片合成 v2 · 全套 CV 智能转场 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Worktree:** 本计划在隔离 worktree `E:\Tools\ComfyUI\Assert\Projects\scripts\shot-drama-master-cv-v2`（分支 `feat/compose-cv-v2`）上实施，避免与主终端 main 冲突。所有路径相对该 worktree。

**Goal:** 给已有的 [智能转场]（=`compose`）面板加上「一键智能转场」CV 分析：PySceneDetect 定位镜头边界 + OpenCV 颜色直方图/SIFT 结构 + Farneback 光流，为每个**未锁定**切口算综合匹配分并映射转场效果/时长，回填到模型供审阅；「生成成片」按钮单独渲染（两步流程）。

**Architecture:** 纯逻辑 `core/transition_analyzer.py`（CV 评分+映射+编排，帧读取注入便于单测）跑在 `FunctionWorker(QThread)`；UI 在现有 `compose_panel`/`clip_strip`/`transition_inspector` 上做增量（分析/生成按钮拆分、切口状态徽章、评分拆解卡）。v1 数据模型已预留 `auto_transition/auto_duration/cv_scores/locked` 字段，零返工。

**Tech Stack:** Python 3.10+，PySide6，opencv-python(主包，含 SIFT)，scenedetect，numpy，ffmpeg(已随包/PATH)。pytest（`QT_QPA_PLATFORM=offscreen`；CV 单测用合成 numpy 帧，不依赖真视频）。

参考：设计规范 `docs/superpowers/specs/2026-05-31-compose-transition-design.md` §5(CV)/§8(打包)；UI mockup（已用户拍板）`docs/explorer/成片合成-v2-CV-layout.html`；v1 实现 `docs/superpowers/plans/2026-05-31-compose-transition-v1.md`。

> **交互（已确认）：** 两步——「✦ 一键智能转场」只跑 CV 填推荐（跳过 locked 切口），「⬇ 生成成片」单独渲染。CV 权重(0.4 画面/0.4 结构/0.2 运动)与高/低阈值用**固定默认**，inspector 只读展示评分（不暴露调参）。

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `drama_shot_master/core/transition_analyzer.py` | CV：边界帧抽取 + 评分(hist/feature/motion) + 映射 + analyze_composition 编排 |
| 修改 | `drama_shot_master/ui/panels/compose_panel.py` | 拆「分析」/「生成」两按钮；分析跑 worker 填模型；进度；刷新 |
| 修改 | `drama_shot_master/ui/widgets/compose/clip_strip.py` | 切口圆点状态化（AI/分析中/手动/锁定）+ 匹配分标签 |
| 修改 | `drama_shot_master/ui/widgets/compose/transition_inspector.py` | CV 评分拆解卡（画面色/结构/运动/综合+类别） |
| 修改 | `build/drama_shot_master.spec` | 移除 cv2 exclude + hidden-import + 关 UPX；scenedetect |
| 修改 | `requirements*.txt` / 依赖声明 | opencv-python>=4.5、scenedetect>=0.6.4,<0.7 |
| 新建 | `tests/test_core/test_transition_analyzer.py` | 合成帧评分/映射/编排单测 |
| 修改 | `tests/test_ui/test_compose_widgets.py` | 分析流程/状态/评分卡 UI 冒烟 |

---

## Task 1: transition_analyzer — 评分核（纯函数）

**Files:** Create `drama_shot_master/core/transition_analyzer.py`; Test `tests/test_core/test_transition_analyzer.py`

> 评分函数吃 numpy BGR 帧数组（注入），不读真视频 → 可纯单测。

- [ ] **Step 1: 失败测试**

```python
# tests/test_core/test_transition_analyzer.py
import numpy as np
import pytest
from drama_shot_master.core import transition_analyzer as ta

cv2 = pytest.importorskip("cv2")   # 没装 opencv 时跳过本文件


def _solid(color, h=64, w=64):
    img = np.zeros((h, w, 3), np.uint8); img[:] = color; return img


def test_hist_score_identical_high():
    a = _solid((30, 60, 120)); b = _solid((30, 60, 120))
    assert ta.hist_similarity(a, b) > 0.95


def test_hist_score_opposite_low():
    a = _solid((10, 10, 10)); b = _solid((240, 240, 240))
    assert ta.hist_similarity(a, b) < 0.5


def test_feature_score_in_range():
    rng = np.random.default_rng(0)
    a = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    s = ta.feature_similarity(a, a.copy())
    assert 0.0 <= s <= 1.0


def test_motion_discontinuity_in_range():
    a = _solid((50, 50, 50)); b = _solid((50, 50, 50))
    m, direction = ta.motion_estimate(a, b)
    assert 0.0 <= m <= 1.0
    assert direction in ("left", "right", "up", "down", "none")


def test_combine_score_weights():
    s = ta.combine_score(hist=1.0, feature=1.0, motion_disc=0.0)
    assert abs(s - 1.0) < 1e-6
    s2 = ta.combine_score(hist=0.0, feature=0.0, motion_disc=1.0)
    assert abs(s2 - 0.0) < 1e-6   # 0.4*0+0.4*0+0.2*(1-1)=0


def test_map_high_score_universal():
    eff, dur = ta.map_to_transition(0.85, "none")
    assert eff in ("dissolve", "fade")
    assert 0.3 <= dur <= 2.0


def test_map_mid_score_directional_by_motion():
    eff, dur = ta.map_to_transition(0.55, "left")
    assert eff == "smoothleft"


def test_map_low_score_creative():
    eff, dur = ta.map_to_transition(0.2, "none")
    assert eff in ("circleopen", "pixelize")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_core/test_transition_analyzer.py -q`
Expected: 若装了 opencv → ERROR ModuleNotFoundError(transition_analyzer)；未装 → skipped。

- [ ] **Step 3: 实现评分核**

```python
# drama_shot_master/core/transition_analyzer.py
"""CV 智能转场分析：相邻片段衔接处视觉评分 + 转场映射。Qt-free。

评分函数吃 numpy BGR 帧（cv2 读），便于注入单测。帧读取见 analyze_composition。
权重/阈值固定（spec §5）：综合 = 0.4*hist + 0.4*feature + 0.2*(1-motion_disc)。
"""
from __future__ import annotations

import numpy as np

# 固定权重与阈值（spec §5）
_W_HIST, _W_FEAT, _W_MOTION = 0.4, 0.4, 0.2
_HIGH, _LOW = 0.7, 0.4
_DUR_UNIVERSAL, _DUR_DIRECTIONAL, _DUR_CREATIVE = 0.5, 0.6, 0.7
_DIR_TRANSITION = {"left": "smoothleft", "right": "smoothright",
                   "up": "smoothup", "down": "smoothdown"}


def hist_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """HSV 颜色直方图相关性，0..1。"""
    import cv2
    ha = cv2.calcHist([cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [0, 1], None, [50, 60], [0, 180, 0, 256])
    hb = cv2.calcHist([cv2.cvtColor(b, cv2.COLOR_BGR2HSV)], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(ha, ha); cv2.normalize(hb, hb)
    c = cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL)
    return float(max(0.0, min(1.0, c)))


def feature_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """SIFT + BFMatcher + Lowe ratio 的匹配率，0..1。取不到特征 → 0.5 中性。"""
    import cv2
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create()
    ka, da = sift.detectAndCompute(ga, None)
    kb, db = sift.detectAndCompute(gb, None)
    if da is None or db is None or len(ka) < 2 or len(kb) < 2:
        return 0.5
    bf = cv2.BFMatcher()
    try:
        matches = bf.knnMatch(da, db, k=2)
    except cv2.error:
        return 0.5
    good = 0
    pairs = 0
    for m_n in matches:
        if len(m_n) < 2:
            continue
        pairs += 1
        m, n = m_n
        if m.distance < 0.75 * n.distance:
            good += 1
    if pairs == 0:
        return 0.5
    return float(max(0.0, min(1.0, good / pairs)))


def motion_estimate(a: np.ndarray, b: np.ndarray) -> tuple[float, str]:
    """Farneback 光流估运动不连续度(0..1)与主方向。跨片段是伪运动场，弱用。"""
    import cv2
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    try:
        flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    except cv2.error:
        return 0.5, "none"
    fx, fy = flow[..., 0].mean(), flow[..., 1].mean()
    mag = float(np.sqrt(fx * fx + fy * fy))
    disc = float(max(0.0, min(1.0, mag / 10.0)))   # 经验归一
    if mag < 0.5:
        return disc, "none"
    if abs(fx) >= abs(fy):
        return disc, ("right" if fx > 0 else "left")
    return disc, ("down" if fy > 0 else "up")


def combine_score(hist: float, feature: float, motion_disc: float) -> float:
    return float(_W_HIST * hist + _W_FEAT * feature + _W_MOTION * (1.0 - motion_disc))


def map_to_transition(score: float, direction: str) -> tuple[str, float]:
    """综合分 + 运动方向 → (xfade 效果名, 时长)。"""
    if score >= _HIGH:
        return "dissolve", _DUR_UNIVERSAL
    if score >= _LOW:
        return _DIR_TRANSITION.get(direction, "dissolve"), _DUR_DIRECTIONAL
    return "circleopen", _DUR_CREATIVE
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_core/test_transition_analyzer.py -q`
Expected: 全部 PASS（装了 opencv）。

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/transition_analyzer.py tests/test_core/test_transition_analyzer.py
git commit -m "feat(compose-cv): transition_analyzer 评分核(hist/SIFT/光流)+映射"
```

---

## Task 2: 边界帧抽取 + analyze_composition 编排

**Files:** Modify `drama_shot_master/core/transition_analyzer.py`; Test 追加。

> 帧抽取注入：`frame_provider(path, t_sec, n) -> list[np.ndarray]`，真实现用 cv2.VideoCapture（带 PySceneDetect 定位末/首镜头、失败退化按时间取）。编排跳过 locked 切口、报进度、回填模型。

- [ ] **Step 1: 失败测试（编排用注入 provider/scorer，纯逻辑）**

```python
def test_analyze_fills_unlocked_skips_locked():
    from drama_shot_master.core.composition_model import ReelClip, CompositionModel
    clips = [
        ReelClip.new(path="/0.mp4", duration=8.0),
        ReelClip.new(path="/1.mp4", duration=8.0, locked=True,
                     user_transition="wipeleft", user_duration=0.6),
        ReelClip.new(path="/2.mp4", duration=8.0),
    ]
    comp = CompositionModel(clips=clips)
    prog = []
    # 注入：scorer 返回固定高分 → dissolve；frame_provider 不被真正用到（scorer 注入）
    ta.analyze_composition(
        comp,
        frame_provider=lambda path, t, n: [],
        score_fn=lambda prev, nxt: (0.85, {"hist": 0.8, "feature": 0.9, "motion": 0.0}, "none"),
        progress_cb=lambda i, total: prog.append((i, total)),
    )
    kept = comp.kept_clips()
    # cut0 (kept[0]→kept[1]) 未锁 → 填 auto；cut1 (kept[1] locked) → 不动
    assert kept[0].auto_transition == "dissolve"
    assert kept[0].cv_scores.get("score") == 0.85
    assert kept[1].user_transition == "wipeleft"   # locked 切口保持手动
    assert kept[1].auto_transition is None
    assert prog and prog[-1][1] == 2   # 2 个切口报进度
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_core/test_transition_analyzer.py::test_analyze_fills_unlocked_skips_locked -q`
Expected: FAIL（analyze_composition 未定义）。

- [ ] **Step 3: 实现编排 + 真实帧抽取**

在 `transition_analyzer.py` 追加：

```python
_MARGIN = 0.25   # 避开段内淡入淡出过渡帧的余量（秒）
_NFRAMES = 5     # 每侧取帧数（取中位抗噪）


def _read_frames_cv2(path, t_sec, n):
    """真实帧抽取：从 t_sec 起取 n 帧 BGR。失败 → []。"""
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t_sec * fps)))
        out = []
        for _ in range(n):
            ok, fr = cap.read()
            if not ok:
                break
            out.append(fr)
        return out
    finally:
        cap.release()


def _median_frame(frames):
    if not frames:
        return None
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def default_score_fn(prev_frames, next_frames):
    """对边界帧组取中位帧后算三维评分 → (score, scores_dict, direction)。"""
    pa = _median_frame(prev_frames)
    pb = _median_frame(next_frames)
    if pa is None or pb is None:
        return 0.5, {"hist": 0.5, "feature": 0.5, "motion": 0.5}, "none"
    h = hist_similarity(pa, pb)
    f = feature_similarity(pa, pb)
    md, direction = motion_estimate(pa, pb)
    s = combine_score(h, f, md)
    return s, {"hist": round(h, 3), "feature": round(f, 3),
               "motion": round(md, 3), "score": round(s, 3)}, direction


def analyze_composition(comp, frame_provider=None, score_fn=None, progress_cb=None,
                        clip_duration=None):
    """对每个未锁定切口跑 CV，回填 auto_transition/auto_duration/cv_scores。

    frame_provider(path, t_sec, n)->frames（默认 cv2 读）；score_fn(prev,next)->
    (score, scores, direction)（默认 default_score_fn）；progress_cb(done, total)。
    locked 切口跳过。clip_duration(path)->秒 用于取尾帧时刻（默认用 clip.duration）。
    """
    frame_provider = frame_provider or _read_frames_cv2
    score_fn = score_fn or default_score_fn
    kept = comp.kept_clips()
    cuts = list(range(len(kept) - 1))
    total = len(cuts)
    for done, i in enumerate(cuts, start=1):
        a, b = kept[i], kept[i + 1]
        if a.locked:
            if progress_cb:
                progress_cb(done, total)
            continue
        # 前段末帧组（留 margin 避开段内过渡帧）；后段首帧组（留 margin）
        a_dur = (clip_duration(a.path) if clip_duration else a.duration) or 0.0
        a_out = a.out_point if a.out_point is not None else a_dur
        prev_t = max(0.0, a_out - _MARGIN - _NFRAMES / 30.0)
        b_in = b.in_point or 0.0
        next_t = b_in + _MARGIN
        prev_frames = frame_provider(a.path, prev_t, _NFRAMES)
        next_frames = frame_provider(b.path, next_t, _NFRAMES)
        score, scores, direction = score_fn(prev_frames, next_frames)
        eff, dur = map_to_transition(score, direction)
        a.auto_transition = eff
        a.auto_duration = dur
        a.cv_scores = scores
        # 不动 user_*：effective = user ?? auto，未手动覆盖时即用 auto
        if progress_cb:
            progress_cb(done, total)
```

> **PySceneDetect（可选增强）：** `_read_frames_cv2` 可在取前段末帧前用 `scenedetect` 定位该片段最后一个镜头起点，把 `prev_t` 落到末镜头内而非整段末尾，避免段内转场污染。失败/未装时退化为上面的按时间取帧。本步先实现时间法；PySceneDetect 增强放 Task 2b（可选，不阻断 v2）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_core/test_transition_analyzer.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/transition_analyzer.py tests/test_core/test_transition_analyzer.py
git commit -m "feat(compose-cv): 边界帧抽取 + analyze_composition 编排(跳过locked/进度/回填)"
```

---

## Task 2b（可选）: PySceneDetect 末镜头定位增强

**Files:** Modify `transition_analyzer.py`

- [ ] **Step 1:** 在 `_read_frames_cv2` 前加 `_last_shot_start(path) -> float|None`，用 `scenedetect.detect(path, ContentDetector())` 取最后一个 scene 的起始秒；异常/空 → None。analyze 取前段末帧时若有值且在片段内则用它收窄 `prev_t`。
- [ ] **Step 2:** 测试：monkeypatch `scenedetect.detect` 返回桩 scene 列表，断言 `_last_shot_start` 解析正确；异常 → None。
- [ ] **Step 3:** 提交 `feat(compose-cv): PySceneDetect 末镜头定位增强(失败退化时间法)`。

> 若 scenedetect 集成成本过高，可跳过本任务——时间法已满足；记录为后续增强。

---

## Task 3: ComposePanel — 拆「分析」/「生成」两步 + 分析 worker

**Files:** Modify `drama_shot_master/ui/panels/compose_panel.py`; Test 追加。

- [ ] **Step 1: 失败测试**

```python
def test_compose_panel_has_analyze_and_render(tmp_path):
    _app()
    from drama_shot_master.config import load_config
    from drama_shot_master.ui.panels.compose_panel import ComposePanel
    p = ComposePanel(load_config(), payload={"clips": [
        {"clip_id": "a", "path": "/0.mp4", "duration": 8.0},
        {"clip_id": "b", "path": "/1.mp4", "duration": 8.0},
    ]})
    assert hasattr(p, "analyzeRequested")
    # 注入假分析器：直接给第一个切口填 auto
    called = {}
    def fake_analyze(comp, progress_cb=None, **kw):
        comp.kept_clips()[0].auto_transition = "dissolve"
        comp.kept_clips()[0].cv_scores = {"score": 0.8}
        if progress_cb: progress_cb(1, 1)
        called["ok"] = True
    p._run_analyze(analyzer=fake_analyze)   # 同步入口便于测试（真实走 worker）
    assert called.get("ok")
    assert p.model().kept_clips()[0].auto_transition == "dissolve"
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py::test_compose_panel_has_analyze_and_render -q`
Expected: FAIL。

- [ ] **Step 3: 改 compose_panel**

工具栏拆按钮：
```python
self._b_analyze = QPushButton("✦ 一键智能转场"); self._b_analyze.setObjectName("ComposePrimary")
self._b_analyze.clicked.connect(self._on_analyze)
self._b_render = QPushButton("⬇ 生成成片"); self._b_render.setObjectName("ComposeRenderBtn")
self._b_render.clicked.connect(self._on_render)
for b in (b_listdir, b_add, self._b_analyze, self._b_render):
    tb.addWidget(b)
```
新增信号 `analyzeRequested = Signal()`。分析逻辑（worker + 同步入口便于测试）：
```python
def _on_analyze(self):
    from drama_shot_master.core import transition_analyzer as ta
    if len(self._model.kept_clips()) < 2:
        self.statusMessage.emit("至少 2 个保留片段才能分析转场"); return
    self._progress.setVisible(True); self._progress.setRange(0, 0)
    self._status.setText("CV 分析中…"); self._b_analyze.setEnabled(False)
    comp = self._model            # 直接在模型上回填（analyze 跳过 locked）
    def job():
        ta.analyze_composition(comp, progress_cb=None)
        return True
    from drama_shot_master.ui.worker import FunctionWorker
    self._aworker = FunctionWorker(job)
    self._aworker.finished_with_result.connect(self._on_analyze_done)
    self._aworker.failed.connect(self._on_analyze_failed)
    self._aworker.start(); self.analyzeRequested.emit()

def _run_analyze(self, analyzer=None):
    """同步分析入口（测试/无线程场景）。"""
    from drama_shot_master.core import transition_analyzer as ta
    (analyzer or ta.analyze_composition)(self._model, progress_cb=None)
    self._strip.refresh(); self.dirty.emit()

def _on_analyze_done(self, _ok):
    self._progress.setVisible(False); self._b_analyze.setEnabled(True)
    self._status.setText("CV 分析完成"); self._strip.refresh(); self.dirty.emit()
    self.statusMessage.emit("智能转场分析完成，请审阅各切口推荐")

def _on_analyze_failed(self, err):
    self._progress.setVisible(False); self._b_analyze.setEnabled(True)
    self._status.setText("分析失败"); self.statusMessage.emit(err)
```

- [ ] **Step 4: QSS** — `theme.qss.tpl` 加 `#ComposeRenderBtn`（次级描边胶囊，对照 mockup `.btn-render`）：
```css
#ComposeRenderBtn {{ color:#a0c8ff; border:1px solid #4a9eff66; border-radius:20px; padding:8px 16px; font-weight:600; background:rgba(74,158,255,0.08); }}
#ComposeRenderBtn:hover {{ background:rgba(74,158,255,0.16); }}
```

- [ ] **Step 5: 运行 + 提交**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_compose_widgets.py -q`（全过）
```bash
git add drama_shot_master/ui/panels/compose_panel.py drama_shot_master/ui/styles/theme.qss.tpl tests/test_ui/test_compose_widgets.py
git commit -m "feat(compose-cv): 面板拆分析/生成两步 + 分析 worker"
```

---

## Task 4: ClipStrip — 切口状态徽章 + 匹配分

**Files:** Modify `drama_shot_master/ui/widgets/compose/clip_strip.py`; Test 追加。

- [ ] **Step 1: 失败测试**

```python
def test_connector_label_reflects_ai_locked_manual():
    _app()
    from drama_shot_master.core.composition_model import ReelClip, CompositionModel
    from drama_shot_master.ui.widgets.compose.clip_strip import ClipStrip
    c0 = ReelClip.new(path="/0.mp4", duration=8)
    c0.auto_transition = "dissolve"; c0.auto_duration = 0.5
    c0.cv_scores = {"score": 0.82}
    c1 = ReelClip.new(path="/1.mp4", duration=8)
    c1.user_transition = "wipeleft"; c1.locked = True
    c2 = ReelClip.new(path="/2.mp4", duration=8)
    m = CompositionModel(clips=[c0, c1, c2])
    s = ClipStrip(); s.set_model(m)
    st0 = s.connector_state(0)   # AI 推荐
    st1 = s.connector_state(1)   # 锁定（且手动）
    assert st0 == "ai"
    assert st1 == "locked"
```

- [ ] **Step 2: 运行确认失败** → `connector_state` 未定义。

- [ ] **Step 3: 实现** — `ClipStrip.connector_state(idx)` 返回 `"ai"|"manual"|"locked"|"plain"`：locked→"locked"；user_transition 有→"manual"；cv_scores 有 score→"ai"；否则 "plain"。`_Connector` 按状态设 objectName 属性 + 显示匹配分（cv_scores.score）/ 来源徽章文字；`_conn_label`/构造读取。state→样式用 QSS property（`#ComposeConnector[state="ai"]` 紫、`[state="locked"]` 橙等）。

- [ ] **Step 4: QSS** 加各 state 配色（对照 mockup：ai=紫、locked=橙、manual=灰、analyzing=脉冲可省略动画用静态紫）。

- [ ] **Step 5: 运行 + 提交** `feat(compose-cv): ClipStrip 切口状态徽章(AI/手动/锁定)+匹配分`

---

## Task 5: TransitionInspector — CV 评分拆解卡

**Files:** Modify `drama_shot_master/ui/widgets/compose/transition_inspector.py`; Test 追加。

- [ ] **Step 1: 失败测试**

```python
def test_inspector_shows_cv_scores():
    _app()
    from drama_shot_master.ui.widgets.compose.transition_inspector import TransitionInspector
    insp = TransitionInspector()
    insp.set_connector(index=0, effect="dissolve", duration=0.5, source="auto",
                       locked=False, cv_scores={"hist": 0.78, "feature": 0.88,
                                                "motion": 0.5, "score": 0.82})
    assert insp.has_scores() is True
    insp.set_connector(index=1, effect="fade", duration=0.5, source="user", locked=True)
    assert insp.has_scores() is False   # 无 cv_scores → 隐藏评分卡
```

- [ ] **Step 2: 运行确认失败** — `set_connector` 旧签名无 `cv_scores`。

- [ ] **Step 3: 实现** — `set_connector` 增可选 `cv_scores: dict|None=None`；新增只读评分卡（画面色/结构/运动三条进度条 + 综合分 + 命中类别文字：score≥0.7「高→万能」/≥0.4「中→方向」/否则「低→创意」）；`has_scores()` 返回是否有分；无分时隐藏卡。`ComposePanel._on_conn_selected` 传 `cv_scores=c.cv_scores`。

- [ ] **Step 4: 运行 + 提交** `feat(compose-cv): TransitionInspector CV 评分拆解卡(只读)`

---

## Task 6: 依赖 + cv2 打包（spec）

**Files:** Modify `build/drama_shot_master.spec`、依赖声明（`requirements.txt` 或等价）。

- [ ] **Step 1:** 依赖声明加 `opencv-python>=4.5`、`scenedetect>=0.6.4,<0.7`（numpy 已有）。本地 `pip install` 之，确认 `python -c "import cv2, scenedetect; print(cv2.__version__)"`。
- [ ] **Step 2:** `build/drama_shot_master.spec`：从 `excludes` 移除 `'cv2'`；`Analysis(..., hiddenimports=[..., 'cv2'])`；`scenedetect` 加 `--hidden-import platformdirs.windows`（在 hiddenimports 列表加 `'platformdirs.windows'`）；EXE/COLLECT 保持 onedir 且 `upx=False`（关 UPX 防 `Recursion is detected during loading of cv2`）。
- [ ] **Step 3:** 注释标注 Nuitka 路径（若用）需 `--include-package=cv2`。
- [ ] **Step 4:** `python -c "import ast; ast.parse(open('build/drama_shot_master.spec').read()); print('spec parses')"`。
- [ ] **Step 5:** 提交 `build(compose-cv): 引入 cv2/scenedetect(移除exclude/hidden-import/关UPX)`。

---

## Task 7: 集成冒烟 + 回归

**Files:** 无新增（验证）。

- [ ] **Step 1: 真 CV 冒烟**（本地有 opencv + ffmpeg）：生成 2-3 个差异明显的短 mp4，`analyze_composition` 跑真分析，断言每个未锁切口被填了 `auto_transition`/`cv_scores`，分值合理（同源高、异源低）。
```bash
python -c "
from drama_shot_master.core.composition_model import ReelClip, CompositionModel
from drama_shot_master.core import transition_analyzer as ta
m=CompositionModel(clips=[ReelClip.new('a.mp4',duration=3),ReelClip.new('b.mp4',duration=3)])
ta.analyze_composition(m)
print(m.kept_clips()[0].auto_transition, m.kept_clips()[0].cv_scores)
"
```
- [ ] **Step 2:** 分析→生成端到端：分析后 `transition_render.render` 出片成功（v1 渲染管线复用）。
- [ ] **Step 3:** 回归 `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_core/ tests/test_ui/test_compose_widgets.py tests/test_ui/test_nav_config.py -q`（全绿；不跑会卡的全量 test_ui）。
- [ ] **Step 4:** PowerShell 原生渲染 compose 面板，对照 `docs/explorer/成片合成-v2-CV-layout.html` 核对状态徽章/评分卡/双按钮。
- [ ] **Step 5:** 提交 `test(compose-cv): v2 集成冒烟 + 回归`。

---

## 自我审查

### Spec 覆盖（§5/§8）
| Spec 要点 | 覆盖任务 |
|---------|---------|
| PySceneDetect 边界 + 留 margin/中位帧 | Task 2 + 2b |
| 直方图/SIFT/光流 三维 + 0.4/0.4/0.2 综合 | Task 1 |
| 评分→效果映射(高万能/中方向/低创意) | Task 1 |
| 编排：跳过 locked、进度、回填 auto/cv_scores | Task 2 |
| 「一键智能转场」CV（不直接渲染）+ 进度 | Task 3 |
| 切口状态徽章 + 匹配分 | Task 4 |
| inspector 评分拆解（只读） | Task 5 |
| cv2/scenedetect 打包(移除exclude/hidden-import/关UPX/Nuitka) | Task 6 |
| 两步流程（分析 vs 生成） | Task 3（用户确认） |

### 类型/方法一致性
- `transition_analyzer.{hist_similarity,feature_similarity,motion_estimate,combine_score,map_to_transition,default_score_fn,analyze_composition}` — Task 1/2 定义，Task 3/7 调用 ✓
- `analyze_composition(comp, frame_provider, score_fn, progress_cb, clip_duration)` 注入点与测试一致 ✓
- 回填字段 `auto_transition/auto_duration/cv_scores` — v1 模型已有，`effective_*` 自动生效 ✓
- `ClipStrip.connector_state(idx)` — Task 4 定义，inspector/panel 取用 ✓
- `TransitionInspector.set_connector(..., cv_scores=None)`/`has_scores()` — Task 5 定义，panel 传 ✓
- locked 切口：analyze 跳过 + inspector `锁定` + strip `locked` 态一致 ✓

### Placeholder 扫描：无 TBD/TODO；核心(Task1/2)含完整代码与命令；UI(Task3-5)给出关键代码片段+信号契约+QSS+冒烟测试。Task 2b 明确标注可选、不阻断。
