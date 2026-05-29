# 任务栏折叠功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给五个面板（编剧/出图/视频/配音/配乐）的左侧任务栏加折叠/展开功能，折叠后显示 40px 图标轨（序号徽章+状态点+tooltip）。

**Architecture:** 新建 CollapsibleTaskBar 共用包装器，内部 QStackedWidget 切换展开视图（原 task manager）和图标轨视图（_IconRail）；折叠时调 splitter.setSizes([40, rest])，展开时恢复；各 task manager 实现 icon_rail_items() 协议。

**Tech Stack:** Python 3.11+ / PySide6 (QWidget, QPainter, QSplitter, QStackedWidget)

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `drama_shot_master/ui/widgets/collapsible_task_bar.py` | 新建 | IconRailItem + _RailBadge + _IconRail + CollapsibleTaskBar |
| `tests/test_ui/test_collapsible_task_bar.py` | 新建 | 全部组件测试 |
| `drama_shot_master/config.py` | 修改 | 加 `task_bar_collapsed: dict` 字段 |
| `tests/test_config/test_load_config.py` | 修改 | 追加 task_bar_collapsed roundtrip 测试 |
| `drama_shot_master/ui/widgets/screenwriter/task_manager.py` | 修改 | 加 `icon_rail_updated` signal、`icon_rail_items()`、`select_by_id()` |
| `tests/test_ui/screenwriter/test_task_manager.py` | 修改 | 追加 icon_rail 2 个测试 |
| `drama_shot_master/ui/panels/imggen_task_manager_panel.py` | 修改 | 加 `icon_rail_updated` signal、`icon_rail_items()`、`select_by_id()` |
| `tests/test_ui/test_imggen_task_manager_smoke.py` | 新建 | imggen icon_rail_items 冒烟测试 |
| `drama_shot_master/ui/panels/video_task_manager_panel.py` | 修改 | 加 `icon_rail_updated` signal、`icon_rail_items()`、`select_by_id()` |
| `tests/test_ui/test_video_task_manager_icon_rail_smoke.py` | 新建 | video icon_rail_items 冒烟测试 |
| `drama_shot_master/ui/panels/dub_task_manager_panel.py` | 修改 | 加 `icon_rail_updated` signal、`icon_rail_items()`、`select_by_id()` |
| `tests/test_ui/test_dub_task_manager_icon_rail_smoke.py` | 新建 | dub icon_rail_items 冒烟测试 |
| `drama_shot_master/ui/pages/task_workspace_page.py` | 修改 | 用 CollapsibleTaskBar 包 manager；绑定 splitter |
| `tests/test_ui/test_task_workspace_page_smoke.py` | 修改 | 追加 has_collapsible_bar 测试 |
| `drama_shot_master/ui/panels/screenwriter_panel.py` | 修改 | 用 CollapsibleTaskBar 包 _task_manager；绑定 splitter |
| `tests/test_ui/screenwriter/test_screenwriter_panel.py` | 修改 | 追加 has_collapsible_bar 测试 |

---

## Task 1: Config 加 task_bar_collapsed 字段

**Files:**
- Modify: `drama_shot_master/config.py`
- Modify: `tests/test_config/test_load_config.py`

- [ ] **Step 1: 在测试文件末尾追加两个失败测试**

打开 `tests/test_config/test_load_config.py`，在文件末尾追加：

```python
def test_task_bar_collapsed_default():
    from drama_shot_master.config import Config
    cfg = Config()
    assert cfg.task_bar_collapsed == {}


def test_task_bar_collapsed_update_settings_roundtrip(tmp_path):
    import json
    from drama_shot_master.config import Config, load_config
    cfg = Config()
    cfg.settings_path = tmp_path / "settings.json"
    cfg.update_settings(task_bar_collapsed={"screenwriter": True, "imggen": False})
    data = json.loads(cfg.settings_path.read_text(encoding="utf-8"))
    assert data["task_bar_collapsed"] == {"screenwriter": True, "imggen": False}
    cfg2 = load_config(env_path=tmp_path / ".env.nonexistent",
                       settings_path=cfg.settings_path)
    assert cfg2.task_bar_collapsed == {"screenwriter": True, "imggen": False}
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
python -m pytest tests/test_config/test_load_config.py::test_task_bar_collapsed_default tests/test_config/test_load_config.py::test_task_bar_collapsed_update_settings_roundtrip -v
```

预期：FAIL — `AttributeError: 'Config' object has no attribute 'task_bar_collapsed'`

- [ ] **Step 3: 在 Config dataclass 加字段**

在 `drama_shot_master/config.py` 里，找到：

```python
    # Phase 4a: SFX 音效层
    sfx_workflow_id: str = "2060218796413112321"
```

在该行**上方**插入：

```python
    # UI 状态
    task_bar_collapsed: dict = field(default_factory=dict)
```

- [ ] **Step 4: 在 update_settings 写盘字典加 task_bar_collapsed**

在 `drama_shot_master/config.py` 的 `update_settings` 方法里，找到 `data = {` 字典中最后一个 SFX 字段（即 `"sfx_seeds_count": self.sfx_seeds_count,`），在其**后面**（`}` 之前）追加：

```python
                "task_bar_collapsed": self.task_bar_collapsed,
```

- [ ] **Step 5: 在 load_config 的读取段加 task_bar_collapsed**

在 `drama_shot_master/config.py` 的 `load_config` 函数里，找到处理 sfx 字段的循环（约第 406–418 行）：

```python
                for fld, caster in [
                    ("sfx_workflow_id", str),
                    ("sfx_plan_frames_per_shot", int),
                    ("sfx_max_concurrency", int),
                    ("sfx_default_volume", float),
                    ("sfx_ducking_db", float),
                    ("sfx_seeds_count", int),
                ]:
                    if fld in data:
                        try:
                            setattr(cfg, fld, caster(data[fld]))
                        except (TypeError, ValueError):
                            pass
```

