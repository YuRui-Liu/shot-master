# 文件罗盘协议 + 题材模板 + 风格圣经：本项目设计建议（研究综合）

> 日期：2026-05-31　来源：4 个短剧 skill 仓库研究（0xsline/short-drama、A-cat-with-carrots/OnlyShot、YvonneMovingon/short-drama-skills、zhaihao118/Micro-Drama-Skills）综合。
> 落点：PySide6 桌面「糯米AI分镜影视创作台」，已有产物约定（`project_dir` 下 `创意.json` / `剧本.json` / `剧本_E1.md` / `分镜_E1.json` / `prompts/E1/`，集 ID `E1,E2…`）。**升级而非推倒**现有约定。
> 关联：post-3c/3d backlog 第 ②③ 项。是 ③ 项目级重构的地基。

---

## 1. 跨仓库共性与差异

四仓都把「隐性创作经验」编码为「可按需加载的结构化文档 + manifest 驱动的状态机 + 落盘产物」，在 5 维度各有侧重。

### 1.1 题材模板（genre）
| 仓库 | 组织法 | 字段 schema | 值得抄 |
|---|---|---|---|
| 0xsline | 13 类独立条目 | 一句话/受众/爽点/设定/关键要素(含人物弧线) | **5 字段统一 schema** + **题材叠加(≤3 类,主定基调副差异+验证配方)** |
| OnlyShot | 6 流派,**单文件共用骨架** | §0硬约束/§1特征/§2节奏(秒锚点+爆点密度)/§3代表作/§4守则/§5不要做 | **共用结构骨架**便于选型;**秒级节奏**;**§0硬约束放最前** |
| Yvonne | **正交切分**:拆解策略×润色风格,不按内容题材 | — | **内层两 slot 独立替换**(拆解逻辑×成片风格) |
| zhaihao118 | **不为每题材建目录**:`project_type` 字段+ID前缀+分片单位切换 | metadata.json `project_type`/`mv_type` | **同一目录骨架承载多题材**,只参数化分片/时长/节奏源 |

**结论**：组织法抄 zhaihao118（统一目录+`genre`字段+参数化），字段 schema 抄 OnlyShot（共用骨架+秒级节奏+§0/§5），叠加规则抄 0xsline，内层正交化抄 Yvonne。

### 1.2 风格圣经（style bible）
| 仓库 | 机制 | 关键洞见 |
|---|---|---|
| 0xsline | 拆「调性+节奏+镜头语言」多横切文档,按阶段加载、自检回灌 | 风格=多分片组合 |
| OnlyShot | 拆三本角色/场景/道具圣经,**圣经内嵌出图 prompt**;ref 稳定名 `@周翠英_ref.png` | **指纹仅 ref 阶段加,出片 `--no-fingerprint`**;**ref 不纯下游救不回** |
| Yvonne | 风格=可切换润色档+参考图锚定+统一收尾约束句 | 风格即一条可替换 prompt+参考图锁一致性 |
| zhaihao118 | **三段式**:全局库 `visual_styles.json`+项目引 `style_id`+渲染 suffix 注入;支持双风格 | **全局定义一次、项目引 ID、渲染注入**;摄影参数化 |

**结论**：主结构抄 zhaihao118 三段式；分层打光抄 OnlyShot；收尾护栏抄 Yvonne。

### 1.3 流水线
共性：**低成本可迭代区（剧本/圣经/ref图）与高成本按集解锁区（出片）分离**。本项目侧栏 4 阶段（⓪剧本→①素材→②分镜→③出片）天然对齐：⓪①② 设可反复迭代区，③ 按集/片段解锁，manifest 标 `episodes_video_done[]` 增量出片。抄 OnlyShot 成本分阶段 + 资源完备性闸门。

### 1.4 文件协议——**三层 manifest（全研究最可直接抄）**
1. **全局注册表** `index.json`：`next_id` 自增、缺失自愈、多项目索引。
2. **项目清单** `project.json`：`status` 三态机 + `params` + `next_action` + `dependencies` + `archive[]`。
3. **资源索引** `ref_index.json`：`name→落盘文件` + `source/status`，断点跳过。
本项目已有平铺产物，缺的正是这三层。OnlyShot 的 manifest **不只记状态、还驱动 `next_action` 与阶段门禁** 是关键升级点。

