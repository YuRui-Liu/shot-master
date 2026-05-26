# 去白边额外向内裁剪 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去白边自动裁之后，允许四边各自向内再裁 N 像素（默认 0），兜底去掉 bbox 去不掉的雾气近白边。

**Architecture:** `grid_ops` 加纯函数 `_inset_crop` + `trim_one`/`trim_batch` 追加 4 个 inset 参数（白边裁后调用）；`trim_panel` 加 4 个 spinbox 透传。默认全 0 → 现有行为不变。

**Tech Stack:** Python + PIL（已用）；PySide6；pytest。

**Spec:** [docs/superpowers/specs/2026-05-26-trim-inward-crop-design.md](../specs/2026-05-26-trim-inward-crop-design.md)

---

## File Structure

修改：
- `drama_shot_master/grid_ops.py` — `_inset_crop` + `trim_one`/`trim_batch` 加 inset 参数
- `drama_shot_master/ui/panels/trim_panel.py` — 4 个 spinbox + execute 透传
- `tests/test_grid_ops.py` — `_inset_crop` 单测

---

## Task 1: `_inset_crop` + trim_one/trim_batch（TDD）

**Files:**
- Modify: `drama_shot_master/grid_ops.py`
- Test: `tests/test_grid_ops.py`

- [ ] **Step 1.1: 写失败测试**

Append to `tests/test_grid_ops.py`:

```python
def test_inset_crop_basic():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (100, 100), (10, 20, 30))
    out = _inset_crop(img, top=5, right=10, bottom=15, left=20)
    assert out.size == (70, 80)   # w=100-20-10, h=100-5-15


def test_inset_crop_zero_returns_same_object():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (50, 50), (0, 0, 0))
    assert _inset_crop(img) is img
    assert _inset_crop(img, 0, 0, 0, 0) is img


def test_inset_crop_overlarge_clamps_to_min_1px():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    out = _inset_crop(img, left=200, right=200, top=200, bottom=200)
    w, h = out.size
    assert w >= 1 and h >= 1   # 不空、不崩


def test_inset_crop_negative_treated_as_zero():
    from PIL import Image
    from drama_shot_master.grid_ops import _inset_crop
    img = Image.new("RGB", (40, 40), (0, 0, 0))
    out = _inset_crop(img, top=-5, right=-5, bottom=0, left=0)
    assert out is img   # 负值钳到 0 → 全 0 → 原样返回
```

- [ ] **Step 1.2: 运行测试，确认失败**

Run: `pytest tests/test_grid_ops.py -v -k inset_crop` (or `python3.10 -m pytest`)
Expected: ImportError / AttributeError（`_inset_crop` 不存在）。

- [ ] **Step 1.3: 实现 `_inset_crop`**

Edit `drama_shot_master/grid_ops.py`. Add this function right BEFORE `def trim_one`:

```python
def _inset_crop(img: Image.Image, top: int = 0, right: int = 0,
                bottom: int = 0, left: int = 0) -> Image.Image:
    """四边各向内裁 N 像素；负值钳到 0；超量保底至少 1×1；全 0 时原样返回。"""
    top = max(0, top); right = max(0, right)
    bottom = max(0, bottom); left = max(0, left)
    if top == right == bottom == left == 0:
        return img
    w, h = img.size
    x0 = min(left, w - 1)
    y0 = min(top, h - 1)
    x1 = max(w - right, x0 + 1)
    y1 = max(h - bottom, y0 + 1)
    return img.crop((x0, y0, x1, y1))
```

- [ ] **Step 1.4: 给 trim_one 加 inset 参数 + 调用**

Edit `drama_shot_master/grid_ops.py`. Current `trim_one`:
```python
def trim_one(src_path: Path, out_path: Path,
             threshold: int = 240, max_iter: int = 5,
             output_format: str = "PNG") -> Path:
    img = Image.open(src_path)
    trimmed = trim_white_edges(img, threshold=threshold, max_iter=max_iter)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(trimmed, out_path, output_format)
    return out_path
```
Replace with:
```python
def trim_one(src_path: Path, out_path: Path,
             threshold: int = 240, max_iter: int = 5,
             output_format: str = "PNG",
             inset_top: int = 0, inset_right: int = 0,
             inset_bottom: int = 0, inset_left: int = 0) -> Path:
    img = Image.open(src_path)
    trimmed = trim_white_edges(img, threshold=threshold, max_iter=max_iter)
    trimmed = _inset_crop(trimmed, top=inset_top, right=inset_right,
                          bottom=inset_bottom, left=inset_left)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(trimmed, out_path, output_format)
    return out_path
```

- [ ] **Step 1.5: 给 trim_batch 加 inset 参数 + 透传**

