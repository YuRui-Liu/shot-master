# 拆图重采样（比例 + 分辨率 + AI 超分）设计

**项目**：shot-prompt-backwards
**版本**：v0.5（设计阶段）
**日期**：2026-05-24
**状态**：设计评审中（待用户复核）

---

## 1. 背景与目标

### 1.1 问题

当前 `SplitPanel`（`app/ui/panels/split_panel.py`）只配置网格、白边、间距、输出格式（PNG/JPG）。拆出的子图分辨率等于源图自然像素：2K 原图按 4×4 拆 16 张 → 单张 ~512×512，明显不够送 ComfyUI 视频/图像生成流水线。

### 1.2 目标

在拆图面板增加可选的"重采样"后处理：

1. 用户可指定**目标比例**（1:1 / 16:9 / 9:16 / 自定义）和**长边像素**（短边按比例自动算）。
2. 用户可选**重采样算法**：纯 LANCZOS（CPU、零依赖）或 **AI 超分**（调本机 ComfyUI HTTP API 的 `ImageUpscaleWithModel`）。
3. AI 超分不可用时**自动回退 LANCZOS** 并在状态栏提示，不中断任务。
4. 仅作用于拆图面板的落盘输出，文件名保持现状不变。

### 1.3 非目标

- 不修改 shot-master 包（`shot_master.core.splitter` / `specs` 保持不动）
- 不在反推预览 / 拼图 / 去白边 面板加重采样
- 不内置 onnxruntime 等 AI 超分依赖
- 不做任务取消按钮
- v0.5 不做反推预览同步重采样

---

## 2. 需求决策记录

下列为 brainstorm 阶段一问一答的最终结果（不可在实现阶段擅自变更）：

| # | 决策点 | 结果 |
|---|---|---|
| 1 | 目标尺寸输入方式 | **比例预设 + 长边像素**（短边自动） |
| 2 | 目标比例与原始比例不符时 | **中心裁剪**（复用 `center_crop_to_aspect`） |
| 3 | 上采样算法档位 | **LANCZOS / AI 超分** 两档可选 |
| 4 | AI 超分后端 | **调本机 ComfyUI HTTP API** |
| 5 | 默认行为 | 默认 Auto（不缩放）；勾"启用重采样"展开新控件 |
| 6 | 比例预设清单 | **5 项**：跟随原图 / 1:1 / 16:9 / 9:16 / 自定义 |
| 7 | 长边输入框 | 默认 **2048**，范围 **256–8192** |
| 8 | AI 失败回退策略 | **自动回退 LANCZOS + 状态栏提示**（整批仅提示 1 次） |
| 9 | 超分模型列表 | 调 ComfyUI `/object_info/UpscaleModelLoader` 动态拉取 |
| 10 | 输出文件命名 | **保持现状**（`{stem}_{i}.{ext}`） |
| 11 | ComfyUI URL 存储位置 | 设置页加 `comfyui_url` 字段，默认 `http://127.0.0.1:8188` |
| 12 | 重采样作用范围 | **仅拆图面板的落盘输出** |

---

## 3. 架构

### 3.1 改动文件清单

```
app/
├── grid_ops.py                       # 修改：加 ResampleSpec / ResampleAlgo / resize_tile()
├── providers/
│   └── comfyui_upscaler.py           # 新增：ComfyUIUpscaler 客户端
├── config.py                         # 修改：加 comfyui_url + split_resample_defaults
├── ui/
│   ├── panels/
│   │   └── split_panel.py            # 修改：加重采样组 + execute 串新逻辑
│   └── widgets/
│       └── resample_group.py         # 新增：ResampleGroup QWidget
docs/superpowers/specs/
└── 2026-05-24-split-resample-design.md   # 本文档
tests/
├── test_resize_tile.py               # 新增
└── test_comfyui_upscaler.py          # 新增
（test_split_panel.py 若存在则扩展，否则新增）
```

shot-master 包不动。

### 3.2 组件职责切片

