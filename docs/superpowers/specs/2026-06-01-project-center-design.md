# 项目中心 (Project Center) — 独立内容页

## 目标

新增「项目中心」作为独立内容页，用户可从顶部栏或侧栏进入，浏览/搜索/筛选最近项目，切换进入不同项目。

---

## 导航集成

### 顶部栏（`web/app.html` titlebar）

在「任务中心」按钮左侧新增「项目中心」按钮：

```
[糯米 AI]  [项目 / 叽里咕噜]  .............  [▦ 项目中心]  [● 任务中心 3]  [— □ ✕]
```

- landing 状态（未进项目）：面包屑显示「未选择项目」，项目中心按钮仍可见可点击
- 已进项目：面包屑显示真实项目名

### 侧栏导航（`web/app.html` nav）

「项目中心」作为侧栏 **第一项**（在「概览」之上）：

```
▦ 项目中心     ← 新增
▦ 概览
✎ 剧本创作
◈ 资源库
▤ 分镜板
▶ 视频生成
✂ 视频后期
────
✦ 技能库
⚙ 全局设置
```

- `data-key="project_center"`，`data-page="project-center.html"`
- 点击导航到 `/project_center` hash 路由
- 无子路由（不属于阶段向导容器）

### welcome 首页保留不变

- 未进项目时默认显示 welcome（landing 页），用户可以从中选项目进入
- 侧栏项目中心也可在 landing 时点击，展示全部项目列表

---

## 页面设计（`web/project-center.html` 新建）

### 布局方案：列表行（方案 B）

- 壳内内容页，复用 `tokens.css`
- 顶部渐变标题 `▦ 项目中心` + 项目计数
- 搜索/筛选栏
- 项目列表（每条一行）

### 每行信息

| 位置 | 内容 |
|------|------|
| 左侧 | 48×48 封面缩略图（缺图时虚线框 + "?" 占位） |
| 主体 | 项目名称 + 类型标签 + P-ID + 集数 |
| 右侧 | 最后打开时间 + 「进入」按钮 |

### 当前打开项目

- 蓝色描边高亮 + 蓝色光晕
- 名称旁显示「当前打开」badge
- 按钮文字改为「已进入」

### 空状态

- 居中图标「📁」+ 提示文案
- 引导用户「新建项目」或「打开目录」

### 搜索/筛选

- 文本搜索框：按项目名称过滤（前端本地过滤，无需后端搜索端点）
- 类型标签筛选：全部 / 短剧 / MV / 广告 / 其他

### 新建/打开按钮

- 标题栏右侧「＋ 新建项目」主按钮 +「📁 打开目录」次按钮
- 复用 welcome.html 已有对话框逻辑（`newMask` 对话框 + `POST /projects/create`）

### 项目切换流程

1. 用户点击「进入」→ 调用 `POST /projects/open` 登记
2. 通过 `postMessage({ type: "project.open", path, name })` 通知壳
3. 壳更新 PROJECT → 面包屑 → iframe 重载当前内容页
4. 项目中心页自身不关闭

---

## 后端新增端点

### `GET /project/center`

返回最近项目列表，每个项目含封面、类型、集数、进度摘要。
数据来源：`recent_projects.json` + 逐项目扫描 `project.json` manifest。

```json
{
  "projects": [
    {
      "name": "叽里咕噜",
      "path": "E:\\DramaAsserts\\P-003_叽里咕噜",
      "project_id": "P-003",
      "genre": "短剧",
      "episode_count": 12,
      "cover": "E:\\DramaAsserts\\P-003_叽里咕噜\\cover.jpg",
      "last_opened": "2026-06-01T02:52:10Z",
      "shot_count": 0,
      "status": "scripted"
    }
  ],
  "total": 3
}
```

**实现位置：** `media_agent/routes/projectx.py` 新增函数

**字段逻辑：**
- `genre` → 读 `project.json` manifest `genre` 字段，回退空串
- `episode_count` → 复用 `_episode_count()` 扫描 `剧本_E*.md` 数量
- `cover` → 约定路径 `<project>/cover.jpg`，文件存在才返回（否则 `null`）
- `shot_count` → 来自 `recent_projects.json`
- `status` → manifest 状态字段

---

## 涉及文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `web/project-center.html` | **新建** | 项目中心页面 |
| `web/app.html` | 编辑 | titlebar 新增按钮 + 侧栏新增第一项 + landing 状态适配 |
| `media_agent/routes/projectx.py` | 编辑 | 新增 `GET /project/center` 端点 |

---

## 不改动

- welcome.html 首页
- 其他内容页（概览/剧本/资源库等）
- `/projects/list` 端点语义
- manifest / registry / recent_projects 存储格式
- tokens.css 全局变量
