# R2/R3 迁移计划 · 把现有 UI/worker 接到文件罗盘协议

> 日期：2026-05-31　来源：只读结构审计（导航壳/面板/worker/项目目录）综合。
> 基线 spec：`2026-05-31-project-compass-refactor-design.md`（4 倾向已锁定）。
> **关键修正**：`drama_shot_master/core/compass/`（manifest/registry/ref_index/paths/task/**migrate**）**R1 已全部落地（115 passed）**。R2/R3 性质 = **把现有 UI/store 接到既有 compass 核心**（消费方，非生产方），不是造轮子。

## ① 现状总览（真实结构 + 耦合）

**导航壳**（均 Qt-free 单一事实源）
- `nav_config.py`：`FUNCS`(8 功能无门禁元数据) / `PHASES`(4 阶段静态分组) / `ICONS` / `LABELS`。无 `PHASE_GATES`/`next_action`。
- `flow_sidebar.py:20-115`：迭代 PHASES 渲染阶段标题 + checkable 功能按钮；`QButtonGroup(exclusive)`；`_buttons:dict[key→btn]`。**无 key→phase 反向映射、无 setEnabled 门禁，所有按钮恒可交互**。
- `app_shell.py`：8 页预生成进 QStackedWidget；`_on_welcome_new_project` 弹 QFileDialog 选目录直接扫图（**无 allocate_id/无 project.json**）；`_open_dir_path` 仅 `state.load_dir`+`recent_mgr.push`。
- `state.py:16-39 AppState`：`current_dir`/`images`/`output_dir` 批处理中间态。**无 current_project_dir/current_project_id/pipeline_state/next_action**。
- `recent_projects.py`：`~/.drama_shot_master/recent_projects.json`，未接 registry。

**5 大面板**（均走 `TaskWorkspacePage` 双页，**编剧除外**）

| 面板 | 锚点 | 数据模型 | 落点 |
|---|---|---|---|
| ImgGen | `imggen_panel.py:68-287` | `ImgGenTask` ← `ImgGenTaskStore` ← `cfg.imggen_tasks[]` | `resolve_imggen_out_dir(cfg)` |
| Video | `video_panel.py:47-501` | `VideoTask` ← `video_task_store.py` ← `cfg.video_tasks[]` | `resolve_video_output_dir(cfg)` |
| Dub | `dub_panel.py:52-388` | `DubTask` ← `dub_task_store.py` ← `cfg.dub_tasks[]` | `cfg.dub_output_dir/dub` |
| Soundtrack | `soundtrack_panel.py:45-273` | `cfg.soundtrack_tasks[]` **裸 list[dict] 无 Store** | `work_root/soundtrack` |
| Screenwriter | `screenwriter_panel.py:30-175` | `cfg.screenwriter_projects[]` + 6 wizard page 直读写 md/json | 项目目录直写 |

**worker/store**：4 个分离 store（高度重复）+ 配乐裸 dict；`task_aggregator.py` 只读快照；各 panel 独立 `FunctionWorker`(QThread 顺序阻塞)，**完成判定四套**（last_result 字符串/退出码/dict["output"]/流式事件）。⚠️ `core/task_runner.py`（API/SSE 的 async TaskRunner）与 `compass/task.py:TaskRunner` **同名异物**，勿混。

**已落地 compass 核心（R1，迁移依赖）**
- `task.py`：`Task(type∈{image,video,dub,music}/out_path/scope)`，music→`__post_init__` 强制 scope=project 解绑 episode；`TaskRunner.run_task` 看 out_path 文件存在判完成 + 幂等跳过。**与倾向④吻合，可直接被 R3 调用**。
- `manifest.py`：`STAGE_NAMES=(screenwriter,assets,storyboard,production)`（已对齐侧栏 4 阶段）+ `StageState{state,next_action}` + `mark_shot_done/mark_video_done` + load/save。
- `registry.py`：allocate_id/register/list_projects/update_summary。
- `migrate.py`：旧 project_dir→project.json（**R1-T6 已实现**，审计当时未完成误判缺失）。

## ② R2 迁移步骤（导航/UI 项目 scope）排序 + 风险

- **R2-1 `nav_config.PHASE_GATES`**：加 `{phase_key→STAGE_NAMES}` 映射（PHASES 中文 emoji 标题 ↔ 英文 STAGE_NAMES 需显式映射）。纯追加，风险低。
- **R2-2 `AppState` 扩展**：加 `current_project_dir/current_project_id/pipeline_state/next_action` + `load_project(root)`（调 load_manifest 或 migrate）；`load_dir` 不动。⚠️ **批处理 current_dir 与项目 current_project_dir 必须物理分离**，风险中。
- **R2-3 `FlowSidebar` 门禁 API**：加 `_phase_of` 反向映射 + `set_phase_accessible(phase,bool)` + `set_next_action(phase,text)`，默认全可达（向后兼容）。⚠️ 互斥组：禁用选中按钮前先转移选中态；不可达阶段不得 `currentChanged` 切页。风险中。
- **R2-4 `AppShell` 接线**：`_open_dir_path` 有 project.json→load_manifest，无→migrate；`_on_welcome_new_project`→allocate_id+save_manifest+register；新增 `_sync_nav_gates`/`_display_next_actions`。⚠️ `_open_dir_path` 多入口，改签名前穷举调用点。风险中高。
- **R2-5 WelcomePage/ProjectCard 接 registry**：refresh 数据源 `recent_mgr.load()`→`registry.list_projects()`；`push()` 同步 register/update_summary。⚠️ recent_projects.json 与 index.json 双轨过渡防漂移。风险中。
- **R2-6 per-shot 回填**：输入分镜号→`分镜_EN.json.storyboard[idx].ai_image_prompt` 填入 ImgGen prompt；保存写回 grid + `manifest.mark_shot_done`（已有）。⚠️ 严守倾向③：prompt 正文不进 manifest，只记 shots_done[]。风险中。

## ③ R3 迁移步骤（worker 收敛）排序 + 风险

- **R3-1 provider 适配层**（新增无侵入）：给 `compass.TaskRunner` 注入 `{image,video,dub,music}` provider，内部仍调现有 generate/tts_submit/RunningHub，**out_path 必填**。⚠️ `type=image`=出图，文本生成不入此队列。风险中。
- **R3-2 panel `_generate()`→构造 Task**：逐 panel 灰度（imggen 先、video 最后因退出码语义差异最大）。⚠️ **完成判定从 last_result/退出码→out_path 落盘**，须确认 RunningHub 产物确实落到本地 out_path。风险中高。
- **R3-3 music 单例**：`Task(type=music)` scope=project 不绑 episode，out_path=`soundtrack/bgm_final.flac`。⚠️ 当前 TaskRunner 无并发/Semaphore（串行），music max=3 与编剧并行**暂不能由它提供**，保留语义实现延后。风险中。
- **R3-4 进度回写 manifest**：Task 完成→`mark_shot_done`/`mark_video_done`→save；`TaskAggregator.snapshot` 改读 `manifest.episodes[].shots_done[]`。⚠️ 运行态 `_live_status`（in_progress 不落盘）与落盘进度两粒度，只 done 时回写。风险中。
- **R3-5 编剧 dialogue 收敛（缓做）**：`TASK_TYPES` 仅 4 类无 dialogue，流式 vs out_path 判定不契合。**建议 R3 不动编剧**，留 R4+。风险高。

## ④ 渐进迁移顺序（先包装兼容 / 须改签名）

**阶段 A 纯新增零破坏（可立即并行）**：~~migrate.py(R2-0)~~ **已完成** · `nav_config.PHASE_GATES`(R2-1) · R3-1 provider 适配层 · `task.py` 扩 Semaphore 并发（为 music/编剧并行铺路）。
**阶段 B 兼容扩展旧路径保留**：`AppState.load_project`(R2-2,新增方法) · `FlowSidebar` 门禁 API(R2-3,默认全可达) · `recent.push` 双写 registry(R2-5 上) · WelcomePage 数据源切 registry(R2-5 下,缺 project_id 降级)。
**阶段 C 须改签名/语义（破坏性，穷举调用点+回归）**：`_open_dir_path` load_dir→load_project(R2-4) · 新建走 allocate_id+save_manifest(R2-4) · panel `_generate()`→Task+TaskRunner(R3-2,逐 panel 灰度) · `TaskAggregator` 改读 manifest(R3-4) · per-shot 回填+回写(R2-6/R3-4)。
**最后/缓做**：`_activate_task` 硬编码映射→`Task.type` 通用路由 · 编剧 dialogue 收敛(R3-5)。

## 核心风险红线

1. **批处理 vs 项目 scope 物理分离**：`current_dir`(拆/拼/裁) ≠ `current_project_dir`，混用破坏现有批处理。
2. **out_path 幂等判完成是全局语义切换**：所有 provider 必须保证产物真实落到声明 out_path，否则 `run_task` 误判 failed。
3. **互斥 QButtonGroup + 门禁**：禁用选中按钮前转移选中态；不可达阶段不切页。
4. **同名 TaskRunner 二义**：`core/task_runner.py`(API/SSE) ≠ `compass/task.py:TaskRunner`(收敛)，勿误改 batch.py。
5. **R1 已落地不要重写**：compass.Task/manifest/registry 已符合 spec，R2/R3 是消费方。
