# 外壳改用原生 PySide6 + QSS（去 qfluentwidgets）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 GUI 外壳从 qfluentwidgets（GPLv3）换成原生 PySide6（LGPLv3）+ QSS，使代码库零 GPL 依赖、可商用；UX 不变。

**Architecture:** `AppShell` 基类 `FluentWindow→QMainWindow`，中央 = `QVBoxLayout[ProjectCommandBar; QHBoxLayout[FlowSidebar | QStackedWidget]]`；新增原生 `FlowSidebar`（流程分组+可折叠图标条），导航/菜单/主题改用 `QToolButton`/`QMenu`/扩展版 `dark.qss`；AppShell 全部控制器逻辑（任务窗回调、stores、目录、restore/close、license）原样保留。

**Tech Stack:** PySide6 6.11（QtWidgets/QtSvg/QtGui）、QSS、pytest 9（offscreen Qt，无 pytest-qt）。

**Spec:** `docs/superpowers/specs/2026-05-27-gui-shell-stock-pyside6-design.md`

**验收硬指标：** `grep -rl qfluentwidgets drama_shot_master/ tests/` 为空（仅在最后 Task 8 达成）。

---

## 排序原则（每次提交保持测试绿）
现有 Fluent `AppShell._icon()` 用 `getattr(FluentIcon, ICONS[key], FluentIcon.TAG)`，所以把 `ICONS` 值改成 svg 文件名后它只会回退到 TAG 图标、不会崩——这让 nav_config 改动可先于 app_shell 重写完成。顺序：theme 工具 → 图标/nav_config → FlowSidebar → 命令栏控件 → QSS → app_shell 重写 → 拆 init_fluent_theme → 删 main_window/收尾。

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| Modify | `drama_shot_master/ui/theme.py` | 加 `_find_app_icon_path`/`apply_window_icon`；（Task7）删 `init_fluent_theme`/`THEME_ACCENT` |
| Create | `drama_shot_master/assets/icons/*.svg` | 9 个单色线性图标 |
| Modify | `drama_shot_master/ui/nav_config.py` | `ICONS` 值→svg 文件名；加 `ICON_SETTINGS`/`ICON_HELP`/`icon_path()` |
| Create | `drama_shot_master/ui/widgets/flow_sidebar.py` | 原生流程侧栏 `FlowSidebar`（可折叠） |
| Modify | `drama_shot_master/ui/widgets/project_command_bar.py` | 改纯 `QPushButton`，去 qfluentwidgets |
| Modify | `drama_shot_master/ui/styles/dark.qss` | 侧栏/命令栏/AccentButton/主题色 `#2563EB` |
| Modify | `drama_shot_master/ui/app_shell.py` | 基类→QMainWindow；重写 nav/命令栏装配/菜单/switchTo/图标；去 qfluentwidgets；控制器方法不动 |
| Modify | `drama_shot_master/main.py` | 删 `init_fluent_theme` import+调用 |
| Delete | `drama_shot_master/ui/main_window.py` | 旧横向按钮主窗 |
| Delete | `tests/test_ui/test_fluent_theme_smoke.py` | 主题改纯 QSS |
| Modify | `tests/test_ui/test_main_window_soundtrack_smoke.py` | `FUNCS` 改从 nav_config 导入；去 MainWindow 断言 |
| Create | `tests/test_ui/test_flow_sidebar_smoke.py` | FlowSidebar 单测 |
| Modify | `tests/test_ui/test_app_shell_smoke.py` | 适配 QMainWindow + 新断言 |
| Modify | `tests/test_ui/test_nav_config.py` | 加 icon_path / svg 存在断言 |

---

## Task 1: theme.py 新增 `apply_window_icon`（修复标题栏图标）

**Files:**
- Modify: `drama_shot_master/ui/theme.py`
- Test: `tests/test_ui/test_window_icon_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_window_icon_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMainWindow
from drama_shot_master.ui.theme import apply_window_icon, _find_app_icon_path


def _app():
    return QApplication.instance() or QApplication([])


def test_find_app_icon_path_exists():
    p = _find_app_icon_path()
    assert p is not None and p.exists()      # assets/app_icon.ico|png 存在


def test_apply_window_icon_sets_nonnull_icon():
    _app()
    w = QMainWindow()
    assert w.windowIcon().isNull()
    apply_window_icon(w)
    assert not w.windowIcon().isNull()       # 标题栏图标来源：窗口自身 icon
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master && python -m pytest tests/test_ui/test_window_icon_smoke.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_window_icon'`

