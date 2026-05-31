# 实施计划 — 项目级重构 · 文件罗盘协议（②③）

> Spec：`docs/superpowers/specs/2026-05-31-project-compass-refactor-design.md`
> 研究：`docs/superpowers/specs/2026-05-31-file-compass-protocol-research.md`
> 方法：TDD。**整体排在 #3d 之后**；R1 基本 greenfield 可先行（与 3d 无文件冲突）。

## 分期总览

```
R1 协议地基(core/compass 纯逻辑) ── 可先行,greenfield
   └─▶ R2 导航/UI 项目级重构 ──┐
   └─▶ R3 worker 收敛 ────────┤(R2/R3 改既有 UI/worker,需 3d 后 + 结构审计)
R4 题材模板 ──┐                │
R5 风格圣经 ──┴── 挂在 R1 协议上,内容资产,可与 R2/R3 并行
R6 guardrail + 导出 lint ── 收尾,依赖 R3(管线)+R4/R5(资产)
```

---

## R1 — 文件罗盘协议地基（greenfield 纯逻辑，可先行）

新增包 `drama_shot_master/core/compass/` + `tests/test_core/compass/`。全程 TDD，纯逻辑无 Qt。

### R1-T1 manifest.py（ProjectManifest）
- RED：load/save round-trip；`from_dict` 缺字段（status/params/pipeline）→默认值迁移；`pipeline` state 读写；`episodes["E1"].shots_done` 增量幂等（重复 add 同 shot 不重复）；坏 JSON→空/默认不崩。
- GREEN：`ProjectManifest` dataclass（schema_version/project_id/genre/params/style_bible/status/pipeline/artifacts/episodes/dependencies/archive/时间戳）+ 访问器（`stage_state(name)`/`set_stage`/`mark_shot_done(ep,shot)`/`mark_video_done(ep)`）+ `load_manifest/save_manifest`。
- 验证：`pytest tests/test_core/compass/test_manifest.py -q`。

### R1-T2 registry.py（ProjectRegistry）
- RED：缺失自愈初始化 `{schema_version:1,next_id:"P-001",projects:[]}`；`allocate_id()` 自增 P-001→P-002；register/list/update_summary（status/completed_episodes/cover）；坏文件→自愈。
- GREEN：`ProjectRegistry`（load/save index.json + allocate_id + register + list_projects + update_summary）。
- 验证：`pytest tests/test_core/compass/test_registry.py -q`。

### R1-T3 ref_index.py（RefIndex）
- RED：name→path 映射 round-trip；`add(name,path,source,status)`；`completeness_check()` 返回缺失（status!=ready 或文件不存在）列表。
- GREEN：`RefIndex`（load/save + add/get + completeness_check）。
- 验证：`pytest tests/test_core/compass/test_ref_index.py -q`。

### R1-T4 paths.py（布局 + split_unit 感知）
- RED：项目根/各产物路径拼装（兼容 `创意.json`/`剧本_E1.md`/`分镜_E1.json`/`prompts/E1/`）；`split_unit` 切 episode/segment/shot 时 ID 前缀与子目录正确；三位补零 `shot001`。
- GREEN：路径常量 + 拼装函数，复用/包装 `screenwriter_agent/core/paths.py` 不重复定义。
- 验证：`pytest tests/test_core/compass/test_paths.py -q`。

### R1-T5 task.py（统一 Task + TaskRunner）
- RED：Task round-trip；TaskRunner 按 `type(image|video|dub|music)` 路由（mock provider）；`out_path` 已存在→跳过（幂等返回 done 不重跑）；`type:music` scope=project 不绑 episode；完成判定看文件存在非退出码。
- GREEN：`Task` dataclass + `TaskQueue` + `TaskRunner`（submit/route_by_type/file-confirm completion）。provider 注入便于测。
- 验证：`pytest tests/test_core/compass/test_task.py -q`。

### R1-T6 migrate.py（现有项目 → project.json）
- RED：构造一个无 project.json 的临时 project_dir（含 创意.json/剧本.json/剧本_E1.md/分镜_E1.json/prompts/E1/）→ `migrate_project_dir()` 生成 project.json，正确推断 `pipeline`（剧本 completed、分镜 in_progress…）/`episodes`/`artifacts`；已有 project.json→不覆盖（幂等）。
- GREEN：扫描既有产物推断状态，生成 manifest + 登记进 registry。
- 验证：`pytest tests/test_core/compass/test_migrate.py -q`。

