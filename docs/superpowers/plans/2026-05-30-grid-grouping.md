# 分镜图提示词 手动分组 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在分镜图提示词阶段手动定义每组「镜头范围 + 宫格模式」，逐组或一键生成，修复尾组被强制按更大宫格出图。

**Architecture:** 新增独立可单测组件 `_GridGroupEditor`（含纯函数 auto_fit_mode/default_groups/group_is_valid）；后端 `/prompts` 路由在收到 `options.groups` 时按显式组生成、否则回退原统一切块；PromptsPage 接入编辑器并把 groups 传入请求。全部在 main，TDD。

**Tech Stack:** PySide6 QWidget/QTableWidget, FastAPI SSE, Pydantic, pytest

---

## 文件结构

| 文件 | 职责 | 改动 |
|------|------|------|
| `drama_shot_master/ui/widgets/screenwriter/_grid_group_editor.py` | 分组纯函数 + `_GridGroupEditor` 表格组件 | 新建 |
| `screenwriter_agent/models/requests.py` | `PromptsOptions` + groups/only_group_index | 改 |
| `screenwriter_agent/routes/prompts.py` | 分组生成 + 回退 + `resolve_group_shots` | 改 |
| `drama_shot_master/ui/widgets/screenwriter/_product_tree.py` | `build_from_sb` 支持 groups | 改 |
| `drama_shot_master/ui/widgets/screenwriter/prompts_page.py` | 接入编辑器 + 请求体 | 改 |
| `tests/test_ui/screenwriter/test_grid_group_editor.py` | 纯函数 + widget 测试 | 新建 |
| `tests/test_screenwriter_agent/test_route_prompts.py` | 分组/单组/回退 | 补 |
| `tests/test_ui/screenwriter/test_prompts_page.py` | 集成请求体 | 补 |

---

## Task 1：分组纯函数

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/_grid_group_editor.py`
- Test: `tests/test_ui/screenwriter/test_grid_group_editor.py`

- [ ] **Step 1：写失败测试**

创建 `tests/test_ui/screenwriter/test_grid_group_editor.py`：

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import (
    auto_fit_mode, default_groups, group_capacity, group_is_valid,
)


def test_auto_fit_mode():
    assert auto_fit_mode(1) == "single"
    assert auto_fit_mode(2) == "4"
    assert auto_fit_mode(4) == "4"
    assert auto_fit_mode(5) == "9"
    assert auto_fit_mode(9) == "9"


def test_group_capacity():
    assert group_capacity("single") == 1
    assert group_capacity("4") == 4
    assert group_capacity("9") == 9


def test_default_groups_10_shots():
    ids = [f"S01_{i}" for i in range(1, 11)]
    g = default_groups(ids)
    assert len(g) == 2
    assert g[0]["grid_mode"] == "9"
    assert g[0]["shot_ids"] == ids[:9]
    assert g[1]["grid_mode"] == "single"
    assert g[1]["shot_ids"] == ["S01_10"]


def test_default_groups_4_shots():
    ids = ["A", "B", "C", "D"]
    g = default_groups(ids)
    assert len(g) == 1
    assert g[0]["grid_mode"] == "4"


def test_default_groups_empty():
    assert default_groups([]) == []


def test_group_is_valid():
    assert group_is_valid({"grid_mode": "9", "shot_ids": ["a", "b"]}) is True
    assert group_is_valid({"grid_mode": "single", "shot_ids": ["a", "b"]}) is False
    assert group_is_valid({"grid_mode": "4", "shot_ids": []}) is False
```

- [ ] **Step 2：运行确认失败**

Run: `python -m pytest tests/test_ui/screenwriter/test_grid_group_editor.py -q`
Expected: FAIL（ModuleNotFoundError：`_grid_group_editor` 不存在）

- [ ] **Step 3：创建文件 + 纯函数**

创建 `drama_shot_master/ui/widgets/screenwriter/_grid_group_editor.py`：

