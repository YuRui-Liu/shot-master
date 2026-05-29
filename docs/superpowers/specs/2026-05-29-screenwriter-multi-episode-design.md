# 编剧多集化（Sub-spec #1）设计 Spec

**日期：** 2026-05-29
**作者：** Brainstorm pass with user
**状态：** Draft → 待用户最终审阅
**范围：** 编剧管线 v2 的第 1 个子项目——多集剧本基础。后 3 个子项目（分镜图提示词 / 视频提示词 / 配音配乐提示词）会各自独立 brainstorm。

---

## 1. 背景与目标

当前编剧管线（v1）4 阶段——创意 / 剧本 / 分镜 / 提示词——假设一项目对应一集剧本。但用户场景里常见多集系列剧（3-20 集），整套架构需要按集组织产物与流程。

**目标：** 引入多集语义。剧本阶段先产「集索引」（`剧本.json`）+ 每集 markdown（`剧本_E1.md` ...），分镜阶段按集产 `分镜_E*.json`，后续提示词阶段按集组织产物目录。N=1 单集情况完全兼容、不暴露多集机械感。

**关键约束：**
- 复用既有 4 子面板和 TaskWorkspacePage 范式
- 保持 v1 单集项目自动迁移（一次性确认对话）
- N=1 路径仍统一产 `剧本.json` + `剧本_E1.md`，下游阶段一份逻辑读两种规模
- 多集并发生成支持（worker dict key 升级到 `(project_dir, episode_id)`）
- Sub-spec #1 范围明确：剧本 + 分镜 + 提示词的过渡兼容。不重构提示词 stage 内部结构（留给 Sub-spec #2）

---

## 2. 架构

```
ScreenwriterPanel (复用现架构)
  └ QSplitter[ScreenwriterTaskManager | ScreenwriterWizardHost]
      └ ScreenwriterWizardHost (4 子面板 stack 不变)
          ├ IdeatePage      (不变)
          ├ ScriptPage      (大改：参数栏 + 大纲表 + 当前集 md 编辑器)
          ├ StoryboardPage  (顶部加 _EpisodeSelector + per-episode 适配)
          └ PromptsPage     (顶部加 _EpisodeSelector + 路径走 prompts/E{id}/)
```

**新增共享组件 `_EpisodeSelector(QWidget)`：**
- 读 `剧本.json.episodes` + 文件存在性扫描
- 显示 `QComboBox`（label 含状态点）+ 右侧状态点 dot row
- 信号 `episodeChanged(str)` 携带新 episode_id
- 切集时调宿主 page `try_release()` 拦截 dirty

**数据流：**
1. IdeatePage 推进 → ScriptPage 接管 `创意.json.selected`
2. ScriptPage 按集数 N=1 走快路径 / N>1 走「大纲→分集」二步；产 `剧本.json` + `剧本_E*.md`
3. 推进到分镜 → 携带 `selected_episode` 写入 `剧本.json`，StoryboardPage 集选择器初值用之
4. StoryboardPage 按当前集生成 `分镜_E{id}.json`
5. 推进到提示词 → PromptsPage 集选择器同步当前集，落盘到 `prompts/E{id}/`

---

## 3. 数据模型

### 3.1 `剧本.json` (集索引)

```json
{
  "title": "整剧标题",
  "episode_count": 3,
  "selected_episode": "E1",
  "episodes": [
    { "id": "E1", "title": "第 1 集：邂逅", "summary": "三段式概要..." },
    { "id": "E2", "title": "第 2 集：…", "summary": "..." },
    { "id": "E3", "title": "第 3 集：…", "summary": "..." }
  ],
  "input": {
    "core_idea": "...",
    "genre_tags": [...]
  },
  "updated_at": "2026-05-29T10:00:00"
}
```

### 3.2 集 ID 规范

- 必须匹配 `^E\d+$`（大写 E + 1-based 整数）
- 跨平台路径片段安全（避免空格、中文、特殊字符）
- pydantic schema (`EpisodeEntry.id`) 强制校验

### 3.3 Per-episode 产物