> R1 收尾：`pytest tests/test_core/compass -q` 全绿。提交 `feat(core): 文件罗盘协议地基 manifest/registry/ref_index/task/migrate`。

---

## R2 — 导航/UI 项目级重构（依赖 R1 + 3d + 结构审计）

> 前置：先做一次现有 UI 结构审计（`drama_shot_master/ui/` panels/pages/app_shell/nav_config 现状 → 迁移粒度）。建议用只读 Explore 工作流。

- R2-T1 `nav_config.py` 接 manifest：阶段可达性由 `pipeline.*.state`+`status` 门禁（未达置灰可预览）。
- R2-T2 项目级 scope：app_shell/各 panel 从「全局功能」改为「读 active project manifest」；切项目刷新。
- R2-T3 概览页（参考 `项目面板.jpg`）：4 阶段卡（进度=manifest）+ 全片 STYLE BIBLE 卡 + 每阶段 `next_action` banner。
- R2-T4 WelcomePage 接 registry：ProjectCard 列表渲染 `index.json.projects[]`；新建走 `allocate_id`+`migrate`。
- R2-T5 per-shot 回填 UI：视频生成输入分镜号 → 按键从 `分镜_EN.json` grid 取 `ai_image_prompt` 回填文本框（待决3）。
- 测试：nav 门禁 smoke、项目切换 scope smoke、回填逻辑单测。

## R3 — worker 收敛（依赖 R1.task + 3d + 结构审计）

- R3-T1 现有 `*_task_store.py`（imggen/video/dub/dialogue）改为统一 `Task` + `TaskRunner` 提交；明细各自存、粗进度回写 `project.json`。
- R3-T2 完成判定统一为 out_path 文件存在（幂等跳过）；限流并发统一调度（长串行短并行、请求间 2s）。
- R3-T3 配乐 `type:music` 项目级单例：禁多面板，落 `soundtrack/`，同队列不同 scope。
- 测试：各 type 路由 smoke、幂等跳过、music 单例。

## R4 — 题材模板（挂 R1，可与 R2/R3 并行）

- R4-T1 `templates/genres/` 6 模板（共用 yaml 骨架 + inner_slots）+ `index.json`。
- R4-T2 loader：加载 + schema 校验 + 占位符未填报错 + 叠加 ≤3 校验。
- R4-T3 题材选择 UI（主+副 ≤3，验证配方下拉）→ 写 `project.json.genre/params`。
- 测试：6 模板加载、校验、叠加规则。

## R5 — 风格圣经三段式（挂 R1，可与 R2/R3 并行）

- R5-T1 全局 `visual_styles.json`（真人/2D/3D × 模板/自定义/AI生成）+ loader。
- R5-T2 注入纯函数：`base_prompt + prompt_suffix` 拼装 + 指纹分层开关（ref 阶段加/出片关）+ 收尾禁字幕常量句。
- R5-T3 STYLE BIBLE 卡 UI（参考 `真人/2D/3D风格库.jpg`）：模板/自定义/AI生成 tab + 风格卡网格 → 写 `project.json.style_bible.ref` + 项目快照 `风格圣经.json`。
- R5-T4 ref 完备性闸门：进③出片前扫 `ref_index` 缺图阻断 + 自动生成/手动补/跳过。
- 测试：注入拼装、指纹开关、完备性闸门。

## R6 — guardrail + 导出 lint（收尾，依赖 R3+R4+R5）

- R6-T1 工程护栏：prompt ≤1500 字 lint、禁词替换表、文件落盘确认轮询、长短并发分流。
- R6-T2 内容 guardrail prompt：注入剧本/分镜 agent（爽点压抑/反转钩限次/拆镜时长规则）。
- R6-T3 导出前 lint：拆镜/时长/占位符未填/缺 ref 阻断 export。

---

## 落地建议

1. **先 R1**（greenfield、可与 3d 并行、是一切地基）。
2. 3d 合并后做**结构审计** → R2/R3（UI/worker，改既有代码）。
3. R4/R5（内容资产）可与 R2/R3 并行。
4. R6 收尾。
每个 R 阶段各自 spec 细化可按需补；本 plan 为总路线 + R1 详细 TDD。