Edit `drama_shot_master/grid_ops.py`. Current `trim_batch`:
```python
def trim_batch(src_folder: Path, out_folder: Path,
               threshold: int = 240, max_iter: int = 5,
               output_format: str = "PNG",
               name_suffix: str = "") -> list[Path]:
    out_folder.mkdir(parents=True, exist_ok=True)
    ext = ".png" if output_format.upper() == "PNG" else ".jpg"
    saved = []
    for p in sorted(src_folder.iterdir()):
        if p.suffix.lower() not in SUPPORTED_IMG_EXTS:
            continue
        out = out_folder / f"{p.stem}{name_suffix}{ext}"
        trim_one(p, out, threshold=threshold, max_iter=max_iter,
                 output_format=output_format)
        saved.append(out)
    return saved
```
Replace with (add params + pass through):
```python
def trim_batch(src_folder: Path, out_folder: Path,
               threshold: int = 240, max_iter: int = 5,
               output_format: str = "PNG",
               name_suffix: str = "",
               inset_top: int = 0, inset_right: int = 0,
               inset_bottom: int = 0, inset_left: int = 0) -> list[Path]:
    out_folder.mkdir(parents=True, exist_ok=True)
    ext = ".png" if output_format.upper() == "PNG" else ".jpg"
    saved = []
    for p in sorted(src_folder.iterdir()):
        if p.suffix.lower() not in SUPPORTED_IMG_EXTS:
            continue
        out = out_folder / f"{p.stem}{name_suffix}{ext}"
        trim_one(p, out, threshold=threshold, max_iter=max_iter,
                 output_format=output_format,
                 inset_top=inset_top, inset_right=inset_right,
                 inset_bottom=inset_bottom, inset_left=inset_left)
        saved.append(out)
    return saved
```

- [ ] **Step 1.6: 运行测试，确认通过**

Run: `pytest tests/test_grid_ops.py -v`
Expected: 全 PASS（含 4 个新 inset_crop 测试）。

- [ ] **Step 1.7: 全量回归**

Run: `pytest -q`
Expected: 0 failures。

- [ ] **Step 1.8: 提交**

```bash
git add drama_shot_master/grid_ops.py tests/test_grid_ops.py
git commit -m "feat(trim): add inward-crop (_inset_crop) after white-edge trim

trim_one/trim_batch gain inset_{top,right,bottom,left} (default 0). After
trim_white_edges, _inset_crop crops each edge inward by N px, clamped so it
never yields an empty image; all-zero returns the image unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 1)
- Working dir `/mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master`, branch `feat/video-panel`.
- `trim_white_edges` / `save_image` are imported from external `shot_master` at the top of grid_ops.py — don't touch those imports.
- `_inset_crop` is pure PIL (no external dep), so its tests don't need shot_master.
- IMPORTANT: working tree has UNTRACKED files from the user's other work (theme.py, ui/styles/, assets/, sound-track docs). Do NOT touch/stage them. Stage ONLY grid_ops.py + test_grid_ops.py.

## Self-Review (Task 1)
- 4 inset tests pass + full suite 0 failures?
- `_inset_crop` placed before `trim_one`; returns same object on all-zero?
- trim_one calls `_inset_crop` AFTER `trim_white_edges`, BEFORE save?
- trim_batch passes all 4 insets through to trim_one?
- Committed only the 2 files?

---

## Task 2: trim_panel 4 个 spinbox + 透传

**Files:**
- Modify: `drama_shot_master/ui/panels/trim_panel.py`

- [ ] **Step 2.1: 加 4 个 spinbox 到表单**

Edit `drama_shot_master/ui/panels/trim_panel.py`. Imports currently: `QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox, QLineEdit, QMessageBox`. Add `QHBoxLayout, QWidget, QLabel`:
```python
from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QLineEdit, QMessageBox, QHBoxLayout, QWidget, QLabel,
)
```

In `__init__`, after the existing `f.addRow("格式", self.fmt)` line, add the 4 inset spinboxes in one row:
```python
        self.inset_top = _spin(0, 2000, 0)
        self.inset_bottom = _spin(0, 2000, 0)
        self.inset_left = _spin(0, 2000, 0)
        self.inset_right = _spin(0, 2000, 0)
        inset_row = QHBoxLayout()
        for lbl, sp in (("上", self.inset_top), ("下", self.inset_bottom),
                        ("左", self.inset_left), ("右", self.inset_right)):
            inset_row.addWidget(QLabel(lbl))
            inset_row.addWidget(sp)
        inset_row.addStretch(1)
        inset_wrap = QWidget(); inset_wrap.setLayout(inset_row)
        f.addRow("额外向内裁剪 (px)", inset_wrap)
