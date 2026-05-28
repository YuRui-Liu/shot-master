# GUI Phase 3+4+5 合并设计：统一设置 / 任务中心 / 主题系统 + 侧栏折叠

- 日期：2026-05-28
- 前置：Phase 2 配乐主-详已收口（四个生成功能均 TaskWorkspacePage）；`main_window.py` 早已退役（`find` 验证），入口直接 AppShell。
- 范围：原 UX 路线 Phase 3（统一设置页 + 浅色主题）/ Phase 4（任务中心抽屉）/ Phase 5（侧栏折叠 + 样式 token 统一 + 过时注释清理）。
- 用户硬约束：**无 GPL 依赖**（qfluentwidgets 禁用）；纯 PySide6 + QSS。

---

## 1. 总体架构与推进顺序

**核心洞察**：Phase 3 的"实时主题切换"与 Phase 5 的"QSS 统一样式"本质同一件事——都要求所有控件以"主题 token"为单一样式源。故合并为 **§2 主题系统**，作为最底层基础设施。

**三大产物：**
1. **主题系统**（§2）—— token 化 QSS + 运行时切换 + 全代码硬编码颜色清扫。
2. **UnifiedSettingsPage**（§3）—— 左树+右内容；6 个旧 dialog 合一；主题切换即点即生效；6 个旧 dialog 文件**干净退场**。
3. **TaskCenterDock**（§4）—— 右侧 `QDockWidget`，默认隐藏；只读总览+跳转；最近完成上限 20。
4. **CollapsibleFlowSidebar + 精修**（§5）—— 两态手动折叠（展开 / 只图标）；过时 MainWindow 注释清理；重命名一致性 audit。

**推进顺序（最小返工）：**
```
主题系统 → UnifiedSettingsPage → TaskCenterDock → 侧栏折叠/精修
```
理由：主题 token 是基础设施，先立好；设置页内含主题切换入口、要消费切换 API；任务中心独立但用 token 着色；侧栏折叠是纯增量、最后。

**统一约束：**
- 切了主题 = 已持久化，不提供"预览/还原"语义。
- 任务中心默认隐藏，启动时不自动弹。
- 全程不引入 qfluentwidgets / 任何 GPL widget 库。

---

## 2. 主题系统（Phase 3 触发，Phase 5 收口）

### 2.1 文件布局
```
drama_shot_master/ui/
├── theme.py                      # 改造：tokens 加载 + apply_theme/titlebar 升级
└── styles/
    ├── theme.qss.tpl             # 新：模板，{bg}/{accent}/{radius} 占位符
    ├── tokens_dark.py            # 新：DARK = {"bg":"#1a1b1e", ...}
    └── tokens_light.py           # 新：LIGHT = {...}
```
旧的 `styles/dark.qss` 由 `theme.qss.tpl` 取代（占位符版本）。

### 2.2 Token 清单（首版）

| token | dark | light |
|---|---|---|
| `bg` 主背景 | `#1a1b1e` | `#fafafa` |
| `bg_alt` 次背景/卡片 | `#22232a` | `#ffffff` |
| `bg_elevated` 浮层/对话框 | `#2a2b32` | `#f5f6f7` |
| `fg` 主文字 | `#e5e6e8` | `#1a1b1e` |
| `fg_muted` 次要文字 | `#9aa0a6` | `#5f6368` |
| `border` 分隔线 | `#353740` | `#e0e2e6` |
| `accent` 强调（按钮主色/选中边） | `#4a9eff` | `#0066cc` |
| `success` | `#4ec98f` | `#1e8e3e` |
| `danger` | `#ff5c5c` | `#d93025` |
| `radius` 圆角 | `6px` | `6px` |
| `titlebar_bg` 原生标题栏 | `#1a1b1e` | `#fafafa` |

状态色（沿用 dark.qss 中 `_STATUS_COLORS`）暂保留当前色值（"生成中=蓝、失败=红、完成=绿、空闲=灰"），在两个 token 字典各列一组 `status_running / status_failed / status_done / status_idle`，浅色主题下浅化处理但保持语义同色相。