### 1.5 prompt 分层
四仓一致：**规则骨架(常量)+结构化字段(变量)+风格 slot(可换)+护栏收尾句(常量)**。分层抄 zhaihao118 三层（数据层→风格注入层→任务层），字段抄 Yvonne 8 字段，工程护栏（禁词表/限长/exclusion）抄 OnlyShot。

---

## 2. 本项目「文件罗盘协议」草案

### 2.1 原则
1. **三层 manifest**：`<root>/index.json` → `<project>/project.json` → `<project>/{characters,scenes,props}/ref_index.json`。
2. **兼容现有命名**：保留 `创意.json`/`剧本.json`/`剧本_E1.md`/`分镜_E1.json`/`prompts/E1/`、集 ID `E1…`。`project.json` 是**新增总线**，不改既有文件名。
3. **manifest 是单一事实源**：侧栏 4 阶段进度/上游 banner/断点续作全读 `project.json`，UI 不再各自扫目录猜状态。
4. **风格圣经引用而非内联**：`project.json` 只存 `style_id`，全局库定义实体。

### 2.2 全局注册表 `<projects_root>/index.json`
```json
{
  "schema_version": 1, "last_updated": "2026-05-31T10:00:00+08:00", "next_id": "P-007",
  "projects": [
    { "project_id": "P-006", "project_name": "替嫁新娘的逆袭", "dir": "P-006_tijia-xinniang/",
      "genre": "短剧", "status": "media_ready", "episode_count": 12,
      "completed_episodes": ["E1","E2"], "cover": "P-006_tijia-xinniang/cover.png",
      "created_at": "...", "last_modified": "..." }
  ]
}
```
> 缺失自愈：不存在则以 `{"schema_version":1,"next_id":"P-001","projects":[]}` 初始化。**禁硬编码 ID**，新建前必读注册表自增。WelcomePage 的 ProjectCard 直接渲染 `projects[]`。

### 2.3 项目清单 `<project>/project.json`（核心，6 组字段）
```json
{
  "schema_version": 1, "project_id": "P-006", "project_name": "替嫁新娘的逆袭", "app_version": "0.7.0",
  "genre": "短剧",
  "params": {
    "split_unit": "episode", "episode_count": 12, "duration_per_unit_sec": 60,
    "grids_per_unit": 9, "aspect_ratio": "9:16", "fps": 24, "language": "zh-CN",
    "rhythm_driver": "plot", "audience": "女频25-40", "tone_tags": ["爽燃","甜虐"], "platform": ["红果","抖音"]
  },
  "style_bible": { "ref": "real/cinematic-warm-v1", "category": "real", "source": "template",
    "mode": "single", "overrides": { "color_palette": ["#2B1A12","#C9A26B"] } },
  "status": "media_ready",
  "pipeline": {
    "screenwriter": { "state": "completed", "next_action": "进入 ① 素材准备" },
    "assets": { "state": "in_progress" }, "storyboard": { "state": "pending" }, "production": { "state": "pending" }
  },
  "artifacts": {
    "idea": "创意.json", "script_index": "剧本.json", "style_bible": "风格圣经.json",
    "characters": "characters/ref_index.json", "scenes": "scenes/ref_index.json",
    "props": "props/ref_index.json", "soundtrack": "soundtrack/soundtrack.json"
  },
  "episodes": {
    "E1": { "title": "替嫁", "script": "剧本_E1.md", "storyboard": "分镜_E1.json",
      "image_prompts": "prompts/E1/", "video_prompts": "video_prompts/E1/", "audio_prompts": "audio_prompts/E1/",
      "shots_done": ["S001","S002"], "video_done": false, "markers": { "🔥": ["S004"], "💰": [] } }
  },
  "soundtrack": { "scope": "project", "tracks": "soundtrack/soundtrack.json", "applies_to": "all" },
  "dependencies": {
    "分镜_E1.json": ["剧本_E1.md","风格圣经.json"],
    "prompts/E1/": ["分镜_E1.json","characters/ref_index.json"]
  },
  "revision_count": 3,
  "archive": [ { "version": "v1.0", "date": "2026-05-22", "dir": "归档/v1.0_2026-05-22/" } ],
  "created_at": "...", "last_modified": "..."
}
```
**关键说明**
- `status` 三态（zhaihao118）：`scripted|media_ready|tasks_ready` 粗粒度门禁；`pipeline.*.state`（`pending|in_progress|completed`）细粒度对应侧栏 4 阶段。粗驱动闸门、细驱动进度条。
- `next_action`（OnlyShot）：每阶段给「下一步建议」，驱动 WelcomePage/上游 banner 引导文案。
- **per-shot prompts 是路径索引非内联**：`prompts/E1/` 是目录，`shots_done[]` 记进度，单镜内容留 `分镜_E1.json` 的 storyboard 数组（避免 manifest 膨胀，见 §6.3）。
- `markers`（0xsline）：🔥关键转折/💰付费卡点，给分镜板做配额校验。
- `dependencies`（OnlyShot）：文件依赖图，上游变更下游标 stale。

