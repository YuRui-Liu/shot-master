# Drama-Shot-Master GUI 外壳重构设计

- 日期：2026-05-27
- 范围：**整体重构导航与外壳**，所有功能逻辑保持不变
- 技术：PySide6 + PyQt-Fluent-Widgets（已安装，当前 0 使用）
- 主色：影视冷蓝 `#4CC2FF`（浅）/ `#2563EB`（强调），深色默认 + 浅色可切换

---

## 1. 背景与目标

Drama-Shot-Master 是一款面向短剧分镜与视频制作的专业桌面软件，功能已较完整
（拆图、拼图、去白边、图片生成、视频生成、配乐、配音），但 GUI 是逐功能叠加而成，
缺乏「成熟专业软件」的统一外壳。本次目标：**在不改动任何功能逻辑的前提下，重做导航与外壳**，
让产品从「一堆脚本工具的拼盘」升级为「有制作流程感的专业软件」。

非目标见 §9。

## 2. 现状诊断（5 个核心摩擦点）

| # | 问题 | 现状 |
|---|------|------|
| ① | 配置散落 | 6 个配置藏在「设置」菜单，各自独立对话框（RunningHub/翻译/提示词优化/配乐/配音/图片生成）|
| ② | 导航不可扩展、无流程感 | 7 个功能挤成一行横向 `QPushButton`，靠 `QFrame` 分隔符分「图像/视频」两组，看不出制作先后顺序 |
| ③ | 左栏信息密度低 | 仅「目录/输出目录/计数」 |
| ④ | 两套交互范式打架 | 批处理类（拆/拼/去白边）用「中栏缩略图网格 + 右栏参数 + 底部执行」；生成类（图片/视频/配乐/配音）用「宽任务列表面板 + 双击另开 OS 任务窗」。靠 `_on_func_changed` 里的 `is_wide` 标志来回隐藏/显示控件 |
| ⑤ | 状态栏信息单薄 | 只有「就绪」+ 一个 `QProgressBar`；多任务并行时无全局可见的队列视图 |

已有的好底子：深色影视主题 + Windows DWM 深色标题栏；40 个 UI 文件模块化清晰；
任务管理器 + 任务窗范式适合长耗时生成；`BasePanel` 统一了 `validate/execute/select_mode` 接口契约。

## 3. 设计决策汇总（均已确认）

1. **尺度**：整体重构导航与外壳，功能逻辑全保留。
2. **导航**：流程式侧栏，三个带编号的阶段
   `① 素材准备 → ② 分镜创作 → ③ 视频出片`。
3. **主区范式**：窗内「主-详」（master-detail）为默认；每个任务有「⧉ 浮出独立窗」按钮；
   **多窗并行是硬需求**（同时跑视频/图片/音频以加速产出）。
4. **设置**：统一设置页（侧栏底部进入，左分类右参数，可搜索）。
5. **视觉**：影视冷蓝，深色默认 + 设置内浅/深切换。语义色固定：
   绿 `#4EC98F`=完成、黄/蓝 `#4A9EFF`=进行中、红 `#FF5C5C`=失败。

## 4. 外壳架构：组件分解

重构集中在 `drama_shot_master/ui/`，新增一个外壳层，复用所有现有 panel/window/dialog。

```
AppShell  (FluentWindow / MSFluentWindow 派生)
├── NavigationInterface              侧栏：流程式分阶段导航（§4.1）
├── 顶部面包屑 BreadcrumbBar          当前阶段 › 当前功能（§4.2）
├── ContentHost (QStackedWidget)     主区，每个功能一页（§4.3）
│   ├── BatchToolPage   ×3           拆图/拼图/去白边：图库网格+参数+执行
│   └── TaskWorkspacePage ×4         图片/视频/配乐/配音：主-详+浮出
├── GlobalTaskCenter                 底部全局任务中心（§4.4）
└── SettingsPage                     统一设置页（§4.5）
```

### 4.1 流程式侧栏 NavigationInterface

- 用 Fluent `NavigationInterface`（或 `FluentWindow` 自带的导航）。
- 三个阶段用 `addItem` 的分组 + 阶段标题文本：
  - **① 素材准备**：拆图、拼图、去白边
  - **② 分镜创作**：图片生成
  - **③ 视频出片**：视频生成、配乐、配音
