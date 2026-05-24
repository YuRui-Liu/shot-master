# RunningHub API 客户端 + LTX 提交器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现视频生成模块的地基库——RunningHub HTTP 客户端 + LTX 工作流提交器（纯 Python 库，零 UI）。

**Architecture:** 5 个单元集中在 `app/providers/runninghub.py`：`RunningHubClient`（裸 HTTP）+ `LTXDirectorSpec`（frozen dataclass）+ `LTXTaskBuilder`（spec→工作流翻译）+ 顶层 `submit_ltx_task` 编排 + `LTXTaskHandle`（轮询/下载）。LTX 工作流模板 JSON 入仓到 `app/templates/`。配置扩展走 `Config` + `.env` + `settings.json` 三通道。

**Tech Stack:** Python 3.10+, httpx ≥ 0.27（已在依赖），json/copy/secrets/time 标准库；测试用 pytest + httpx.MockTransport + unittest.mock。

**Spec:** `docs/superpowers/specs/2026-05-24-runninghub-api-design.md`

---

## File Structure

新增 / 修改文件清单：

| 文件 | 操作 | 职责 |
|---|---|---|
| `app/templates/ltx_director_v23.json` | 新增 | LTX 工作流模板（拷自源 JSON，进 git） |
| `app/providers/runninghub.py` | 新增 | RunningHubClient + LTXDirectorSpec + LTXTaskBuilder + submit_ltx_task + LTXTaskHandle + 4 个异常类 + 3 个 resolve_ 函数 |
| `app/config.py` | 修改 | 加 6 字段 + .env 读 + settings 读写白名单 |
| `.env.example` | 修改 | 末尾追加 RUNNINGHUB_API_KEY 行 |
| `tests/test_providers/test_runninghub_client.py` | 新增 | mock httpx 测 5 endpoint + 异常 |
| `tests/test_providers/test_ltx_task_builder.py` | 新增 | 纯函数测 builder + dataclasses |
| `tests/test_providers/test_runninghub_submit.py` | 新增 | mock client 测 submit + handle 轮询 |
| `tests/test_config.py` | 修改 | 加 RunningHub 字段持久化用例 |

---

## Task 1: 模板文件入仓 + 基础异常类

**Files:**
- Create: `app/templates/ltx_director_v23.json`（拷贝二进制）
- Create: `app/providers/runninghub.py`（仅含 4 个异常类）
- Create: `tests/test_providers/test_runninghub_client.py`（仅含模板/异常类导入冒烟）

- [ ] **Step 1: 创建模板目录并拷贝 JSON**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
mkdir -p app/templates
cp "/mnt/e/Rui/笔记/AIEngineer/AIEngineer/漫剧/01-Workflow配置/07-comfyui/全民导演时代！LTX2.3全流程导演台！_api.json" app/templates/ltx_director_v23.json
ls -la app/templates/ltx_director_v23.json
```

Expected: 文件存在，大小约 11KB。

- [ ] **Step 2: 验证模板可被 JSON 解析且含关键节点**

```bash
python3 -c "
import json
from pathlib import Path
with open('app/templates/ltx_director_v23.json', encoding='utf-8') as f:
    wf = json.load(f)
for nid in ('46', '104', '132', '139'):
    assert nid in wf, f'node {nid} missing'
print(f'OK: {len(wf)} nodes, key nodes present')
"
```

Expected: `OK: 24 nodes, key nodes present`

- [ ] **Step 3: 写 failing test 验证异常类可导入**

新建 `tests/test_providers/test_runninghub_client.py`：

```python
"""RunningHubClient 单测（mock httpx）。"""
from __future__ import annotations

import pytest

from app.providers.runninghub import (
    RunningHubUnavailable, RunningHubTaskFailed,
    RunningHubUploadError, RunningHubInvalidSpec,
)


def test_exception_classes_are_distinct():
    assert issubclass(RunningHubUnavailable, Exception)
    assert issubclass(RunningHubTaskFailed, Exception)
    assert issubclass(RunningHubUploadError, Exception)
    assert issubclass(RunningHubInvalidSpec, Exception)
    # 都是独立类，互不继承
    for a, b in [
        (RunningHubUnavailable, RunningHubTaskFailed),
        (RunningHubUploadError, RunningHubTaskFailed),
        (RunningHubInvalidSpec, RunningHubUnavailable),
    ]:
        assert not issubclass(a, b) and not issubclass(b, a)
```

- [ ] **Step 4: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_runninghub_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.providers.runninghub'`

- [ ] **Step 5: 新建 `app/providers/runninghub.py` 含 4 个异常类**

```python
"""RunningHub HTTP API 客户端 + LTX 工作流提交器。

独立于 vision providers 与 ComfyUIUpscaler——RunningHub 是远端 SaaS，
封装 5 个 endpoint（upload / create / query / download / cancel），
顶层 submit_ltx_task 串成"提交→轮询→下载"。
"""
from __future__ import annotations


class RunningHubUnavailable(Exception):
    """连接失败 / 服务不可达 / 鉴权缺失。调用方可重试或降级。"""


class RunningHubTaskFailed(Exception):
    """任务执行失败（业务错 / FAILED 状态 / 超时 / 取消）。"""


class RunningHubUploadError(Exception):
    """文件上传失败（本地文件不存在 / 上传 HTTP 错 / 上传业务错）。"""


class RunningHubInvalidSpec(Exception):
    """LTXDirectorSpec 校验失败 / submit 入参非法。"""
```

- [ ] **Step 6: 运行验证 PASS**

```bash
pytest tests/test_providers/test_runninghub_client.py -v
```

Expected: 1 passed

- [ ] **Step 7: Commit**

```bash
git add app/templates/ltx_director_v23.json app/providers/runninghub.py tests/test_providers/test_runninghub_client.py
git commit -m "feat(runninghub): scaffold module with template JSON and exceptions"
```

---

## Task 2: 数据模型 `LTXSegment` / `LTXAudioSegment` / `LTXDirectorSpec`

**Files:**
- Modify: `app/providers/runninghub.py`（追加 3 个 dataclass）
- Create: `tests/test_providers/test_ltx_task_builder.py`（dataclass 部分用例）

- [ ] **Step 1: 写 failing tests**

新建 `tests/test_providers/test_ltx_task_builder.py`：

```python
"""LTXDirectorSpec / LTXSegment / LTXTaskBuilder 单测。"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.providers.runninghub import (
    LTXSegment, LTXAudioSegment, LTXDirectorSpec,
    RunningHubInvalidSpec,
)


# ---------- Dataclass 基础行为 ----------

def test_ltx_segment_defaults():
    s = LTXSegment(local_prompt="p", length=24)
    assert s.local_prompt == "p"
    assert s.length == 24
    assert s.image_path is None
    assert s.segment_type == "image"
    assert s.guide_strength == 1.0
    assert s.seg_id == ""


def test_ltx_segment_is_frozen():
    s = LTXSegment(local_prompt="p", length=24)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.length = 48


def test_ltx_audio_segment_basic():
    a = LTXAudioSegment(audio_path=Path("/x.mp3"),
                          start_frame=0, length_frames=96)
    assert a.audio_path == Path("/x.mp3")
    assert a.start_frame == 0
    assert a.length_frames == 96


def test_ltx_director_spec_defaults():
    spec = LTXDirectorSpec()
    assert spec.global_prompt == ""
    assert spec.use_global_prompt is True
    assert spec.segments == ()
    assert spec.audio_segments == ()
    assert spec.use_custom_audio is False
    assert spec.display_mode == "seconds"
    assert spec.frame_rate == 24
    assert spec.resolution_preset == "1280x720 (16:9) (横屏)"
    assert spec.use_custom_resolution is False
    assert spec.custom_width == 1024
    assert spec.custom_height == 1024
    assert spec.noise_seed is None
    assert spec.filename_prefix == "spb_video"
    assert spec.output_dir == Path("./output")
    assert spec.epsilon == 0.5


def test_ltx_director_spec_is_frozen():
    spec = LTXDirectorSpec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.frame_rate = 30


def test_total_length_frames():
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=33),
        LTXSegment(local_prompt="b", length=33),
        LTXSegment(local_prompt="c", length=30),
    ))
    assert spec.total_length_frames() == 96


def test_total_length_seconds_uses_frame_rate():
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=96),),
        frame_rate=24,
    )
    assert spec.total_length_seconds() == 4.0


def test_unique_local_files_deduplicates_images():
    p1 = Path("/img1.png")
    p2 = Path("/img2.png")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=p1),
        LTXSegment(local_prompt="b", length=10, image_path=p1),  # 重复
        LTXSegment(local_prompt="c", length=10, image_path=p2),
        LTXSegment(local_prompt="d", length=10, image_path=None),  # 跳过
    ))
    assert spec.unique_local_files() == (p1, p2)


def test_unique_local_files_includes_audio_paths():
    img = Path("/img.png")
    aud = Path("/aud.mp3")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                         length_frames=10),),
    )
    assert set(spec.unique_local_files()) == {img, aud}


def test_unique_local_files_empty_when_all_text_segments():
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=None),
    ))
    assert spec.unique_local_files() == ()
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_ltx_task_builder.py -v
```

Expected: `ImportError: cannot import name 'LTXSegment'`

- [ ] **Step 3: 在 `app/providers/runninghub.py` 末尾追加 dataclasses**

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


SegmentType = Literal["image", "text"]


@dataclass(frozen=True)
class LTXSegment:
    """时间轴上的一段画面：本地图片 + 本段 prompt + 本段时长。"""
    local_prompt: str
    length: int                          # 帧数
    image_path: Path | None = None       # None 表示纯文本段（占时长不占图）
    segment_type: SegmentType = "image"
    guide_strength: float = 1.0          # 0.0~1.0
    seg_id: str = ""                     # 空 → builder 兜底生成


@dataclass(frozen=True)
class LTXAudioSegment:
    """时间轴上的一段音频。"""
    audio_path: Path
    start_frame: int
    length_frames: int