在该代码块**后面**（仍在 `except (json.JSONDecodeError, OSError, UnicodeDecodeError)` 之前）追加：

```python
                if "task_bar_collapsed" in data and isinstance(
                        data["task_bar_collapsed"], dict):
                    cfg.task_bar_collapsed = dict(data["task_bar_collapsed"])
```

- [ ] **Step 6: 运行测试，确认 PASS**

```bash
python -m pytest tests/test_config/test_load_config.py -v
```

预期：全部 PASS（包含原有的 sfx 相关用例）

- [ ] **Step 7: Commit**

```bash
git add drama_shot_master/config.py tests/test_config/test_load_config.py
git commit -m "feat(config): add task_bar_collapsed dict field + roundtrip"
```

---

## Task 2: IconRailItem + _RailBadge 组件

**Files:**
- Create: `drama_shot_master/ui/widgets/collapsible_task_bar.py`
- Create: `tests/test_ui/test_collapsible_task_bar.py`

- [ ] **Step 1: 创建测试文件，写 _RailBadge 的失败测试**

新建 `tests/test_ui/test_collapsible_task_bar.py`，内容：

```python
"""CollapsibleTaskBar 组件测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


# ── Task 2: IconRailItem + _RailBadge ─────────────────────────────────────

def test_rail_badge_size():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _RailBadge
    item = IconRailItem(1, "A", "idle", "tt", "x")
    badge = _RailBadge(item)
    assert badge.width() == 40 and badge.height() == 36


def test_rail_badge_emits_item_id_on_click():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _RailBadge
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    item = IconRailItem(1, "测", "done", "测试项目\n已完成", "id-abc")
    badge = _RailBadge(item)
    got = []
    badge.clicked.connect(got.append)
    QTest.mouseClick(badge, Qt.LeftButton)
    assert got == ["id-abc"]


def test_rail_badge_all_status_keys_have_color():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import _RailBadge
    for status in ("done", "running", "idle", "error"):
        color = _RailBadge.STATUS_COLORS[status]
        assert color.startswith("#") and len(color) == 7
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/test_collapsible_task_bar.py::test_rail_badge_size tests/test_ui/test_collapsible_task_bar.py::test_rail_badge_emits_item_id_on_click tests/test_ui/test_collapsible_task_bar.py::test_rail_badge_all_status_keys_have_color -v
```

预期：FAIL — `ModuleNotFoundError` 或 `ImportError`（文件尚不存在）

- [ ] **Step 3: 创建实现文件，写 IconRailItem + _RailBadge**

新建 `drama_shot_master/ui/widgets/collapsible_task_bar.py`，内容：

```python
"""CollapsibleTaskBar：任务栏折叠/展开包装器。

组件层次：
  IconRailItem          dataclass — 图标轨一行数据
  _RailBadge            QWidget   — 单个圆形徽章行（40×36px）
  _IconRail             QWidget   — 整个图标轨（顶部展开按钮 + 徽章列表）
  CollapsibleTaskBar    QWidget   — 包装任意 task manager，提供折叠/展开
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QStackedWidget, QPushButton, QScrollArea, QSplitter,
)


# ── 数据类 ─────────────────────────────────────────────────────────────────

@dataclass
class IconRailItem:
    index: int        # 1-based 序号
    label: str        # 项目名首两字（备用）
    status: str       # "done" | "running" | "idle" | "error"
    tooltip: str      # "项目名\n当前阶段: xxx"
    item_id: str      # 路径或 task_id 字符串


# ── _RailBadge ─────────────────────────────────────────────────────────────

class _RailBadge(QWidget):
    """40×36px 圆形徽章行：序号圆 + 右下角状态点。点击发出 clicked(item_id)。"""

    clicked = Signal(str)

    STATUS_COLORS: dict[str, str] = {
        "done":    "#52b788",
        "running": "#4a9eff",
        "idle":    "#666666",
        "error":   "#e05252",
    }

    def __init__(self, item: IconRailItem, parent=None):
        super().__init__(parent)
        self._item = item
        self.setFixedSize(40, 36)
        self.setToolTip(item.tooltip)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 圆形徽章（24px 直径，居中偏上）
        badge_size = 24
        bx = (self.width() - badge_size) // 2
        by = (self.height() - badge_size) // 2 - 1
        p.setBrush(QColor("#3a3f4a"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(bx, by, badge_size, badge_size)

        # 序号文字
        p.setPen(QPen(QColor("#d0d4dc")))
        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(bx, by, badge_size, badge_size,
                   Qt.AlignCenter, str(self._item.index))

        # 右下角 8px 状态点
        dot_color = self.STATUS_COLORS.get(self._item.status, "#666666")
        p.setBrush(QColor(dot_color))
        p.setPen(Qt.NoPen)
        dot_size = 8
        dx = bx + badge_size - dot_size // 2
        dy = by + badge_size - dot_size // 2
        p.drawEllipse(dx, dy, dot_size, dot_size)

        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._item.item_id)
        super().mousePressEvent(event)
```

- [ ] **Step 4: 运行测试，确认 PASS**

```bash
python -m pytest tests/test_ui/test_collapsible_task_bar.py::test_rail_badge_size tests/test_ui/test_collapsible_task_bar.py::test_rail_badge_emits_item_id_on_click tests/test_ui/test_collapsible_task_bar.py::test_rail_badge_all_status_keys_have_color -v
```

预期：3 PASS

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/collapsible_task_bar.py tests/test_ui/test_collapsible_task_bar.py
git commit -m "feat(ui): IconRailItem dataclass + _RailBadge widget"
```

---

## Task 3: _IconRail 组件

**Files:**
- Modify: `drama_shot_master/ui/widgets/collapsible_task_bar.py`
- Modify: `tests/test_ui/test_collapsible_task_bar.py`

- [ ] **Step 1: 在测试文件末尾追加 _IconRail 失败测试**

在 `tests/test_ui/test_collapsible_task_bar.py` 末尾追加：

```python
# ── Task 3: _IconRail ──────────────────────────────────────────────────────

