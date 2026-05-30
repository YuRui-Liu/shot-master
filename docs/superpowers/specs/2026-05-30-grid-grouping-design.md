# 分镜图提示词 手动分组 设计

> 日期：2026-05-30
> 范围：仅编剧 Stage 4「分镜图提示词」(PromptsPage) 的宫格分组 + `/prompts` 路由分组逻辑。不动角色参考图、grid_prompt 模板内容、其它阶段。

## 问题

当前 PromptsPage 用单个全局 `grid_combo`（single/4/9）统一套用所有镜头；`/prompts` 路由按固定大小 `shots[i:i+size]` 切块。后果：10 镜在「9」模式下切成 `[S01_1…S01_9]` + `[S01_10]`，尾组 1 镜仍按「9宫格」生成（1 格 + 8 blank）。用户无法：① 为不同组指定不同宫格模式；② 逐组生成（只能一键全生成）。

## 目标

让用户手动定义每组的「镜头范围 + 宫格模式」，逐组或一键生成。

- 例：`S01_1–S01_9` 为九宫格、`S01_10` 为单帧；或单独 `S01_1–S01_4` 为四宫格。
- 允许部分生成（组不必覆盖全部镜头）。
- 逐组「生成」按钮 + 「全部生成」。

## 数据模型

一个**组**：
```json
{"grid_mode": "9" | "4" | "single", "shot_ids": ["S01_1", ..., "S01_9"]}
```
- 组是**有序列表**；第 k 组（1-based）→ 落盘 `prompts/E{id}/N宫格/S{k}.md`。
- `shot_ids` 为该组连续镜头（顺序即 F1, F2, …）。
- 容量：`single`=1，`4`≤4，`9`≤9。

**智能默认**（打开页面 / 切集时）：按 9 切块，每组 `grid_mode` = 容纳其镜头数的最小容量：
- 1 镜 → `single`
- 2–4 镜 → `4`
- 5–9 镜 → `9`

## 架构（受影响单元）

### 1. 新组件 `drama_shot_master/ui/widgets/screenwriter/_grid_group_editor.py`
独立 QWidget，封装分组表格逻辑，可单测。

**纯函数（模块级，无 Qt 依赖，便于单测）：**
```python
def auto_fit_mode(count: int) -> str:
    """按镜头数返回最小容量模式。"""
    if count <= 1: return "single"
    if count <= 4: return "4"
    return "9"

def default_groups(shot_ids: list[str]) -> list[dict]:
    """按 9 切块 + auto_fit_mode 生成默认组列表。"""
    # 每 9 个一组；每组 grid_mode = auto_fit_mode(len(组))

def group_capacity(grid_mode: str) -> int:
    return {"single": 1, "4": 4, "9": 9}.get(grid_mode, 9)

def group_is_valid(group: dict) -> bool:
    """shot_ids 非空且数量 ≤ 容量。"""
```

**`_GridGroupEditor(QWidget)`：**
- 信号：`generateGroup = Signal(int)`（组 1-based 序号）、`generateAll = Signal()`、`groupsChanged = Signal()`。
- `set_shots(shot_ids: list[str])`：存镜头列表 + 用 `default_groups` 建默认组 + 重建表格。
- `groups() -> list[dict]`：返回当前组列表（含 grid_mode + shot_ids）。
- 表格列：`组 | 起始▾ | 结束▾ | 模式▾ | 生成▶ | 状态`。
  - 起始/结束下拉 = 全部 shot_ids；模式下拉 = 单帧/四宫格/九宫格。
  - 改起始/结束/模式 → 重算该组 shot_ids（起止之间连续镜头）→ emit groupsChanged。
  - 行无效（结束<起始 或 数量>容量）→ 状态显示「✗ 超容量」+ 禁用该行生成按钮。
  - 生成▶ → emit generateGroup(行号)。
- 底部：`+ 添加组`（追加一个默认单组）、`全部生成`（emit generateAll）。
- `set_group_status(index, status)`：更新某组状态点（idle/running/done/error）。

### 2. `drama_shot_master/ui/widgets/screenwriter/prompts_page.py`
- 移除 param bar 的 `_grid_combo`（及其 `_rebuild_tree` 连接）。
- 在**左侧面板树的上方**嵌入 `_GridGroupEditor`（`_build_left` 内，树之前 `addWidget`）。
- `set_project` / `_on_episode_changed` 加载分镜后：`_group_editor.set_shots([shot ids from sb])`。
- 连接：
  - `generateAll` → `_on_generate_clicked()`（请求体带全部 groups，不带 only_group_index）。
  - `generateGroup(idx)` → `_on_generate_group(idx)`（请求体带全部 groups + `only_group_index=idx`）。
