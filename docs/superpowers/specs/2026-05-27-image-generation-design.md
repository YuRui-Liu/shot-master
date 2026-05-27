# 图片生成 — 设计

**日期**：2026-05-27
**目标**：新增「图片生成」功能，镜像「视频生成」的任务栏 + 独立任务窗范式。统一界面支持文生图 / 图生图 / 图文生图（自动判定），支持 @参考图锁一致性、画质/比例/数量选择、快捷提示词按钮。默认走豆包 ARK 图片 API，provider/模型可在设置切换；RunningHub 占位，待工作流后接入。

## 已确认决策

- **Provider**：抽象 `ImageGenProvider`；默认 **豆包**（ARK `/api/v3/images/generations`，默认模型 Seedream 系列，模型 id/base_url 可配）；备选 **OpenAI**；**RunningHub** 占位 stub（暂未接入）。
- **模式**：统一界面 + **自动判定**——无参考图=文生图；有参考图+提示词=图文生图；有参考图为主=图生图。顶部显示判定标签。
- **@参考图**：加图→缩略卡片→自动 `@图N`（可改名如 `@书生`）→点卡片把 `@标签` 插入提示词光标处；提交时**所有**参考图随提示词发给模型。
- **画质**：1K / 2K（默认 2K）。**比例**：自动 / 1:1 / 16:9 / 9:16 / 4:3 / 3:4。**数量**：1–4（默认 1）。
- **快捷按钮**：三视图 / 人设 / 2D / 360° / 3D / 国漫 / 特写 / 中焦 / 广角（点击在光标处插入预设文本）。
- 生成前查授权（同视频/配音的分散校验）。

## 架构（镜像视频/配音）

### 1. Provider 层 `drama_shot_master/providers/image_gen.py`
- `ImageGenProvider`（ABC）：
  - `generate(prompt: str, references: list[Path], *, size: str | None, n: int) -> list[bytes]`
    返回 n 张图的字节（PNG）。`references` 为本地图路径列表；`size` 形如 `"2304x1296"`，`None`=不指定（自动）。
- `DoubaoImageProvider(api_key, base_url, model)`：
  - POST `{base_url}/api/v3/images/generations`，body `{model, prompt, size?, n, response_format:"b64_json", image:[data-url...]}`；
    `image` 为参考图的 base64 data URL 数组（无参考图则不带 `image`，即文生图）。
  - 解析 `data[*].b64_json` → 解码为 bytes 列表。错误抛 `ImageGenError`。
- `OpenAIImageProvider(api_key, base_url, model)`：
  - 无参考图：POST `{base_url}/v1/images/generations`（model 默认 gpt-image-1）；有参考图：`{base_url}/v1/images/edits`（multipart，首图为主图，其余为附加）。返回 b64 → bytes。
- `RunningHubImageProvider`：`generate(...)` 直接抛 `ImageGenError("RunningHub 图片工作流暂未接入，待提供工作流后通过插件接入")`。预留，结构与 video/dub 的 WorkflowProfile 一致，便于后续接。
- `ImageGenError(Exception)`。
- 工厂 `make_image_provider(cfg) -> ImageGenProvider`：按 `cfg.imggen_provider`（"doubao"|"openai"|"runninghub"）构造，读 `cfg.imggen_base_url`、`cfg.imggen_model`、`cfg.api_keys[provider]`。

### 2. 画质×比例 → size `drama_shot_master/core/imggen_sizes.py`
```
SIZES = {
  "2K": {"1:1":"2048x2048","16:9":"2304x1296","9:16":"1296x2304",
         "4:3":"2304x1728","3:4":"1728x2304"},
  "1K": {"1:1":"1024x1024","16:9":"1152x648","9:16":"648x1152",
         "4:3":"1152x864","3:4":"864x1152"},
}
def resolve_size(quality: str, ratio: str) -> str | None:  # ratio=="自动" → None
```

### 3. 快捷提示词 `drama_shot_master/core/imggen_presets.py`
按钮→插入文本（用户原文，纯函数式常量）：
```
QUICK_PROMPTS = [
  ("三视图", "三视图（正面、侧面、背面），白色纯色背景，人物角色设计图，"),
  ("人设",   "角色人设参考图，白色纯色背景，正面、背面、侧面展示，"),
  ("2D",     "2D平面画风，动漫风格，"),
  ("360°",   "生成该图的360全景图，360度水平无死角，180度垂直全视角覆盖，画面完整连贯.首尾无缝衔接，无畸变.无拉伸.无黑边.无裁切"),
  ("3D",     "3D建模风格，CG渲染，"),
  ("国漫",   "中国漫画风格，线条流畅，"),
  ("特写",   "特写镜头，面部细节，"),
  ("中焦",   "标准镜头，透视正常，"),
  ("广角",   "广角镜头，透视变形，场景开阔，"),
]
```

### 4. 任务存储 `drama_shot_master/core/imggen_task_store.py`
- `ImgGenTask(id, name, payload: dict, updated_at: float, last_result: str)`。
  `payload` = `{prompt, refs:[{path,label}], quality, ratio, n}`。
- `ImgGenTaskStore`：`all/get/add/update/remove/duplicate/to_list/from_list`（同 `DubTaskStore`，复用 `_gen_task_id`）。

