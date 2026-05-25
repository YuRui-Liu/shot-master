# 视频生成多工作流支持（导演台 + ALL IN ONE V3）设计

**项目**：drama-shot-master
**版本**：v0.7.x 增量（设计阶段）
**日期**：2026-05-25
**状态**：设计评审通过，待写实现 plan
**关联**：现有 `runninghub.py` 的 `LTXTaskBuilder`（写死导演台节点 ID）+ 视频任务体系。

---

## 1. 背景与目标

视频生成当前写死匹配「LTX2.3 导演台」工作流（`templates/ltx_director_v23.json`，节点 ID 4/32/23/34）。用户想在界面上把某个任务切到「LTX2.3 超高清编导级全能 ALL IN ONE V3」工作流。

两个工作流的 `LTXDirector` 节点**输入字段完全一致**，所以 spec→11 字段映射可复用；差异仅在节点 ID、分辨率节点、以及 V3 的额外节点 + 一个音频开关。

### 目标
- 代码内置 2 个工作流 profile；任务窗口内下拉切换，跟随任务持久化。
- V3 的额外可调项走 YAML（不在前台加文本框）。
- V3 上传音频时除 `use_custom_audio=ON` 外，同时翻 `LazySwitchKJ`(687) 的 `switch`。

### 非目标
- 不做"通用添加任意工作流"UI（只内置 2 个）
- 不在前台暴露 V3 的 LoRA/sigma/数字人等开关（走 YAML）

---

## 2. 关键决策（评审 Q&A）

| 决策 | 选择 |
|---|---|
| profile 来源 | 代码内置 2 个（节点 ID/分辨率策略从 JSON 推好），V3 模板 JSON 拷进项目 |
| 切换位置 | 每个任务窗口内下拉，跟随任务（存进 TimelineModel） |
| 每 profile 的 workflow_id | 各自配（设置里填），不共用 |
| V3 额外参数 | YAML 配置（`templates/ltx_v3_extras.yaml`），初始全注释 |
| V3 分辨率 | 映射到 director 节点的 custom_width/custom_height（无 TTResolutionSelector）|
| V3 音频开关 | 内置条件覆盖：`{node 687, field "switch", value use_custom_audio}` |

---

## 3. 两工作流节点对照（已从 JSON 推定）

| 角色 | 导演台 | V3 |
|---|---|---|
| LTXDirector | `4` | `672` |
| VHS_VideoCombine（filename_prefix）| `32` | `683` |
| RandomNoise（noise_seed）| `23` | `654` |
| TTResolutionSelector | `34` | 无 |
| 分辨率落点 | 节点 34 | director(672) 的 custom_width/custom_height |
| 音频开关 LazySwitchKJ | 无 | `687`（switch: True=上传音频, False=生成音频）|

`LTXDirector` 11 字段在两者一致（global_prompt/timeline_data/local_prompts/segment_lengths/use_custom_audio/frame_rate/display_mode/guide_strength/epsilon/duration_frames/duration_seconds）。

---

## 4. 架构

| 单元 | 文件 | 职责 |
|---|---|---|
| 工作流 profile 注册表 | `core/workflow_profiles.py`（新增，Qt-free） | `WorkflowProfile` dataclass + 2 个内置 PROFILES + 解析助手 |
| V3 模板 | `templates/ltx_director_v3_api.json`（新增，从外部拷入） | LTXTaskBuilder 结构校验 + 节点 |
| V3 额外覆盖 | `templates/ltx_v3_extras.yaml`（新增，可编辑，初始全注释） | 静态额外 nodeInfoList 覆盖 |
| builder 参数化 | `providers/runninghub.py`（改） | `LTXTaskBuilder(template_path, profile)` 用 profile 节点 ID + 分辨率分支 + 音频开关 + YAML extras |
| config workflow_ids | `config.py`（改） | `workflow_ids: dict[str,str]` + 旧 id 迁移 |
| RunningHub 设置 | `ui/dialogs/runninghub_settings_dialog.py`（改） | 每 profile 一个 workflow_id 输入框 |
| 任务记忆工作流 | `core/video_timeline_model.py`（改） | `TimelineModel.workflow_key` 字段 |
| 前台下拉 + 提交改造 | `ui/panels/video_panel.py`（改） | 工作流下拉绑 model.workflow_key；`_on_submit` 按 profile 取模板+workflow_id+builder |

### 边界
`workflow_profiles` 无 Qt 依赖、可单测。builder 由 profile 驱动，不再 import 写死的 `LTXNodes`（保留 `LTXNodes` 作为导演台 profile 的常量来源亦可，但 builder 取值改走 profile）。

---

## 5. 详细设计