```python
"""分镜图提示词 — 手动分组编辑器 + 纯函数。

纯函数无 Qt 依赖，便于单测；_GridGroupEditor 是表格 UI。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QHeaderView,
)

_MODE_LABELS = [("single", "单帧"), ("4", "四宫格"), ("9", "九宫格")]
_CAP = {"single": 1, "4": 4, "9": 9}


def group_capacity(grid_mode: str) -> int:
    return _CAP.get(grid_mode, 9)


def auto_fit_mode(count: int) -> str:
    """容纳 count 镜的最小容量模式。"""
    if count <= 1:
        return "single"
    if count <= 4:
        return "4"
    return "9"


def default_groups(shot_ids: list[str]) -> list[dict]:
    """按 9 切块；每组 grid_mode = auto_fit_mode(组镜头数)。"""
    out: list[dict] = []
    for i in range(0, len(shot_ids), 9):
        chunk = shot_ids[i:i + 9]
        out.append({"grid_mode": auto_fit_mode(len(chunk)),
                    "shot_ids": list(chunk)})
    return out


def group_is_valid(group: dict) -> bool:
    ids = group.get("shot_ids") or []
    return 0 < len(ids) <= group_capacity(group.get("grid_mode", "9"))
```

- [ ] **Step 4：运行确认通过**

Run: `python -m pytest tests/test_ui/screenwriter/test_grid_group_editor.py -q`
Expected: 6 passed

- [ ] **Step 5：提交**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_grid_group_editor.py \
    tests/test_ui/screenwriter/test_grid_group_editor.py
git commit -m "feat(screenwriter): 分组纯函数 auto_fit_mode/default_groups/group_is_valid"
```

---

## Task 2：`_GridGroupEditor` widget

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/_grid_group_editor.py`（追加类）
- Test: `tests/test_ui/screenwriter/test_grid_group_editor.py`（追加）

- [ ] **Step 1：写失败测试**

在测试文件末尾追加：

```python
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def test_editor_set_shots_builds_default_groups():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()
    ed.set_shots([f"S01_{i}" for i in range(1, 11)])
    g = ed.groups()
    assert len(g) == 2
    assert g[0]["grid_mode"] == "9" and len(g[0]["shot_ids"]) == 9
    assert g[1]["grid_mode"] == "single"


def test_editor_generate_group_signal():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()
    ed.set_shots(["A", "B"])
    got = []
    ed.generateGroup.connect(got.append)
    ed._emit_generate_group(1)        # 1-based
    assert got == [1]


def test_editor_generate_all_signal():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()
    ed.set_shots(["A", "B", "C", "D"])
    got = []
    ed.generateAll.connect(lambda: got.append(True))
    ed._gen_all_btn.click()
    assert got == [True]


def test_editor_add_group_appends():
    _app()
    from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
    ed = _GridGroupEditor()
    ed.set_shots(["A", "B", "C"])
    n0 = len(ed.groups())
    ed._add_group()
    assert len(ed.groups()) == n0 + 1
```

- [ ] **Step 2：运行确认失败**

Run: `python -m pytest tests/test_ui/screenwriter/test_grid_group_editor.py -k editor -q`
Expected: FAIL（`_GridGroupEditor` 不存在）

- [ ] **Step 3：追加 widget 类**

在 `_grid_group_editor.py` 末尾追加：

