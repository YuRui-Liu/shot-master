# 子项目 A · RunningHub API 客户端 + LTX 提交器设计

**项目**：shot-prompt-backwards
**版本**：v0.6 子项目 A（设计阶段）
**日期**：2026-05-24
**状态**：设计评审中（待用户复核）
**关联**：视频生成模块整体由 A/B/C 三个子项目组成；本文档只覆盖 A（纯库，零 UI）。
**前置依赖**：v0.5 split-resample 已合并至 main（commit 42feaa3）。

---

## 1. 背景与目标

### 1.1 问题

用户需要新增"视频生成功能模块"——把"全民导演时代 LTX2.3 全流程导演台"工作流通过 RunningHub HTTP API 跑起来。整套功能拆为 4 段：

- A · **RunningHub API 客户端 + LTX 提交器**（本文档，纯库）
- B · 视频生成面板（UI，依赖 A）
- C · 提示词智能优化（轨道段右键反推，复用现有 inference 链路）
- D · 多任务并行（YAGNI，暂不做）

A 是所有上层的地基，必须独立可测、零 UI 依赖。

### 1.2 目标

提供一组类与函数，使调用方能用以下 6 行代码完成"一次完整提交"：

```python
client = RunningHubClient(api_key)
builder = LTXTaskBuilder(template_path)
spec = LTXDirectorSpec(segments=(...), global_prompt="...", ...)
handle = submit_ltx_task(client, spec, builder, mode="inline")
mp4_path = handle.wait_for_result()
```

### 1.3 非目标

- 不做 UI（B 子项目的事）
- 不做提示词反推集成（C 的事）
- 不做多任务调度（D 的事）
- 不内嵌 webhook 接收服务器（默认轮询；webhook URL 仅作为 spec 字段透传给 RunningHub）
- 不做积分预算/扣费校验（依赖 RunningHub 端拒绝即可）
- 不做任务历史持久化（每次提交独立）

---

## 2. 需求决策记录

| # | 决策点 | 结果 |
|---|---|---|
| 1 | 分支策略 | 先合并 feat/split-resample 到 main，新分支 `feat/video-gen` 从 main 起步 |
| 2 | 子项目拆分 | A/B/C 走，D 暂不做 |
| 3 | API 鉴权 | `Authorization: Bearer <apiKey>` + body 里同步塞 `apiKey`（按文档要求） |
| 4 | 工作流提交模式 | **两者都支持**：默认 `inline`（嵌入完整 workflow JSON），可切到 `id`（workflowId + nodeInfoList）；模式由 settings.json 字段控制 |
| 5 | 任务进度 | 轮询 V2 接口 `POST /openapi/v2/query`，8 秒一次 |
| 6 | 文件上传时机 | 提交任务那一刻一次性批上传未上传过的资源；handle 暴露 progress_cb |
| 7 | 结果落盘位置 | 由 spec.output_dir 决定；B 层从 settings.video_output_dir 注入 |
| 8 | API key 存储 | `.env: RUNNINGHUB_API_KEY` + `settings.json: runninghub_api_key` 可覆盖 |
| 9 | LTX 工作流模板 | 拷贝到项目 `app/templates/ltx_director_v23.json`，进 git |
| 10 | 实现方案 | A2：分层 `RunningHubClient` / `LTXDirectorSpec` / `LTXTaskBuilder` + 顶层 `submit_ltx_task` |

---

## 3. 架构

### 3.1 改动文件清单

```
app/
├── providers/
│   └── runninghub.py                # 新增（含 client / spec / builder / submit / handle 五件套）
├── templates/                       # 新增目录
│   └── ltx_director_v23.json        # 新增（拷自工作流原 JSON，进 git）
└── config.py                        # 修改（加 6 字段 + .env / settings 读写）
.env.example                         # 修改（加 RUNNINGHUB_API_KEY / RUNNINGHUB_BASE_URL）
docs/superpowers/specs/
└── 2026-05-24-runninghub-api-design.md  # 本文档
tests/test_providers/
├── test_runninghub_client.py        # 新增（mock httpx）
├── test_ltx_task_builder.py         # 新增（纯函数）
└── test_runninghub_submit.py        # 新增（mock client）
```