@dataclass(frozen=True)
class LTXDirectorSpec:
    """一次 LTX 视频生成提交的完整用户态参数。

    字段语义与 LTXDirector 节点 (id=46) 的 inputs 对齐。
    """
    # 提示词
    global_prompt: str = ""
    use_global_prompt: bool = True

    # 时间轴
    segments: tuple[LTXSegment, ...] = ()
    audio_segments: tuple[LTXAudioSegment, ...] = ()
    use_custom_audio: bool = False

    # 时长 / 帧率
    display_mode: Literal["seconds", "frames"] = "seconds"
    frame_rate: int = 24

    # 分辨率
    resolution_preset: str = "1280x720 (16:9) (横屏)"
    use_custom_resolution: bool = False
    custom_width: int = 1024
    custom_height: int = 1024

    # 采样
    noise_seed: int | None = None        # None = 用模板默认（固定种子）

    # 输出
    filename_prefix: str = "spb_video"
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    # 其他可调
    epsilon: float = 0.5

    def total_length_frames(self) -> int:
        return sum(s.length for s in self.segments)

    def total_length_seconds(self) -> float:
        return self.total_length_frames() / self.frame_rate

    def unique_local_files(self) -> tuple[Path, ...]:
        """所有需要上传的本地资源路径（去重保序）。"""
        seen: set[Path] = set()
        result: list[Path] = []
        for s in self.segments:
            if s.image_path and s.image_path not in seen:
                seen.add(s.image_path)
                result.append(s.image_path)
        for a in self.audio_segments:
            if a.audio_path not in seen:
                seen.add(a.audio_path)
                result.append(a.audio_path)
        return tuple(result)
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_ltx_task_builder.py -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_ltx_task_builder.py
git commit -m "feat(runninghub): add LTXSegment / LTXAudioSegment / LTXDirectorSpec dataclasses"
```

---

## Task 3: `RunningHubClient` init + `upload_file`

**Files:**
- Modify: `app/providers/runninghub.py`（追加 RunningHubClient 类 + _guess_mime）
- Modify: `tests/test_providers/test_runninghub_client.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_providers/test_runninghub_client.py` 顶部 import 区追加：

```python
from pathlib import Path
import httpx

from app.providers.runninghub import RunningHubClient
```

文件末尾追加：

```python
# ---------- init / 基础 ----------

def test_init_rejects_empty_api_key():
    with pytest.raises(RunningHubUnavailable):
        RunningHubClient("")


def test_init_strips_base_url_trailing_slash():
    c = RunningHubClient("k", base_url="https://x.com/")
    assert c.base_url == "https://x.com"


def test_init_default_base_url():
    c = RunningHubClient("k")
    assert c.base_url == "https://www.runninghub.cn"


# ---------- upload_file ----------

def _png_bytes() -> bytes:
    # 1x1 PNG
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90"
            b"wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
            b"\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82")


def _set_mock_transport(client: RunningHubClient, handler):
    """把 RunningHubClient._client 换成 MockTransport 客户端。"""
    client._client = httpx.Client(transport=httpx.MockTransport(handler))


