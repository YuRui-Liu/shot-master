# 一键提示词反推优化（Prompt Refine）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 视频面板加「✨ 优化提示词」按钮：把 global + 所有段（image 附图 / text 仅文本）交给当前 vision provider（注入 LTX 2.3 反 PPT meta-prompt，要求 JSON 输出），弹窗逐行 before/after 让用户勾选替换。

**Architecture:** 新增可编辑 meta-prompt 资源文件 + Qt-free 的 `prompt_refiner.py`（构造请求/解析响应/读 meta 文件，可单测）+ `refine_review_dialog.py`（逐行勾选弹窗）+ `video_panel.py` 编排（按钮→worker→弹窗→回写 model）。

**Tech Stack:** Python stdlib（json、dataclasses、pathlib）；PySide6（QDialog、QScrollArea、QCheckBox）；复用 `providers.factory` + `ui.worker.FunctionWorker`；pytest 单测纯函数。

**Spec:** [docs/superpowers/specs/2026-05-25-prompt-refine-design.md](../specs/2026-05-25-prompt-refine-design.md)

---

## File Structure

新增：
- `templates/ltx_refine_meta_prompt.md` — 反 PPT + 导演台优化的 meta-prompt，强制 JSON 输出
- `drama_shot_master/core/prompt_refiner.py` — `RefineRequest` / `RefineResult` / `RefineParseError` / `build_refine_request` / `parse_refine_response` / `load_refine_meta_prompt`
- `drama_shot_master/ui/widgets/refine_review_dialog.py` — `RefineRow` / `RefineReviewDialog`
- `tests/test_core/test_prompt_refiner.py`

修改：
- `drama_shot_master/ui/panels/video_panel.py` — 按钮 + `_on_refine` + `_on_refine_done`

---

## Task 1: meta-prompt 资源文件

**Files:**
- Create: `templates/ltx_refine_meta_prompt.md`

无单测（内容文件）；验收 = 文件存在、非空、含关键标记。

- [ ] **Step 1.1: 写 meta-prompt 文件**

Create `templates/ltx_refine_meta_prompt.md` with EXACTLY this content:

````markdown
# LTX 2.3 Prompt Refiner · 导演台工作流专用

你是 LTX 2.3 视频生成的提示词工程师。用户给你**一组已有的 prompt + 参考图**（来自一个分镜导演台时间轴），你的任务是**精炼它们**，让它们更精确、更适合 LTX 2.3 出片，并且**坚决避免生成 PPT 式（画面像幻灯片切换 / 背景冻结）的视频**。

## 输入格式

用户消息会给你：
- `GLOBAL PROMPT (current)`：全片统一风格/角色描述（可能为空）
- `Frame rate`：帧率
- `SEGMENTS`：每段一行，形如 `[seg N] type=image|text, has_image=yes|no, duration=X.XXs, current_local="..."`，image 段会标 `attached_image=#k`
- 标了 `attached_image=#k` 的段，对应**按顺序附上的第 k+1 张图**（k 从 0 起）

## 六元素框架（每条 prompt 必含，织进单段流式现在时英文）

1. SHOT — 景别/视角（wide establishing / medium / close-up / OTS / overhead / static）
2. SCENE — 光影、色调、材质、氛围
3. ACTION — 现在时动作链
4. CHARACTER — 年龄/外观/服装/特征
5. CAMERA MOVEMENT — 明确镜头动词（slow dolly in / handheld tracking / pans right / tilts up / pulls back）
6. AUDIO — 环境音 + 对白 + 语气

## ★ 反 PPT 铁律（导演台工作流的头号陷阱，每条 prompt 必须自检）

