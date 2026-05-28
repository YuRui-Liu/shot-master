# 编剧 Agent · 设计稿（前置创作链路）

**日期**：2026-05-28
**代号**：`screenwriter_agent`
**版本**：v0.1.0 (设计稿)
**状态**：待用户复审

---

## 0. 摘要

为短剧分镜大师增加**前置创作链路**：把"零碎 idea → 多组创意 → 剧本 → 分镜 JSON → 出图提示词"这条链路工程化，给非编程视频创作者降低门槛。

实现为**完全独立**的 FastAPI 子进程 `screenwriter_agent`，与主软件通过 HTTP + SSE 流式通信，避免开发期与主软件 UI 改动冲突。状态走文件系统（项目目录），Agent 自身无内存 session。Stage 3 产出沿用用户已成熟的"教学系列 02" schema（camelCase + globalStyle + characters[] + shots[].stylePrompt），主软件未来需要灌入 video_panel 时由主软件侧适配一层。

---

## 1. 背景与约束

### 1.1 用户场景

- 用户已用豆包/DeepSeek **手工跑通过完整链路**（参见 `漫剧/剧本/教学系列/01-03`），但每次复制粘贴提示词 + 校对 JSON + 出多个 N 宫格图，操作繁琐。
- 目标：把这条手工链路程序化，做成"小白也能点 4 步出片"的桌面 wizard。
- 用户已有的成熟 prompt 模板**就是 Agent 内置基线**，不要重新发明。

### 1.2 项目内既有可复用资产

| 资产 | 路径 | Agent 复用方式 |
|---|---|---|
| OpenAI 兼容 LLM provider | `drama_shot_master/providers/openai_compat.py` | import 直接用 |
| Refine 修复链思路（去代码栅 / JSON 容错 / warnings） | `drama_shot_master/core/prompt_refiner.py` | 借鉴算法，重写于 Agent 内部 |
| YAML frontmatter 模板引擎 | `drama_shot_master/core/template_engine.py` | import 直接用 |
| 现有"分镜 JSON" 用户手工 schema | `漫剧/剧本/教学系列/02 根据剧本出分镜json.md` | 作为 Stage 3 输出 schema 标准 |
| 现有 3 套 prompt 模板 | `漫剧/剧本/教学系列/01-03 *.md` | 移植为 5 套内置模板 |
| `sound_track_agent/` | 独立子目录 + CLI 入口 | 作为新 Agent 目录结构参考 |

### 1.3 硬性约束

- **不引入 GPL 依赖**（既有约束 `feedback_no_gpl_deps`）：FastAPI/uvicorn/pydantic/json5 都是 MIT / BSD / Apache-2.0。
- **不破坏既有主软件代码**：Agent 是新 top-level 目录，主软件只在 `main.py`/`nav_config.py`/`config.py` 加少量胶水代码。
- **包内可复用，跨包用 HTTP**：`screenwriter_agent` 可 import `drama_shot_master` 子模块（同 repo）；`drama_shot_master` 不 import `screenwriter_agent`（保持进程隔离）。
- **不绑死 TimelineModel**：Stage 3 产出独立 schema；未来灌 video_panel 由主软件做适配层。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│  drama_shot_master（PySide6 桌面主软件）                       │
│  ┌──────────────────────────────────────────────┐           │
│  │  新增 "编剧" 面板（screenwriter_panel.py）      │           │
│  │  · 项目目录选择 / 已有产物预览                    │           │
│  │  · 4 步 Wizard：创意 → 剧本 → 分镜 → 提示词       │           │
│  │  · 创意步：聊天面板（用户/LLM 多轮对话）          │           │
│  │  · 任何阶段输出可手动编辑，落盘后再触发下游         │           │
│  └──────────────────────────────────────────────┘           │
│                       │ HTTP / SSE                            │
│                       ▼                                       │
└─────────────────────────────────────────────────────────────┘
       │                       
       │ subprocess.Popen（主软件启动时 spawn，退出时收尾）        
       ▼                       
┌─────────────────────────────────────────────────────────────┐
│  screenwriter_agent（独立 FastAPI 服务，本地 127.0.0.1:18430）  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  HTTP 路由层                                         │   │
│  │    GET  /health                                      │   │
│  │    GET  /project?dir=...                             │   │
│  │    POST /ideate/chat              (SSE)             │   │
│  │    POST /ideate/select                               │   │
│  │    POST /script                   (SSE)             │   │
│  │    POST /storyboard               (SSE)             │   │
│  │    POST /prompts                  (SSE)             │   │
│  │    GET/POST/DELETE /templates                        │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  prompt 模板层                                        │   │
│  │   - 内置 5 套（教学系列 01/02/03 移植）+ YAML frontmatter│
│  │   - 项目目录里同名文件可覆盖                            │
│  │   - 复用 drama_shot_master.core.template_engine     │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LLM 接入层（OpenAI 兼容）                            │   │
│  │   - 复用 drama_shot_master.providers.openai_compat  │   │
│  │   - DeepSeek v4 / 豆包 1.5-thinking / 自定义端点      │   │
│  │   - 4 个阶段各配独立 model + reasoning_effort         │   │
│  │   - 流式：SSE 透传 LLM stream chunks                  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  JSON 容错修复层                                      │   │
│  │   - 去代码栅 / json5 / 字段补全 / Schema 校验 / warnings│
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  项目文件系统层（Agent 唯一"状态"）                   │   │
│  │   project_dir/                                       │   │
│  │     idea.json   (候选 + chat history + 选定)         │   │
│  │     剧本.md     (剧本信息 + 镜头逐条)                  │   │
│  │     分镜.json   (教学系列 02 schema)                 │   │
│  │     prompts/                                         │   │
│  │       角色参考图/<角色名>_ref.md                       │   │
│  │       N宫格/S1.md, S2.md, ...                       │   │
│  │     .agent/                                          │   │
│  │       config.json (本项目的 LLM/模板覆盖)           │   │
│  │       logs/<stage>_<ts>.json                         │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
       │（未来阶段，本设计不实现）              
       │ 适配层（主软件内）：分镜.json → TimelineModel.to_dict()
       ▼                       
   video_panel + imggen_panel + ComfyUI 出图工作流