```python
class _GridGroupEditor(QWidget):
    """分组表格：组 | 起始 | 结束 | 模式 | 生成 | 状态 + 添加组 / 全部生成。"""

    generateGroup = Signal(int)   # 1-based 组序号
    generateAll = Signal()
    groupsChanged = Signal()

    _COL_LABEL, _COL_START, _COL_END, _COL_MODE, _COL_GEN, _COL_STATUS = range(6)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shot_ids: list[str] = []
        self._groups: list[dict] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(QLabel("分组："))
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["组", "起始", "结束", "模式", "生成", "状态"])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(self._COL_START, QHeaderView.Stretch)
        h.setSectionResizeMode(self._COL_END, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        v.addWidget(self._table)
        bar = QHBoxLayout()
        add_btn = QPushButton("+ 添加组")
        add_btn.clicked.connect(self._add_group)
        bar.addWidget(add_btn)
        bar.addStretch(1)
        self._gen_all_btn = QPushButton("全部生成")
        self._gen_all_btn.clicked.connect(lambda: self.generateAll.emit())
        bar.addWidget(self._gen_all_btn)
        v.addLayout(bar)

    # —— 公共 API ——

    def set_shots(self, shot_ids: list[str]) -> None:
        self._shot_ids = list(shot_ids)
        self._groups = default_groups(self._shot_ids)
        self._rebuild()

    def groups(self) -> list[dict]:
        return [dict(g) for g in self._groups]

    def set_group_status(self, index: int, status: str) -> None:
        """index 1-based；status: idle/running/done/error。"""
        r = index - 1
        if 0 <= r < self._table.rowCount():
            it = self._table.item(r, self._COL_STATUS)
            glyph = {"idle": "○", "running": "●", "done": "✓",
                     "error": "✗"}.get(status, "○")
            if it:
                it.setText(glyph)

    # —— 内部 ——

    def _emit_generate_group(self, index: int) -> None:
        self.generateGroup.emit(index)

    def _add_group(self) -> None:
        # 追加一个默认单帧组（取第一个镜头，用户可改）
        first = self._shot_ids[0] if self._shot_ids else ""
        self._groups.append({"grid_mode": "single",
                             "shot_ids": [first] if first else []})
        self._rebuild()
        self.groupsChanged.emit()

    def _slice_ids(self, start_id: str, end_id: str) -> list[str]:
        try:
            i = self._shot_ids.index(start_id)
            j = self._shot_ids.index(end_id)
        except ValueError:
            return []
        if j < i:
            i, j = j, i
        return self._shot_ids[i:j + 1]

    def _mk_combo(self, items, current) -> QComboBox:
        c = QComboBox()
        for data, label in items:
            c.addItem(label, data)
        idx = c.findData(current)
        if idx >= 0:
            c.setCurrentIndex(idx)
        return c

    def _rebuild(self) -> None:
        self._table.setRowCount(0)
        for gi, g in enumerate(self._groups, start=1):
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, self._COL_LABEL, QTableWidgetItem(f"S{gi}"))
            ids = g.get("shot_ids") or []
            start_id = ids[0] if ids else (self._shot_ids[0] if self._shot_ids else "")
            end_id = ids[-1] if ids else start_id
            start_combo = self._mk_combo(
                [(s, s) for s in self._shot_ids], start_id)
            end_combo = self._mk_combo(
                [(s, s) for s in self._shot_ids], end_id)
            mode_combo = self._mk_combo(_MODE_LABELS, g.get("grid_mode", "9"))
            start_combo.currentIndexChanged.connect(
                lambda _=0, row=r: self._on_row_changed(row))
            end_combo.currentIndexChanged.connect(
                lambda _=0, row=r: self._on_row_changed(row))
            mode_combo.currentIndexChanged.connect(
                lambda _=0, row=r: self._on_row_changed(row))
            self._table.setCellWidget(r, self._COL_START, start_combo)
            self._table.setCellWidget(r, self._COL_END, end_combo)
            self._table.setCellWidget(r, self._COL_MODE, mode_combo)
            gen_btn = QPushButton("▶")
            gen_btn.setMinimumWidth(40)
            gen_btn.clicked.connect(
                lambda _=False, idx=gi: self._emit_generate_group(idx))
            self._table.setCellWidget(r, self._COL_GEN, gen_btn)
            valid = group_is_valid(g)
            st = QTableWidgetItem("○" if valid else "✗ 超容量")
            self._table.setItem(r, self._COL_STATUS, st)
            gen_btn.setEnabled(valid)

    def _on_row_changed(self, row: int) -> None:
        if not (0 <= row < len(self._groups)):
            return
        sc = self._table.cellWidget(row, self._COL_START)
        ec = self._table.cellWidget(row, self._COL_END)
        mc = self._table.cellWidget(row, self._COL_MODE)
        if sc is None or ec is None or mc is None:
            return
        self._groups[row] = {
            "grid_mode": mc.currentData(),
            "shot_ids": self._slice_ids(sc.currentData(), ec.currentData()),
        }
        # 仅刷新该行状态/生成按钮可用性
        valid = group_is_valid(self._groups[row])
        st = self._table.item(row, self._COL_STATUS)
        if st:
            st.setText("○" if valid else "✗ 超容量")
        gb = self._table.cellWidget(row, self._COL_GEN)
        if gb:
            gb.setEnabled(valid)
        self.groupsChanged.emit()
```

