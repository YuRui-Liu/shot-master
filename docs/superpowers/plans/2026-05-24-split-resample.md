# 拆图重采样 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SplitPanel 增加可选「重采样」后处理（比例预设 + 长边像素 + LANCZOS/AI 超分），AI 档调本机 ComfyUI HTTP API，失败自动回退 LANCZOS。

**Architecture:** 数据模型/后处理逻辑落在 `app/grid_ops.py`（纯函数 `resize_tile`），ComfyUI 客户端独立到 `app/providers/comfyui_upscaler.py`，UI 控件抽成 `app/ui/widgets/resample_group.py`。SplitPanel 只做装配。shot-master 包不动。

**Tech Stack:** Python 3.10+, PySide6, Pillow (LANCZOS), httpx (新增依赖，ComfyUI HTTP)。测试用 pytest + monkeypatch mock httpx；不引入 pytest-qt。

**Spec:** `docs/superpowers/specs/2026-05-24-split-resample-design.md`

---

## File Structure

新增 / 修改文件清单：

| 文件 | 操作 | 职责 |
|---|---|---|
| `app/grid_ops.py` | 修改 | 加 `ResampleAlgo` / `ResampleSpec` / `_resize_to_long_edge` / `resize_tile` / `validate_resample_spec` |
| `app/providers/comfyui_upscaler.py` | 新增 | `ComfyUIUpscaler` 客户端 + `ComfyUIUnavailable` / `ComfyUIUpscaleError` |
| `app/config.py` | 修改 | 加 `comfyui_url` / `split_resample_defaults` 字段 + 扩 `update_settings` 落盘白名单 |
| `app/ui/widgets/resample_group.py` | 新增 | `ResampleGroup` QWidget（控件组 + 模型懒加载） |
| `app/ui/panels/split_panel.py` | 修改 | 嵌入 `ResampleGroup`；execute 串新逻辑 |
| `pyproject.toml` | 修改 | 加 `httpx>=0.27` |
| `tests/test_grid_ops.py` | 修改 | 加 `resize_tile` / `_resize_to_long_edge` / `validate_resample_spec` 用例 |
| `tests/test_providers/test_comfyui_upscaler.py` | 新增 | mock httpx 单测 ComfyUI 客户端 |
| `tests/test_config.py` | 修改 | 加 `comfyui_url` / `split_resample_defaults` 持久化用例 |

**注：** Spec §5.5 提到的"设置页 ComfyUI URL 行 + 测试连接按钮"依赖尚未实现的 SettingsDialog（spec 2026-05-17）。本计划只把 `comfyui_url` 落到 `config.py` 层，UI 入口暂由 ResampleGroup 内的🔄按钮兼任（功能等价：连不上就提示）。SettingsDialog 落地时再把这一行作为它的子任务加进去。

---

## Task 1: 数据模型 `ResampleAlgo` + `ResampleSpec`

**Files:**
- Modify: `app/grid_ops.py`（顶部加 dataclass 与 Enum）
- Test: `tests/test_grid_ops.py`（追加用例）

- [ ] **Step 1: Write the failing test**

在 `tests/test_grid_ops.py` 文件末尾追加：

```python
from app.grid_ops import ResampleAlgo, ResampleSpec


def test_resample_spec_defaults_are_disabled_auto_lanczos():
    spec = ResampleSpec()
    assert spec.enabled is False
    assert spec.aspect_w == 0 and spec.aspect_h == 0
    assert spec.long_edge == 2048
    assert spec.algorithm == ResampleAlgo.LANCZOS
    assert spec.ai_model == ""


def test_resample_spec_is_auto_aspect_when_either_zero():
    assert ResampleSpec(aspect_w=0, aspect_h=0).is_auto_aspect
    assert ResampleSpec(aspect_w=16, aspect_h=0).is_auto_aspect
    assert ResampleSpec(aspect_w=0, aspect_h=9).is_auto_aspect
    assert not ResampleSpec(aspect_w=16, aspect_h=9).is_auto_aspect


def test_resample_spec_is_frozen():
    import dataclasses
    spec = ResampleSpec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.enabled = True


def test_resample_algo_enum_values():
    assert ResampleAlgo.LANCZOS.value == "lanczos"
    assert ResampleAlgo.AI.value == "ai"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_grid_ops.py::test_resample_spec_defaults_are_disabled_auto_lanczos -v
```

Expected: `ImportError: cannot import name 'ResampleAlgo' from 'app.grid_ops'`

- [ ] **Step 3: Add dataclass/enum to `app/grid_ops.py`**

在 `app/grid_ops.py` 文件顶部（`from __future__ import annotations` 之后，其他 import 之前）插入：

```python
from dataclasses import dataclass
from enum import Enum


class ResampleAlgo(str, Enum):
    LANCZOS = "lanczos"
    AI = "ai"


@dataclass(frozen=True)
class ResampleSpec:
    """拆图重采样后处理规格。enabled=False 时其他字段被忽略。"""
    enabled: bool = False
    aspect_w: int = 0           # 0 = 跟随原图（与 aspect_h=0 同义 Auto）
    aspect_h: int = 0
    long_edge: int = 2048
    algorithm: ResampleAlgo = ResampleAlgo.LANCZOS
    ai_model: str = ""

    @property
    def is_auto_aspect(self) -> bool:
        return self.aspect_w == 0 or self.aspect_h == 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_grid_ops.py -v -k resample_spec
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/grid_ops.py tests/test_grid_ops.py
git commit -m "feat(grid_ops): add ResampleSpec dataclass and ResampleAlgo enum"
```

---

## Task 2: `_resize_to_long_edge` 辅助函数

**Files:**
- Modify: `app/grid_ops.py`（追加私有函数）
- Test: `tests/test_grid_ops.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_grid_ops.py` 文件末尾追加：

```python
from PIL import Image
from app.grid_ops import _resize_to_long_edge


def test_resize_to_long_edge_upsample_landscape():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    out = _resize_to_long_edge(img, 2048, Image.LANCZOS)
    assert out.size == (2048, 1024)


def test_resize_to_long_edge_upsample_portrait():
    img = Image.new("RGB", (512, 1024), (128, 128, 128))
    out = _resize_to_long_edge(img, 2048, Image.LANCZOS)
    assert out.size == (1024, 2048)


def test_resize_to_long_edge_downsample():
    img = Image.new("RGB", (4096, 2048), (128, 128, 128))
    out = _resize_to_long_edge(img, 1024, Image.LANCZOS)
    assert out.size == (1024, 512)


def test_resize_to_long_edge_noop_when_already_target():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    out = _resize_to_long_edge(img, 1024, Image.LANCZOS)
    assert out is img    # 同一对象，未触发 resize


def test_resize_to_long_edge_square():
    img = Image.new("RGB", (1000, 1000), (128, 128, 128))
    out = _resize_to_long_edge(img, 500, Image.LANCZOS)
    assert out.size == (500, 500)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_grid_ops.py -v -k resize_to_long_edge
```

