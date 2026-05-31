# 项目级重构 · 文件罗盘协议 + 题材模板 + 风格圣经 设计

> 日期：2026-05-31　分支：main
> 用户已确认 ③ 4 个倾向（导航=阶段流水线为主 / `project.json` 只做索引总线 / per-shot prompt 存分镜 json·manifest 只记进度 / worker 收敛为单队列）。
> 详尽研究与依据：`docs/superpowers/specs/2026-05-31-file-compass-protocol-research.md`（本 spec 是其落地契约，不重复 rationale）。
> 原则：**升级而非推倒**——保留现有 `创意.json`/`剧本.json`/`剧本_E1.md`/`分镜_E1.json`/`prompts/E1/`、集 ID `E1…`；新增「总线」层把它们串起来。

## 已锁定决策（来自用户确认的 4 倾向）

1. **导航 = 阶段流水线为主轴**：侧栏一级 = 4 阶段（⓪剧本→①素材→②分镜→③出片），二级 = 阶段内功能；由 `project.json.pipeline` 状态机驱动可达性门禁 + 每阶段顶显 `next_action`。沿用现有 `nav_config.py`（已把 8 功能展平进 4 阶段）。
2. **`project.json` 只做「索引 + 状态机 + 参数」总线**：绝不内联大产物。进 manifest = 身份/`genre`/`params`/`style_id` 引用/阶段 state/产物路径/shot-video 进度/markers/依赖/归档；不进 = 分镜逐镜文本、prompt 正文、风格圣经实体。
3. **per-shot prompt 存分镜 json**：单镜 prompt 落 `分镜_EN.json` 的 storyboard 数组（每 grid 一个 `ai_image_prompt`）+ `prompts/EN/shotNNN.txt`；`project.json` 只回填 `episodes.EN.shots_done[]` 进度（幂等续跑）。"输入分镜号→回填 local_prompt" 从 grid 取。
4. **worker 收敛为单队列**：统一 `Task{type:image|video|dub|music,...}` 描述符 + 单 `TaskRunner` 按 type 分发；**完成判定看 `out_path` 文件存在**（非进程退出码，幂等跳过）；配乐 `type:music` 项目级单例不绑 episode。

## 三层 manifest 数据契约

数据结构与字段见研究文档 §2.2/§2.3，本 spec 锁定如下：

- **全局注册表** `<projects_root>/index.json`：`schema_version / next_id / projects[]`。缺失自愈初始化 `{"schema_version":1,"next_id":"P-001","projects":[]}`；**禁硬编码 ID**，新建必读注册表自增。
- **项目清单** `<project>/project.json`：6 组字段（元信息 / `genre`+`params` / `style_bible` 引用 / `status`三态+`pipeline`细粒度 / `artifacts`+`episodes`路径索引+进度 / `dependencies`+`archive`）。
- **资源索引** `<project>/{characters,scenes,props}/ref_index.json`：`name→落盘文件 + source/status`，断点跳过。
- **分片单位参数化** `params.split_unit ∈ {episode,segment,shot,take}`：骨架不变，子键 + ID 前缀随其切换。三位补零 `shot001`，引用统一 `@女主_ref.png`。

## 模块分解（新增 `drama_shot_master/core/compass/`）

纯逻辑、无 Qt、全单测的协议核心，与现有 `drama_shot_master/core/video_task_store.py`、`screenwriter_agent/core/paths.py` 平级/协作。

```
drama_shot_master/core/compass/
  manifest.py        # ProjectManifest dataclass + load/save/migrate + 字段访问器（status/pipeline/episodes/artifacts）
  registry.py        # ProjectRegistry：index.json 读写 + next_id 自增 + 缺失自愈 + register/list/update_summary
  ref_index.py       # RefIndex：ref_index.json 读写 + name→path 映射 + completeness_check（缺失列表）
  paths.py           # 项目目录布局常量 + 路径拼装（兼容现有命名，split_unit 感知）
  task.py            # 统一 Task 描述符 + TaskQueue/TaskRunner（type 路由 + out_path 落盘判定 + music 单例 scope）
  migrate.py         # 现有 project_dir（无 project.json）→ 生成 project.json（扫描既有产物推断 pipeline/episodes/artifacts）
```