```

### 2.1 关键设计决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 接口形态 | FastAPI HTTP + SSE 流式 | LLM 流式输出是核心 UX；进程隔离不污染主软件开发 |
| 进程拓扑 | 主软件 spawn 子进程，退出时收尾 | 用户感知与主软件同生命周期；零额外服务管理 |
| 状态归属 | Agent 无内存 session；文件系统是唯一真相源 | 重启不丢；主软件与 Agent 共享 view；不需要 DB |
| 分镜 schema | 教学系列 02（camelCase + globalStyle + characters + stylePrompt） | 用户已验证；可独立用于豆包/即梦出图；不绑 LTX |
| 项目目录结构 | 沿用现有 `漫剧/剧本/<项目名>/` 约定 | 用户既有习惯；不引入新文件命名学习成本 |
| 输入加载 | 打开项目目录 → Agent 扫描 → 任意阶段重入 | 已写剧本.md 可跳过 1/2 步直接出分镜 |
| 创意微调 | 多轮 LLM 对话（"再生一个 / 深入第 2 个 / 改成悲剧"） | UX 最优；主软件传完整 messages，Agent 仍无状态 |
| 模板形态 | 内置代码资源 + YAML 可覆盖 | 默认即用；项目级 / 用户级 / 内置 三层优先级；复用既有 template_engine |
| LLM 切换粒度 | 每阶段独立选模型 | 创意/剧本/分镜/提示词对模型能力诉求不同；允许"flash 入库价 + pro 关键阶段" |
| 分镜生成策略 | 纯 LLM 直出 + 后端容错修复 | 用户手工经验已证可行；豆包/DeepSeek 都支持 `response_format=json_object`；修复链兜底兼顾稳定性与开发量 |

---

## 3. API 端点详解

### 3.0 通用约定

- **Base URL**：`http://127.0.0.1:18430`（端口占用时往后试 18431/18432...）
- **请求 / 响应正文**：`application/json; charset=utf-8`
- **流式端点**：`Content-Type: text/event-stream`，SSE 格式
- **所有 POST 都接收 `project_dir`** 字段（绝对路径），Agent 据此读上游产物 + 写当前阶段产物
- **`model` / `provider` / `reasoning_effort` 可选**，缺省走 `<project>/.agent/config.json` 或全局默认
- **错误响应**：HTTP 4xx/5xx + `{"error": {"code", "message", "hint", "details"}}`；中文 `hint` 是给小白看的人话

#### SSE 事件协议

| event | data 内容 | 何时发 |
|---|---|---|
| `status` | `{"phase": "thinking"\|"streaming"\|"validating"\|"saving"}` | 阶段切换 |
| `delta` | `{"text": "<chunk>"}` | LLM token 流式吐出 |
| `partial` | `{"saved": "<path>", "kind": "<…>"}` | 多产物端点的子文件落盘事件（`/prompts` 用） |
| `done` | `{"saved": "<path>\|[paths]", "result": <full_object>, "warnings": [...]}` | 最终结果 |
| `error` | `{"code", "message", "hint", "details"}` | 任何失败 |

流结束（不论成败）服务端关闭 connection。客户端断连 → Agent 检测后取消上游 LLM 调用。

### 3.1 `GET /health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "default_models": {
    "ideate": "doubao-1-5-thinking-pro-250415",
    "script": "doubao-1-5-thinking-pro-250415",
    "storyboard": "deepseek-v4-pro",
    "prompts": "deepseek-v4-flash"
  }
}
```

### 3.2 `GET /project?dir=<absolute_path>`

扫描项目目录，返回各阶段已完成状态 + 推荐下一步 + 项目级聚合状态：

```json
{
  "project_dir": "/abs/path",
  "name": "SD-005_守株待兔",            // 目录名
  "status": "storyboard_pending",      // 项目级状态（见下表），由 Agent 据 stages 推导
  "stages": {
    "ideate":     {"done": true,  "file": "idea.json",  "summary": "已选定候选 c2「躺平农夫」"},
    "script":     {"done": true,  "file": "剧本.md",    "summary": "60s · 9 镜头 · 史上最离谱的躺平"},
    "storyboard": {"done": false, "file": "分镜.json",  "summary": null},
    "prompts":    {"done": false, "subdir": "prompts/", "summary": null}
  },
  "recommended_next": "storyboard",
  "config_overrides": { "models": {...}, "templates": {...} }
}
```

主软件据 `stages.*.done` 渲染 Wizard 进度条；`recommended_next` 决定默认聚焦到哪一步；`status` 用于项目列表的状态列着色（§ 7.4）。

**项目级状态枚举**（Agent 据 stages 推导，主软件无需重复计算）：

| status | 含义 | 触发条件 |
|---|---|---|
| `empty` | 空目录或仅有 `.agent/` | 4 阶段均 done=false |
| `ideating` | 创意进行中 | idea.json 存在但无 selected_id |
| `script_pending` | 选定创意，等剧本 | ideate.done 且 script.done=false |
| `storyboard_pending` | 有剧本，等分镜 | script.done 且 storyboard.done=false |
| `prompts_pending` | 有分镜，等出图提示词 | storyboard.done 且 prompts.done=false |
| `done` | 4 阶段全 done | 全部 done=true |
| `stale_downstream` | 上游 mtime > 下游 mtime（手工编辑触发下游过期） | 检测到上游文件被后写 |

### 3.3 `POST /ideate/chat`（SSE）

创意阶段的多轮对话。主软件每次都把完整 `messages` 传回来——Agent 无状态。

**请求**：
```json
{
  "project_dir": "/abs/path",
  "context": {
    "core_idea": "古风狐妖和书生雨夜相遇",
    "genre_tags": ["古风"],
    "format": "短剧",
    "tone_tags": ["治愈"],
    "visual_style": "水墨",
    "candidate_count": 3,
    "duration_sec": 60,
    "extra_constraints": "结局不要太悲"
  },
  "messages": [
    {"role": "user", "content": "<首轮 user msg 或后续追问>"}
  ],
  "model": "doubao-1-5-thinking-pro-250415",
  "reasoning_effort": "high",
  "auto_save_idea_json": true
}
```

**SSE 输出（示意）**：
```
event: status
data: {"phase": "thinking"}