Expected: `ImportError` 或 `AttributeError: module 'app.grid_ops' has no attribute '_resize_to_long_edge'`

- [ ] **Step 3: Add helper to `app/grid_ops.py`**

在 `app/grid_ops.py` 末尾追加：

```python
def _resize_to_long_edge(img: Image.Image, long_edge: int, resample) -> Image.Image:
    """按 max(w,h)==long_edge 等比缩放。已经满足则返回同一对象。"""
    w, h = img.size
    if max(w, h) == long_edge:
        return img
    scale = long_edge / max(w, h)
    return img.resize((round(w * scale), round(h * scale)), resample)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_grid_ops.py -v -k resize_to_long_edge
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/grid_ops.py tests/test_grid_ops.py
git commit -m "feat(grid_ops): add _resize_to_long_edge helper"
```

---

## Task 3: `resize_tile` LANCZOS 路径（无 AI）

**Files:**
- Modify: `app/grid_ops.py`（追加公开函数）
- Test: `tests/test_grid_ops.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_grid_ops.py` 末尾追加：

```python
from app.grid_ops import resize_tile


def test_resize_tile_disabled_passthrough():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    spec = ResampleSpec(enabled=False)
    out = resize_tile(img, spec)
    assert out is img


def test_resize_tile_lanczos_auto_aspect_just_resizes():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    spec = ResampleSpec(enabled=True, long_edge=2048,
                        algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (2048, 1024)


def test_resize_tile_lanczos_crops_then_resizes_16_9_from_4_3():
    # 1200x900 (4:3) → center crop 16:9 → 1200x675 → long_edge 1600 → 1600x900
    img = Image.new("RGB", (1200, 900), (128, 128, 128))
    spec = ResampleSpec(enabled=True, aspect_w=16, aspect_h=9,
                        long_edge=1600, algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (1600, 900)


def test_resize_tile_lanczos_crops_1_1_from_landscape():
    img = Image.new("RGB", (1920, 1080), (128, 128, 128))
    spec = ResampleSpec(enabled=True, aspect_w=1, aspect_h=1,
                        long_edge=512, algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (512, 512)


def test_resize_tile_lanczos_custom_3_2():
    img = Image.new("RGB", (1000, 1000), (128, 128, 128))
    spec = ResampleSpec(enabled=True, aspect_w=3, aspect_h=2,
                        long_edge=600, algorithm=ResampleAlgo.LANCZOS)
    out = resize_tile(img, spec)
    assert out.size == (600, 400)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_grid_ops.py -v -k resize_tile
```

Expected: `ImportError`

- [ ] **Step 3: Implement `resize_tile` (LANCZOS-only branch)**

在 `app/grid_ops.py` 顶部 import 区追加：

```python
from typing import Callable, Optional
from shot_master.core.aspect_ops import center_crop_to_aspect
```

确保已 import `AspectRatio`（已存在 `from shot_master.core.specs import ... AspectRatio ...`）。

在 `_resize_to_long_edge` 上方追加：

```python
def resize_tile(tile: Image.Image,
                spec: ResampleSpec,
                upscaler: Optional["ComfyUIUpscaler"] = None,
                status_cb: Optional[Callable[[str], None]] = None,
                ) -> Image.Image:
    """重采样后处理：可选中心裁剪 + 选定算法缩放到 long_edge。

    spec.enabled=False 直接返回原图。
    spec.algorithm=AI 时尝试 ComfyUI 超分，失败回退 LANCZOS 并通过 status_cb 提示。
    最终都用 LANCZOS 把长边压/拉到 spec.long_edge（AI 输出通常 4× 需收尾）。
    """
    if not spec.enabled:
        return tile

    if not spec.is_auto_aspect:
        tile = center_crop_to_aspect(
            tile, AspectRatio(spec.aspect_w, spec.aspect_h))

    if spec.algorithm == ResampleAlgo.AI and upscaler is not None:
        # AI 分支在 Task 7 接入，目前未达此条件
        pass

    return _resize_to_long_edge(tile, spec.long_edge, Image.LANCZOS)
```

> 注：目前 `upscaler` 形参保留但未使用；Task 7 接入实际调用。`"ComfyUIUpscaler"` 用字符串占位类型注解避免循环 import。

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_grid_ops.py -v -k resize_tile
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/grid_ops.py tests/test_grid_ops.py
git commit -m "feat(grid_ops): add resize_tile with LANCZOS path"
```

---

## Task 4: 添加 `httpx` 依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 httpx 到 dependencies**

打开 `pyproject.toml`，在 `dependencies = [...]` 列表中添加 `"httpx>=0.27",`（按字母序插在合适位置，例如 `dashscope` 行后）。

修改后的 dependencies 块（仅展示完整块）：

```toml
dependencies = [
    "PySide6>=6.6",
    "python-dotenv>=1.0",
    "Pillow>=10.0",
    "numpy>=1.24",
    "pyyaml>=6.0",
    "google-genai>=0.3",
    "openai>=1.30",
    "anthropic>=0.30",
    "dashscope>=1.17",
    "httpx>=0.27",
    "shot-master @ file:../../shot-master",
]
```

- [ ] **Step 2: 安装新依赖**

```bash
pip install -e .
```

Expected: 输出包含 `Successfully installed ... httpx-0.27.x ...` 或 `Requirement already satisfied: httpx`。

- [ ] **Step 3: 验证可 import**

```bash
python -c "import httpx; print(httpx.__version__)"
```

Expected: 打印 `0.27.x` 之类的版本号。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add httpx>=0.27 for ComfyUI HTTP client"
```

---

## Task 5: `ComfyUIUpscaler.list_models()` + 异常类

**Files:**
- Create: `app/providers/comfyui_upscaler.py`
- Create: `tests/test_providers/test_comfyui_upscaler.py`

- [ ] **Step 1: Write the failing tests**

新建 `tests/test_providers/test_comfyui_upscaler.py`：