| 阶段 | 文件 |
|---|---|
| 剧本 | `剧本_E1.md`, `剧本_E2.md`, ... |
| 分镜 | `分镜_E1.json`, `分镜_E2.json`, ... |
| 提示词 | `prompts/E1/角色参考图/*_ref.md`, `prompts/E1/N宫格/S*.md`, `prompts/E2/...` |

### 3.4 schema 校验（pydantic）

新建 `screenwriter_agent/models/script_index_schema.py`：

```python
class EpisodeEntry(BaseModel):
    id: str = Field(..., pattern=r"^E\d+$")
    title: str
    summary: str

class ScriptIndex(BaseModel):
    title: str = ""
    episode_count: int = Field(..., ge=1, le=20)
    selected_episode: str = ""
    episodes: list[EpisodeEntry]
    input: dict = Field(default_factory=dict)
    updated_at: str = ""
```

---

## 4. 文件结构 + 向后兼容

### 4.1 新项目目录

```
<项目根>/
  创意.json                  (v1 已存在)
  剧本.json                  ← 集索引（新）
  剧本_E1.md                 ← per-episode (新)
  剧本_E2.md
  剧本_E3.md
  分镜_E1.json               ← per-episode (新)
  分镜_E2.json
  分镜_E3.json
  prompts/
    E1/
      角色参考图/*_ref.md
      N宫格/S*.md
    E2/
      ...
```

### 4.2 旧项目检测 + 迁移

| 旧 | 检测 | 行为 |
|---|---|---|
| `剧本.md` 存在但无 `剧本.json` | 老项目（单集，v1） | UI 弹「检测到旧版单集剧本，是否迁移到多集结构？」 |
| 用户选「是」 | — | 建 `剧本.json`（1 集，title=项目名）+ 重命名 `剧本.md` → `剧本_E1.md` |
| 用户选「否」 | — | 视为只读浏览模式，推进按钮禁用，banner 提示「先迁移」 |
| `分镜.json` 存在但无 `分镜_E1.json` | 同上 | 迁移时同步重命名 |
| 任务栏状态点 | 兼容旧名 | `_paths.py` helper 优先新名兜底旧名 |

### 4.3 helper 扩展

`screenwriter_agent/core/paths.py` + `drama_shot_master/ui/widgets/screenwriter/_paths.py` 加：

```python
def script_index_path(project_dir: Path) -> Path
def script_episode_path(project_dir: Path, episode_id: str) -> Path
def script_episode_read_path(project_dir, episode_id) -> Path | None  # 兜底旧名
def storyboard_episode_path(project_dir, episode_id) -> Path
def storyboard_episode_read_path(project_dir, episode_id) -> Path | None
def is_valid_episode_id(s: str) -> bool
def episode_prompts_dir(project_dir: Path, episode_id: str) -> Path
```

---

## 5. ScriptPage UI 重构

### 5.1 布局

```
┌─ 参数栏 ────────────────────────────────────────────┐
│ [集数 N: 1▾] [时长/集 60s▾] [语言风格 口语化▾]      │
│                          ●流式  [生成大纲]  [中止] │
├─ 上游 banner（创意.json 缺失） ────────────────────│
├─ 大纲表 QTableWidget ──────────────────────────────│
│ ┌───┬──────────┬──────────────┬──────────┐         │
│ │集 │ 标题     │ 概要          │ 操作      │         │
│ ├───┼──────────┼──────────────┼──────────┤         │
│ │E1 │ 第1集    │ 概要…         │[生成此集]│         │
│ │E2 │ 第2集    │ …             │[生成此集]│         │
│ └───┴──────────┴──────────────┴──────────┘         │
│ [一键全集 ▶]   N 集已完成 / N 集                   │
├─ 当前集 md 编辑器（QPlainTextEdit） ───────────────│
│ ## 镜头 1 …                                         │
├─ 操作栏 ────────────────────────────────────────────│
│ [💾 保存] [📂 打开] [{ } 看JSON]  [推进到分镜 →]   │
└─────────────────────────────────────────────────────┘
```

### 5.2 交互流（按集数）

**N=1 快路径：**
- 参数栏 N=1 → 「生成大纲」按钮文案自动切「生成剧本」
- 单次 `/script/episode` LLM 调用：agent 端检测 `剧本.json` 不存在自动建 1 集索引 + 落盘 `剧本_E1.md`
- 大纲表只 1 行自动选中

