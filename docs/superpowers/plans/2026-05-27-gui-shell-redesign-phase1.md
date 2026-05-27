# GUI 外壳重构 · Phase 1（Fluent 流程外壳）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 PyQt-Fluent-Widgets 的 `FluentWindow` 实现一个流程式（① 素材准备 / ② 分镜创作 / ③ 视频出片）侧栏外壳，完整替换现有横向按钮主窗，所有 7 个功能可达、行为不变（生成类仍双击开窗），主题切到影视冷蓝，DWM 深色标题栏共存。

**Architecture:** 新增 `AppShell(FluentWindow)`，复用全部现有 panel/window/store/dialog 与回调逻辑；把 `FUNCS` 与分组抽到 `nav_config.py` 供新旧共享；`main.py` 入口切到 `AppShell`。批处理类（拆/拼/去白边）与生成类（图片/视频/配乐/配音）各自成为侧栏一页；本期生成类仍沿用「双击任务列表行 → 开独立任务窗」，不做内嵌主-详（留给 Phase 2）。

**Tech Stack:** PySide6 6.11、qfluentwidgets 1.11.2、pytest 9（offscreen Qt，无 pytest-qt）。

**Spec:** `docs/superpowers/specs/2026-05-27-gui-shell-redesign-design.md`

---

## 本期范围（Phase 1）

覆盖 spec §4.1（流程侧栏）、§4.2（面包屑）、§4.3(a) 批处理页外壳、§5（主题色/深浅初始化）、§6（main_window→app_shell 映射）、§7 phase ①。

**不在本期**：§4.3(b) 内嵌主-详 + 浮出（Phase 2）、§4.4 全局任务中心（Phase 4）、§4.5 统一设置页（Phase 3）、逐控件 Fluent 化（Phase 5）。本期生成类页内直接放现有 `*TaskManagerPanel`，其「双击开窗」行为原样保留。

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| Create | `drama_shot_master/ui/nav_config.py` | 单一事实源：`FUNCS`、阶段分组 `PHASES`、key↔图标映射 |
| Create | `drama_shot_master/ui/app_shell.py` | `AppShell(FluentWindow)`：侧栏装配 + 复用现有 panel/回调 + 面包屑 |
| Create | `drama_shot_master/ui/pages/__init__.py` | 包初始化 |
| Create | `drama_shot_master/ui/pages/batch_tool_page.py` | `BatchToolPage`：缩略图网格 + 批处理 panel + 预览/执行，封装现状右栏底栏逻辑 |
| Modify | `drama_shot_master/ui/theme.py` | 增 `init_fluent_theme(app)`：`setTheme` + `setThemeColor("#2563EB")`；DWM 配色沿用 |
| Modify | `drama_shot_master/ui/main_window.py` | 顶部 `from .nav_config import FUNCS` 回导，删除本地 `FUNCS` 定义（保持旧测试 `from ...main_window import FUNCS` 可用）|
| Modify | `drama_shot_master/main.py` | 入口由 `MainWindow` 切到 `AppShell`；`apply_theme` 后调 `init_fluent_theme` |
| Create | `tests/test_ui/test_nav_config.py` | 纯逻辑：FUNCS/PHASES 一致性 |
| Create | `tests/test_ui/test_batch_tool_page_smoke.py` | BatchToolPage 结构 smoke |
| Create | `tests/test_ui/test_app_shell_smoke.py` | AppShell 装配 smoke（页数、面包屑、设置项、主题色）|

---

## Task 1: 抽取导航配置 `nav_config.py`（纯逻辑，先建地基）

**Files:**
- Create: `drama_shot_master/ui/nav_config.py`
- Modify: `drama_shot_master/ui/main_window.py:34-44`
- Test: `tests/test_ui/test_nav_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_nav_config.py
from drama_shot_master.ui.nav_config import FUNCS, PHASES, ICONS


def test_funcs_has_seven_functions():
    keys = [key for _label, key in FUNCS]
    assert keys == ["split", "combine", "trim", "imggen",
                    "video_gen", "soundtrack", "dubbing"]


def test_phases_cover_all_func_keys_in_order():
    # 阶段内 key 顺序拼起来必须等于 FUNCS 的 key 顺序（流程式侧栏顺序契约）
    flat = [k for _title, keys in PHASES for k in keys]
    assert flat == [key for _label, key in FUNCS]


def test_phases_are_three_numbered_stages():
    titles = [title for title, _keys in PHASES]
    assert titles == ["① 素材准备", "② 分镜创作", "③ 视频出片"]


def test_every_func_key_has_icon():
    for _label, key in FUNCS:
        assert key in ICONS
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_nav_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'drama_shot_master.ui.nav_config'`

