# ② 核心：剧本/分镜/视频生成 题材+风格驱动 设计

> 日期：2026-05-31　分支：main
> ②「优化剧本生成」核心：把 screenwriter_agent 各生成阶段从**固定提示词**改为由**题材模板 + 风格圣经**驱动。
> 架构决策：**A 客户端组装（解耦）**——drama_shot_master 读 project.json + load_genre/get_style 组装注入文本，经 request 新字段传给 screenwriter_agent；screenwriter_agent 不反向依赖主包。
> 借鉴：4 个短剧 skill 仓库（研究 `2026-05-31-file-compass-protocol-research.md`）。视频提示词须符合**导演台**结构（全局 + 各分镜 + 时间，LTX 2.3）。

## 现状（screenwriter_agent 5 阶段 prompt 装配）

各阶段 = `load_template(.md) + 拼接 context`，routes 在 `screenwriter_agent/routes/`：
| 阶段 | 模板 | route | 注入现状 |
|---|---|---|---|
| ideate 立意 | `templates/ideate.md` | ideate.py:98 | 已有 `{{genre_tags}}/{{tone_tags}}/{{visual_style}}` 占位，缺题材**规则** |
| script_outline 剧本 | `templates/script_outline.md`(极简) | script_outline.py:71 | 无题材注入 |
| storyboard 分镜 | `templates/storyboard.md` | storyboard.py:64 | globalStyle 自填，缺 style_bible 注入 |
| prompts 出图 | `templates/grid_prompt.md` | prompts.py:146 | globalStyle 从 storyboard 读，缺 ref_fingerprint |
| **video_prompt 导演台** | — | `routes/video_prompt.py` | 派生 video 模型 global_prompt+segments(local_prompt,length_frames)，缺 style/genre/时间公式 |

视频模型已是导演台结构（`video_panel`: `global_prompt` + `segments[local_prompt, length_frames]`，`total_frames=Σlength_frames`，fps）。

## 注入契约（客户端组装，纯函数）

新增 `drama_shot_master/core/gen_context.py`（纯逻辑全单测，主包侧）：

```python
def build_genre_context(genre_dict: dict) -> str:
    """题材模板 → 注入文本（用于 script/storyboard 阶段 prompt）。
    组装 OnlyShot 共用骨架：§0 hard_constraints(⚠️置顶) + identity(一句话/受众/冲突源)
    + rhythm(秒锚点 open_3s/open_30s + beat_density) + satisfaction_weights(爽点类型%)
    + writing_rules(do) + donts(don't)。借鉴 0xsline 爽点矩阵+节奏曲线。"""

def build_style_context(style_dict: dict, *, stage: str) -> str:
    """风格圣经 → 注入文本。复用 style_bible.inject_style_prompt：
    prompt_suffix + 镜头语言(△景别/WIDE-MEDIUM-CLOSE) + [ref_fingerprint 仅 stage='ref']
    + negative_suffix(禁字幕常量)。zhaihao118 三段式 + OnlyShot 指纹分层。"""

def build_video_director_prompts(storyboard: dict, style_dict: dict,
                                 genre_dict: dict, *, fps: int) -> dict:
    """storyboard → 导演台视频提示词结构（LTX 2.3）：
    {
      "global_prompt": "<style_dict.prompt_suffix + 全片基调>",
      "shots": [
        {"shot_id": "S001", "prompt": "<镜头描述 + 风格>",
         "length_frames": <duration*fps>, "duration": <sec>},
        ...
      ],
      "fps": fps, "total_frames": Σ
    }
    时间 = storyboard 各 Shot.duration * fps；可选 Yvonne 时长公式精修
    (台词字数÷8+1s / 动作 2s / 单镜上限 12s)。"""

def guard_prompt(text: str, *, max_chars: int = 1400) -> str:
    """失败模式 guardrail：禁词替换表(sinister→moody/blush→rose tint) + ≤1500字截断
    (即梦/LLM 安全)。OnlyShot 失败模式 1/2。"""
```

## 各阶段注入（A：route 追加 request 传入的 context）