**N>1 二步：**
1. 点「生成大纲」→ `/script/outline` 流式产 `剧本.json`（N 集 entries）
2. 用户可在 QTableWidget cell 直接编辑 title / summary，dirty 自动保存到 `剧本.json`
3. 点行尾「生成此集」→ `/script/episode` 携带 episode_id → `剧本_E{id}.md`
4. 点「一键全集」→ **顺序**触发各集（UX 策略：避免 LLM 速率限制 + 让用户能看进度。架构上 worker dict 支持并发，详见 §9.6）。批量进行时禁用其他「生成此集」按钮防误点
5. 单击行 → 下方编辑器加载该集 md，用户可手改

### 5.3 dirty 跟踪

- 大纲表 dirty（cell 改） → `剧本.json` 保存按钮亮
- 当前集 md dirty → md 保存按钮亮
- 集 dirty 时切别集 → `try_release()` 弹「保存/丢弃/取消」

### 5.4 「推进到分镜 →」

- dirty → try_release 拦截
- 设置 `剧本.json.selected_episode = 当前选中行 id` 并落盘
- emit `stageAdvanceRequested(2)`
- StoryboardPage 集选择器初值从 `剧本.json.selected_episode` 读

---

## 6. StoryboardPage UI 重构

### 6.1 布局变化（最小化）

顶部加「集选择行」，其余保留：

```
┌─ 集选择行 (新) ─────────────────────────────────────┐
│ [当前集: E1 ▾]  ✓ E1  ✓ E2  ○ E3                   │
├─ 参数栏（原有）                                     │
├─ 上游 banner（剧本_E{id}.md 缺失）                 │
├─ 全局头（per-episode）：标题/时长/globalStyle/角色 │
├─ 表格（原有）                                       │
├─ warnings banner（原有）                            │
└─ 操作栏  [保存][看JSON]  [推进到提示词 →]         │
└─────────────────────────────────────────────────────┘
```

### 6.2 切集流程

1. 用户选 E2 → emit `episodeChanged("E2")`
2. StoryboardPage 接 → `try_release()` 当前 E1 dirty
3. 拒绝 → ComboBox `blockSignals` 还原 E1
4. 接受 → `set_episode("E2")`:
   - `self._sb_path = path / "分镜_E2.json"`
   - 上游 banner 检查 `剧本_E2.md`
   - `_load_from_disk()` 加载 E2
   - 更新表格 / 全局头

### 6.3 生成行为

- 「生成分镜」→ `/storyboard` 携带 `episode_id` → 读 `剧本_E{id}.md` → 写 `分镜_E{id}.json`
- worker dict key 改 `(Path, episode_id)`，多集并发不互踩
- partial / done / error event 数据加 `episode_id`，UI 按当前过滤

### 6.4 任务栏状态点

任务栏「分镜」列推断升级：
- 所有集都有 `分镜_E*.json` → `✓`
- 部分有 → 显示 `2/3`
- 全无 → `○`

「提示词」列同理。

---

## 7. PromptsPage 过渡兼容（Sub-spec #1 不重构内部）

### 7.1 改动（最小）

- 顶部加 `_EpisodeSelector`
- 切集 → `self._sb_path = path / "分镜_E{id}.json"` + `_load_sb()` + `_rebuild_tree()`
- 上游 banner 检查 `分镜_E{id}.json`
- 「生成提示词」→ `/prompts` 携带 `episode_id`
- 落盘路径 `prompts/角色参考图/` → `prompts/E{id}/角色参考图/`，N宫格同理
- partial event 加 `episode_id`，UI 按当前过滤

### 7.2 `_ProductTree` 适配

`build_from_sb()` 加 `episode_id` 参数，路径计算用 `prompts_dir / f"E{id}" / "角色参考图" / ...`，状态点扫描自动跟随。

---

## 8. Agent 端 endpoints

### 8.1 改造现有