### 3.2 组件职责切片

1. **`RunningHubClient`** — 裸 HTTP 客户端：上传 / 提交 / 查任务 / 下载 / 取消 5 个 method。不懂 LTX 工作流细节，可复用于未来其他 RunningHub 工作流。
2. **`LTXDirectorSpec`** — `frozen` dataclass，描述一次视频生成请求的全部用户态参数。零依赖，纯数据契约。
3. **`LTXTaskBuilder`** — 唯一懂 LTX 工作流细节的单元：`(spec, uploaded_files) → workflow dict` 或 `→ nodeInfoList`。两种 build 路径共享一份"LTXDirector 入参生成"逻辑，消除漂移。
4. **`submit_ltx_task(client, spec, builder, *, mode, ...) → LTXTaskHandle`** — 顶层胶水：扫描 spec 找未上传文件 → 批量调 `client.upload_file` → 调 builder → 调 `client.create_task` → 返回 handle。
5. **`LTXTaskHandle`** — 任务句柄：`.status()` / `.wait_for_result(timeout, poll_interval, progress_cb, cancel_check)` / `.cancel()`。
6. **异常族**：`RunningHubUnavailable` / `RunningHubTaskFailed` / `RunningHubUploadError` / `RunningHubInvalidSpec`。

### 3.3 调用链

```
[B 层 UI] submit clicked
    ↓
client = RunningHubClient(resolve_api_key(cfg))
builder = LTXTaskBuilder(resolve_template_path(cfg))   ← 启动时构造一次，多任务复用
spec = LTXDirectorSpec(...)                            ← 从 UI 状态构建
handle = submit_ltx_task(client, spec, builder, mode=cfg.runninghub_submit_mode,
                         webhook_url=None,
                         upload_progress_cb=lambda d,t,p: status.emit(f"上传 {d}/{t}: {p.name}"))
    ↓ 内部：
    files = spec.unique_local_files()
    uploaded = {p: client.upload_file(p) for p in files}
    if mode == "inline":
        workflow = builder.build_inline_workflow(spec, uploaded)
        task_id = client.create_task(workflow=workflow, webhook_url=...)
    else:
        items = builder.build_node_info_list(spec, uploaded)
        task_id = client.create_task(workflow_id=cfg.runninghub_workflow_id,
                                     node_info_list=items, webhook_url=...)
    ↓
mp4_path = handle.wait_for_result(
    timeout=1800, poll_interval=8,
    progress_cb=lambda s: status.emit(f"任务状态: {s}"),
    cancel_check=lambda: ui_cancel_flag,
)
```

---

## 4. 数据模型

### 4.1 dataclasses

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SegmentType = Literal["image", "text"]

@dataclass(frozen=True)
class LTXSegment:
    local_prompt: str
    length: int                         # 帧数（display_mode=frames）或秒×fps 后的整数
    image_path: Path | None = None
    segment_type: SegmentType = "image"
    guide_strength: float = 1.0
    seg_id: str = ""                    # 空 → builder 兜底生成


@dataclass(frozen=True)
class LTXAudioSegment:
    audio_path: Path
    start_frame: int
    length_frames: int


@dataclass(frozen=True)
class LTXDirectorSpec:
    global_prompt: str = ""
    use_global_prompt: bool = True
    segments: tuple[LTXSegment, ...] = ()
    audio_segments: tuple[LTXAudioSegment, ...] = ()
    use_custom_audio: bool = False
    display_mode: Literal["seconds", "frames"] = "seconds"
    frame_rate: int = 24
    resolution_preset: str = "1280x720 (16:9) (横屏)"
    use_custom_resolution: bool = False
    custom_width: int = 1024
    custom_height: int = 1024
    noise_seed: int | None = None
    filename_prefix: str = "spb_video"
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    epsilon: float = 0.5

    def total_length_frames(self) -> int:
        return sum(s.length for s in self.segments)

    def total_length_seconds(self) -> float:
        return self.total_length_frames() / self.frame_rate

    def unique_local_files(self) -> tuple[Path, ...]:
        seen, result = set(), []
        for s in self.segments:
            if s.image_path and s.image_path not in seen:
                seen.add(s.image_path); result.append(s.image_path)
        for a in self.audio_segments:
            if a.audio_path not in seen:
                seen.add(a.audio_path); result.append(a.audio_path)
        return tuple(result)