def test_upload_file_happy_path(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = req.read()
        return httpx.Response(200, json={
            "code": 0, "message": "success",
            "data": {"type": "image",
                     "download_url": "https://x/a.png",
                     "fileName": "openapi/abc.png",
                     "size": "1234"},
        })

    c = RunningHubClient("test-key")
    _set_mock_transport(c, handler)
    name = c.upload_file(img)
    assert name == "openapi/abc.png"
    assert captured["url"].endswith("/openapi/v2/media/upload/binary")
    assert captured["auth"] == "Bearer test-key"
    assert b'name="file"' in captured["body"]


def test_upload_file_raises_on_missing_local_file(tmp_path):
    c = RunningHubClient("k")
    with pytest.raises(RunningHubUploadError):
        c.upload_file(tmp_path / "nonexistent.png")


def test_upload_file_raises_on_http_4xx(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    def handler(req):
        return httpx.Response(401, text="unauthorized")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUploadError) as exc_info:
        c.upload_file(img)
    assert "401" in str(exc_info.value)


def test_upload_file_raises_unavailable_on_connect_error(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    def handler(req):
        raise httpx.ConnectError("connection refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.upload_file(img)


def test_upload_file_raises_on_business_error_code(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(_png_bytes())

    def handler(req):
        return httpx.Response(200, json={
            "code": 1001, "msg": "余额不足", "data": None})

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUploadError) as exc_info:
        c.upload_file(img)
    assert "余额不足" in str(exc_info.value) or "1001" in str(exc_info.value)


def test_upload_file_mime_inferred_from_extension(tmp_path):
    img = tmp_path / "x.jpg"
    img.write_bytes(_png_bytes())   # 内容无所谓，扩展名决定 mime

    captured = {}

    def handler(req):
        captured["body"] = req.read()
        return httpx.Response(200, json={
            "code": 0, "data": {"fileName": "openapi/x.jpg"}})

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    c.upload_file(img)
    assert b"image/jpeg" in captured["body"]
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_runninghub_client.py -v
```

Expected: `ImportError: cannot import name 'RunningHubClient'`

- [ ] **Step 3: 在 `app/providers/runninghub.py` 末尾追加 client init + upload_file**

```python
import httpx


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
        ".mp4": "video/mp4", ".mov": "video/quicktime",
    }.get(ext, "application/octet-stream")


class RunningHubClient:
    """RunningHub OpenAPI 裸客户端：封装鉴权 + 5 个核心端点。

    每个方法对应一次 HTTP 调用；调用方负责把它们编排成业务流程。
    """

    def __init__(self, api_key: str,
                 base_url: str = "https://www.runninghub.cn",
                 request_timeout: float = 30.0):
        if not api_key:
            raise RunningHubUnavailable("RUNNINGHUB_API_KEY 未设置")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=request_timeout)

    # ---------- upload ----------

    def upload_file(self, path: Path) -> str:
        """上传一个本地文件，返回 RunningHub 内部 fileName。"""
        if not path.exists():
            raise RunningHubUploadError(f"文件不存在: {path}")
        url = f"{self.base_url}/openapi/v2/media/upload/binary"
        try:
            with path.open("rb") as f:
                resp = self._client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (path.name, f, _guess_mime(path))},
                )
            if resp.status_code >= 400:
                raise RunningHubUploadError(
                    f"upload HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if data.get("code") != 0:
                msg = data.get("msg") or data.get("message") or ""
                raise RunningHubUploadError(
                    f"upload code={data.get('code')} msg={msg}")
            return data["data"]["fileName"]
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"upload 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubUploadError(f"upload 响应异常: {e}") from e
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_runninghub_client.py -v
```

Expected: 9 passed（1 原有 + 8 新增）

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_runninghub_client.py
git commit -m "feat(runninghub): add RunningHubClient init and upload_file"
```

---

## Task 4: `RunningHubClient.create_task`

**Files:**
- Modify: `app/providers/runninghub.py`（在 RunningHubClient 类内追加）
- Modify: `tests/test_providers/test_runninghub_client.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_providers/test_runninghub_client.py` 末尾追加：

```python
# ---------- create_task ----------

def _ok_create_response(task_id="tid-1", status="QUEUED"):
    return httpx.Response(200, json={
        "code": 0, "msg": "success",
        "data": {
            "netWssUrl": "wss://x",
            "taskId": task_id,
            "clientId": "cid",
            "taskStatus": status,
            "promptTips": "{\"result\": true}",
        },
    })


def test_create_task_inline_workflow():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = req.read()
        return _ok_create_response("tid-42")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    task_id = c.create_task(workflow={"3": {"class_type": "VAE"}})
    assert task_id == "tid-42"
    assert captured["url"].endswith("/task/openapi/create")
    body = captured["body"].decode()
    assert '"workflow"' in body
    assert '"workflowId"' not in body


def test_create_task_with_workflow_id_and_node_info_list():
    captured = {}

    def handler(req):
        captured["body"] = req.read()
        return _ok_create_response("tid-2")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    items = [{"nodeId": "46", "fieldName": "global_prompt",
              "fieldValue": "hello"}]
    task_id = c.create_task(workflow_id="wf-123", node_info_list=items)
    assert task_id == "tid-2"
    body = captured["body"].decode()
    assert '"workflowId":"wf-123"' in body.replace(" ", "")
    assert '"nodeInfoList"' in body
    assert '"workflow"' not in body or body.count('"workflow"') == 1  # workflowId 也含"workflow"


def test_create_task_rejects_when_both_workflow_and_id_missing():
    c = RunningHubClient("k")
    with pytest.raises(RunningHubInvalidSpec):
        c.create_task()


def test_create_task_passes_webhook_url():
    captured = {}

    def handler(req):
        captured["body"] = req.read()
        return _ok_create_response()

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    c.create_task(workflow={}, webhook_url="https://callback/x")
    assert b"https://callback/x" in captured["body"]


def test_create_task_business_error_includes_prompt_tips():
    def handler(req):
        return httpx.Response(200, json={
            "code": 805, "msg": "validation failed",
            "data": {"promptTips":
                     "{\"node_errors\": {\"46\": \"invalid\"}}"},
        })

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        c.create_task(workflow={})
    msg = str(exc_info.value)
    assert "805" in msg
    assert "validation failed" in msg


def test_create_task_http_5xx_raises_task_failed():
    def handler(req):
        return httpx.Response(503, text="service unavailable")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        c.create_task(workflow={})
    assert "503" in str(exc_info.value)


def test_create_task_connect_error_raises_unavailable():
    def handler(req):
        raise httpx.ConnectError("refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.create_task(workflow={})
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_runninghub_client.py -v -k create_task
```

Expected: `AttributeError: 'RunningHubClient' object has no attribute 'create_task'`

- [ ] **Step 3: 在 RunningHubClient 类内追加 create_task method**

将以下方法加到 `upload_file` 之后：

```python
    # ---------- create_task ----------

    def create_task(self, *,
                    workflow: dict | None = None,
                    workflow_id: str | None = None,
                    node_info_list: list[dict] | None = None,
                    webhook_url: str | None = None,
                    add_metadata: bool = True) -> str:
        """提交 ComfyUI 任务。

        workflow 与 workflow_id 二选一：
          - workflow=完整 JSON（inline 模式）
          - workflow_id=平台模板 ID + node_info_list（id 模式）

        返回 taskId（字符串）。
        """
        if workflow is None and not workflow_id:
            raise RunningHubInvalidSpec(
                "create_task 必须传 workflow 或 workflow_id")
        payload: dict = {
            "apiKey": self.api_key,
            "addMetadata": add_metadata,
        }
        if workflow is not None:
            payload["workflow"] = workflow
        else:
            payload["workflowId"] = workflow_id
        if node_info_list:
            payload["nodeInfoList"] = node_info_list
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        url = f"{self.base_url}/task/openapi/create"
        try:
            resp = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                raise RunningHubTaskFailed(
                    f"create_task HTTP {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            if data.get("code") != 0:
                tips = (data.get("data") or {}).get("promptTips", "")[:300]
                raise RunningHubTaskFailed(
                    f"create_task code={data.get('code')} "
                    f"msg={data.get('msg')} tips={tips}")
            return str(data["data"]["taskId"])
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"create_task 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubTaskFailed(f"create_task 响应异常: {e}") from e
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_runninghub_client.py -v
```

Expected: 16 passed (9 prior + 7 新)

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_runninghub_client.py
git commit -m "feat(runninghub): add RunningHubClient.create_task"
```

---

## Task 5: `query_task` + `download_file` + `cancel_task` + context manager

**Files:**
- Modify: `app/providers/runninghub.py`
- Modify: `tests/test_providers/test_runninghub_client.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_providers/test_runninghub_client.py` 末尾追加：

```python
# ---------- query_task ----------

def test_query_task_v2_dict_shape():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = req.read()
        return httpx.Response(200, json={
            "code": 0, "msg": "",
            "data": {
                "taskId": "tid", "status": "RUNNING",
                "results": None, "errorCode": "",
                "errorMessage": "",
            },
        })

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    d = c.query_task("tid")
    assert d["status"] == "RUNNING"
    assert d["results"] is None
    assert captured["url"].endswith("/openapi/v2/query")
    assert b"tid" in captured["body"]


def test_query_task_legacy_string_data_compat():
    def handler(req):
        return httpx.Response(200, json={
            "code": 0, "msg": "", "data": "SUCCESS"})

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    d = c.query_task("tid")
    assert d == {"status": "SUCCESS", "results": None,
                  "errorCode": "", "errorMessage": ""}


def test_query_task_success_with_results():
    def handler(req):
        return httpx.Response(200, json={
            "code": 0, "msg": "",
            "data": {
                "status": "SUCCESS",
                "results": [{"url": "https://x/v.mp4",
                              "outputType": "mp4"}],
                "errorCode": "", "errorMessage": "",
            },
        })

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    d = c.query_task("tid")
    assert d["status"] == "SUCCESS"
    assert d["results"] == [{"url": "https://x/v.mp4", "outputType": "mp4"}]


def test_query_task_connect_error_raises_unavailable():
    def handler(req):
        raise httpx.ConnectError("refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.query_task("tid")


def test_query_task_5xx_raises_unavailable():
    def handler(req):
        return httpx.Response(503)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.query_task("tid")


# ---------- download_file ----------

def test_download_file_streams_to_dest(tmp_path):
    payload = b"a" * 5000

    def handler(req):
        return httpx.Response(200, content=payload)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    dest = tmp_path / "sub" / "out.mp4"
    result = c.download_file("https://x/v.mp4", dest)
    assert result == dest
    assert dest.read_bytes() == payload
    assert dest.parent.exists()


def test_download_file_raises_on_404(tmp_path):
    def handler(req):
        return httpx.Response(404)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    with pytest.raises(RunningHubUnavailable):
        c.download_file("https://x/v.mp4", tmp_path / "v.mp4")


# ---------- cancel_task ----------

def test_cancel_task_silent_on_error():
    def handler(req):
        raise httpx.ConnectError("refused")

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    # 不应抛错
    c.cancel_task("tid")


def test_cancel_task_silent_on_4xx():
    def handler(req):
        return httpx.Response(400)

    c = RunningHubClient("k")
    _set_mock_transport(c, handler)
    c.cancel_task("tid")


# ---------- context manager ----------

def test_context_manager_closes_client():
    c = RunningHubClient("k")
    with c as got:
        assert got is c
    assert c._client.is_closed
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_runninghub_client.py -v -k "query_task or download or cancel or context"
```

Expected: `AttributeError: ... has no attribute 'query_task'`

- [ ] **Step 3: 在 RunningHubClient 类内追加四个方法**

```python
    # ---------- query_task ----------

    def query_task(self, task_id: str) -> dict:
        """POST /openapi/v2/query 查任务状态。

        返回 {status, results, errorCode, errorMessage}（V2 dict）或
        {status, results=None, errorCode='', errorMessage=''}（legacy string 兼容）。
        """
        url = f"{self.base_url}/openapi/v2/query"
        try:
            resp = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"taskId": task_id},
            )
            if resp.status_code >= 400:
                raise RunningHubUnavailable(
                    f"query_task HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if data.get("code") != 0:
                raise RunningHubUnavailable(
                    f"query_task code={data.get('code')} msg={data.get('msg')}")
            d = data["data"]
            if isinstance(d, str):
                return {"status": d, "results": None,
                        "errorCode": "", "errorMessage": ""}
            return d
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"query_task 连接失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise RunningHubUnavailable(f"query_task 响应异常: {e}") from e

    # ---------- download_file ----------

    def download_file(self, url: str, dest: Path) -> Path:
        """流式下载到 dest（自动创建 parent dir），返回 dest。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise RunningHubUnavailable(
                        f"download HTTP {resp.status_code}")
                with dest.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
            return dest
        except httpx.HTTPError as e:
            raise RunningHubUnavailable(f"download 连接失败: {e}") from e

    # ---------- cancel_task ----------

    def cancel_task(self, task_id: str) -> None:
        """POST /task/openapi/cancel；best-effort，失败静默吞错。"""
        url = f"{self.base_url}/task/openapi/cancel"
        try:
            self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"apiKey": self.api_key, "taskId": task_id},
            )
        except httpx.HTTPError:
            pass

    # ---------- 生命周期 ----------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RunningHubClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_runninghub_client.py -v
```

Expected: 26 passed (16 prior + 10 new)

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_runninghub_client.py
git commit -m "feat(runninghub): add query_task / download_file / cancel_task / context manager"
```

---

## Task 6: `LTXTaskBuilder` init + `build_inline_workflow`

**Files:**
- Modify: `app/providers/runninghub.py`（追加 LTXNodes / LTXTaskBuilder 上半部）
- Modify: `tests/test_providers/test_ltx_task_builder.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_providers/test_ltx_task_builder.py` 顶部 import 区追加：

```python
import copy
import json

from app.providers.runninghub import LTXNodes, LTXTaskBuilder
```

文件末尾追加：

```python
# ---------- Builder fixture ----------

@pytest.fixture
def template_path():
    """指向项目内置的真实模板。"""
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent.parent
         / "app" / "templates" / "ltx_director_v23.json")
    assert p.exists(), f"模板不存在: {p}"
    return p


@pytest.fixture
def builder(template_path):
    return LTXTaskBuilder(template_path)


# ---------- init ----------

def test_builder_init_loads_template(builder):
    assert LTXNodes.DIRECTOR in builder._template
    assert LTXNodes.SAVE_VIDEO in builder._template
    assert LTXNodes.NOISE in builder._template
    assert LTXNodes.RESOLUTION in builder._template


def test_builder_init_rejects_template_missing_director_node(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"99": {"class_type": "X"}}))
    with pytest.raises(RunningHubInvalidSpec) as exc_info:
        LTXTaskBuilder(bad)
    assert LTXNodes.DIRECTOR in str(exc_info.value)


def test_builder_init_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        LTXTaskBuilder(tmp_path / "absent.json")


# ---------- build_inline_workflow ----------

def _basic_spec(img_path: Path | None = None,
                 length=33, n_segs=1) -> LTXDirectorSpec:
    return LTXDirectorSpec(
        global_prompt="global",
        segments=tuple(
            LTXSegment(local_prompt=f"p{i}", length=length,
                        image_path=img_path)
            for i in range(n_segs)
        ),
        frame_rate=24,
    )


def test_inline_workflow_minimal_spec(builder, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    uploaded = {img: "openapi/abc.png"}
    wf = builder.build_inline_workflow(spec, uploaded)
    assert LTXNodes.DIRECTOR in wf
    inputs = wf[LTXNodes.DIRECTOR]["inputs"]
    assert inputs["global_prompt"] == "global"
    assert inputs["frame_rate"] == 24


def test_inline_workflow_does_not_mutate_template(builder, tmp_path):
    snapshot = copy.deepcopy(builder._template)
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    builder.build_inline_workflow(spec, {img: "openapi/abc.png"})
    assert builder._template == snapshot


def test_inline_workflow_other_nodes_unchanged(builder, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    wf = builder.build_inline_workflow(spec, {img: "openapi/abc.png"})
    # 节点 80 / 113 / 140（LoRA loaders）必须保持模板默认
    for nid in ("80", "113", "140"):
        assert wf[nid] == builder._template[nid]


def test_inline_timeline_data_json_structure(builder, tmp_path):
    img1 = tmp_path / "a.png"; img1.write_bytes(b"x")
    img2 = tmp_path / "b.png"; img2.write_bytes(b"y")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="p1", length=33, image_path=img1),
        LTXSegment(local_prompt="p2", length=33, image_path=img2),
        LTXSegment(local_prompt="p3", length=30, image_path=img1),  # 复用
    ))
    uploaded = {img1: "openapi/a.png", img2: "openapi/b.png"}
    wf = builder.build_inline_workflow(spec, uploaded)
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    assert len(td["segments"]) == 3
    assert td["segments"][0]["start"] == 0
    assert td["segments"][1]["start"] == 33
    assert td["segments"][2]["start"] == 66
    assert td["segments"][0]["length"] == 33
    assert td["segments"][0]["prompt"] == "p1"
    assert td["segments"][0]["type"] == "image"
    assert td["segments"][0]["imageFile"] == "a.png"
    assert "filename=a.png" in td["segments"][0]["imageB64"]
    assert td["audioSegments"] == []


def test_inline_local_prompts_joined_with_pipe_and_spaces(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img),
        LTXSegment(local_prompt="b", length=10, image_path=img),
        LTXSegment(local_prompt="c", length=10, image_path=img),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["local_prompts"] == "a | b | c"


def test_inline_segment_lengths_csv(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=33, image_path=img),
        LTXSegment(local_prompt="b", length=33, image_path=img),
        LTXSegment(local_prompt="c", length=30, image_path=img),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["segment_lengths"] == "33,33,30"


def test_inline_guide_strength_two_decimals(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img,
                    guide_strength=1.0),
        LTXSegment(local_prompt="b", length=10, image_path=img,
                    guide_strength=0.75),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["guide_strength"] == "1.00,0.75"


def test_inline_global_prompt_blanked_when_disabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        global_prompt="should-be-blanked",
        use_global_prompt=False,
        segments=(LTXSegment(local_prompt="p", length=10, image_path=img),),
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.DIRECTOR]["inputs"]["global_prompt"] == ""


def test_inline_duration_frames_and_seconds_consistent(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=96, image_path=img),),
        frame_rate=24,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    inputs = wf[LTXNodes.DIRECTOR]["inputs"]
    assert inputs["duration_frames"] == 96
    assert inputs["duration_seconds"] == 4.0


def test_inline_audio_empty_when_disabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"; aud.write_bytes(b"a")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=False,  # 关闭
    )
    wf = builder.build_inline_workflow(
        spec, {img: "openapi/a.png", aud: "openapi/x.mp3"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    assert td["audioSegments"] == []
    assert wf[LTXNodes.DIRECTOR]["inputs"]["use_custom_audio"] is False


def test_inline_audio_present_when_enabled(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"; aud.write_bytes(b"a")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=True,
    )
    wf = builder.build_inline_workflow(
        spec, {img: "openapi/a.png", aud: "openapi/x.mp3"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    assert len(td["audioSegments"]) == 1
    assert td["audioSegments"][0]["audioFile"] == "x.mp3"


def test_inline_filename_prefix_node_104(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        filename_prefix="myvid",
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.SAVE_VIDEO]["inputs"]["filename_prefix"] == "myvid"


def test_inline_noise_seed_none_preserves_template(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    original_seed = builder._template[LTXNodes.NOISE]["inputs"]["noise_seed"]
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        noise_seed=None,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.NOISE]["inputs"]["noise_seed"] == original_seed


def test_inline_noise_seed_overrides_template(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        noise_seed=42,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    assert wf[LTXNodes.NOISE]["inputs"]["noise_seed"] == 42


def test_inline_resolution_preset_applied(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        resolution_preset="720x1280 (9:16) (竖屏)",
        use_custom_resolution=False,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    inputs = wf[LTXNodes.RESOLUTION]["inputs"]
    assert inputs["use_custom_resolution"] is False
    assert inputs["resolution"] == "720x1280 (9:16) (竖屏)"


def test_inline_custom_resolution_applied(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        use_custom_resolution=True,
        custom_width=1024, custom_height=768,
    )
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    inputs = wf[LTXNodes.RESOLUTION]["inputs"]
    assert inputs["use_custom_resolution"] is True
    assert inputs["custom_width"] == 1024
    assert inputs["custom_height"] == 768


def test_seg_id_generated_when_blank(builder, tmp_path):
    import re
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img, seg_id=""),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    generated_id = td["segments"][0]["id"]
    assert re.match(r"^\d{13}[0-9a-f]{1,5}$", generated_id), generated_id


def test_seg_id_preserved_when_provided(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=img,
                    seg_id="custom-abc"),
    ))
    wf = builder.build_inline_workflow(spec, {img: "openapi/a.png"})
    td = json.loads(wf[LTXNodes.DIRECTOR]["inputs"]["timeline_data"])
    assert td["segments"][0]["id"] == "custom-abc"
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_ltx_task_builder.py -v -k "builder or inline or seg_id"
```

Expected: `ImportError: cannot import name 'LTXNodes'`

- [ ] **Step 3: 在 `app/providers/runninghub.py` 末尾追加 LTXNodes 常量 + LTXTaskBuilder（inline 部分）**

```python
import copy
import json
import secrets
import time


class LTXNodes:
    """LTX 工作流的关键节点 id。模板更新时改这里。"""
    DIRECTOR = "46"
    SAVE_VIDEO = "104"
    NOISE = "132"
    RESOLUTION = "139"


# ID 模式 nodeInfoList 白名单：仅这 11 个 Director 字段允许被覆盖
_DIRECTOR_FIELDS = (
    "global_prompt", "duration_frames", "duration_seconds",
    "timeline_data", "local_prompts", "segment_lengths",
    "use_custom_audio", "frame_rate", "display_mode",
    "guide_strength", "epsilon",
)


def _gen_seg_id() -> str:
    """模仿原 JSON 里的 id 格式：13 位毫秒戳 + 5 位 hex 随机。"""
    ts = int(time.time() * 1000)
    rnd = secrets.token_hex(3)[:5]
    return f"{ts}{rnd}"


class LTXTaskBuilder:
    """LTXDirectorSpec → workflow JSON / nodeInfoList 翻译。

    启动时一次性加载模板并校验关键节点存在；每次 build_* deepcopy 一份新结果。
    """

    def __init__(self, template_path: Path):
        self.template_path = template_path
        with template_path.open(encoding="utf-8") as f:
            self._template: dict = json.load(f)
        for nid in (LTXNodes.DIRECTOR, LTXNodes.SAVE_VIDEO,
                    LTXNodes.NOISE, LTXNodes.RESOLUTION):
            if nid not in self._template:
                raise RunningHubInvalidSpec(
                    f"模板 {template_path} 缺少节点 {nid}")

    # ---------- 公共构建 API ----------

    def build_inline_workflow(self, spec: LTXDirectorSpec,
                              uploaded_files: dict[Path, str]) -> dict:
        """生成完整 workflow JSON（嵌入模式）。"""
        self._validate(spec, uploaded_files)
        wf = copy.deepcopy(self._template)
        params = self._compute_director_params(spec, uploaded_files)
        wf[LTXNodes.DIRECTOR]["inputs"].update(params)
        wf[LTXNodes.SAVE_VIDEO]["inputs"]["filename_prefix"] = spec.filename_prefix
        if spec.noise_seed is not None:
            wf[LTXNodes.NOISE]["inputs"]["noise_seed"] = spec.noise_seed
        self._apply_resolution(wf[LTXNodes.RESOLUTION]["inputs"], spec)
        return wf

    # ---------- 私有：spec → LTXDirector inputs ----------

    def _compute_director_params(self, spec: LTXDirectorSpec,
                                  uploaded_files: dict[Path, str]) -> dict:
        segments_payload = self._build_segments_payload(spec, uploaded_files)
        audio_payload = self._build_audio_segments_payload(spec, uploaded_files)
        timeline_data = json.dumps(
            {"segments": segments_payload, "audioSegments": audio_payload},
            ensure_ascii=False,
        )
        total_frames = spec.total_length_frames()
        return {
            "global_prompt": spec.global_prompt if spec.use_global_prompt else "",
            "duration_frames": total_frames,
            "duration_seconds": round(total_frames / spec.frame_rate, 6),
            "timeline_data": timeline_data,
            "local_prompts": " | ".join(s.local_prompt for s in spec.segments),
            "segment_lengths": ",".join(str(s.length) for s in spec.segments),
            "use_custom_audio": spec.use_custom_audio,
            "frame_rate": spec.frame_rate,
            "display_mode": spec.display_mode,
            "guide_strength": ",".join(
                f"{s.guide_strength:.2f}" for s in spec.segments),
            "epsilon": spec.epsilon,
        }

    def _build_segments_payload(self, spec: LTXDirectorSpec,
                                 uploaded_files: dict[Path, str]) -> list[dict]:
        payload: list[dict] = []
        start = 0
        for seg in spec.segments:
            entry: dict = {
                "id": seg.seg_id or _gen_seg_id(),
                "start": start,
                "length": seg.length,
                "prompt": seg.local_prompt,
                "type": seg.segment_type,
            }
            if seg.image_path is not None:
                file_name = uploaded_files[seg.image_path]
                entry["imageFile"] = Path(file_name).name
                entry["imageB64"] = (
                    f"/view?filename={Path(file_name).name}"
                    f"&type=input&subfolder=")
            payload.append(entry)
            start += seg.length
        return payload

    def _build_audio_segments_payload(self, spec: LTXDirectorSpec,
                                       uploaded_files: dict[Path, str]
                                       ) -> list[dict]:
        if not spec.use_custom_audio or not spec.audio_segments:
            return []
        return [{
            "id": _gen_seg_id(),
            "start": a.start_frame,
            "length": a.length_frames,
            "audioFile": Path(uploaded_files[a.audio_path]).name,
        } for a in spec.audio_segments]

    def _apply_resolution(self, inputs: dict, spec: LTXDirectorSpec) -> None:
        inputs["use_custom_resolution"] = spec.use_custom_resolution
        if spec.use_custom_resolution:
            inputs["custom_width"] = spec.custom_width
            inputs["custom_height"] = spec.custom_height
        else:
            inputs["resolution"] = spec.resolution_preset

    # ---------- 校验（Task 7 完整实现） ----------

    def _validate(self, spec: LTXDirectorSpec,
                   uploaded_files: dict[Path, str]) -> None:
        # 最低限度校验：保证下游 _build_segments_payload 不 KeyError
        if not spec.segments:
            raise RunningHubInvalidSpec("至少需要 1 段")
        for i, s in enumerate(spec.segments):
            if s.image_path is not None and s.image_path not in uploaded_files:
                raise RunningHubInvalidSpec(
                    f"段 {i} 的图片 {s.image_path} 未在 uploaded_files 中")
        if spec.use_custom_audio:
            for j, a in enumerate(spec.audio_segments):
                if a.audio_path not in uploaded_files:
                    raise RunningHubInvalidSpec(
                        f"音频段 {j} {a.audio_path} 未在 uploaded_files 中")
```

> 注：Task 7 会扩展 `_validate` 加入更多规则（length / guide_strength / frame_rate 范围）。

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_ltx_task_builder.py -v
```

Expected: 27 passed (8 prior + 19 new)

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_ltx_task_builder.py
git commit -m "feat(runninghub): add LTXTaskBuilder.build_inline_workflow"
```

---

## Task 7: `LTXTaskBuilder.build_node_info_list` + 完整 `_validate`

**Files:**
- Modify: `app/providers/runninghub.py`
- Modify: `tests/test_providers/test_ltx_task_builder.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_providers/test_ltx_task_builder.py` 末尾追加：

```python
# ---------- build_node_info_list ----------

def test_nodeinfolist_includes_all_director_fields(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    field_names = {it["fieldName"] for it in items
                    if it["nodeId"] == LTXNodes.DIRECTOR}
    expected = {"global_prompt", "duration_frames", "duration_seconds",
                "timeline_data", "local_prompts", "segment_lengths",
                "use_custom_audio", "frame_rate", "display_mode",
                "guide_strength", "epsilon"}
    assert expected.issubset(field_names)


def test_nodeinfolist_excludes_non_whitelisted_director_fields(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    director_fields = {it["fieldName"] for it in items
                        if it["nodeId"] == LTXNodes.DIRECTOR}
    # 这些字段不应出现在 nodeInfoList（它们是节点连线 / 常量）
    forbidden = {"model", "clip", "audio_vae", "custom_width",
                  "custom_height", "timeline_ui", "resize_method",
                  "divisible_by", "img_compression"}
    assert not director_fields & forbidden


def test_nodeinfolist_includes_filename_prefix_104(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    spec = dataclasses.replace(spec, filename_prefix="myvid")
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    matching = [it for it in items
                if it["nodeId"] == LTXNodes.SAVE_VIDEO
                and it["fieldName"] == "filename_prefix"]
    assert len(matching) == 1
    assert matching[0]["fieldValue"] == "myvid"


def test_nodeinfolist_noise_seed_only_when_set(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec_none = _basic_spec(img_path=img)
    items_none = builder.build_node_info_list(spec_none, {img: "openapi/a.png"})
    assert not any(it["nodeId"] == LTXNodes.NOISE for it in items_none)

    spec_seed = dataclasses.replace(spec_none, noise_seed=42)
    items_seed = builder.build_node_info_list(spec_seed, {img: "openapi/a.png"})
    seed_items = [it for it in items_seed if it["nodeId"] == LTXNodes.NOISE]
    assert len(seed_items) == 1
    assert seed_items[0]["fieldName"] == "noise_seed"
    assert seed_items[0]["fieldValue"] == 42


def test_nodeinfolist_resolution_preset_when_not_custom(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    res_items = [it for it in items if it["nodeId"] == LTXNodes.RESOLUTION]
    assert len(res_items) == 1
    assert res_items[0]["fieldName"] == "resolution"
    assert res_items[0]["fieldValue"] == "1280x720 (16:9) (横屏)"


def test_nodeinfolist_custom_resolution_three_fields(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        use_custom_resolution=True,
        custom_width=1024, custom_height=768,
    )
    items = builder.build_node_info_list(spec, {img: "openapi/a.png"})
    res_items = {it["fieldName"]: it["fieldValue"]
                  for it in items if it["nodeId"] == LTXNodes.RESOLUTION}
    assert res_items == {"use_custom_resolution": True,
                          "custom_width": 1024, "custom_height": 768}


# ---------- 完整 _validate ----------

def test_validate_rejects_empty_segments(builder):
    spec = LTXDirectorSpec(segments=())
    with pytest.raises(RunningHubInvalidSpec, match="至少需要 1 段"):
        builder.build_inline_workflow(spec, {})


def test_validate_rejects_segment_length_lt_1(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=0, image_path=img),
    ))
    with pytest.raises(RunningHubInvalidSpec, match="length"):
        builder.build_inline_workflow(spec, {img: "openapi/a.png"})


def test_validate_rejects_missing_uploaded_image(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    spec = _basic_spec(img_path=img)
    with pytest.raises(RunningHubInvalidSpec, match="未在 uploaded_files"):
        builder.build_inline_workflow(spec, {})


def test_validate_rejects_guide_strength_out_of_range(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for bad in (-0.1, 1.5):
        spec = LTXDirectorSpec(segments=(
            LTXSegment(local_prompt="a", length=10, image_path=img,
                        guide_strength=bad),
        ))
        with pytest.raises(RunningHubInvalidSpec, match="guide_strength"):
            builder.build_inline_workflow(spec, {img: "openapi/a.png"})


def test_validate_rejects_invalid_frame_rate(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    for bad in (0, 200):
        spec = LTXDirectorSpec(
            segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
            frame_rate=bad,
        )
        with pytest.raises(RunningHubInvalidSpec, match="frame_rate"):
            builder.build_inline_workflow(spec, {img: "openapi/a.png"})


def test_validate_rejects_missing_audio_upload(builder, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "x.mp3"
    spec = LTXDirectorSpec(
        segments=(LTXSegment(local_prompt="a", length=10, image_path=img),),
        audio_segments=(LTXAudioSegment(audio_path=aud, start_frame=0,
                                          length_frames=10),),
        use_custom_audio=True,
    )
    with pytest.raises(RunningHubInvalidSpec, match="音频段"):
        builder.build_inline_workflow(spec, {img: "openapi/a.png"})


def test_validate_passes_text_segment_without_upload(builder):
    spec = LTXDirectorSpec(segments=(
        LTXSegment(local_prompt="a", length=10, image_path=None),
    ))
    # 不应抛错（text 段不要求 image_path）
    builder.build_inline_workflow(spec, {})
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_ltx_task_builder.py -v -k "nodeinfolist or validate_rejects_segment_length or validate_rejects_guide or validate_rejects_invalid_frame"
```

Expected: 多项失败（缺 `build_node_info_list` 方法 + `_validate` 校验不全）

- [ ] **Step 3: 在 LTXTaskBuilder 类内追加 `build_node_info_list` + 替换 `_validate`**

在 `_apply_resolution` 之后插入：

```python
    def build_node_info_list(self, spec: LTXDirectorSpec,
                              uploaded_files: dict[Path, str]) -> list[dict]:
        """生成 nodeInfoList 数组（ID 模式）。"""
        self._validate(spec, uploaded_files)
        items: list[dict] = []
        params = self._compute_director_params(spec, uploaded_files)
        for fname in _DIRECTOR_FIELDS:
            if fname in params:
                items.append({
                    "nodeId": LTXNodes.DIRECTOR,
                    "fieldName": fname,
                    "fieldValue": params[fname],
                })
        items.append({
            "nodeId": LTXNodes.SAVE_VIDEO,
            "fieldName": "filename_prefix",
            "fieldValue": spec.filename_prefix,
        })
        if spec.noise_seed is not None:
            items.append({
                "nodeId": LTXNodes.NOISE,
                "fieldName": "noise_seed",
                "fieldValue": spec.noise_seed,
            })
        if spec.use_custom_resolution:
            items.extend([
                {"nodeId": LTXNodes.RESOLUTION,
                 "fieldName": "use_custom_resolution", "fieldValue": True},
                {"nodeId": LTXNodes.RESOLUTION,
                 "fieldName": "custom_width", "fieldValue": spec.custom_width},
                {"nodeId": LTXNodes.RESOLUTION,
                 "fieldName": "custom_height", "fieldValue": spec.custom_height},
            ])
        else:
            items.append({
                "nodeId": LTXNodes.RESOLUTION,
                "fieldName": "resolution",
                "fieldValue": spec.resolution_preset,
            })
        return items
```

替换 `_validate` 整个方法（Task 6 留的最小版）：

```python
    def _validate(self, spec: LTXDirectorSpec,
                   uploaded_files: dict[Path, str]) -> None:
        if not spec.segments:
            raise RunningHubInvalidSpec("至少需要 1 段")
        if not (1 <= spec.frame_rate <= 120):
            raise RunningHubInvalidSpec(
                f"frame_rate 须在 1-120 之间，当前 {spec.frame_rate}")
        for i, s in enumerate(spec.segments):
            if s.length < 1:
                raise RunningHubInvalidSpec(
                    f"段 {i} length<1（{s.length}）")
            if s.image_path is not None and s.image_path not in uploaded_files:
                raise RunningHubInvalidSpec(
                    f"段 {i} 的图片 {s.image_path} 未在 uploaded_files 中")
            if not (0.0 <= s.guide_strength <= 1.0):
                raise RunningHubInvalidSpec(
                    f"段 {i} guide_strength 越界（{s.guide_strength}）")
        if spec.use_custom_audio:
            for j, a in enumerate(spec.audio_segments):
                if a.audio_path not in uploaded_files:
                    raise RunningHubInvalidSpec(
                        f"音频段 {j} {a.audio_path} 未在 uploaded_files 中")
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_ltx_task_builder.py -v
```

Expected: 40 passed (27 prior + 13 new)

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_ltx_task_builder.py
git commit -m "feat(runninghub): add build_node_info_list and complete _validate"
```

---

## Task 8: `submit_ltx_task` + `LTXTaskHandle.status`

**Files:**
- Modify: `app/providers/runninghub.py`
- Create: `tests/test_providers/test_runninghub_submit.py`

- [ ] **Step 1: 写 failing tests**

新建 `tests/test_providers/test_runninghub_submit.py`：

```python
"""submit_ltx_task + LTXTaskHandle 单测（mock RunningHubClient）。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.providers.runninghub import (
    LTXSegment, LTXDirectorSpec, LTXTaskBuilder,
    RunningHubClient, RunningHubInvalidSpec,
    RunningHubTaskFailed, RunningHubUnavailable, RunningHubUploadError,
    submit_ltx_task, LTXTaskHandle,
)


# ---------- fixtures ----------

@pytest.fixture
def template_path():
    p = (Path(__file__).resolve().parent.parent.parent
         / "app" / "templates" / "ltx_director_v23.json")
    return p


@pytest.fixture
def builder(template_path):
    return LTXTaskBuilder(template_path)


@pytest.fixture
def mock_client():
    c = MagicMock(spec=RunningHubClient)
    c.create_task.return_value = "tid-1"
    c.upload_file.side_effect = lambda p: f"openapi/{p.name}"
    return c


def _spec_with_3_segments(tmp_path) -> LTXDirectorSpec:
    img1 = tmp_path / "a.png"; img1.write_bytes(b"a")
    img2 = tmp_path / "b.png"; img2.write_bytes(b"b")
    return LTXDirectorSpec(
        segments=(
            LTXSegment(local_prompt="s1", length=10, image_path=img1),
            LTXSegment(local_prompt="s2", length=10, image_path=img1),  # 复用
            LTXSegment(local_prompt="s3", length=10, image_path=img2),
        ),
        frame_rate=24,
        filename_prefix="testvid",
        output_dir=tmp_path / "out",
    )


# ---------- submit_ltx_task ----------

def test_submit_rejects_unknown_mode(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    with pytest.raises(RunningHubInvalidSpec):
        submit_ltx_task(mock_client, spec, builder, mode="weird")


def test_submit_id_mode_requires_workflow_id(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    with pytest.raises(RunningHubInvalidSpec):
        submit_ltx_task(mock_client, spec, builder, mode="id")


def test_submit_uploads_unique_files_only(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="inline")
    # 3 段但只 2 个唯一文件
    assert mock_client.upload_file.call_count == 2


def test_submit_inline_passes_workflow_dict(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="inline")
    call = mock_client.create_task.call_args
    assert "workflow" in call.kwargs
    assert isinstance(call.kwargs["workflow"], dict)
    assert "workflow_id" not in call.kwargs or not call.kwargs.get("workflow_id")


def test_submit_id_mode_passes_workflow_id_and_node_info_list(
        mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="id",
                     workflow_id="wf-123")
    call = mock_client.create_task.call_args
    assert call.kwargs.get("workflow_id") == "wf-123"
    assert isinstance(call.kwargs.get("node_info_list"), list)
    assert "workflow" not in call.kwargs or not call.kwargs.get("workflow")


def test_submit_passes_webhook_url(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="inline",
                     webhook_url="https://cb.x")
    call = mock_client.create_task.call_args
    assert call.kwargs.get("webhook_url") == "https://cb.x"


def test_submit_upload_progress_callback(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    calls = []
    submit_ltx_task(mock_client, spec, builder, mode="inline",
                     upload_progress_cb=lambda d, t, p: calls.append((d, t, p.name)))
    assert calls == [(1, 2, "a.png"), (2, 2, "b.png")]


def test_submit_returns_handle_with_correct_task_id(
        mock_client, builder, tmp_path):
    mock_client.create_task.return_value = "tid-42"
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, mode="inline")
    assert isinstance(handle, LTXTaskHandle)
    assert handle.task_id == "tid-42"
    assert handle.spec is spec


# ---------- LTXTaskHandle.status ----------

def test_handle_status_proxies_query_task(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, mode="inline")
    mock_client.query_task.return_value = {"status": "RUNNING",
                                            "results": None}
    assert handle.status() == "RUNNING"
    mock_client.query_task.assert_called_with("tid-1")
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_runninghub_submit.py -v
```

Expected: `ImportError: cannot import name 'submit_ltx_task'`

- [ ] **Step 3: 在 `app/providers/runninghub.py` 末尾追加 submit + handle（只含 status）**

```python
from typing import Callable, Optional
import logging

log = logging.getLogger(__name__)


def submit_ltx_task(client: RunningHubClient,
                    spec: LTXDirectorSpec,
                    builder: LTXTaskBuilder,
                    *,
                    mode: str = "inline",
                    workflow_id: str = "",
                    webhook_url: Optional[str] = None,
                    upload_progress_cb: Optional[
                        Callable[[int, int, Path], None]] = None,
                    ) -> "LTXTaskHandle":
    """编排一次完整提交：上传 → 构造 → create_task → 返回句柄。

    Args:
        mode: "inline"（嵌入完整 workflow JSON）或 "id"（workflow_id + nodeInfoList）
        workflow_id: mode="id" 时必填
        webhook_url: 可选；非 None 时透传给 create_task
        upload_progress_cb(done, total, path): 每上传完一个文件回调一次

    Returns:
        LTXTaskHandle，调用方用 .wait_for_result() 等结果。

    Raises:
        RunningHubInvalidSpec / RunningHubUploadError /
        RunningHubUnavailable / RunningHubTaskFailed
    """
    if mode not in ("inline", "id"):
        raise RunningHubInvalidSpec(f"未知 submit mode: {mode}")
    if mode == "id" and not workflow_id:
        raise RunningHubInvalidSpec("mode='id' 需要传 workflow_id")

    # 1. 批量上传
    files_to_upload = spec.unique_local_files()
    uploaded: dict[Path, str] = {}
    for i, path in enumerate(files_to_upload):
        uploaded[path] = client.upload_file(path)
        if upload_progress_cb:
            upload_progress_cb(i + 1, len(files_to_upload), path)

    # 2. 构造 + 提交
    if mode == "inline":
        workflow = builder.build_inline_workflow(spec, uploaded)
        task_id = client.create_task(
            workflow=workflow, webhook_url=webhook_url)
    else:
        node_info_list = builder.build_node_info_list(spec, uploaded)
        task_id = client.create_task(
            workflow_id=workflow_id,
            node_info_list=node_info_list,
            webhook_url=webhook_url,
        )

    log.info("RunningHub task submitted: %s (mode=%s, segments=%d)",
             task_id, mode, len(spec.segments))
    return LTXTaskHandle(client, task_id, spec, uploaded)


class LTXTaskHandle:
    """提交后的任务句柄。可跨线程传递（mock client 已天然线程安全）。"""

    TERMINAL = {"SUCCESS", "FAILED"}

    def __init__(self, client: RunningHubClient, task_id: str,
                 spec: LTXDirectorSpec,
                 uploaded_files: dict[Path, str]):
        self.client = client
        self.task_id = task_id
        self.spec = spec
        self.uploaded_files = uploaded_files

    def status(self) -> str:
        """单次拉取状态，返回 QUEUED/RUNNING/SUCCESS/FAILED。"""
        d = self.client.query_task(self.task_id)
        return d.get("status", "UNKNOWN")
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_runninghub_submit.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_runninghub_submit.py
git commit -m "feat(runninghub): add submit_ltx_task and LTXTaskHandle.status"
```

---

## Task 9: `LTXTaskHandle.wait_for_result` + `cancel`

**Files:**
- Modify: `app/providers/runninghub.py`
- Modify: `tests/test_providers/test_runninghub_submit.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_providers/test_runninghub_submit.py` 末尾追加：

```python
# ---------- LTXTaskHandle.wait_for_result ----------

@pytest.fixture(autouse=False)
def fast_sleep(monkeypatch):
    """禁掉 time.sleep 加速轮询测试。"""
    monkeypatch.setattr("app.providers.runninghub.time.sleep",
                        lambda _: None)


def _make_handle(mock_client, builder, tmp_path,
                 download_fn=None) -> LTXTaskHandle:
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, mode="inline")
    if download_fn is not None:
        mock_client.download_file.side_effect = download_fn
    else:
        mock_client.download_file.side_effect = lambda url, dest: dest
    return handle


def test_wait_success_downloads_mp4(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {
        "status": "SUCCESS",
        "results": [{"url": "https://x/v.mp4", "outputType": "mp4"}],
    }
    handle = _make_handle(mock_client, builder, tmp_path)
    result = handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert result.name == "testvid_tid-1.mp4"
    assert result.parent == tmp_path / "out"
    mock_client.download_file.assert_called_once_with(
        "https://x/v.mp4", result)


def test_wait_failed_raises(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {
        "status": "FAILED",
        "errorCode": "E_OOM",
        "errorMessage": "out of memory",
    }
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert "out of memory" in str(exc_info.value)


def test_wait_timeout_cancels_and_raises(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {"status": "RUNNING",
                                            "results": None}
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        handle.wait_for_result(timeout=0.5, poll_interval=0.1)
    assert "timeout" in str(exc_info.value).lower()
    mock_client.cancel_task.assert_called_with("tid-1")


def test_wait_progress_emitted_on_status_change(
        mock_client, builder, tmp_path, fast_sleep):
    states = iter([
        {"status": "QUEUED"},
        {"status": "RUNNING"},
        {"status": "RUNNING"},   # 不变，不回调
        {"status": "SUCCESS",
         "results": [{"url": "https://x/v.mp4", "outputType": "mp4"}]},
    ])
    mock_client.query_task.side_effect = lambda _: next(states)
    handle = _make_handle(mock_client, builder, tmp_path)

    seen = []
    handle.wait_for_result(timeout=10, poll_interval=0.1,
                            progress_cb=seen.append)
    # 状态变化 2 次（QUEUED → RUNNING），SUCCESS 是终态不计 progress
    assert seen == ["QUEUED", "RUNNING"]


def test_wait_cancel_check_aborts(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {"status": "RUNNING"}
    handle = _make_handle(mock_client, builder, tmp_path)
    counter = {"n": 0}

    def cancel_check():
        counter["n"] += 1
        return counter["n"] >= 2  # 第 2 轮触发取消

    with pytest.raises(RunningHubTaskFailed, match="cancelled"):
        handle.wait_for_result(timeout=10, poll_interval=0.1,
                                cancel_check=cancel_check)
    mock_client.cancel_task.assert_called_with("tid-1")


def test_wait_tolerates_transient_network_error(
        mock_client, builder, tmp_path, fast_sleep):
    responses = iter([
        RunningHubUnavailable("net1"),
        RunningHubUnavailable("net2"),
        {"status": "SUCCESS",
         "results": [{"url": "https://x/v.mp4", "outputType": "mp4"}]},
    ])

    def query(_):
        r = next(responses)
        if isinstance(r, Exception):
            raise r
        return r

    mock_client.query_task.side_effect = query
    handle = _make_handle(mock_client, builder, tmp_path)
    result = handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert result.name == "testvid_tid-1.mp4"


def test_wait_3_consecutive_network_errors_raises(
        mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.side_effect = RunningHubUnavailable("down")
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubUnavailable, match="3"):
        handle.wait_for_result(timeout=10, poll_interval=0.1)


def test_wait_empty_results_raises(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {"status": "SUCCESS",
                                            "results": []}
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubTaskFailed, match="results"):
        handle.wait_for_result(timeout=10, poll_interval=0.1)


def test_wait_uses_outputType_for_extension(
        mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {
        "status": "SUCCESS",
        "results": [{"url": "https://x/v.webm", "outputType": "webm"}],
    }
    handle = _make_handle(mock_client, builder, tmp_path)
    result = handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert result.suffix == ".webm"


# ---------- handle.cancel ----------

def test_handle_cancel_calls_client(mock_client, builder, tmp_path):
    handle = _make_handle(mock_client, builder, tmp_path)
    handle.cancel()
    mock_client.cancel_task.assert_called_with("tid-1")
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_runninghub_submit.py -v -k wait
```

Expected: 多项失败（`wait_for_result` / `cancel` 不存在）

- [ ] **Step 3: 在 LTXTaskHandle 类内追加 `wait_for_result` + `cancel` + `_download_first_result`**

替换 LTXTaskHandle 类整体（紧接现有 status 方法之后）：

```python
class LTXTaskHandle:
    """提交后的任务句柄。可跨线程传递（client 自己负责线程安全）。"""

    TERMINAL = {"SUCCESS", "FAILED"}

    def __init__(self, client: RunningHubClient, task_id: str,
                 spec: LTXDirectorSpec,
                 uploaded_files: dict[Path, str]):
        self.client = client
        self.task_id = task_id
        self.spec = spec
        self.uploaded_files = uploaded_files

    def status(self) -> str:
        d = self.client.query_task(self.task_id)
        return d.get("status", "UNKNOWN")

    def wait_for_result(self,
                        timeout: float = 1800.0,
                        poll_interval: float = 8.0,
                        progress_cb: Optional[Callable[[str], None]] = None,
                        cancel_check: Optional[Callable[[], bool]] = None,
                        ) -> Path:
        """阻塞轮询直到终态。SUCCESS 时下载并返回 MP4 路径。

        timeout 超时 → cancel_task + RunningHubTaskFailed("timeout")。
        cancel_check 返 True → cancel_task + RunningHubTaskFailed("cancelled")。
        网络抖动连续 3 次失败 → RunningHubUnavailable。
        SUCCESS 但 results 为空 → RunningHubTaskFailed。
        """
        deadline = time.time() + timeout
        last_status = ""
        consecutive_network_errors = 0

        while time.time() < deadline:
            if cancel_check and cancel_check():
                self.client.cancel_task(self.task_id)
                raise RunningHubTaskFailed(
                    f"task {self.task_id} cancelled by user")

            try:
                d = self.client.query_task(self.task_id)
                consecutive_network_errors = 0
            except RunningHubUnavailable as e:
                consecutive_network_errors += 1
                if consecutive_network_errors >= 3:
                    raise RunningHubUnavailable(
                        f"query_task 连续 3 次失败: {e}") from e
                log.warning("query_task transient error #%d: %s",
                            consecutive_network_errors, e)
                time.sleep(poll_interval)
                continue

            status = d.get("status", "UNKNOWN")
            if status != last_status and status not in self.TERMINAL:
                last_status = status
                if progress_cb:
                    progress_cb(status)

            if status == "SUCCESS":
                return self._download_first_result(d)
            if status == "FAILED":
                raise RunningHubTaskFailed(
                    f"task {self.task_id} FAILED: "
                    f"code={d.get('errorCode')} msg={d.get('errorMessage')}")

            time.sleep(poll_interval)

        self.client.cancel_task(self.task_id)
        raise RunningHubTaskFailed(
            f"task {self.task_id} timeout after {timeout}s")

    def cancel(self) -> None:
        self.client.cancel_task(self.task_id)

    def _download_first_result(self, query_data: dict) -> Path:
        results = query_data.get("results") or []
        if not results:
            raise RunningHubTaskFailed(
                f"task {self.task_id} SUCCESS 但 results 为空")
        first = results[0]
        url = first.get("url")
        if not url:
            raise RunningHubTaskFailed(
                f"task {self.task_id} results[0] 无 url 字段")
        ext = "." + (first.get("outputType") or "mp4").lower().lstrip(".")
        dest = (self.spec.output_dir
                / f"{self.spec.filename_prefix}_{self.task_id}{ext}")
        return self.client.download_file(url, dest)
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_runninghub_submit.py -v
```

Expected: 19 passed (9 prior + 10 new)

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_runninghub_submit.py
git commit -m "feat(runninghub): add LTXTaskHandle.wait_for_result and cancel"
```

---

## Task 10: `Config` 扩展 + `.env.example` 追加 + 持久化测试

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `tests/test_config.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_config.py` 末尾追加：

```python
# ---------- RunningHub 字段持久化 ----------

def test_config_default_runninghub_fields(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.runninghub_api_key == ""
    assert cfg.runninghub_workflow_id == ""
    assert cfg.runninghub_submit_mode == "inline"
    assert cfg.runninghub_base_url == "https://www.runninghub.cn"
    assert cfg.runninghub_template_path == ""
    assert cfg.video_output_dir == ""


def test_config_loads_runninghub_api_key_from_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RUNNINGHUB_API_KEY=k-from-env\n", encoding="utf-8")
    cfg = load_config(env_path=env_file,
                       settings_path=tmp_path / "settings.json")
    assert cfg.runninghub_api_key == "k-from-env"


def test_config_loads_runninghub_base_url_from_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RUNNINGHUB_BASE_URL=https://other.x\n",
                          encoding="utf-8")
    cfg = load_config(env_path=env_file,
                       settings_path=tmp_path / "settings.json")
    assert cfg.runninghub_base_url == "https://other.x"


def test_config_settings_overrides_env_for_runninghub_api_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RUNNINGHUB_API_KEY=from-env\n", encoding="utf-8")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        '{"runninghub_api_key": "from-settings"}', encoding="utf-8")
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.runninghub_api_key == "from-settings"


def test_config_settings_loads_all_runninghub_fields(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        '{"runninghub_workflow_id": "wf-1",'
        ' "runninghub_submit_mode": "id",'
        ' "runninghub_template_path": "/x/tpl.json",'
        ' "video_output_dir": "/x/out"}',
        encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=settings_file)
    assert cfg.runninghub_workflow_id == "wf-1"
    assert cfg.runninghub_submit_mode == "id"
    assert cfg.runninghub_template_path == "/x/tpl.json"
    assert cfg.video_output_dir == "/x/out"


def test_config_update_settings_persists_runninghub_fields(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(
        runninghub_api_key="new-key",
        runninghub_submit_mode="id",
        video_output_dir="/x/v",
    )
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["runninghub_api_key"] == "new-key"
    assert data["runninghub_submit_mode"] == "id"
    assert data["video_output_dir"] == "/x/v"
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_config.py -v -k runninghub
```

Expected: `AttributeError: 'Config' object has no attribute 'runninghub_api_key'`

- [ ] **Step 3: 扩展 `app/config.py` Config dataclass**

打开 `app/config.py`。在 `Config` 的 `split_resample_defaults` 字段之后追加 6 个字段：

```python
    runninghub_api_key: str = ""
    runninghub_workflow_id: str = ""
    runninghub_submit_mode: str = "inline"       # "inline" 或 "id"
    runninghub_base_url: str = "https://www.runninghub.cn"
    runninghub_template_path: str = ""           # 空 = 用内置 app/templates/ltx_director_v23.json
    video_output_dir: str = ""                   # 空 = 用 state.output_dir
```

- [ ] **Step 4: 扩展 `update_settings` 落盘白名单**

在 `update_settings` 方法的 `data = {...}` dict 末尾（紧接 `split_resample_defaults` 之后）追加：

```python
                "runninghub_api_key": self.runninghub_api_key,
                "runninghub_workflow_id": self.runninghub_workflow_id,
                "runninghub_submit_mode": self.runninghub_submit_mode,
                "runninghub_base_url": self.runninghub_base_url,
                "runninghub_template_path": self.runninghub_template_path,
                "video_output_dir": self.video_output_dir,
```

- [ ] **Step 5: 扩展 `load_config` 读 .env**

在 `load_config` 中已有的 OPENAI_COMPAT_ENDPOINTS 循环之后、`cfg = Config(...)` 构造之前，添加：

```python
    # RunningHub
    rh_api_key = env.get("RUNNINGHUB_API_KEY") or ""
    rh_base_url = env.get("RUNNINGHUB_BASE_URL") or "https://www.runninghub.cn"
```

然后在 `Config(...)` 构造调用里加 2 个 keyword（在 `settings_path=` 那行之前）：

```python
        runninghub_api_key=rh_api_key,
        runninghub_base_url=rh_base_url,
```

- [ ] **Step 6: 扩展 `load_config` 读 settings.json**

在 `if "split_resample_defaults" in data and isinstance(...)...` 块之后追加：

```python
                for key in ("runninghub_api_key", "runninghub_workflow_id",
                            "runninghub_submit_mode", "runninghub_base_url",
                            "runninghub_template_path", "video_output_dir"):
                    if key in data and isinstance(data[key], str):
                        setattr(cfg, key, data[key])
```

- [ ] **Step 7: 追加 `.env.example`**

打开 `.env.example`，在文件末尾追加：

```env

# === RunningHub（远端 SaaS，用于 LTX 视频生成）===
RUNNINGHUB_API_KEY=
RUNNINGHUB_BASE_URL=https://www.runninghub.cn
```

- [ ] **Step 8: 运行验证 PASS**

```bash
pytest tests/test_config.py -v -k runninghub
```

Expected: 6 passed

完整 test_config 不应 regress：

```bash
pytest tests/test_config.py -v
```

Expected: 18 passed (12 prior + 6 new)

- [ ] **Step 9: Commit**

```bash
git add app/config.py .env.example tests/test_config.py
git commit -m "feat(config): persist runninghub_* and video_output_dir fields"
```

---

## Task 11: `resolve_api_key` / `resolve_template_path` / `resolve_video_output_dir`

**Files:**
- Modify: `app/providers/runninghub.py`
- Modify: `tests/test_providers/test_runninghub_submit.py`

- [ ] **Step 1: 写 failing tests**

在 `tests/test_providers/test_runninghub_submit.py` 末尾追加：

```python
# ---------- resolve_ helpers ----------

from app.providers.runninghub import (
    resolve_api_key, resolve_template_path, resolve_video_output_dir,
)


class _FakeCfg:
    def __init__(self, **kwargs):
        defaults = {
            "runninghub_api_key": "",
            "runninghub_template_path": "",
            "video_output_dir": "",
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_resolve_api_key_from_cfg():
    cfg = _FakeCfg(runninghub_api_key="from-cfg")
    assert resolve_api_key(cfg) == "from-cfg"


def test_resolve_api_key_raises_when_missing():
    cfg = _FakeCfg(runninghub_api_key="")
    with pytest.raises(RunningHubUnavailable, match="RUNNINGHUB_API_KEY"):
        resolve_api_key(cfg)


def test_resolve_template_path_uses_builtin_when_cfg_empty():
    cfg = _FakeCfg(runninghub_template_path="")
    p = resolve_template_path(cfg)
    assert p.name == "ltx_director_v23.json"
    assert p.exists()


def test_resolve_template_path_uses_cfg_override(tmp_path):
    custom = tmp_path / "my.json"
    custom.write_text('{"46": {"class_type": "X"}}')
    cfg = _FakeCfg(runninghub_template_path=str(custom))
    assert resolve_template_path(cfg) == custom


def test_resolve_template_path_raises_when_cfg_path_missing(tmp_path):
    cfg = _FakeCfg(runninghub_template_path=str(tmp_path / "absent.json"))
    with pytest.raises(RunningHubInvalidSpec, match="不存在"):
        resolve_template_path(cfg)


def test_resolve_video_output_dir_uses_cfg(tmp_path):
    cfg = _FakeCfg(video_output_dir=str(tmp_path / "v"))
    assert resolve_video_output_dir(cfg, None) == tmp_path / "v"


def test_resolve_video_output_dir_falls_back_to_state(tmp_path):
    cfg = _FakeCfg(video_output_dir="")
    assert resolve_video_output_dir(cfg, tmp_path) == tmp_path


def test_resolve_video_output_dir_raises_when_both_missing():
    cfg = _FakeCfg(video_output_dir="")
    with pytest.raises(RunningHubInvalidSpec, match="视频输出目录"):
        resolve_video_output_dir(cfg, None)
```

- [ ] **Step 2: 运行验证 FAIL**

```bash
pytest tests/test_providers/test_runninghub_submit.py -v -k resolve
```

Expected: `ImportError: cannot import name 'resolve_api_key'`

- [ ] **Step 3: 在 `app/providers/runninghub.py` 末尾追加 3 个 resolve 函数**

```python
def resolve_api_key(cfg) -> str:
    """settings.json 中已合并的 cfg.runninghub_api_key > 报错。

    .env / settings.json 的优先级合并由 load_config 在加载时完成；
    本函数只读取最终态字段。
    """
    if getattr(cfg, "runninghub_api_key", ""):
        return cfg.runninghub_api_key
    raise RunningHubUnavailable(
        "未配置 RUNNINGHUB_API_KEY（.env 或 settings.json）")


def resolve_template_path(cfg) -> Path:
    """cfg.runninghub_template_path 自定义 > 项目内置 app/templates/ltx_director_v23.json。"""
    custom = getattr(cfg, "runninghub_template_path", "")
    if custom:
        p = Path(custom)
        if not p.exists():
            raise RunningHubInvalidSpec(
                f"settings.json 指定的模板不存在: {p}")
        return p
    builtin = (Path(__file__).resolve().parent.parent
               / "templates" / "ltx_director_v23.json")
    if not builtin.exists():
        raise RunningHubInvalidSpec(f"内置模板缺失: {builtin}")
    return builtin


def resolve_video_output_dir(cfg, state_output_dir: Path | None) -> Path:
    """cfg.video_output_dir > state_output_dir > 报错。"""
    custom = getattr(cfg, "video_output_dir", "")
    if custom:
        return Path(custom)
    if state_output_dir:
        return state_output_dir
    raise RunningHubInvalidSpec(
        "未设置视频输出目录（settings.video_output_dir 或 state.output_dir 至少一个）")
```

- [ ] **Step 4: 运行验证 PASS**

```bash
pytest tests/test_providers/test_runninghub_submit.py -v -k resolve
```

Expected: 8 passed

完整 runninghub 测试不应 regress：

```bash
pytest tests/test_providers/test_runninghub_client.py tests/test_providers/test_ltx_task_builder.py tests/test_providers/test_runninghub_submit.py -v
```

Expected: 92 passed (26 + 40 + 19 + 8 - 1 重复计数 + 字段总和会略有差异；目标是无 FAIL)

实际由 pytest 收集决定，关键是没有 FAIL。

- [ ] **Step 5: Commit**

```bash
git add app/providers/runninghub.py tests/test_providers/test_runninghub_submit.py
git commit -m "feat(runninghub): add resolve_api_key / resolve_template_path / resolve_video_output_dir helpers"
```

---

## Task 12: 整体回归 + 手工冒烟说明

**Files:** 仅运行测试，无代码修改。

- [ ] **Step 1: 全量回归**

```bash
pytest -v 2>&1 | tail -10
```

Expected: 全部通过（应为 ~190+ tests，含 split-resample 项目的 102 + 子项目 A 新增 ~90）。

- [ ] **Step 2: 在分支末尾用 git log 确认 commit 颗粒**

```bash
git log --oneline main..feat/video-gen
```

Expected: 11 commits（Task 1-11 各 1 个 commit），message 都符合 conventional commit 格式。

- [ ] **Step 3: 手工冒烟（**必须**由你执行）**

A 子项目是纯库，无 UI，冒烟靠 Python REPL 跑一次端到端，验证真实 API 通路。前提：

- 在 `.env` 里配置 `RUNNINGHUB_API_KEY=<你的 key>`
- RunningHub 账号有积分

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
/root/miniconda3/envs/UniRig/bin/python -c "
from pathlib import Path
from app.config import load_config
from app.providers.runninghub import (
    RunningHubClient, LTXTaskBuilder, LTXSegment, LTXDirectorSpec,
    submit_ltx_task, resolve_api_key, resolve_template_path,
)

cfg = load_config()
api_key = resolve_api_key(cfg)
tpl = resolve_template_path(cfg)

# 准备测试图片（任选一张本地 PNG，宽高需匹配模板默认 1280×720 比例）
test_img = Path('/path/to/test.png')   # 改成你的真实测试图
assert test_img.exists(), f'放一张测试图到 {test_img}'

out_dir = Path('./output/runninghub_smoke')
out_dir.mkdir(parents=True, exist_ok=True)

spec = LTXDirectorSpec(
    global_prompt='cinematic test scene',
    segments=(LTXSegment(local_prompt='test seg', length=24, image_path=test_img),),
    frame_rate=24,
    output_dir=out_dir,
    filename_prefix='smoke_test',
)

with RunningHubClient(api_key, base_url=cfg.runninghub_base_url) as client:
    builder = LTXTaskBuilder(tpl)
    handle = submit_ltx_task(client, spec, builder, mode='inline',
                              upload_progress_cb=lambda d, t, p: print(f'  上传 {d}/{t}: {p.name}'))
    print(f'task_id = {handle.task_id}')
    mp4 = handle.wait_for_result(
        timeout=600, poll_interval=8,
        progress_cb=lambda s: print(f'  状态: {s}'))
    print(f'OK: {mp4}')
"
```

Expected: 终端打印上传进度 → task_id → 状态变化 → 最终 `OK: /path/to/smoke_test_<tid>.mp4`。

- [ ] **Step 4: 若冒烟失败，根据错误类型反查**

| 错误 | 可能原因 | 检查 |
|---|---|---|
| `RunningHubUnavailable: 未配置 RUNNINGHUB_API_KEY` | .env 没填或路径错 | `cat .env \| grep RUNNINGHUB` |
| `RunningHubUploadError` HTTP 401 | API key 错 | RunningHub 后台重新生成 key |
| `RunningHubTaskFailed code=805 ...node_errors` | 模板节点不被 RunningHub 支持 | 看 errorMessage 给出的具体节点 |
| `RunningHubTaskFailed timeout` | 任务超过 600s 没出来 | 拉长 timeout 或检查 RunningHub 队列 |
| MP4 下载完是 0 字节 | results[0].url 临时签名失效 | 重跑一次 |

- [ ] **Step 5: 冒烟通过后报告**

把 `task_id` + MP4 路径 + 总耗时报回（在群里 / PR 里）。子项目 A 算完成，可以进入子项目 B（视频生成面板 UI）的 brainstorming。

---

## Self-Review

完成 Tasks 1–12 后做最终 review（这是你自己跑的检查项，非新任务）：

- [ ] `pytest -v` 全部通过
- [ ] 设计 spec §2 所有 10 条决策都有对应任务实现
- [ ] 设计 spec §11 验收标准 6 条全部满足
- [ ] `git log --oneline main..feat/video-gen` 看到 11 commits（Task 1-11 各 1）
- [ ] `app/templates/ltx_director_v23.json` 进 git
- [ ] 模板节点 id 常量 `LTXNodes` 集中维护，未来模板变只改一处
- [ ] `RunningHubClient` 5 个 endpoint 全部用 `with` / `close()` 释放（context manager 测试覆盖）
- [ ] 手工冒烟通过（至少 1 段图片，inline 模式）