LTX 2.3 + 漫画/cel-shaded 风格极易输出"幻灯片切换"。每条 prompt **必含三件套**：
1. **背景元素显式运动** —— 配角/人群/烟尘/树叶/光斑/旗帜都写持续运动动词（"the crowd continues shuffling restlessly throughout the shot"）
2. **时间维度副词** —— throughout / continuously / never stops / gradually / mid-motion，告诉模型"运动持续整段"
3. **反 PPT 兜底句** —— 镜头描述末尾加一句 "Nothing in this frame is still; live continuous motion across all elements"
- camera "static/locked" 只表示镜头不动，必须拆写 "Camera holds locked still; subjects within frame continue motion"
- 反 PPT 动词库：shuffle / lurch / sway / twitch / drift / curl / ripple / flicker / drag / claw

## 九法则

1. 极致具体（不写 nice/cool/beautiful，改 worn leather / oxidized brass）
2. 精确空间（foreground left / mid-ground center / distant right，不写 somewhere）
3. 刻画材质（rough linen / weathered wood / glossy lacquer）
4. 动词驱动动态
5. 拒绝静态照片式描述（不要 "A photo of..."，要 "The camera opens on..."）
6. 竖屏 9:16 主体居中上下留白（16:9 用 horizontal cinematic widescreen）
7. 明确音频
8. 复杂镜头可写，只要内部逻辑一致
9. ★ 反 PPT（见上）

## 七禁忌（违反就重写）

1. 内心情绪标签（sad/angry）→ 改物理外显（eyes lower, voice cracks）
2. 可读文字/logo（sign reading "OPEN"）
3. 数字规格（exactly 3 birds at 45°）→ 自然语言
4. 互斥逻辑（still lake + crashing waves）
5. 过载场景（>3 主角 + >3 并行动作）
6. 模糊空间（somewhere/around/near）
7. 抽象修饰（beautiful/amazing/cool/dynamic）

## 长度准则（与时长成正比）

- 1-2s：50-80 词；4-6s：80-130 词；8-10s：130-200 词

## 模式区分

- **image 段（has_image=yes）→ I2V**：不要重述参考图里已可见的静态元素；重点写"从静到动"的过渡（角色怎么动、镜头怎么动、背景细节怎么变）；角色说话必含 "mouth moves naturally as the character speaks"，绝不写具体嘴型
- **text 段（has_image=no）→ T2V**：六元素全配，从零生成

## 导演台运行参数意识

精炼时心里清楚：导演台全局 guide_strength 通常 0.4-0.5、per-seg 0.6-0.75；guide_strength 偏高会"贴死"参考图导致 PPT 化，所以 prompt 必须自带充足的持续运动描述来对冲。

## 输出契约（极其重要）

只输出**一个 JSON 对象**，不要任何 markdown 围栏、不要任何解释文字、不要中文。结构：

```
{
  "global_prompt": "refined global style/character description in English",
  "segments": [
    {"index": 0, "local_prompt": "refined English prompt for seg 0"},
    {"index": 1, "local_prompt": "refined English prompt for seg 1"}
  ]
}
```

- `index` = 输入里 `[seg N]` 的 N
- 每段都要给精炼后的 `local_prompt`（英文、单段流式现在时、含六元素、过了反 PPT 自检）
- `global_prompt` 给精炼后的全局风格串；若输入 global 为空且无从精炼，可省略该字段
- 不要新增/删除段，不要改 index
````

- [ ] **Step 1.2: 验收文件存在且含关键标记**

Run:
```bash
test -s templates/ltx_refine_meta_prompt.md && grep -q "Nothing in this frame is still" templates/ltx_refine_meta_prompt.md && grep -q '"global_prompt"' templates/ltx_refine_meta_prompt.md && grep -q "导演台" templates/ltx_refine_meta_prompt.md && echo "OK"
```
Expected: `OK`。

- [ ] **Step 1.3: 提交**