def test_icon_rail_badge_count():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _IconRail
    rail = _IconRail()
    items = [IconRailItem(i + 1, "X", "idle", "t", f"id{i}") for i in range(3)]
    rail.refresh(items)
    assert rail.badge_count() == 3


def test_icon_rail_empty_shows_zero():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import _IconRail
    rail = _IconRail()
    rail.refresh([])
    assert rail.badge_count() == 0


def test_icon_rail_item_clicked_forwarded():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem, _IconRail
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    rail = _IconRail()
    items = [IconRailItem(1, "A", "done", "tip", "my-id")]
    rail.refresh(items)
    got = []
    rail.item_clicked.connect(got.append)
    # 找到 badge 并点击
    from drama_shot_master.ui.widgets.collapsible_task_bar import _RailBadge
    badges = rail.findChildren(_RailBadge)
    assert len(badges) == 1
    QTest.mouseClick(badges[0], Qt.LeftButton)
    assert got == ["my-id"]


def test_icon_rail_expand_clicked_signal():
    _app()
    from drama_shot_master.ui.widgets.collapsible_task_bar import _IconRail
    rail = _IconRail()
    got = []
    rail.expand_clicked.connect(lambda: got.append(True))
    # 找展开按钮并点击
    btn = rail._expand_btn
    btn.click()
    assert got == [True]
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/test_collapsible_task_bar.py::test_icon_rail_badge_count tests/test_ui/test_collapsible_task_bar.py::test_icon_rail_empty_shows_zero -v
```

预期：FAIL — `ImportError: cannot import name '_IconRail'`

- [ ] **Step 3: 在 collapsible_task_bar.py 末尾追加 _IconRail 类**

在 `drama_shot_master/ui/widgets/collapsible_task_bar.py` 末尾（`_RailBadge` 类定义后）追加：

```python

# ── _IconRail ──────────────────────────────────────────────────────────────

class _IconRail(QWidget):
    """固定 40px 宽的图标轨：顶部 ▶ 展开按钮 + 下方徽章列表。"""

    expand_clicked = Signal()
    item_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(40)
        self._badges: list[_RailBadge] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        # 顶部展开按钮
        self._expand_btn = QPushButton("▶")
        self._expand_btn.setFixedSize(40, 28)
        self._expand_btn.setToolTip("展开任务栏")
        self._expand_btn.setObjectName("iconRailExpandBtn")
        self._expand_btn.clicked.connect(self.expand_clicked)
        layout.addWidget(self._expand_btn)

        # 徽章滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll = scroll

        container = QWidget()
        self._badge_layout = QVBoxLayout(container)
        self._badge_layout.setContentsMargins(0, 2, 0, 2)
        self._badge_layout.setSpacing(0)
        self._badge_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

    def refresh(self, items: list[IconRailItem]) -> None:
        """用新数据重建徽章列表。"""
        # 清掉旧徽章（stretch 留着）
        for badge in self._badges:
            self._badge_layout.removeWidget(badge)
            badge.deleteLater()
        self._badges.clear()

        for item in items:
            badge = _RailBadge(item)
            badge.clicked.connect(self.item_clicked)
            # 插到 stretch 之前
            self._badge_layout.insertWidget(
                self._badge_layout.count() - 1, badge)
            self._badges.append(badge)

    def badge_count(self) -> int:
        return len(self._badges)
```

- [ ] **Step 4: 运行测试，确认 PASS**

```bash
python -m pytest tests/test_ui/test_collapsible_task_bar.py::test_icon_rail_badge_count tests/test_ui/test_collapsible_task_bar.py::test_icon_rail_empty_shows_zero tests/test_ui/test_collapsible_task_bar.py::test_icon_rail_item_clicked_forwarded tests/test_ui/test_collapsible_task_bar.py::test_icon_rail_expand_clicked_signal -v
```

预期：4 PASS

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/collapsible_task_bar.py tests/test_ui/test_collapsible_task_bar.py
git commit -m "feat(ui): _IconRail widget (expand btn + badge scroll list)"
```

---

## Task 4: CollapsibleTaskBar 核心

**Files:**
- Modify: `drama_shot_master/ui/widgets/collapsible_task_bar.py`
- Modify: `tests/test_ui/test_collapsible_task_bar.py`

- [ ] **Step 1: 在测试文件末尾追加 CollapsibleTaskBar 失败测试**

在 `tests/test_ui/test_collapsible_task_bar.py` 末尾追加：

```python
# ── Task 4: CollapsibleTaskBar ────────────────────────────────────────────

class _StubManager(QWidget):
    """最小桩：实现 icon_rail_items() 协议，无需 MagicMock。"""
    from PySide6.QtCore import Signal as _Signal
    icon_rail_updated = _Signal()

    def icon_rail_items(self):
        return []


def test_collapse_changes_splitter_sizes():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0, expanded_width=280)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    bar.collapse()
    assert splitter.sizes()[0] == 40


def test_expand_restores_width():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0, expanded_width=280)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    bar.collapse()
    bar.expand()
    assert splitter.sizes()[0] == 280


def test_is_collapsed_state():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    assert bar.is_collapsed() is False
    bar.collapse()
    assert bar.is_collapsed() is True
    bar.expand()
    assert bar.is_collapsed() is False


def test_collapse_emits_signal():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    got = []
    bar.collapsed.connect(lambda: got.append("collapsed"))
    bar.expanded.connect(lambda: got.append("expanded"))
    bar.collapse()
    bar.expand()
    assert got == ["collapsed", "expanded"]


def test_toggle_switches_state():
    _app()
    from PySide6.QtWidgets import QSplitter, QWidget
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    stub = _StubManager()
    right = QWidget()
    splitter = QSplitter()
    bar = CollapsibleTaskBar(stub, splitter, manager_index=0)
    splitter.addWidget(bar)
    splitter.addWidget(right)
    splitter.resize(800, 600)
    splitter.setSizes([280, 520])
    assert not bar.is_collapsed()
    bar.toggle()
    assert bar.is_collapsed()
    bar.toggle()
    assert not bar.is_collapsed()
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/test_collapsible_task_bar.py::test_collapse_changes_splitter_sizes tests/test_ui/test_collapsible_task_bar.py::test_is_collapsed_state -v
```