### 2.3 API

```python
# theme.py

DARK_TOKENS_PATH = "tokens_dark"        # 模块 import 路径
LIGHT_TOKENS_PATH = "tokens_light"

def _tokens(name: str) -> dict:
    """name='dark'|'light' → 返回 token 字典；未知名称回退 dark。"""
    if name == "light":
        from drama_shot_master.ui.styles.tokens_light import LIGHT
        return LIGHT
    from drama_shot_master.ui.styles.tokens_dark import DARK
    return DARK

def apply_theme(app, name: str = "dark") -> None:
    tokens = _tokens(name)
    tpl = (_QSS_DIR / "theme.qss.tpl").read_text(encoding="utf-8")
    app.setStyleSheet(tpl.format(**tokens))
    # 切主题后强制重 polish 所有顶层窗（含 dock/对话框）
    for w in app.topLevelWidgets():
        w.style().unpolish(w); w.style().polish(w); w.update()

def apply_titlebar(widget, name: str = "dark") -> None:
    """替代旧 apply_dark_titlebar。读 titlebar_bg token，给 Windows DWM 上色；非 Win 安静跳过。"""
    ...

def current_theme(cfg) -> str:
    return getattr(cfg, "theme", "dark") or "dark"
```

### 2.4 迁移策略（必须严格按顺序）

1. **保 dark 视觉不变（基线锁定）**
   - 拷贝 `dark.qss` → `theme.qss.tpl`
   - **整文件先做 `{` `}` 转义为 `{{` `}}`**（因 `.format()` 把裸花括号当占位符；必须脚本批处理，禁止手改）
   - 把 dark 配色字面值替换为 `{xxx}` 占位符（10-15 个 token）
   - `tokens_dark.py` 用原 dark 值填回
   - 启动 app → 视觉零差异（如肉眼可见差异立刻回退）

2. **加 light 变体**
   - 新 `tokens_light.py` 按 §2.2 表填值
   - 设置页主题 section 已就位时连通验证

3. **代码硬编码清扫**
   - `grep -rnE "setStyleSheet\(|QColor\(" drama_shot_master/ui/` 实测 **53 处**
   - 分类处理：
     - 局部 widget 样式（如配音 panel 高亮）→ 用 `objectName` + QSS 选择器
     - QPalette 设置 → 改 QSS
     - 状态色字典（如 `_STATUS_COLORS`）→ 集中到 theme.py 暴露 `status_color(name) -> str`，按当前主题返回 token
   - 每改一处后跑 `test_ui/` smoke 确认无回归

4. **持久化与启动**
   - `cfg.theme: "dark"|"light"`，默认 `"dark"`
   - `main.py` 启动 `apply_theme(app, current_theme(cfg))`；AppShell `showEvent` 调 `apply_titlebar(self, current_theme(self.cfg))`
   - **删除旧 `apply_dark_titlebar` 调用点**（AppShell `_titlebar_themed` 那段），改用新 `apply_titlebar`

### 2.5 测试
- `tests/test_ui/test_theme_smoke.py`（新）：
  - `apply_theme(app, "dark")` 后 `app.styleSheet()` 含某个 dark 标识色（如 `#1a1b1e`）
  - 切到 `"light"` 后含 light 标识色（如 `#fafafa`）、不含 dark 标识色
  - `apply_titlebar(widget, "light")` 不抛
  - dark→light→dark 循环切 3 次后 widget 仍能 show
- 既有 `test_window_icon_smoke` 保留。

### 2.6 风险与回避
- **QSS 裸花括号被 `.format` 误解** —— 整文件先 `{`/`}` 转义为 `{{`/`}}`，再插占位符；脚本化（不要手动）。
- **runtime repolish 不彻底** —— 已在 `apply_theme` 内 unpolish+polish 所有顶层窗；自绘控件（`AccentEditorWidget._AccentTimeline.paintEvent`）若缓存了颜色变量，需另调 `update()` 触发重绘。该控件目前每次 paintEvent 都从 QColor 字面量重建，问题不大；测试时回归一次浅色下时间轴显示。