event: delta
data: {"text": "候选 1｜标题：…"}

event: status
data: {"phase": "saving"}

event: done
data: {
  "saved": "/abs/path/idea.json",
  "result": {
    "candidates": [{"id": "c1", "title": "...", "angle": "...", "summary": "...", "highlights": "...", "est_duration": 60}],
    "raw_text": "<整段 LLM 输出>",
    "warnings": []
  }
}
```

**idea.json 文件最终形态**：
```json
{
  "input": { /* context 字段原样 */ },
  "messages": [ /* 完整对话历史 */ ],
  "candidates": [ /* 当前候选列表，被微调时整体替换 */ ],
  "selected_id": "c2",
  "updated_at": "2026-05-28T..."
}
```

### 3.4 `POST /ideate/select`（非流式）

用户在 UI 上点"选这个"时调，Agent 只写 `selected_id` 到 idea.json，不调 LLM。

```json
// 请求
{"project_dir": "...", "selected_id": "c2"}

// 200
{"saved": "/abs/path/idea.json", "selected": { /* 选定的候选对象 */ }}
```

### 3.5 `POST /script`（SSE）

把 `idea.json.selected` 喂给 LLM 生成"教学系列 01"风格的分镜剧本（md，不是 JSON）。

**请求**：
```json
{
  "project_dir": "/abs/path",
  "options": {
    "length_preset": "完整版",
    "language_style": "口语化",
    "fps": 24,
    "duration_sec": 60
  },
  "model": "doubao-1-5-thinking-pro-250415",
  "reasoning_effort": "high"
}
```

Agent 内部：读 `idea.json` 拿 selected → 渲染 `templates/script.md` → 流式调 LLM → SSE delta 透传 → 落盘 `剧本.md`。

`done.result.summary = {"shot_count": 9, "total_duration": 60, "title": "..."}`（从 md 头部解析提取）。

### 3.6 `POST /storyboard`（SSE + JSON 修复）

读 `剧本.md` → 调 LLM → 拿到 JSON → **后端容错修复 + Schema 校验** → 落盘 `分镜.json`。

**请求**：
```json
{
  "project_dir": "/abs/path",
  "options": {
    "aspect_ratio": "9:16",
    "fps": 24,
    "shot_duration_default": 3,
    "density": "常规"
  },
  "model": "deepseek-v4-pro",
  "reasoning_effort": "max"
}
```

调用 LLM 时附 `response_format={"type": "json_object"}`（支持的模型）。

**SSE 输出**：delta 透传 LLM stream；`status: validating` 进修复阶段；`done.result` 含完整 schema 对象 + `warnings[]`。

### 3.7 `POST /prompts`（SSE）

读 `分镜.json` → 同时产"角色参考图提示词" + "N 宫格分镜图提示词"。

**请求**：
```json
{
  "project_dir": "/abs/path",
  "options": {
    "grid_mode": "9",
    "include_character_refs": true,
    "style_extra": "色调更冷一些",
    "negative_preset": "标准 SDXL",
    "quality_boost": true
  },
  "model": "deepseek-v4-flash",
  "reasoning_effort": "high"
}
```

内部按角色 / 按 sheet 顺序逐个调 LLM；每完成一份 SSE `partial` 事件；最终 `done` 汇总所有路径。

### 3.8 `GET/POST/DELETE /templates`

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/templates` | 列内置 + 当前项目覆盖 |
| GET | `/templates/{id}?project_dir=...` | 读单个（项目覆盖优先） |
| POST | `/templates/{id}` | 写到项目目录（默认）或 user scope |
| DELETE | `/templates/{id}?project_dir=...` | 删覆盖、回退基线 |

模板 id 固定：`ideate` / `script` / `storyboard` / `character_ref` / `grid_prompt`。

### 3.9 取消机制

所有 SSE 端点支持客户端断连即取消：FastAPI `request.is_disconnected()` 在每个 chunk 边界检查；检测到 → 关闭上游 httpx 流。主软件 UI 的"中止"按钮 = `EventSource.close()`。

### 3.10 重做下游清理（共享 query 参数）

`POST /script` / `POST /storyboard` / `POST /prompts` 均接受可选 query 参数 `?purge_downstream=true`：

- 设为 true 时，Agent 在生成当前阶段产物**之前**先删除所有下游阶段产物：
  - `/script?purge_downstream=true` → 删除 `分镜.json` + `prompts/` 全部
  - `/storyboard?purge_downstream=true` → 删除 `prompts/` 全部
  - `/prompts?purge_downstream=true` → 无下游可删，参数无效
- 主软件 UI 应在用户点"重新生成"时弹出确认框，征得同意后带此参数。
- `POST /ideate/chat` 不支持此参数（创意阶段是多轮对话累积，"重新生成"由用户在 UI 上重置 messages）。

---

## 4. 数据流时序

### 4.1 主线（端到端 happy path）

