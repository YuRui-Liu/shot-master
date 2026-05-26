# 配音（TTS：音色设计 + 声音克隆）— 设计

**日期**：2026-05-26
**目标**：新增「配音」功能，镜像「视频生成」的任务栏 + 独立任务窗范式。任务窗支持两类 TTS：**音色设计**（Qwen3 TTS VoiceDesign）与**声音克隆**（IndexTTS2，含 4 种情感模式）。提交走 RunningHub（workflow_id + nodeInfoList 覆盖）。「设置」新增「配音…」。

设计依据：用户提供的两份工作流——
- 声音克隆完整图 `TTS2情绪化声音.json`（16 节点多分支 + #26 选组），api 简版 `TTS2情感声音克隆_api.json`。
- 音色设计 `Qwen3 TTS 音色设计_api.json`。

## 确认的节点映射（已通过 link 追踪验证）

### 声音克隆 — `workflow_id = 2058388078015901697`（16 节点多分支）
共享输入（4 个分支共用）：

| 角色 | 节点 | 字段 |
|---|---|---|
| 要合成文本 | `4` (CR Prompt Text) | `prompt` |
| 说话人参考音频 | `10` (LoadAudio) | `audio` |
| 情感描述（模式2） | `16` (CR Prompt Text) | `prompt` |
| 情感参考音频（模式3） | `19` (LoadAudio) | `audio` |
| 情感向量（模式4） | `21` (CR Prompt Text) | `prompt` |

模式 → 分支 → `#26 Fast Groups Bypasser` 组开关（开当前、关其余 3 个模式组；`控制区` 组不动）：

| 模式 | 分支节点(emo_alpha 写这里) | #26 组标题(fieldName) |
|---|---|---|
| 1 默认声音克隆 | `1` | `默认声音克隆 1` |
| 2 文本情绪 | `14` | `文本情绪方案 2` |
| 3 语音情绪模仿 | `17` | `语音情绪模仿 3` |
| 4 情感向量 | `20` | `情感向量方案 4` |

- `#26` 覆盖方式：`{nodeId:"26", fieldName:<组标题>, fieldValue:true/false}`，4 个模式组中只开当前模式那个。
- `emo_alpha`（情感强度，0.0–2.0，默认 1.0）→ 写当前模式分支节点的 `emo_alpha` widget。
- 情感向量字符串格式：`"[h, a, s, f, ht, low, sur, neu]"`，每项 0–1，顺序 `[Happy, Angry, Sad, Fear, Hate, Low, Surprise, Neutral]`。
- `_s2` 系列（第二说话人）不暴露、不覆盖，留默认。
- 输出：只有激活组会跑，其 SaveAudio 产出即结果（无需指定具体 SaveAudio 节点；从任务结果列表取产出的音频）。

> 部署前提：线上 `2058388078015901697` 必须是这份 16 节点多分支版（含 `#19` 情感音频与 `#26`）。若线上仍是 4 节点简版，模式 3 跑不了——以最终部署的 workflow 为准；节点号做成可配置（见「配音设置」）。

### 音色设计 — `workflow_id = 2059260167811850242`

| 角色 | 节点 | 字段 |
|---|---|---|
| 要合成文本 | `14` (Text) | `text` |
| 音色描述 | `15` (Text) | `text` |
| 语言 | `22` (TDQwen3TTSVoiceDesign) | `language`（默认 `Auto`） |

输出：节点 `18` SaveAudio 产出。

## 架构（镜像视频生成）

新增单元，边界清晰、各自可独立理解/测试：

1. **任务模型/存储** `drama_shot_master/core/dub_task_store.py`
   - `DubTask`（dataclass）：`id, name, mode("design"|"clone"), payload(dict), updated_at, last_result`。
     `payload` 存该任务的所有输入（文本、音色描述/语言；或 克隆的文本/说话人音频路径/情感子模式/emo_text/emo_vector/emo_audio 路径/emo_alpha）。
   - `DubTaskStore`：`all/get/add/update/remove/duplicate/to_list/from_list`，与 `VideoTaskStore` 同形。

2. **TTS 提交构造** `drama_shot_master/core/tts_profiles.py` + `drama_shot_master/providers/tts_builder.py`
   - `tts_profiles.py`：`TTSProfile`（dataclass：`key, name, workflow_id, nodes:dict[str,str]`）+ `PROFILES = {"voice_design":…, "voice_clone":…}`，`nodes` 默认填上表角色→节点号。
   - `tts_builder.py`：`build_design_node_info(text, style, language, prof) -> list[dict]`；
     `build_clone_node_info(text, mode, emo_alpha, emo_text, emo_vector, uploaded:dict, prof) -> list[dict]`
     —— 后者按模式生成共享输入覆盖 + `#26` 4 组开关 + 当前分支 `emo_alpha` + 模式特有字段；纯函数，可单测。
   - 上传：复用 `RunningHubClient.upload_file`（返回 `openapi/<hash>.ext`）；`LoadAudio.audio` 的 fieldValue 直接用返回的完整 fileName（参考此前 V3 图修复：保留 `openapi/` 前缀）。