---

## 3. UnifiedSettingsPage（Phase 3）

### 3.1 文件结构
```
drama_shot_master/ui/
├── dialogs/
│   └── unified_settings_dialog.py          # 新：壳 + 左树 + QStackedWidget + 保存编排
└── widgets/settings_sections/               # 新目录
    ├── __init__.py
    ├── runninghub_section.py                # 从旧 dialog 抽出表单 widget
    ├── translation_section.py
    ├── refine_section.py
    ├── imggen_section.py
    ├── dub_section.py
    ├── soundtrack_section.py
    └── theme_section.py                     # 新：主题切换 + light 预览
```

**旧 6 个 dialog 文件**：随本期**干净退场**（删 `drama_shot_master/ui/dialogs/{runninghub,translation,refine,soundtrack,dub,imggen}_settings_dialog.py`）。在删除前 grep 确认 import 点仅在 `app_shell.py`、统一替换。

### 3.2 SectionWidget 协议
```python
# 每个 section widget 类属性与方法约定：
class _SectionProto(QWidget):
    title: str                                   # 类属性，左树叶子文本（如 "RunningHub"）
    category: str                                # 类属性，左树分类（"平台核心"/"生成功能"/"辅助"/"外观"）
    def load_from(self, cfg) -> None: ...
    def save_to(self, cfg) -> None: ...
    def validate(self) -> tuple[bool, str]:       # 默认 (True, "")
        return (True, "")
```

每个 section 在 ctor 调 `load_from(cfg)` 自填，dialog 关时由壳遍历 `save_to(cfg)`。validate 失败 → 弹窗 + 切到该 section。

### 3.3 字段对照（实施前 plan 阶段需要把每个旧 dialog 的字段清单列全；下面只列概要）

| Section | 旧 dialog | 主要字段 |
|---|---|---|
| RunningHub | `runninghub_settings_dialog.py` | API key / workflow_id / 禁用水印 / [连通测试] |
| 翻译 | `translation_settings_dialog.py` | provider / base_url / model / api_key |
| 提示词优化 | `refine_settings_dialog.py` | provider / base_url / model / api_key / system prompt |
| 出图 | `imggen_settings_dialog.py` | provider / base_url / model / api_key / 输出目录 / 无水印 / [连通测试] |
| 配音 | `dub_settings_dialog.py` | `voice_design` workflow_id / `voice_clone` workflow_id / 输出目录 |
| 配乐 | `soundtrack_settings_dialog.py` | workflow_id / seeds_count / crossfade / accent_big_threshold / snap_window / output_dir |
| 主题 | （新）theme_section.py | combo 深色/浅色 |

> plan 阶段每个 section 需单独列字段表，确保零字段遗漏。

### 3.4 UnifiedSettingsDialog 编排

