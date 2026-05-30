# 糯米AI分镜影视创作台 · 欢迎首页设计规范

**日期**：2026-05-30  
**状态**：已确认，待实施  
**参考图**：`tests/pic/炫酷界面.jpg`（土豆AI短剧欢迎页）

---

## 1. 概述

在应用启动时显示全画布欢迎首页，替代直接进入侧边栏主界面的方式。欢迎页提供品牌展示、快捷操作入口和最近项目列表，用户点击项目或新建操作后，欢迎页淡出，主界面（侧边栏 + 内容区）滑入显示。

### 核心决策

| 维度 | 决策 |
|------|------|
| 类型 | 欢迎首页（Welcome Home Page），非传统 Splash |
| 集成方式 | 全画布（侧边栏隐藏），进入功能后侧边栏 slide-in |
| 色调 | 深蓝紫调（独立于主界面深灰蓝） |
| 布局 | 中轴居中 + 沉浸光晕（方案三） |
| 中心内容 | 快捷操作 + 最近项目卡片 + 工作流引导条 |

---

## 2. 视觉规范

### 2.1 颜色系统

```
背景基色：        #0d1020（主）→ #08090f（深）→ #100820（暗紫）
顶部氛围光晕：    radial-gradient 蓝色 #4a9eff14，椭圆，窗口宽度 60%，高 280px
左下氛围光晕：    radial-gradient 紫色 #a06cff08，宽度 35%，高 200px
右下氛围光晕：    radial-gradient 蓝色 #4a9eff06，宽度 25%，高 150px

主 Accent 渐变：  linear-gradient(90deg, #4a9eff → #a06cff)
卡片边框激活：    #4a9eff55 + box-shadow 0 0 32px #4a9eff20
卡片边框普通：    #252540
文字主色：        #e8eaed
文字次色：        #9aa0a6
文字暗色：        #5a6a8a / #3a4a6a
分割线：          #1e1e3a
```

### 2.2 字体规格

```
顶部应用名：    12px / 700 / letter-spacing 2px
Hero 主标题：   32px / 900 / letter-spacing 1px / text-shadow 蓝色 0 0 40px rgba(74,158,255,0.25)
Hero 副标题：   13px / 400 / letter-spacing 3px / uppercase
卡片标题：      11px / 700
卡片元信息：    9px / 400
流程步骤名：    11px / 600（激活）/ 400（未激活）
流程步骤编号：  9px / 700
```

---

## 3. 布局结构

```
┌─────────────────────────────────────────────────────┐
│  顶部导航栏（42px 固定高度）                          │
├─────────────────────────────────────────────────────┤
│                                                     │
│              Hero 区（约 22% 窗口高）                 │
│         主标题 / 副标题 / 双 CTA 按钮                 │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│         卡片走马灯区（flex:1，撑满剩余高度）            │
│      远卡  近卡  ████中心卡████  近卡  [+新建]         │
│                                                     │
├─────────────────────────────────────────────────────┤
│         分页圆点（6px，中心对齐，首期仅装饰）           │
├─────────────────────────────────────────────────────┤
│    ━━━━━━━━━ 01剧本 › 02分镜 › 03视频 › 04后期 ━━━━━  │
└─────────────────────────────────────────────────────┘
```

---

## 4. 各区域详细规范

### 4.1 顶部导航栏

- **高度**：42px
- **背景**：`rgba(13,16,32,0.95)` + `backdrop-filter: blur(8px)`
- **下边框**：`1px solid #1e1e3a`
- **左侧**：App Icon（20×20px，圆角 5px，蓝→紫渐变，`box-shadow: 0 0 12px #4a9eff55`）+ 应用名"糯米 AI"
- **右侧**：
  - "⚙ 全局设置"按钮（11px，`background: rgba(26,26,50,0.8)`，`border: 1px solid #2a2a4a`，圆角 5px）
  - 窗口控件三圆点（最小化黄 `#f5a623`、最大化绿 `#27c93f`、关闭红 `#ff5f57`，直径 12px）
- **PySide6**：`QWidget` 自定义绘制，`FramelessWindowHint` + DWM 暗色模式；三圆点为自定义 `QPushButton`

### 4.2 Hero 区

- **内边距**：上 4%，左右 20%，下 3%
- **主标题**："糯米AI分镜影视创作台"，居中
- **副标题**："剧本 · 分镜 · 视频 · 后期配音配乐"，居中，uppercase
- **CTA 按钮**：
  - 主按钮"＋ 新建项目"：`border-radius: 50px`（胶囊形），蓝→紫渐变背景，`box-shadow: 0 0 24px #4a9eff50`
  - 次按钮"打开目录"：胶囊形，毛玻璃深色，`border: 1px solid #2a2a4a`
  - 两按钮间距 10px，居中对齐

### 4.3 卡片走马灯区

卡片景深系统（从左到右，共 5 个槽位）：

| 位置 | flex | 高度 | 透明度 | 边框 | 说明 |
|------|------|------|--------|------|------|
| 远左 | 0.65 | 78% | 0.50 | `#1a1a30` | 最远最暗 |
| 近左 | 0.85 | 88% | 0.72 | `#252540` | 次远 |
| **中心** | **1.4** | **100%** | **1.0** | `#4a9eff55` + glow | **焦点卡** |
| 近右 | 0.85 | 88% | 0.72 | `#252540` | 次远 |
| 新建 | 0.50 | 72% | 0.60 | 虚线 `#252540` | 虚线边框 + "＋" |

右侧无「远右」卡，不对称布局使视觉重心略偏中左，符合从左到右的阅读习惯。

