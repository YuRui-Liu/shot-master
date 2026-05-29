# 任务栏折叠功能 设计 Spec

**日期：** 2026-05-29  
**代号：** `collapsible_task_bar`  
**版本：** v1.0  
**状态：** 已用户审阅通过  

---

## 0. 背景与目标

五个面板（编剧/出图/生视频/配音/配乐）的左侧任务栏在项目多时占用较多横向空间。用户希望能通过点击小图标将任务栏折叠为 40px 宽的图标轨，悬停可见项目名称和状态，点击可直接切换项目，清爽高效。

---

## 1. 折叠交互规格

### 1.1 展开状态（默认）

```
┌─── 任务栏 (280px) ────────────────┐ ┌─── 工作区 ─────┐
│ [+ 新建] [打开] [删除]        [◀] │ │                │
│ ┌──────┬────┬────────┬────────┐   │ │                │
│ │ 名称 │状态│当前阶段│更新时间│   │ │                │
│ ├──────┼────┼────────┼────────┤   │ │                │
│ │ 项目A│✓✓○○│待分镜  │5分前  │   │ │                │
│ │ 项目B│●●○○│生成中  │刚刚   │   │ │                │
│ └──────┴────┴────────┴────────┘   │ │                │
└───────────────────────────────────┘ └───────────────┘
                                 ^ [◀] 折叠按钮（右上角）
```

### 1.2 折叠状态（图标轨 40px）

```
┌──┐ ┌─── 工作区（展开占满）──────────┐
│▶ │ │                                │
│──│ │                                │
│①✓│ │                                │
│②●│ │                                │
│③○│ │                                │
│④○│ │                                │
└──┘ └────────────────────────────────┘
```

**图标轨各行说明：**

| 行 | 内容 | 说明 |
|---|---|---|
| 顶行 | `▶`（展开按钮） | 居中，点击展开 |
| 各项目行 | `①` 序号圆形徽章 + 右下角状态小点 | 36px 高，点击切换到该项目 |

**状态点颜色：**

- `✓` 绿色 (`#52b788`) — 所有阶段完成
- `●` 蓝色 (`#4a9eff`) — 当前有阶段在生成中
- `○` 灰色 (`#666`) — 部分完成或未开始
- `✗` 红色 (`#e05252`) — 有阶段失败

**tooltip（悬停显示）：** `项目名\n当前阶段: 待分镜`

---

## 2. 架构

### 2.1 新增文件

```
drama_shot_master/ui/widgets/collapsible_task_bar.py
    ├── IconRailItem          dataclass（图标轨一行数据）
    ├── _RailBadge            QWidget（单个圆形徽章行）
    ├── _IconRail             QWidget（整个图标轨，含展开按钮）
    └── CollapsibleTaskBar    QWidget（包装器，对外暴露 expand/collapse API）
```

### 2.2 修改文件

| 文件 | 改动 |
|------|------|
| `drama_shot_master/ui/pages/task_workspace_page.py` | 用 `CollapsibleTaskBar` 包裹 `manager`；绑定 splitter |
| `drama_shot_master/ui/panels/screenwriter_panel.py` | 同上，包裹 `ScreenwriterTaskManager` |
| `drama_shot_master/ui/panels/soundtrack_panel.py` | 同上（视其左右结构而定） |
| `drama_shot_master/ui/widgets/screenwriter/task_manager.py` | 实现 `icon_rail_items()` 方法 |
| `drama_shot_master/ui/panels/imggen_task_manager_panel.py` | 实现 `icon_rail_items()` 方法 |
| `drama_shot_master/ui/panels/video_task_manager_panel.py` | 实现 `icon_rail_items()` 方法 |
| `drama_shot_master/ui/panels/dub_task_manager_panel.py` | 实现 `icon_rail_items()` 方法 |
| `drama_shot_master/ui/panels/soundtrack_panel.py` | 实现 `icon_rail_items()` 方法（如适用） |

---

## 3. 核心组件设计

### 3.1 `IconRailItem` dataclass

```python
from dataclasses import dataclass

@dataclass
class IconRailItem:
    index: int            # 序号（1-based），显示在徽章内
    label: str            # 备用显示（如项目名首字）
    status: str           # "done" | "running" | "idle" | "error"
    tooltip: str          # 悬停文字，如 "项目A\n当前阶段: 待分镜"
    item_id: str          # 用于点击回调时识别选中的是哪项（路径/task_id）
```

### 3.2 `icon_rail_items()` 协议

每个 task manager 添加以下方法：

