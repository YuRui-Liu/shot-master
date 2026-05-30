# 视频提示词产物合并为单文件 设计

> 日期：2026-05-30
> 范围：仅编剧 Stage 5「视频提示词」子系统。不动导演台/LTX 出片 pipeline 的 global_prompt（独立子系统），不动配音页 voices/sfx_cues。

## 问题

`screenwriter_agent/routes/video_prompt.py` 把 LLM 的单个输出对象 `{"global_prompt": ..., "shots": [...]}` **拆成两个文件**落盘：
- `video_prompts/E1/global.md`（全局画风，纯文本）
- `video_prompts/E1/shots.json`（镜头数组）

`global_prompt` 本可作为字段与 shots 同放一个 JSON。拆两文件无必要，且引入 `# global_prompt` 头污染、SSE 双事件、加载双读等复杂度。

## 目标

合并为单文件 `video_prompts/E1/shots.json`，内容即 LLM 原始对象：

```json
{
  "global_prompt": "<全局画风提示词>",
  "shots": [
    {"shot_id": "S01_01", "local_prompt": "...", "duration_s": 5.0}
  ]
}
```

不再写 `global.md`。

## 关键后果

`shots.json` 的形状由**裸数组** `[...]` 变为**对象** `{global_prompt, shots:[...]}`。所有读取方按类型分流：
- `dict` → 新格式：global = `data["global_prompt"]`，shots = `data["shots"]`
- `list` → 旧格式：shots = 数组本身，global 回退读 `global.md`（去 `# global_prompt` 头）

## 架构（受影响单元）

### 1. 后端 `screenwriter_agent/routes/video_prompt.py`
- LLM 解析出的 `data`（已是 `{global_prompt, shots}`）整体一次性原子写入 `shots.json`。
- **删除** `global.md` 的写入与对应 SSE partial。
- SSE：发 1 个 `partial`（`{"file": ".../shots.json", "content": <整体 JSON 字符串>}`）+ `done`。

### 2. UI `drama_shot_master/ui/widgets/screenwriter/video_prompt_page.py`
- `_load_from_disk(project_dir, episode_id)`：
  1. 读 `shots.json`。`isinstance(data, dict)` → global=`data.get("global_prompt","")`、shots=`data.get("shots",[])`；否则（list 旧格式）→ shots=data、global=回退读 `global.md`（`_strip_global_header`）。
  2. 填充 `_global_prompt_edit` + `_populate_shots_table`。
  3. shots.json 不存在但 global.md 存在的边角情形：仅显示 global（shots 表空）。
- `_on_sse_event` partial 分支：
  - `fname.endswith("shots.json")` → 解析 content（dict）→ 同时刷新全局框（`data["global_prompt"]`）+ 镜头表（`data["shots"]`）。
  - **删除** `global.md` 分支。
- `start_generation_if_idle`：判定仍以 `shots.json` 存在为准（逻辑不变）。
- 全局面板 label「全局画风提示词（global.md）：」→「全局画风提示词：」。
- `_strip_global_header`：**保留**（旧 global.md 回退路径仍用）。
- episode_selector `file_pattern_for_status="video_prompts/{ep}/shots.json"`：不变（shots.json 仍是产物标记）。

### 3. 不变项
- `_paths.video_prompt_dir_in`：不变。
- `purge_downstream`：删整个 `video_prompts/` 目录，不受文件数影响。
- 导演台/LTX 子系统、配音页：不动。

## 数据流

```
LLM → {global_prompt, shots:[...]}
  → 路由原子写 video_prompts/E1/shots.json（整个对象）
  → SSE partial(shots.json, content=整个对象)
  → UI 解析 dict → 全局框 + 镜头表
```

加载已有项目：
```
读 shots.json
  ├ dict（新）→ 字段取 global + shots
  └ list（旧）→ shots=数组；global 回退读 global.md（去头）
```

## 错误处理
- shots.json 解析失败 → shots 表清空、全局框清空（沿用现有 try/except）。
- 旧 global.md 缺失而 shots.json 是旧 list 格式 → global 显示空（不报错）。

## 测试

### 后端 `tests/test_screenwriter_agent/test_route_video_prompt.py`
- 既有 3 个错误条件测试不变。
- 新增：构造一个走通的写盘单元（或对 `build_video_user_prompt` 之外抽一个 `write_video_output(out_dir, data)` 纯函数）断言：写出的 `shots.json` 是含 `global_prompt` 的 dict，且**不存在** `global.md`。

### UI `tests/test_ui/screenwriter/test_video_prompt_page.py`
- 新格式：写 `shots.json = {"global_prompt":"GP","shots":[{shot_id,duration_s,...}]}` → set_project → 全局框 == "GP"、ID/时长正确。
- 旧格式回退：写旧 `global.md` + 旧 `shots.json=[...]`（裸数组）→ set_project → 全局框 == global.md 内容（去头）、镜头表来自数组。
- 更新现有用例：把写 `global.md`+数组 `shots.json` 的 fixture 迁移到新对象格式（保留至少 1 个旧格式回退用例）。

## 实施顺序（TDD）
1. UI `_load_from_disk` + SSE handler 支持新对象格式 + 旧回退（先写测试）。
2. 后端路由改写单文件（抽 `write_video_output` 便于测试）。
3. 清理 label / 文档串。
4. 全套回归。
