# 编剧 Wizard Phase 2 设计 Spec

**日期：** 2026-05-29  
**代号：** `screenwriter_phase2`  
**版本：** v1.0  
**状态：** 已用户审阅通过  

---

## 0. 背景与目标

### 0.1 现状

当前编剧 Wizard 有 4 个阶段：

```
1.创意 → 2.剧本 → 3.分镜 → 4.提示词
```

存在以下问题：
1. **创意→剧本无自动触发**：用户选定创意点[推进]后，到剧本页需手动点「生成剧本」，体验割裂
2. **第 4 阶段「提示词」定位模糊**：现有实现混合了多种输出类型，与下游工具（SeedDream、LTX2.3、TTS）的对接不清晰
3. **缺少视频提示词输出**：LTX2.3 视频生成的 global_prompt + per-shot local_prompt 没有专门阶段
4. **缺少配音配乐提示词**：角色音色设计与分镜配音匹配没有专门阶段

### 0.2 目标

将 Wizard 扩展为 6 个明确阶段，每个阶段对应一个明确的下游工具/产物：

```
1.创意 → 2.剧本 → 3.分镜 → 4.分镜图提示词 → 5.视频提示词 → 6.配音配乐
```

---

## 1. 阶段结构

| 阶段 | 核心产物 | 下游工具 | 改动幅度 |
|------|---------|---------|---------|
| 1. 创意 | `创意.json` | — | 无改动 |
| 2. 剧本 | `剧本.json` + `剧本_E*.md` | — | 小改：推进触发 |
| 3. 分镜 | `分镜_E*.json` | — | 无改动 |
| 4. 分镜图提示词 | `image_prompts_E*.md` | SeedDream/即梦 | **新建** |
| 5. 视频提示词 | `video_prompts_E*.json` + `video_prompts_E*.md` | LTX2.3 | **新建** |
| 6. 配音配乐提示词 | `audio_prompts_E*.md` | TTS/配音软件（工具无关） | **新建** |

---

## 2. 架构改动

### 2.1 wizard_host.py

当前断言 `len(pages) == len(stage_names) == 4`，改为：

```python
# wizard_host.py
assert len(pages) == len(stage_names)   # 去掉固定数字断言
```

`screenwriter_panel.py` 中 `_STAGE_NAMES` 改为 6 个：

```python
_STAGE_NAMES = ["创意", "剧本", "分镜", "分镜图提示词", "视频提示词", "配音配乐"]
```

### 2.2 新增文件

```
drama_shot_master/ui/widgets/screenwriter/
├── image_prompts_page.py    # Stage 4：分镜图提示词
├── video_prompts_page.py    # Stage 5：视频提示词
└── audio_prompts_page.py    # Stage 6：配音配乐提示词

screenwriter_agent/routes/
├── image_prompts.py         # POST /image_prompts（SSE）
├── video_prompts.py         # POST /video_prompts（SSE）
└── audio_prompts.py         # POST /audio_prompts（SSE）

screenwriter_agent/templates/
├── image_prompts.md         # 分镜图提示词生成模板
├── video_prompts.md         # 视频提示词生成模板
└── audio_prompts.md         # 配音配乐提示词生成模板
```

### 2.3 修改文件

| 文件 | 改动 |
|------|------|
| `wizard_host.py` | 去掉 `== 4` 断言 |
| `screenwriter_panel.py` | `_STAGE_NAMES` 改 6 项；`_pages` 加 3 个新页 |
| `ideate_page.py` | `_on_advance_clicked` 通知 ScriptPage 高亮按钮 |
| `script_page.py` | 新增 `highlight_generate_button()` 公开方法 |
| `screenwriter_panel.py` | `_on_stage_advance_requested` 处理 idx=1 时调用高亮 |
| `screenwriter_agent/server.py` | 注册 3 个新路由 |
| `screenwriter_agent/templates/template_loader.py` | `BUILTIN_IDS` 加 3 个新模板 |

---

## 3. Stage 2 剧本：推进触发改造

### 3.1 需求

用户在「1.创意」选定候选后点[推进]，切到「2.剧本」时：
- 按钮「生成剧本」显示为高亮绿色 + 呼吸光晕效果
- 顶部出现来自创意的提示条：`💡 从「{创意标题}」已选定 · 点击上方按钮开始生成`
- **不自动触发生成**（防止用户想先调整参数集数/时长）

### 3.2 实现

**`script_page.py` 新增方法：**

```python
def highlight_generate_button(self, idea_title: str = "") -> None:
    """从创意推进过来时调用，高亮生成按钮 + 显示来源提示。"""
    self._gen_btn.setStyleSheet(
        "QPushButton { background: #2d6a4f; color: #95e5b8; "
        "border: 2px solid #52b788; border-radius: 5px; "
        "padding: 4px 14px; font-weight: bold; }")
    if idea_title:
        self._idea_hint_banner.setText(
            f"💡 从「{idea_title}」已选定 · 点击上方按钮开始生成")
        self._idea_hint_banner.show()
    # 首次生成完成后清除高亮
    self._gen_btn_highlighted = True
```