```bash
git add templates/ltx_refine_meta_prompt.md
git commit -m "feat(refine): add LTX 2.3 anti-PPT meta-prompt resource

Editable system prompt for prompt refinement: six-element framework,
nine rules with the anti-PPT three-piece-set front and center, seven
taboos, I2V/T2V mode split, director-console guide_strength awareness,
and a strict JSON-only output contract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 1)

- This file IS the knowledge core. User explicitly required: optimize for the 导演台 (director console) workflow and avoid PPT-like videos. The anti-PPT three-piece-set (background motion / temporal adverbs / "Nothing is still" fallback) is the headline requirement.
- Working dir: `/mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master`, branch `feat/video-panel`.
- Do NOT touch the unrelated uncommitted `runninghub.py` / `test_ltx_task_builder.py`.

---

## Task 2: prompt_refiner.py（TDD）

**Files:**
- Create: `drama_shot_master/core/prompt_refiner.py`
- Create: `tests/test_core/test_prompt_refiner.py`

- [ ] **Step 2.1: 写失败测试**

Create `tests/test_core/test_prompt_refiner.py`:

```python
"""Tests for drama_shot_master.core.prompt_refiner."""
from __future__ import annotations

from pathlib import Path

import pytest

from drama_shot_master.core.prompt_refiner import (
    build_refine_request, parse_refine_response, RefineParseError,
)
from drama_shot_master.core.video_timeline_model import TimelineModel


def _model_2img_1text() -> TimelineModel:
    m = TimelineModel(global_prompt="cinematic noir style")
    m.add_image_segment(Path("/fake/a.png"), length_frames=36, local_prompt="a")
    m.add_image_segment(Path("/fake/b.png"), length_frames=24, local_prompt="b")
    m.add_text_segment(length_frames=12, local_prompt="t")
    return m


def test_build_request_collects_only_image_paths():
    req = build_refine_request(_model_2img_1text())
    assert req.images == [Path("/fake/a.png"), Path("/fake/b.png")]


def test_build_request_seg_ids_cover_all_in_order():
    m = _model_2img_1text()
    req = build_refine_request(m)
    assert req.seg_ids == [s.seg_id for s in m.segments]
    assert len(req.seg_ids) == 3


def test_build_request_message_has_global_and_all_segments():
    req = build_refine_request(_model_2img_1text())
    assert "cinematic noir style" in req.user_message
    assert "[seg 0]" in req.user_message
    assert "[seg 1]" in req.user_message
    assert "[seg 2]" in req.user_message
    # image segments annotate attached_image ordinal
    assert "attached_image=#0" in req.user_message
    assert "attached_image=#1" in req.user_message


def test_parse_valid_json_maps_indices_to_seg_ids():
    raw = ('{"global_prompt": "G", "segments": ['
           '{"index": 0, "local_prompt": "A"}, '
           '{"index": 1, "local_prompt": "B"}]}')
    res = parse_refine_response(raw, ["s0", "s1"])
    assert res.global_prompt == "G"
    assert res.segment_locals == [("s0", "A"), ("s1", "B")]
    assert res.warnings == []


def test_parse_strips_code_fence():
    raw = '```json\n{"global_prompt": "G", "segments": []}\n```'
    res = parse_refine_response(raw, ["s0"])
    assert res.global_prompt == "G"
    assert res.segment_locals == []


def test_parse_missing_global_is_none():
    raw = '{"segments": [{"index": 0, "local_prompt": "A"}]}'
    res = parse_refine_response(raw, ["s0"])
    assert res.global_prompt is None
    assert res.segment_locals == [("s0", "A")]


def test_parse_index_out_of_range_skipped_with_warning():
    raw = '{"segments": [{"index": 99, "local_prompt": "X"}]}'
    res = parse_refine_response(raw, ["s0"])
    assert res.segment_locals == []
    assert res.warnings  # non-empty


def test_parse_bad_json_raises():
    with pytest.raises(RefineParseError):
        parse_refine_response("not json at all", ["s0"])


def test_parse_blank_global_treated_as_none():
    raw = '{"global_prompt": "   ", "segments": []}'
    res = parse_refine_response(raw, [])
    assert res.global_prompt is None