- [ ] **Step 3: 改 theme.py**

把现有 `apply_app_icon` 里的找路径逻辑抽成函数，并新增 `apply_window_icon`。在 `apply_app_icon` 定义之前加：

```python
def _find_app_icon_path(name: str = "app_icon"):
    """在 assets/ 下按 .ico→.png→.svg 找图标，返回 Path 或 None。"""
    for ext in (".ico", ".png", ".svg"):
        p = _ASSET_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


def apply_window_icon(widget, name: str = "app_icon") -> None:
    """给窗口自身设图标——原生标题栏据此在软件名左侧显示 [图标]。

    仅设 QApplication 图标不足以保证标题栏内显示，故须对窗口显式设置。
    """
    p = _find_app_icon_path(name)
    if p:
        from PySide6.QtGui import QIcon
        widget.setWindowIcon(QIcon(str(p)))
```

并把 `apply_app_icon` 内部改为复用 `_find_app_icon_path`：

```python
def apply_app_icon(app, name: str = "app_icon") -> None:
    from PySide6.QtGui import QIcon
    p = _find_app_icon_path(name)
    if p:
        app.setWindowIcon(QIcon(str(p)))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/test_window_icon_smoke.py -q`
Expected: 2 passed（判据为 "N passed"；结果之后的 teardown 段错误是已知 WSL 伪影）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/theme.py tests/test_ui/test_window_icon_smoke.py
git commit -m "feat(ui): apply_window_icon —— 修复标题栏软件名旁不显示图标"
```

---

## Task 2: 自带 SVG 图标 + nav_config 接入

**Files:**
- Create: `drama_shot_master/assets/icons/{cut,photo,erase,palette,video,music,mic,settings,help}.svg`
- Modify: `drama_shot_master/ui/nav_config.py`
- Test: `tests/test_ui/test_nav_config.py`

- [ ] **Step 1: 写失败测试（追加到 test_nav_config.py）**

```python
def test_icons_are_svg_filenames():
    assert all(v.endswith(".svg") for v in ICONS.values())


def test_icon_path_resolves_existing_files():
    from drama_shot_master.ui.nav_config import icon_path, ICON_SETTINGS, ICON_HELP
    for key in ICONS:
        p = icon_path(ICONS[key])
        assert p is not None and p.exists(), f"missing icon for {key}"
    assert icon_path(ICON_SETTINGS).exists()
    assert icon_path(ICON_HELP).exists()
```
（顶部 import 行补上 `ICONS`，若尚未导入。）

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_nav_config.py -q`
Expected: FAIL — `ImportError`（`icon_path`/`ICON_SETTINGS` 不存在）或图标文件缺失

- [ ] **Step 3a: 建 9 个 SVG**（`drama_shot_master/assets/icons/`，全部 `stroke="#c8ccd4"` 中性灰、24×24）

`cut.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>
```
`photo.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="M21 17l-5-5L5 19"/></svg>
```
`erase.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16l8-8 6 6-6 6H8z"/><line x1="6" y1="20" x2="20" y2="20"/></svg>
```
`palette.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a9 9 0 100 18c1 0 1.5-.8 1.5-1.5 0-1 .5-1.5 1.5-1.5H17a4 4 0 004-4c0-3.9-4-8-9-8z"/><circle cx="7.5" cy="11" r="1"/><circle cx="11" cy="7.5" r="1"/><circle cx="15.5" cy="9" r="1"/></svg>
```
`video.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/></svg>
```
`music.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/></svg>
```
`mic.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0"/><line x1="12" y1="18" x2="12" y2="21"/></svg>
```
`settings.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/></svg>
```
`help.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c8ccd4" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 115 .5c0 1.5-2 2-2 3.5"/><circle cx="12" cy="16.5" r="0.6" fill="#c8ccd4" stroke="none"/></svg>
```

- [ ] **Step 3b: 改 nav_config.py**

把 `ICONS` 的值换成 svg 文件名，并新增常量与 helper（保持 Qt-free，仅用 pathlib）：