## 与现有代码的关系（锚点）

- `screenwriter_agent/core/paths.py`：现有产物路径约定——compass/paths.py 复用/包装，不重复定义。
- `screenwriter_agent/models/script_index_schema.py`：集索引 schema——`project.json.episodes` 从它派生，不取代 `剧本.json`。
- `screenwriter_agent/models/requests.py`（`genre_tags`/`format`/`visual_style`/`tone_tags`）——映射进 `project.json.genre`/`params`/`style_bible`。
- `drama_shot_master/ui/nav_config.py`：导航 4 阶段单一事实源——R2 接 manifest pipeline 驱动门禁/next_action。
- 现有 `*_task_store.py`（imggen/video/dub/dialogue）——R3 收敛对象：明细仍各自存，粗粒度进度统一回写 `project.json`，提交/完成判定走统一 TaskRunner。
- `sound_track_agent/`（配乐）——R3 `type:music` 单例，落 `soundtrack/`。

## 内容资产

- **题材模板** `templates/genres/{short-drama,single-episode,commercial,vlog,mv,oral-skit}/template.yaml`：共用骨架（§0硬约束/§1特征/§2节奏秒锚点/§4守则/§5不要做 + `params_default` + `inner_slots{decompose_strategy,polish_style}`）。`index.json` 登记，入库门槛=真实跑通无占位符。题材叠加 ≤3 类（主定 params、副覆盖 satisfaction_weights）。详见研究 §3。
- **风格圣经** 三段式：全局 `<app_config>/visual_styles.json`（真人/2D/3D × 模板/自定义/AI生成）→ `project.json.style_bible.ref=style_id` → 渲染时 `base_prompt + prompt_suffix` 注入。护栏：指纹仅 ref 阶段加（出片 `--no-fingerprint`）、ref 完备性闸门、双风格 `mode:dual`、收尾禁字幕常量句。详见研究 §4。

## 失败模式 → guardrail（详见研究 §5）

工程类沉淀为管线护栏：即梦 prompt ≤1500 字 lint、禁词替换表、`ref_index` 完备性闸门（进③前缺图阻断）、**以文件落盘确认为准**的轮询（非 poll 退出码）、长短 prompt 并发分流。内容类沉淀为剧本/分镜 agent guardrail prompt + 导出前 lint（拆镜/时长/占位符未填阻断 export）。

## 测试策略（纯逻辑优先）

- `manifest`：load/save round-trip；缺 status/字段迁移默认值；`pipeline` state 读写；`episodes.EN.shots_done` 增量幂等；坏 JSON→降级不崩。
- `registry`：缺失自愈初始化；`next_id` 自增（P-001→P-002）；register/list/update_summary；并发写不丢（最后写赢 + 重读）。
- `ref_index`：name→path 映射；completeness_check 返回缺失列表。
- `migrate`：给一个无 project.json 的现有 project_dir（含 创意/剧本/分镜/prompts），生成的 project.json 正确推断 pipeline state/episodes/artifacts。
- `task`：Task round-trip；TaskRunner 按 type 路由（mock provider）；out_path 已存在→跳过（幂等）；music task scope=project 不绑 episode。
- 题材模板 loader：6 模板加载 + schema 校验 + 占位符未填报错；叠加 ≤3 校验。
- 风格圣经：全局库加载 + style_id 解析 + prompt_suffix 注入拼装（纯函数）+ 指纹分层开关。
- UI（R2 smoke）：nav 阶段门禁随 pipeline state 置灰/可达；next_action 显示；项目切换 scope。

## 范围与分期（见 plan）

R1 协议地基（manifest/registry/ref_index/paths/migrate）→ R2 导航/UI 项目级重构 → R3 worker 收敛 → R4 题材模板 → R5 风格圣经三段式 → R6 guardrail + 导出 lint。

## 依赖与时机

- **实现排在 #3d 之后**（R2/R3 改 `soundtrack_editor.py`/`nav_config.py`/`*_task_store.py`，与 3d 改动重叠）。
- **R1 协议地基基本 greenfield**（新 `core/compass/` 纯逻辑），与 3d 无文件冲突，可先行。
- R2/R3 实现前需一次**现有 UI/worker 结构审计**（panels/nav/task_store 现状）以定迁移粒度。