```

- [ ] **Step 2.2: 运行测试，确认失败**

Run: `pytest tests/test_core/test_prompt_refiner.py -v`
Expected: ImportError（模块不存在）。

- [ ] **Step 2.3: 实现 prompt_refiner.py**

Create `drama_shot_master/core/prompt_refiner.py`:

```python
"""提示词反推优化：构造模型请求 + 解析 JSON 响应。

Qt-free，可单测。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from drama_shot_master.core.video_timeline_model import TimelineModel

REFINE_META_PROMPT_PATH = Path("templates/ltx_refine_meta_prompt.md")


class RefineParseError(Exception):
    """模型返回无法解析为预期 JSON。"""


@dataclass
class RefineRequest:
    images: list[Path]
    user_message: str
    seg_ids: list[str]


@dataclass
class RefineResult:
    global_prompt: Optional[str]
    segment_locals: list[tuple[str, str]]   # [(seg_id, refined_local)]
    warnings: list[str] = field(default_factory=list)


def load_refine_meta_prompt() -> str:
    """读 meta-prompt 文件全文。缺失 → FileNotFoundError。"""
    return REFINE_META_PROMPT_PATH.read_text(encoding="utf-8")


def build_refine_request(model: TimelineModel) -> RefineRequest:
    """收集 global + 所有段 → 模型输入。

    images 仅含 image 段的 image_path（按段序）；seg_ids 含全部段。
    """
    images: list[Path] = []
    seg_ids: list[str] = []
    lines: list[str] = [
        f"GLOBAL PROMPT (current): {model.global_prompt!r}",
        f"Frame rate: {model.frame_rate} fps",
        "SEGMENTS:",
    ]
    fr = max(model.frame_rate, 1)
    for i, seg in enumerate(model.segments):
        seg_ids.append(seg.seg_id)
        dur = seg.length_frames / fr
        has_img = seg.segment_type == "image" and seg.image_path is not None
        if has_img:
            note = f", attached_image=#{len(images)}"
            images.append(seg.image_path)
        else:
            note = ""
        lines.append(
            f"[seg {i}] type={seg.segment_type}, "
            f"has_image={'yes' if has_img else 'no'}, "
            f"duration={dur:.2f}s, current_local={seg.local_prompt!r}{note}"
        )
    return RefineRequest(images=images,
                         user_message="\n".join(lines),
                         seg_ids=seg_ids)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text.split("\n")
    if body and body[0].startswith("```"):
        body = body[1:]
    if body and body[-1].strip() == "```":
        body = body[:-1]
    return "\n".join(body).strip()


def parse_refine_response(raw: str, seg_ids: list[str]) -> RefineResult:
    """解析模型 JSON 输出，把 index 映射回 seg_id。失败 → RefineParseError。"""
    text = _strip_code_fence(raw)
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        raise RefineParseError(
            f"无法解析模型返回为 JSON：{raw[:300]}") from e
    if not isinstance(obj, dict):
        raise RefineParseError(f"模型返回不是 JSON 对象：{raw[:300]}")

    warnings: list[str] = []
    gp = obj.get("global_prompt")
    global_prompt = gp if isinstance(gp, str) and gp.strip() else None

    segment_locals: list[tuple[str, str]] = []
    seg_items = obj.get("segments")
    if isinstance(seg_items, list):
        for item in seg_items:
            if not isinstance(item, dict):
                warnings.append(f"跳过非对象 segment 项：{str(item)[:80]}")
                continue
            idx = item.get("index")
            local = item.get("local_prompt")
            if not isinstance(idx, int) or not isinstance(local, str):
                warnings.append(f"跳过格式错误 segment 项：{str(item)[:80]}")
                continue
            if idx < 0 or idx >= len(seg_ids):
                warnings.append(f"段 index={idx} 越界，跳过")
                continue
            segment_locals.append((seg_ids[idx], local))
    return RefineResult(global_prompt=global_prompt,
                        segment_locals=segment_locals, warnings=warnings)
```

- [ ] **Step 2.4: 运行测试，确认通过**

Run: `pytest tests/test_core/test_prompt_refiner.py -v`
Expected: 9/9 PASS。

- [ ] **Step 2.5: 全量回归**

Run: `pytest -q`
Expected: 之前基线 + 9 新测试，全 PASS。

- [ ] **Step 2.6: 提交**

```bash
git add drama_shot_master/core/prompt_refiner.py tests/test_core/test_prompt_refiner.py
git commit -m "feat(refine): add prompt_refiner request/response logic

Qt-free build_refine_request (collects global + segments, image-only
paths, attached_image ordinals) and parse_refine_response (code-fence
stripping, index→seg_id mapping, out-of-range/bad-JSON handling).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 2)

- `TimelineModel.add_image_segment(image_path, length_frames=24, local_prompt="")` and `add_text_segment(length_frames, local_prompt)` auto-assign `seg_id`. `build_refine_request` does NOT read image files — it only collects paths, so fake paths are fine in tests.
- The `attached_image=#k` ordinal lets the model correlate the k-th attached image with the right segment index (the meta-prompt explains this).
- Working dir `/mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master`, branch `feat/video-panel`. Don't touch runninghub.py / test_ltx_task_builder.py.

---

## Task 3: refine_review_dialog.py

**Files:**
- Create: `drama_shot_master/ui/widgets/refine_review_dialog.py`

PyQt 不自动化；验收 = 烟测导入。

- [ ] **Step 3.1: 实现 refine_review_dialog.py**

Create `drama_shot_master/ui/widgets/refine_review_dialog.py`:

```python
"""精炼结果逐行 review 弹窗：左原文右精炼，每行一个勾选框。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QCheckBox,
    QPushButton, QScrollArea, QWidget, QFrame,
)