```python
class UnifiedSettingsDialog(QDialog):
    def __init__(self, app, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置"); self.resize(800, 600)
        self._app = app; self._cfg = cfg
        self._sections: list[_SectionProto] = self._build_sections()
        self._build_ui()
        self._restore_last_section()

    def _build_sections(self):
        from drama_shot_master.ui.widgets.settings_sections import (
            RunningHubSection, TranslationSection, RefineSection,
            ImgGenSection, DubSection, SoundtrackSection, ThemeSection)
        return [
            RunningHubSection(self._cfg),
            TranslationSection(self._cfg),
            RefineSection(self._cfg),
            ImgGenSection(self._cfg),
            DubSection(self._cfg),
            SoundtrackSection(self._cfg),
            ThemeSection(self._app, self._cfg),   # 主题 section 需要 app handle
        ]

    def _build_ui(self):
        split = QSplitter(Qt.Horizontal)
        # 左：QTreeWidget，按 category 分组、叶子=title
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        cats = {}
        for s in self._sections:
            top = cats.setdefault(s.category, None)
            if top is None:
                top = QTreeWidgetItem([s.category]); self.tree.addTopLevelItem(top); cats[s.category] = top
            leaf = QTreeWidgetItem([s.title]); leaf.setData(0, Qt.UserRole, s); top.addChild(leaf)
        self.tree.expandAll()
        self.tree.itemSelectionChanged.connect(self._on_tree_sel)
        split.addWidget(self.tree); self.tree.setMaximumWidth(220)
        # 右：QStackedWidget
        self.stack = QStackedWidget()
        for s in self._sections: self.stack.addWidget(s)
        split.addWidget(self.stack); split.setSizes([200, 600])
        # 底栏
        bar = QHBoxLayout(); bar.addStretch(1)
        self.btn_cancel = QPushButton("取消"); self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("保存"); self.btn_save.clicked.connect(self._on_save); self.btn_save.setDefault(True)
        bar.addWidget(self.btn_cancel); bar.addWidget(self.btn_save)
        root = QVBoxLayout(self); root.addWidget(split, 1); root.addLayout(bar)

    def _on_save(self):
        # 校验所有 section
        for i, s in enumerate(self._sections):
            ok, why = s.validate()
            if not ok:
                QMessageBox.warning(self, "设置无效", why)
                self.stack.setCurrentIndex(i)
                # 同时切左树
                self._select_section_in_tree(s); return
        # 全过 → 落盘
        for s in self._sections: s.save_to(self._cfg)
        # 记上次访问 section
        cur = self._current_section()
        if cur is not None: self._cfg.update_settings(last_settings_section=cur.title)
        self.accept()

    def _on_tree_sel(self):
        s = self._current_section()
        if s is None: return
        self.stack.setCurrentWidget(s)
```

### 3.5 ThemeSection（实时持久化、例外于"保存"按钮）

```python
class ThemeSection(QWidget):
    title = "主题"; category = "外观"
    def __init__(self, app, cfg, parent=None):
        super().__init__(parent)
        self._app = app; self._cfg = cfg
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("主题"))
        self.combo = QComboBox(); self.combo.addItems(["深色", "浅色"])
        cur = "浅色" if getattr(cfg, "theme", "dark") == "light" else "深色"
        self.combo.setCurrentText(cur)
        self.combo.currentTextChanged.connect(self._apply_now)
        lay.addWidget(self.combo); lay.addStretch(1)

    def _apply_now(self, txt):
        from drama_shot_master.ui.theme import apply_theme, apply_titlebar
        name = "dark" if txt == "深色" else "light"
        apply_theme(self._app, name)
        # 给当前 dialog 自己的窗 + 父 AppShell 都更新原生标题栏
        apply_titlebar(self.window(), name)
        top = self.window().parent()
        if top is not None: apply_titlebar(top, name)
        self._cfg.update_settings(theme=name)        # 实时持久化

    def load_from(self, cfg): pass    # ctor 已读
    def save_to(self, cfg): pass      # 无延迟保存
    def validate(self): return (True, "")
```

### 3.6 AppShell 入口改造

```python
# app_shell.py:_open_settings_menu —— 删除现有 6 项菜单（删整个方法 + sidebar.settingsRequested 改连法）
self.sidebar.settingsRequested.connect(self._open_unified_settings)

def _open_unified_settings(self):
    from drama_shot_master.ui.dialogs.unified_settings_dialog import UnifiedSettingsDialog
    UnifiedSettingsDialog(QApplication.instance(), self.cfg, parent=self).exec()
```

并删除 6 个 `_open_<X>_settings` 方法、对应 import。

### 3.7 测试
- `tests/test_ui/test_unified_settings_dialog_smoke.py`（新）：
  - 构造 dialog（用 mock cfg）→ 左树 4 个分类 + 共 7 个叶子（含主题）
  - 切叶子 → `stack.currentWidget()` 是对应 section
  - 每个 section `load_from(mock_cfg)` 然后 `save_to(mock_cfg)` 不崩
  - 主题 combo 切 "浅色" → `apply_theme` 调用记录 + `mock_cfg.update_settings` 收到 `theme="light"`
  - `_on_save` 全过 → cfg.update_settings 收到合并字段