### 2.4 标准目录树（6 题材共用骨架）
```
<projects_root>/
├─ index.json                          # 全局注册表
└─ P-006_tijia-xinniang/               # {ID}_{拼音slug}
   ├─ project.json                     # 项目清单+状态机（新增总线）
   ├─ cover.png
   ├─ 创意.json / 剧本.json / 剧本_E1.md…  # ⓪ 立项+逐集剧本（已存在）
   ├─ 风格圣经.json                      # 项目级风格圣经快照（引全局库+overrides）
   ├─ characters/ (character_bible.md + ref_index.json + 女主_ref.png …)
   ├─ scenes/     (scene_bible.md + ref_index.json + scene_01_ref.png)
   ├─ props/      (prop_bible.md  + ref_index.json + prop_01_ref.png)
   ├─ assets/                          # 用户导入素材
   ├─ 分镜_E1.json… / prompts/E1/… / video_prompts/E1/… / audio_prompts/E1/…  # 已存在
   ├─ shots/E1/   (shot001.png …)      # ② 分镜底图/选帧
   ├─ clips/E1/   (段001.mp4 …)        # ③ 视频碎片
   ├─ soundtrack/ (soundtrack.json + stems/)   # 配乐项目级单例
   ├─ exports/    (成片 + video_index.json)
   └─ 归档/v1.0_2026-05-22/            # 大改版本快照
```
> **分片单位参数化** `split_unit ∈ {episode,segment,shot,take}`：短剧/单集短篇用 `episode`(E1…)，MV 用 `segment`(SEG01…)，广告/口播用 `shot`。骨架不变，仅子键+ID前缀随 `params.split_unit` 切换。三位补零 `shot001`，引用统一 `@女主_ref.png`。

---

## 3. 题材模板建议

不为 6 题材各建目录树（zhaihao118 教训）。建一个模板目录，每题材一个 `template.{yaml|md}` + `example/`，入库门槛：真实跑通、无未填占位符（Yvonne）。
```
templates/genres/
├─ index.json
├─ short-drama/  single-episode/  commercial/  vlog/  mv/  oral-skit/   (各 template.yaml + example/)
```
**共用骨架（每题材填同一 schema）**：
```yaml
genre_id: short-drama
display_name: 短剧
hard_constraints: []                  # §0 仅高风险题材填(⚠️放最前)
identity: { one_liner: 钩子密集爽点驱动竖屏连续剧, audience: 女频25-40, conflict_source: [钱,房,孩子,面子,身份反转] }
rhythm: { open_3s: 强冲突/悬念前置, open_30s: 立人设+第一个钩子, beat_density: 每分钟4个爽/钩点 }
satisfaction_weights: { 打脸: 40, 逆袭: 30, 甜宠: 20, 悬念: 10 }
writing_rules: [...]                   # §4 守则
donts: [...]                           # §5 不要做
params_default: { split_unit: episode, duration_per_unit_sec: 60, rhythm_driver: plot, grids_per_unit: 9 }
inner_slots: { decompose_strategy: emotion|action|narrative, polish_style: neutral|high-energy|slow }  # Yvonne 正交内层
```
**6 题材要点 + 变量化**：
| 题材 | 分片/时长 | 节奏驱动 | 特有变量 | 内层默认 slot |
|---|---|---|---|---|
| **短剧** | episode/60s·9grid | plot | 爽点权重、🔥/💰配额、付费卡点集 | emotion/narrative+high-energy |
| **单集短篇** | episode/90-180s | plot | 三幕浓缩、单反转、无付费卡点 | narrative+neutral |
| **商业广告** | shot/15-60s | sell-point | 品牌色板、CTA、产品镜头占比、卖点序列 | action+high-energy |
| **vlog** | shot/自由 | narration | 第一人称、B-roll清单、地点时间轴、配乐情绪 | narrative+slow |
| **MV** | segment/按歌长切 | music-beat | `mv_type`、`lyrics_at_grid`、双风格 transition | mixed+按段切 |
| **口播剧** | shot/按稿长 | script | 逐句对白只读、机位固定、字幕规范 | dialogue+neutral |
> `decompose_strategy` 与 `polish_style` 是两个可独立替换 slot（Yvonne 正交化），避免组合爆炸。题材叠加（0xsline）：选主+副(≤3)，主定 `params`、副只覆盖 `satisfaction_weights`，附验证配方做下拉预设。