- **`resize_tile(tile, spec, upscaler?, status_cb?) → PIL.Image`**
  纯函数后处理。输入一张 tile + ResampleSpec，输出一张图。负责中心裁剪、算法分支、AI 失败回退。

- **`ComfyUIUpscaler`**
  封装 ComfyUI 4 个 endpoint：`/upload/image`、`/prompt`、`/history/{id}`、`/view`，以及 `/object_info/UpscaleModelLoader` 模型探测。完全独立于 vision provider，独立可单测。

- **`ResampleGroup(QWidget)`**
  纯 UI 容器：复选框 + 比例下拉 + 长边 spin + 算法下拉 + AI 模型下拉 + 刷新按钮。发出 `specChanged` 信号；不感知图像处理。设计为可复用（虽然 v0.5 只在 SplitPanel 用）。

- **`SplitPanel`**
  组装层。收集 GridSpec + ResampleSpec，构造 upscaler（仅 AI 档），串联 `split_to_tiles → resize_tile → save_image`，处理状态栏、汇总弹窗。

### 3.3 调用链

```
SplitPanel.execute()
  └─ for path in selected:
       tiles = split_to_tiles(path, grid_spec)        # shot-master，无改动
       for tile in tiles:
         resized = resize_tile(tile, resample_spec,
                               upscaler=upscaler,
                               status_cb=status_dedupe)
         save_image(resized, out_dir / f"{stem}_{i+1}{ext}")
```

---

## 4. 数据模型

### 4.1 `app/grid_ops.py` 顶部新增

```python
from dataclasses import dataclass
from enum import Enum

class ResampleAlgo(str, Enum):
    LANCZOS = "lanczos"
    AI = "ai"

@dataclass(frozen=True)
class ResampleSpec:
    """重采样后处理规格。enabled=False 时其他字段全部忽略。"""
    enabled: bool = False
    aspect_w: int = 0          # 0 = 跟随原图（与 aspect_h=0 同义 Auto）
    aspect_h: int = 0
    long_edge: int = 2048
    algorithm: ResampleAlgo = ResampleAlgo.LANCZOS
    ai_model: str = ""

    @property
    def is_auto_aspect(self) -> bool:
        return self.aspect_w == 0 or self.aspect_h == 0
```

### 4.2 `settings.json` 新增字段

```jsonc
{
  // ... 现有字段
  "comfyui_url": "http://127.0.0.1:8188",
  "split_resample_defaults": {
    "enabled": false,
    "aspect_w": 1, "aspect_h": 1,
    "long_edge": 2048,
    "algorithm": "lanczos",
    "ai_model": ""
  }
}
```

> 注：dataclass 默认 `aspect_w=aspect_h=0`（Auto）但 settings.json 默认 `1:1`——
> 前者是"程序内未指定 spec 时的安全 Auto"，后者是"UI 第一次打开时的初始选择"，
> 故意不一致。

### 4.3 `app/config.py` 新增字段

```python
@dataclass
class Config:
    # ... 现有字段
    comfyui_url: str = "http://127.0.0.1:8188"
    split_resample_defaults: dict = field(default_factory=lambda: {
        "enabled": False, "aspect_w": 1, "aspect_h": 1,
        "long_edge": 2048, "algorithm": "lanczos", "ai_model": "",
    })
```

### 4.4 ComfyUI 客户端对外契约

```python
class ComfyUIUnavailable(Exception):
    """ComfyUI 不可达 / 探测失败。回退 LANCZOS。"""

class ComfyUIUpscaleError(Exception):
    """工作流执行失败（模型不存在 / 超时 / 节点报错）。回退 LANCZOS。"""

class ComfyUIUpscaler:
    def __init__(self, base_url: str, timeout: int = 120):
        """timeout 用作 history 轮询的整体上限秒数；
        httpx 单次请求超时单独按 10s 处理。"""
        ...

    def list_models(self) -> list[str]:
        """GET /object_info/UpscaleModelLoader → upscale_model 选项列表。
        连接失败抛 ComfyUIUnavailable；JSON 中缺节点返回 []。"""

    def upscale(self, image: Image.Image, model_name: str) -> Image.Image:
        """提交 4 节点 upscale workflow → 轮询 history → 下载结果。
        连接失败抛 ComfyUIUnavailable；执行类失败抛 ComfyUIUpscaleError
        （细分原因：model_not_found / timeout / bad_response）。"""
```