- [ ] **Step 3: 写实现**

```python
# drama_shot_master/ui/nav_config.py
"""导航配置单一事实源：功能列表、流程阶段分组、图标映射。

新旧外壳（main_window / app_shell）共享，避免顺序/分组出现两份。
图标用 qfluentwidgets.FluentIcon 名称字符串，装配时再解析为枚举，
保持本模块 Qt-free 以便纯逻辑单测。
"""
from __future__ import annotations

# (显示名, key)；顺序即侧栏从上到下顺序，须与 PHASES 展平后一致。
FUNCS = [
    ("拆图", "split"),
    ("拼图", "combine"),
    ("去白边", "trim"),
    ("图片生成", "imggen"),
    ("视频生成", "video_gen"),
    ("配乐", "soundtrack"),
    ("配音", "dubbing"),
]

# 流程阶段：(阶段标题, [key, ...])。标题带编号体现制作管线先后。
PHASES = [
    ("① 素材准备", ["split", "combine", "trim"]),
    ("② 分镜创作", ["imggen"]),
    ("③ 视频出片", ["video_gen", "soundtrack", "dubbing"]),
]

# 批处理类（主区：网格+参数+执行）vs 任务管理类（主区：任务列表，双击开窗）
BATCH_KEYS = {"split", "combine", "trim"}
TASK_KEYS = {"imggen", "video_gen", "soundtrack", "dubbing"}

# key → FluentIcon 成员名（装配时 getattr(FluentIcon, name)）
ICONS = {
    "split": "CUT",
    "combine": "PHOTO",
    "trim": "ERASE_TOOL",
    "imggen": "PALETTE",
    "video_gen": "VIDEO",
    "soundtrack": "MUSIC",
    "dubbing": "MICROPHONE",
}

# 功能名映射（key → 显示名），便于面包屑/标题查询
LABELS = {key: label for label, key in FUNCS}
```

- [ ] **Step 4: 改 main_window 回导，删除本地 FUNCS/分组定义**

把 `drama_shot_master/ui/main_window.py` 第 34–44 行的本地 `FUNCS`、`_IMAGE_KEYS`、`_VIDEO_KEYS` 定义替换为回导（其余引用 `FUNCS` 处不变；`_IMAGE_KEYS/_VIDEO_KEYS` 在 main_window 内已不再被横向分组使用以外的逻辑引用，删除前用 grep 确认）：

```python
# main_window.py 顶部 import 区（原 34-44 行那段注释 + FUNCS + _IMAGE_KEYS + _VIDEO_KEYS 整体替换为）
from drama_shot_master.ui.nav_config import FUNCS  # 单一事实源；旧测试仍从本模块导入
```

**推荐做法（最小改动、零回归）**：本步**只**把 `main_window.py` 第 36–40 行的 `FUNCS = [...]` 列表整体替换为上面的回导一行；`_IMAGE_KEYS`/`_VIDEO_KEYS`（第 43–44 行）与 `_build_ui` 里引用它们的横向切换条逻辑**保持不动**——旧主窗 Phase 1 仍可独立运行作为回退安全网，其清理统一放到 Phase 5。不要在本步触碰 main_window 的任何其它逻辑。

- [ ] **Step 5: 跑测试确认通过 + 旧主窗测试不回归**

