# GUI 外壳改用原生 PySide6 + QSS 设计（去 qfluentwidgets）

- 日期：2026-05-27
- 关系：本设计**取代** Phase 1 的实现substrate；UX 设计仍以
  [`2026-05-27-gui-shell-redesign-design.md`](2026-05-27-gui-shell-redesign-design.md) 为准（不变）。
- 触发原因：`qfluentwidgets` 是 **GPLv3**，与本产品（闭源商用，含 `licensing/` 激活模块）不兼容。
  选择用 **原生 PySide6（LGPLv3）+ QSS** 重做外壳，而非购买商业授权。

---

## 1. 目标与不变量

**不变（沿用已批准 UX）**：流程式编号侧栏 `① 素材准备 → ② 分镜创作 → ③ 视频出片`；
主区两种页型（批处理 BatchToolPage / 任务管理 *TaskManagerPanel，后者沿用双击开窗，Phase 2 再做内嵌主-详）；
全局顶部命令栏（打开目录/设置输出/计数）；底部设置与帮助入口；影视冷蓝 `#2563EB` 深色。

**本设计的唯一目标**：把外壳实现从 qfluentwidgets 换成原生 PySide6 + QSS，
使整个代码库**不含 GPL 依赖**，可商用。验收时 `grep -r qfluentwidgets drama_shot_master/` 必须为空。

**复用不动**（与框架无关）：`nav_config.py`（仅 `ICONS` 值改为 svg 路径）、`BatchToolPage`、
AppShell 的全部控制器逻辑（任务窗回调、stores、`_open_dir`/`_set_out_dir`、`_restore_state`、
`closeEvent`、license watch）、`ProjectCommandBar`（仅换按钮控件）。

## 2. 外壳架构：`AppShell(QMainWindow)`

基类 `FluentWindow → QMainWindow`。中央 widget 用普通布局：

```
QWidget(central) / QVBoxLayout(0 margin)
├── ProjectCommandBar                 # 顶部命令栏（普通布局，不再做 FluentWindow 布局手术）
└── QHBoxLayout
    ├── FlowSidebar  (新)             # 替换 NavigationInterface
    └── QStackedWidget                # 7 个页（不变）
```

- `switchTo(page)`：`self.stack.setCurrentWidget(page)` + `self.sidebar.set_active(key)`。
- `_current_key()` / `breadcrumb_text()`：基于 `self.stack.currentWidget()`，逻辑不变。
- 标题栏：原生（QMainWindow）→ 应用图标自动显示；`showEvent` 中 `apply_window_icon(self)` 显式设窗口图标 +
  `apply_dark_titlebar(self)`（Win11 深色，已有）。
- 菜单：底部「设置」「帮助/关于」改用原生 `QMenu`（替换 `RoundMenu`）。
- 所有 `_open_*`/`_on_*`/`_persist_*`/`closeEvent`/license 方法**保持不变**。

## 3. 新组件 `FlowSidebar(QWidget)`

唯一实质新代码。职责：渲染导航 + 折叠。位置 `drama_shot_master/ui/widgets/flow_sidebar.py`。

- **结构**：按 `nav_config.PHASES` 渲染 —— 每个阶段一个非点击的 section 标题 `QLabel`
  （objectName `navPhase`），其下每个 key 一个 checkable `QToolButton`（icon+text，
  `ToolButtonTextBesideIcon`），统一加入一个 `QButtonGroup`（互斥）。底部分隔后放
  「设置」「帮助/关于」两个 `QToolButton`（非互斥，点击触发回调）。
- **选中态**：选中按钮设 `property("selected", True)` + QSS 画蓝色左边条与高亮底；
  `set_active(key)` 用于外部（restore / switchTo）同步选中。
- **信号**：`currentChanged = Signal(str)`（发 key）；功能按钮点击 → 发对应 key。
  设置/帮助按钮 → 独立 `settingsRequested`/`helpRequested` 信号（AppShell 分别连到 `_open_settings_menu`/`_open_help_menu`）。
- **折叠**：顶部一个折叠 `QToolButton`（≡）。折叠时：所有按钮
  `setToolButtonStyle(Qt.ToolButtonIconOnly)` + 文字转 tooltip、section 标题隐藏、
  用 `QPropertyAnimation` 动画 `maximumWidth`（展开 ~184 / 折叠 ~52）。`is_collapsed` 状态可持久化（可选，YAGNI 一期不存）。
- **图标**：`QIcon(str(path))`，path 来自 `nav_config.ICONS[key]`（见 §4）。
- 自包含、可独立单测（不依赖 AppShell）。

## 4. 图标：自带 SVG

折叠图标条需要真实图标。去掉 `FluentIcon`，自带 **9 个单色 SVG** 于 `drama_shot_master/assets/icons/`：
`cut.svg, photo.svg, erase.svg, palette.svg, video.svg, music.svg, mic.svg, settings.svg, help.svg`。
`nav_config.ICONS` 值由 FluentIcon 名改为文件名（解析时拼 `assets/icons/<name>`）：

```python
ICONS = {
    "split": "cut.svg", "combine": "photo.svg", "trim": "erase.svg",
    "imggen": "palette.svg", "video_gen": "video.svg",
    "soundtrack": "music.svg", "dubbing": "mic.svg",
}
ICON_SETTINGS = "settings.svg"
ICON_HELP = "help.svg"
```
提供一个 helper（如 `nav_config.icon_path(name)` 或在 sidebar 内）拼绝对路径；
文件缺失时回退为无图标（仅文字），不崩。SVG 为简单线性单色图标，描边色走中性灰，
靠 QSS/不变色即可（一期不要求随主题反色）。

## 5. 主题：扩展 `dark.qss`