---

## 5. UI 设计

### 5.1 拆图面板新布局

在「白边/间距」和「输出」之间插入「重采样」分组：

```
┌─ 网格 ─────────────────────────────┐
│ 源图 行 [2]   源图 列 [2]          │
│ 子图 行 [1]   子图 列 [1]          │
└────────────────────────────────────┘
┌─ 白边 / 间距 ──────────────────────┐
│ ...（不变）                         │
└────────────────────────────────────┘
┌─ 重采样 ───────────────────────────┐
│ ☐ 启用重采样                       │
│ 比例    [跟随原图  ▼] [w][:][h]    │   ← w/h 仅「自定义」时可见
│ 长边    [2048] px                  │
│ 算法    [LANCZOS    ▼]             │
│ AI 模型 [4x-UltraSharp.pth  ▼][🔄] │   ← 仅 algorithm=AI 时可见
└────────────────────────────────────┘
┌─ 输出 ─────────────────────────────┐
│ 格式 [PNG ▼]                       │
└────────────────────────────────────┘
```

### 5.2 控件清单（`ResampleGroup`）

| 控件 | 类型 | 说明 |
|---|---|---|
| 启用重采样 | `QCheckBox` | 关闭 → 下方控件 `setEnabled(False)` 并视觉灰化 |
| 比例预设 | `QComboBox` | 5 项：`跟随原图` (0:0) / `1:1` / `16:9` / `9:16` / `自定义` |
| 自定义 w/h | 2× `QSpinBox` 1–9999 | 仅选「自定义」时 `show()` |
| 长边 | `QSpinBox` 256–8192，默认 2048，步进 64 | suffix " px" |
| 算法 | `QComboBox` | `LANCZOS` / `AI 超分` |
| AI 模型 | `QComboBox`（可编辑） | 仅 algorithm=AI 时 `show()`；下拉项动态填 |
| 刷新模型 | `QPushButton` | 点 → 调 `list_models()` 重新填；失败弹 toast |

### 5.3 信号联动

```
启用重采样 toggled(checked):
    ResampleGroup.set_form_enabled(checked)
    SplitPanel.validityChanged.emit()

比例下拉 currentTextChanged(text):
    text == "自定义" → show() w/h spin，其余 hide()

算法下拉 currentTextChanged(text):
    text == "AI 超分" → show() 模型下拉 + 刷新按钮
                       懒触发 list_models()（仅首次）

刷新按钮 clicked:
    阻塞调用 list_models() → 重填下拉 → 若历史选中仍在列表则恢复
    失败 → QMessageBox.warning + statusMessage.emit
```

### 5.4 模型下拉的"懒加载 + 缓存"

- 第一次切到「AI 超分」时**自动**触发一次 `list_models()`
- 拉取期间下拉显示"加载中…"并 `setDisabled(True)`
- 结果缓存在 `ResampleGroup` 实例内，直到面板销毁
- 点🔄按钮强制重拉

### 5.5 设置页新增

```
ComfyUI URL  [http://127.0.0.1:8188              ]  [测试连接]
```

「测试连接」按钮：阻塞调 `ComfyUIUpscaler(url).list_models()`，成功弹"已发现 N 个 upscale 模型"，失败弹错误详情。

### 5.6 验证规则（SplitPanel.validate 新增）

- `resample.enabled and aspect=="自定义" and (w<=0 or h<=0)` → `(False, "请填写自定义比例")`
- `resample.enabled and algorithm==AI and not ai_model` → `(False, "请选择 AI 超分模型")`
- `resample.enabled and not (256 <= long_edge <= 8192)` → `(False, "长边须在 256–8192 范围内")`

### 5.7 默认值写回

**仅在 execute() 启动那一刻**把当前面板状态写回 `cfg.split_resample_defaults`。中间任意改动不自动写。