| Endpoint | 改动 |
|---|---|
| `POST /script` | **删除** |
| `POST /storyboard` | Req body 加 `episode_id: str` 必填；读 `剧本_E{id}.md` 写 `分镜_E{id}.json` |
| `POST /prompts` | Req body 加 `episode_id: str` 必填；读 `分镜_E{id}.json` 写 `prompts/E{id}/...` |

### 8.2 新增（替代 `/script`）

**`POST /script/outline`** — 多集大纲生成：

```python
class ScriptOutlineReq(BaseModel):
    project_dir: str
    episode_count: int = Field(..., ge=1, le=20)
    options: ScriptOptions
    creds: LLMCreds | None = None
    model: str | None = None
    reasoning_effort: str = "high"
```

- 行为：读 `创意.json.selected` → LLM 产出 `剧本.json` → 流式 delta（JSON 修复链同 storyboard）→ done 落盘
- SSE: `status` / `delta` / `done(saved, result={episodes:[...]})` / `error`

**`POST /script/episode`** — 单集 md 生成：

```python
class ScriptEpisodeReq(BaseModel):
    project_dir: str
    episode_id: str  # ^E\d+$
    options: ScriptOptions
    creds: LLMCreds | None = None
    model: str | None = None
    reasoning_effort: str = "high"
```

- 行为：读 `剧本.json` 找该 entry → 读 `创意.json.selected` → LLM → 流式 delta → done 落盘 `剧本_E{id}.md`
- **N=1 优化**：FE 直调 `/script/episode("E1")` 跳过 outline；agent 端检测 `剧本.json` 不存在自动建 1 集索引

### 8.3 模板新增

`screenwriter_agent/templates/` 加 builtin：
- `script_outline.md`：输入「创意 candidate + episode_count + options」→ 输出 JSON 含 episodes 数组
- `script_episode.md`：输入「创意 + 大纲该集条目 + options」→ 输出 markdown 含 `## 镜头 N` 段

旧 `script.md` 保留作 legacy 备份，实际 BUILTIN_IDS 加这两个新名。

### 8.4 `purge_downstream` 集感知扩展

`downstream.py:purge_downstream(stage, *, episode_id=None)`：

| 调用 | 行为 |
|---|---|
| `purge_downstream("script_outline")` | 删 `剧本.json` + 所有 `剧本_E*.md` + 所有 `分镜_E*.json` + `prompts/` |
| `purge_downstream("script_episode", episode_id="E2")` | 删 `剧本_E2.md` + `分镜_E2.json` + `prompts/E2/` |
| `purge_downstream("storyboard", episode_id="E2")` | 删 `分镜_E2.json` + `prompts/E2/` |
| `purge_downstream("prompts", episode_id="E2")` | 删 `prompts/E2/` |
| `purge_downstream(stage, episode_id=None)` | 该 stage 类型扫所有集（向后兼容） |

---

## 9. 错误处理 + 边界

### 9.1 大纲生成失败回滚

`/script/outline` 期间或 done validate 失败：
- atomic write 保证不写半成品 `剧本.json`
- error event 含 `details.raw_output_path`
- UI 弹「JSON 修复失败」对话框（同 storyboard 模式）

### 9.2 单集生成失败

`/script/episode` 失败：
- 不落盘
- error event 携 `episode_id`
- UI 大纲表该行尾显示红 ✗
- 「一键全集」遇错立即停止后续集
- 用户单点 [生成此集] 重试

### 9.3 大纲改了但部分集已生成

- 大纲改集 entry 后，该集行尾显示「⚠ 大纲已变」hint
- 重生该集时 `purge_downstream("script_episode", episode_id=...)` 级联清下游
- 状态点重置 → 用户重新生成

### 9.4 切集 dirty 拦截

`_EpisodeSelector` 内部缓存 `_last_selected_id`，切换前调宿主 `try_release()`，拒绝则还原。

### 9.5 集 ID 越界 / 不一致

- agent 收到 `episode_id="E99"` 但 `剧本.json` 只 3 集 → 400 `EPISODE_NOT_FOUND`
- UI 弹 warning + 集选择器还原
- 格式不匹配 `^E\d+$` → 同样 400

### 9.6 worker dict key 升级