- 生成请求体 `options` 追加 `groups`（来自 `_group_editor.groups()`）+（逐组时）`only_group_index`。
- 旧 `_grid_combo` 相关：`build_from_sb(grid_mode=...)` 调用点改为不再依赖 grid_combo（树用组数；见下）。

### 3. `drama_shot_master/ui/widgets/screenwriter/_product_tree.py`
- `build_from_sb` 当前按 `grid_mode` 算 `n_groups`。改为接受 `groups: list` 直接按组数渲染 `N宫格/S{k}.md`（k=1..len(groups)）。保留旧签名兼容：若传 `grid_mode` 仍按旧逻辑（向后兼容现有测试）。

### 4. `screenwriter_agent/models/requests.py`
- `PromptsOptions` 追加：
```python
groups: list = Field(default_factory=list)   # [{"grid_mode":..,"shot_ids":[..]}]
only_group_index: int | None = None          # 1-based；仅生成该组
```

### 5. `screenwriter_agent/routes/prompts.py`
- N 宫格生成段：若 `opts["groups"]` 非空 → 走新分组逻辑：
  - 遍历 `enumerate(groups, start=1)`；若 `only_group_index` 非空则只处理 `gi == only_group_index` 的那组。
  - 该组镜头 = 按 `shot_ids` 从 `sb["shots"]` 解析出 shot dict（保序）。
  - 构造该组 `opts` 副本，`grid_mode` = 组的 grid_mode。
  - 调已有 `build_grid_user_prompt(tpl_grid, sb, grp_shots, gi, group_opts)` → 落 `S{gi}.md` + SSE partial。
- 若 `groups` 为空 → **回退**原 `grid_size = {single:1,4:4,9:9}[grid_mode]` 统一切块逻辑（保持现有测试/调用不破）。

## 数据流

```
分镜 sb.shots → _GridGroupEditor.set_shots(ids) → default_groups → 表格
用户改组 → groups()
生成（全部/单组）→ body.options.groups (+ only_group_index)
  → /prompts：按组解析镜头 + 各自 grid_mode → grid_prompt 模板 → N宫格/S{k}.md
  → SSE partial(S{k}.md) → 树状态点 + 组状态点
```

## 错误处理
- 组无效（超容量/空）：UI 标红 + 禁生成；路由侧若收到超容量组，按 `shot_ids` 实际数生成（模板支持 blank），不崩。
- `shot_ids` 含 sb 中不存在的 id：解析时跳过该 id。
- `only_group_index` 越界：不生成任何组（done 返回 0）。

## 测试

### `tests/test_ui/screenwriter/test_grid_group_editor.py`（新）
- `auto_fit_mode`：1→single、4→"4"、5→"9"、9→"9"。
- `default_groups`：10 个 id → 2 组，第1组 9宫格(9镜)、第2组 single(1镜)；4 个 id → 1 组 4宫格。
- `group_is_valid`：超容量 False、正常 True、空 False。
- `_GridGroupEditor`：构造 + `set_shots(10 ids)` → `groups()` 长度 2、模式正确；改某行模式 → groupsChanged 发出；点生成 → generateGroup(行号) 带正确 index；全部生成 → generateAll。

### `tests/test_screenwriter_agent/test_route_prompts.py`（补充）
- groups 分组：body 带 2 组（9 + single）→ 生成 S1.md + S2.md（用 monkeypatch/stub LLM 或仅验证分组解析的纯函数）。
- only_group_index：只生成指定组对应 S{k}.md。
- 无 groups 回退：仅 grid_mode 时仍按原切块（既有测试不变）。
- 抽纯函数 `resolve_group_shots(sb, shot_ids) -> list` 便于单测镜头解析。

### `tests/test_ui/screenwriter/test_prompts_page.py`（补充）
- 加载分镜后 `_group_editor` 有默认组。
- 触发全部生成 → 请求体 options 含 `groups`（非空）。
- 触发单组生成 → 请求体含 `only_group_index`。

## 向后兼容
- 旧请求（只带 `grid_mode`，无 `groups`）→ 路由回退原逻辑。
- `_product_tree.build_from_sb` 保留旧 `grid_mode` 路径。
- 不动 grid_prompt 模板、角色参考、其它阶段。

## 实施顺序（TDD）
1. `_grid_group_editor.py` 纯函数（auto_fit_mode/default_groups/group_capacity/group_is_valid）+ 单测。
2. `_GridGroupEditor` widget（表格/信号/set_shots/groups）+ 单测。
3. 后端 `PromptsOptions` + 路由分组逻辑（抽 `resolve_group_shots`）+ 回退 + 测试。
4. `_product_tree.build_from_sb` 支持 groups。
5. PromptsPage 接入 `_GridGroupEditor`（移除 grid_combo）+ 请求体 + 集成测试。
6. 全套回归。