@dataclass
class RefineRow:
    key: str         # "global" 或 seg_id
    label: str       # "全局" / "段 N（image）"
    original: str
    refined: str


class RefineReviewDialog(QDialog):
    """构造入参 rows: list[RefineRow]；exec 后用 accepted_keys() 读勾选。"""

    def __init__(self, rows: list[RefineRow], parent=None):
        super().__init__(parent)
        self.setWindowTitle("提示词优化 · 逐行确认")
        self.setMinimumSize(720, 480)
        self._checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        # 顶部说明 + 全选/全不选
        top = QHBoxLayout()
        top.addWidget(QLabel("勾选要替换的项（左=原文，右=精炼）："))
        top.addStretch(1)
        btn_all = QPushButton("全部应用")
        btn_none = QPushButton("全部取消")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        top.addWidget(btn_all); top.addWidget(btn_none)
        root.addLayout(top)

        # 滚动区
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); col = QVBoxLayout(inner)
        for r in rows:
            col.addWidget(self._build_row(r))
        col.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # 底部
        bottom = QHBoxLayout(); bottom.addStretch(1)
        ok = QPushButton("应用勾选"); cancel = QPushButton("取消")
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        bottom.addWidget(ok); bottom.addWidget(cancel)
        root.addLayout(bottom)

    def _build_row(self, r: RefineRow) -> QWidget:
        box = QFrame(); box.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(box)
        head = QHBoxLayout()
        cb = QCheckBox(r.label)
        # 精炼为空或与原文相同 → 默认不勾
        meaningful = bool(r.refined.strip()) and r.refined.strip() != r.original.strip()
        cb.setChecked(meaningful)
        cb.setEnabled(meaningful)
        self._checks[r.key] = cb
        head.addWidget(cb); head.addStretch(1)
        v.addLayout(head)
        cols = QHBoxLayout()
        left = QPlainTextEdit(r.original); left.setReadOnly(True)
        left.setMaximumHeight(90)
        right = QPlainTextEdit(r.refined); right.setReadOnly(True)
        right.setMaximumHeight(90)
        cols.addWidget(left); cols.addWidget(right)
        v.addLayout(cols)
        return box

    def _set_all(self, on: bool):
        for cb in self._checks.values():
            if cb.isEnabled():
                cb.setChecked(on)

    def accepted_keys(self) -> set[str]:
        return {k for k, cb in self._checks.items() if cb.isChecked()}
```

- [ ] **Step 3.2: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.widgets.refine_review_dialog import RefineReviewDialog, RefineRow; print('ok')"
```
Expected: `ok`（若 PySide6 不可用，回退 `python -c "import ast; ast.parse(open('drama_shot_master/ui/widgets/refine_review_dialog.py').read()); print('syntax ok')"`，如实报告）。