```python
from pathlib import Path

_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

ICONS = {
    "split": "cut.svg",
    "combine": "photo.svg",
    "trim": "erase.svg",
    "imggen": "palette.svg",
    "video_gen": "video.svg",
    "soundtrack": "music.svg",
    "dubbing": "mic.svg",
}
ICON_SETTINGS = "settings.svg"
ICON_HELP = "help.svg"


def icon_path(filename: str):
    """assets/icons/<filename> 的绝对 Path；缺失返回 None。"""
    p = _ICON_DIR / filename
    return p if p.exists() else None
```

- [ ] **Step 4: 跑测试确认通过（含旧 app_shell 不回归）**

Run: `python -m pytest tests/test_ui/test_nav_config.py tests/test_ui/test_app_shell_smoke.py -q`
Expected: PASS（nav_config 新断言绿；旧 Fluent app_shell `_icon` 回退到 TAG，不崩）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/assets/icons drama_shot_master/ui/nav_config.py tests/test_ui/test_nav_config.py
git commit -m "feat(ui): 自带 9 个 SVG 图标 + nav_config.icon_path（替代 FluentIcon）"
```

---

## Task 3: 原生 `FlowSidebar`（可折叠流程侧栏）

**Files:**
- Create: `drama_shot_master/ui/widgets/flow_sidebar.py`
- Test: `tests/test_ui/test_flow_sidebar_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_flow_sidebar_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar, COLLAPSED_W, EXPANDED_W
from drama_shot_master.ui.nav_config import FUNCS, PHASES


def _app():
    return QApplication.instance() or QApplication([])


def test_renders_all_functions_and_phase_headers():
    _app()
    sb = FlowSidebar()
    assert set(sb._buttons.keys()) == {k for _l, k in FUNCS}
    assert len(sb._phase_labels) == len(PHASES)


def test_clicking_item_emits_currentChanged_key():
    _app()
    sb = FlowSidebar()
    seen = []
    sb.currentChanged.connect(seen.append)
    sb._buttons["video_gen"].click()
    assert seen == ["video_gen"]


def test_set_active_checks_button():
    _app()
    sb = FlowSidebar()
    sb.set_active("trim")
    assert sb._buttons["trim"].isChecked()


def test_collapse_switches_icononly_and_width():
    _app()
    sb = FlowSidebar()
    assert sb.minimumWidth() == EXPANDED_W
    sb.set_collapsed(True)
    assert sb.is_collapsed
    assert sb._buttons["split"].toolButtonStyle() == Qt.ToolButtonIconOnly
    assert sb.minimumWidth() == COLLAPSED_W
    sb.set_collapsed(False)
    assert sb._buttons["split"].toolButtonStyle() == Qt.ToolButtonTextBesideIcon
    assert sb.minimumWidth() == EXPANDED_W