```python
def icon_rail_items(self) -> list[IconRailItem]:
    """返回当前任务列表的图标轨数据，供 CollapsibleTaskBar 渲染折叠视图。
    
    需在 refresh() 之后数据一致。CollapsibleTaskBar 在两处调用：
    - refresh() 后（task manager 调 self.icon_rail_updated.emit() 触发）
    - 折叠按钮被点击时（一次性读取）
    """
    ...

# 同时新增 signal
icon_rail_updated = Signal()   # 数据变化时发出，CollapsibleTaskBar 监听并刷新 _IconRail
```

**ScreenwriterTaskManager 的实现示例：**

```python
def icon_rail_items(self) -> list[IconRailItem]:
    items = []
    for i, p in enumerate(self._projects):
        dots, current_stage = self._compute_status(p)
        if self._active_worker_query(p):
            status = "running"
        elif "✗" in dots:
            status = "error"
        elif all(c == "✓" for c in dots.split() if c in ("✓", "○")):
            status = "done"
        else:
            status = "idle"
        items.append(IconRailItem(
            index=i + 1,
            label=p.name[:2],
            status=status,
            tooltip=f"{p.name}\n当前阶段: {current_stage}",
            item_id=str(p),
        ))
    return items
```

### 3.3 `CollapsibleTaskBar` 组件

```python
class CollapsibleTaskBar(QWidget):
    """包裹任意 task manager，提供折叠/展开能力。
    
    使用方式：
        bar = CollapsibleTaskBar(manager_widget, splitter, manager_index=0)
        splitter.insertWidget(0, bar)   # 替换原来直接插入 manager 的位置
    """
    
    collapsed = Signal()    # 折叠完成
    expanded = Signal()     # 展开完成
    
    def __init__(self, manager: QWidget, splitter: QSplitter,
                 manager_index: int = 0,
                 expanded_width: int = 280,
                 collapsed_width: int = 40,
                 parent=None):
        ...
    
    def is_collapsed(self) -> bool: ...
    def collapse(self) -> None: ...
    def expand(self) -> None: ...
    def toggle(self) -> None: ...
```

**内部结构（QStackedWidget，index 0=展开，index 1=折叠）：**

```
CollapsibleTaskBar (QWidget, 固定宽度由折叠状态决定)
└── QStackedWidget
    ├── page 0: 展开视图
    │   ├── manager_widget（原 task manager）
    │   └── _collapse_btn（QPushButton「◀」，绝对定位在右上角）
    └── page 1: 折叠视图（_IconRail）
        ├── _expand_btn（QPushButton「▶」，顶部居中）
        └── QScrollArea → QVBoxLayout → [_RailBadge × N]
```

**折叠/展开逻辑：**

```python
def collapse(self) -> None:
    self._expanded_width = self._splitter.sizes()[self._manager_index]  # 记住当前宽
    self._icon_rail.refresh(self._manager.icon_rail_items())
    self._stack.setCurrentIndex(1)
    sizes = self._splitter.sizes()
    sizes[self._manager_index] = self._collapsed_width
    self._splitter.setSizes(sizes)
    self._splitter.handle(self._manager_index).setEnabled(False)  # 折叠时锁住 splitter 把手
    self.collapsed.emit()

def expand(self) -> None:
    self._stack.setCurrentIndex(0)
    sizes = self._splitter.sizes()
    sizes[self._manager_index] = self._expanded_width
    self._splitter.setSizes(sizes)
    self._splitter.handle(self._manager_index).setEnabled(True)
    self.expanded.emit()
```

### 3.4 `_RailBadge` 单个图标行

```
┌──────────────────────┐  高 36px
│  ┌──┐                │
│  │ 1│  ●             │  ← 圆形徽章(24px) + 右下角 8px 状态点
│  └──┘                │
└──────────────────────┘
```

```python
class _RailBadge(QWidget):
    clicked = Signal(str)   # 发出 item_id
    
    def __init__(self, item: IconRailItem, parent=None): ...
    
    STATUS_COLORS = {
        "done":    "#52b788",
        "running": "#4a9eff",
        "idle":    "#666666",
        "error":   "#e05252",
    }
    
    def paintEvent(self, event):
        # 绘制圆形徽章（深色背景 + 序号文字）
        # 绘制右下角小状态点（8px 实心圆，颜色按 STATUS_COLORS）
        ...
```

点击 `_RailBadge` → 调 `manager.select_by_id(item_id)` → task manager 选中对应行 → 触发正常的 `taskSelected` 信号链。

每个 task manager 新增：

```python
def select_by_id(self, item_id: str) -> None:
    """图标轨点击时调用，按 item_id（路径/task_id 字符串）选中对应行。"""
    ...
```