```
主软件                Agent                   文件系统              LLM
  │                     │                       │                      │
  │ spawn               │                       │                      │
  │ ──────────────────► │                       │                      │
  │ GET /health         │                       │                      │
  │ ──────────────────► │ ◄─ 200                                      │
  │                                                                     │
  │ ① 打开项目                                                          │
  │ GET /project?dir=...                                               │
  │ ──────────────────► │ ls + parse 已有产物                          │
  │ ◄── {stages...}                                                    │
  │                                                                     │
  │ ② 创意                                                              │
  │ POST /ideate/chat (SSE) ────────────────────────────────────────► │
  │                     │ 渲染模板 + 调 LLM ─────────────────────────► │
  │ ◄── delta×N ──────  │ ◄────── stream ─────────────────────────── │
  │ ◄── done {candidates[3]}                idea.json 落盘             │
  │                                                                     │
  │ ③ 用户操作：                                                        │
  │   选 c2  → POST /ideate/select → idea.json 写 selected_id          │
  │   改 c2  → POST /ideate/chat (messages 含历史 + 新 user msg)       │
  │   再生   → 同上                                                     │
  │                                                                     │
  │ ④ 生成剧本                                                          │
  │ POST /script (SSE) ──────────────────────────────────────────────► │
  │ ◄── delta×N ───── │ ◄ LLM stream                                  │
  │ ◄── done {path=剧本.md}    剧本.md 落盘                            │
  │                                                                     │
  │ ⑤ 用户编辑剧本.md（主软件 UI 内编辑器或外部）                       │
  │   保存 = 主软件 fs 写，Agent 下一阶段读最新版                         │
  │                                                                     │
  │ ⑥ 生成分镜                                                          │
  │ POST /storyboard (SSE) ──────────────────────────────────────────► │
  │ ◄── delta×N ───── │ ◄ LLM JSON stream                             │
  │                    │ status: validating → 修复链                    │
  │ ◄── done {result, warnings[]}   分镜.json 落盘                     │
  │                                                                     │
  │ ⑦ 用户编辑分镜.json                                                  │
  │                                                                     │
  │ ⑧ 生成提示词                                                        │
  │ POST /prompts (SSE) ─────────────────────────────────────────────► │
  │                    │ loop 1: 每 character → LLM → 落盘             │
  │                    │ loop 2: 每 sheet → LLM → 落盘                  │
  │ ◄── partial×K ─── │                                                │
  │ ◄── done {saved[paths]}    prompts/* 落盘                          │
  │                                                                     │
  │ 主软件关闭                                                          │
  │ ── terminate ────► │ 优雅退出（5s timeout, 否则 kill）              │
```

### 4.2 边界场景

| 场景 | Agent 行为 | 主软件 UI 行为 |
|---|---|---|
| 用户中止 | 检测断连 → 取消上游 LLM → **当前阶段产物不落盘** | "已停止"toast；下次重做该阶段 |
| 中途加入（已有上游产物） | `GET /project` 返回 done 状态 + recommended_next | UI 跳到 recommended_next 步 |
| 重做某一步 | 接收 `?purge_downstream=true` 时清下游产物 | 弹"重新生成会让下游过期"确认框 |
| 手工编辑产物后重入 | mtime 检查；不强校验 | 显示 ⚠️ 但不阻断 |
| 并发写同一项目 | 原子写（tmp + replace），最后写者赢 | 不做 file lock；文档提示避免并行 |
| LLM 失败/超时/配额 | SSE error 事件 + 语义化 code + 中文 hint | toast + 重试按钮（必要时跳设置） |
| JSON 修复失败到底 | 落盘 `分镜_raw_<ts>.txt` + error | 提供"打开 raw 文件 / 换模型重试"按钮 |

### 4.3 原子写入

所有 Agent 写文件：
```python
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(content, encoding="utf-8")
os.replace(tmp, path)   # POSIX 原子；NTFS 基本原子
```

---

## 5. Prompt 模板的迁移与变量映射

### 5.1 总体映射

| Agent 模板 id | 教学系列原型 | 用途 |
|---|---|---|
| `ideate` | 01（第一轮 + 多轮微调） | 多轮对话生候选 |
| `script` | 01（第二轮） | 选定候选 → 完整分镜剧本 |
| `storyboard` | 02 | 剧本.md → 分镜 JSON |
| `character_ref` | 03 A | 分镜.json → 角色参考图提示词 |
| `grid_prompt` | 03 B | 分镜.json → N 宫格分镜图提示词 |

### 5.2 `ideate.md`

frontmatter 变量：`core_idea` / `genre_tags` / `format` / `tone_tags` / `visual_style` / `candidate_count` / `duration_sec` / `extra_constraints`。

**改写要点 vs 教学系列 01**：
- 保留：角色定义 / 题材识别（成语典故触发额外约束）/ 风格定位 / 钩子结构 / 4 段式候选输出格式
- 改：去掉"等我发题目"，因为 Agent 第一轮就有完整 context；增加多轮意图识别指令（"用户可能说『再生一个 / 深入第 N 个 / 改成 X』，识别意图、保留未涉及的候选、只更新涉及的候选"）
- 删：原版的"小提示 / 示例"部分（移至 description 字段供 UI 显示）

### 5.3 `script.md`

frontmatter 变量：`selected_candidate`（自动注入）/ `original_input`（自动注入）/ `length_preset` / `language_style` / `fps` / `duration_sec`。

**改写要点 vs 教学系列 01 第二轮**：
- 保留：整体风格 / 钩子结构 / 镜头格式（时长/画面/旁白/字幕/音效）/ 旁白语速估算 / 质量约束
- 改：把"等我发选择"逻辑改为一次性注入；镜头节奏 3-6 秒由 `duration_sec / 镜头数` 自适应
- 加：输出前固定"剧本信息"头部块，便于 Agent 解析提取 summary（标题 / 题材类型 / 总时长 / 画面风格基调）
- 加：固定 md 锚点 `# 剧本信息` `## 镜头 01` `## 镜头 02`...，Agent 据此扫 shot_count

### 5.4 `storyboard.md`

frontmatter 变量：`script_md`（自动注入）/ `aspect_ratio` / `fps` / `shot_duration_default` / `density`。

**改写要点 vs 教学系列 02**：
- 高保真复用：全局设定 / 角色固定外貌 / globalStyle / stylePrompt 写法 / 镜头切分规则 / 输出 JSON 结构
- 改：去掉"等剧本"+"截断处理"段
- 加：头部明确"**只输出一个 JSON 代码块**"
- 加：调用时附 `response_format={"type": "json_object"}`
- 加：把现成示例 JSON（教学系列 02 末尾那段）原样嵌入 prompt 末尾作为 few-shot example