**`screenwriter_panel.py` `_on_stage_advance_requested` 处理：**

```python
def _on_stage_advance_requested(self, idx: int) -> None:
    if idx == 1:   # 从创意推进到剧本
        idea_title = self._get_selected_idea_title()
        script_page = self._pages[1]
        if hasattr(script_page, "highlight_generate_button"):
            script_page.highlight_generate_button(idea_title)
    self._wizard_host.set_stage(idx)
```

---

## 4. Stage 4 分镜图提示词

### 4.1 布局

```
ImagePromptsPage（QVBoxLayout）
├── 顶 _ParamBar
│   ├── 集数选择 QComboBox（E1/E2/...）
│   ├── 格式选择：[9宫格] [4宫格] [单帧×N]（三个 QPushButton toggles）
│   └── QPushButton「生成提示词」/ 「▣ 中止」
├── 上游 banner（分镜_E*.json 缺失时）
├── 主区 QScrollArea（分组卡片列表）
│   ├── 分组卡片 1（折叠/展开）
│   │   ├── 标题：「第1组 S01-S09（9宫格）」+ [📋 复制此组]
│   │   ├── 角色参考 + 场景摘要（只读）
│   │   └── QPlainTextEdit（生成的 prompt，可编辑）
│   └── 分组卡片 2 ...
└── 底 _ActionBar
    ├── QPushButton「💾 保存」
    └── QPushButton「推进到视频提示词 →」
```

### 4.2 分组逻辑

- **9宫格**：`ceil(N/9)` 组，末组不足 9 张
- **4宫格**：`ceil(N/4)` 组，末组不足 4 张
- **单帧**：N 组，每组 1 张（N 个独立 prompt）
- 用户可在 UI 中**拖拽 shot 到不同分组**（避免末组落单），使用 `QListWidget` dragDrop 模式

### 4.3 Agent 端点 `POST /image_prompts`（SSE）

**Request body：**
```json
{
  "project_dir": "string",
  "episode_id": "E1",
  "grid_mode": "9x9 | 4x4 | single",
  "options": {
    "style_extra": "",
    "include_character_refs": true
  },
  "model": null,
  "creds": null
}
```

**SSE 事件流：**
- `status {"phase": "reading_storyboard"}`
- `partial {"group_index": 0, "shot_ids": ["S01",...], "text": "..."}`（每组完成后推送）
- `done {"saved": "image_prompts_E1.md", "group_count": 2}`
- `error {"code": "...", "message": "..."}`

**生成模板逻辑（`templates/image_prompts.md`）：**
- 读取 `分镜_E{id}.json` 的 characters + shots
- 对每组 shots 合成一段 SeedDream 多格 prompt
- 格式：`Panel 1: {描述}. Panel 2: {描述}...` + 统一角色参考行

### 4.4 产物路径

```
{project_dir}/image_prompts_E1.md
```

文件结构：
```markdown
# 分镜图提示词 E1

## 第1组（9宫格）S01-S09
**角色参考：** 周翠英_ref | 场景：雨夜松林
**提示词：**
Panel 1: 古风水墨，雨夜松林，女子白衣立于树下，远景构图，冷调...
Panel 2: ...

## 第2组（4宫格）S10-S13
...
```

---

## 5. Stage 5 视频提示词

### 5.1 布局

```
VideoPromptsPage（QVBoxLayout）
├── 顶 _ParamBar
│   ├── 集数选择 QComboBox（E1/E2/...）
│   └── QPushButton「生成提示词」/ 「▣ 中止」
├── 上游 banner（分镜_E*.json 缺失时）
├── global_prompt 区块
│   ├── 标题「🌐 global_prompt」+ 右上角 [📋 复制] 按钮
│   └── QPlainTextEdit（可编辑，1-3 行高）
├── shots 表格 QTableWidget
│   列：ID | local_prompt（可编辑）| 时长(s) | ⧉（复制单行）
└── 底 _ActionBar
    ├── QPushButton「💾 .json」
    ├── QPushButton「📄 .md」
    └── QPushButton「推进到配音配乐 →」
```

### 5.2 复制行为

- **global_prompt 复制**：`QApplication.clipboard().setText(text)`
- **单行 ⧉ 复制**：复制 `{shot_id}: {local_prompt}（{duration}s）` 格式文本
- 复制后按钮短暂变为 `✓` 0.5s 后恢复（视觉反馈）

### 5.3 Agent 端点 `POST /video_prompts`（SSE）