预期：FAIL — `ImportError: cannot import name 'CollapsibleTaskBar'`

- [ ] **Step 3: 在 collapsible_task_bar.py 末尾追加 CollapsibleTaskBar 类**

在 `drama_shot_master/ui/widgets/collapsible_task_bar.py` 末尾（`_IconRail` 类定义后）追加：

```python

# ── CollapsibleTaskBar ─────────────────────────────────────────────────────

class CollapsibleTaskBar(QWidget):
    """包裹任意 task manager，提供折叠/展开能力。

    使用方式：
        bar = CollapsibleTaskBar(manager_widget, splitter, manager_index=0)
        splitter.addWidget(bar)   # 替换原来直接插入 manager 的位置
    """

    collapsed = Signal()
    expanded = Signal()

    def __init__(self, manager: QWidget, splitter: QSplitter,
                 manager_index: int = 0,
                 expanded_width: int = 280,
                 collapsed_width: int = 40,
                 parent=None):
        super().__init__(parent)
        self._manager = manager
        self._splitter = splitter
        self._manager_index = manager_index
        self._expanded_width = expanded_width
        self._collapsed_width = collapsed_width
        self._is_collapsed = False

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()

        # page 0: 展开视图 —— manager + 右上角悬浮折叠按钮
        expanded_page = QWidget()
        ep_layout = QVBoxLayout(expanded_page)
        ep_layout.setContentsMargins(0, 0, 0, 0)
        ep_layout.setSpacing(0)
        ep_layout.addWidget(self._manager)

        # 折叠按钮：绝对定位浮在展开页右上角
        self._collapse_btn = QPushButton("◀")
        self._collapse_btn.setParent(expanded_page)
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setObjectName("taskBarCollapseBtn")
        self._collapse_btn.setToolTip("折叠任务栏")
        self._collapse_btn.clicked.connect(self.collapse)

        # page 1: 折叠视图 —— 图标轨
        self._icon_rail = _IconRail()
        self._icon_rail.expand_clicked.connect(self.expand)

        self._stack.addWidget(expanded_page)   # index 0
        self._stack.addWidget(self._icon_rail) # index 1
        root.addWidget(self._stack)

        # 展开页 resizeEvent 重定位折叠按钮
        expanded_page.resizeEvent = self._on_expanded_page_resize

    def _on_expanded_page_resize(self, event):
        """把折叠按钮定位在展开页右上角。"""
        w = event.size().width()
        self._collapse_btn.move(w - self._collapse_btn.width() - 2, 4)
        self._collapse_btn.raise_()

    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def collapse(self) -> None:
        if self._is_collapsed:
            return
        sizes = self._splitter.sizes()
        if sizes and self._manager_index < len(sizes):
            self._expanded_width = sizes[self._manager_index]
        self._icon_rail.refresh(self._manager.icon_rail_items())
        self._stack.setCurrentIndex(1)
        sizes = self._splitter.sizes()
        if sizes and self._manager_index < len(sizes):
            sizes[self._manager_index] = self._collapsed_width
            self._splitter.setSizes(sizes)
        self.setMinimumWidth(self._collapsed_width)
        self.setMaximumWidth(self._collapsed_width)
        self._is_collapsed = True
        self.collapsed.emit()

    def expand(self) -> None:
        if not self._is_collapsed:
            return
        self._stack.setCurrentIndex(0)
        sizes = self._splitter.sizes()
        if sizes and self._manager_index < len(sizes):
            sizes[self._manager_index] = self._expanded_width
            self._splitter.setSizes(sizes)
        self.setMinimumWidth(40)
        self.setMaximumWidth(16777215)
        self._is_collapsed = False
        self.expanded.emit()

    def toggle(self) -> None:
        if self._is_collapsed:
            self.expand()
        else:
            self.collapse()
```

- [ ] **Step 4: 运行所有 CollapsibleTaskBar 测试**

```bash
python -m pytest tests/test_ui/test_collapsible_task_bar.py -v
```

预期：全部 PASS（Task 2+3+4 的测试，共 12+ 个）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/collapsible_task_bar.py tests/test_ui/test_collapsible_task_bar.py
git commit -m "feat(ui): CollapsibleTaskBar core (collapse/expand/toggle)"
```

---

## Task 5: ScreenwriterTaskManager.icon_rail_items() + select_by_id()

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/task_manager.py`
- Modify: `tests/test_ui/screenwriter/test_task_manager.py`

- [ ] **Step 1: 在测试文件末尾追加失败测试**

在 `tests/test_ui/screenwriter/test_task_manager.py` 末尾追加：

```python
def test_icon_rail_items_returns_correct_count(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    tm = ScreenwriterTaskManager(cfg)
    items = tm.icon_rail_items()
    assert len(items) == 2
    assert items[0].index == 1 and items[1].index == 2


def test_icon_rail_items_status_running_when_worker_active(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    tm.set_active_worker_query(lambda p: True)   # 全部标记为 running
    items = tm.icon_rail_items()
    assert items[0].status == "running"


def test_select_by_id_selects_row(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    tm = ScreenwriterTaskManager(cfg)
    tm.select_by_id(str(pB))
    assert tm._table.currentRow() == 1


def test_icon_rail_updated_emits_on_refresh(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    got = []
    tm.icon_rail_updated.connect(lambda: got.append(True))
    tm.refresh()
    assert got  # 至少 emit 一次
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/screenwriter/test_task_manager.py::test_icon_rail_items_returns_correct_count tests/test_ui/screenwriter/test_task_manager.py::test_select_by_id_selects_row -v
```