- 旧 6 个 dialog smoke 测试**随旧 dialog 一并删除**。

### 3.8 风险
- **字段遗漏** —— plan 阶段须人工对照旧 6 个 dialog 的全部字段；落 plan 时每个 section 提供独立字段清单作为 checklist。
- **连通测试异步** —— RunningHubSection / ImgGenSection 里的"连通测试"按钮调 worker thread；section unmount（dialog 关）时要取消 worker，避免回调击中已销毁 widget。实现里在 section 加 `closeEvent`/`hideEvent` 或在 dialog `reject/accept` 前调 `section.cancel_workers()`。

---

## 4. TaskCenterDock（Phase 4）

### 4.1 文件
```
drama_shot_master/
├── core/
│   └── task_aggregator.py             # 新
└── ui/widgets/
    └── task_center_dock.py            # 新
```

### 4.2 TaskRecord + TaskAggregator

```python
# core/task_aggregator.py
from dataclasses import dataclass

@dataclass
class TaskRecord:
    kind: str            # "video" | "imggen" | "dub" | "soundtrack"
    task_id: str
    name: str
    status: str          # "生成中" / "失败" / "完成" / "空闲"
    last_result: str     # 输出路径；空串=未出

class TaskAggregator:
    """读 cfg + 3 stores + 3 managers (取实时 status)。无事件订阅；调用方按需 snapshot()。"""
    def __init__(self, cfg, video_store, dub_store, imggen_store, managers: dict):
        self.cfg = cfg
        self._video_s = video_store; self._dub_s = dub_store; self._imggen_s = imggen_store
        self._managers = managers     # {"video":VideoTaskManagerPanel, "dub":..., "imggen":...}

    def snapshot(self) -> list[TaskRecord]:
        out = []
        for kind, store in (("video", self._video_s),
                            ("dub", self._dub_s),
                            ("imggen", self._imggen_s)):
            mgr = self._managers.get(kind)
            for t in store.all():
                status = mgr.get_status(t.id) if mgr is not None else "空闲"
                out.append(TaskRecord(kind, t.id, t.name, status,
                                      getattr(t, "last_result", "") or ""))
        for d in getattr(self.cfg, "soundtrack_tasks", []):
            out.append(TaskRecord(
                "soundtrack", d.get("id", ""), d.get("name", ""),
                d.get("status", "空闲"), d.get("output", "")))
        return out
```

### 4.3 三个 Manager 加 `get_status(tid)` 公开方法

`VideoTaskManagerPanel` / `DubTaskManagerPanel` / `ImgGenTaskManagerPanel` 各加：
```python
def get_status(self, task_id: str) -> str:
    return self._live_status.get(task_id, "空闲")
```

### 4.4 TaskCenterDock

