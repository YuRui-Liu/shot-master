# Bug Fixes ①②③ — 首页/概览/404

## 范围

三个低风险纯度修 bug：首页面包屑硬编码项目名、概览封面无图片、favicon+cover 404。
不动 JS 逻辑架构、后端 API 语义、数据库/文件格式。

---

## Bug ①：首页初始显示伪项目名 + 概览封面无图

### ①a：app.html 面包屑伪名

**根因：** `web/app.html` 第93行硬编码 `测试剧本_废铁场之夜`，welcome 发 `postMessage` 前该伪名一直可见。

**修复：** 初始值改为「未选择项目」（`openProject()` 会在收到 postMessage 后覆盖）。

| 文件 | 改动 |
|------|------|
| `web/app.html` L93 | `<b id="proj">测试剧本_废铁场之夜</b>` → `<b id="proj">未选择项目</b>` |

### ①b：概览封面只显示 CSS 渐变、从不加载图片

**根因：** `web/overview.html` L167 `<div class="cover">` 是空 div，仅 CSS `linear-gradient` 背景。没有 `<img>` 标签。

**修复：**
1. cover div 加 `id="pjCover"`
2. 新增 `coverPath(dir)` 函数（与 `welcome.html` L322-327 同约定：`<project>/cover.jpg`）
3. `renderHeader()` 内注入 `<img>`（`onerror` 隐藏自身→CSS 渐变回退）
4. `renderPlaceholder()` 清空 cover 内 img
5. CSS 新增 `.project .cover img` 规则

---

## Bug ②：概览追踪始终显示"暂无待办"

**根因分析：** commit `79d2bb7` 已修复。旧逻辑从 manifest pipeline 读状态（默认全 `pending`→前端显示全锁），新逻辑 `_scan_stage_states()` 扫描磁盘真实文件。

**后端修复（已落地，无需再动）：**
- `media_agent/routes/projectx.py` L149-180 `_scan_stage_states()`
- L433-443 `next_action` 双循环（磁盘扫描优先，manifest 覆盖）
- L360-369 `_NEXT_ACTION_TEXT` 七阶段文案映射

**前端链验证无误：**
- `stOf()` → `"lock"` 正确映射到 CSS class `"locked"`
- `renderFlow()` → 三态分色正确
- `renderNext()` → `next_action` 为空时回退文案

**结论：** 无需改动。若用户仍看到异常，可能是服务未重启导致运行旧代码。

---

## Bug ③：/favicon.ico 和 cover.jpg 均 404

### ③a：favicon.ico 404

**根因：** 浏览器自动请求 `GET /favicon.ico`，但无路由、无文件、HTML 无 `<link rel="icon">`。

**修复：** `media_agent/server.py` 新增路由：

```python
@app.get("/favicon.ico", include_in_schema=False)
async def _favicon():
    icon = _REPO_ROOT / "drama_shot_master" / "assets" / "app_icon.ico"
    if icon.is_file():
        return FileResponse(str(icon), media_type="image/x-icon")
    return Response(status_code=204)
```

文件缺失时返回 204（No Content）而非 404，优雅降级。

### ③b：cover.jpg 404

**根因：** 项目目录中缺少 `cover.jpg`。前端 `coverPath()` 生成 `<project>/cover.jpg` 路径 → `GET /file?path=...` → 文件不存在 → 404。

**修复：** 分两步 ——

**短期（本 spec）：** `media_agent/routes/files.py` 在 `get_file()` 中对 cover.jpg 做缺图回退。路径以 `cover.jpg` 结尾且文件缺失时，返回 204 或 1×1 透明 SVG（前端 `<img onerror>` 已处理，不显示破图）。

**长期（后续）：** 用户通过项目设置上传封面图片，后端写 `cover.jpg` 到项目根目录。

---

## 不改动

- 各页面 JS 主要逻辑
- 后端 API 契约
- 数据库 / manifest / registry 格式
- 新建/打开项目流程
- `tokens.css` 全局变量