- [ ] **Step 4：运行确认通过**

Run: `python -m pytest tests/test_ui/screenwriter/test_grid_group_editor.py -q`
Expected: 10 passed

- [ ] **Step 5：提交**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_grid_group_editor.py \
    tests/test_ui/screenwriter/test_grid_group_editor.py
git commit -m "feat(screenwriter): _GridGroupEditor 分组表格组件"
```

---

## Task 3：后端 PromptsOptions + 路由分组

**Files:**
- Modify: `screenwriter_agent/models/requests.py:79-84`
- Modify: `screenwriter_agent/routes/prompts.py`
- Test: `tests/test_screenwriter_agent/test_route_prompts.py`

- [ ] **Step 1：写失败测试（`resolve_group_shots` 纯函数）**

在 `tests/test_screenwriter_agent/test_route_prompts.py` 末尾追加：

```python
def test_resolve_group_shots_orders_and_skips_missing():
    from screenwriter_agent.routes.prompts import resolve_group_shots
    sb = {"shots": [{"shotId": "S01_1"}, {"shotId": "S01_2"},
                    {"shotId": "S01_3"}]}
    out = resolve_group_shots(sb, ["S01_2", "S01_3", "NOPE"])
    assert [s["shotId"] for s in out] == ["S01_2", "S01_3"]


def test_prompts_options_has_groups_fields():
    from screenwriter_agent.models.requests import PromptsOptions
    o = PromptsOptions()
    assert o.groups == []
    assert o.only_group_index is None
    o2 = PromptsOptions(groups=[{"grid_mode": "9", "shot_ids": ["a"]}],
                        only_group_index=1)
    assert o2.groups[0]["grid_mode"] == "9"
    assert o2.only_group_index == 1
```

- [ ] **Step 2：运行确认失败**

Run: `python -m pytest tests/test_screenwriter_agent/test_route_prompts.py -k "resolve_group_shots or groups_fields" -v`
Expected: FAIL（ImportError + AttributeError）

- [ ] **Step 3：改 `PromptsOptions`**

将 `screenwriter_agent/models/requests.py:79-84` 的 `PromptsOptions` 替换为：

```python
class PromptsOptions(BaseModel):
    grid_mode: str = "9"                  # "single" | "4" | "9"（无 groups 时的回退切块）
    include_character_refs: bool = True
    style_extra: str = ""
    negative_preset: str = "标准 SDXL"
    quality_boost: bool = True
    groups: list = Field(default_factory=list)   # [{"grid_mode":..,"shot_ids":[..]}]
    only_group_index: int | None = None          # 1-based；仅生成该组
```

（确认文件顶部已 `from pydantic import BaseModel, Field`；若缺 Field 则补。）

- [ ] **Step 4：加 `resolve_group_shots` + 改路由分组段**

在 `screenwriter_agent/routes/prompts.py` 的 `build_grid_user_prompt` 之后（模块级）追加：

```python
def resolve_group_shots(sb: dict, shot_ids: list) -> list:
    """按 shot_ids 顺序从 sb['shots'] 取出 shot dict；缺失的 id 跳过。"""
    by_id = {}
    for s in sb.get("shots", []):
        sid = s.get("shotId") or s.get("shot_id") or s.get("id")
        if sid is not None:
            by_id[str(sid)] = s
    out = []
    for sid in shot_ids:
        s = by_id.get(str(sid))
        if s is not None:
            out.append(s)
    return out