预期：FAIL — `AttributeError: 'ScreenwriterTaskManager' object has no attribute 'icon_rail_items'`

- [ ] **Step 3: 修改 task_manager.py，加 signal + icon_rail_items() + select_by_id()**

在 `drama_shot_master/ui/widgets/screenwriter/task_manager.py` 的 `ScreenwriterTaskManager` 类里：

**3a. 在类属性区（`taskSelected = Signal(...)` 等三行之后）追加：**

```python
    icon_rail_updated = Signal()   # refresh() 末尾 emit，供 CollapsibleTaskBar 刷新图标轨
```

**3b. 在 `refresh()` 方法的最后一行（`self._fit_name_col()` 之后）追加：**

```python
        self.icon_rail_updated.emit()
```

**3c. 在 `_on_selection_changed()` 方法之后（类末尾）追加两个方法：**

```python
    def icon_rail_items(self):
        """返回当前项目列表的图标轨数据，供 CollapsibleTaskBar 渲染折叠视图。"""
        from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem
        items = []
        for i, p in enumerate(self._projects):
            dots, stage = self._compute_status(p)
            if self._active_worker_query(p):
                status = "running"
            elif "✗" in dots:
                status = "error"
            elif dots.replace("✓", "").replace(" ", "") == "":
                status = "done"
            else:
                status = "idle"
            items.append(IconRailItem(
                index=i + 1,
                label=p.name[:2],
                status=status,
                tooltip=f"{p.name}\n当前阶段: {stage}",
                item_id=str(p),
            ))
        return items

    def select_by_id(self, item_id: str) -> None:
        """图标轨点击时调用，按 item_id（路径字符串）选中对应行。"""
        from pathlib import Path
        try:
            p = Path(item_id)
            idx = self._projects.index(p)
            self._table.selectRow(idx)
        except (ValueError, OSError):
            pass
```

- [ ] **Step 4: 运行测试，确认 PASS**

```bash
python -m pytest tests/test_ui/screenwriter/test_task_manager.py -v
```

预期：全部 PASS（原有用例 + 新增 4 个）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/task_manager.py tests/test_ui/screenwriter/test_task_manager.py
git commit -m "feat(screenwriter): icon_rail_items() + select_by_id() + icon_rail_updated signal"
```

---

## Task 6: ImgGenTaskManagerPanel.icon_rail_items() + select_by_id()

**Files:**
- Modify: `drama_shot_master/ui/panels/imggen_task_manager_panel.py`
- Create: `tests/test_ui/test_imggen_task_manager_icon_rail_smoke.py`

- [ ] **Step 1: 新建测试文件，写失败测试**

新建 `tests/test_ui/test_imggen_task_manager_icon_rail_smoke.py`，内容：

```python
"""ImgGenTaskManagerPanel icon_rail 接口冒烟测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from unittest.mock import MagicMock


def _app():
    return QApplication.instance() or QApplication([])


def _make_panel():
    """用 __new__ + 手动注入桩跳过完整 __init__。"""
    from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
    panel = ImgGenTaskManagerPanel.__new__(ImgGenTaskManagerPanel)
    store = MagicMock()
    store.all.return_value = []
    panel.store = store
    panel._live_status = {}
    return panel


def test_imggen_icon_rail_items_empty():
    _app()
    panel = _make_panel()
    items = panel.icon_rail_items()
    assert items == []


def test_imggen_icon_rail_items_count():
    _app()
    from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
    panel = ImgGenTaskManagerPanel.__new__(ImgGenTaskManagerPanel)
    task_a = MagicMock(); task_a.id = "a"; task_a.name = "任务A"
    task_b = MagicMock(); task_b.id = "b"; task_b.name = "任务B"
    store = MagicMock(); store.all.return_value = [task_a, task_b]
    panel.store = store
    panel._live_status = {"a": "已完成"}
    items = panel.icon_rail_items()
    assert len(items) == 2
    assert items[0].index == 1 and items[1].index == 2
    assert items[0].status == "done"


def test_imggen_icon_rail_items_running_status():
    _app()
    from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
    panel = ImgGenTaskManagerPanel.__new__(ImgGenTaskManagerPanel)
    task = MagicMock(); task.id = "x"; task.name = "X"
    store = MagicMock(); store.all.return_value = [task]
    panel.store = store
    panel._live_status = {"x": "生成中"}
    items = panel.icon_rail_items()
    assert items[0].status == "running"
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/test_imggen_task_manager_icon_rail_smoke.py -v
```

预期：FAIL — `AttributeError: 'ImgGenTaskManagerPanel' object has no attribute 'icon_rail_items'`

- [ ] **Step 3: 修改 imggen_task_manager_panel.py**

**3a. 在类的 Signal 声明区（`taskRenamed = Signal(...)` 等三行之后）追加：**

```python
    icon_rail_updated = Signal()
```

**3b. 在 `refresh()` 方法末尾（`self._fit_name_col()` 之后）追加：**

```python
        self.icon_rail_updated.emit()
```

**3c. 在 `_del()` 方法之后（类末尾）追加两个方法：**

```python
    def icon_rail_items(self):
        """返回当前任务列表的图标轨数据。"""
        from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem
        tasks = self.store.all()
        items = []
        for i, t in enumerate(tasks):
            raw = self._live_status.get(t.id, "—")
            if raw in ("生成中", "running", "●"):
                status = "running"
            elif raw in ("已完成", "done", "✓"):
                status = "done"
            elif "失败" in raw or "error" in raw.lower():
                status = "error"
            else:
                status = "idle"
            items.append(IconRailItem(
                index=i + 1,
                label=t.name[:2],
                status=status,
                tooltip=f"{t.name}\n状态: {raw}",
                item_id=t.id,
            ))
        return items

    def select_by_id(self, item_id: str) -> None:
        """图标轨点击时调用，按 task_id 选中对应行。"""
        self._select_task(item_id)
```

- [ ] **Step 4: 运行测试，确认 PASS**

```bash
python -m pytest tests/test_ui/test_imggen_task_manager_icon_rail_smoke.py -v
```

预期：4 PASS

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/imggen_task_manager_panel.py tests/test_ui/test_imggen_task_manager_icon_rail_smoke.py
git commit -m "feat(imggen): icon_rail_items() + select_by_id() + icon_rail_updated signal"
```

---

## Task 7: VideoTaskManagerPanel.icon_rail_items() + select_by_id()

**Files:**
- Modify: `drama_shot_master/ui/panels/video_task_manager_panel.py`
- Create: `tests/test_ui/test_video_task_manager_icon_rail_smoke.py`

- [ ] **Step 1: 新建测试文件，写失败测试**

新建 `tests/test_ui/test_video_task_manager_icon_rail_smoke.py`，内容：

```python
"""VideoTaskManagerPanel icon_rail 接口冒烟测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from unittest.mock import MagicMock


