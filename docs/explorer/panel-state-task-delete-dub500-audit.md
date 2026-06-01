# 多面板状态持久化 + 任务删除 + 配音500修复 + 后台任务不中断

## 审计发现摘要

### ① 面板模式不保留（根因）

`web/app.html` `loadPage()` 每次设置 `VIEW.src` 导致 iframe 完全重新加载，所有 JS 内存状态销毁。

| 面板 | 模式变量 | 持久化？ |
|------|----------|----------|
| video-mode2 | 模式1/模式2 (`setMode(1/2)`) | ❌ 纯 DOM class 切换 |
| dub-mode2 | 模式1/模式2 (`applyMode("m1/m2")`) | ❌ 每次 reload 默认 m2 |
| storyboard-board | 分镜视角/自由模式 | ❌ 纯 DOM 切换 |

**修复方向：** 每个页面在切换模式时写 `localStorage`（key: `nuomi.<page>.mode.<project>`），初始化时恢复。

### ② 并行任务缺少删除

| 页面 | 任务存储 | 添加 | 删除 |
|------|----------|------|------|
| video-mode2 | 内存 `taskState.tasks` | ✅ addTask() | ❌ 不存在 |
| dub-mode2 模式1 | 内存 `m1Tasks` | ✅ 按钮存在 | ❌ 不存在 |
| dub-mode2 模式2 | 硬编码 `PARALLEL_TASKS` (const) | ❌ 不可变 | ❌ 不可变 |

**修复方向：** 每个任务项渲染 ✕ 删除按钮（至少保留一个），实现 `removeTask(id)`。

### ③ 配音 HTTP 500（根因）

`media_agent/routes/tts.py` 只捕获 `ValueError`。`RunningHubUnavailable`、`RunningHubTaskFailed` 等异常未捕获 → FastAPI 返回 500。

对比 `video.py` 已正确捕获这些异常（返回 502），`tts.py` 缺失相同的异常处理。

### ④ 切面板打断生成任务（架构问题）

**现状：** 所有生成请求用 `await fetch()` —— iframe 卸载时浏览器中止请求，前端永远收不到响应。

**服务器端：** 文件可能已落盘，但前端无任务 ID/轮询机制发现这些"孤儿产物"。

**修复方向分两级：**

- **短期（本 spec）：** 生成请求前先记 `localStorage`（任务 ID + 时间戳 + 参数），`beforeunload` 不阻止离开但标记"进行中"。页面重新加载时轮询产物目录发现已完成文件。
  
- **长期（后续 spec）：** 后端返回 `task_id`，前端 `EventSource` 轮询 `/task/{id}/status`，即使页面重载也能恢复。需要新端点。

---

## 问题确认

这四个问题的优先级你倾向哪种？

- **A) 全部 P0 一次性修** — ①面板状态 + ②任务删除 + ③配音500 + ④短期方案（localStorage标记+产物轮询），一锅端
- **B) 先修 ①②③，④ 长期方案单独设计** — 面板状态/删除/500 快速修完；任务不中断作为独立大项另开 spec（需要新后端端点）
- **C) ③最急，其他按顺序** — 配音 500 先修→面板状态→删除→任务不中断