---

## 4. 风格圣经机制建议（三段式 + 分层打光 + 收尾护栏）

### 4.1 全局风格库 `<app_config>/visual_styles.json`（按 真人/2D/3D 三类）
```json
{ "schema_version": 1, "default_style_id": "real/cinematic-warm-v1",
  "styles": [ {
    "style_id": "real/cinematic-warm-v1", "category": "real", "name_cn": "电影感暖调", "source": "template",
    "photography": { "camera": "Panavision Sphero 65", "film_stock": "Vision3 500T 5219", "focal_length": "35mm", "aperture": "f/2.0" },
    "prompt_suffix": "cinematic, warm tungsten grade, shallow depth of field, film grain",
    "ref_fingerprint": "neutral studio flat lighting, even key",
    "negative_suffix": "no subtitles, no watermark, no split frame" } ] }
```
> 三类对应不同 STYLE 段模板：`real`(摄影参数)、`2D`(cell-shaded/line-weight/palette)、`3D`(render-engine/PBR/lighting-rig)。

### 4.2 三来源
- **template**：内置精选档（随安装分发），只读，可「另存为自定义」派生。
- **custom**：用户在 STYLE BIBLE 卡手填/调参，写用户级 `visual_styles.json`。
- **ai-generated**：LLM 从 题材+tone_tags+参考图 反推一套 `photography`/`prompt_suffix`，落盘标 `source:ai-generated`，要用户审批 checkpoint 后才 `ready`。

### 4.3 项目引用 + 注入分镜 prompt（三层）
```
project.json.style_bible.ref = "real/cinematic-warm-v1"
   │ 解析全局库+overrides → 写项目快照 风格圣经.json（防全局库改动事后污染老项目）
   ▼ 渲染三层拼装：
   ① 数据层  分镜_E1.json 的 grid.ai_image_prompt
   ② 风格注入 base_prompt + ", " + style.prompt_suffix      ← ref 阶段额外 append ref_fingerprint
   ③ 任务层  头部 @女主_ref.png + 常量 exclusion 护栏 + negative_suffix(禁字幕/禁分屏)
```
**关键护栏**
1. **指纹分层**（OnlyShot 失败模式16）：`ref_fingerprint`(neutral/flat) 只在出 ref 图阶段 append；分镜/出片关闭(`--no-fingerprint`)，否则中性平光污染戏剧打光。
2. **ref 上游纯净**：一致性必须在 ref 设计阶段定死，「ref 不纯下游救不回」。出片前 `ref_index.json` 完备性校验，缺图阻断。
3. **双风格**（zhaihao118）：`mode:dual` 时 `style_a/style_b` 段落交替，单 shot 可 `visual_mode` 覆盖，转场标 `transition.type`。
4. **收尾约束句**（Yvonne）：每条出片 prompt 强制「参考上传角色/场景/道具图、不要生成字幕」常量句。

---

## 5. 值得警惕的失败模式

### 5.1 工程类（直接威胁出图/出片管线）
| # | 坑 | 防护 |
|---|---|---|
| 1 | prompt 超长（即梦 ≤1500 字） | imggen 加 `--check-length`，1200-1400 截断 |
| 2 | 内容审核失败 | 禁词替换表：sinister→moody、blush→rose tint |
| 3 | 视觉指纹污染戏剧打光 | 指纹仅 ref 阶段，分镜/出片 `--no-fingerprint` |
| 4 | @ref 不存在就生任务（最大坑） | **资源完备性闸门**：进 ③ 前扫 `ref_index.json`，缺失阻断+给 自动生成/手动补/跳过 |
| 5 | Bash UTF-8/AWK 切中文乱码 | 调 CLI 走 Python subprocess args 列表，不拼 shell；中文用 substring+regex |
| 6 | Python stdout UTF-8 截断 | `sys.stdout.reconfigure(utf-8)`；`python\|\|python3` fallback |
| 7 | 多模态卡住无报错/poll 退出码不可信 | **以文件落盘确认为准**，轮询+列表兜底，请求间 2s 防限流 |
| 8 | 出图缺图做单张兜底污染半成品 | 缺图「跳过整组并告警」 |
| 9 | 长短 prompt 并发策略 | 按长度分流（长串行短并行） |
| 10 | API 失败无级联兜底 | Gemini 带 ref → Imagen 级联降级 |