def _app():
    return QApplication.instance() or QApplication([])


def test_video_icon_rail_items_empty():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    store = MagicMock(); store.all.return_value = []
    panel.store = store
    panel._live_status = {}
    items = panel.icon_rail_items()
    assert items == []


def test_video_icon_rail_items_count():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    task_a = MagicMock(); task_a.id = "a"; task_a.name = "视频A"
    task_b = MagicMock(); task_b.id = "b"; task_b.name = "视频B"
    store = MagicMock(); store.all.return_value = [task_a, task_b]
    panel.store = store
    panel._live_status = {}
    items = panel.icon_rail_items()
    assert len(items) == 2
    assert items[0].index == 1 and items[1].index == 2


def test_video_icon_rail_items_running_status():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    task = MagicMock(); task.id = "x"; task.name = "X"
    store = MagicMock(); store.all.return_value = [task]
    panel.store = store
    panel._live_status = {"x": "生成中"}
    items = panel.icon_rail_items()
    assert items[0].status == "running"


def test_video_icon_rail_items_error_status():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    panel = VideoTaskManagerPanel.__new__(VideoTaskManagerPanel)
    task = MagicMock(); task.id = "x"; task.name = "X"
    store = MagicMock(); store.all.return_value = [task]
    panel.store = store
    panel._live_status = {"x": "失败"}
    items = panel.icon_rail_items()
    assert items[0].status == "error"
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/test_video_task_manager_icon_rail_smoke.py -v
```

预期：FAIL — `AttributeError: 'VideoTaskManagerPanel' object has no attribute 'icon_rail_items'`

- [ ] **Step 3: 修改 video_task_manager_panel.py**

**3a. 在类的 Signal 声明区（`taskDeleted = Signal(str)` 之后）追加：**

```python
    icon_rail_updated = Signal()
```

**3b. 在 `refresh()` 方法末尾（`self._fit_name_col()` 之后）追加：**

```python
        self.icon_rail_updated.emit()
```

**3c. 在 `_on_item_changed()` 方法之后（类末尾）追加两个方法：**

```python
    def icon_rail_items(self):
        """返回当前任务列表的图标轨数据。"""
        from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem
        tasks = self.store.all()
        items = []
        for i, t in enumerate(tasks):
            raw = self._live_status.get(t.id, "空闲")
            if raw in ("生成中", "running"):
                status = "running"
            elif raw in ("已完成", "done"):
                status = "done"
            elif "失败" in raw or "error" in raw.lower():
                status = "error"
            else:
                status = "idle"
            items.append(IconRailItem(
                index=i + 1,
                label=t.name[:2],
                status=status,
                tooltip=f"{t.name}\n状态: {raw}",
                item_id=t.id,
            ))
        return items

    def select_by_id(self, item_id: str) -> None:
        """图标轨点击时调用，按 task_id 选中对应行。"""
        self._select_task(item_id)
```

- [ ] **Step 4: 运行测试，确认 PASS**

```bash
python -m pytest tests/test_ui/test_video_task_manager_icon_rail_smoke.py -v
```

预期：4 PASS

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/video_task_manager_panel.py tests/test_ui/test_video_task_manager_icon_rail_smoke.py
git commit -m "feat(video): icon_rail_items() + select_by_id() + icon_rail_updated signal"
```

---

## Task 8: DubTaskManagerPanel.icon_rail_items() + select_by_id()

**Files:**
- Modify: `drama_shot_master/ui/panels/dub_task_manager_panel.py`
- Create: `tests/test_ui/test_dub_task_manager_icon_rail_smoke.py`

- [ ] **Step 1: 新建测试文件，写失败测试**

新建 `tests/test_ui/test_dub_task_manager_icon_rail_smoke.py`，内容：

```python
"""DubTaskManagerPanel icon_rail 接口冒烟测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from unittest.mock import MagicMock


def _app():
    return QApplication.instance() or QApplication([])


def test_dub_icon_rail_items_empty():
    _app()
    from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
    panel = DubTaskManagerPanel.__new__(DubTaskManagerPanel)
    store = MagicMock(); store.all.return_value = []
    panel.store = store
    panel._live_status = {}
    items = panel.icon_rail_items()
    assert items == []


def test_dub_icon_rail_items_count():
    _app()
    from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
    panel = DubTaskManagerPanel.__new__(DubTaskManagerPanel)
    task_a = MagicMock(); task_a.id = "a"; task_a.name = "配音A"
    task_b = MagicMock(); task_b.id = "b"; task_b.name = "配音B"
    store = MagicMock(); store.all.return_value = [task_a, task_b]
    panel.store = store
    panel._live_status = {}
    items = panel.icon_rail_items()
    assert len(items) == 2
    assert items[0].index == 1 and items[1].index == 2


def test_dub_icon_rail_items_running_status():
    _app()
    from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
    panel = DubTaskManagerPanel.__new__(DubTaskManagerPanel)
    task = MagicMock(); task.id = "x"; task.name = "X"
    store = MagicMock(); store.all.return_value = [task]
    panel.store = store
    panel._live_status = {"x": "生成中"}
    items = panel.icon_rail_items()
    assert items[0].status == "running"


def test_dub_icon_rail_items_error_status():
    _app()
    from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
    panel = DubTaskManagerPanel.__new__(DubTaskManagerPanel)
    task = MagicMock(); task.id = "x"; task.name = "X"
    store = MagicMock(); store.all.return_value = [task]
    panel.store = store
    panel._live_status = {"x": "失败"}
    items = panel.icon_rail_items()
    assert items[0].status == "error"
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/test_dub_task_manager_icon_rail_smoke.py -v
```