```python
"""ComfyUIUpscaler 单测（mock httpx，不连真实服务）。"""
from __future__ import annotations

import httpx
import pytest

from app.providers.comfyui_upscaler import (
    ComfyUIUpscaler, ComfyUIUnavailable,
)


def _mock_transport(handler):
    """构造 httpx MockTransport，把所有请求交给 handler 处理。"""
    return httpx.MockTransport(handler)


@pytest.fixture
def fake_object_info():
    """ComfyUI /object_info/UpscaleModelLoader 标准响应（按真实 API 形状）。"""
    return {
        "UpscaleModelLoader": {
            "input": {
                "required": {
                    "model_name": [
                        ["4x-UltraSharp.pth", "RealESRGAN_x4plus.pth", "ESRGAN_4x.pth"]
                    ]
                }
            }
        }
    }


def test_list_models_happy_path(fake_object_info, monkeypatch):
    def handler(req):
        assert req.method == "GET"
        assert req.url.path == "/object_info/UpscaleModelLoader"
        return httpx.Response(200, json=fake_object_info)

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    assert up.list_models() == [
        "4x-UltraSharp.pth", "RealESRGAN_x4plus.pth", "ESRGAN_4x.pth"]


def test_list_models_empty_when_node_missing(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={})    # 不含 UpscaleModelLoader

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    assert up.list_models() == []


def test_list_models_raises_unavailable_on_connect_error(monkeypatch):
    def handler(req):
        raise httpx.ConnectError("Connection refused")

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    with pytest.raises(ComfyUIUnavailable):
        up.list_models()


def test_list_models_raises_unavailable_on_5xx(monkeypatch):
    def handler(req):
        return httpx.Response(500, text="ComfyUI internal error")

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    with pytest.raises(ComfyUIUnavailable):
        up.list_models()


def test_base_url_trailing_slash_normalized():
    up = ComfyUIUpscaler("http://test:8188/")
    assert up.base_url == "http://test:8188"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_providers/test_comfyui_upscaler.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.providers.comfyui_upscaler'`

- [ ] **Step 3: Create `app/providers/comfyui_upscaler.py`**

新建文件，写入：

```python
"""ComfyUI HTTP API 客户端：upscale 模型探测 + 上采样工作流提交。

独立于 vision providers——vision 是文本生成、upscale 是图像生成，本质不同路径。
"""
from __future__ import annotations

import httpx


class ComfyUIUnavailable(Exception):
    """ComfyUI 不可达 / 探测失败。调用方应回退 LANCZOS。"""


class ComfyUIUpscaleError(Exception):
    """工作流执行失败（model_not_found / timeout / bad_response）。回退 LANCZOS。"""


class ComfyUIUpscaler:
    def __init__(self, base_url: str, timeout: int = 120):
        """
        Args:
            base_url: ComfyUI 根 URL，如 http://127.0.0.1:8188
            timeout: history 轮询的整体上限秒数；单次 HTTP 请求超时按 10s。
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=10.0)

    def list_models(self) -> list[str]:
        """GET /object_info/UpscaleModelLoader → upscale_model_name 选项列表。

        连接/解析失败抛 ComfyUIUnavailable；JSON 缺节点返回 []。
        """
        url = f"{self.base_url}/object_info/UpscaleModelLoader"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ComfyUIUnavailable(f"GET {url} 失败: {e}") from e

        try:
            return list(data["UpscaleModelLoader"]["input"]["required"]["model_name"][0])
        except (KeyError, TypeError, IndexError):
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_providers/test_comfyui_upscaler.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/providers/comfyui_upscaler.py tests/test_providers/test_comfyui_upscaler.py
git commit -m "feat(providers): add ComfyUIUpscaler.list_models + exceptions"
```

---

## Task 6: `ComfyUIUpscaler.upscale()`

**Files:**
- Modify: `app/providers/comfyui_upscaler.py`
- Modify: `tests/test_providers/test_comfyui_upscaler.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_providers/test_comfyui_upscaler.py` 末尾追加：

```python
import io
import json
from PIL import Image

from app.providers.comfyui_upscaler import ComfyUIUpscaleError


def _png_bytes(w=64, h=64, color=(100, 100, 100)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


class _ComfyUIScenario:
    """可编程的 ComfyUI mock 响应序列。"""

    def __init__(self, history_responses):
        self.history_responses = list(history_responses)
        self.upload_calls = []
        self.prompt_calls = []
        self.history_calls = 0
        self.view_calls = []

    def handler(self, req):
        path = req.url.path
        if path == "/upload/image":
            self.upload_calls.append(req)
            return httpx.Response(200, json={
                "name": "spb_uploaded.png", "subfolder": "", "type": "input"})
        if path == "/prompt":
            self.prompt_calls.append(req)
            return httpx.Response(200, json={"prompt_id": "test-prompt-1"})
        if path.startswith("/history/"):
            idx = min(self.history_calls, len(self.history_responses) - 1)
            self.history_calls += 1
            return httpx.Response(200, json=self.history_responses[idx])
        if path == "/view":
            self.view_calls.append(req)
            return httpx.Response(200, content=_png_bytes(256, 256),
                                   headers={"Content-Type": "image/png"})
        return httpx.Response(404)


def _make_upscaler_with_scenario(scenario, timeout=2):
    up = ComfyUIUpscaler("http://test:8188", timeout=timeout)
    up._client = httpx.Client(transport=httpx.MockTransport(scenario.handler))
    return up


def _outputs_ready():
    return {
        "test-prompt-1": {
            "outputs": {
                "4": {"images": [
                    {"filename": "spb_upscale_001.png",
                     "subfolder": "", "type": "output"}
                ]}
            }
        }
    }


def test_upscale_happy_path():
    scen = _ComfyUIScenario([_outputs_ready()])
    up = _make_upscaler_with_scenario(scen)
    img = Image.new("RGB", (64, 64), (1, 2, 3))
    out = up.upscale(img, "4x-UltraSharp.pth")
    assert isinstance(out, Image.Image)
    assert out.size == (256, 256)
    assert len(scen.upload_calls) == 1
    assert len(scen.prompt_calls) == 1
    assert len(scen.view_calls) == 1


def test_upscale_polls_until_outputs_present():
    scen = _ComfyUIScenario([
        {"test-prompt-1": {}},                # 第 1 次空
        {"test-prompt-1": {}},                # 第 2 次空
        _outputs_ready(),                     # 第 3 次有 outputs
    ])
    up = _make_upscaler_with_scenario(scen)
    img = Image.new("RGB", (64, 64))
    up.upscale(img, "4x-UltraSharp.pth")
    assert scen.history_calls == 3


def test_upscale_timeout_raises_upscale_error(monkeypatch):
    # history 始终为空 → 超过 timeout 抛错
    scen = _ComfyUIScenario([{"test-prompt-1": {}}])
    up = _make_upscaler_with_scenario(scen, timeout=1)
    img = Image.new("RGB", (64, 64))
    with pytest.raises(ComfyUIUpscaleError) as exc_info:
        up.upscale(img, "4x-UltraSharp.pth")
    assert "timeout" in str(exc_info.value).lower()


def test_upscale_model_not_found_in_prompt_response(monkeypatch):
    def handler(req):
        if req.url.path == "/upload/image":
            return httpx.Response(200, json={
                "name": "spb_uploaded.png", "subfolder": "", "type": "input"})
        if req.url.path == "/prompt":
            return httpx.Response(400, json={
                "error": {"message": "Value not in list: model_name: 'wrong.pth'"},
                "node_errors": {}})
        return httpx.Response(404)

    up = ComfyUIUpscaler("http://test:8188")
    up._client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ComfyUIUpscaleError) as exc_info:
        up.upscale(Image.new("RGB", (64, 64)), "wrong.pth")
    assert "model" in str(exc_info.value).lower() or "400" in str(exc_info.value)


def test_upscale_uses_unique_filename_per_call():
    seen = []

    def handler(req):
        if req.url.path == "/upload/image":
            # 解析 multipart 取出 filename 段（粗略：找 'filename="...png"'）
            body = req.read().decode("latin-1", errors="ignore")
            import re
            m = re.search(r'filename="([^"]+)"', body)
            if m:
                seen.append(m.group(1))
            return httpx.Response(200, json={
                "name": seen[-1], "subfolder": "", "type": "input"})
        if req.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p"})
        if req.url.path.startswith("/history/"):
            return httpx.Response(200, json={
                "p": {"outputs": {
                    "4": {"images": [{"filename": "out.png",
                                       "subfolder": "", "type": "output"}]}}}})
        if req.url.path == "/view":
            return httpx.Response(200, content=_png_bytes(),
                                   headers={"Content-Type": "image/png"})
        return httpx.Response(404)

    up = ComfyUIUpscaler("http://test:8188")
    up._client = httpx.Client(transport=httpx.MockTransport(handler))
    img = Image.new("RGB", (32, 32))
    up.upscale(img, "m.pth")
    up.upscale(img, "m.pth")
    assert len(seen) == 2
    assert seen[0] != seen[1]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_providers/test_comfyui_upscaler.py -v -k upscale
```