`_BaseStagePage._workers: dict[tuple[Path, str], StreamWorker]`，key 是 `(project_dir, episode_id)`。
- `is_streaming(project_dir, episode_id=None)` 加可选参数：不传时返「该项目任一集 streaming」
- 多集并发（E1 大纲 + E2 单集同时）互不冲突

### 9.7 索引缺失但 md 散落

`剧本_E*.md` 存在但 `剧本.json` 丢 → UI 弹「索引文件缺失，是否从已有 md 重建？」
- [是] → 扫所有 `剧本_E*.md`，从第一行提标题 + 空概要，重建 `剧本.json`
- [否] → 禁用所有阶段操作

### 9.8 N=1 单集模式回退

- N=1 时大纲表 1 行，集数 spin 改 N 需走「重新规划」按钮：`purge_downstream("script_outline")` + 重新大纲
- 防止 N=2 用户点回 1 导致 E2 文件孤立

---

## 10. 测试矩阵

### 10.1 后端新增

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_script_index_schema.py` | ~6 | `EpisodeEntry.id` 校验、`ScriptIndex.episodes` 长度、缺字段、序列化 |
| `test_route_script_outline.py` | ~5 | N=1 快路径、N=3 大纲、缺创意、JSON_REPAIR_FAILED、purge_downstream |
| `test_route_script_episode.py` | ~5 | 单集生成、EPISODE_NOT_FOUND、缺索引、purge、LLM 异常 |
| `test_route_storyboard_episode.py`（改） | ~4 | episode_id 必填、读 E{id}.md 写 E{id}.json、缺上游、并发 |
| `test_downstream.py`（扩） | ~5 | script_outline 全清、script_episode 单集清、storyboard E{id}、prompts E{id}、不传 episode_id 全集清 |
| `test_paths.py`（扩） | ~6 | script_index_path、script_episode_path、旧名兜底、storyboard_episode_path、is_valid_episode_id、episode_prompts_dir |

### 10.2 前端新增

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_episode_selector.py`（新） | ~5 | N entry 渲染、状态点、信号、try_release 拦截、回滚 |
| `test_script_page.py`（扩） | ~8 | N=1 按钮文案、N=3 大纲表、单集生成、一键全集、cell dirty、切行加载、推进时设 selected |
| `test_storyboard_page.py`（扩） | ~4 | 集选择器、切集 upstream 检查、dirty 拦截、worker key 升级 |
| `test_prompts_page.py`（扩） | ~3 | 集选择器、tree 路径 prompts/E{id}/、partial 过滤 |
| `test_screenwriter_panel.py`（扩） | ~3 | selected_episode 跨 stage、集级别并发、旧项目迁移对话框 |