### 5. 编辑器 `drama_shot_master/ui/panels/imggen_panel.py`
内嵌于任务窗。`DubPanel` 风格的信号：`statusChanged(str)`、`resultReady(str)`（首张结果路径）、`dirty()`。
布局：
- **模式标签**（只读）：随参考图/提示词变化自动更新「文生图 / 图生图 / 图文生图」。
- **参考图区**：横向可滚动卡片列；`[+ 参考图]` 选文件（多选）→ 每张一卡片：缩略图 + 可编辑标签（默认 `图1/图2…`）+ `×` 删除；点卡片把 `@标签` 插入提示词光标处。
- **画质** QComboBox(2K/1K，默认 2K)、**比例** QComboBox(自动/1:1/16:9/9:16/4:3/3:4)、**数量** QSpinBox(1–4，默认 1)。
- **快捷按钮行**：按 `QUICK_PROMPTS` 生成一排小按钮，点击在提示词光标处插入文本。
- **提示词** QPlainTextEdit（多行）。
- **生成** 按钮（AccentButton）+ 状态标签 + **结果区**（n 张结果缩略图，点开/「打开所在文件夹」）。
- `to_payload()/load_payload()` 持久化全部输入。
- `_generate()`：查授权 → 组装 size(`resolve_size`) → 后台 `FunctionWorker`：`make_image_provider(cfg).generate(prompt, ref_paths, size, n)` → 落盘 `输出目录/imggen/img_<ts>_<i>.png` → emit 结果。

### 6. 任务窗 + 任务栏
- `drama_shot_master/ui/windows/imggen_task_window.py`：`ImgGenTaskWindow(task, cfg)`，内嵌 `ImgGenPanel`，信号 `statusChanged/resultReady/dirty/closed`，`set_title_name`（同 `DubTaskWindow`）。
- `drama_shot_master/ui/panels/imggen_task_manager_panel.py`：`ImgGenTaskManagerPanel`（同 `DubTaskManagerPanel`：表格 名称/状态/最近输出/更新时间 + 新建/打开/复制/删除/重命名，信号 `taskRenamed`）。

### 7. 设置 `drama_shot_master/ui/dialogs/imggen_settings_dialog.py`
字段：provider 下拉(豆包/OpenAI/RunningHub) + base_url + model + api_key + 输出目录。保存进 config。菜单「设置」新增「图片生成…」。

### 8. config `drama_shot_master/config.py`
新增字段 + 持久化 + load：
- `imggen_tasks: list`
- `imggen_provider: str = "doubao"`
- `imggen_base_url: str = "https://ark.cn-beijing.volces.com"`
- `imggen_model: str = ""`（默认空，用户在设置填豆包 Seedream 模型 id；空时给出友好提示）
- `imggen_output_dir: str = ""`
- api_key 复用 `api_keys[provider]`（豆包用 `api_keys["doubao"]`）。

### 9. 主窗集成 `drama_shot_master/ui/main_window.py`
- `FUNCS` 加 `("图片生成","imggen")`，放「图像」组（拆图/拼图/去白边/**图片生成**）。
- `is_wide` 集合加 `"imggen"`（独占主区）。
- `self.imggen_store = ImgGenTaskStore.from_list(cfg.imggen_tasks)` + `_open_imggen_windows` + `_make_imggen_panel()` 入 panels（保持 FUNCS↔panels 索引对齐）。
- 任务窗管理方法 `_open_imggen_window/_close_imggen_window/_persist_imggen_tasks/_on_imggen_*/_on_imggen_renamed`（镜像 dub）；`closeEvent` 持久化。
- 设置菜单加「图片生成…」→ `_open_imggen_settings`。

## 提交/数据流

1. 编辑器收集 prompt + refs(本地路径) + quality/ratio/n。
2. `resolve_size(quality, ratio)` → size 或 None。
3. 后台 worker：provider.generate(prompt, ref_paths, size=size, n=n)。
   - 豆包：参考图读入 base64 data URL 放 `image` 数组（无参考图则文生图）。
4. 落盘 n 张到 `输出目录/imggen/`，emit 首张为 last_result，结果区展示全部。
5. 失败 → 状态 FAILED + 弹错误（含 RunningHub stub 的"暂未接入"提示）。

## 测试

纯逻辑单测 `tests/test_imggen/`：
- `resolve_size`：2K/1K × 各比例返回正确 size；自动→None。
- `imggen_presets`：QUICK_PROMPTS 含 9 项且文本与规范一致（抽查 360°/广角 文案）。
- `ImgGenTaskStore`：add/update/remove/duplicate/to_list/from_list round-trip。
- `make_image_provider`：按 cfg.imggen_provider 返回对应类；runninghub provider.generate 抛"暂未接入"。
- `DoubaoImageProvider`（用假 httpx/client）：无参考图不带 image 字段；有参考图带 base64 data URL 数组；解析 b64_json → bytes。
UI（面板/窗/设置）薄层，手动验证：建任务→加参考图→插 @标签→选画质/比例/数量→生成→结果区出图。

## 非目标

- 不内置具体豆包模型 id（留设置填；空时提示）。
- RunningHub 图片工作流本期只占位，不实现提交（待工作流）。
- 不做图片局部编辑/涂抹/扩图（仅整图生成/参考生成）。
- 不做生成历史画廊（结果随任务 last_result 存最近一张/一组）。