```python
class TaskCenterDock(QDockWidget):
    taskActivated = Signal(str, str)        # (kind, task_id)

    def __init__(self, aggregator, parent=None):
        super().__init__("任务中心", parent)
        self.setAllowedAreas(Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self._agg = aggregator
        self._recent_complete_limit = 20
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        w = QWidget(); v = QVBoxLayout(w)
        # 顶 toolbar
        tb = QHBoxLayout()
        self.lbl_counts = QLabel(""); tb.addWidget(self.lbl_counts, 1)
        self.btn_refresh = QPushButton("⟳"); self.btn_refresh.setFlat(True)
        self.btn_refresh.clicked.connect(self.refresh); tb.addWidget(self.btn_refresh)
        v.addLayout(tb)
        # 3 分组
        self.list_running = QListWidget(); self.list_failed = QListWidget(); self.list_done = QListWidget()
        for grp_title, lst in (("生成中", self.list_running),
                                ("失败", self.list_failed),
                                ("最近完成", self.list_done)):
            box = QGroupBox(grp_title); bv = QVBoxLayout(box); bv.addWidget(lst)
            lst.itemDoubleClicked.connect(self._on_double_click)
            v.addWidget(box)
        self.setWidget(w)

    def refresh(self):
        records = self._agg.snapshot()
        running = [r for r in records if r.status == "生成中"]
        failed  = [r for r in records if r.status == "失败"]
        # 最近完成：last_result 非空 + status="完成"；按 last_result mtime 倒序（不可得则原序），取前 N
        done    = [r for r in records if r.status == "完成" and r.last_result]
        done    = self._sort_recent(done)[: self._recent_complete_limit]
        self._fill(self.list_running, running)
        self._fill(self.list_failed,  failed)
        self._fill(self.list_done,    done)
        self.lbl_counts.setText(
            f"生成中 {len(running)} · 失败 {len(failed)} · 完成 {len(done)}")

    def _fill(self, lst, records):
        lst.clear()
        for r in records:
            it = QListWidgetItem(self._row_text(r))
            it.setData(Qt.UserRole, (r.kind, r.task_id))
            lst.addItem(it)

    def _row_text(self, r: TaskRecord) -> str:
        suffix = (" · " + Path(r.last_result).name) if r.last_result else ""
        kind_lbl = {"video":"视频","imggen":"出图","dub":"配音","soundtrack":"配乐"}[r.kind]
        return f"[{kind_lbl}] {r.name}{suffix}"

    def _on_double_click(self, item):
        kind, tid = item.data(Qt.UserRole)
        self.taskActivated.emit(kind, tid)

    def _sort_recent(self, records: list[TaskRecord]) -> list[TaskRecord]:
        """按 last_result 文件 mtime 倒序；不可读则按原序。"""
        def key(r):
            try: return -Path(r.last_result).stat().st_mtime
            except Exception: return 0
        return sorted(records, key=key)
```

### 4.5 AppShell 接入

```python
# _build_ui 末尾追加（在 setCentralWidget 之后）
from drama_shot_master.core.task_aggregator import TaskAggregator
from drama_shot_master.ui.widgets.task_center_dock import TaskCenterDock
self._task_agg = TaskAggregator(
    self.cfg, self.video_store, self.dub_store, self.imggen_store,
    managers={"video": self._video_manager(),
              "dub":   self._dub_manager(),
              "imggen": self._imggen_manager()})
self.task_center_dock = TaskCenterDock(self._task_agg, parent=self)
self.addDockWidget(Qt.RightDockWidgetArea, self.task_center_dock)
self.task_center_dock.setVisible(getattr(self.cfg, "task_center_visible", False))
self.task_center_dock.taskActivated.connect(self._activate_task)
self.task_center_dock.visibilityChanged.connect(
    lambda v: self.cfg.update_settings(task_center_visible=v))
```

```python
def _activate_task(self, kind: str, tid: str):
    key = {"video":"video_gen", "dub":"dubbing",
           "imggen":"imggen", "soundtrack":"soundtrack"}[kind]
    self.switchTo(self.pages[key])
    mgr = getattr(self.pages[key], "manager", None)
    if mgr is not None and hasattr(mgr, "_select_task"):
        mgr._select_task(tid)
```

**已有 4 个状态 handler 末尾追加 `self.task_center_dock.refresh()`：**
- `_on_task_status` / `_on_task_result`（video）
- `_on_dub_status` / `_on_dub_result`
- `_on_imggen_status` / `_on_imggen_result`
- `_on_soundtrack_status` / `_on_soundtrack_result`

### 4.6 ProjectCommandBar 加 toggle

```python
# project_command_bar.py
class ProjectCommandBar(QWidget):
    taskCenterToggled = Signal(bool)
    ...
    self.btn_task_center = QPushButton("⧉ 任务"); self.btn_task_center.setCheckable(True)
    self.btn_task_center.toggled.connect(self.taskCenterToggled)
```

AppShell `_wire`：
```python
self.command_bar.taskCenterToggled.connect(self.task_center_dock.setVisible)
self.task_center_dock.visibilityChanged.connect(self.command_bar.btn_task_center.setChecked)
```

### 4.7 测试
- `tests/test_core/test_task_aggregator.py`（新）：
  - mock cfg.soundtrack_tasks（含状态字段） + 3 mock stores（实例化用真 TaskStore.from_list） + 3 mock managers（`get_status` 返回固定字典）→ `snapshot()` 返回正确数量与字段。