```

将 `prompts.py:131-151`（从 `tpl_grid, _ = load_template(...)` 到第二个 `yield sse_event("partial", {... grid_prompt ...})` 结束，即整个 N 宫格 for 循环段）替换为：

```python
            # 2) N 宫格分镜图
            tpl_grid, _ = load_template("grid_prompt", project_dir=project_dir)
            shots = sb.get("shots", [])
            user_groups = opts.get("groups") or []
            if user_groups:
                # 显式分组：每组按自己的 grid_mode + shot_ids 生成 S{gi}.md
                plan = []
                for gi, g in enumerate(user_groups, start=1):
                    grp = resolve_group_shots(sb, g.get("shot_ids", []))
                    plan.append((gi, grp, g.get("grid_mode", "9")))
                only = opts.get("only_group_index")
                if only is not None:
                    plan = [t for t in plan if t[0] == only]
                n_groups = len(user_groups)
            else:
                # 回退：按统一 grid_mode 切块
                grid_size = {"single": 1, "4": 4, "9": 9}.get(opts["grid_mode"], 9)
                plan = [(gi, shots[i:i + grid_size], opts["grid_mode"])
                        for gi, i in enumerate(
                            range(0, len(shots), grid_size), start=1)]
                n_groups = len(plan)

            for gi, grp, gmode in plan:
                yield sse_event("status", {"phase": "streaming"})
                group_opts = dict(opts)
                group_opts["grid_mode"] = gmode
                prompt = build_grid_user_prompt(tpl_grid, sb, grp, gi, group_opts)
                acc: list[str] = []
                for c in client.stream_chat([{"role": "user", "content": prompt}]):
                    if await request.is_disconnected():
                        print("[prompts] disconnected mid-grid", flush=True)
                        return
                    if c.kind == "delta":
                        acc.append(c.text)
                sheet_md = "".join(acc)
                sheet_path = grid_dir / f"S{gi}.md"
                atomic_write_text(sheet_path, sheet_md)
                saved_paths.append(str(sheet_path))
                yield sse_event("partial", {"saved": str(sheet_path),
                                            "kind": "grid_prompt",
                                            "episode_id": req.episode_id})
```

并把紧随其后的 `done` 事件里 `"grid_sheets": len(groups)` 改为 `"grid_sheets": n_groups`。

- [ ] **Step 5：运行确认通过**

Run: `python -m pytest tests/test_screenwriter_agent/test_route_prompts.py -q`
Expected: 全部通过（既有 + 新增 2）

- [ ] **Step 6：全套 agent 回归**

Run: `python -m pytest tests/test_screenwriter_agent/ -q`
Expected: 全部通过

- [ ] **Step 7：提交**

```bash
git add screenwriter_agent/models/requests.py screenwriter_agent/routes/prompts.py \
    tests/test_screenwriter_agent/test_route_prompts.py
git commit -m "feat(screenwriter): /prompts 支持显式 groups + only_group_index + 回退"
```

---

## Task 4：_product_tree 支持 groups

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/_product_tree.py:28-56`
- Test: `tests/test_ui/screenwriter/test_product_tree.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_ui/screenwriter/test_product_tree.py` 末尾追加：

```python
def test_build_from_sb_with_groups(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from drama_shot_master.ui.widgets.screenwriter._product_tree import _ProductTree
    sb = {"characters": [], "shots": [{"shotId": f"S{i}"} for i in range(10)]}
    t = _ProductTree()
    t.build_from_sb(tmp_path, sb, groups=[{"shot_ids": ["a"] * 9},
                                          {"shot_ids": ["b"]}],
                    include_character_refs=False)
    # 期望 N宫格 下 2 个文件 S1.md / S2.md
    names = [p.name for p in t.tree_items]
    assert "S1.md" in names and "S2.md" in names and "S3.md" not in names
```

- [ ] **Step 2：运行确认失败**

Run: `python -m pytest tests/test_ui/screenwriter/test_product_tree.py -k with_groups -v`
Expected: FAIL（`build_from_sb` 不接受 `groups` 关键字）

- [ ] **Step 3：改 `build_from_sb` 签名 + 网格段**

将 `_product_tree.py:28-56` 替换为：