**Request body：**
```json
{
  "project_dir": "string",
  "episode_id": "E1",
  "options": {
    "video_model": "LTX-2.3",
    "aspect_ratio": "9:16",
    "fps": 24
  },
  "model": null,
  "creds": null
}
```

**生成逻辑：**
- 读 `分镜_E{id}.json` 的 globalStyle + characters + shots
- `global_prompt`：整合风格、角色外观、摄影风格，面向 LTX2.3 格式
- `local_prompt` per shot：结合 description + stylePrompt + camera 动作，输出 LTX2.3 兼容格式
- `duration`：直接从 `分镜.json.shots[i].duration` 取

**SSE 事件流：**
- `status {"phase": "generating_global"}`
- `delta {"text": "..."}` （global_prompt 流式）
- `status {"phase": "generating_shots"}`
- `partial {"shot_index": 0, "shot_id": "S01", "local_prompt": "...", "duration": 4.5}` （每个镜头完成后推送）
- `done {"saved_json": "...", "saved_md": "..."}`

### 5.4 产物路径

```
{project_dir}/video_prompts_E1.json
{project_dir}/video_prompts_E1.md
```

**JSON 结构：**
```json
{
  "episode_id": "E1",
  "video_model": "LTX-2.3",
  "global_prompt": "...",
  "shots": [
    {"shot_id": "S01", "local_prompt": "...", "duration": 4.5},
    ...
  ]
}
```

---

## 6. Stage 6 配音配乐提示词

### 6.1 布局

```
AudioPromptsPage（QVBoxLayout）
├── 顶 _ParamBar
│   ├── 集数选择 QComboBox
│   └── QPushButton「生成提示词」/ 「▣ 中止」
├── 上游 banner（分镜_E*.json 缺失时）
├── 音色卡区（上方，两列 QGridLayout）
│   ├── 角色卡 1（border-left 蓝/紫色 accent）
│   │   ├── 角色名 + 角色类型
│   │   └── 性别/年龄/语调/情绪范围/声线描述（QTextEdit，可编辑）
│   └── 角色卡 2 ...（每行两列）
├── 分镜配音匹配表（下方，QTableWidget，全宽）
│   列：ID | 角色 | 台词/旁白 | 音效提示 | BGM情绪
└── 底 _ActionBar
    ├── QPushButton「📄 导出 Markdown」
    └── QPushButton「✓ 完成」
```

### 6.2 Agent 端点 `POST /audio_prompts`（SSE）

**Request body：**
```json
{
  "project_dir": "string",
  "episode_id": "E1",
  "options": {
    "include_sfx": true,
    "include_bgm_mood": true
  },
  "model": null,
  "creds": null
}
```

**生成逻辑：**
- 读 `分镜_E{id}.json` + `剧本_E{id}.md`
- **音色卡**：从 characters 列表生成每个角色的音色设计，包含性别/年龄/语调/情绪范围/声线参考描述
- **分镜匹配表**：遍历每个 shot，从剧本 md 中提取台词归属角色，标注情绪，建议 BGM 情绪词 + 音效提示

**SSE 事件流：**
- `status {"phase": "generating_voice_cards"}`
- `partial {"type": "voice_card", "character": "周翠英", "content": "..."}`
- `status {"phase": "generating_shot_table"}`
- `partial {"type": "shot_row", "shot_id": "S01", "character": "旁白", "dialogue": "...", "sfx": "...", "bgm_mood": "..."}`
- `done {"saved": "audio_prompts_E1.md"}`

### 6.3 产物路径

```
{project_dir}/audio_prompts_E1.md
```

**Markdown 结构：**
```markdown
# 配音配乐提示词 E1

## 角色音色卡

### 周翠英（女主）
- 性别：女 · 年龄：25岁
- 语调：清冽柔和，偶带忧郁
- 情绪范围：平静 / 悲切 / 坚定
- 声线描述：...

### 李书生（男主）
...

## 分镜配音配乐匹配表

| ID   | 角色   | 台词 / 旁白             | 音效提示     | BGM 情绪   |
|------|--------|------------------------|-------------|-----------|
| S01  | 旁白OS | 世人皆说守株待兔是愚...   | 雨声·风声    | 悲切·慢板  |
| S02  | 李书生 | 姑娘留步，这雨来得急...   | —           | 温柔·中板  |
...
```

---

## 7. 数据流总图

```
创意.json
  └─→ 剧本_E*.md ──┐
        剧本.json   │
                    ↓
              分镜_E*.json ──────────────────────────────┐
                    │                                    │
                    ├─→ image_prompts_E*.md              │
                    │   （SeedDream 分组 prompt）         │
                    │                                    │
                    ├─→ video_prompts_E*.json+md          │
                    │   （LTX2.3 global+local prompt）    │
                    │                                    │
                    └─→ audio_prompts_E*.md               │
                        （角色音色卡+分镜配音表）←──────────┘
                                                   剧本_E*.md
                                              （补充台词信息）
```