Expected: `AttributeError: 'ComfyUIUpscaler' object has no attribute 'upscale'`

- [ ] **Step 3: Implement `upscale` and helpers**

在 `app/providers/comfyui_upscaler.py` 顶部 import 区追加：

```python
import io
import time
import uuid
from PIL import Image
```

在 `ComfyUIUpscaler` 类中追加方法：

```python
    def upscale(self, image: Image.Image, model_name: str) -> Image.Image:
        """提交 4 节点 upscale workflow → 轮询 history → 下载结果。

        连接失败抛 ComfyUIUnavailable；执行失败抛 ComfyUIUpscaleError。
        """
        uploaded = self._upload(image)
        prompt_id = self._submit(self._build_workflow(uploaded, model_name))
        entry = self._wait(prompt_id)
        try:
            out_info = entry["outputs"]["4"]["images"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise ComfyUIUpscaleError(f"bad_response: outputs 结构异常: {e}") from e
        return self._fetch_image(out_info["filename"],
                                  out_info.get("subfolder", ""),
                                  out_info.get("type", "output"))

    def _upload(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, "PNG")
        buf.seek(0)
        filename = f"spb_{uuid.uuid4().hex}.png"
        files = {"image": (filename, buf, "image/png")}
        data = {"type": "input", "overwrite": "true"}
        try:
            resp = self._client.post(f"{self.base_url}/upload/image",
                                       files=files, data=data)
            resp.raise_for_status()
            return resp.json()["name"]
        except httpx.HTTPError as e:
            raise ComfyUIUnavailable(f"upload 失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise ComfyUIUpscaleError(f"bad_response upload: {e}") from e

    def _build_workflow(self, uploaded_name: str, model_name: str) -> dict:
        return {
            "1": {"class_type": "LoadImage",
                  "inputs": {"image": uploaded_name}},
            "2": {"class_type": "UpscaleModelLoader",
                  "inputs": {"model_name": model_name}},
            "3": {"class_type": "ImageUpscaleWithModel",
                  "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
            "4": {"class_type": "SaveImage",
                  "inputs": {"filename_prefix": "spb_upscale",
                              "images": ["3", 0]}},
        }

    def _submit(self, workflow: dict) -> str:
        client_id = f"spb-{uuid.uuid4().hex}"
        try:
            resp = self._client.post(f"{self.base_url}/prompt",
                                       json={"prompt": workflow,
                                             "client_id": client_id})
            if resp.status_code >= 400:
                # ComfyUI 在 model 不存在时返回 400 + JSON body
                raise ComfyUIUpscaleError(
                    f"model_not_found 或参数错（HTTP {resp.status_code}）: "
                    f"{resp.text[:300]}")
            return resp.json()["prompt_id"]
        except httpx.HTTPError as e:
            raise ComfyUIUnavailable(f"submit 失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise ComfyUIUpscaleError(f"bad_response submit: {e}") from e

    def _wait(self, prompt_id: str) -> dict:
        deadline = time.time() + self.timeout
        url = f"{self.base_url}/history/{prompt_id}"
        while time.time() < deadline:
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                data = resp.json()
                entry = data.get(prompt_id)
                if entry and entry.get("outputs"):
                    return entry
            except httpx.HTTPError as e:
                raise ComfyUIUnavailable(f"history 轮询失败: {e}") from e
            except ValueError as e:
                raise ComfyUIUpscaleError(f"bad_response history: {e}") from e
            time.sleep(0.5)
        raise ComfyUIUpscaleError(f"timeout: history {self.timeout}s 无 outputs")

    def _fetch_image(self, filename: str, subfolder: str, type_: str) -> Image.Image:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        try:
            resp = self._client.get(f"{self.base_url}/view", params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ComfyUIUnavailable(f"view 下载失败: {e}") from e
        try:
            return Image.open(io.BytesIO(resp.content))
        except Exception as e:
            raise ComfyUIUpscaleError(f"bad_response view: 解码失败 {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_providers/test_comfyui_upscaler.py -v
```

Expected: 10 passed（5 原有 + 5 新增）

- [ ] **Step 5: Commit**

```bash
git add app/providers/comfyui_upscaler.py tests/test_providers/test_comfyui_upscaler.py
git commit -m "feat(providers): implement ComfyUIUpscaler.upscale workflow"
```

---

## Task 7: `resize_tile` 接入 AI 路径 + 回退逻辑

**Files:**
- Modify: `app/grid_ops.py`
- Modify: `tests/test_grid_ops.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_grid_ops.py` 末尾追加：