### 5.5 `character_ref.md`

frontmatter 变量：`storyboard_json`（自动注入）/ `extra_constraints`。

**改写要点 vs 教学系列 03 A**：
- 几乎完整移植（这套提示词已经非常成熟）
- 改：明确每段 markdown 头部用 `### 角色：<name>`，Agent 据此 split 文本 → 分文件落盘

### 5.6 `grid_prompt.md`

frontmatter 变量：`storyboard_json`（自动注入）/ `grid_mode` / `style_extra` / `quality_boost` / `negative_preset`。

**改写要点 vs 教学系列 03 B**：
- 保留：分组规则 / 每段必含小节 / 像素尺寸参考
- 改：默认 9 格 → 由 `grid_mode` 动态（single / 4 / 9）
- 加：`style_extra` 注入"画风锁定"段尾
- 加：`quality_boost=true` 时在画面主体细节末尾追加预设画质词
- 加：`negative_preset` 注入提示词尾部"负面词"段（教学系列原版没显式负面词）

### 5.7 模板查找与覆盖优先级

```
1. <project_dir>/.agent/templates/<id>.md       项目级
2. <user_home>/.screenwriter_agent/<id>.md      用户级
3. <agent_install_dir>/templates/<id>.md        内置基线（不可写）
```

响应里带 `source` 字段：`project | user | builtin`。`POST` 默认写项目级（除非显式 `scope=user`）。

---

## 6. 错误处理 / JSON 修复 / Warnings

### 6.1 错误码总表

| code | HTTP | 中文 hint 样例 |
|---|---|---|
| `PROJECT_DIR_NOT_FOUND` | 400 | "选的路径打不开，确认一下是不是被改名或挪走了？" |
| `PROJECT_DIR_NOT_WRITABLE` | 400 | "这个目录没写权限，换个位置或检查文件夹属性" |
| `UPSTREAM_PRODUCT_MISSING` | 400 | "还没生成剧本，先回到上一步生成剧本再来" |
| `TEMPLATE_RENDER_FAILED` | 500 | "提示词模板里用到了未定义的字段，可能你改坏了——可以恢复默认模板试试" |
| `LLM_AUTH_FAILED` | 401 | "豆包/DeepSeek 的 API key 错了，去设置里检查" |
| `LLM_RATE_LIMIT` | 429 | "请求太快了，{retry_after}s 后重试，或换 flash 模型省额度" |
| `LLM_QUOTA_EXCEEDED` | 402 | "豆包额度用完了，去火山方舟充值，或暂时换 DeepSeek" |
| `LLM_TIMEOUT` | 504 | "模型 5 分钟没回话，可能在排队或服务繁忙，再试一次" |
| `LLM_CONTENT_FILTERED` | 451 | "模型不愿意生成这段内容，可能题材里有触发词，调整一下输入" |
| `LLM_NETWORK_ERROR` | 502 | "连不上模型服务，检查网络/代理/base_url" |
| `LLM_INVALID_RESPONSE` | 502 | "模型这次回答异常，换个模型或重试" |
| `JSON_REPAIR_FAILED` | 422 | "模型这次没给出 JSON，原始输出存到了 分镜_raw.txt，可以换模型再试或手工修一下" |
| `SCHEMA_VALIDATION_FAILED` | 422 | "分镜数据缺关键字段，已尽量补全；红色高亮处需要你手工确认" |
| `CONCURRENT_WRITE_DETECTED` | 409 | "这个文件刚被外部修改过，确认是否覆盖" |
| `INTERNAL_ERROR` | 500 | "出了点意外，技术细节已写到日志：{log_path}" |

统一响应体：
```json
{
  "error": {
    "code": "JSON_REPAIR_FAILED",
    "message": "<英文 message>",
    "hint": "<中文人话>",
    "details": {"raw_output_path": "...", "repair_steps_tried": [...]}
  }
}
```

### 6.2 JSON 修复链（仅 `/storyboard` 使用）

```
原始 raw_text
  │
  │ Step 1: strip_codefence
  │   - 剥离 ```json ... ``` 包裹
  │   - 用正则定位首个 '{' 到最末 '}'
  ▼
candidate_text
  │
  │ Step 2: try strict json.loads
  ▼
 ┌ 成功 → obj (Step 5)
 └ 失败
       │
       │ Step 3: json5.loads（容忍尾逗号 / 单引号 / 注释 / 未引号 key）
       ▼
      ┌ 成功 → obj
      └ 失败
            │
            │ Step 4: regex 兜底修复
            │   - 中文引号 → "
            │   - 尾逗号 ,] / ,} → ] / }
            │   - 拼接被截断的字符串字面量
            │   - 再次 try json.loads
            ▼
           ┌ 成功 → obj
           └ 失败 → 抛 JSON_REPAIR_FAILED + 落盘 raw
                  
Step 5: 字段补全
  - 缺 title → 从剧本.md 头部"标题"取
  - 缺 aspectRatio → options.aspect_ratio
  - 缺 fps → options.fps
  - 缺 totalDuration → sum(shots[].duration) 或按 default 估算
  - 缺 globalStyle → 从 options.visual_style 生成一句话
  - shots[i] 缺 shotId → 按位置生成 S01_<i+1>
  - shots[i] 缺 duration → shot_duration_default
  - shots[i] 缺 composition → 按 description 关键词推断（近景/中景/全景）
  - 每补一项 → warnings.append({path, issue, severity})

Step 6: Schema 校验（pydantic）
  - title 非空、shots 长度 ≥1
  - 每 shot 必有 shotId + description
  - characters[].name 非空 + appearance ≥ 10 字
  - stylePrompt ≥ 30 字 + 必须含 globalStyle 关键词（防漏锁画风）
  - 硬性失败 → SCHEMA_VALIDATION_FAILED
  - 软性失败 → warnings

Step 7: 原子写入 分镜.json
```