---

## 4. 接入各面板

### 4.1 `TaskWorkspacePage`（出图/视频/配音 共用）

```python
# 原来
splitter.addWidget(self.manager)
self.manager.setMinimumWidth(290)
self.manager.setMaximumWidth(300)

# 改为
self._collapsible = CollapsibleTaskBar(
    self.manager, splitter,
    manager_index=0, expanded_width=290)
splitter.addWidget(self._collapsible)
self._collapsible.setMinimumWidth(40)   # 允许折叠到 40px
# 不再设 manager 的 setMaximumWidth（CollapsibleTaskBar 控制宽度）
```

### 4.2 `ScreenwriterPanel`

```python
# 原来
self._task_manager = ScreenwriterTaskManager(self._cfg)
self._task_manager.setMaximumWidth(300)
self._task_manager.setMinimumWidth(220)
splitter.addWidget(self._task_manager)

# 改为
self._task_manager = ScreenwriterTaskManager(self._cfg)
self._collapsible = CollapsibleTaskBar(
    self._task_manager, splitter,
    manager_index=0, expanded_width=280)
self._collapsible.setMinimumWidth(40)
splitter.addWidget(self._collapsible)
```

### 4.3 配乐面板

配乐面板（`SoundtrackPanel`）作为任务列表本身使用；其对应的展开视图是 `SoundtrackEditor`，走 `TaskWorkspacePage` 包装路径，与出图/视频/配音一致，无需特殊处理。

---

## 5. 状态持久化

折叠/展开状态保存到 `cfg.ui_state`（或 `settings.json` 的 `task_bar_collapsed` 字段），键名按面板区分：

```json
{
  "task_bar_collapsed": {
    "screenwriter": false,
    "imggen": false,
    "video": false,
    "dub": false,
    "soundtrack": false
  }
}
```

`CollapsibleTaskBar.__init__` 读取初始状态；折叠/展开时更新。

---

## 6. 最小宽度约束处理

折叠状态下 splitter 必须允许左侧缩到 40px：

```python
# CollapsibleTaskBar.collapse() 内
self.setMinimumWidth(self._collapsed_width)
self.setMaximumWidth(self._collapsed_width)

# CollapsibleTaskBar.expand() 内
self.setMinimumWidth(40)
self.setMaximumWidth(16777215)   # QWIDGETSIZE_MAX
```

---

## 7. 新增文件结构

```
drama_shot_master/ui/widgets/
└── collapsible_task_bar.py      ← 新建，所有组件在此文件

tests/test_ui/
└── test_collapsible_task_bar.py ← 新建
```

---

## 8. 测试策略

| 用例 | 验证 |
|------|------|
| `test_collapse_changes_splitter_sizes` | 折叠后 splitter 左侧 == 40 |
| `test_expand_restores_width` | 展开后恢复上次宽度 |
| `test_icon_rail_shows_correct_count` | N 个项目 → N 个 badge |
| `test_badge_click_selects_item` | 点 badge → taskSelected 信号 |
| `test_status_colors_match` | running/done/idle/error 颜色正确 |
| `test_tooltip_text` | tooltip 含项目名 + 阶段 |
| `test_initial_state_from_config` | cfg.task_bar_collapsed 控制初始状态 |

总计 **7 个新测试用例**，覆盖 `CollapsibleTaskBar` 核心行为。  
各 task manager 的 `icon_rail_items()` / `select_by_id()` 由各自测试文件追加用例，约 **5 × 2 = 10 个**。  
总计约 **17 个新用例**，现有测试零回归。

---

## 9. 不在本期（显式延后）

- 图标轨支持拖拽排序（重新排列项目顺序）
- 折叠动画（平滑过渡）
- 键盘快捷键（如 `Ctrl+[` 折叠/展开）
- 图标轨显示自定义颜色标记

---

## 10. 验收标准

1. 五个面板（编剧/出图/生视频/配音/配乐）左侧任务栏顶部都有 `◀` 折叠按钮
2. 点击 `◀` → 任务栏收缩到 40px 图标轨，工作区自动占满
3. 图标轨显示正确数量的徽章，序号从 1 开始
4. 状态点颜色与任务状态一致（绿/蓝/灰/红）
5. 悬停 badge → tooltip 显示 `项目名\n当前阶段`
6. 点击 badge → 切换到对应项目（taskSelected 信号正常触发）
7. 点击 `▶` → 恢复到折叠前的宽度
8. 折叠状态写入 settings.json，重启后保持
9. 17 个新用例全绿，235+ 原有用例零回归