```python
from unittest.mock import MagicMock
from app.providers.comfyui_upscaler import (
    ComfyUIUpscaler, ComfyUIUnavailable, ComfyUIUpscaleError,
)


def test_resize_tile_ai_calls_upscaler_then_resizes():
    img = Image.new("RGB", (1024, 1024), (128, 128, 128))
    up = MagicMock(spec=ComfyUIUpscaler)
    up.upscale.return_value = Image.new("RGB", (4096, 4096), (200, 200, 200))
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="4x-UltraSharp.pth")
    out = resize_tile(img, spec, upscaler=up)
    up.upscale.assert_called_once_with(img, "4x-UltraSharp.pth")
    assert out.size == (2048, 2048)


def test_resize_tile_ai_unavailable_falls_back_to_lanczos():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    up = MagicMock(spec=ComfyUIUpscaler)
    up.upscale.side_effect = ComfyUIUnavailable("connection refused")
    statuses = []
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="x.pth")
    out = resize_tile(img, spec, upscaler=up, status_cb=statuses.append)
    assert out.size == (2048, 1024)
    assert len(statuses) == 1
    assert "回退" in statuses[0]


def test_resize_tile_ai_upscale_error_falls_back_to_lanczos():
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    up = MagicMock(spec=ComfyUIUpscaler)
    up.upscale.side_effect = ComfyUIUpscaleError("timeout")
    statuses = []
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="x.pth")
    out = resize_tile(img, spec, upscaler=up, status_cb=statuses.append)
    assert out.size == (2048, 1024)
    assert len(statuses) == 1


def test_resize_tile_ai_without_upscaler_falls_through_to_lanczos():
    # algorithm=AI 但 upscaler=None 时直接走 LANCZOS（不调任何 ai api）
    img = Image.new("RGB", (1024, 512), (128, 128, 128))
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI,
                        long_edge=2048, ai_model="x.pth")
    out = resize_tile(img, spec, upscaler=None)
    assert out.size == (2048, 1024)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_grid_ops.py -v -k "ai"
```

Expected: `test_resize_tile_ai_calls_upscaler_then_resizes` 失败（mock 未被调用，因为 AI 分支是 `pass`）。

- [ ] **Step 3: Implement AI branch**

在 `app/grid_ops.py` 中**替换** `resize_tile` 的 AI 分支 `pass` 这段：

```python
    if spec.algorithm == ResampleAlgo.AI and upscaler is not None:
        # AI 分支在 Task 7 接入，目前未达此条件
        pass
```

替换为：

```python
    if spec.algorithm == ResampleAlgo.AI and upscaler is not None:
        try:
            tile = upscaler.upscale(tile, spec.ai_model)
        except Exception as e:
            # 捕获 ComfyUIUnavailable / ComfyUIUpscaleError（以及兜底的其他异常）
            if status_cb:
                status_cb(f"AI 超分不可用，已回退 LANCZOS：{e}")
            # 继续走下面的 LANCZOS 收尾
```

> 注：用宽 `except Exception` 而非具名异常类型——避免让 `grid_ops` 模块在 import 时强依赖 `comfyui_upscaler`（如果未来 ComfyUI 客户端被替换或重命名）。具名异常类型在 `comfyui_upscaler.py` 已定义但 grid_ops 不引入，靠"任何异常都回退"的语义兜底。

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_grid_ops.py -v -k "ai"
```

Expected: 4 passed

```bash
pytest tests/test_grid_ops.py -v
```

Expected: 全部通过（含 Task 1-3 + 7 的所有用例）

- [ ] **Step 5: Commit**

```bash
git add app/grid_ops.py tests/test_grid_ops.py
git commit -m "feat(grid_ops): wire AI upscale branch with LANCZOS fallback"
```

---

## Task 8: `validate_resample_spec` 纯函数

**Files:**
- Modify: `app/grid_ops.py`
- Modify: `tests/test_grid_ops.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_grid_ops.py` 末尾追加：

```python
from app.grid_ops import validate_resample_spec


def test_validate_resample_disabled_always_ok():
    assert validate_resample_spec(ResampleSpec(enabled=False)) == (True, "")


def test_validate_resample_auto_aspect_lanczos_ok():
    spec = ResampleSpec(enabled=True, aspect_w=0, aspect_h=0,
                        long_edge=2048, algorithm=ResampleAlgo.LANCZOS)
    assert validate_resample_spec(spec) == (True, "")


def test_validate_resample_custom_aspect_zero_fails():
    spec = ResampleSpec(enabled=True, aspect_w=0, aspect_h=9,
                        long_edge=2048, algorithm=ResampleAlgo.LANCZOS)
    # 注意：aspect_w=0,aspect_h=9 视为 Auto（is_auto_aspect=True），所以 OK
    assert validate_resample_spec(spec) == (True, "")
    # 但若声明 enabled + 用户期望"自定义"模式：调用方应保证 w>0 且 h>0
    # validate 不区分 preset/custom，只看数值合法性


def test_validate_resample_ai_without_model_fails():
    spec = ResampleSpec(enabled=True, algorithm=ResampleAlgo.AI, ai_model="")
    ok, msg = validate_resample_spec(spec)
    assert ok is False
    assert "AI 超分模型" in msg


def test_validate_resample_long_edge_too_small_fails():
    spec = ResampleSpec(enabled=True, long_edge=100)
    ok, msg = validate_resample_spec(spec)
    assert ok is False
    assert "256" in msg and "8192" in msg


def test_validate_resample_long_edge_too_large_fails():
    spec = ResampleSpec(enabled=True, long_edge=10000)
    ok, msg = validate_resample_spec(spec)
    assert ok is False


def test_validate_resample_long_edge_boundaries_ok():
    assert validate_resample_spec(
        ResampleSpec(enabled=True, long_edge=256))[0] is True
    assert validate_resample_spec(
        ResampleSpec(enabled=True, long_edge=8192))[0] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_grid_ops.py -v -k validate_resample