### 5.2 内容/一致性类（guardrail prompt）
- 爽点必先压抑（压抑越深释放越爽）；反转钩全剧 ≤5-7 次；隐藏反派 ≥3 处前置铺垫；节奏靠**波形(张弛循环)**非堆高潮。
- 一致性：`分镜_EN` 交叉比对前序集人物/剧情，mismatch 标记/回滚（依赖 `dependencies` + `ref_index.json`）。
- 拆镜：无新信息不切镜；静态单镜 ≤6s；非叙事空镜 <20%；相邻 ≤15s 连贯应合并；台词零改动（只读）。
- 时长引擎（Yvonne）：台词 字数÷8+1s（急促÷10/情绪÷5/旁白÷7）；动作 2s/复杂 4s/单镜上限 12s。做自动时长估算+拆镜触发。
- **幂等/断点**：`ref_index.json` 记 status、已存在跳过、区间重跑——资源/分镜/出片都可中断恢复。
> 内容类沉淀为剧本/分镜 agent 的 guardrail prompt；拆镜/时长/占位符未填做**导出前 lint**（违反阻断 export）。

---

## 6. ③ 项目级重构 4 待决问题——倾向建议

**待决1 导航模型** → **阶段流水线(PHASES)为主轴、FUNCS 为阶段内子工具**，由 `project.json.pipeline` 状态机驱动门禁。侧栏一级=4 阶段，二级=阶段内 FUNCS；阶段可达性由 `pipeline.*.state`+`status` 门禁（如 assets 未完成时 ② 分镜置灰可预览）；每阶段顶显 `next_action`。本项目 `nav_config.py` 已把 8 FUNCS 展平进 4 PHASES，方向正确。

**待决2 协议范围** → `project.json` 只做「索引+状态机+参数」总线，**绝不内联大产物**。进 manifest：身份/`genre`/`params`/`style_id` 引用/阶段 state/产物路径/shot-video 进度/markers/依赖/归档。不进：分镜逐镜文本(留 `分镜_EN.json`)、prompt 正文(留 `prompts/EN/`)、风格圣经实体(留快照+全局库)。

**待决3 per-shot 回填** → 单镜 prompt 落 `分镜_EN.json` 的 storyboard 数组(每 grid 一个 `ai_image_prompt`) + 独立 `prompts/EN/shotNNN.txt`；`project.json` 只回填 `episodes.EN.shots_done[]` 进度，不回填正文。理由：正文体积大改动频繁塞 manifest 易冲突；`shots_done[]` 支持幂等续跑；grid→prompt 同源便于一致性校验与「改 storyboard 自动标 prompt stale」。回填路径：分镜生成写 `分镜_EN.json` → 出图前从 grid 抽 prompt 注入风格 → 出图成功把 `shotNNN` 加进 `shots_done[]`。

**待决4 worker 收敛** → 收敛为「单一任务队列 + 统一 Task 描述符 + manifest 落盘确认」一套 worker，按 `task.type` 分发 provider，放弃每功能一套。`Task = {task_id,type(image|video|dub|music),project_id,episode_id,shot_id,prompt,ref_files[],model_config,status,out_path}`；单一 `TaskRunner`+队列，**完成判定看 `out_path` 文件存在**(幂等跳过)非进程退出码；进度回写 `project.json`+各自 `*_task_store` 明细；限流并发统一调度(长串行短并行、请求间 2s)；配乐项目级单例 `type:music` 不绑 episode、`scope:project`、落 `soundtrack/`，同队列不同 scope。本项目现有多个 `*_task_store.py`(imggen/video/dub/dialogue) 是收敛对象。

---

**落地优先级**：先做 §2 三层 manifest + §6.4 worker 收敛（架构地基）→ 再做 §3 题材模板 + §4 风格圣经三段式（内容资产）→ 最后 §5 失败模式沉淀为 guardrail + 导出 lint。

**现有代码锚点**：
- 产物路径约定：`screenwriter_agent/core/paths.py`
- 集索引 schema：`screenwriter_agent/models/script_index_schema.py`
- 题材/风格请求字段（`genre_tags`/`format`/`visual_style`/`tone_tags`）：`screenwriter_agent/models/requests.py`
- 导航 4 阶段单一事实源：`drama_shot_master/ui/nav_config.py`