### 6.3 Warnings 分级

| severity | 含义 | UI 视觉 |
|---|---|---|
| `info` | 已自动修复且大概率没问题（如补默认 fps） | 灰色提示 ▷ |
| `warning` | 已修复但建议人工核对 | 黄色 ⚠ + 行号锚点 |
| `error` | 字段缺失且无法可靠推断 | 红色 ✕ + 行号锚点 |
| `critical` | 修复后仍不合 schema 关键约束 | 红底 ✕ + toast |

单条 warning：
```json
{
  "path": "shots[3].duration",
  "issue": "字段缺失，已按默认 3s 补全",
  "severity": "warning",
  "suggested_fix": "看一下镜头 3 的画面复杂度，长动作建议 5-6s",
  "auto_fix_applied": true
}
```

### 6.4 重试策略

| 错误 | Agent 自动 | 主软件 UI |
|---|---|---|
| `LLM_RATE_LIMIT` | 不重试 | `retry_after` 倒计时按钮 |
| `LLM_TIMEOUT` | 不重试 | 重试按钮 |
| `LLM_NETWORK_ERROR` | 不重试 | 重试 + 检查网络 hint |
| `LLM_INVALID_RESPONSE` | 重试 1 次（同模型） | 用户可再触发 |
| `JSON_REPAIR_FAILED` | 不重试 | "换模型重试"下拉 |

Agent 故意不做自动换模型——换模型涉及费用/风格差异，由主软件 UI 显式呈现。

### 6.5 日志与可观测性

每次 LLM 调用后写 `<project_dir>/.agent/logs/<stage>_<ts>.json`：

```json
{
  "ts": "2026-05-28T12:34:56+08:00",
  "stage": "storyboard",
  "model": "deepseek-v4-pro",
  "reasoning_effort": "max",
  "input_tokens": 1234,
  "output_tokens": 5678,
  "duration_ms": 23400,
  "repair_steps": ["strip_codefence", "json5"],
  "warnings_count": 3,
  "warnings_by_severity": {"info": 1, "warning": 2, "error": 0},
  "error": null,
  "raw_output_kept": false
}
```

`GET /project/logs?dir=...&stage=storyboard&limit=10` 返回最近 N 条（不含 raw）。

### 6.6 raw_output 保留策略

`分镜_raw_<ts>.txt` 仅在以下情形落盘：

1. `JSON_REPAIR_FAILED`
2. `SCHEMA_VALIDATION_FAILED` 且 severity=critical
3. 用户在 `.agent/config.json` 显式开启 `"always_keep_raw": true`（默认 false）

带时间戳防覆盖；`.agent/logs/` 旧 raw 自动清理：超过 30 天或文件数超 50 时按 mtime 滚动删除。

---

## 7. 包结构 / 主软件对接面 / 测试策略

### 7.1 Agent 包目录骨架

```
shot-drama-master/
├── drama_shot_master/            主软件包（既有）
├── sound_track_agent/            既有配乐 agent（参照对象）
├── screenwriter_agent/           【新增】
│   ├── __init__.py               版本号、公共导出
│   ├── __main__.py               python -m screenwriter_agent
│   ├── server.py                 FastAPI app + uvicorn 启动入口
│   ├── config.py                 运行时配置 / 命令行参数解析
│   ├── routes/
│   │   ├── health.py             GET /health
│   │   ├── project.py            GET /project /project/logs
│   │   ├── ideate.py             POST /ideate/chat /ideate/select
│   │   ├── script.py             POST /script
│   │   ├── storyboard.py         POST /storyboard
│   │   ├── prompts.py            POST /prompts
│   │   └── templates.py          GET/POST/DELETE /templates
│   ├── core/
│   │   ├── llm_client.py         复用 drama_shot_master.providers.openai_compat 的薄封装
│   │   ├── template_loader.py    三层优先级查找（项目/用户/内置）
│   │   ├── json_repair.py        §6.2 那条修复链
│   │   ├── schema_validator.py   pydantic models for 教学系列 02 schema
│   │   ├── project_scanner.py    /project 的扫目录逻辑
│   │   ├── sse.py                SSE 事件 helpers
│   │   ├── atomic_write.py       tmp + os.replace
│   │   └── logger.py             按 stage 写 .agent/logs/<ts>.json
│   ├── models/
│   │   ├── requests.py
│   │   ├── responses.py
│   │   ├── storyboard_schema.py
│   │   └── idea_schema.py
│   ├── templates/                5 套内置模板（§5）
│   │   ├── ideate.md
│   │   ├── script.md
│   │   ├── storyboard.md
│   │   ├── character_ref.md
│   │   └── grid_prompt.md
│   └── cli.py                    离线 CLI（便于单元测试每阶段）
└── tests/
    └── test_screenwriter_agent/  【新增】
        ├── test_json_repair.py
        ├── test_schema_validator.py
        ├── test_template_loader.py
        ├── test_project_scanner.py
        ├── test_sse_helpers.py
        ├── test_atomic_write.py
        ├── test_route_health.py
        ├── test_route_project.py
        ├── test_route_ideate.py
        ├── test_route_script.py
        ├── test_route_storyboard.py
        ├── test_route_prompts.py
        ├── test_route_templates.py
        ├── test_e2e_smoke.py
        ├── fixtures/
        │   ├── sample_idea.json
        │   ├── sample_script.md
        │   ├── sample_storyboard.json
        │   ├── dirty_storyboards/
        │   └── mock_llm_responses/
        └── conftest.py
```

### 7.2 新增依赖（pyproject.toml）

| 包 | 用途 | License |
|---|---|---|
| `fastapi` | HTTP 框架 | MIT |
| `uvicorn[standard]` | ASGI 服务器 | BSD |
| `pydantic` ≥2 | Schema 校验 | MIT |
| `json5` | 容错 JSON 解析 | Apache-2.0 |
| `sse-starlette` | SSE 流封装（可选） | BSD |
| `httpx` | 主软件 client 侧 | BSD |