```python
    def build_from_sb(self, prompts_dir: Path, sb: dict,
                      *, grid_mode: str = "9",
                      groups: list | None = None,
                      include_character_refs: bool,
                      episode_id: str = ""):
        """按分镜.json 推算预期文件，构建树 + 状态点。
        groups 非空时按组数渲染 N宫格/S{k}.md；否则按 grid_mode 统一切块。"""
        self.clear()
        self.tree_items = {}
        if include_character_refs:
            characters = sb.get("characters") or []
            char_group = QTreeWidgetItem(self,
                [f"📁 角色参考图 ({len(characters)})"])
            char_group.setExpanded(True)
            for ch in characters:
                name = ch.get("name", "")
                if not name:
                    continue
                p = prompts_dir / "角色参考图" / f"{name}_ref.md"
                status = "done" if p.is_file() else "missing"
                self._add_file_item(char_group, p, status)
        # 网格
        shots = sb.get("shots") or []
        if groups:
            n_groups = len(groups)
        else:
            grid_size = {"single": 1, "4": 4, "9": 9}.get(grid_mode, 9)
            n_groups = ceil(len(shots) / grid_size) if shots else 0
        grid_group = QTreeWidgetItem(self, [f"📁 N 宫格 ({n_groups})"])
        grid_group.setExpanded(True)
        for i in range(1, n_groups + 1):
            p = prompts_dir / "N宫格" / f"S{i}.md"
            status = "done" if p.is_file() else "missing"
            self._add_file_item(grid_group, p, status)
```

- [ ] **Step 4：运行确认通过**

Run: `python -m pytest tests/test_ui/screenwriter/test_product_tree.py -q`
Expected: 全部通过（既有 + 新增 1）

- [ ] **Step 5：提交**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_product_tree.py \
    tests/test_ui/screenwriter/test_product_tree.py
git commit -m "feat(screenwriter): _product_tree.build_from_sb 支持 groups"
```

---

## Task 5：PromptsPage 接入编辑器 + 请求体

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/prompts_page.py`
- Test: `tests/test_ui/screenwriter/test_prompts_page.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_ui/screenwriter/test_prompts_page.py` 末尾追加：

```python
def test_generate_all_body_includes_groups(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    captured = {}
    p._start_stream = lambda path, body, params=None: captured.update(body)
    p._group_editor.generateAll.emit()
    assert "groups" in captured["options"]
    assert captured["options"].get("only_group_index") is None


def test_generate_single_group_body_includes_index(tmp_path):
    _app()
    (tmp_path / "分镜.json").write_text(json.dumps(_sb_min()), encoding="utf-8")
    p = PromptsPage(_StubClient())
    p.set_project(tmp_path)
    captured = {}
    p._start_stream = lambda path, body, params=None: captured.update(body)
    p._group_editor.generateGroup.emit(1)
    assert captured["options"]["only_group_index"] == 1
    assert "groups" in captured["options"]
```

> 注：`_sb_min()` 已在该测试文件中定义（含 characters + shots）。若 shots 数不足，仍能形成至少 1 组。

- [ ] **Step 2：运行确认失败**

Run: `python -m pytest tests/test_ui/screenwriter/test_prompts_page.py -k "generate_all_body or single_group_body" -v`
Expected: FAIL（`_group_editor` 不存在 / 无 only_group_index）

- [ ] **Step 3：接入编辑器（移除 grid_combo，嵌入 _GridGroupEditor）**

(a) `prompts_page.py` 顶部 imports 追加：

```python
from drama_shot_master.ui.widgets.screenwriter._grid_group_editor import _GridGroupEditor
```

(b) 删除 `_build_param_bar` 里 grid 相关 3 行（`bar.addWidget(QLabel("grid:"))` + `self._grid_combo = QComboBox()` + `addItems` + `setCurrentText` + `currentTextChanged.connect` + `bar.addWidget(self._grid_combo)`）。即移除整段 grid_combo 构建（约 63-68 行）。

(c) `_build_left` 中，在 `self._tree = _ProductTree()` **之前**插入编辑器：

```python
    def _build_left(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        self._group_editor = _GridGroupEditor()
        self._group_editor.generateAll.connect(self._on_generate_clicked)
        self._group_editor.generateGroup.connect(self._on_generate_group)
        self._group_editor.groupsChanged.connect(self._rebuild_tree)
        v.addWidget(self._group_editor)
        self._tree = _ProductTree()
        self._tree.fileActivated.connect(self._on_file_activated)
        v.addWidget(self._tree, 1)
        btn = QPushButton("📂 打开 prompts/")
        btn.clicked.connect(self._on_open_prompts_dir)
        v.addWidget(btn)
        return w
```