```

Expected: `ImportError: cannot import name 'validate_resample_spec'`

- [ ] **Step 3: Implement `validate_resample_spec`**

在 `app/grid_ops.py` 中（紧跟 `ResampleSpec` 类定义之后）追加：

```python
def validate_resample_spec(spec: ResampleSpec) -> tuple[bool, str]:
    """校验 ResampleSpec 字段合法性，返回 (ok, error_message)。

    enabled=False → 直接 True。
    enabled=True 时：
      - long_edge 必须在 256..8192 闭区间
      - algorithm=AI 时必须有 ai_model
    aspect 字段不在此校验——Auto(0,0) 与有效比例都允许。
    UI 层需自行确保「自定义」模式下 w>0 且 h>0。
    """
    if not spec.enabled:
        return True, ""
    if not (256 <= spec.long_edge <= 8192):
        return False, f"长边须在 256–8192 范围内（当前 {spec.long_edge}）"
    if spec.algorithm == ResampleAlgo.AI and not spec.ai_model:
        return False, "请选择 AI 超分模型"
    return True, ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_grid_ops.py -v -k validate_resample
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/grid_ops.py tests/test_grid_ops.py
git commit -m "feat(grid_ops): add validate_resample_spec pure validator"
```

---

## Task 9: `Config` 扩展 + 持久化

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

打开 `tests/test_config.py`，在末尾追加：

```python
def test_config_default_comfyui_url(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.comfyui_url == "http://127.0.0.1:8188"


def test_config_default_split_resample_defaults(tmp_path):
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    d = cfg.split_resample_defaults
    assert d["enabled"] is False
    assert d["aspect_w"] == 1 and d["aspect_h"] == 1
    assert d["long_edge"] == 2048
    assert d["algorithm"] == "lanczos"
    assert d["ai_model"] == ""


def test_config_loads_comfyui_url_from_settings(tmp_path):
    sp = tmp_path / "settings.json"
    sp.write_text('{"comfyui_url": "http://other:1234"}', encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.comfyui_url == "http://other:1234"


def test_config_loads_split_resample_defaults_from_settings(tmp_path):
    sp = tmp_path / "settings.json"
    sp.write_text(
        '{"split_resample_defaults": {"enabled": true, "long_edge": 1024, '
        '"aspect_w": 16, "aspect_h": 9, "algorithm": "ai", '
        '"ai_model": "x.pth"}}',
        encoding="utf-8")
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.split_resample_defaults["enabled"] is True
    assert cfg.split_resample_defaults["long_edge"] == 1024
    assert cfg.split_resample_defaults["ai_model"] == "x.pth"


def test_config_update_settings_persists_comfyui_and_resample(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    cfg.update_settings(
        comfyui_url="http://x:9999",
        split_resample_defaults={
            "enabled": True, "aspect_w": 1, "aspect_h": 1,
            "long_edge": 2048, "algorithm": "lanczos", "ai_model": ""})
    import json
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["comfyui_url"] == "http://x:9999"
    assert data["split_resample_defaults"]["enabled"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v -k "comfyui or resample"
```

Expected: `AttributeError: 'Config' object has no attribute 'comfyui_url'`

- [ ] **Step 3: Extend `Config` dataclass**

在 `app/config.py` 的 `Config` dataclass 中，在 `last_output_dir` 字段之后追加两行：

```python
    comfyui_url: str = "http://127.0.0.1:8188"
    split_resample_defaults: dict = field(default_factory=lambda: {
        "enabled": False, "aspect_w": 1, "aspect_h": 1,
        "long_edge": 2048, "algorithm": "lanczos", "ai_model": "",
    })
```

- [ ] **Step 4: 扩展 `update_settings` 落盘白名单**

把 `update_settings` 方法里的 `data` dict 替换为：

```python
            data = {
                "current_provider": self.current_provider,
                "current_model": self.current_model,
                "ui": self.ui,
                "last_input_dir": self.last_input_dir,
                "last_output_dir": self.last_output_dir,
                "comfyui_url": self.comfyui_url,
                "split_resample_defaults": self.split_resample_defaults,
            }
```

- [ ] **Step 5: 扩展 `load_config` 读取逻辑**

在 `load_config` 函数中、`settings_path.exists()` 块内 `if "last_output_dir" in data:` 这一行后追加：

```python
                if "comfyui_url" in data:
                    cfg.comfyui_url = data["comfyui_url"]
                if "split_resample_defaults" in data and isinstance(
                        data["split_resample_defaults"], dict):
                    cfg.split_resample_defaults.update(
                        data["split_resample_defaults"])
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v -k "comfyui or resample"
```

Expected: 5 passed

```bash
pytest tests/test_config.py -v
```

Expected: 全部已有 + 新加用例都通过

- [ ] **Step 7: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): persist comfyui_url and split_resample_defaults"
```

---

## Task 10: `ResampleGroup` QWidget

**Files:**
- Create: `app/ui/widgets/resample_group.py`

> **测试豁免：** 本项目不引入 pytest-qt，UI widget 不写单测；下一个 Task 通过 SplitPanel 集成 + 手工冒烟验证。

- [ ] **Step 1: 新建 `app/ui/widgets/resample_group.py`**

```python
"""ResampleGroup: 拆图重采样控件组（启用开关 + 比例 + 长边 + 算法 + AI 模型）。"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QFormLayout, QCheckBox,
    QComboBox, QSpinBox, QPushButton, QWidget, QLabel, QMessageBox,
)

from app.grid_ops import ResampleAlgo, ResampleSpec


# 比例预设：(显示名, w, h)；w=h=0 表示「跟随原图」（Auto）
ASPECT_PRESETS = [
    ("跟随原图", 0, 0),
    ("1:1", 1, 1),
    ("16:9", 16, 9),
    ("9:16", 9, 16),
    ("自定义", -1, -1),    # -1 哨兵；选中时从 w/h spin 读
]


class ResampleGroup(QGroupBox):
    """重采样控件组。发出 specChanged 让外部刷新 validate 状态。"""

    specChanged = Signal()

    def __init__(self,
                 list_models_fn: Callable[[], list[str]],
                 initial: Optional[dict] = None,
                 parent=None):
        """
        Args:
            list_models_fn: 无参函数，返回 upscaler 模型名列表；失败抛异常。
                由外部注入（通常是 lambda: ComfyUIUpscaler(cfg.comfyui_url).list_models()）。
            initial: 从 settings.json 读出的初始字段 dict。
        """
        super().__init__("重采样", parent)
        self._list_models_fn = list_models_fn
        self._models_loaded = False

        v = QVBoxLayout(self)

        self.enable_cb = QCheckBox("启用重采样")
        v.addWidget(self.enable_cb)

        form = QFormLayout()

        # 比例行：下拉 + (w):(h) 两个 spin（仅"自定义"时显示）
        aspect_row = QHBoxLayout()
        self.aspect_combo = QComboBox()
        for label, _, _ in ASPECT_PRESETS:
            self.aspect_combo.addItem(label)
        self.aspect_w = QSpinBox(); self.aspect_w.setRange(1, 9999); self.aspect_w.setValue(1)
        self.aspect_h = QSpinBox(); self.aspect_h.setRange(1, 9999); self.aspect_h.setValue(1)
        self.aspect_colon = QLabel(":")
        aspect_row.addWidget(self.aspect_combo, 1)
        aspect_row.addWidget(self.aspect_w)
        aspect_row.addWidget(self.aspect_colon)
        aspect_row.addWidget(self.aspect_h)
        aspect_w_h = QWidget(); aspect_w_h.setLayout(aspect_row)
        form.addRow("比例", aspect_w_h)

        # 长边
        self.long_edge = QSpinBox()
        self.long_edge.setRange(256, 8192)
        self.long_edge.setSingleStep(64)
        self.long_edge.setValue(2048)
        self.long_edge.setSuffix(" px")
        form.addRow("长边", self.long_edge)

        # 算法
        self.algo_combo = QComboBox()
        self.algo_combo.addItem("LANCZOS", ResampleAlgo.LANCZOS)
        self.algo_combo.addItem("AI 超分", ResampleAlgo.AI)
        form.addRow("算法", self.algo_combo)

        # AI 模型 + 刷新按钮（仅 AI 档显示）
        ai_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(200)
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setMaximumWidth(40)
        self.refresh_btn.setToolTip("从 ComfyUI 重新拉取 upscale 模型列表")
        ai_row.addWidget(self.model_combo, 1)
        ai_row.addWidget(self.refresh_btn)
        self.ai_row_widget = QWidget(); self.ai_row_widget.setLayout(ai_row)
        form.addRow("AI 模型", self.ai_row_widget)

        v.addLayout(form)

        # 初始状态
        self._set_form_enabled(False)
        self._on_aspect_changed(self.aspect_combo.currentText())
        self._on_algo_changed(self.algo_combo.currentText())

        # 信号
        self.enable_cb.toggled.connect(self._set_form_enabled)
        self.enable_cb.toggled.connect(lambda _: self.specChanged.emit())
        self.aspect_combo.currentTextChanged.connect(self._on_aspect_changed)
        self.aspect_combo.currentTextChanged.connect(lambda _: self.specChanged.emit())
        self.aspect_w.valueChanged.connect(lambda _: self.specChanged.emit())
        self.aspect_h.valueChanged.connect(lambda _: self.specChanged.emit())
        self.long_edge.valueChanged.connect(lambda _: self.specChanged.emit())
        self.algo_combo.currentTextChanged.connect(self._on_algo_changed)
        self.algo_combo.currentTextChanged.connect(lambda _: self.specChanged.emit())
        self.model_combo.currentTextChanged.connect(lambda _: self.specChanged.emit())
        self.refresh_btn.clicked.connect(self._force_refresh_models)

        # 应用 initial
        if initial:
            self.set_from_dict(initial)

    def _set_form_enabled(self, on: bool):
        for w in (self.aspect_combo, self.aspect_w, self.aspect_h, self.aspect_colon,
                  self.long_edge, self.algo_combo, self.model_combo, self.refresh_btn):
            w.setEnabled(on)
        if on:
            self._on_aspect_changed(self.aspect_combo.currentText())
            self._on_algo_changed(self.algo_combo.currentText())

    def _on_aspect_changed(self, text: str):
        is_custom = (text == "自定义")
        self.aspect_w.setVisible(is_custom)
        self.aspect_h.setVisible(is_custom)
        self.aspect_colon.setVisible(is_custom)

    def _on_algo_changed(self, text: str):
        is_ai = (text == "AI 超分")
        self.ai_row_widget.setVisible(is_ai)
        if is_ai and not self._models_loaded:
            self._lazy_load_models()

    def _lazy_load_models(self):
        self._models_loaded = True    # 即使失败也只懒加载一次（用户点🔄强刷）
        try:
            models = self._list_models_fn()
        except Exception as e:
            self.model_combo.clear()
            QMessageBox.warning(self, "ComfyUI 不可达",
                                f"无法拉取 upscale 模型列表：{e}\n\n"
                                "你可以手动在下拉框输入模型文件名（如 4x-UltraSharp.pth），"
                                "或点🔄按钮重试。")
            return
        self._populate_models(models)

    def _force_refresh_models(self):
        self._models_loaded = False
        self._lazy_load_models()

    def _populate_models(self, models: list[str]):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if current and current in models:
            self.model_combo.setCurrentText(current)
        elif models:
            self.model_combo.setCurrentIndex(0)

    # ----- 与外部交换数据 -----

    def get_spec(self) -> ResampleSpec:
        text = self.aspect_combo.currentText()
        if text == "跟随原图":
            w, h = 0, 0
        elif text == "自定义":
            w, h = self.aspect_w.value(), self.aspect_h.value()
        else:
            for label, pw, ph in ASPECT_PRESETS:
                if label == text:
                    w, h = pw, ph
                    break
            else:
                w, h = 0, 0
        algo = self.algo_combo.currentData()
        if algo is None:
            algo = ResampleAlgo.LANCZOS
        return ResampleSpec(
            enabled=self.enable_cb.isChecked(),
            aspect_w=w, aspect_h=h,
            long_edge=self.long_edge.value(),
            algorithm=algo,
            ai_model=self.model_combo.currentText().strip(),
        )

    def to_dict(self) -> dict:
        s = self.get_spec()
        return {
            "enabled": s.enabled,
            "aspect_w": s.aspect_w, "aspect_h": s.aspect_h,
            "long_edge": s.long_edge,
            "algorithm": s.algorithm.value,
            "ai_model": s.ai_model,
        }

    def set_from_dict(self, d: dict):
        self.enable_cb.setChecked(bool(d.get("enabled", False)))
        w, h = int(d.get("aspect_w", 1)), int(d.get("aspect_h", 1))
        # 匹配预设
        matched = False
        for label, pw, ph in ASPECT_PRESETS:
            if (pw, ph) == (w, h):
                self.aspect_combo.setCurrentText(label)
                matched = True
                break
        if not matched:
            self.aspect_combo.setCurrentText("自定义")
            self.aspect_w.setValue(max(w, 1))
            self.aspect_h.setValue(max(h, 1))
        self.long_edge.setValue(int(d.get("long_edge", 2048)))
        algo_str = d.get("algorithm", "lanczos")
        for i in range(self.algo_combo.count()):
            if self.algo_combo.itemData(i).value == algo_str:
                self.algo_combo.setCurrentIndex(i)
                break
        self.model_combo.setEditText(d.get("ai_model", ""))
```

- [ ] **Step 2: 手工冒烟（仅语法编译检查，无 UI 弹出）**

```bash
python -c "from app.ui.widgets.resample_group import ResampleGroup; print('OK')"
```

Expected: 打印 `OK`，无 import 错误。

- [ ] **Step 3: Commit**

```bash
git add app/ui/widgets/resample_group.py
git commit -m "feat(ui): add ResampleGroup widget with lazy model loading"
```

---

## Task 11: `SplitPanel` 接入 ResampleGroup + 执行链改造

**Files:**
- Modify: `app/ui/panels/split_panel.py`

- [ ] **Step 1: 修改 import 区**

在 `app/ui/panels/split_panel.py` 顶部 imports 块替换为（删除已有的 import 并整体重写头部）：

```python
"""拆图面板：网格参数 + 白边/网格一键检测 + 可选重采样 + 批量拆。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QPushButton, QHBoxLayout, QMessageBox,
)

from shot_master.core.border_detector import detect_borders, infer_grid
from shot_master.core.saver import save_image as sm_save_image

from app.config import Config
from app.grid_ops import (
    make_grid_spec, split_to_tiles,
    ResampleSpec, ResampleAlgo, resize_tile, validate_resample_spec,
)
from app.providers.comfyui_upscaler import ComfyUIUpscaler
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.widgets.resample_group import ResampleGroup
from app.ui.worker import FunctionWorker
```

- [ ] **Step 2: 在 `__init__` 中嵌入 `ResampleGroup`**

在 `__init__` 方法里、`root.addWidget(mar)` 之后、`out = QGroupBox("输出")` 之前插入：

```python
        self.resample = ResampleGroup(
            list_models_fn=lambda: ComfyUIUpscaler(
                cfg.comfyui_url).list_models(),
            initial=cfg.split_resample_defaults,
        )
        self.resample.specChanged.connect(self.validityChanged)
        root.addWidget(self.resample)
```

- [ ] **Step 3: 扩展 `validate`**

替换 `validate` 方法为：

```python
    def validate(self) -> tuple[bool, str]:
        if not self.state.selected_paths():
            return False, "请先选图"
        if not self.state.output_dir:
            return False, "请先设置输出目录"
        sr, sc = self.src_rows.value(), self.src_cols.value()
        br, bc = self.sub_rows.value(), self.sub_cols.value()
        if sr % br != 0 or sc % bc != 0:
            return False, f"子图 {br}×{bc} 必须整除源图 {sr}×{sc}"
        # 重采样校验
        rspec = self.resample.get_spec()
        ok, msg = validate_resample_spec(rspec)
        if not ok:
            return False, msg
        # 自定义比例时强校验 w/h>0（validate_resample_spec 不做这层）
        if rspec.enabled and self.resample.aspect_combo.currentText() == "自定义":
            if rspec.aspect_w <= 0 or rspec.aspect_h <= 0:
                return False, "请填写自定义比例（w 和 h 都需 >0）"
        return True, ""
```

- [ ] **Step 4: 替换 `execute` 方法**

把整个 `execute` 方法替换为：

```python
    def execute(self):
        paths = self.state.selected_paths()
        spec = make_grid_spec(
            self.src_rows.value(), self.src_cols.value(),
            self.sub_rows.value(), self.sub_cols.value(),
            self.m_top.value(), self.m_right.value(),
            self.m_bottom.value(), self.m_left.value(),
            self.gap.value(),
        )
        rspec = self.resample.get_spec()
        out_dir = self.state.output_dir
        fmt = self.fmt.currentText()
        ext = ".png" if fmt.upper() == "PNG" else ".jpg"

        # 持久化当前重采样默认值
        self.cfg.update_settings(
            split_resample_defaults=self.resample.to_dict())

        # AI 档才构造 upscaler
        upscaler = None
        if rspec.enabled and rspec.algorithm == ResampleAlgo.AI:
            upscaler = ComfyUIUpscaler(self.cfg.comfyui_url)

        status_emit = self.statusMessage.emit
        seen_statuses: set[str] = set()

        def dedupe_status(msg: str):
            if msg not in seen_statuses:
                seen_statuses.add(msg)
                status_emit(msg)

        def task():
            out_dir.mkdir(parents=True, exist_ok=True)
            total = 0
            ai_total = 0
            ai_fallback = 0
            for src_path in paths:
                tiles = split_to_tiles(src_path, spec)
                for i, tile in enumerate(tiles):
                    if rspec.enabled and rspec.algorithm == ResampleAlgo.AI:
                        ai_total += 1
                        before = len(seen_statuses)
                        resized = resize_tile(
                            tile, rspec, upscaler=upscaler,
                            status_cb=dedupe_status)
                        if len(seen_statuses) > before:
                            ai_fallback += 1
                    else:
                        resized = resize_tile(tile, rspec)
                    out_path = out_dir / f"{src_path.stem}_{i+1}{ext}"
                    sm_save_image(resized, out_path, fmt)
                    total += 1
            return {"total": total, "ai_total": ai_total,
                    "ai_fallback": ai_fallback}

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "拆图失败", e))
        self._worker.start()

    def _on_done(self, result):
        n = result["total"]
        ai_fb = result["ai_fallback"]
        ai_total = result["ai_total"]
        msg = f"已拆出 {n} 张"
        if ai_fb:
            msg += f"\n（其中 {ai_fb}/{ai_total} 张因超分失败回退 LANCZOS）"
        QMessageBox.information(self, "完成", msg)
```

> **注：** 删除原 `execute` 顶部 `from app.grid_ops import split_to_files`（已不用）。如果旧 import 在文件其他位置仍存在，整体清理。

- [ ] **Step 5: 编译检查**

```bash
python -c "from app.ui.panels.split_panel import SplitPanel; print('OK')"
```

Expected: 打印 `OK`。

- [ ] **Step 6: 跑全部测试确保未破坏现有用例**

```bash
pytest -v
```

Expected: 全部通过（除已知与本次无关的失败外）。

- [ ] **Step 7: Commit**

```bash
git add app/ui/panels/split_panel.py
git commit -m "feat(split-panel): integrate ResampleGroup with AI fallback + writeback"
```

---

## Task 12: 手工冒烟清单

> **执行者注：** 本任务无自动化测试，**必须**人工跑过 7 项再勾完成。

- [ ] **冒烟 1：默认行为不变（重采样关闭）**
  启动 `./run.sh`；选一张多宫格图 + 输出目录；不勾"启用重采样"；点执行；输出文件应与改造前完全等价（尺寸、命名、格式）。

- [ ] **冒烟 2：LANCZOS 比例+长边**
  勾"启用重采样"；比例 `16:9`；长边 `1600`；算法 `LANCZOS`；执行；验证输出文件全部为 1600×900。

- [ ] **冒烟 3：LANCZOS 自定义比例**
  比例 `自定义` w=7 h=3；长边 `2100`；执行；验证输出 2100×900。

- [ ] **冒烟 4：LANCZOS 长边缩小**
  比例 `跟随原图`；长边 `256`；执行；验证输出长边均为 256。

- [ ] **冒烟 5：AI 超分 - ComfyUI 关闭场景**
  关掉 ComfyUI；切到"AI 超分"算法；🔄 按钮点一下应弹"ComfyUI 不可达"；
  执行拆图任务；应整批顺利完成，状态栏出现 1 次"AI 超分不可用，已回退 LANCZOS"；
  末尾弹窗带 `N/N 张因超分失败回退 LANCZOS`。

- [ ] **冒烟 6：AI 超分 - 正常路径**
  启动 ComfyUI，确保至少装了一个 upscale 模型（如 `4x-UltraSharp.pth`）；
  🔄 拉取模型列表，下拉应出现已安装模型；
  选一个模型，长边 `2048`；
  对一张 4×4 拆 16 张的 2K 大图执行；
  验证输出文件单张分辨率 ≈ 长边 2048（短边按原始比例算）；
  ComfyUI 控制台应能看到 16 次 prompt 执行（每个 tile 一次）。

- [ ] **冒烟 7：默认值持久化**
  在面板设各种值（启用 + 16:9 + 长边 1600 + AI + 某模型）→ 执行；
  关闭程序 → 重启；
  打开拆图面板，验证上述字段全部恢复（启用、比例、长边、算法、AI 模型名）。

- [ ] **完成**：人工 7 项全过 → 在本任务卡上勾选完成。

---

## Self-Review

完成 Tasks 1–12 后做最终 review：

- [ ] `pytest -v` 全部通过
- [ ] 设计 spec §2 所有 12 条决策都有对应任务实现（对照 spec 表格）
- [ ] 设计 spec §9 验收标准 10 条全部满足
- [ ] 无残留 `from app.grid_ops import split_to_files` 这种死 import
- [ ] `git log --oneline` 应看到 ≥10 个 feat/build/docs 提交，颗粒清晰