### 10.3 集成测试

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_multi_episode_e2e.py`（新） | ~2 | N=1 端到端、N=3 端到端 |

### 10.4 旧测试改造

- `test_route_script.py` 6 用例 → 拆为 outline + episode
- `test_storyboard_page.py` 9 现 → 12 fixture 改用 `剧本_E1.md` + `剧本.json`
- `test_prompts_page.py` 6 现 → 类似
- `test_e2e_smoke.py` → 升级多集流程

### 10.5 预期测试数

| 区块 | 净新增 |
|---|---|
| 后端 schema/route/downstream/paths | +25 |
| 前端 page/selector/panel | +13 |
| 集成 | +1 |
| **合计净新增** | **+39** |

预期总数 **194 → ~233**。

---

## 11. 验收标准

1. 全套件 `pytest tests/test_ui/screenwriter/ tests/test_screenwriter_agent/` 全绿
2. 应用启动 → 创建新项目 → 创意阶段填 context 选定候选
3. 推进到剧本 → N=1 单击「生成剧本」流式吐字，done 后大纲表 1 行 + 编辑器加载 `剧本_E1.md`
4. 推进到分镜 → 集选择器默认 E1 → 「生成分镜」产 `分镜_E1.json`
5. 推进到提示词 → 集选择器默认 E1 → 「生成提示词」产 `prompts/E1/角色参考图/*` + `prompts/E1/N宫格/S*`
6. 回剧本阶段 → 集数 spin 改 3 → 「重新规划」清下游 → 「生成大纲」产 3 集索引
7. 单点 E2 行 [生成此集] 流式生成 `剧本_E2.md`
8. 切到分镜 → 集选择器切 E2 → 「生成分镜」产 `分镜_E2.json`
9. 任务栏「分镜」列状态点显示 `2/3`（E1+E2 已生成、E3 未生成）
10. 旧 v1 项目（`剧本.md` 无 `剧本.json`）打开 → 弹迁移对话框 → 选「是」自动迁移到 `剧本.json` + `剧本_E1.md`

---

## 12. 与 Sub-spec #2/#3/#4 关系

| Sub-spec | 内容 | 依赖 #1 何处 |
|---|---|---|
| #2 分镜图提示词（SeedDream） | 重构当前提示词 stage：每集独立 + 9/4/single grid + 角色/场景拆分 | 集选择器 + `prompts/E{id}/` 目录结构 |
| #3 视频提示词（LTX 2.3） | 新 stage：global + 各镜头 local + 时间 | 集选择器 + 新 `prompts/E{id}/视频/` 子目录 |
| #4 配音配乐提示词 | 新 stage：音色设计 + 各分镜配音 + 音效 | 集选择器 + 新 `prompts/E{id}/配音/` 子目录 |

Sub-spec #2/#3/#4 各自独立 brainstorm/spec/plan，但都建立在 #1 集选择器与目录约定上。

---

## 13. 文件清单

### 新建

- `screenwriter_agent/models/script_index_schema.py` — pydantic 模型
- `screenwriter_agent/templates/script_outline.md` — 模板
- `screenwriter_agent/templates/script_episode.md` — 模板
- `screenwriter_agent/routes/script_outline.py` — 新路由
- `screenwriter_agent/routes/script_episode.py` — 新路由
- `drama_shot_master/ui/widgets/screenwriter/_episode_selector.py` — 共享集选择器
- `tests/test_screenwriter_agent/test_script_index_schema.py`
- `tests/test_screenwriter_agent/test_route_script_outline.py`
- `tests/test_screenwriter_agent/test_route_script_episode.py`
- `tests/test_ui/screenwriter/test_episode_selector.py`
- `tests/test_multi_episode_e2e.py`

### 修改

- `screenwriter_agent/server.py` — 注册新路由 / 删除旧 `/script`
- `screenwriter_agent/models/requests.py` — `StoryboardReq` / `PromptsReq` 加 `episode_id` 字段
- `screenwriter_agent/routes/storyboard.py` — 按 episode_id 读写
- `screenwriter_agent/routes/prompts.py` — 按 episode_id 读写
- `screenwriter_agent/core/paths.py` — 加 `script_*` `storyboard_episode_*` helper
- `screenwriter_agent/core/downstream.py` — `purge_downstream` 加 `episode_id` 参数
- `drama_shot_master/ui/widgets/screenwriter/_paths.py` — 镜像 helper
- `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py` — worker dict key 改 `(Path, str)`
- `drama_shot_master/ui/widgets/screenwriter/script_page.py` — 大改：大纲表 + 当前集编辑器
- `drama_shot_master/ui/widgets/screenwriter/storyboard_page.py` — 加集选择器
- `drama_shot_master/ui/widgets/screenwriter/prompts_page.py` — 加集选择器 + 路径走 E{id}
- `drama_shot_master/ui/widgets/screenwriter/_product_tree.py` — `build_from_sb` 加 episode_id
- `drama_shot_master/ui/widgets/screenwriter/task_manager.py` — 状态点 N/M 显示
- 既有测试 ~6 文件适配新文件名 + 新参数

---

## 14. 不在本 spec 范围（明确排除）

- 提示词 stage 的内部重构（拆分角色/场景/grid）→ Sub-spec #2
- 视频提示词 stage 新增 → Sub-spec #3
- 配音配乐提示词 stage 新增 → Sub-spec #4
- 集间依赖关系（如 E2 引用 E1 角色）→ 暂当作集独立，未来可扩
- 集顺序调整 / 删除单集 → 当前仅支持重新规划清空重来
- 跨集角色一致性保证 → 由 LLM 在大纲阶段自然处理，UI 不强制