预期：FAIL — `AttributeError: 'DubTaskManagerPanel' object has no attribute 'icon_rail_items'`

- [ ] **Step 3: 修改 dub_task_manager_panel.py**

**3a. 在类的 Signal 声明区（`taskDeleted = Signal(str, str)` 等三行之后）追加：**

```python
    icon_rail_updated = Signal()
```

**3b. 在 `refresh()` 方法末尾（`self._fit_name_col()` 之后）追加：**

```python
        self.icon_rail_updated.emit()
```

**3c. 在 `_del()` 方法之后（类末尾）追加两个方法：**

```python
    def icon_rail_items(self):
        """返回当前任务列表的图标轨数据。"""
        from drama_shot_master.ui.widgets.collapsible_task_bar import IconRailItem
        tasks = self.store.all()
        items = []
        for i, t in enumerate(tasks):
            raw = self._live_status.get(t.id, "—")
            if raw in ("生成中", "running", "●"):
                status = "running"
            elif raw in ("已完成", "done", "✓"):
                status = "done"
            elif "失败" in raw or "error" in raw.lower():
                status = "error"
            else:
                status = "idle"
            items.append(IconRailItem(
                index=i + 1,
                label=t.name[:2],
                status=status,
                tooltip=f"{t.name}\n状态: {raw}",
                item_id=t.id,
            ))
        return items

    def select_by_id(self, item_id: str) -> None:
        """图标轨点击时调用，按 task_id 选中对应行。"""
        self._select_task(item_id)
```

- [ ] **Step 4: 运行测试，确认 PASS**

```bash
python -m pytest tests/test_ui/test_dub_task_manager_icon_rail_smoke.py -v
```

预期：4 PASS

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/dub_task_manager_panel.py tests/test_ui/test_dub_task_manager_icon_rail_smoke.py
git commit -m "feat(dub): icon_rail_items() + select_by_id() + icon_rail_updated signal"
```

---

## Task 9: 接入 TaskWorkspacePage

**Files:**
- Modify: `drama_shot_master/ui/pages/task_workspace_page.py`
- Modify: `tests/test_ui/test_task_workspace_page_smoke.py`

- [ ] **Step 1: 在测试文件末尾追加失败测试**

在 `tests/test_ui/test_task_workspace_page_smoke.py` 末尾追加：

```python
def test_task_workspace_has_collapsible_bar():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar

    class _ManagerWithRail(_FakeManager):
        from PySide6.QtCore import Signal as _Signal
        icon_rail_updated = _Signal()
        def icon_rail_items(self): return []

    mgr = _ManagerWithRail()
    page = TaskWorkspacePage(
        manager=mgr,
        editor_factory=lambda task: _FakeEditor(),
        wire_editor=lambda ed, task: None,
        payload_of=lambda ed: ed.payload,
        on_persist=lambda tid, p: None,
        title_for=lambda task: f"任务 · {task.name}",
    )
    assert hasattr(page, "_task_bar")
    assert isinstance(page._task_bar, CollapsibleTaskBar)
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/test_task_workspace_page_smoke.py::test_task_workspace_has_collapsible_bar -v
```

预期：FAIL — `AttributeError: 'TaskWorkspacePage' object has no attribute '_task_bar'`

- [ ] **Step 3: 修改 task_workspace_page.py 的 _build_ui 方法**

在 `drama_shot_master/ui/pages/task_workspace_page.py` 的 `_build_ui` 方法里，找到：

```python
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.manager)
        # 任务列表宽度区间锁定：详情编辑器再宽也不能挤占它，避免最右"状态"列被裁
        self.manager.setMinimumWidth(290)
        self.manager.setMaximumWidth(300)
```

替换为：

```python
        splitter = QSplitter(Qt.Horizontal)
        # 用 CollapsibleTaskBar 包裹 manager，提供折叠/展开能力
        from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
        self._task_bar = CollapsibleTaskBar(
            self.manager, splitter, manager_index=0, expanded_width=290)
        self._task_bar.setMinimumWidth(40)
        splitter.addWidget(self._task_bar)
        # 连接 icon_rail_updated → 刷新图标轨
        if hasattr(self.manager, "icon_rail_updated"):
            self.manager.icon_rail_updated.connect(
                lambda: self._task_bar._icon_rail.refresh(
                    self.manager.icon_rail_items()))
        # 连接图标轨点击 → select_by_id
        self._task_bar._icon_rail.item_clicked.connect(
            lambda iid: self.manager.select_by_id(iid)
            if hasattr(self.manager, "select_by_id") else None)
```

- [ ] **Step 4: 运行所有 task_workspace 测试**

```bash
python -m pytest tests/test_ui/test_task_workspace_page_smoke.py -v
```

预期：全部 PASS（原有 8 个 + 新增 1 个）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/pages/task_workspace_page.py tests/test_ui/test_task_workspace_page_smoke.py
git commit -m "feat(ui): wire CollapsibleTaskBar into TaskWorkspacePage"
```

---

## Task 10: 接入 ScreenwriterPanel

**Files:**
- Modify: `drama_shot_master/ui/panels/screenwriter_panel.py`
- Modify: `tests/test_ui/screenwriter/test_screenwriter_panel.py`