**中心卡附加效果**：
- `box-shadow: 0 0 32px #4a9eff20, 0 0 80px #a06cff10, 0 8px 32px rgba(0,0,0,0.6)`
- 缩略图内含"AI 主创"标签（左上角，毛玻璃蓝色背景）
- 缩略图底部渐变遮罩（`linear-gradient(transparent, rgba(10,10,28,0.85))`）
- 卡片底部 meta：项目名 + 蓝色圆点 + 张数 + 最后修改时间

**卡片交互**：
- Hover：`translateY(-3px)` + 轻微 box-shadow 增强，`transition: 200ms ease`
- 点击：淡出欢迎页，主界面侧边栏 slide-in，并自动打开对应项目目录

**空状态**（无最近项目时）：
- 卡片区中央显示"创建你的第一个项目"引导文案
- 仅保留"＋ 新建项目"虚线卡，其余卡不渲染

### 4.4 分页圆点

- 圆点：直径 6px，颜色 `#1e1e3a`
- 激活圆点：宽 16px，圆角 3px，颜色 `#4a9eff`（变形为胶囊）
- 位置：卡片区与流程条之间，水平居中，`padding: 6px 0`
- **首期仅装饰，不可交互**；圆点数量 = min(最近项目数, 4)，激活第一个

### 4.5 底部工作流条

```
──────────────── 01 剧本创作 › 02 AI分镜出图 › 03 生成视频 › 04 后期配音配乐 ────────────────
```

- **布局**：两侧渐隐水平线（`linear-gradient` 从透明到 `#1e1e3a`）+ 居中步骤组
- **步骤圆点**：直径 20px，激活为蓝→紫渐变 + `box-shadow: 0 0 10px #4a9eff60`；未激活为 `#111128` + `border: 1px solid #252540`
- **步骤标签**：激活 `#c0c8e0 / 600`，未激活 `#3a4a6a / 400`
- **分隔符** `›`：激活步骤后为 `#4a9eff`，其余为 `#252540`
- **初始状态**：欢迎页上步骤 01 始终为激活状态（表示"从这里开始"）

---

## 5. 交互与动效

### 5.1 欢迎页进入动画（App 启动时）

1. 窗口出现时：背景 + 光晕 `fade-in` 200ms
2. 顶部导航栏：从上方 `slide-down` 8px + fade-in，300ms `ease-out`
3. Hero 区：从下方 `slide-up` 16px + fade-in，400ms `ease-out`，delay 100ms
4. 卡片区：各卡片 stagger slide-up，delay 30ms × index，共 350ms
5. 流程条：fade-in，delay 300ms

所有动画遵循 `prefers-reduced-motion`，关闭时直接显示最终态。

### 5.2 进入功能页面

- 用户点击卡片或"新建项目"：
  1. 点击的卡片 scale-up 到 1.02，持续 100ms
  2. 欢迎页整体 fade-out，300ms
  3. 侧边栏从左侧 slide-in（0 → 184px），300ms `ease-out`，与 fade-out 同步开始
  4. 内容区淡入，delay 150ms

### 5.3 从主界面回到欢迎页

- 侧边栏顶部添加"首页"图标按钮（Home 图标）
- 点击：侧边栏 slide-out + 内容区淡出 → 欢迎页淡入，300ms

---

## 6. 数据模型

### 最近项目存储

```json
// {app_data_dir}/recent_projects.json
// app_data_dir = QStandardPaths::AppDataLocation，与现有 config 文件同目录
{
  "projects": [
    {
      "name": "都市风云",
      "path": "E:/Projects/都市风云",
      "last_opened": "2026-05-29T14:30:00",
      "shot_count": 12,
      "thumbnail": null
    }
  ]
}
```

- 最多保留 **8 条**，按 `last_opened` 降序
- 打开项目时写入/更新；目录不存在时从列表移除并提示
- 卡片走马灯最多展示 **4 张**（中心 + 左右 + 近侧），其余通过分页点切换

---

## 7. PySide6 实现要点

| 组件 | 实现方案 |
|------|----------|
| 背景渐变 + 光晕 | `QWidget.paintEvent()` → `QPainter` + `QRadialGradient` / `QLinearGradient` |
| 无边框窗口 | `Qt.FramelessWindowHint` + Windows DWM 暗色标题栏（复用现有 `theme.py`）|
| 动画 | `QPropertyAnimation` + `QParallelAnimationGroup` / `QSequentialAnimationGroup` |
| 卡片组件 | 自定义 `QWidget` 子类 `ProjectCard`，重写 `paintEvent` + `enterEvent` |
| 最近项目 | `RecentProjectsManager`（单例），读写 JSON，`project_opened` 信号触发更新 |
| 欢迎→主界面切换 | `AppShell` 中 `QStackedWidget`：index 0 = `WelcomePage`，index 1 = 主界面布局；切换时播放动画 |
| 侧边栏动画 | `QPropertyAnimation` 控制 `FlowSidebar.maximumWidth`：0 → 184px |

### 文件结构（新增）

```
drama_shot_master/
├── ui/
│   ├── pages/
│   │   └── welcome_page.py          # WelcomePage(QWidget)
│   ├── widgets/
│   │   ├── project_card.py          # ProjectCard(QWidget)
│   │   └── workflow_strip.py        # WorkflowStrip(QWidget)
│   └── styles/
│       └── welcome.qss.tpl          # 欢迎页专属 QSS 模板
├── core/
│   └── recent_projects.py           # RecentProjectsManager
```

---

## 8. 不在本期范围内

- 卡片区真实 3D 透视变换（CSS transform rotateY）——当前用 opacity/size 差异模拟景深
- 分页点点击切换卡片的轮播逻辑——首期仅展示固定 4 张
- 卡片缩略图自动截图生成——首期显示色块占位
- 欢迎页"我的作品"标签页——与主界面的"任务中心"功能重叠，暂不加