- `tests/test_ui/test_task_center_dock_smoke.py`（新）：
  - 用桩 aggregator（写死 4 条混合记录：1 生成中 / 1 失败 / 2 完成）→ refresh 后 3 list 行数对、counts label 文本对。
  - `itemDoubleClicked` 触发 `taskActivated` 发出 `(kind,tid)`。
- `tests/test_ui/test_app_shell_smoke.py` 加 1 用例：dock 存在、默认不可见；toggle 按钮 toggled→dock setVisible 切换；`_activate_task("video", tid)` 切到 video_gen 页。

### 4.8 风险
- **长列表刷新性能** —— 每次 status 改全表刷；v1 接受，任务数 <100 时无感。如实测卡，后续改增量更新单行。
- **mtime 取不到** —— `_sort_recent` 已有 try/except 兜底为 0。

---

## 5. CollapsibleFlowSidebar + 精修（Phase 5）

### 5.1 可折叠 FlowSidebar
改造 `drama_shot_master/ui/widgets/flow_sidebar.py`（**不新增文件**）。

API 增量：
```python
class FlowSidebar(QWidget):
    collapsedChanged = Signal(bool)
    EXPANDED_WIDTH = 200
    COLLAPSED_WIDTH = 56

    def __init__(self):
        ...
        self._collapsed = False
        self._anim = None     # QPropertyAnimation 引用，防 GC
        self._build_header()  # 新：顶部右上角 « 按钮
        ...

    def set_collapsed(self, v: bool, animate: bool = True):
        if v == self._collapsed: return
        self._collapsed = v
        target = self.COLLAPSED_WIDTH if v else self.EXPANDED_WIDTH
        if v:
            # 折叠：先切布局（隐藏 label/标题），再起动画收缩
            self._apply_collapsed_layout(True)
            self._animate_width(target, animate)
        else:
            # 展开：先起动画扩张，动画结束才把 label 显回去
            def after():
                self._apply_collapsed_layout(False)
            self._animate_width(target, animate, on_finished=after)
        self.collapsedChanged.emit(v)

    def _animate_width(self, target, animate, on_finished=None):
        if not animate:
            self.setMaximumWidth(target); self.setMinimumWidth(target)
            if on_finished: on_finished()
            return
        anim = QPropertyAnimation(self, b"maximumWidth", self)
        anim.setDuration(160); anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(self.maximumWidth()); anim.setEndValue(target)
        if on_finished: anim.finished.connect(on_finished)
        anim.finished.connect(lambda: self.setMinimumWidth(target))
        anim.start(); self._anim = anim

    def _apply_collapsed_layout(self, collapsed: bool):
        """折叠：阶段标题隐藏；每项 label 隐藏（仅图标）；tooltip 兜底。
        展开：全部恢复。每项 widget 是构造时就建好的，这里只切 setVisible/property。"""
        for w in self._phase_title_widgets:
            w.setVisible(not collapsed)
        for w, label_text, full_tooltip in self._item_label_widgets:
            w.setVisible(not collapsed)
        for item_btn, label_text, phase_title in self._item_buttons:
            item_btn.setToolTip(f"{phase_title} › {label_text}" if collapsed else "")
```

**折叠态视觉规则：**
- 宽度 56px（图标 32 + 左右内外边距）。
- 阶段标题（"① 素材准备" 等）隐藏；条目间用 1px `border` 分隔阶段（QSS 选择器在折叠态生效）。
- 每项 label 隐藏，仅留图标；选中态背景保留。
- 折叠/展开按钮始终在顶部右上角，对称两种字符 `«` / `»`。

**持久化：** `cfg.sidebar_collapsed: bool`，默认 `False`。AppShell `_restore_state` 启动调 `sidebar.set_collapsed(cfg.sidebar_collapsed, animate=False)`。