---

## 8. 公共基础设施（三个新 Page 共用）

三个新阶段的 Page 结构高度相同，抽取公共基类 `_BasePromptsPage`（继承自 `_BaseStagePage`）：

```python
class _BasePromptsPage(_BaseStagePage):
    """Stage 4/5/6 共用基类：读分镜JSON → LLM → 显示可编辑文本 → 保存。"""
    
    # 子类实现
    def _endpoint(self) -> str: ...          # "/image_prompts" 等
    def _output_file_name(self, ep: str) -> str: ...  # "image_prompts_E1.md" 等
    def _build_result_widget(self) -> QWidget: ...    # 结果显示区域
    def _populate_result(self, data: dict) -> None: ...  # partial 事件填充
```

这样 `ImagePromptsPage` / `VideoPromptsPage` / `AudioPromptsPage` 只需实现 4 个方法，其余 SSE 处理、上游 banner、集数选择、保存逻辑全部复用。

---

## 9. 上游产物依赖链

| 阶段 | 要求上游 | 缺失时 |
|------|---------|--------|
| 2. 剧本 | `创意.json` 已选定 | banner：请先完成创意阶段 |
| 3. 分镜 | `剧本_E{id}.md` | banner：请先生成该集剧本 |
| 4. 分镜图提示词 | `分镜_E{id}.json` | banner：请先生成该集分镜 |
| 5. 视频提示词 | `分镜_E{id}.json` | banner：请先生成该集分镜 |
| 6. 配音配乐 | `分镜_E{id}.json` + `剧本_E{id}.md` | banner：请先生成分镜和剧本 |

---

## 10. 错误处理

| 场景 | 处理 |
|------|------|
| LLM 返回格式异常（非 JSON/非 md） | `repair_json_text` 修复 or 直接落盘原始文本，UI 显示警告 |
| 分镜 JSON shots 为空 | 400 + banner 提示：该集分镜无镜头数据 |
| 网络断开 / 超时 | SSE `error` 事件 → 显示重试按钮，已生成部分保留 |
| 产物文件写盘失败 | QMessageBox warning |
| 切集时有 dirty 改动 | `try_release()` 弹保存/丢弃/取消 |

---

## 11. 测试策略

| 测试文件 | 用例数 | 覆盖 |
|---------|--------|------|
| `tests/test_screenwriter_agent/test_route_image_prompts.py` | 5 | 路由 + SSE + 产物落盘 |
| `tests/test_screenwriter_agent/test_route_video_prompts.py` | 5 | 路由 + JSON/MD 双格式 |
| `tests/test_screenwriter_agent/test_route_audio_prompts.py` | 5 | 路由 + 音色卡 + 分镜表 |
| `tests/test_ui/screenwriter/test_image_prompts_page.py` | 5 | widget smoke + 上游 banner |
| `tests/test_ui/screenwriter/test_video_prompts_page.py` | 5 | widget smoke + 复制按钮 |
| `tests/test_ui/screenwriter/test_audio_prompts_page.py` | 5 | widget smoke + 音色卡两列 |
| `tests/test_ui/screenwriter/test_wizard_host.py` | 追加 2 | 6 阶段 stepper 不崩 |
| `tests/test_ui/screenwriter/test_script_page.py` | 追加 1 | highlight_generate_button |

**总计约 33 个新用例**。现有套件零回归。

---

## 12. 不在本期（显式延后）

- 分镜图提示词：shot 分组的拖拽排序 UI（目前只按格式自动分组）
- 视频提示词：直接调 LTX2.3 API 自动出片
- 配音配乐：直接对接 sound_track_agent 自动生成
- Stage 4/5/6 的 purge_downstream 集感知扩展（新产物加入清理链）
- 多集「一键全集」批量生成 image/video/audio prompts

---

## 13. 验收标准

1. Wizard 顶部显示 6 个数字按钮，切换不崩
2. 从「1.创意」选定候选推进后，「2.剧本」页的生成按钮高亮，显示创意来源提示条
3. 「3.分镜」页行为与现在完全一致（零回归）
4. 「4.分镜图提示词」：选 9宫格/4宫格/单帧后点生成，出对应分组 prompt；每组有复制按钮
5. 「5.视频提示词」：生成 global_prompt + 13 条 local_prompt，每行有 ⧉ 复制图标；导出 .json + .md
6. 「6.配音配乐」：顶部两列音色卡 + 下方分镜匹配表；导出 .md
7. 所有 3 个新 stage 缺失上游分镜 JSON 时显示 banner
8. 33 个新测试全绿，现有 235+ 测试零回归