全部非 GPL。

### 7.3 主软件对接面（drama_shot_master 内的新增 / 改动）

**新增**：
```
drama_shot_master/
├── agents/                                       【新增】
│   ├── screenwriter_client.py                    AgentClient 类（subprocess + httpx + SSE）
│   └── screenwriter_lifecycle.py                 spawn / health-poll / terminate
├── ui/panels/
│   └── screenwriter_panel.py                     【新增】Wizard 主面板
├── ui/dialogs/
│   └── screenwriter_settings_dialog.py           【新增】API key + 模型选型
└── ui/widgets/
    ├── ideate_chat_panel.py                      【新增】创意阶段聊天面板
    ├── storyboard_table_view.py                  【新增】分镜双视图
    └── warnings_inline.py                        【新增】warnings 行内高亮
```

**改动**：
```
drama_shot_master/
├── main.py                  启动时 spawn agent；退出时收尾
├── config.py                加 screenwriter_agent_port / screenwriter_models / screenwriter_api_keys
├── ui/nav_config.py         导航 + 阶段重排（§7.4）
└── ui/app_shell.py          导航栏页签注册
```

### 7.4 导航栏整合（与既有面板风格一致）

#### nav_config.py 改动

**FUNCS**（新增 `screenwriter` 放在最前）：
```python
FUNCS = [
    ("编剧", "screenwriter"),    # 新增·剧本筹备
    ("拆图", "split"),
    ("拼图", "combine"),
    ("裁边", "trim"),
    ("出图", "imggen"),
    ("生视频", "video_gen"),
    ("配音", "dubbing"),
    ("配乐", "soundtrack"),
]
```

**PHASES**（新增"剧本筹备"阶段、其它阶段编号顺延）：
```python
PHASES = [
    ("① 剧本筹备", ["screenwriter"]),           # 新增
    ("② 素材准备", ["split", "combine", "trim"]),
    ("③ 分镜创作", ["imggen"]),
    ("④ 视频出片", ["video_gen", "dubbing", "soundtrack"]),
]
```

**TASK_KEYS** 加入 `screenwriter`（视为任务管理类，因为面板形态是"项目列表 + Wizard 编辑"）：
```python
TASK_KEYS = {"imggen", "video_gen", "soundtrack", "dubbing", "screenwriter"}
```

**ICONS** 新增：
```python
ICONS = {
    "screenwriter": "edit.svg",   # 新增；可换为 script.svg / pen.svg
    ...
}
```

`assets/icons/edit.svg` 需新增同风格 SVG（线条粗细、视觉权重与既有 cut.svg / palette.svg / video.svg 一致；建议沿用 lucide-icons 或 tabler-icons 的 `feather-square` 风格）。

#### UI 风格一致性要求

新面板 `screenwriter_panel.py` 必须遵循既有 UX 规范：

| 维度 | 既有约定（来自 video_panel / dub_panel / imggen_panel） | screenwriter_panel 实现 |
|---|---|---|
| 顶部按钮排 | QHBoxLayout + `bar.addStretch(1)` 后置 | 沿用：新建项目 / 打开项目 / 删除 |
| 任务列表 | QTableWidget（既有 video/dub/imggen 都用），首列名称，列宽按 `_fit_name_col` 模式 | 沿用：列出已知项目目录 |
| 主-详结构 | TaskWorkspacePage（master 上限 300、splitter [280, 900]） | 复用 `TaskWorkspacePage` 的 master-detail 骨架；详情区"editor" = wizard widget（QStackedWidget 套 4 子面板），TaskWorkspacePage 视角下它仍是单个 widget，不破坏既有约定 |
| 详情头条 | 任务名 QLabel + ⧉ 浮出按钮 | 沿用 |
| 配色 | QSS 主题（既有暗色） | 沿用项目 `_STATUS_COLORS` 风格定义；新增"状态"映射：草稿/创意中/剧本中/分镜中/已完成 |
| 按钮命名 | "新建" / "复制" / "删除"（避免长动名词） | 沿用；wizard 内步骤按钮用"生成" / "重新生成" / "下一步" |
| Toast/提示 | `QMessageBox.information / warning` + 中文 | 沿用 |
| 表单 | QFormLayout + QPlainTextEdit + 调整窗 | 沿用 |
| 右侧"快捷"侧栏 | dub_panel 的 360px 折叠分组（参考 `_CollapsibleGroup`） | 在分镜阶段可选用，复用同一控件 |

#### 项目列表（master 区）

```
（master 上限 300）
┌────────────────────┐
│ [新建项目][打开...][删除] │
├────────────────────┤
│ 名称       状态     │
│ 守株待兔   分镜中   │   ← 用 _STATUS_COLORS 着色
│ 仙界BUG    已完成   │
│ ...                │
└────────────────────┘
```

行右键菜单：在文件管理器打开 / 复制路径 / 删除项目（与既有面板风格一致）。

#### 详情区（wizard）

```
┌─────────────────────────────────────────────┐
│ 项目名 · SD-005_守株待兔        ⧉ 浮出独立窗    │
├─────────────────────────────────────────────┤
│ ① 创意  ──●  ② 剧本  ──○  ③ 分镜  ──○  ④ 提示词  ──○   │  ← 进度条/Tab
├─────────────────────────────────────────────┤
│ 阶段内容（QStackedWidget 切换 4 个子面板）  │
└─────────────────────────────────────────────┘
```

- 已完成的步骤可回点（不阻断），下游过期时显示 ⚠️ 但不强阻断
- 当前活跃 step 用既有 `_STATUS_COLORS["生成中"]`（蓝色）
- 步骤间分隔线沿用 video_panel 的 QFrame HLine 风格

### 7.5 AgentClient API（主软件用的客户端封装）