```

- [ ] **Step 2.2: execute 读值 + 透传**

Edit `drama_shot_master/ui/panels/trim_panel.py`. Current `execute`:
```python
    def execute(self):
        out = self.state.output_dir
        th = self.threshold.value()
        mi = self.max_iter.value()
        suf = self.suffix.text()
        fmt = self.fmt.currentText()
        sel = self.state.selected_paths()
        src_dir = self.state.current_dir

        def task():
            if sel:
                ext = ".png" if fmt.upper() == "PNG" else ".jpg"
                for p in sel:
                    trim_one(p, out / f"{p.stem}{suf}{ext}",
                             threshold=th, max_iter=mi, output_format=fmt)
                return len(sel)
            files = trim_batch(src_dir, out, threshold=th, max_iter=mi,
                               output_format=fmt, name_suffix=suf)
            return len(files)
        ...
```
Replace the body up to and including the `task()` definition with:
```python
    def execute(self):
        out = self.state.output_dir
        th = self.threshold.value()
        mi = self.max_iter.value()
        suf = self.suffix.text()
        fmt = self.fmt.currentText()
        it = self.inset_top.value()
        ib = self.inset_bottom.value()
        il = self.inset_left.value()
        ir = self.inset_right.value()
        sel = self.state.selected_paths()
        src_dir = self.state.current_dir

        def task():
            if sel:
                ext = ".png" if fmt.upper() == "PNG" else ".jpg"
                for p in sel:
                    trim_one(p, out / f"{p.stem}{suf}{ext}",
                             threshold=th, max_iter=mi, output_format=fmt,
                             inset_top=it, inset_right=ir,
                             inset_bottom=ib, inset_left=il)
                return len(sel)
            files = trim_batch(src_dir, out, threshold=th, max_iter=mi,
                               output_format=fmt, name_suffix=suf,
                               inset_top=it, inset_right=ir,
                               inset_bottom=ib, inset_left=il)
            return len(files)
```
(Leave the worker setup below `task()` unchanged.)

- [ ] **Step 2.3: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.panels.trim_panel import TrimPanel; print('ok')"
```
Expected: `ok`（或 ast 回退，如实报告）。

- [ ] **Step 2.4: 全量回归**

Run: `pytest -q`
Expected: 0 failures。

- [ ] **Step 2.5: 提交**

```bash
git add drama_shot_master/ui/panels/trim_panel.py
git commit -m "feat(trim): add 上/下/左/右 inward-crop spinboxes to trim panel

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 2)
- Task 1 added the inset params to `trim_one`/`trim_batch`. This wires the UI to them.
- `_spin(lo, hi, val)` helper already exists in trim_panel.py.
- Note the param order: `trim_one(..., inset_top, inset_right, inset_bottom, inset_left)` — keep keyword args so order can't be mixed up.
- Stage ONLY trim_panel.py.

## Self-Review (Task 2)
- 4 spinboxes (上/下/左/右) default 0, range 0-2000?
- execute reads all 4 + passes to both sel-loop (trim_one) and batch (trim_batch) by keyword?
- Smoke import ok + suite 0 failures?
- Committed only trim_panel.py?

---

## Task 3: 手测清单

**Files:** 无代码变更。

- [ ] **Step 3.1: 交回用户手测清单**

1. 去白边面板出现「额外向内裁剪 (px)」一行，4 个框（上/下/左/右），默认全 0。
2. 全 0 执行 → 输出与之前一致（仅白边 bbox 裁）。
3. 选中 `G1_2.png`，上=8 下=8 左=0 右=0 执行 → 输出比之前上下各少 8px，雾气近白边被裁掉。
4. 整目录批量（不选图）→ 同样应用 inset。
5. 填超大值（如上=99999）→ 不崩、不出空图（保底 1px）。
6. 用裁后图重新生成视频 → 确认白边问题缓解。

报告：全过 DONE；异常 DONE_WITH_CONCERNS + 具体步。

---

## Self-Review 记录
- **Spec coverage:** §4.1 `_inset_crop` → Task 1.3；§4.2 trim_one → 1.4；§4.3 trim_batch → 1.5；§4.4 UI → Task 2；§6 钳制边界 → Task 1.3 + 测试 1.1；§7 测试 → Task 1.1；手测 → Task 3。
- **Placeholder scan:** 无 TBD/“similar to”；每步含完整代码或精确 before/after。
- **Type consistency:** `_inset_crop(img, top, right, bottom, left)`（1.3 定义）→ trim_one（1.4）调用关键字一致；trim_one inset 参数名 `inset_top/right/bottom/left`（1.4）→ trim_batch（1.5）+ trim_panel（2.2）透传一致。