---

## 6. ComfyUI 客户端与工作流

### 6.1 `list_models()` 实现

```
GET {base_url}/object_info/UpscaleModelLoader
解析路径：["UpscaleModelLoader"]["input"]["required"]["model_name"][0]
返回 list[str]，形如 ["4x-UltraSharp.pth", "RealESRGAN_x4plus.pth", ...]
```

- httpx ConnectError / 非 2xx / JSON 解析异常 → `raise ComfyUIUnavailable(detail)`
- JSON 中缺 `UpscaleModelLoader` 节点 → 返回 `[]`（不抛）

### 6.2 `upscale(image, model_name)` 流程

```
1. PIL.Image → PNG bytes
2. POST /upload/image (multipart: image + type=input + overwrite=true)
   → {"name": "spb_<uuid>.png", "subfolder": "", "type": "input"}
3. 组装 4 节点 workflow → POST /prompt {"prompt": workflow, "client_id": "spb-<uuid>"}
   → {"prompt_id": "..."}
4. 轮询 GET /history/{prompt_id} 每 0.5s，直到 entry["outputs"] 出现
   超时 timeout 秒 → ComfyUIUpscaleError("timeout")
5. 取 outputs["4"]["images"][0] = {filename, subfolder, type:"output"}
   （节点 "4" 是 workflow 中的 SaveImage 节点；3 是中间 ImageUpscaleWithModel 不产出 images）
   GET /view?filename=...&subfolder=...&type=output
   → 返回 PIL.Image
```

文件名加 uuid 避免并发拆图互踩。

### 6.3 工作流（4 节点）

```jsonc
{
  "1": {"class_type": "LoadImage",
        "inputs": {"image": "<uploaded_filename>"}},
  "2": {"class_type": "UpscaleModelLoader",
        "inputs": {"model_name": "<model_name>"}},
  "3": {"class_type": "ImageUpscaleWithModel",
        "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
  "4": {"class_type": "SaveImage",
        "inputs": {"filename_prefix": "spb_upscale", "images": ["3", 0]}}
}
```

> `ImageUpscaleWithModel` 按模型固有倍率（通常 4×）放大，不接受目标尺寸参数——这就是为什么 `resize_tile` 在 AI 档拿到结果后**还要做一次 LANCZOS 收尾**把长边压到用户填的 `long_edge`。

### 6.4 `resize_tile()` 实现

```python
def resize_tile(tile: Image.Image,
                spec: ResampleSpec,
                upscaler: ComfyUIUpscaler | None = None,
                status_cb: Callable[[str], None] | None = None
                ) -> Image.Image:
    if not spec.enabled:
        return tile

    # 1. 按比例中心裁剪（仅非 Auto）
    if not spec.is_auto_aspect:
        tile = center_crop_to_aspect(tile,
                  AspectRatio(spec.aspect_w, spec.aspect_h))

    # 2. AI 档先尝试 ComfyUI 超分
    if spec.algorithm == ResampleAlgo.AI and upscaler is not None:
        try:
            tile = upscaler.upscale(tile, spec.ai_model)
        except (ComfyUIUnavailable, ComfyUIUpscaleError) as e:
            if status_cb:
                status_cb(f"AI 超分不可用，已回退 LANCZOS：{e}")
            # 落入 LANCZOS 收尾

    # 3. 无论 AI 是否生效，都用 LANCZOS 缩放到目标长边
    #    （AI 出 4x 通常过大需要缩小；LANCZOS 档可能需放大或缩小）
    return _resize_to_long_edge(tile, spec.long_edge, Image.LANCZOS)


def _resize_to_long_edge(img, long_edge, resample):
    w, h = img.size
    if max(w, h) == long_edge:
        return img
    scale = long_edge / max(w, h)
    return img.resize((round(w*scale), round(h*scale)), resample)
```

---

## 7. 数据流与错误处理

### 7.1 错误矩阵

