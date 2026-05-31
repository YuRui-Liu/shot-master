# 创作技能库 / Skill Loader 设计说明

> 配套 mockup：`web/skills.html`（蓝紫设计系统 `web/tokens.css`）。
> 调研依据：`docs/explorer/短剧Skill可选模块资源接入建议.md`。

## 1. 目标

把项目从「只做短剧」扩展为**多类型创作平台**：用户在技能库页选择一个创作类型（短剧 / MV / 广告·TVC / 纪录·人文 / 动画 / 口播·解说 / 直播·转播 / 互动·POV / 工具·素材），系统加载该类型对应的**流水线预设**——题材模板、风格圣经倾向、分镜 prompt schema、生视频约束、配音/配乐对齐协议——并把这些以 system-prompt 片段「动态注入」到各阶段 Agent。

机制等价于 Skill 的动态加载：技能 .md 本身是知识库 + 元数据，加载时按其声明的「模块 + 阶段」从 `resources/skills/` 只读知识库挑选片段注入。

## 2. 目录与扫描

```
resources/skills/                # 只读知识库（纯 Markdown / JSON，零外部依赖）
├── creations/                   # 一个创作类型一个 .md（≈33 个，对应 tests/pic/skills.jpg 列表）
│   ├── 01-微缩世界创意短片.md
│   ├── 09-AI短剧一站式生成.md
│   └── ...
├── modules/                     # 可选模块资源（4 仓库调研产物，按阶段分组）
│   ├── shot_prompt/             # 分镜 prompt：8段SOP / 05八字段 / 一致性协议 / 风格注入 …
│   ├── video/                   # 生视频：负向清单 / 时长公式 / 4模式选择器 / ref门控 …
│   ├── mv/                      # MV：9宫格schema / music_sync / 资产圣经 …
│   └── audio/                   # 配音/配乐：台词结构化 / ♪ambient / 节奏曲线 …
└── index.json                   # 扫描缓存（可选，加速冷启动）
```

后端启动时（或首次访问技能库时）扫描 `creations/*.md`，解析出 manifest 列表；扫描 `modules/**/*.md` 建立「模块 ID → 片段路径 + 阶段 + 优先级」表。结果可缓存到 `index.json`，文件 mtime 变化时失效重建。

## 3. Skill .md 解析

每个创作类型 .md 用 **YAML front-matter 元数据 + 正文知识库**。解析只读 front-matter 决定卡片展示与注入；正文按需作为 prompt 注入素材。

```markdown
---
id: ai-short-drama-oneshot
name: AI短剧一站式生成
cat: 短剧                       # 分类筛选用枚举
medium: 短剧                    # 创作媒介
icon: "🎭"
desc: 剧本→分镜→出图→生视频→配音 全链路一站式短剧生产。
output: 全链路工程
modules:                        # 声明要注入的可选模块（引用 modules/ 下的片段 ID）
  - id: shot_prompt.eight_field_sop
    stage: 分镜prompt
    priority: high
  - id: video.ref_gate
    stage: 生视频
    priority: mid
  - id: audio.dialogue_markup
    stage: 配音
    priority: mid
style_hint: cinematic            # 风格圣经倾向（可选）
prompt_template: |               # 该类型专属 prompt 骨架（可选，正文也可承载）
  你是短剧导演……
---

## 方法论正文
（拆解策略 / 镜头语言 / 节奏建议……作为注入素材或参考文档）
```

解析产出的内存结构 `SkillManifest`（与 `web/skills.html` 中 `SKILLS[]` 字段一一对应，便于前端零改造消费）：

```python
@dataclass
class SkillModuleRef:
    id: str            # "shot_prompt.eight_field_sop"
    stage: str         # 分镜prompt / 生视频 / 风格 / 配乐 / 配音 / 成片 / 剧本
    priority: str      # high | mid | low

@dataclass
class SkillManifest:
    id: str
    name: str
    cat: str
    medium: str
    icon: str
    desc: str
    output: str
    modules: list[SkillModuleRef]
    style_hint: str | None
    prompt_template: str | None
    body_md: str       # 正文（注入素材）
    source_path: str
```

容错：front-matter 缺失时回退——`name` 取文件名（去序号前缀/扩展名），`cat`/`medium` 缺省「通用」，`modules` 缺省空列表。解析失败的文件登记到告警列表，不阻断其他技能加载。

## 4. 后端 API（与 split-tool.html 同源 REST，零 Qt）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/skills/list` | 返回全部 `SkillManifest`（前端网格/筛选直接消费）|
| GET | `/skills/detail?id=` | 单技能详情 + 解析后的注入模块清单 |
| GET | `/skills/modules` | 可选模块资源目录（按阶段分组，供资源区展示）|
| POST | `/skills/apply` | body `{skill_id, project_id}`；把该技能预设落到项目配置 |

`/skills/apply` 不直接改写 Agent，而是把选中的 manifest 写入项目级 `project.json.active_skill`（id + 解析快照），各阶段 Agent 生成前读取并按 `stage` 过滤注入。

## 5. 注入流水线

加载一个技能 → 各阶段 Agent 在构造 system-prompt 时：

1. 读 `project.active_skill.modules`，按当前阶段 `stage` 过滤出相关模块。
2. 按 `priority`（high→mid→low）拼接对应 `modules/**` 片段；high 必注入，mid/low 受字符预算约束（分镜 prompt 段沿用调研里 1200–1400 软限 / 1500 硬限）。
3. 叠加 `style_hint`（注入风格圣经倾向）与 `prompt_template`（类型专属骨架）。
4. 注入素材来源唯一为 `resources/skills/`（只读），不引入任何外部依赖、不照搬云端 CLI（即梦/Dreamina/Seedance/Gemini）。

阶段 → 现有模块映射（沿用调研文档结论）：

- **分镜prompt** → 出图/分镜 Agent（`imaging` 阶段 prompt 构造）
- **生视频** → LTX2.3 切片/约束（时长公式、负向清单、4模式选择器、ref 门控）
- **风格** → 风格圣经逐镜注入层
- **配乐** → ACE-Step1.5XL（music_sync 段落 + 情绪曲线 + ♪/ambient）
- **配音** → qwen3-tts / index-tts2（仅消费上游台词结构化标注，方法论自建）
- **智能转场 / 成片** → 归另一终端，本页仅作资源登记，不落地执行

## 6. 前端契约（mockup → 真实页）

`web/skills.html` 即未来真实页：

- `SKILLS[]` 字段 = `/skills/list` 返回结构，上线时把硬编码示例数据换成 `fetch(API+"/skills/list")`。
- `RESOURCES[]` = `/skills/modules` 按阶段分组结果。
- 「加载/应用」按钮 → `POST /skills/apply`，成功后由宿主（启动器 / 项目面板）切到对应创作工作区。
- 健康检查、`?api=` 参数、设计令牌渲染与 `split-tool.html` 完全一致（同一 QWebEngine 宿主）。

## 7. 扩展性

- 新增创作类型 = 往 `creations/` 丢一个带 front-matter 的 .md，无需改代码（扫描即生效）。
- 新增可选模块 = 往 `modules/<stage>/` 丢片段并在技能 manifest 里引用其 ID。
- 分类枚举（`CATS`）与阶段枚举集中维护，前后端共享同一份常量，避免漂移。