- 选中项：左侧蓝色高亮条 + 圆角底（Fluent 默认行为）。
- 正在运行任务的功能项右侧显示一个小圆点指示（复用 `_live_status`）。
- 底部固定项：**设置**、**帮助 / 关于**。
- 支持折叠成纯图标条（`NavigationItemPosition` + 折叠按钮，Fluent 自带）。
- 顺序与现有 `FUNCS` 一致，仅展示形态从横向按钮改为侧栏分组。

### 4.2 面包屑 BreadcrumbBar

主区顶部一行：`③ 视频出片 › 视频生成`，强化用户在制作流程中的位置。
随侧栏选择联动更新。

### 4.3 ContentHost：两种主区布局

主区仍是一个 `QStackedWidget`（替换现有 `self.stack`），每功能一页。
两种页型复用同一外壳 chrome（面包屑、内边距、配色）：

**(a) BatchToolPage —— 拆图 / 拼图 / 去白边**

- 无任务列表。布局：左侧「图库网格」（复用现有 `ThumbnailGrid`）+ 右侧参数面板（复用现有 `SplitPanel/CombinePanel/TrimPanel`）+ 底部「预览 / 执行」。
- 即把现有「中栏 thumb + 右栏 panel + 底部 act」整体收进这一页，不再靠 `is_wide` 在主窗层级隐藏控件。
- 现有 `BasePanel.validate/execute/select_mode/has_preview/overlay_spec` 契约**不变**。

**(b) TaskWorkspacePage —— 图片生成 / 视频生成 / 配乐 / 配音**

- 主-详布局：
  - **master（左）**：任务列表 = 现有 `*TaskManagerPanel`（已是表格/列表 + 新建/复制/删除）。
  - **detail（右）**：选中任务后内嵌该任务的编辑器（现有 `VideoPanel` / `imggen` / `dub` / `soundtrack` 编辑器）。
- detail 顶部操作条：任务名 + 状态 pill + **`⧉ 浮出独立窗`** + 主操作（生成/提交）。
- **浮出机制**：点「浮出」时，把当前 detail 编辑器移交给现有 `*TaskWindow`（如 `VideoTaskWindow`），
  与今天的「双击开窗」完全等价；窗内 detail 区置空或显示「已在独立窗编辑」。多个浮出窗可并行。
- 关闭浮出窗时编辑器收回内嵌区（或按现有逻辑落盘）。

> 关键复用：`*TaskManagerPanel` 天然就是 master；`*TaskWindow` 内嵌的 editor 天然就是 detail。
> 重构只是让 detail **默认内嵌**、按钮触发才浮出，而非永远开窗。现有信号
> （`taskRenamed/statusChanged/resultReady/timelineDirty/closed`）保持不变。

### 4.4 GlobalTaskCenter 全局任务中心（底部）

替换现状单薄的状态栏。一行常驻条：

- 汇总计数：`▶ N 运行　⏸ N 排队　✓ N 完成`。
- 并行分类计数：`视频×N　图片×N　音频×N`（直接服务多窗并行出片需求）。
- `▲ 展开队列`：拉起一个抽屉（`QWidget` 浮层或 Fluent `Flyout`），列出所有任务（含浮出窗中的）及进度，可点击聚焦/打开对应任务。
- 数据来源：聚合现有各 `*TaskStore` 的状态 + 各 manager panel 的 `_live_status`。
- 单条进度仍可用现有 `QProgressBar` 思路，移入抽屉/条内。

### 4.5 统一设置页 SettingsPage

- 侧栏底部「设置」进入一个独立页（不是对话框）。
- 左侧分类、右侧参数（Fluent `SettingCardGroup` / `ScrollArea`）。建议分类：
  - **账号与 API**：RunningHub 配置
  - **生成**：图片生成、提示词优化
  - **音频**：配乐、配音
  - **翻译**：翻译配置
  - **外观**：深/浅主题切换、主题色、缩略图尺寸
- 实现策略：**不重写 6 个配置的表单逻辑**，而是把现有 6 个 dialog 的内容控件抽出/嵌入到设置页对应分组中（dialog 类可保留为薄壳或逐步迁移）。一期可先做「设置页 = 一个带左侧分类列表的容器，点分类打开对应已有配置区」，降低风险。
- 顶部可留搜索框（YAGNI：一期可选）。

## 5. 视觉规范