- [ ] **Step 3.3: 提交**

```bash
git add drama_shot_master/ui/widgets/refine_review_dialog.py
git commit -m "feat(refine): add per-row before/after review dialog

RefineReviewDialog shows global + each segment as a row with a checkbox,
read-only original vs refined columns, and 全部应用/全部取消 toggles.
Rows whose refinement is empty or identical default unchecked+disabled.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 3)

- Pure UI glue. `accepted_keys()` returns the set of checked keys ("global" or seg_id), read by the panel after `exec()` returns Accepted.
- Working dir / branch as above; don't touch runninghub.py / test_ltx_task_builder.py.

---

## Task 4: video_panel.py 集成

**Files:**
- Modify: `drama_shot_master/ui/panels/video_panel.py`

- [ ] **Step 4.1: 加 imports**

Edit `drama_shot_master/ui/panels/video_panel.py`. After the existing import block (after the line importing `FunctionWorker`), add:

```python
from PySide6.QtWidgets import QDialog
from drama_shot_master.providers import factory
from drama_shot_master.core.prompt_refiner import (
    build_refine_request, parse_refine_response, load_refine_meta_prompt,
    RefineParseError,
)
from drama_shot_master.ui.widgets.refine_review_dialog import (
    RefineReviewDialog, RefineRow,
)
```

(Note: `QDialog` may need merging into the existing `from PySide6.QtWidgets import (...)` block instead of a separate line — either is fine as long as it imports.)

- [ ] **Step 4.2: 加按钮到 toolbar**

Edit `drama_shot_master/ui/panels/video_panel.py`. Current toolbar block in `_build_ui`:

```python
        self.btn_add_text = QPushButton("+ Add Text")
        self.btn_add_audio = QPushButton("+ Add Audio")
        for b in (self.btn_import, self.btn_import_dir, self.btn_clear_pool):
            pool_toolbar.addWidget(b)
        pool_toolbar.addStretch(1)
        pool_toolbar.addWidget(self.btn_add_text)
        pool_toolbar.addWidget(self.btn_add_audio)
```

Change to (add a refine button after Add Audio):

```python
        self.btn_add_text = QPushButton("+ Add Text")
        self.btn_add_audio = QPushButton("+ Add Audio")
        self.btn_refine = QPushButton("✨ 优化提示词")
        for b in (self.btn_import, self.btn_import_dir, self.btn_clear_pool):
            pool_toolbar.addWidget(b)
        pool_toolbar.addStretch(1)
        pool_toolbar.addWidget(self.btn_add_text)
        pool_toolbar.addWidget(self.btn_add_audio)
        pool_toolbar.addWidget(self.btn_refine)
```

- [ ] **Step 4.3: wire 按钮 + 初始化 refine worker 字段**

Edit `drama_shot_master/ui/panels/video_panel.py`. In `__init__`, current:

```python
        self._worker: Optional[FunctionWorker] = None
        self._cancel_flag = {"v": False}
```

Change to:

```python
        self._worker: Optional[FunctionWorker] = None
        self._refine_worker: Optional[FunctionWorker] = None
        self._cancel_flag = {"v": False}
```

In `_wire`, after the toolbar connects (after `self.btn_add_audio.clicked.connect(self._on_add_audio)`), add:

```python
        self.btn_refine.clicked.connect(self._on_refine)