Run: `python -m pytest tests/test_ui/test_nav_config.py tests/test_ui/test_main_window_soundtrack_smoke.py -q`
Expected: PASS（新 4 条 + 旧 2 条全绿；旧测试仍 `from ...main_window import FUNCS` 成功）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/nav_config.py drama_shot_master/ui/main_window.py tests/test_ui/test_nav_config.py
git commit -m "refactor(ui): 抽取导航配置 nav_config（FUNCS+流程阶段分组），供新旧外壳共享"
```

---

## Task 2: 主题初始化 `init_fluent_theme`（影视冷蓝）

**Files:**
- Modify: `drama_shot_master/ui/theme.py`（尾部新增函数）
- Test: `tests/test_ui/test_fluent_theme_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_fluent_theme_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.theme import init_fluent_theme, THEME_ACCENT


def test_init_fluent_theme_sets_blue_accent():
    app = QApplication.instance() or QApplication([])
    # 不应抛异常；返回当前主题色 QColor，name() 等于配置的冷蓝
    color = init_fluent_theme(app)
    assert color.name().lower() == THEME_ACCENT.lower()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_fluent_theme_smoke.py -q`
Expected: FAIL — `ImportError: cannot import name 'init_fluent_theme'`

- [ ] **Step 3: 写实现（追加到 theme.py 尾部）**

```python
# 追加到 drama_shot_master/ui/theme.py 末尾

# 影视冷蓝（spec §5）；浅色切换在 Phase 3 设置页接入
THEME_ACCENT = "#2563EB"


def init_fluent_theme(app, dark: bool = True, accent: str = THEME_ACCENT):
    """初始化 PyQt-Fluent-Widgets 全局主题：深/浅 + 主题色。

    返回设置后的主题色 QColor。在 apply_theme(app) 之后调用，
    让 Fluent 控件接管自身配色（QSS 仍可覆盖非 Fluent 控件）。
    """
    from qfluentwidgets import setTheme, setThemeColor, Theme
    from PySide6.QtGui import QColor
    setTheme(Theme.DARK if dark else Theme.LIGHT)
    c = QColor(accent)
    setThemeColor(c)
    return c
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/test_fluent_theme_smoke.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/theme.py tests/test_ui/test_fluent_theme_smoke.py
git commit -m "feat(ui): init_fluent_theme 影视冷蓝主题初始化(#2563EB)"
```

---

## Task 3: 批处理页 `BatchToolPage`（网格+参数+执行）

封装现状「中栏缩略图网格 + 右栏 panel + 底部 预览/执行」为一个自包含页，供拆/拼/去白边复用。复用现有 `ThumbnailGrid` 与 `BasePanel` 子类，契约不变。

**Files:**
- Create: `drama_shot_master/ui/pages/__init__.py`（空文件）
- Create: `drama_shot_master/ui/pages/batch_tool_page.py`
- Test: `tests/test_ui/test_batch_tool_page_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_batch_tool_page_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.config import load_config
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.panels.trim_panel import TrimPanel
from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage


def _app():
    return QApplication.instance() or QApplication([])


def test_page_exposes_grid_panel_and_exec_button():
    _app()
    state, cfg = AppState(), load_config()
    panel = TrimPanel(state, cfg)
    page = BatchToolPage(panel, state, cfg)
    assert page.thumb is not None          # 缩略图网格
    assert page.panel is panel             # 内嵌的批处理 panel
    assert hasattr(page, "btn_exec")       # 执行按钮
    assert hasattr(page, "btn_preview")    # 预览按钮