去掉 `init_fluent_theme`/`THEME_ACCENT`/`setThemeColor`。主题色 `#2563EB` 直接写进 QSS。
扩展现有 `drama_shot_master/ui/styles/dark.qss`（368 行）新增选择器：

- `#FlowSidebar`（背景、右边框）、`QLabel#navPhase`（小字灰、字距）、
  `FlowSidebar QToolButton`（内边距/圆角/hover）、
  `FlowSidebar QToolButton[selected="true"]`（高亮底 + 左侧 3px `#2563EB` 边条，
  用 border-left 或叠加实现）。
- `#ProjectCommandBar`（轻微背景区分 chrome 与内容，呼应用户对对比度的要求）+ 其中按钮/标签。
- `QPushButton#AccentButton`（主操作蓝按钮 `#2563EB`，hover/pressed 态）。
- 语义色（完成 `#4EC98F` / 进行中 `#4A9EFF` / 失败 `#FF5C5C`）维持现状。

`main.py` 保留 `apply_theme(app)`（已加载 dark.qss），删 `init_fluent_theme`。
浅色主题：本期仍不做（与原 UX spec 一致，留 Phase 3）。

## 6. qfluentwidgets 移除清单（验收 grep 为零）

| 文件 | 改动 |
|------|------|
| `ui/app_shell.py` | 基类→`QMainWindow`；重写 `_build_nav`(用 FlowSidebar)、`_build_command_bar`(普通布局)、`_open_settings_menu`/`_open_help_menu`(用 `QMenu`)、`switchTo`、窗口图标；删所有 qfluentwidgets import；控制器方法不动 |
| `ui/widgets/project_command_bar.py` | 改用 `QPushButton`（删 qfluentwidgets 尝试导入与回退分支）；QSS 化 |
| `ui/theme.py` | 删 `init_fluent_theme` 与 `THEME_ACCENT`；新增 `apply_window_icon(widget)`（§7） |
| `main.py` | 删 `init_fluent_theme` 的 import 与调用；其余不变 |
| `ui/nav_config.py` | `ICONS` 值→svg 文件名；加 `ICON_SETTINGS`/`ICON_HELP` 与 `icon_path()` helper |
| `ui/widgets/flow_sidebar.py` | **新增**（§3） |
| `assets/icons/*.svg` | **新增** 9 个图标（§4） |
| `ui/styles/dark.qss` | 扩展（§5） |
| `ui/main_window.py` | **删除**（旧横向按钮主窗，已被 AppShell 取代）|
| `tests/test_ui/test_fluent_theme_smoke.py` | **删除**（主题改纯 QSS）|
| `tests/test_ui/test_main_window_soundtrack_smoke.py` | 更新：`FUNCS` 改从 `nav_config` 导入；删除针对 `MainWindow` 的断言（或改为针对 `AppShell`）|

`core/`、`providers/`、`config.py`、各 panel/window/store **零改动**。

## 7. theme.py 新增 `apply_window_icon`

把找图标路径的逻辑抽出复用，并给窗口（而非仅 QApplication）设图标：

```python
def _find_app_icon_path(name="app_icon"):
    for ext in (".ico", ".png", ".svg"):
        p = _ASSET_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None

def apply_window_icon(widget, name="app_icon"):
    p = _find_app_icon_path(name)
    if p:
        from PySide6.QtGui import QIcon
        widget.setWindowIcon(QIcon(str(p)))
```
`apply_app_icon` 复用 `_find_app_icon_path`。AppShell（及各任务窗，可选）调用 `apply_window_icon(self)`。

## 8. 测试

- 新 `tests/test_ui/test_flow_sidebar_smoke.py`：渲染 7 功能项 + 3 阶段标题；
  点击功能按钮发 `currentChanged(key)`；`set_active(key)` 设选中；
  折叠切换后按钮为 IconOnly、`maximumWidth` 收窄；展开还原。
- `tests/test_ui/test_app_shell_smoke.py`：适配 `QMainWindow`（仍：7 页、命令栏存在、
  面包屑确定值、`switchTo` 生效、`_refresh_counts`、`statusMessage` 不丢、页切换同步选择）。
- 删 `test_fluent_theme_smoke.py`；更新 `test_main_window_soundtrack_smoke.py`。
- 验收：`grep -rl qfluentwidgets drama_shot_master/ tests/` 为空；`python -m pytest tests/` 全绿；
  `python -m drama_shot_master.main` 在 Windows 真机肉眼通过（侧栏/命令栏/折叠/标题栏图标/深色/蓝）。

## 9. 非目标（YAGNI）

- 不改 UX 设计、不改功能逻辑/算法/provider/数据模型。
- 不做内嵌主-详+浮出（Phase 2）、统一设置页（Phase 3）、全局任务中心抽屉（Phase 4）。
- 折叠状态持久化、侧栏宽度记忆：一期可不存。
- 浅色主题：留 Phase 3。
- SVG 图标随主题反色：一期用中性灰静态图标即可。

## 10. 风险

- **QToolButton 选中态 QSS**：`property("selected", ...)` 改变后需 `style().unpolish/polish` 才刷新——
  `set_active` 内显式 repolish。
- **折叠动画**：`maximumWidth` 动画 + 内容裁剪需设 `minimumWidth` 同步，避免控件挤压；
  headless 测试只断言末态宽度/按钮样式，不依赖动画过程。
- **删除 main_window.py**：确认无其它模块 import 它（已知仅旧测试导入 `FUNCS`/`MainWindow`，本设计一并更新）。
  删除前 `grep -rn "main_window import\|MainWindow" drama_shot_master/ tests/` 复核。
- **SVG 渲染**：PySide6 加载 SVG 图标需 `QtSvg` 可用（PySide6 自带）；构造 `QIcon(svg_path)` 即可。