| 错误类别 | 行为 | 用户反馈 |
|---|---|---|
| 控件验证失败 | 不进 worker，立即拒绝 | QMessageBox.warning |
| 输出目录不可写 | worker 第一张就抛 → 中止整任务 | QMessageBox.critical |
| splitter 抛 `SplitGridError` / `CellTooSmallError` | 中止整任务（同当前行为） | QMessageBox.critical |
| **AI 超分不可达 / 模型不存在** | **单张静默回退 LANCZOS**，整批仅提示 1 次 | 状态栏 |
| **AI 超分单张超时 / 数据损坏** | 该张回退 LANCZOS，继续下一张 | 末尾汇总弹窗 |
| save_image IO 失败 | 中止整任务 | QMessageBox.critical |

### 7.2 状态去重

```python
class _StatusDedupe:
    def __init__(self, emit):
        self.emit, self.seen = emit, set()
    def __call__(self, msg):
        if msg not in self.seen:
            self.seen.add(msg)
            self.emit(msg)
```

`status_cb=_StatusDedupe(self.statusMessage.emit)` 传入 `resize_tile`，同样错误整批只透出一次。

### 7.3 末尾汇总

worker 统计 `ai_fallback_count / ai_total_count`，完成后：

```python
QMessageBox.information(self, "完成",
    f"已拆出 {total} 张" +
    (f"\n（其中 {ai_fb}/{ai_total} 张因超分失败回退 LANCZOS）"
     if ai_fb else ""))
```

### 7.4 日志

ComfyUI 所有请求/响应明细写入 `logs/comfyui.log`（用现有 logging）。

### 7.5 并发与取消

- ComfyUI 单实例 prompt 队列串行处理，与我们的串行调用天然兼容，不需要锁
- v0.5 不做取消按钮（单张 AI 超分预期 <5s，20 张可接受）

---

## 8. 测试策略

### 8.1 `tests/test_resize_tile.py`（纯函数）

| 用例 | 验证 |
|---|---|
| `disabled_passthrough` | enabled=False → 返回同一对象（`is`） |
| `lanczos_long_edge_scaling` | 1024×512 + long_edge=2048 + Auto → 2048×1024 |
| `lanczos_no_op_when_size_matches` | 1024×512 + long_edge=1024 → 1024×512（同一对象） |
| `lanczos_downsample` | 4096×2048 + long_edge=1024 → 1024×512 |
| `aspect_center_crop_16_9_from_4_3` | 1200×900 + 16:9 + long_edge=1600 → 1600×900 |
| `aspect_center_crop_1_1_from_landscape` | 1920×1080 + 1:1 + long_edge=512 → 512×512 |
| `custom_aspect_3_2` | 1000×1000 + 3:2 + long_edge=600 → 600×400 |
| `ai_path_calls_upscaler_then_resize` | mock upscale 返 4096×4096，输入 1024×1024，long_edge=2048 → 2048×2048，mock 被调 1 次 |
| `ai_unavailable_falls_back_to_lanczos` | mock 抛 `ComfyUIUnavailable` → 走 LANCZOS，status_cb 被调 1 次含"回退" |
| `ai_upscale_error_falls_back_to_lanczos` | 同上但抛 `ComfyUIUpscaleError` |

### 8.2 `tests/test_comfyui_upscaler.py`（mock httpx）

| 用例 | 验证 |
|---|---|
| `list_models_happy_path` | mock `/object_info/UpscaleModelLoader` → 返回标准列表 |
| `list_models_returns_empty_when_no_upscaler_node` | JSON 缺节点 → `[]`，不抛 |
| `list_models_raises_unavailable_on_connection_error` | httpx ConnectError → `ComfyUIUnavailable` |
| `list_models_raises_unavailable_on_500` | HTTP 500 → `ComfyUIUnavailable` |
| `upscale_happy_path` | mock 4 个 endpoint 按序响应 → PIL.Image，尺寸 4× |
| `upscale_polls_history_until_outputs_present` | /history 前两次空，第三次有 outputs → 成功 |
| `upscale_timeout` | /history 始终空 → `ComfyUIUpscaleError("timeout")` |
| `upscale_model_not_found` | /prompt 返回 node validation error → `ComfyUIUpscaleError("model_not_found")` |
| `upscale_uses_unique_filename_per_call` | 连续 2 次 /upload/image 收到的 filename 不同（含 uuid） |