```python
class ScreenwriterClient:
    """主软件单例。负责 spawn agent + 发请求 + 解析 SSE。"""

    def start(self) -> None: ...
    def shutdown(self) -> None: ...
    def scan_project(self, project_dir: Path) -> ProjectState: ...

    async def ideate_chat(self, project_dir: Path,
                          context: IdeateContext,
                          messages: list[ChatMessage],
                          model: str | None = None) -> AsyncIterator[SSEEvent]: ...
    def ideate_select(self, project_dir: Path, selected_id: str) -> dict: ...
    async def generate_script(self, ...) -> AsyncIterator[SSEEvent]: ...
    async def generate_storyboard(self, ...) -> AsyncIterator[SSEEvent]: ...
    async def generate_prompts(self, ...) -> AsyncIterator[SSEEvent]: ...

    def cancel_current(self) -> None: ...
```

### 7.6 进程生命周期

- spawn 命令：`sys.executable -m screenwriter_agent --port <auto-pick>`
- stdout/stderr 重定向到 `<user_dir>/logs/screenwriter_agent.log`（滚动）
- 父进程崩溃时子进程会成为孤儿——Windows 下 ok（父退出即 close handle）；Linux 下加 `prctl(PR_SET_PDEATHSIG)` 兜底
- 端口冲突时往后试 +1..+9，写实际端口到 `.agent_port` 文件供主软件读取
- spawn 时记录 PID 到 `.pid` 文件；下次启动检查并清理

### 7.7 测试策略

#### 单元测试（offline，~50 用例）

| 模块 | 用例数 | 关键场景 |
|---|---|---|
| `json_repair` | ~15 | 每种脏 JSON 样本；修复链每步成功/失败；regex 兜底；完全乱码 |
| `schema_validator` | ~10 | 缺各字段、空 shots、stylePrompt 不含 globalStyle、duration < 0 |
| `template_loader` | ~5 | 三层优先级；frontmatter 解析错误回退；未定义变量 |
| `project_scanner` | ~8 | 0/1/2/3/4 步已完成的各种组合 |
| `sse` | ~5 | event 序列化、各类型 |
| `atomic_write` | ~3 | 普通写、异常不留半成品、并发竞争 |
| schema round-trip | ~5 | idea.json / storyboard pydantic 序列化反序列化 |

#### 路由集成测试（mock LLM，~25 用例）

每个 route 用 FastAPI `TestClient`，按章节 3 端点全覆盖。mock LLM provider 在 `conftest.py` 提供 fixture。

#### 端到端 smoke（mock LLM，1 用例）

`test_e2e_smoke.py`：空目录开始，依次跑 4 阶段，断言产物文件齐全 + 内容形状合规。

#### 真 LLM 烟雾测试（可选，手动）

`@pytest.mark.requires_real_llm`，默认 skip；本地 `pytest -m requires_real_llm` 跑完整链路，落产物到 `tests/_smoke_output/<ts>/` 人工检视。

#### CI 矩阵

- OS：Linux + Windows
- Python：3.11+
- 命令：`pytest tests/test_screenwriter_agent/ -q`
- 真 LLM smoke 不在 CI（避账单）

### 7.8 上线分阶段（YAGNI）

| Phase | 范围 |
|---|---|
| **P1（MVP）** | 4 阶段 endpoint + 内置模板 + JSON 修复 + 主软件 wizard 面板 + 导航整合 |
| **P2** | warnings 行内高亮 / 聊天面板美化 / 重做下游清理 / 浮出独立窗 |
| **P3** | 用户级模板编辑器 / 多项目历史侧栏 / `/project/logs` 可视化 |

P1 完成即 v0.1.0。

### 7.9 风险与缓解

| 风险 | 缓解 |
|---|---|
| 子进程残留（主软件 crash 未收尾） | spawn 时写 .pid；下次启动检查并清理；Linux 加 PDEATHSIG |
| 端口冲突 | 18430+1..+9 试；写 `.agent_port` |
| 大模型计费失控 | UI 每次调用前显示预估 tokens / 累计消耗 |
| LLM 幻觉 / 史实错误 | 模板强约束"宁可模糊不要编造"；warnings 不阻断由用户判断 |
| 项目目录被外部并发写 | 原子写 + mtime 校验，不强 lock |
| Windows 路径中文 / OneDrive 同步 | pathlib + utf-8 严格；CI Windows 矩阵覆盖 |

---

## 8. 后续工作（不在本设计范围）

- **分镜.json → TimelineModel 适配层**：主软件侧的转换器，让用户点"用这套分镜做视频"时把 stylePrompt 灌入 video_panel 的 local_prompt、把 duration 换算成 length_frames、把 characters 的固定外貌写入 global_prompt 头部。这一层属主软件内部改造，不涉及 Agent。
- **图生图集成**：把"prompts/N宫格/Sk.md"接入 imggen_panel 一键提交豆包/即梦/nano-banana 出图，回填到 ref图/ 目录。
- **角色参考图复用**：当用户已经生成过 `<name>_ref.png`，下一次同项目跑 prompts 时自动检测并直接复用 ref，不再重新生成参考图提示词。

---

## 9. 参考资料

- [DeepSeek v4 API 文档](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion)
- [豆包 1.5-thinking-pro 火山方舟文档](https://www.volcengine.com/docs/82379/1536428)
- [火山方舟兼容 OpenAI SDK](https://www.volcengine.com/docs/82379/1330626)
- 项目内：`漫剧/剧本/教学系列/01-03 *.md`（5 套内置模板的原型）
- 项目内：`screenwriter_agent/doubao research.md`（豆包给的对照方案）
- 项目内：`drama_shot_master/providers/openai_compat.py`（LLM 抽象层）
- 项目内：`drama_shot_master/core/template_engine.py`（模板引擎）
- 项目内：`drama_shot_master/core/prompt_refiner.py`（JSON 修复借鉴）
- 项目内：`drama_shot_master/ui/nav_config.py`（导航 / 阶段 / 图标的事实源）

---

**完。**