(d) `_rebuild_tree` 改为用 editor 的 groups：

```python
    def _rebuild_tree(self, *_):
        if self._prompts_dir is None or self._sb is None:
            self._tree.clear()
            self._tree.tree_items = {}
            return
        self._tree.build_from_sb(
            self._prompts_dir, self._sb,
            groups=self._group_editor.groups(),
            include_character_refs=self._char_refs_chk.isChecked())
```

(e) 加载分镜后给 editor 喂镜头 id。找到读取 `self._sb` 成功后（`set_project` 与 `_on_episode_changed` 里 `self._rebuild_tree()` 调用**之前**）插入：

```python
        self._group_editor.set_shots(
            [str(s.get("shotId") or s.get("shot_id") or s.get("id") or "")
             for s in (self._sb.get("shots") or [])])
```

（两处：`set_project` 的成功分支、`_on_episode_changed` 的成功分支。）

(f) `_on_generate_clicked` 的 body.options 改为带 groups（去掉 grid_mode 来源 grid_combo）。将 options 字典替换为：

```python
            "options": {
                "include_character_refs": self._char_refs_chk.isChecked(),
                "style_extra": self._style_extra_edit.text().strip(),
                "negative_preset": self._negative_combo.currentText(),
                "quality_boost": self._quality_chk.isChecked(),
                "groups": self._group_editor.groups(),
            },
```

(g) 新增单组生成方法（放在 `_on_generate_clicked` 之后）：

```python
    def _on_generate_group(self, index: int):
        if self._project_dir is None or self._sb is None:
            QMessageBox.warning(self, "上游缺失",
                                 "请先在「分镜」阶段生成分镜.json。")
            return
        body = {
            "project_dir": str(self._project_dir),
            "episode_id": self._current_episode,
            "options": {
                "include_character_refs": False,
                "style_extra": self._style_extra_edit.text().strip(),
                "negative_preset": self._negative_combo.currentText(),
                "quality_boost": self._quality_chk.isChecked(),
                "groups": self._group_editor.groups(),
                "only_group_index": index,
            },
        }
        self._start_stream("/prompts", body, None)
```

- [ ] **Step 4：运行确认通过**

Run: `python -m pytest tests/test_ui/screenwriter/test_prompts_page.py -q`
Expected: 全部通过（既有 + 新增 2）

> 既有用例若引用 `self._grid_combo`，改为不再依赖（grid 已移除）。若有 `test_episode_selector_renders` 等不涉及 grid 的用例不受影响。若个别用例断言 grid_combo 存在，删除该断言或改断言 `_group_editor` 存在。

- [ ] **Step 5：提交**

```bash
git add drama_shot_master/ui/widgets/screenwriter/prompts_page.py \
    tests/test_ui/screenwriter/test_prompts_page.py
git commit -m "feat(screenwriter): PromptsPage 接入 _GridGroupEditor + 逐组/全部生成请求体"
```

---

## Task 6：端到端回归

- [ ] **Step 1：跑相关全套**

Run:
```bash
python -m pytest tests/test_ui/screenwriter/ tests/test_screenwriter_agent/ \
  --deselect "tests/test_ui/screenwriter/test_screenwriter_panel.py::test_stage_advance_target_with_existing_output_skips_auto_gen" -q
```
Expected: 全部通过

- [ ] **Step 2：确认在 main**

Run: `git branch --show-current`
Expected: `main`

---

## 验收标准

| 检查项 | 验证 |
|--------|------|
| auto_fit/default_groups/valid | `test_grid_group_editor.py` 纯函数 |
| 编辑器 set_shots/信号/添加组 | `test_grid_group_editor.py` widget |
| 路由显式分组 + 单组 + 回退 | `test_route_prompts.py` |
| 树按 groups 渲染 | `test_product_tree.py` |
| 全部/单组请求体 | `test_prompts_page.py` |
| 无回归 | Task 6 |