```

### 4.2 `Config` 扩展（`app/config.py`）

```python
@dataclass
class Config:
    # ... 现有字段
    runninghub_api_key: str = ""
    runninghub_workflow_id: str = ""
    runninghub_submit_mode: str = "inline"      # "inline" 或 "id"
    runninghub_base_url: str = "https://www.runninghub.cn"
    runninghub_template_path: str = ""          # 空 = 用内置
    video_output_dir: str = ""                  # 空 = 用 state.output_dir
```

### 4.3 `.env.example` 追加

```env
# RunningHub
RUNNINGHUB_API_KEY=
RUNNINGHUB_BASE_URL=https://www.runninghub.cn
```

### 4.4 `settings.json` 新增字段

```jsonc
{
  // ... 现有字段
  "runninghub_api_key": "",
  "runninghub_workflow_id": "",
  "runninghub_submit_mode": "inline",
  "runninghub_base_url": "https://www.runninghub.cn",
  "runninghub_template_path": "",
  "video_output_dir": ""
}
```

> 优先级：`settings.json` > `.env`。理由：UI 修改 key 后立即生效，不被 .env 反着覆盖。

---

## 5. `RunningHubClient`（裸 HTTP 层）

```python
class RunningHubClient:
    def __init__(self, api_key: str,
                 base_url: str = "https://www.runninghub.cn",
                 request_timeout: float = 30.0):
        if not api_key:
            raise RunningHubUnavailable("RUNNINGHUB_API_KEY 未设置")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=request_timeout)

    def upload_file(self, path: Path) -> str:
        """POST /openapi/v2/media/upload/binary; 返回 RunningHub fileName。"""

    def create_task(self, *, workflow: dict | None = None,
                    workflow_id: str | None = None,
                    node_info_list: list[dict] | None = None,
                    webhook_url: str | None = None,
                    add_metadata: bool = True) -> str:
        """POST /task/openapi/create; workflow 与 workflow_id 二选一; 返回 taskId。"""

    def query_task(self, task_id: str) -> dict:
        """POST /openapi/v2/query; 返回 {status, results, errorCode, errorMessage, ...}。
        V2 返回 dict；为兼容 legacy /status 接口，data 是字符串时退化封装。"""

    def download_file(self, url: str, dest: Path) -> Path:
        """流式 GET; 自动 mkdir parent; 返回 dest。"""

    def cancel_task(self, task_id: str) -> None:
        """POST /task/openapi/cancel; best-effort, 失败静默。"""

    def close(self) -> None: ...
    def __enter__(self) -> "RunningHubClient": ...
    def __exit__(self, *exc) -> None: ...