3. **任务栏面板** `drama_shot_master/ui/panels/dub_task_manager_panel.py`
   - `DubTaskManagerPanel(BasePanel)`，构造 `(state, cfg, store, open_window_cb, close_window_cb, persist_cb)`，
     方法 `refresh/set_task_status/clear_task_status`，信号 `taskRenamed(str,str)`。列：名称/模式/状态/输出/更新时间 + 新建/打开/复制/删除。

4. **任务窗** `drama_shot_master/ui/windows/dub_task_window.py`
   - `DubTaskWindow(QMainWindow)`，构造 `(task, state, cfg)`，信号 `statusChanged/resultReady/closed/dirty`（与 video 同形）。
   - 内嵌 `DubPanel`（`drama_shot_master/ui/panels/dub_panel.py`）：顶部单选 `音色设计/声音克隆`（QButtonGroup），下面用 `QStackedWidget` 切两套表单：
     - 设计页：文本(QPlainTextEdit) + 音色描述(QPlainTextEdit) + 语言(QComboBox: Auto/中文/English…)。
     - 克隆页：文本 + 说话人参考音频(选文件) + 情感强度(QDoubleSpinBox 0–2,步0.05,默认1.0) + 4 选 1 情感子模式(QButtonGroup) + 子模式额外区(QStackedWidget)：模式2→情感描述(QPlainTextEdit)；模式3→情感参考音频(选文件)；模式4→8 个 QDoubleSpinBox(0–1，带 Happy/Angry/Sad/Fear/Hate/Low/Surprise/Neutral 标签)；模式1→空。
   - 底部「生成」按钮 → FunctionWorker 后台跑（上传+create_task+轮询）→ 完成 emit `resultReady(task_id, flac_path)`；提供「播放/打开所在文件夹」。

5. **配音设置对话框** `drama_shot_master/ui/dialogs/dub_settings_dialog.py`
   - 两个 workflow_id（默认上面两个 id）；节点号 profile（默认上表，JSON/表单可改，应对线上重部署后节点号变化）；输出目录；进阶采样默认值（top_k=30/top_p=0.8/temperature=0.8/num_beams=3/max_mel_tokens=1500）。存进 config。
   - 「设置」菜单新增 `配音…`。

6. **主窗集成** `drama_shot_master/ui/main_window.py`
   - `FUNCS` 视频组追加 `("配音","dubbing")`；`_VIDEO_KEYS` 与 `is_wide` 集合加 `"dubbing"`。
   - 仿 `_try_make_soundtrack_panel` 做软导入兜底（缺失则占位 QWidget，不影响启动）。
   - `self.dub_store = DubTaskStore.from_list(self.cfg.dub_tasks)`；
     `_open_dub_task_window/_close_dub_task_window/_persist_dub_tasks/_on_dub_task_*` 一套（与 video 平行），`self._open_dub_windows: dict`。

7. **配置** `drama_shot_master/config.py`
   - 新增 `dub_tasks: list`（持久化任务）、`dub_workflow_ids: dict`（design/clone）、`dub_node_profiles: dict`（可选覆盖默认节点号）、`dub_output_dir: str`、`dub_sampling: dict`。`update_settings` 与 `load_config` 一并读写（含老 settings.json 兼容）。

## 提交逻辑（tts_builder 细节）

**音色设计** `build_design_node_info`：
```
[{14,"text",文本},{15,"text",音色描述},{22,"language",语言}]
```

**声音克隆** `build_clone_node_info`（mode∈1..4）：
- 公共：`{4,"prompt",文本}`、`{10,"audio",上传的说话人音频fileName}`
- #26 组开关：当前模式组 true，其余 3 个模式组 false（`控制区` 不写）
- emo_alpha：`{活动分支节点,"emo_alpha",值}`
- 模式 2：`{16,"prompt",情感描述}`
- 模式 3：`{19,"audio",上传的情感音频fileName}`
- 模式 4：`{21,"prompt","[h, a, s, f, ht, low, sur, neu]"}`
- 进阶采样默认值写活动分支对应 widget（从 cfg.dub_sampling 取）。

## 测试

纯逻辑单测 `tests/test_dub/`：
- `tts_builder.build_design_node_info` 产出含 14/15/22 三项且值正确。
- `build_clone_node_info` 模式 1/2/4：含 #4/#10、#26 仅当前组 true 其余 false、emo_alpha 写对分支、模式 2 含 #16、模式 4 含 #21 且向量字符串格式正确（`[..]` 8 项）。
- 模式 3：含 #19 audio 覆盖（用占位 fileName）+ #26「语音情绪模仿 3」=true。
- `DubTaskStore` to_list/from_list round-trip；add/update/remove/duplicate。
UI（面板/窗/设置）薄层，手动验证：建任务→两模式切换→填写→生成→出 FLAC→播放。

## 非目标
- 不暴露 `_s2` 第二说话人参数。
- 不在软件内编辑工作流图（只覆盖 widget/开关）。
- 不内嵌音频波形编辑；仅生成 + 播放/打开。
- rgthree `控制区` 组保持启用，不做开关。