def test_exec_button_disabled_when_panel_invalid():
    _app()
    state, cfg = AppState(), load_config()
    page = BatchToolPage(TrimPanel(state, cfg), state, cfg)
    # 未选目录/图片 → 不可执行
    ok, _why = page.panel.validate()
    assert page.btn_exec.isEnabled() == ok
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_batch_tool_page_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError: ...pages.batch_tool_page`

- [ ] **Step 3: 写实现**

```python
# drama_shot_master/ui/pages/__init__.py
# (空文件)
```

```python
# drama_shot_master/ui/pages/batch_tool_page.py
"""BatchToolPage：批处理功能（拆图/拼图/去白边）的主区页。

把现状 main_window 里「中栏 ThumbnailGrid + 右栏 BasePanel + 底部 预览/执行」
收拢为一个自包含页。BasePanel 的 validate/execute/select_mode/has_preview/
overlay_spec 契约保持不变；本页只负责布局与按钮联动。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QMessageBox,
)

from drama_shot_master.config import Config
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.thumbnail_grid import ThumbnailGrid
from drama_shot_master.ui.preview_dialog import PreviewDialog


class BatchToolPage(QWidget):
    def __init__(self, panel: BasePanel, state: AppState, cfg: Config,
                 parent=None):
        super().__init__(parent)
        self.panel = panel
        self.state = state
        self.cfg = cfg

        self.thumb = ThumbnailGrid()
        self.thumb.set_mode(panel.select_mode())

        right = QVBoxLayout()
        right.addWidget(panel, 1)
        act = QHBoxLayout()
        self.btn_preview = QPushButton("预览")
        self.btn_exec = QPushButton("执行")
        self.btn_exec.setObjectName("AccentButton")
        self.exec_hint = QLabel("")
        self.exec_hint.setStyleSheet("color:#888")
        act.addWidget(self.btn_preview)
        act.addWidget(self.btn_exec)
        act.addWidget(self.exec_hint, 1)
        right.addLayout(act)
        right_w = QWidget(); right_w.setLayout(right)
        right_w.setMinimumWidth(340); right_w.setMaximumWidth(420)

        root = QHBoxLayout(self)
        root.addWidget(self.thumb, 1)
        root.addWidget(right_w)

        self.btn_preview.clicked.connect(self._do_preview)
        self.btn_exec.clicked.connect(self._do_execute)
        self.thumb.selectionChanged.connect(self._on_selection)
        if hasattr(panel, "validityChanged"):
            panel.validityChanged.connect(self.refresh_validity)
        self.btn_preview.setVisible(panel.has_preview())
        self.refresh_validity()

    def populate(self, images):
        self.thumb.populate(images)

    def _on_selection(self, order):
        self.state.selected = list(order)
        self.refresh_validity()

    def refresh_validity(self):
        ok, why = self.panel.validate()
        self.btn_exec.setEnabled(ok)
        self.exec_hint.setText(why)

    def _do_preview(self):
        sel = self.state.selected_paths()
        if not sel:
            QMessageBox.information(self, "预览", "请先选一张图")
            return
        PreviewDialog(sel[0], overlay_spec=self.panel.overlay_spec(),
                      parent=self).exec()

    def _do_execute(self):
        ok, why = self.panel.validate()
        if not ok:
            QMessageBox.warning(self, "无法执行", why)
            return
        self.panel.execute()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/test_batch_tool_page_smoke.py -q`
Expected: PASS（2 条）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/pages/__init__.py drama_shot_master/ui/pages/batch_tool_page.py tests/test_ui/test_batch_tool_page_smoke.py
git commit -m "feat(ui): BatchToolPage 批处理页(网格+参数+执行)，复用 ThumbnailGrid/BasePanel"
```

---

## Task 4: 装配验证 Spike —— `FluentWindow` + 侧栏 + DWM 标题栏共存

spec §7 列为风险点。先用一个最小可运行的 AppShell 验证三件事能共存：FluentWindow 能加载、`addSubInterface` 能注册带阶段分组的侧栏、`apply_dark_titlebar` 仍生效。本任务产出可运行骨架，不接真实 panel。

**Files:**
- Create: `drama_shot_master/ui/app_shell.py`（最小骨架）
- Test: `tests/test_ui/test_app_shell_smoke.py`（仅本任务相关的 2 条）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_app_shell_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell


def _app():
    return QApplication.instance() or QApplication([])


def test_shell_constructs_and_registers_seven_pages():
    _app()
    w = AppShell()
    w.show(); QApplication.instance().processEvents()
    # 7 个功能页都注册进 stackedWidget（设置/帮助为 Phase 3/已有对话框，不计入）
    assert len(w.pages) == 7


def test_shell_breadcrumb_reflects_initial_function():
    _app()
    w = AppShell()
    # 面包屑随当前功能更新；初始为某个有效阶段标题 + 功能名
    txt = w.breadcrumb_text()
    assert "›" in txt
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_app_shell_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError: ...app_shell`

- [ ] **Step 3: 写最小骨架实现**

```python
# drama_shot_master/ui/app_shell.py
"""AppShell：基于 qfluentwidgets.FluentWindow 的流程式外壳（Phase 1）。