`conftest.py` 加 `fake_comfyui_response()` 辅助函数集中维护 JSON 字面量。

### 8.3 `tests/test_split_panel.py`（集成层薄测）

| 用例 | 验证 |
|---|---|
| `validate_rejects_ai_without_model` | enabled=True, algorithm=AI, ai_model="" → 拒绝 |
| `validate_rejects_custom_aspect_zero` | aspect="自定义" w=0 → 拒绝 |
| `validate_rejects_long_edge_out_of_range` | long_edge=100 → 拒绝 |
| `defaults_writeback_on_execute` | 跑一次 execute → settings.json 被更新 |
| `execute_passes_correct_spec_to_resize_tile` | mock resize_tile，断言 spec 字段值与控件一致 |

### 8.4 不测的

- shot-master 的 `split_image` / `center_crop_to_aspect`（已有自测）
- PIL LANCZOS 算法本身
- ComfyUI 实际工作流执行（mock 已足够，真实联调留给手工冒烟）

### 8.5 手工冒烟清单

1. ComfyUI 关闭 → 选 AI 档拆 → 验证回退 LANCZOS + 状态栏提示
2. ComfyUI 开启但模型名不存在 → 同上回退
3. ComfyUI 正常 + 4x-UltraSharp → 输出尺寸正确（4× 后 LANCZOS 压到 long_edge）
4. 长边设 256（缩小场景）→ 输出对应缩小
5. 自定义比例 7:3 → 输出比例正确
6. 设置页「测试连接」按钮 → 成功/失败两种路径
7. 20 张图批量 AI 档（ComfyUI 关闭）→ 整批仅 1 次状态栏提示，末尾汇总弹窗

---

## 9. 验收标准

v0.5 完成的标志：

- [ ] 拆图面板可见「重采样」分组，默认折叠（disabled）
- [ ] 5 项比例预设可切，自定义档可填 w/h
- [ ] 长边 spin 限制 256–8192
- [ ] LANCZOS 档纯本地工作（无网络）
- [ ] AI 档可拉模型列表 / 跑通超分 / 失败回退 LANCZOS
- [ ] 设置页可改 ComfyUI URL + 测试连接
- [ ] 验证规则全部生效
- [ ] 默认值仅在 execute 时写回 settings.json
- [ ] 手工冒烟 7 项全过
- [ ] 单测全通过

---

## 10. 风险与开放问题

| 风险 | 影响 | 应对 |
|---|---|---|
| ComfyUI API 在新版本破坏性升级 | upscale 路径全断 | 锁住 endpoint 行为契约的集成测试；版本不兼容时只回退 LANCZOS |
| 大批量超分 LANCZOS 回退被忽略 | 用户以为出了 4K 实际是 LANCZOS 2K | 末尾汇总弹窗强提醒；命名不变所以无法事后区分（v0.6 可考虑加水印日志） |
| 用户填了非法比例（w/h=0） | 中心裁剪计算除零 | UI 层验证拒绝；resize_tile 内部再 assert |
| ComfyUI 超分模型输出非 RGB（带 alpha） | LANCZOS resize 后保留 alpha，JPG 保存炸 | 由 `save_image` 层按目标格式做模式转换（shot-master `saver.py` 现有职责，需确认其对 RGBA→JPG 的处理；若缺则补） |

**开放问题（v0.6+ 再考虑）：**
- 是否在反推预览中同步应用重采样（让送 vision 模型的图也是高分版本）？
- 是否支持每模型记住"最近一次选择"？
- 是否暴露 LANCZOS 之外的本地算法（BICUBIC / NEAREST）？

---

## 11. 下一步

1. 用户复核本设计文档
2. 复核通过后调用 `superpowers:writing-plans` 生成实现计划
3. 实现计划按 milestone 切分 → 编码 → 测试 → 集成

---

**文档负责人**：项目作者
**最近更新**：2026-05-24