- [ ] **Step 1: 在测试文件末尾追加失败测试**

在 `tests/test_ui/screenwriter/test_screenwriter_panel.py` 末尾追加：

```python
def test_screenwriter_panel_has_collapsible_bar():
    _app()
    from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel
    from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
    panel = ScreenwriterPanel(_StubCfg())
    assert hasattr(panel, "_task_bar")
    assert isinstance(panel._task_bar, CollapsibleTaskBar)


def test_screenwriter_task_bar_wraps_task_manager():
    _app()
    from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel
    panel = ScreenwriterPanel(_StubCfg())
    # _task_bar 内嵌的 manager 就是 _task_manager
    assert panel._task_bar._manager is panel._task_manager
```

- [ ] **Step 2: 运行测试，确认 FAIL**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py::test_screenwriter_panel_has_collapsible_bar tests/test_ui/screenwriter/test_screenwriter_panel.py::test_screenwriter_task_bar_wraps_task_manager -v
```

预期：FAIL — `AttributeError: 'ScreenwriterPanel' object has no attribute '_task_bar'`

- [ ] **Step 3: 修改 screenwriter_panel.py 的 _build_ui 方法**

在 `drama_shot_master/ui/panels/screenwriter_panel.py` 的 `_build_ui` 方法里，找到：

```python
        # 左
        self._task_manager = ScreenwriterTaskManager(self._cfg)
        self._task_manager.setMaximumWidth(300)
        self._task_manager.setMinimumWidth(220)
        splitter.addWidget(self._task_manager)
```

替换为：

```python
        # 左（用 CollapsibleTaskBar 包裹任务管理器）
        from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
        self._task_manager = ScreenwriterTaskManager(self._cfg)
        self._task_bar = CollapsibleTaskBar(
            self._task_manager, splitter, manager_index=0, expanded_width=280)
        self._task_bar.setMinimumWidth(40)
        splitter.addWidget(self._task_bar)
        # 连接 icon_rail_updated → 刷新图标轨
        self._task_manager.icon_rail_updated.connect(
            lambda: self._task_bar._icon_rail.refresh(
                self._task_manager.icon_rail_items()))
        # 连接图标轨点击 → select_by_id
        self._task_bar._icon_rail.item_clicked.connect(
            self._task_manager.select_by_id)
```

- [ ] **Step 4: 运行所有 screenwriter panel 测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py -v
```

预期：全部 PASS（原有 3 个 + 新增 2 个）

- [ ] **Step 5: 回归跑全量 test_ui 测试**

```bash
python -m pytest tests/test_ui/ -v --tb=short 2>&1 | tail -30
```

预期：所有用例 PASS，无回归失败

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/panels/screenwriter_panel.py tests/test_ui/screenwriter/test_screenwriter_panel.py
git commit -m "feat(screenwriter): wire CollapsibleTaskBar into ScreenwriterPanel"
```

---

## Task 11: 全量回归 + 状态持久化验收

**Files:**
- 无新文件，验证已有实现

- [ ] **Step 1: 跑全量测试套件**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -50
```

预期：所有测试 PASS（含原有 235+ 个 + 新增约 30 个）

- [ ] **Step 2: 验证 config 字段被 task bar 读写**

验证 CollapsibleTaskBar 在初始化时可以从 cfg.task_bar_collapsed 读取初始折叠状态。

注意：当前实现没有自动持久化钩子——CollapsibleTaskBar 本身不持有 cfg 引用。调用方（TaskWorkspacePage / ScreenwriterPanel）负责在 `collapsed` / `expanded` 信号触发时调用 `cfg.update_settings(task_bar_collapsed={...})`。

检查 spec 第 5 节（状态持久化），确认当前计划符合 `task_bar_collapsed` dict 键名规范：

```
{"screenwriter": false, "imggen": false, "video": false, "dub": false, "soundtrack": false}
```

若需要在 TaskWorkspacePage / ScreenwriterPanel 内增加持久化连接，追加以下改动（超出本期最小可交付范围，可选做）：

**TaskWorkspacePage 可选持久化（不影响测试通过）：** 在 `_build_ui` 内，若 manager 持有 `panel_key` 属性，可接：

```python
# 可选：折叠状态持久化（调用方按需传入 cfg + panel_key）
# bar.collapsed.connect(lambda: cfg.update_settings(task_bar_collapsed={panel_key: True}))
# bar.expanded.connect(lambda: cfg.update_settings(task_bar_collapsed={panel_key: False}))
```

本计划以「17 个核心用例全绿 + 原有零回归」为验收标准，持久化连接为可选后续。

- [ ] **Step 3: 最终 commit（如有遗漏文件）**

```bash
git status
# 确认 working tree clean；如有未提交文件则追加 commit
```

---

## 验收清单

全部 tasks 完成后，检查以下每一项：

- [ ] `drama_shot_master/ui/widgets/collapsible_task_bar.py` 存在，含 `IconRailItem`、`_RailBadge`、`_IconRail`、`CollapsibleTaskBar` 四个公开符号
- [ ] `tests/test_ui/test_collapsible_task_bar.py` 存在，pytest 全绿
- [ ] `drama_shot_master/config.py` 含 `task_bar_collapsed: dict` 字段，roundtrip 测试通过
- [ ] `ScreenwriterTaskManager` 有 `icon_rail_updated`、`icon_rail_items()`、`select_by_id()`
- [ ] `ImgGenTaskManagerPanel` 有同上三项
- [ ] `VideoTaskManagerPanel` 有同上三项
- [ ] `DubTaskManagerPanel` 有同上三项
- [ ] `TaskWorkspacePage` 的 `_build_ui` 创建 `self._task_bar: CollapsibleTaskBar`
- [ ] `ScreenwriterPanel` 的 `_build_ui` 创建 `self._task_bar: CollapsibleTaskBar`
- [ ] `python -m pytest tests/ -v --tb=short` 全绿，无回归