```

### 5.1 错误分类策略

错误归类**按 endpoint 分**，而非按 HTTP 状态码统一规则：

| Endpoint | 连接错误（ConnectError / Timeout） | HTTP 4xx/5xx | 业务 `code != 0` |
|---|---|---|---|
| `upload_file` | `RunningHubUnavailable` | `RunningHubUploadError`（含状态码） | `RunningHubUploadError` |
| `create_task` | `RunningHubUnavailable` | `RunningHubTaskFailed`（含状态码 + body 片段） | `RunningHubTaskFailed`（含 `promptTips`） |
| `query_task` | `RunningHubUnavailable` | `RunningHubUnavailable` | `RunningHubUnavailable` |
| `download_file` | `RunningHubUnavailable` | `RunningHubUnavailable` | — |
| `cancel_task` | 静默吞错 | 静默吞错 | — |

**理由：** `upload` 和 `create_task` 的 HTTP 4xx/5xx 多半是业务原因（文件超大 / 积分不足 / nodeInfoList 不合法），分类成"上传/任务"错误更符合调用方决策（弹"任务失败"而非"网络问题"）。`query_task` 和 `download_file` 是只读探测，任何失败都视为暂时不可达，方便 wait_for_result 层做重试。

### 5.2 鉴权双塞策略

`apiKey` 同时塞 header (`Authorization: Bearer <key>`) 与 body (`{"apiKey": ...}`)。理由：文档示例显示某些端点要求 body 里也有 `apiKey`；双塞最安全。

### 5.3 `query_task` 兼容两种响应形状

V2 返回 `data: {status, results, ...}` (dict)；legacy 返回 `data: "SUCCESS"` (string)。客户端层兼容：字符串时退化为 `{status: <string>, results: None, errorCode: "", errorMessage: ""}`。

### 5.4 `cancel_task` 不抛错

任务可能已完成或已取消，cancel 是 best-effort，吞所有 httpx.HTTPError。

---

## 6. `LTXTaskBuilder`（spec → 工作流翻译）

### 6.1 节点 id 常量

```python
class LTXNodes:
    DIRECTOR = "46"             # LTXDirector
    SAVE_VIDEO = "104"          # SaveVideo
    NOISE = "132"               # RandomNoise
    RESOLUTION = "139"          # TTResolutionSelector
```

### 6.2 公共构建 API

```python
class LTXTaskBuilder:
    def __init__(self, template_path: Path):
        """启动时一次性加载 + 校验关键节点存在。"""

    def build_inline_workflow(self, spec, uploaded_files) -> dict:
        """deepcopy 模板 → 更新节点 46/104/132/139 → 返回完整 workflow dict。"""

    def build_node_info_list(self, spec, uploaded_files) -> list[dict]:
        """仅生成 [{nodeId, fieldName, fieldValue}, ...]，给 ID 模式用。"""
```

### 6.3 单一真值源 `_compute_director_params`

两种 build 模式都从这一个函数拿 LTXDirector 11 个入参的 dict，inline 模式 update 进 `wf["46"].inputs`，ID 模式拆成 nodeInfoList。**消除"两边逻辑漂移"的风险**。

涵盖字段：`global_prompt / duration_frames / duration_seconds / timeline_data / local_prompts / segment_lengths / use_custom_audio / frame_rate / display_mode / guide_strength / epsilon`。

### 6.4 `timeline_data` 形状（严格对齐原 dump）

```json
{
  "segments": [
    {"id": "...", "start": 0, "length": 33, "prompt": "...",
     "type": "image", "imageFile": "abc.png",
     "imageB64": "/view?filename=abc.png&type=input&subfolder="},
    ...
  ],
  "audioSegments": []
}
```

- `start` 是累积帧数（前面所有 seg.length 之和）
- `imageB64` 字段名虽含 "B64"，原 JSON 实际放 `/view?...` URL，沿用
- `imageFile` 取 RunningHub fileName 的 basename
- `audioSegments` 空数组当 `use_custom_audio=False`

### 6.5 字符串字段拼接格式

| 字段 | 格式 | 例子 |
|---|---|---|
| `local_prompts` | `" \| "` 分隔（**带空格**） | `"prompt1 \| prompt2 \| prompt3"` |
| `segment_lengths` | `","` 分隔（无空格） | `"33,33,30"` |
| `guide_strength` | `","` 分隔，两位小数 | `"1.00,1.00,1.00"` |

### 6.6 `_DIRECTOR_FIELDS` 白名单（ID 模式专用）

```python
_DIRECTOR_FIELDS = (
    "global_prompt", "duration_frames", "duration_seconds",
    "timeline_data", "local_prompts", "segment_lengths",
    "use_custom_audio", "frame_rate", "display_mode",
    "guide_strength", "epsilon",
)
```

模板里 LTXDirector 还有 `model/clip/audio_vae/timeline_ui/custom_width/custom_height/resize_method/divisible_by/img_compression` 等节点连线/常量字段——这些**不应**被 nodeInfoList 改（会断图），从白名单排除。

### 6.7 `noise_seed` 处理

- `spec.noise_seed is None` → 不修改节点 132，保持模板默认（固定种子，保证可复现）
- 不为 None → 覆盖

### 6.8 分辨率字段

- `use_custom_resolution=False` → 改节点 139 `resolution` preset
- `True` → 改 `use_custom_resolution=True` + `custom_width` + `custom_height` 三字段

### 6.9 `seg_id` 兜底

```python
def _gen_seg_id() -> str:
    """模仿原 JSON 格式：13 位毫秒戳 + 5 位 hex 随机。"""
    ts = int(time.time() * 1000)
    rnd = secrets.token_hex(3)[:5]
    return f"{ts}{rnd}"