```

- [ ] **Step 4.4: 加 _on_refine + _on_refine_done 方法**

Edit `drama_shot_master/ui/panels/video_panel.py`. Insert these two methods right after `_on_add_audio` (end of the "slots: toolbar" section, before "# ---------- slots: image pool ----------"):

```python
    def _on_refine(self):
        if not self.model.segments:
            QMessageBox.information(self, "无内容", "时间轴为空，先添加分镜段")
            return
        try:
            provider = factory.build_provider(
                self.cfg, self.cfg.current_provider, self.cfg.current_model)
        except Exception as e:
            QMessageBox.critical(self, "Provider 错误", str(e))
            return
        try:
            system_prompt = load_refine_meta_prompt()
        except FileNotFoundError:
            QMessageBox.critical(
                self, "缺少 meta-prompt",
                "templates/ltx_refine_meta_prompt.md 不存在")
            return
        req = build_refine_request(self.model)

        def task():
            raw = provider.generate(req.images, system_prompt, req.user_message)
            return parse_refine_response(raw, req.seg_ids)

        self.video_status_bar.set_status("优化中…")
        self.btn_refine.setEnabled(False)
        self._refine_worker = FunctionWorker(task)
        self._refine_worker.finished_with_result.connect(self._on_refine_done)
        self._refine_worker.failed.connect(self._on_refine_failed)
        self._refine_worker.start()

    def _on_refine_failed(self, err_msg: str):
        self.btn_refine.setEnabled(True)
        self.video_status_bar.set_idle()
        QMessageBox.critical(self, "优化失败", err_msg)

    def _on_refine_done(self, result):
        self.btn_refine.setEnabled(True)
        self.video_status_bar.set_idle()
        rows: list[RefineRow] = []
        if result.global_prompt is not None:
            rows.append(RefineRow("global", "全局",
                                  self.model.global_prompt,
                                  result.global_prompt))
        for seg_id, refined in result.segment_locals:
            seg = next((s for s in self.model.segments
                        if s.seg_id == seg_id), None)
            if seg is None:
                continue
            idx = self.model.segments.index(seg)
            rows.append(RefineRow(
                seg_id, f"段 {idx}（{seg.segment_type}）",
                seg.local_prompt, refined))
        if result.warnings:
            self.statusMessage.emit("；".join(result.warnings))
        if not rows:
            QMessageBox.information(self, "无可替换项", "模型未返回有效的精炼结果")
            return
        dlg = RefineReviewDialog(rows, self)
        if dlg.exec() != QDialog.Accepted:
            return
        accepted = dlg.accepted_keys()
        if "global" in accepted and result.global_prompt is not None:
            self.model.global_prompt = result.global_prompt
        for seg_id, refined in result.segment_locals:
            if seg_id in accepted:
                self.model.update_segment(seg_id, local_prompt=refined)
        self.global_form.set_state(self.model)
        self.timeline.rebuild()
        self.statusMessage.emit(f"已应用 {len(accepted)} 项优化")
```

Note on `RefineParseError`: it's raised inside `task()` (worker thread) by `parse_refine_response`; `FunctionWorker` catches all exceptions and emits `failed` with the message, so it surfaces via `_on_refine_failed`. The import is kept for clarity/future use even though not referenced directly — if a linter complains about unused import, remove `RefineParseError` from the import line.

- [ ] **Step 4.5: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.panels.video_panel import VideoPanel; print('ok')"
```
Expected: `ok`（PySide6 不可用则回退 ast 语法检查，如实报告）。

- [ ] **Step 4.6: 全量回归**

Run: `pytest -q`
Expected: 与 Task 2 后基线一致（本任务无新测试，UI 不自动化）。

- [ ] **Step 4.7: 提交**