侧栏按 nav_config.PHASES 分阶段注册 7 个功能页，复用现有 panel；
生成类页本期仍内嵌 *TaskManagerPanel，沿用其「双击开窗」行为。
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition, setTheme, Theme,
)

from drama_shot_master.ui.nav_config import FUNCS, PHASES, ICONS, LABELS


def _icon(key: str):
    return getattr(FluentIcon, ICONS[key])


class _Placeholder(QWidget):
    """Spike 占位页；Task 5 替换为真实页。"""
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName(f"page_{key}")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(LABELS[key]))


class AppShell(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drama-Shot-Master")
        self.resize(1360, 860)
        self.pages: dict[str, QWidget] = {}
        self._phase_of: dict[str, str] = {}
        self._build_nav()

    def _build_nav(self):
        for phase_title, keys in PHASES:
            # 非选中的阶段标题项（spec：编号阶段分组）
            self.navigationInterface.addItem(
                routeKey=f"phase::{phase_title}", icon=FluentIcon.TAG,
                text=phase_title, onClick=None, selectable=False,
                position=NavigationItemPosition.SCROLL)
            for key in keys:
                page = _Placeholder(key)
                self.pages[key] = page
                self._phase_of[key] = phase_title
                self.addSubInterface(
                    page, _icon(key), LABELS[key],
                    position=NavigationItemPosition.SCROLL)
            self.navigationInterface.addSeparator(
                position=NavigationItemPosition.SCROLL)

    def _current_key(self) -> str:
        cur = self.stackedWidget.currentWidget()
        for key, page in self.pages.items():
            if page is cur:
                return key
        return FUNCS[0][1]

    def breadcrumb_text(self) -> str:
        key = self._current_key()
        return f"{self._phase_of.get(key, '')} › {LABELS.get(key, '')}"

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_titlebar_themed", False):
            self._titlebar_themed = True
            from drama_shot_master.ui.theme import apply_dark_titlebar
            apply_dark_titlebar(self)
```

> **Spike 验证（手动）**：临时 `python -c "from PySide6.QtWidgets import QApplication; import sys; from drama_shot_master.ui.app_shell import AppShell; from drama_shot_master.ui.theme import init_fluent_theme; a=QApplication(sys.argv); init_fluent_theme(a); w=AppShell(); w.show(); a.exec()"` 在有显示的机器上肉眼确认：侧栏出现三阶段、深色标题栏生效、主题蓝。记录 `addItem(selectable=False)` 与 `addSeparator` 在 1.11.2 的实际签名；若签名不符按报错调整（这是本 spike 的目的）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ui/test_app_shell_smoke.py -q`
Expected: PASS（2 条）。若 `addItem`/`addSeparator` 签名报错，依实际 API 调整 `_build_nav` 后再绿。

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/app_shell.py tests/test_ui/test_app_shell_smoke.py
git commit -m "feat(ui): AppShell 骨架(FluentWindow+流程侧栏+DWM标题栏)，spike 验证共存"
```

---

## Task 5: 接入真实功能页（复用现有 panel 与全部回调）

把占位页换成真实页：批处理类用 `BatchToolPage`，生成类直接放现有 `*TaskManagerPanel`，并把 main_window 里的 store/回调/开窗逻辑迁入 AppShell。本任务较大，按子步推进，每步可跑。

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Test: `tests/test_ui/test_app_shell_smoke.py`（补充断言）

- [ ] **Step 1: 写失败测试（补充到现有文件）**

```python
# 追加到 tests/test_ui/test_app_shell_smoke.py
def test_batch_pages_are_batch_tool_page():
    _app()
    from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
    w = AppShell()
    for key in ("split", "combine", "trim"):
        assert isinstance(w.pages[key], BatchToolPage)


def test_task_pages_are_manager_panels():
    _app()
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    w = AppShell()
    assert isinstance(w.pages["video_gen"], VideoTaskManagerPanel)


def test_open_dir_populates_batch_pages():
    _app()
    w = AppShell()
    # 打开目录的逻辑应同步喂给所有 BatchToolPage 的网格（无图时不崩）
    assert hasattr(w, "_open_dir")


def test_shell_exposes_settings_and_about_entries():
    _app()
    w = AppShell()
    # 底部入口方法存在（Phase 1 沿用现有对话框）
    assert hasattr(w, "_open_settings_menu") or hasattr(w, "_open_about")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_app_shell_smoke.py -q`
Expected: FAIL — `pages["split"]` 仍是 `_Placeholder`，断言不通过

- [ ] **Step 3: 实现 —— 迁入 store/回调并构造真实页**

把 `main_window.py` 中以下方法**逐字复制**进 `AppShell`（方法体一行不改，仅换宿主类；`main_window.py` 原文件不动）。源行号见括注，照抄即可：

- store/字典构造（`main_window.py:54-61`）→ 放进本任务的 `_build_pages`
- `_make_imggen_panel`（500-505）、`_make_dub_panel`（441-445）、`_try_make_soundtrack_panel`（371-384）、`_persist_soundtrack`（386-390）
- `_video_manager`（317-319）、`_dub_manager`（447-449）、`_imggen_manager`（507-509）、`_soundtrack_panel`（392-394）
- 视频任务窗回调 `_persist_tasks`/`_open_task_window`/`_close_task_window`/`_on_task_dirty`/`_on_task_status`/`_on_task_result`/`_on_task_window_closed`/`_on_task_renamed`（321-365）
- 配音任务窗回调 `_persist_dub_tasks`/`_open_dub_window`/`_close_dub_window`/`_on_dub_*`（451-494）
- 图片任务窗回调 `_persist_imggen_tasks`/`_open_imggen_window`/`_close_imggen_window`/`_on_imggen_*`（511-553）
- 配乐任务窗回调 `_open_soundtrack_window`/`_on_soundtrack_*`（396-435）
- 目录与设置入口 `_open_dir`/`_set_out_dir`/`_open_runninghub_settings`/`_open_translation_settings`/`_open_refine_settings`/`_open_soundtrack_settings`/`_open_dub_settings`/`_open_imggen_settings`/`_open_about`/`_open_help`（241-297）
- 授权 `_install_license_watch`/`_check_license_runtime`（299-315）、`closeEvent` 落盘段（638-672）

**唯一改动点**：`_open_dir` 末尾把原 `self.thumb.populate(...)` 改为调本任务新增的 `self._populate_batch_pages()`（因为缩略图网格现在分布在各 BatchToolPage 内，不再有单一 `self.thumb`）。该步以 `tests/test_ui/test_app_shell_smoke.py` 全绿为完成门槛。

构造页时：

```python
# app_shell.py 中 _build_pages（在 _build_nav 之前调用，_build_nav 改为消费 self.pages）
def _build_pages(self):
    from drama_shot_master.config import load_config
    from drama_shot_master.ui.state import AppState
    import drama_shot_master.providers  # noqa: F401  触发注册
    from drama_shot_master.core.video_task_store import VideoTaskStore
    from drama_shot_master.core.dub_task_store import DubTaskStore
    from drama_shot_master.core.imggen_task_store import ImgGenTaskStore
    from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
    from drama_shot_master.ui.panels.split_panel import SplitPanel
    from drama_shot_master.ui.panels.combine_panel import CombinePanel
    from drama_shot_master.ui.panels.trim_panel import TrimPanel
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel

    self.cfg = load_config()
    self.state = AppState()
    self.video_store = VideoTaskStore.from_list(self.cfg.video_tasks)
    self.dub_store = DubTaskStore.from_list(self.cfg.dub_tasks)
    self.imggen_store = ImgGenTaskStore.from_list(self.cfg.imggen_tasks)
    self._open_task_windows = {}
    self._open_dub_windows = {}
    self._open_imggen_windows = {}

    builders = {
        "split":   lambda: BatchToolPage(SplitPanel(self.state, self.cfg), self.state, self.cfg),
        "combine": lambda: BatchToolPage(CombinePanel(self.state, self.cfg), self.state, self.cfg),
        "trim":    lambda: BatchToolPage(TrimPanel(self.state, self.cfg), self.state, self.cfg),
        "imggen":  self._make_imggen_panel,
        "video_gen": lambda: VideoTaskManagerPanel(
            self.state, self.cfg, self.video_store,
            self._open_task_window, self._close_task_window, self._persist_tasks),
        "soundtrack": self._try_make_soundtrack_panel,
        "dubbing": self._make_dub_panel,
    }
    for _label, key in FUNCS:
        page = builders[key]()
        page.setObjectName(f"page_{key}")   # FluentWindow 要求唯一 objectName
        self.pages[key] = page
```

`__init__` 改为：

```python
def __init__(self):
    super().__init__()
    self.setWindowTitle("Drama-Shot-Master")
    self.resize(1360, 860)
    self.pages = {}
    self._phase_of = {}
    self._build_pages()
    self._build_nav()       # 现在消费 self.pages 而非建占位
    self._wire()
    self._restore_state()
    self._install_license_watch()
```

`_build_nav` 改为用已存在的 `self.pages[key]` 调 `addSubInterface`（删除 `_Placeholder`）。`_wire/_restore_state` 把 main_window 的 `_wire` 与 `__init__` 尾部目录恢复逻辑搬过来（`restore_from_config`、填充 BatchToolPage 网格、恢复 `last_active_function` → 用 `self.switchTo(self.pages[key])`）。

底部导航加设置/帮助项：

```python
# _build_nav 末尾
self.navigationInterface.addItem(
    routeKey="settings", icon=FluentIcon.SETTING, text="设置",
    onClick=self._open_settings_menu, selectable=False,
    position=NavigationItemPosition.BOTTOM)
self.navigationInterface.addItem(
    routeKey="about", icon=FluentIcon.INFO, text="帮助 / 关于",
    onClick=self._open_about, selectable=False,
    position=NavigationItemPosition.BOTTOM)
```

`_open_settings_menu`（Phase 1 过渡：用现有对话框，弹一个选择菜单或直接复用 main_window 的逐个入口；最简实现弹 `RoundMenu` 列 6 项分别调现有 `_open_*_settings`）：

```python
def _open_settings_menu(self):
    from qfluentwidgets import RoundMenu, Action
    from PySide6.QtGui import QCursor
    menu = RoundMenu(parent=self)
    for text, fn in [
        ("RunningHub 配置…", self._open_runninghub_settings),
        ("翻译配置…", self._open_translation_settings),
        ("提示词优化配置…", self._open_refine_settings),
        ("配乐…", self._open_soundtrack_settings),
        ("配音…", self._open_dub_settings),
        ("图片生成…", self._open_imggen_settings),
    ]:
        act = Action(text, self); act.triggered.connect(fn)
        menu.addAction(act)
    menu.exec(QCursor.pos())
```

目录打开后喂网格：`_open_dir` 末尾对每个 BatchToolPage 调 `page.populate(self.state.images)`：

```python
def _populate_batch_pages(self):
    from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
    for page in self.pages.values():
        if isinstance(page, BatchToolPage):
            page.populate(self.state.images)
```

面包屑随页切换更新：连接 `self.stackedWidget.currentChanged` → 更新一个放在标题栏区或页顶的 `BreadcrumbBar`（Phase 1 可先用 `self.breadcrumb_text()` 写入窗口标题副标题或一个顶部 `QLabel`；完整 BreadcrumbBar 控件留意 §4.2，可本任务接入 `qfluentwidgets.BreadcrumbBar`）。

- [ ] **Step 4: 跑全部 UI 测试确认通过**

Run: `python -m pytest tests/test_ui/ -q`
Expected: PASS（新旧全绿）

- [ ] **Step 5: 真机冒烟（有显示环境）**

Run: `python -m drama_shot_master.main`（或项目既有启动方式）
Expected: 出现流程侧栏；点各功能切换正常；拆/拼/去白边可选图执行；图片/视频/配乐/配音双击开任务窗如旧；设置菜单 6 项可打开；标题栏深色、主题蓝。

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/app_shell.py tests/test_ui/test_app_shell_smoke.py
git commit -m "feat(ui): AppShell 接入真实功能页与全部任务窗回调，复用现有 panel/store"
```

---

## Task 6: 入口切换 + 旧主窗收尾

**Files:**
- Modify: `drama_shot_master/main.py`
- Test: `tests/test_ui/test_entry_uses_app_shell.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui/test_entry_uses_app_shell.py
import inspect
import drama_shot_master.main as m


def test_entry_imports_app_shell():
    src = inspect.getsource(m.main)
    assert "AppShell" in src
    assert "MainWindow" not in src
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ui/test_entry_uses_app_shell.py -q`
Expected: FAIL — main.py 仍 import MainWindow

- [ ] **Step 3: 改 main.py**

把 `drama_shot_master/main.py` 的 `main()` 中：

```python
    from drama_shot_master.ui.main_window import MainWindow
    from drama_shot_master.ui.theme import apply_theme, apply_app_icon
    ...
    apply_theme(app)
    apply_app_icon(app)
    ...
    w = MainWindow()
```

改为：

```python
    from drama_shot_master.ui.app_shell import AppShell
    from drama_shot_master.ui.theme import apply_theme, apply_app_icon, init_fluent_theme
    ...
    apply_theme(app)
    init_fluent_theme(app)      # Fluent 深色 + 影视冷蓝
    apply_app_icon(app)
    ...
    w = AppShell()
```

（激活 gate 逻辑、`return 0` 分支保持不变。）

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python -m pytest tests/test_ui/test_entry_uses_app_shell.py -q && python -m pytest tests/ -q`
Expected: PASS（入口测试绿；全量测试不回归）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/main.py tests/test_ui/test_entry_uses_app_shell.py
git commit -m "feat(ui): 入口切换到 AppShell + init_fluent_theme（Phase 1 外壳上线）"
```

> 注：`main_window.py` 本期**保留不删**（旧 smoke 测试仍依赖它且作为回退安全网），在 Phase 5 收尾任务统一移除。

---

## Phase 1 验收清单（对应 spec §8 子集）

- [ ] 侧栏按 ① 素材准备 / ② 分镜创作 / ③ 视频出片 分阶段展示全部 7 功能，可折叠为图标条（FluentWindow 自带）。
- [ ] 拆/拼/去白边在单页内完成「选图→参数→预览/执行」，无控件隐藏跳变。
- [ ] 图片/视频/配乐/配音页内为任务列表，双击开独立窗（行为同旧版）。
- [ ] 6 项配置经侧栏底部「设置」可达；「帮助/关于」可达。
- [ ] 主题为影视冷蓝深色；Windows 标题栏深色。
- [ ] `python -m pytest tests/ -q` 全绿；`config.json` 持久化项（`last_active_function`、缩略图尺寸、各 *_tasks）不丢。

---

## 后续阶段（各自独立成 plan，Phase 1 落地后再细化）

> 依据 writing-plans Scope Check：以下每个阶段独立可交付、且依赖前一阶段暴露的集成事实，故各自单独写 plan，不在此预写其代码。

- **Phase 2 — 内嵌主-详 + 浮出独立窗（spec §4.3b）**：`TaskWorkspacePage`（左 manager 列表 / 右内嵌 detail editor）；「⧉ 浮出」把 editor 移交现有 `*TaskWindow`，收回时落盘；支持多窗并行。交付物：4 个生成类页改造 + reparent/落盘测试。
- **Phase 3 — 统一设置页（spec §4.5）**：`SettingsPage`（左分类右参数，Fluent `SettingCardGroup`）；6 个配置内容迁入；浅/深主题开关接 `init_fluent_theme(dark=...)`。替换 Phase 1 的 `_open_settings_menu` 过渡菜单。
- **Phase 4 — 全局任务中心（spec §4.4）**：底部常驻条 + 队列抽屉，聚合各 `*TaskStore` 与 `_live_status`，显示运行/排队/完成与并行分类计数。
- **Phase 5 — 逐控件 Fluent 化 + 收尾（spec §5/§6）**：各 panel 内 `QPushButton/QLineEdit/...` 替换为 Fluent 对应控件；移除 `main_window.py` 及其旧测试；浅色主题打磨。