### 5.1 `core/workflow_profiles.py`

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class WorkflowProfile:
    key: str
    name: str
    template_filename: str          # templates/ 下文件名
    director_node: str
    save_video_node: str
    noise_node: str
    resolution_node: str | None     # None → 分辨率落 director custom_w/h
    audio_switch_node: str | None   # None | "687"
    extras_yaml: str | None         # None | "ltx_v3_extras.yaml"

PROFILES: dict[str, WorkflowProfile] = {
    "director": WorkflowProfile(
        key="director", name="LTX2.3 导演台",
        template_filename="ltx_director_v23.json",
        director_node="4", save_video_node="32", noise_node="23",
        resolution_node="34", audio_switch_node=None, extras_yaml=None),
    "director_v3": WorkflowProfile(
        key="director_v3", name="LTX2.3 全能 V3（文生/多图/图音/数字人）",
        template_filename="ltx_director_v3_api.json",
        director_node="672", save_video_node="683", noise_node="654",
        resolution_node=None, audio_switch_node="687",
        extras_yaml="ltx_v3_extras.yaml"),
}

DEFAULT_PROFILE_KEY = "director"

def get_profile(key: str) -> WorkflowProfile:
    return PROFILES.get(key) or PROFILES[DEFAULT_PROFILE_KEY]

def template_path_for(profile: WorkflowProfile) -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / profile.template_filename

def extras_path_for(profile) -> Path | None:
    if not profile.extras_yaml:
        return None
    return Path(__file__).resolve().parent.parent / "templates" / profile.extras_yaml
```

### 5.2 LTXTaskBuilder 参数化（runninghub.py）

- `__init__(self, template_path, profile: WorkflowProfile)`：保存 profile；校验存在的关键节点改为 `profile.director_node / save_video_node / noise_node`（resolution_node 仅在非 None 时校验）。
- 所有 `LTXNodes.DIRECTOR/SAVE_VIDEO/NOISE/RESOLUTION` 引用改取 `self.profile.*`。
- **分辨率分支**（替换现有 `_apply_resolution` + resolution 部分）：
  - `resolution_node` 非 None（导演台）：维持现状，覆盖该节点 use_custom_resolution/custom_width/custom_height/resolution。
  - `resolution_node` None（V3）：在 director 节点上覆盖 `custom_width`/`custom_height`：
    - 自定义分辨率 → 直接用 `spec.custom_width/custom_height`
    - 预设 → 解析 `spec.resolution_preset` 前缀 `"WxH"`（如 `"1280x720 …"` → 1280×720）
- **音频开关**（新增）：`profile.audio_switch_node` 非 None 时追加
  `{nodeId: audio_switch_node, fieldName: "switch", fieldValue: bool(spec.use_custom_audio)}`。
- **YAML extras**（新增）：`profile.extras_yaml` 存在时读 `extras_path_for(profile)`，对每条 `{node, field, value}` 追加
  `{nodeId: node, fieldName: field, fieldValue: value}`。文件缺失/空/无 `overrides` 键 → 跳过（不报错）。用 `yaml.safe_load`。

### 5.3 V3 extras YAML（`templates/ltx_v3_extras.yaml`）

```yaml
# LTX2.3 V3 额外节点覆盖。编辑本文件即可调 V3 专属参数，无需改代码/前台。
# 留空（或全注释）= 全部用工作流自带默认值。
# 每条：{node: "节点ID", field: "字段名", value: 值}
overrides: []
  # 示例（按需取消注释并填）：
  # - {node: "695", field: "lora_01", value: "your_lora.safetensors"}
  # - {node: "637", field: "switch", value: false}   # F9 / T14 帧数切换