```bash
git add drama_shot_master/ui/panels/video_panel.py
git commit -m "feat(refine): wire 优化提示词 button into video panel

Collects global + all segments, runs the current vision provider with the
LTX 2.3 meta-prompt on a worker thread, then opens the per-row review
dialog and applies the user's checked refinements back to the model.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 4)

- Tasks 1-3 done: meta-prompt file exists, `prompt_refiner` + `refine_review_dialog` ready.
- `factory.build_provider(cfg, cfg.current_provider, cfg.current_model)` returns a `VisionProvider` whose `generate(images, system_prompt, user_supplement) -> str`. Mirrors `InferencePanel.execute`.
- `FunctionWorker(task)` runs `task()` on a QThread; emits `finished_with_result(object)` on success and `failed(str)` on any exception. Connect slots to GUI-thread methods (the panel is on the GUI thread), so dialog construction in `_on_refine_done` is safe.
- `video_status_bar` has `set_status(str)` and `set_idle()` (already used in this file).
- `self.model.update_segment(seg_id, local_prompt=...)` and `self.model.global_prompt` are the write paths (mirror `_on_segment_edited` / `_on_global_changed`).
- Don't touch runninghub.py / test_ltx_task_builder.py.

---

## Task 5: 手测清单（end-of-feature）

**Files:** 无代码变更。

- [ ] **Step 5.1: 把手测清单交回用户**（spec §7.2）

1. 视频面板放 2-3 张图成段 + 1 个 text 段，各填粗糙 local，global 填一句。
2. 点「✨ 优化提示词」→ 状态栏"优化中…"，按钮禁用 → 弹窗出现，global + 每段一行 before/after。
3. 勾部分行 → 「应用勾选」→ 只有勾中的被替换（在 VideoGlobalForm 的 global / SegmentEditor 的 local 里核对）。
4. 「全部应用」「全部取消」正确切换所有可用勾选框（空/相同精炼的行保持禁用不勾）。
5. 取消弹窗 → model 不变，按钮恢复可用。
6. 断网或填错 API → 弹"优化失败"，按钮恢复，不崩。
7. 删 `templates/ltx_refine_meta_prompt.md` 再点 → 弹"缺少 meta-prompt"；改该文件内容重跑 → 行为随之变（验证可编辑生效）。
8. 看精炼出的英文 prompt 是否含反 PPT 元素（throughout/continues/Nothing is still 等）—— 验证 meta-prompt 的反 PPT 导向生效。

报告：全过 DONE；任一异常 DONE_WITH_CONCERNS + 具体步。

---

## Self-Review 记录

- **Spec coverage:**
  - §3 架构 4 单元 → Task 1（meta）+ Task 2（refiner）+ Task 3（dialog）+ Task 4（panel）
  - §4.1 meta-prompt 要点（六元素/九法则/反PPT/七禁忌/JSON 契约/导演台） → Task 1.1（用户额外强调的反 PPT + 导演台已作为硬性内容写入）
  - §4.2 RefineRequest/Result/Error + build/parse/load → Task 2.3
  - §4.3 RefineRow + RefineReviewDialog + 全选/全不选 + 空/相同行禁用 → Task 3.1
  - §4.4 面板 _on_refine/_on_refine_done + 按钮 → Task 4.2-4.4
  - §5 数据流 → Task 4 合成
  - §6 错误处理（空/provider/generate/JSON/段数/取消/缺meta） → Task 4.4 + Task 2.3 + Task 4.1
  - §7.1 单测（8 项 + blank_global 共 9） → Task 2.1
  - §7.2 手测 → Task 5.1
  - §8 依赖 → 零新增 pip
  - §9 YAGNI → 计划无弹窗编辑/历史/改时长/流式

- **Placeholder scan:** 无 TBD/“similar to”；每个代码 step 含完整代码或精确 before/after。

- **Type consistency:**
  - `build_refine_request(model) -> RefineRequest{images,user_message,seg_ids}`（Task2 定义）→ Task4 用 `req.images/req.user_message/req.seg_ids` 一致。
  - `parse_refine_response(raw, seg_ids) -> RefineResult{global_prompt,segment_locals,warnings}`（Task2）→ Task4 `result.global_prompt/segment_locals/warnings` 一致。
  - `RefineRow(key,label,original,refined)`（Task3）→ Task4 构造一致。
  - `RefineReviewDialog(rows, parent).accepted_keys()->set[str]`（Task3）→ Task4 用 `dlg.exec()`/`dlg.accepted_keys()` 一致。
  - `load_refine_meta_prompt()`（Task2）→ Task4 调用一致；读 `templates/ltx_refine_meta_prompt.md`（Task1 创建）路径一致。
  - JSON 契约（global_prompt + segments[{index,local_prompt}]）在 Task1 meta-prompt 与 Task2 parse 之间一致。