### 5.2 过时 MainWindow 注释清理
5 处纯 docstring/comment 改名：
- `drama_shot_master/core/submit_debug.py:4,20`：`MainWindow` → `AppShell`
- `drama_shot_master/ui/panels/base_panel.py:1,14`：`MainWindow` → `AppShell`
- `drama_shot_master/ui/widgets/project_command_bar.py:3`：`旧 MainWindow 左栏` → `旧 MainWindow 左栏（已退役）`

### 5.3 重命名一致性 audit
```bash
grep -rn '"重命名"\|"Rename"' drama_shot_master/ui/panels/
```
预计为空（你前期 commit `db04887` 已统一）。如有遗留按钮 → 删除并改为 inline 改名。spec 阶段先记录，plan 阶段列为一步。

### 5.4 测试
- `tests/test_ui/test_flow_sidebar_smoke.py` 增/改：
  - 默认 `_collapsed=False`，`maximumWidth() == EXPANDED_WIDTH`
  - `set_collapsed(True, animate=False)` → `maximumWidth() == COLLAPSED_WIDTH` + 某一 label widget `.isVisible() is False`
  - 反向 `set_collapsed(False, animate=False)` → label 重新可见
  - `collapsedChanged` 信号发出次数对
- `tests/test_ui/test_app_shell_smoke.py` 加 1 用例：折叠按钮 click → sidebar `_collapsed` 翻转 + `cfg.update_settings(sidebar_collapsed=True)` 被调。

### 5.5 风险
- **动画过程中 label 抖动** —— 已在 `set_collapsed` 顺序里规范：折叠时**先**切布局再起动画收缩；展开时先动画扩张、`finished` 才显回 label。
- **折叠态下顶部按钮宽度** —— 按 32px 设计，配 `«`/`»` 字符；嵌在 `_build_header` 里、不参与折叠态隐藏。

---

## 6. 测试策略汇总

新增测试文件：
1. `tests/test_ui/test_theme_smoke.py`
2. `tests/test_ui/test_unified_settings_dialog_smoke.py`
3. `tests/test_core/test_task_aggregator.py`
4. `tests/test_ui/test_task_center_dock_smoke.py`

修改测试文件：
- `tests/test_ui/test_flow_sidebar_smoke.py` —— 增折叠相关用例
- `tests/test_ui/test_app_shell_smoke.py` —— 增 toggle/折叠/dock 用例（继续用 module-scoped fixture，但 dock 默认隐藏，构造一次的开销可忽略）

删除：
- 旧 6 个 `dialogs/*_settings_dialog.py`
- 它们对应的 smoke 测试文件（如有）

acceptance 总闸：
- `grep -rn qfluentwidgets drama_shot_master/ tests/` 仅余文档/注释中的字面提及（不构成 import/usage）
- `apply_theme(app, "light")` 后 `app.styleSheet()` 不含某个 dark 标识色（如 `#1a1b1e`）
- 6 个旧 settings dialog 文件不存在；`unified_settings_dialog.py` 存在
- AppShell 启动后 `getattr(w, "task_center_dock", None) is not None`
- `flow_sidebar.set_collapsed(True/False, animate=False)` 各跑一次不崩

---

## 7. 非目标 / 不做

- 不抽取 `TaskStore` ABC、不把 soundtrack 从 dict-list 迁到 store（已确认任务中心只读 + 跳转，无统一抽象需求）。
- 不引入跟随系统主题（启动时读 Windows/Linux 深浅色）——只手动深/浅二选一。
- 不做 sidebar hover 浮出（仅手动两态切换）。
- 不做"主题预览/还原"——切了即定。
- 不重排 PHASES / FUNCS 顺序（与现状一致）。

---

## 8. 后续阶段（出本期范围）

本期收口后 GUI 大件完成：
- 主题系统 + 实时切换（深/浅二选）
- 统一设置页
- 任务中心（只读）
- 折叠侧栏

潜在后续工作（非本期）：
- 跟随系统主题
- 任务中心增加"重跑/取消/删除"等动作（需 TaskStore ABC 化）
- 自定义主题（用户配色）
- 侧栏拖拽排序 PHASES