def test_settings_and_help_signals():
    _app()
    sb = FlowSidebar()
    s, h = [], []
    sb.settingsRequested.connect(lambda: s.append(1))
    sb.helpRequested.connect(lambda: h.append(1))
    sb.btn_settings.click(); sb.btn_help.click()
    assert s == [1] and h == [1]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_flow_sidebar_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError`（flow_sidebar_consts / flow_sidebar）

- [ ] **Step 3: 建 `drama_shot_master/ui/widgets/flow_sidebar.py`**（宽度常量内联在文件顶部）

```python
"""FlowSidebar：原生流程式侧栏（替换 qfluentwidgets NavigationInterface）。

按 nav_config.PHASES 渲染：阶段标题(非点击 QLabel) + 功能项(checkable QToolButton, 互斥)；
底部 设置/帮助 按钮。可折叠为纯图标条。发 currentChanged(key)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPropertyAnimation
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QToolButton, QButtonGroup, QFrame, QSizePolicy,
)

from drama_shot_master.ui import nav_config

EXPANDED_W = 184
COLLAPSED_W = 52


class FlowSidebar(QWidget):
    currentChanged = Signal(str)      # 功能 key
    settingsRequested = Signal()
    helpRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FlowSidebar")
        self._buttons: dict[str, QToolButton] = {}
        self._phase_labels: list[QLabel] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._collapsed = False
        self.setMinimumWidth(EXPANDED_W)
        self.setMaximumWidth(EXPANDED_W)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(2)

        self.btn_collapse = QToolButton()
        self.btn_collapse.setObjectName("navCollapse")
        self.btn_collapse.setText("≡")
        self.btn_collapse.clicked.connect(self.toggle_collapsed)
        lay.addWidget(self.btn_collapse)

        for phase_title, keys in nav_config.PHASES:
            lbl = QLabel(phase_title)
            lbl.setObjectName("navPhase")
            self._phase_labels.append(lbl)
            lay.addWidget(lbl)
            for key in keys:
                btn = self._make_item(nav_config.LABELS[key], nav_config.ICONS[key])
                btn.setCheckable(True)
                self._group.addButton(btn)
                self._buttons[key] = btn
                btn.clicked.connect(lambda _=False, k=key: self.currentChanged.emit(k))
                lay.addWidget(btn)

        lay.addStretch(1)
        sep = QFrame()
        sep.setObjectName("navSep")
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)
        self.btn_settings = self._make_item("设置", nav_config.ICON_SETTINGS)
        self.btn_settings.clicked.connect(self.settingsRequested)
        lay.addWidget(self.btn_settings)
        self.btn_help = self._make_item("帮助 / 关于", nav_config.ICON_HELP)
        self.btn_help.clicked.connect(self.helpRequested)
        lay.addWidget(self.btn_help)

    def _make_item(self, text: str, icon_filename: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        p = nav_config.icon_path(icon_filename)
        if p is not None:
            btn.setIcon(QIcon(str(p)))
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setToolTip(text)
        return btn

    def _menu_buttons(self):
        return [self.btn_settings, self.btn_help]

    def set_active(self, key: str):
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        style = Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon
        for b in list(self._buttons.values()) + self._menu_buttons():
            b.setToolButtonStyle(style)
        for lbl in self._phase_labels:
            lbl.setVisible(not collapsed)
        target = COLLAPSED_W if collapsed else EXPANDED_W
        # 末态确定（供布局/测试），动画仅作视觉过渡
        self._anim = QPropertyAnimation(self, b"maximumWidth", self)
        self._anim.setDuration(140)
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(target)
        self._anim.start()
        self.setMinimumWidth(target)
        self.setMaximumWidth(target)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed
```

> 说明：`set_collapsed` 末尾显式 `setMinimumWidth/ setMaximumWidth(target)` 让末态确定（测试断言 `minimumWidth()`）；`QPropertyAnimation` 仅在有事件循环时做视觉过渡，headless 下不影响断言。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/test_flow_sidebar_smoke.py -q`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/flow_sidebar.py tests/test_ui/test_flow_sidebar_smoke.py
git commit -m "feat(ui): 原生 FlowSidebar（流程分组+可折叠图标条），替换 NavigationInterface"
```

---

## Task 4: ProjectCommandBar 去 qfluentwidgets

**Files:**
- Modify: `drama_shot_master/ui/widgets/project_command_bar.py`
- Test: `tests/test_ui/test_app_shell_smoke.py`（命令栏相关断言已存在，复跑即可）

- [ ] **Step 1: 读现状**

`project_command_bar.py` 目前用 `try: from qfluentwidgets import PushButton except: from PySide6.QtWidgets import QPushButton as PushButton`（或类似）。确认按钮类引用名。

- [ ] **Step 2: 改为纯 QPushButton**

删除对 qfluentwidgets 的任何 import 与回退分支，直接：

```python
from PySide6.QtWidgets import QPushButton
```
并把 `self.btn_open_dir`/`self.btn_set_output` 的构造改用 `QPushButton(...)`。给两个按钮设 objectName 便于 QSS：`self.btn_open_dir.setObjectName("cmdOpenDir")`、`self.btn_set_output.setObjectName("cmdSetOutput")`。其余（标签/信号/方法 `set_dir`/`set_output`/`set_count`/`count_text`）不变。给根 widget `self.setObjectName("ProjectCommandBar")`（若尚未设）。

- [ ] **Step 3: 验证无 qfluentwidgets 残留 + 复跑命令栏测试**

Run:
```
grep -n qfluentwidgets drama_shot_master/ui/widgets/project_command_bar.py || echo "clean"
python -m pytest tests/test_ui/test_app_shell_smoke.py -q
```
Expected: 打印 `clean`；命令栏相关测试仍 PASS（旧 Fluent app_shell 仍能用 ProjectCommandBar，因为按钮 API 不变）

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/ui/widgets/project_command_bar.py
git commit -m "refactor(ui): ProjectCommandBar 改纯 QPushButton，去 qfluentwidgets"
```

---

## Task 5: 扩展 dark.qss（侧栏/命令栏/AccentButton/主题色）

**Files:**
- Modify: `drama_shot_master/ui/styles/dark.qss`

- [ ] **Step 1: 追加样式到 dark.qss 末尾**

```css
/* ===== 原生外壳：流程侧栏 ===== */
#FlowSidebar { background: #16171a; border-right: 1px solid #24262b; }
QLabel#navPhase {
    color: #7d828c; font-size: 11px; letter-spacing: 1px;
    padding: 8px 10px 2px 10px;
}
#FlowSidebar QToolButton {
    color: #d4d8df; background: transparent; border: none;
    border-radius: 6px; padding: 7px 10px; text-align: left;
}
#FlowSidebar QToolButton:hover { background: #20232a; }
#FlowSidebar QToolButton:checked,
#FlowSidebar QToolButton[selected="true"] {
    background: #1d2a36; color: #ffffff;
    border-left: 3px solid #2563EB;
}
QToolButton#navCollapse { color: #9aa0a6; font-size: 16px; padding: 4px 8px; }
QFrame#navSep { color: #24262b; }

/* ===== 顶部命令栏 ===== */
#ProjectCommandBar { background: #1b1d22; border-bottom: 1px solid #24262b; }
#ProjectCommandBar QLabel { color: #b9bdc6; }
#ProjectCommandBar QPushButton {
    color: #e6e9ee; background: #2a2d34; border: 1px solid #353941;
    border-radius: 6px; padding: 5px 12px;
}
#ProjectCommandBar QPushButton:hover { background: #333741; }

/* ===== 主操作蓝按钮 ===== */
QPushButton#AccentButton {
    color: #ffffff; background: #2563EB; border: none;
    border-radius: 6px; padding: 6px 16px; font-weight: 600;
}
QPushButton#AccentButton:hover { background: #2f6df0; }
QPushButton#AccentButton:pressed { background: #1f55c8; }
QPushButton#AccentButton:disabled { background: #2a3550; color: #8b93a7; }
```

- [ ] **Step 2: 验证 QSS 可加载（语法不破坏现有主题）**

Run:
```
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master && python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.ui.theme import apply_theme; apply_theme(a); print('qss applied len', len(a.styleSheet()))"
```
Expected: 打印非 0 长度，无异常（Qt 对未知选择器静默忽略）

- [ ] **Step 3: 提交**

```bash
git add drama_shot_master/ui/styles/dark.qss
git commit -m "style(ui): dark.qss 增侧栏/命令栏/AccentButton 与影视冷蓝 #2563EB"
```

---

## Task 6: AppShell 基类改 QMainWindow（核心）

把 `AppShell(FluentWindow)` 改成 `AppShell(QMainWindow)`，用 `FlowSidebar` + 普通布局 + `QMenu` + `apply_window_icon` 重写**外壳装配**部分；**所有控制器方法保持不变**。先读 `drama_shot_master/ui/app_shell.py` 全文，区分「装配部分」（要改）与「控制器部分」（不动）。

**要改的方法/部分：** `import` 段、`__init__`、`_build_nav`（删）、`_build_command_bar`（改）、`_build_pages` 末尾 objectName 保留、`_open_settings_menu`/`_open_help_menu`（RoundMenu→QMenu）、`switchTo`（自实现）、`_on_page_changed` 中对侧栏的同步、`showEvent`、`breadcrumb_text`/`_current_key`（基于 stack，逻辑不变）。
**不动的方法：** 所有 `_make_*`/`_*_manager`/`_open_*_window`/`_close_*_window`/`_on_*`/`_persist_*`/`_open_dir`/`_set_out_dir`/`_open_*_settings`/`_open_about`/`_open_help`/`_install_license_watch`/`_check_license_runtime`/`_refresh_counts`/`_refresh_batch_validity`/`_populate_batch_pages`/`_restore_state`/`_set_status`/`closeEvent`。

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Test: `tests/test_ui/test_app_shell_smoke.py`

- [ ] **Step 1: 写/改失败测试（追加到 test_app_shell_smoke.py）**

```python
def test_appshell_is_qmainwindow_and_fluent_free():
    import inspect
    from PySide6.QtWidgets import QMainWindow
    import drama_shot_master.ui.app_shell as m
    assert "qfluentwidgets" not in inspect.getsource(m)   # 外壳已无 GPL 依赖
    _app()
    w = m.AppShell()
    assert isinstance(w, QMainWindow)


def test_appshell_has_flow_sidebar():
    _app()
    from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
    w = AppShell()
    assert isinstance(w.sidebar, FlowSidebar)


def test_sidebar_click_switches_page():
    _app()
    w = AppShell()
    w.sidebar.currentChanged.emit("video_gen")
    assert w.stack.currentWidget() is w.pages["video_gen"]
    assert w.breadcrumb_text() == "③ 视频出片 › 视频生成"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_app_shell_smoke.py -q`
Expected: FAIL（仍是 FluentWindow / 无 `w.sidebar` / source 含 qfluentwidgets）

- [ ] **Step 3: 改 import 段**

把顶部
```python
from qfluentwidgets import FluentWindow, FluentIcon, NavigationItemPosition, ...
```
整段删除，替换为：
```python
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QMenu,
)
from PySide6.QtGui import QAction
from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
from drama_shot_master.ui.widgets.project_command_bar import ProjectCommandBar
from drama_shot_master.ui.theme import apply_window_icon, apply_dark_titlebar
```
（`ProjectCommandBar`、`apply_dark_titlebar` 若原已 import 则去重。删除 `_icon()` 辅助函数与对 `FluentIcon` 的一切引用。）

- [ ] **Step 4: 改类声明与 `__init__`**

类声明 `class AppShell(QMainWindow):`。`__init__` 改为：
```python
def __init__(self):
    super().__init__()
    self.setWindowTitle("Drama-Shot-Master")
    self.resize(1360, 860)
    self.pages = {}
    self._phase_of = {k: t for t, ks in PHASES for k in ks}
    self._status_text = ""
    self._build_pages()
    self._build_ui()          # 新：装配中央布局（命令栏+侧栏+stack）
    self._wire()
    self._restore_state()
    self._install_license_watch()
```
> `_phase_of` 原先在 `_build_nav` 里填充；现改为在 `__init__` 直接从 `PHASES` 构造。前置条件：顶部 import 须含 `from drama_shot_master.ui.nav_config import FUNCS, PHASES, LABELS`（Phase 1 已有此行，仅需确认；`ICONS` 不再需要可从该行移除）。

- [ ] **Step 5: 新增 `_build_ui` + 重写 `_build_command_bar`，删除 `_build_nav`**

```python
def _build_ui(self):
    self.command_bar = ProjectCommandBar()
    self.sidebar = FlowSidebar()
    self.stack = QStackedWidget()
    for _label, key in FUNCS:
        self.stack.addWidget(self.pages[key])

    body = QHBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(0)
    body.addWidget(self.sidebar)
    body.addWidget(self.stack, 1)

    root = QVBoxLayout()
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    root.addWidget(self.command_bar)
    body_w = QWidget()
    body_w.setLayout(body)
    root.addWidget(body_w, 1)

    central = QWidget()
    central.setLayout(root)
    self.setCentralWidget(central)
```
删除旧 `_build_nav` 与 `_build_command_bar`（FluentWindow 布局手术版）整段。命令栏的创建从旧 `_build_command_bar` 移入上面 `_build_ui`；命令栏与侧栏的信号连接放进 `_wire`（Step 6）。

- [ ] **Step 6: 改 `_wire`**

在 `_wire` 中（保留原有 manager `taskRenamed`、各 page panel `statusMessage`、batch page `thumb.selectionChanged→_refresh_counts` 的连接），把导航/命令栏连接改为：
```python
    self.sidebar.currentChanged.connect(self._on_nav_changed)
    self.sidebar.settingsRequested.connect(self._open_settings_menu)
    self.sidebar.helpRequested.connect(self._open_help_menu)
    self.command_bar.openDirRequested.connect(self._open_dir)
    self.command_bar.setOutputRequested.connect(self._set_out_dir)
    self.stack.currentChanged.connect(self._on_page_changed)
```
并新增：
```python
def _on_nav_changed(self, key: str):
    self.switchTo(self.pages[key])
```

- [ ] **Step 7: 新增 `switchTo`，改 `breadcrumb_text`/`_current_key`/`_on_page_changed`**

```python
def switchTo(self, page):
    self.stack.setCurrentWidget(page)
    key = self._key_of(page)
    if key:
        self.sidebar.set_active(key)

def _key_of(self, page):
    for k, p in self.pages.items():
        if p is page:
            return k
    return None

def _current_key(self) -> str:
    return self._key_of(self.stack.currentWidget()) or FUNCS[0][1]
```
`breadcrumb_text` 保持：`f"{self._phase_of.get(key,'')} › {LABELS.get(key,'')}"`（key 取 `_current_key()`）。`_on_page_changed` 保持原逻辑（同步 batch 选择 + `_refresh_counts`）。删除任何对 FluentWindow `stackedWidget` 的引用，统一用 `self.stack`。

- [ ] **Step 8: 重写 `_open_settings_menu` / `_open_help_menu` 用 QMenu**

```python
def _open_settings_menu(self):
    from PySide6.QtGui import QCursor
    menu = QMenu(self)
    for text, fn in [
        ("RunningHub 配置…", self._open_runninghub_settings),
        ("翻译配置…", self._open_translation_settings),
        ("提示词优化配置…", self._open_refine_settings),
        ("配乐…", self._open_soundtrack_settings),
        ("配音…", self._open_dub_settings),
        ("图片生成…", self._open_imggen_settings),
    ]:
        act = QAction(text, self)
        act.triggered.connect(fn)
        menu.addAction(act)
    menu.exec(QCursor.pos())

def _open_help_menu(self):
    from PySide6.QtGui import QCursor
    menu = QMenu(self)
    a_help = QAction("帮助文档", self); a_help.triggered.connect(self._open_help)
    a_about = QAction("关于…", self); a_about.triggered.connect(self._open_about)
    menu.addAction(a_help); menu.addAction(a_about)
    menu.exec(QCursor.pos())
```

- [ ] **Step 9: 改 `showEvent` 设图标 + 深色标题栏**

```python
def showEvent(self, e):
    super().showEvent(e)
    if not getattr(self, "_titlebar_themed", False):
        self._titlebar_themed = True
        apply_window_icon(self)        # 标题栏左侧 [图标] + 软件名
        apply_dark_titlebar(self)
```
（同时确保 `_restore_state` 末尾调用 `self.switchTo(self.pages[key])` 而非 FluentWindow 的旧 switchTo；该方法名一致，逻辑沿用。）

- [ ] **Step 10: 跑全部 UI 测试确认通过**

Run: `python -m pytest tests/test_ui/test_app_shell_smoke.py tests/test_ui/test_flow_sidebar_smoke.py tests/test_ui/test_batch_tool_page_smoke.py -q`
Expected: PASS（含新增 3 条 + 既有命令栏/选择/面包屑断言全绿）

- [ ] **Step 11: 真机冒烟（有显示环境）**

Run: `python -m drama_shot_master.main`
Expected: 原生标题栏左侧显示 `[图标] Drama-Shot-Master`；侧栏分三阶段、可折叠；命令栏可打开目录/设置输出；各功能切换正常；深色 + 蓝高亮。

- [ ] **Step 12: 提交**

```bash
git add drama_shot_master/ui/app_shell.py tests/test_ui/test_app_shell_smoke.py
git commit -m "feat(ui): AppShell 改原生 QMainWindow+FlowSidebar+QMenu，去 qfluentwidgets（控制器逻辑不变）"
```

---

## Task 7: 拆除 init_fluent_theme

**Files:**
- Modify: `drama_shot_master/main.py`
- Modify: `drama_shot_master/ui/theme.py`
- Delete: `tests/test_ui/test_fluent_theme_smoke.py`

- [ ] **Step 1: 改 main.py**

删除 `init_fluent_theme` 的 import 与调用。最终 `main()` 主题相关两行为：
```python
    from drama_shot_master.ui.theme import apply_theme, apply_app_icon
    ...
    apply_theme(app)
    apply_app_icon(app)
```
（`w = AppShell()` 等其余不变。）

- [ ] **Step 2: 改 theme.py**

删除 `THEME_ACCENT` 常量与 `init_fluent_theme` 函数（它们是唯一 import qfluentwidgets 的地方）。`apply_theme`/`apply_app_icon`/`apply_window_icon`/`apply_dark_titlebar`/`load_stylesheet`/`_find_app_icon_path` 保留。

- [ ] **Step 3: 删测试**

```bash
git rm tests/test_ui/test_fluent_theme_smoke.py
```

- [ ] **Step 4: 验证**

Run:
```
grep -n qfluentwidgets drama_shot_master/ui/theme.py drama_shot_master/main.py || echo "clean"
python -m pytest tests/test_ui/test_entry_uses_app_shell.py tests/test_ui/test_window_icon_smoke.py -q
```
Expected: 打印 `clean`；2 个测试文件 PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/main.py drama_shot_master/ui/theme.py
git commit -m "refactor(ui): 移除 init_fluent_theme/THEME_ACCENT，主题改纯 QSS（去 qfluentwidgets）"
```

---

## Task 8: 删除 main_window.py + 收尾验收

**Files:**
- Delete: `drama_shot_master/ui/main_window.py`
- Modify: `tests/test_ui/test_main_window_soundtrack_smoke.py`

- [ ] **Step 1: 复核无残留引用**

Run: `grep -rn "main_window import\|import main_window\|MainWindow" drama_shot_master/ tests/`
Expected: 仅 `tests/test_ui/test_main_window_soundtrack_smoke.py` 命中（它 `from drama_shot_master.ui.main_window import MainWindow, FUNCS`）。若有其它生产代码命中，停下报告。

- [ ] **Step 2: 改 test_main_window_soundtrack_smoke.py**

该测试本意是「配乐功能存在 + 面板数 == FUNCS」。改为基于 nav_config 与 AppShell：
```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.nav_config import FUNCS
from drama_shot_master.ui.app_shell import AppShell


def test_soundtrack_function_registered():
    keys = [key for _label, key in FUNCS]
    assert "soundtrack" in keys


def test_appshell_registers_all_functions():
    app = QApplication.instance() or QApplication([])
    w = AppShell()
    w.show(); app.processEvents()
    assert len(w.pages) == len(FUNCS)
```
（文件可改名为 `test_appshell_functions_smoke.py`；用 `git mv` 保留历史，或直接覆盖内容。本步选择覆盖内容、保留原文件名以减少改动面。）

- [ ] **Step 3: 删 main_window.py**

```bash
git rm drama_shot_master/ui/main_window.py
```

- [ ] **Step 4: 验收 —— 零 GPL 依赖 + 全量回归**

Run:
```
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
echo "== qfluentwidgets 残留检查（应为空）=="
grep -rl qfluentwidgets drama_shot_master/ tests/ && echo "!!! STILL PRESENT" || echo "CLEAN: zero qfluentwidgets"
echo "== 每文件跑 UI 测试 =="
for f in tests/test_ui/*.py; do echo "== $f =="; python -m pytest "$f" -q 2>&1 | tail -2; done
echo "== 非 UI 全量 =="
python -m pytest tests/ -q --ignore=tests/test_ui 2>&1 | tail -3
```
Expected: 打印 `CLEAN: zero qfluentwidgets`；所有 UI 测试文件 "N passed"（结果后 exit 139 段错误为已知 WSL teardown 伪影，非失败）；非 UI 全量通过。

- [ ] **Step 5: 提交**

```bash
git add tests/test_ui/test_main_window_soundtrack_smoke.py
git rm drama_shot_master/ui/main_window.py 2>/dev/null; true
git commit -m "chore(ui): 删除旧 main_window.py，外壳完成原生化（零 qfluentwidgets/GPL 依赖）"
```

---

## 验收清单（对应 spec §1/§8）
- [ ] `grep -rl qfluentwidgets drama_shot_master/ tests/` 为空。
- [ ] `AppShell` 是 `QMainWindow`；侧栏为 `FlowSidebar`，分三阶段、可折叠为图标条。
- [ ] 主题为影视冷蓝深色（QSS）；标题栏左侧显示 `[图标] Drama-Shot-Master`。
- [ ] 7 功能可达，批处理/任务管理两类页行为同 Phase 1（生成类仍双击开窗）。
- [ ] 命令栏（打开目录/设置输出/计数）、设置 6 项、帮助文档/关于 均可达。
- [ ] `config.json` 持久化项（last_active_function、各 *_tasks）不丢。
- [ ] `python -m pytest tests/` 全绿；Windows 真机肉眼通过。

## 后续阶段（不变，沿用原 UX spec，各自单独成 plan）
Phase 2 内嵌主-详+浮出 / Phase 3 统一设置页+浅色切换 / Phase 4 全局任务中心抽屉 / Phase 5 逐控件精修。均在原生 PySide6 基础上进行。
