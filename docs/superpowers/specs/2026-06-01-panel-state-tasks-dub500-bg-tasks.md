# Panel State + Task Delete + Dub 500 + Background Tasks — P0 修复

## 范围

四个独立 P0 问题，共享面板基础架构 (iframe + localStorage)。

---

## ① 面板模式状态持久化

### 根因
`app.html` `loadPage()` 设置 `VIEW.src` 导致 iframe 完全重载，所有 JS 内存状态销毁。

### 修复

三页面各自在模式切换时写 `localStorage`，初始化时恢复：

| 页面 | localStorage Key | 默认值 |
|------|-----------------|--------|
| video-mode2 | `nuomi.videoMode.<project>` | `"m1"` |
| dub-mode2 | `nuomi.dubMode.<project>` | `"m2"` |
| storyboard-board | `nuomi.sbMode.<project>` | `"storyboard"` |

**实现细节：**
- `video-mode2` `setMode(n)` → 末尾加 `localStorage.setItem(LSKEY, n === 1 ? "m1" : "m2")`
- `dub-mode2` `wireModes()` 初始化时读 localStorage 调 `applyMode(savedMode)`
- `storyboard-board` 模式按钮点击 → localStorage 写 `"storyboard"/"free"`，初始化恢复

---

## ② 并行任务删除按钮

### video-mode2

- `renderTaskMenu()` 中每个任务项加 `✕` 删除按钮
- 新增 `removeTask(id)`：`taskState.tasks = taskState.tasks.filter(t => t.id !== id)`，若删除当前任务则切到第一个
- 至少保留一个任务（只有1个时隐藏 ✕）

### dub-mode2 模式1

- 任务下拉选择器旁加删除按钮
- `m1Tasks` splice 删除，至少保留一个

### dub-mode2 模式2

- `PARALLEL_TASKS` const → let
- 允许删除（至少1个）

---

## ③ 配音 TTS HTTP 500

### 根因
`media_agent/routes/tts.py` `synthesize()` / `preview()` 只捕获 `ValueError`。
`RunningHubUnavailable` / `RunningHubTaskFailed` 等未捕获 → FastAPI 500。

### 修复

对照 `video.py` 模式，在 `tts.py` 添加异常处理：

```python
except (ValueError, RunningHubInvalidSpec) as e:
    raise HTTPException(status_code=400, detail=str(e))
except (RunningHubUnavailable, RunningHubUploadError,
        RunningHubTaskFailed) as e:
    raise HTTPException(status_code=502, detail=str(e))
```

涉及函数：`synthesize()`, `preview()`, `_do_synthesize()`

---

## ④ 后台任务不中断（短期方案）

### 问题
`await fetch()` 在 iframe 卸载时被浏览器中止，前端收不到响应。服务器端文件可能已落盘但前端无法发现。

### 短期修复

**生成前：**
1. 写 localStorage 记录："任务进行中" — 含类型/时间戳/参数
2. 生成按钮保持 disabled 状态（即使页面重载也能从 localStorage 恢复）
3. 不阻止页面离开（不用 `beforeunload`）

**页面重载时（`DOMContentLoaded`）：**
1. 检查 localStorage 是否有"进行中"任务
2. 若有，轮询产物目录（`/project/clips` 或 `/project/files`）查找新文件
3. 找到新产物 → 标记任务完成 → 更新 UI

**video-mode2 具体方案：**
- `dirState` 已存 localStorage (`nuomi.director.<project>`) — 新增字段 `pendingJobs: [{slotId, startTime}]`
- 重载时扫描 `video/` 目录文件修改时间 > startTime → 自动关联到对应 slot

**storyboard-board 具体方案：**
- 已有 `nuomi.imggenTasks.<project>` — `running` 状态任务在重载时扫描 `imggen/` 目录
- `reloadShotPreview()` 已能发现新文件，只需确保触发时机

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `web/video-mode2.html` | ① localStorage 模式 + ② 删除按钮 + ④ pendingJobs |
| `web/dub-mode2.html` | ① localStorage 模式 + ② 删除按钮 |
| `web/storyboard-board.html` | ① localStorage 模式 |
| `media_agent/routes/tts.py` | ③ 异常捕获 |

---

## 不改动

- app.html 导航机制（iframe 重载保持不变）
- 后端 API 契约
- localStorage key 命名规范不变的页面