```

UI 传了稳定 id 就用，否则生成；保证下次同段不会"看起来变了"。

### 6.10 校验规则（在 `_validate` 里）

- `len(spec.segments) >= 1`
- `1 <= spec.frame_rate <= 120`
- 每段 `length >= 1` 且 `0.0 <= guide_strength <= 1.0`
- `seg.image_path is not None` 时 `image_path in uploaded_files`
- `use_custom_audio=True` 时所有 audio_path 都在 uploaded_files 中

校验失败抛 `RunningHubInvalidSpec`。

---

## 7. 顶层 `submit_ltx_task` + `LTXTaskHandle`

### 7.1 `submit_ltx_task` 签名

```python
def submit_ltx_task(client: RunningHubClient,
                    spec: LTXDirectorSpec,
                    builder: LTXTaskBuilder,
                    *,
                    mode: str = "inline",
                    workflow_id: str = "",
                    webhook_url: Optional[str] = None,
                    upload_progress_cb: Optional[Callable[[int, int, Path], None]] = None,
                    ) -> "LTXTaskHandle":
```

校验：`mode ∈ {"inline","id"}`；`mode="id"` 必须有 `workflow_id`。两种校验失败抛 `RunningHubInvalidSpec`。

### 7.2 `LTXTaskHandle`

```python
class LTXTaskHandle:
    TERMINAL = {"SUCCESS", "FAILED"}

    def status(self) -> str:
        """单次拉取状态。"""

    def wait_for_result(self, timeout: float = 1800.0,
                        poll_interval: float = 8.0,
                        progress_cb: Optional[Callable[[str], None]] = None,
                        cancel_check: Optional[Callable[[], bool]] = None,
                        ) -> Path:
        """阻塞轮询；SUCCESS 时下载 MP4 到 spec.output_dir 并返回路径。"""

    def cancel(self) -> None:
        """主动取消。"""
```

### 7.3 轮询语义

- **超时**：默认 1800s（30 分钟）。超时 → 调 `client.cancel_task` + 抛 `RunningHubTaskFailed("timeout")`
- **网络抖动**：轮询期间 `query_task` 抛 `RunningHubUnavailable` 时**重试 2 次**（共 3 次），仍失败才抛
- **创建阶段不重试**：`submit_ltx_task` 里的 upload + create_task 失败直接抛，业务错该 fail-fast
- **取消检查**：每次轮询前调 `cancel_check()` 若返 True → cancel_task + 抛 `RunningHubTaskFailed("cancelled")`
- **状态去重**：状态没变化时不调 progress_cb；变化时调一次

### 7.4 结果下载

`SUCCESS` 时取 `data["results"][0]`：
- `url` → 必须存在；否则抛 `RunningHubTaskFailed("results[0] 无 url")`
- `outputType` → 决定文件扩展名，默认 `"mp4"`
- 目标路径：`spec.output_dir / f"{spec.filename_prefix}_{task_id}.{ext}"`

如 `results == []` 抛 `RunningHubTaskFailed("SUCCESS 但 results 为空")`。

### 7.5 任务-client 生命周期

`LTXTaskHandle` 持有 client 引用但**不负责关闭** client。调用方约定：B 层 panel 在 `__del__` / 关闭时调 `client.close()`。与 split-resample 项目里 ComfyUIUpscaler 同语义。

### 7.6 失败/取消的"上传文件清理"

故意不做。RunningHub 自己管 input 存储期（通常 24h 内清理）。客户端不主动 cleanup。YAGNI。

---

## 8. 配置加载与路径解析

### 8.1 `load_config` 改动

```python
    # .env
    if env.get("RUNNINGHUB_API_KEY"):
        cfg.runninghub_api_key = env["RUNNINGHUB_API_KEY"]
    if env.get("RUNNINGHUB_BASE_URL"):
        cfg.runninghub_base_url = env["RUNNINGHUB_BASE_URL"]

    # settings.json（在 split_resample_defaults 读取之后）
    for key in ("runninghub_api_key", "runninghub_workflow_id",
                "runninghub_submit_mode", "runninghub_base_url",
                "runninghub_template_path", "video_output_dir"):
        if key in data and isinstance(data[key], str):
            setattr(cfg, key, data[key])