| 项 | 值 |
|----|----|
| 主题 | 深色默认，浅色可切换（Fluent `setTheme(Theme.DARK/LIGHT)`）|
| 主题色 | `setThemeColor("#2563EB")`；高亮/链接近 `#4CC2FF` |
| 语义色 | 完成 `#4EC98F`，进行中 `#4A9EFF`，失败 `#FF5C5C`，空闲 `#9AA0A6`（沿用现有 `_STATUS_COLORS`）|
| 标题栏 | 沿用现有 `apply_dark_titlebar`（DWM）；浅色模式时同步切换 caption 配色 |
| 圆角/间距 | 卡片/按钮圆角 6–8px；导航项内边距约 7×11；遵循 Fluent 默认度量 |
| 组件映射 | `QPushButton→PushButton/PrimaryPushButton`；`QLineEdit→LineEdit`；`QComboBox→ComboBox`；`QTableWidget→TableWidget`；进度→`ProgressBar/IndeterminateProgressBar`；信息提示→`InfoBar`；下拉浮层→`Flyout` |

无障碍/对比度：选中态、状态色在深色背景上须有清晰对比（呼应历史反馈
「视觉对比度要够、状态一眼可辨」）。

## 6. 与现有代码的映射

| 现有 | 重构后去向 |
|------|-----------|
| `ui/main_window.py`（`QMainWindow` + 横向按钮 + 三栏 splitter）| 改为 `ui/app_shell.py`（`FluentWindow` 派生）；菜单栏精简（文件/退出保留，设置移入设置页）|
| `FUNCS` 列表 + `QButtonGroup` 横向切换 | 改为侧栏 `NavigationInterface` 注册，分阶段；保留 key 与 `last_active_function` 持久化逻辑 |
| `_on_func_changed` 的 `is_wide` 分支 | 删除；改为「每功能一页」，页自身决定布局，无需主窗隐藏控件 |
| `SplitPanel/CombinePanel/TrimPanel` | **不变**，被装进 `BatchToolPage` |
| `*TaskManagerPanel`（video/imggen/dub/soundtrack）| **不变**，作为 master 装进 `TaskWorkspacePage` |
| `*TaskWindow`（video/imggen/dub/soundtrack）| 保留，仅作为「浮出」目标；外观统一为 Fluent 子窗 |
| 6 个 `*SettingsDialog` | 内容迁入 `SettingsPage` 分组；类可保留为过渡 |
| `ThumbnailGrid`/`PreviewDialog`/`theme.py` | 复用；`theme.py` 增加 Fluent 主题初始化 + 浅/深切换 |
| 状态栏 | 替换为 `GlobalTaskCenter` |

所有 `*TaskStore`、`core/`、`providers/`、`config.py` **零改动**。

## 7. 迁移策略与风险

- **分期**：① 引入 `AppShell` + 侧栏 + 把现有 panel 原样塞进页（保留双击开窗），先跑通新外壳；
  ② 实现内嵌 detail + 浮出按钮；③ 设置页；④ 全局任务中心；⑤ Fluent 控件逐面板替换 + 浅/深主题。
  每期可独立验收，主流程始终可用。
- **风险**：Fluent `FluentWindow` 与现有 DWM 标题栏定制可能冲突 → 一期先验证标题栏共存方案。
- **风险**：detail 编辑器在「内嵌 ↔ 浮出」间 reparent 时的状态/落盘 → 复用现有 `timelineDirty`/`payload` 落盘点，浮出/收回时各落盘一次。
- **风险**：`last_active_function`、缩略图尺寸等持久化 key 不能丢 → 映射保留。

## 8. 验收标准

- 侧栏按 `① 素材准备 / ② 分镜创作 / ③ 视频出片` 分阶段展示全部 7 功能，可折叠为图标条。
- 拆/拼/去白边在主区单页内完成「选图→参数→预览/执行」，不再有控件隐藏跳变。
- 图片/视频/配乐/配音默认内嵌主-详；点「浮出」可拆为独立窗并支持多窗并行。
- 底部全局任务中心实时显示运行/排队/完成计数与并行分类，可展开队列。
- 6 项配置集中在统一设置页可达；含浅/深主题切换。
- 现有所有功能行为不变；`config.json` 持久化项不丢。

## 9. 非目标（YAGNI）

- 不改任何功能算法/生成逻辑/provider/数据模型。
- 不新增「合成导出」等当前不存在的功能（FUNCS 之外不扩展）。
- 不做拖拽式时间线重排、不做多语言、不做插件系统。
- 设置页搜索框一期可选；浅色主题为附带能力，不追求像素级打磨。