```

### 5.4 config workflow_ids（config.py）

- 新增 `workflow_ids: dict = field(default_factory=dict)`（key→workflow_id）。
- `update_settings` 落盘 + `load_config` 读取（dict 校验）。
- **迁移**：load 末尾若 `workflow_ids` 为空且旧 `runninghub_workflow_id` 有值 → `workflow_ids = {"director": cfg.runninghub_workflow_id}`。旧字段保留。
- 取值助手（可放 workflow_profiles 或 inline）：`cfg.workflow_ids.get(profile.key) or (cfg.runninghub_workflow_id if profile.key=="director" else "")`。

### 5.5 RunningHub 设置对话框

- 把单个「Workflow ID」输入框换成**每内置 profile 一个**：导演台 workflow_id / V3 workflow_id（用 `PROFILES` 遍历生成，保证未来加 profile 自动出框）。
- 保存：写 `cfg.workflow_ids[key] = 值`（空值也写空串）。加载：从 `cfg.workflow_ids` 回填（导演台回退旧 `runninghub_workflow_id`）。

### 5.6 TimelineModel.workflow_key

- 加字段 `workflow_key: str = "director"`，纳入 `to_dict`/`from_dict`（from_dict 缺省给 "director"）。
- 不进 `to_ltx_spec`（spec 不需要；profile 在提交时单独取）。

### 5.7 VideoPanel：工作流下拉 + 提交改造

- 在面板顶部（如池 toolbar 左侧）加 `QComboBox`「工作流」，items = `PROFILES` 的 name，data = key；初值 = `model.workflow_key`；切换写 `self.model.workflow_key` 并触发持久化（沿用窗口失活/关闭存盘；下拉变更也可即时 `_notify`，但最简：仅写 model，靠既有持久化点存）。
- `_on_submit` 改造：
  ```python
  profile = get_profile(self.model.workflow_key)
  template_path = template_path_for(profile)
  wf_id = self.cfg.workflow_ids.get(profile.key) or (
      self.cfg.runninghub_workflow_id if profile.key == "director" else "")
  if not wf_id:
      QMessageBox.warning(self, "未配置 workflow_id",
          f"请在「设置 → RunningHub」填「{profile.name}」的 workflow_id"); return
  builder = LTXTaskBuilder(template_path, profile)
  handle = submit_ltx_task(client, spec, builder, workflow_id=wf_id, …)
  ```
  （`resolve_template_path` 仅用于"自定义模板路径覆盖"的老逻辑；多工作流下以 profile 模板为准。自定义模板覆盖可保留只对 director 生效，或本期忽略——见 §6。）

---

## 6. 错误处理 / 边界

| 场景 | 行为 |
|---|---|
| 所选 profile 未配 workflow_id | 提交前提示去 RunningHub 设置填 |
| V3 模板 JSON 缺失 | LTXTaskBuilder 构造时 RunningHubInvalidSpec（缺节点/文件） |
| V3 extras YAML 缺失/空/格式错 | 安全跳过（无额外覆盖）；YAML 解析异常 → 记 warning 跳过 |
| 旧任务无 workflow_key | from_dict 给默认 "director" |
| 旧 runninghub_workflow_id 已配 | 迁移进 workflow_ids["director"] |
| 自定义模板路径（旧 cfg.runninghub_template_path）| 本期仅对 director profile 生效（V3 用内置模板）；不冲突 |

---

## 7. 测试

### 7.1 `tests/test_core/test_workflow_profiles.py`
- PROFILES 含 director/director_v3；节点 ID 正确（4/32/23/34/None；672/683/654/None/687）。
- `get_profile("unknown")` 回退 default；`template_path_for` 指向 templates/ 下正确文件名。

### 7.2 builder 测试扩展（`tests/test_providers/test_ltx_task_builder.py`）
- 用 director profile 构造 → nodeInfoList 节点 ID 4/32/23/34（保持现有行为）。
- 用 director_v3 profile 构造（造一个最小 V3 模板 fixture 或用拷入的真模板）：
  - nodeInfoList 用 672/683/654
  - 分辨率落 director 672 的 custom_width/custom_height（preset 解析 + 自定义两路）
  - `use_custom_audio=True` → 含 `{node 687, field switch, value True}`；False → value False
  - extras YAML：写临时 yaml 两条 → 出现在 nodeInfoList；空/缺失 → 不出现

### 7.3 config 测试扩展
- `workflow_ids` round-trip；旧 `runninghub_workflow_id` 迁移成 `{"director": …}`。

### 7.4 手测
1. RunningHub 设置：填导演台 + V3 两个 workflow_id。
2. 任务窗口顶部「工作流」下拉切到 V3 → 关窗重开仍是 V3（持久化）。
3. V3 任务提交 → 用 V3 的 workflow_id + 672/683/654 节点；正常出片。
4. V3 勾「启用音频轨」上传音频提交 → 节点 687 switch=True（上传音频）生效。
5. 编辑 `ltx_v3_extras.yaml` 加一条覆盖 → 提交生效（看 RunningHub 任务参数）。
6. 切回导演台任务 → 行为与之前一致。

---

## 8. 影响面
- 新增 1 模块 + 2 模板/配置文件 + 2 测试；改 runninghub.py / config.py / runninghub 设置对话框 / video_timeline_model.py / video_panel.py
- 零新增 pip 依赖（pyyaml 已声明）
- 兼容：旧任务默认 director；旧 workflow_id 自动迁移

---

## 9. 不做（YAGNI）
- ❌ 通用"添加任意工作流"UI / 节点映射编辑器
- ❌ 前台暴露 V3 LoRA/sigma/数字人开关（YAML 调）
- ❌ V3 自定义模板路径覆盖（V3 用内置模板）
- ❌ 工作流级别的字段差异校验（两者 director 字段一致，无需）