```

### 8.2 `update_settings` 落盘白名单

加 6 个新 key。

### 8.3 三个辅助函数（在 `runninghub.py`）

```python
def resolve_api_key(cfg) -> str:
    """settings.json > .env > 报错。"""

def resolve_template_path(cfg) -> Path:
    """settings.json 自定义 > 内置 app/templates/ltx_director_v23.json > 报错。"""

def resolve_video_output_dir(cfg, state_output_dir: Path | None) -> Path:
    """settings.video_output_dir > state.output_dir > 报错。"""
```

### 8.4 模板文件来源

- 源：`E:\Rui\笔记\AIEngineer\AIEngineer\漫剧\01-Workflow配置\07-comfyui\全民导演时代！LTX2.3全流程导演台！_api.json`
- 目标：`app/templates/ltx_director_v23.json`
- **进 git**（10KB，保证团队/不同机器无外部依赖）

---

## 9. 测试策略

3 个测试文件，无网络/无外部依赖（用 tmp_path + httpx.MockTransport）。

### 9.1 `tests/test_providers/test_runninghub_client.py`

约 20 个用例，覆盖：
- 鉴权失败 / base_url 规范化 / 上下文管理
- upload_file：happy / 文件不存在 / 4xx → UploadError / 连接失败 → Unavailable / 业务 code≠0 → UploadError
- create_task：inline / id+nodeInfoList / 两路都不传 / webhook / 5xx → TaskFailed / 业务错含 promptTips → TaskFailed
- query_task：V2 dict 形状 / legacy string 形状 / 连接失败 → Unavailable / 5xx → Unavailable
- download_file：流式落盘 / 404 → Unavailable
- cancel_task：静默吞错

### 9.2 `tests/test_providers/test_ltx_task_builder.py`

约 25 个用例，覆盖：
- 模板加载与校验（缺关键节点抛错）
- inline 模式：所有 11 个 Director 字段 / 其他节点不变 / timeline_data JSON 结构 / 累积 start / 字符串分隔格式 / global 禁用 / 时长一致 / 音频开关 / filename_prefix / noise_seed None vs 整数 / preset vs custom 分辨率
- nodeInfoList 模式：含全部 Director 字段 / 排除连线字段 / filename_prefix 节点 / 分辨率两路
- 校验：空段 / length<1 / 缺上传 / guide_strength 越界 / frame_rate 越界 / 缺音频上传
- seg_id：空时生成、提供时保留

**Fixture 用真实模板**而非合成模板，保证模板结构变更被捕获。

### 9.3 `tests/test_providers/test_runninghub_submit.py`

约 18 个用例，覆盖：
- submit：mode 校验 / id 模式要求 workflow_id / 上传去重 / inline vs id payload / webhook 透传 / 上传 progress_cb / handle.task_id
- handle.status() 透传
- wait_for_result：
  - SUCCESS 路径下载 MP4，文件名 `{prefix}_{task_id}.{ext}`
  - FAILED → 抛错含 errorMessage
  - timeout → cancel_task 被调 + 抛错
  - progress_cb 状态去重（仅变化时调）
  - cancel_check 中断流程 + cancel_task 被调
  - 网络抖动单次容忍，连续 3 次失败抛错
  - SUCCESS 但 results 空 → 抛错
  - outputType 决定扩展名

**测试加速**：`monkeypatch.setattr("app.providers.runninghub.time.sleep", lambda _: None)`。

### 9.4 不重复测试

- httpx multipart 内部
- json.dumps / Path.mkdir
- secrets.token_hex 随机性
- 现有 Config 持久化模式（split-resample Task 9 已覆盖通用通路；只在端到端层加一个 "RUNNINGHUB_API_KEY 优先级" 用例）

### 9.5 总计

约 60 个用例，3 个文件，约 700-900 行测试代码。

---

## 10. 错误处理矩阵

| 错误类别 | 行为 | 例子 |
|---|---|---|
| `RunningHubUnavailable` | 抛给调用方；B 层弹"网络/RunningHub 不可达"窗 | ConnectError / 5xx |
| `RunningHubUploadError` | 抛给调用方；B 层弹"上传失败"窗 | 4xx / 文件不存在 / code≠0 |
| `RunningHubTaskFailed` | 抛给调用方；B 层弹"任务失败"窗（含 errorMessage / promptTips） | create_task code≠0 / FAILED 状态 / timeout / cancelled |
| `RunningHubInvalidSpec` | 抛给调用方；B 层 validate 应在 submit 前先做、避免到这一层 | mode 错 / segments=[] / 缺上传文件 |
| 任意未捕获异常 | 不吞，原样抛出（B 层 worker 捕获） | bug |

---

## 11. 验收标准

A 子项目完成的标志：

- [ ] `app/providers/runninghub.py` 内含 5 个核心单元 + 4 个异常类 + 3 个辅助函数
- [ ] `app/templates/ltx_director_v23.json` 进 git
- [ ] `app/config.py` 含 6 个新字段，read + write 路径打通
- [ ] `.env.example` 含 RUNNINGHUB_API_KEY / RUNNINGHUB_BASE_URL
- [ ] 60 个测试全过（mock httpx，纯函数 builder，mock client submit）
- [ ] 与一个真实 RunningHub 账号跑通**最小端到端**（手工冒烟，1 段图片，inline 模式）

---

## 12. 风险与开放问题

| 风险 | 影响 | 应对 |
|---|---|---|
| RunningHub API 在新版本破坏性升级 | client 层全断 | 异常分类清晰，UI 能识别"Unavailable"快速降级；测试用真实模板 fixture 捕获 schema 漂移 |
| LTX 工作流模板节点 id 变化 | builder 失效 | `LTXNodes` 常量集中维护；init 时校验节点存在 fail-fast |
| RunningHub 积分用完 / 限频 | 任务失败 | 客户端按错误码原样透传 errorMessage，由用户判断 |
| 大量上传文件（>20MB 单图）耗时长 | 用户感知卡顿 | upload_progress_cb 给 UI 透出进度 |
| 网络长时间间断 | wait_for_result 提前抛错 | 3 次 retry 容忍短抖动；30 分钟 timeout 保底 |
| Spec 的 `timeline_data` JSON 字段名 / 字段格式与 RunningHub 平台版有偏差 | LTXDirector 节点解析失败 | 严格对齐原 dump 格式（一份样本是从该项目作者实际跑通的工作流导出的），实现期需手工冒烟一遍验证 |

**开放问题（v0.7+）：**

- 是否支持 webhook 模式（在本地起 HTTP 服务器接收回调，免轮询）？
- 是否支持多输出文件（一次提交出多个版本）？
- 是否暴露 noise_seed 随机化 UI（"再来一张"按钮）？
- 是否做积分预估 endpoint 的预扣校验？

---

## 13. 下一步

1. 用户复核本设计文档
2. 通过后调用 `superpowers:writing-plans` 生成实现计划
3. 实现计划按 milestone 切分 → 编码 → 测试 → 集成
4. A 完成后，B 子项目（视频生成面板 UI）启动 brainstorming

---

**文档负责人**：项目作者
**最近更新**：2026-05-24