- **请求字段**（`screenwriter_agent/models/requests.py`）：`IdeateContext`/`StoryboardOptions`/`PromptsOptions`/video_prompt req 新增 `genre_context: str = ""` / `style_context: str = ""`（**纯文本**，客户端组装好传入；screenwriter_agent 不 import 主包）。
- **routes 追加**（向后兼容，空则不变）：
  - ideate.py:101-103：system_msg 末尾追加 `genre_context`。
  - script_outline.py:73-80：prompt 追加 `## 题材规则\n{genre_context}`。
  - storyboard.py:67-75：prompt 追加 `## 题材规则\n{genre_context}` + globalStyle 初值用 `style_context`。
  - prompts.py:123-128：grid/character_ref 的 globalStyle 用 `style_context`（render 阶段不含 fingerprint）；角色 ref prompt 用 ref 阶段（含 fingerprint）。
  - video_prompt.py：导演台派生用 `style_context`(global_prompt) + 各 shot local_prompt + 时间。
- **客户端组装**（`drama_shot_master`）：发请求前读 project.json genre+style_id → `load_genre`/`get_style` → `build_genre_context`/`build_style_context` → 填进 request。

## 题材/风格选择器（前端，= R4/R5 UI）

- **题材选择器**（`drama_shot_master/ui/dialogs/genre_picker_dialog.py`）：list_genres() 6 题材卡（短剧/单集短篇/商业广告/vlog/MV/口播剧）+ 主+副≤3 叠加 + 验证配方预设 → 写 `project.json.params.genre`。新建项目时弹 / 概览可改。
- **STYLE BIBLE 选择器**（`drama_shot_master/ui/dialogs/style_bible_dialog.py`，接 OverviewPage.styleBibleEditRequested）：真人/2D/3D × 模板/自定义/AI生成 tab + 风格卡网格（参考 `tests/pic/{真人,2D,3D}风格库.jpg`）→ 写 `project.json.style_bible.ref` + 项目快照 `风格圣经.json`。

## Skills 强项映射（务必体现）

- 题材：OnlyShot 共用骨架(§0-§5) + 0xsline 爽点矩阵/节奏曲线/题材叠加 + Yvonne 正交内层(decompose×polish) + 时长公式。
- 风格：zhaihao118 三段式(全局库→引 id→注入) + OnlyShot 指纹分层(ref 加/render 关) + Yvonne 收尾禁字幕。
- Guardrail：OnlyShot 17 失败模式(爽点先压抑/反转钩≤5-7/隐藏反派≥3铺垫/禁词/≤1500字/@ref 完备闸门) → 注入 guardrail prompt + 导出前 lint。
- 视频：导演台 global+per-shot+timing（LTX 2.3），时间用 storyboard duration×fps + Yvonne 公式。

## 文件清单 / 分波

```
波次1（并行·新建·纯逻辑/widget·不碰 routes/app_shell）：
新增 drama_shot_master/core/gen_context.py (+ test)         # ②a 注入装配纯函数
新增 drama_shot_master/ui/dialogs/genre_picker_dialog.py (+ smoke)   # ②b 题材选择器
新增 drama_shot_master/ui/dialogs/style_bible_dialog.py (+ smoke)    # ②b 风格选择器
新增 drama_shot_master/services/ref_generator.py (+ test)   # 资源库 RefImageGenerator
新增 drama_shot_master/ui/widgets/splash.py (+ smoke)        # ① 加载窗口
波次2（串行·接线）：
改 screenwriter_agent/models/requests.py                    # ②c +genre_context/style_context 字段
改 screenwriter_agent/routes/{ideate,script_outline,storyboard,prompts,video_prompt}.py  # ②c 追加注入
改 drama_shot_master 客户端发请求处                          # ②c 组装 context 填进 request
改 screenwriter_panel/向导 + overview                       # ②d 接选择器→project.json+request
改 app_shell.py                                             # 资源库信号接 RefImageGenerator
改 main.py                                                  # splash 接启动序列
波次3：阶段C-3 worker 灰度（imggen→dub→soundtrack→video）
波次4：R6 guardrail + 导出 lint
```

## Open questions

- 题材模板字段是否够支撑各阶段注入（爽点/节奏/守则已覆盖；是否需补"付费卡点"等短剧专项）。
- 视频导演台时间：纯 storyboard.duration×fps 够，还是默认套 Yvonne 时长公式（台词驱动）。
- 选择器触发时机：新建项目强制选题材/风格，还是可后补（概览编辑）。
