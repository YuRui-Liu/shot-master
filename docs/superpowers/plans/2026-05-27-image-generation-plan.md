# 图片生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「图片生成」功能（镜像视频/配音的任务栏+任务窗）：统一界面文/图/图文生图、@参考图、画质/比例/数量、快捷提示词按钮，默认豆包 ARK，provider 可配，RunningHub 占位。

**Architecture:** 纯逻辑层（size 映射 / 快捷词 / provider 抽象+豆包/OpenAI/RunningHub / 任务存储 / config）可单测；UI 层（编辑器/任务窗/任务栏/设置）镜像已存在的配音(dub_*)实现。生成走后台 worker。

**Tech Stack:** Python, httpx, PySide6, 豆包 ARK images/generations。

依据 spec：`docs/superpowers/specs/2026-05-27-image-generation-design.md`。
参考既有同形实现（可读作模板）：`drama_shot_master/ui/panels/dub_panel.py`、`drama_shot_master/ui/windows/dub_task_window.py`、`drama_shot_master/ui/panels/dub_task_manager_panel.py`、`drama_shot_master/ui/dialogs/dub_settings_dialog.py`、`drama_shot_master/core/dub_task_store.py`。
关键事实：`cfg.api_keys.get("doubao","")` 取豆包 key；`FunctionWorker(callable)` → 信号 `finished_with_result(object)` / `failed(str)`，`.start()`；httpx 已是依赖。

---

### Task 1: size 映射 + 快捷提示词（纯逻辑）

**Files:**
- Create: `drama_shot_master/core/imggen_sizes.py`
- Create: `drama_shot_master/core/imggen_presets.py`
- Test: `tests/test_imggen/__init__.py`（空）, `tests/test_imggen/test_sizes_presets.py`

- [ ] **Step 1: 写失败测试**

`tests/test_imggen/__init__.py` 留空。`tests/test_imggen/test_sizes_presets.py`：

```python
from drama_shot_master.core import imggen_sizes as S
from drama_shot_master.core import imggen_presets as P


def test_resolve_size_2k():
    assert S.resolve_size("2K", "16:9") == "2304x1296"
    assert S.resolve_size("2K", "1:1") == "2048x2048"
    assert S.resolve_size("2K", "3:4") == "1728x2304"


def test_resolve_size_1k():
    assert S.resolve_size("1K", "16:9") == "1152x648"
    assert S.resolve_size("1K", "9:16") == "648x1152"


def test_resolve_size_auto_is_none():
    assert S.resolve_size("2K", "自动") is None
    assert S.resolve_size("1K", "自动") is None


def test_quick_prompts():
    labels = [p[0] for p in P.QUICK_PROMPTS]
    assert labels == ["三视图", "人设", "2D", "360°", "3D", "国漫", "特写", "中焦", "广角"]
    d = dict(P.QUICK_PROMPTS)
    assert d["3D"] == "3D建模风格，CG渲染，"
    assert "360度水平无死角" in d["360°"]
    assert d["广角"] == "广角镜头，透视变形，场景开阔，"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_imggen/test_sizes_presets.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 imggen_sizes.py**

```python
"""画质×比例 → 像素 size 字符串。'自动' 返回 None（不向模型指定尺寸）。"""
from __future__ import annotations

QUALITIES = ["2K", "1K"]
RATIOS = ["自动", "1:1", "16:9", "9:16", "4:3", "3:4"]

_SIZES = {
    "2K": {"1:1": "2048x2048", "16:9": "2304x1296", "9:16": "1296x2304",
           "4:3": "2304x1728", "3:4": "1728x2304"},
    "1K": {"1:1": "1024x1024", "16:9": "1152x648", "9:16": "648x1152",
           "4:3": "1152x864", "3:4": "864x1152"},
}


def resolve_size(quality: str, ratio: str) -> str | None:
    if ratio == "自动":
        return None
    return _SIZES.get(quality, _SIZES["2K"]).get(ratio)
```

- [ ] **Step 4: 实现 imggen_presets.py**

```python
"""快捷提示词按钮：(标签, 插入文本)。点击在提示词光标处插入文本。"""
from __future__ import annotations

QUICK_PROMPTS = [
    ("三视图", "三视图（正面、侧面、背面），白色纯色背景，人物角色设计图，"),
    ("人设", "角色人设参考图，白色纯色背景，正面、背面、侧面展示，"),
    ("2D", "2D平面画风，动漫风格，"),
    ("360°", "生成该图的360全景图，360度水平无死角，180度垂直全视角覆盖，"
              "画面完整连贯.首尾无缝衔接，无畸变.无拉伸.无黑边.无裁切"),
    ("3D", "3D建模风格，CG渲染，"),
    ("国漫", "中国漫画风格，线条流畅，"),
    ("特写", "特写镜头，面部细节，"),
    ("中焦", "标准镜头，透视正常，"),
    ("广角", "广角镜头，透视变形，场景开阔，"),
]
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/test_imggen/test_sizes_presets.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/core/imggen_sizes.py drama_shot_master/core/imggen_presets.py tests/test_imggen/__init__.py tests/test_imggen/test_sizes_presets.py
git commit -m "feat(imggen): 画质×比例 size 映射 + 快捷提示词常量"
```

---

### Task 2: Provider 层（抽象 + 豆包/OpenAI/RunningHub + 工厂）

**Files:**
- Create: `drama_shot_master/providers/image_gen.py`
- Test: `tests/test_imggen/test_image_gen.py`

- [ ] **Step 1: 写失败测试**

`tests/test_imggen/test_image_gen.py`：

```python
import base64
import pytest
from drama_shot_master.providers import image_gen as IG


def test_doubao_payload_no_refs():
    p = IG.DoubaoImageProvider("k", "https://ark", "seedream")
    body = p._build_payload("画一只猫", [], size="2304x1296", n=2)
    assert body["model"] == "seedream" and body["prompt"] == "画一只猫"
    assert body["size"] == "2304x1296" and body["n"] == 2
    assert "image" not in body          # 无参考图=文生图


def test_doubao_payload_with_refs(tmp_path):
    img = tmp_path / "r.png"; img.write_bytes(b"\x89PNG\r\n")
    p = IG.DoubaoImageProvider("k", "https://ark", "seedream")
    body = p._build_payload("台词", [img], size=None, n=1)
    assert "size" not in body            # size=None 不带
    assert isinstance(body["image"], list) and len(body["image"]) == 1
    assert body["image"][0].startswith("data:image/png;base64,")


def test_doubao_parse_response():
    raw = base64.b64encode(b"IMGBYTES").decode()
    out = IG.DoubaoImageProvider("k", "u", "m")._parse_response(
        {"data": [{"b64_json": raw}]})
    assert out == [b"IMGBYTES"]


def test_factory_picks_provider():
    class C:
        imggen_provider = "doubao"; imggen_base_url = "https://ark"
        imggen_model = "seedream"; api_keys = {"doubao": "k"}
    assert isinstance(IG.make_image_provider(C()), IG.DoubaoImageProvider)
    C.imggen_provider = "runninghub"
    assert isinstance(IG.make_image_provider(C()), IG.RunningHubImageProvider)


def test_runninghub_stub_raises(tmp_path):
    p = IG.RunningHubImageProvider()
    with pytest.raises(IG.ImageGenError):
        p.generate("x", [], size=None, n=1)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_imggen/test_image_gen.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 image_gen.py**

```python
"""图片生成 provider：抽象 + 豆包(ARK)/OpenAI/RunningHub(占位) + 工厂。"""
from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path

import httpx


class ImageGenError(Exception):
    pass


def _to_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


class ImageGenProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, references: list[Path], *,
                 size: str | None, n: int) -> list[bytes]:
        ...


class DoubaoImageProvider(ImageGenProvider):
    """火山引擎 ARK images/generations（Seedream）。"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = (base_url or "https://ark.cn-beijing.volces.com").rstrip("/")
        self.model = model

    def _build_payload(self, prompt, references, *, size, n) -> dict:
        body: dict = {"model": self.model, "prompt": prompt, "n": n,
                      "response_format": "b64_json"}
        if size:
            body["size"] = size
        if references:
            body["image"] = [_to_data_url(p) for p in references]
        return body

    def _parse_response(self, data: dict) -> list[bytes]:
        items = data.get("data") or []
        out = []
        for it in items:
            b64 = it.get("b64_json")
            if b64:
                out.append(base64.b64decode(b64))
            elif it.get("url"):
                out.append(httpx.get(it["url"], timeout=60).content)
        if not out:
            raise ImageGenError(f"无图片返回: {str(data)[:300]}")
        return out

    def generate(self, prompt, references, *, size, n) -> list[bytes]:
        if not self.api_key:
            raise ImageGenError("未配置豆包 API Key（设置→图片生成）")
        if not self.model:
            raise ImageGenError("未配置图片模型 id（设置→图片生成）")
        url = f"{self.base_url}/api/v3/images/generations"
        try:
            resp = httpx.post(url, json=self._build_payload(
                prompt, references, size=size, n=n),
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"}, timeout=300)
        except httpx.HTTPError as e:
            raise ImageGenError(f"连接失败: {e}") from e
        if resp.status_code >= 400:
            raise ImageGenError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        return self._parse_response(resp.json())


class OpenAIImageProvider(ImageGenProvider):
    """OpenAI images（无参考图=generations，有参考图=edits）。"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.model = model or "gpt-image-1"

    def generate(self, prompt, references, *, size, n) -> list[bytes]:
        if not self.api_key:
            raise ImageGenError("未配置 OpenAI API Key（设置→图片生成）")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            if references:
                files = [("image[]", (Path(p).name, Path(p).read_bytes(),
                          mimetypes.guess_type(str(p))[0] or "image/png"))
                         for p in references]
                data = {"model": self.model, "prompt": prompt, "n": str(n)}
                if size:
                    data["size"] = size
                resp = httpx.post(f"{self.base_url}/v1/images/edits",
                                  data=data, files=files, headers=headers, timeout=300)
            else:
                body = {"model": self.model, "prompt": prompt, "n": n}
                if size:
                    body["size"] = size
                resp = httpx.post(f"{self.base_url}/v1/images/generations",
                                  json=body, headers={**headers,
                                  "Content-Type": "application/json"}, timeout=300)
        except httpx.HTTPError as e:
            raise ImageGenError(f"连接失败: {e}") from e
        if resp.status_code >= 400:
            raise ImageGenError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        out = []
        for it in resp.json().get("data", []):
            if it.get("b64_json"):
                out.append(base64.b64decode(it["b64_json"]))
            elif it.get("url"):
                out.append(httpx.get(it["url"], timeout=60).content)
        if not out:
            raise ImageGenError("无图片返回")
        return out


class RunningHubImageProvider(ImageGenProvider):
    """占位：待提供图片工作流后通过插件接入。"""

    def generate(self, prompt, references, *, size, n) -> list[bytes]:
        raise ImageGenError("RunningHub 图片工作流暂未接入，待提供工作流后通过插件接入")


def make_image_provider(cfg) -> ImageGenProvider:
    prov = getattr(cfg, "imggen_provider", "doubao")
    # 优先用设置里持久化的 imggen_api_key；为空则回退 .env 的 api_keys[prov]
    key = getattr(cfg, "imggen_api_key", "") or (getattr(cfg, "api_keys", {}) or {}).get(prov, "")
    base = getattr(cfg, "imggen_base_url", "")
    model = getattr(cfg, "imggen_model", "")
    if prov == "openai":
        return OpenAIImageProvider(key, base, model)
    if prov == "runninghub":
        return RunningHubImageProvider()
    return DoubaoImageProvider(key, base, model)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_imggen/test_image_gen.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/providers/image_gen.py tests/test_imggen/test_image_gen.py
git commit -m "feat(imggen): ImageGenProvider 抽象 + 豆包/OpenAI/RunningHub(占位) + 工厂"
```

---

### Task 3: 任务存储 ImgGenTaskStore

**Files:**
- Create: `drama_shot_master/core/imggen_task_store.py`
- Test: `tests/test_imggen/test_imggen_task_store.py`

- [ ] **Step 1: 写失败测试**

`tests/test_imggen/test_imggen_task_store.py`：

```python
from drama_shot_master.core.imggen_task_store import ImgGenTask, ImgGenTaskStore


def test_add_get_update_remove():
    s = ImgGenTaskStore()
    t = s.add("出图A", payload={"prompt": "猫", "n": 1})
    assert isinstance(t, ImgGenTask) and s.get(t.id) is t
    s.update(t.id, name="B", last_result="/x/o.png")
    assert s.get(t.id).name == "B" and s.get(t.id).last_result == "/x/o.png"
    s.remove(t.id)
    assert s.get(t.id) is None


def test_duplicate_and_roundtrip():
    s = ImgGenTaskStore()
    t = s.add("A", payload={"prompt": "p", "refs": [{"path": "/a.png", "label": "图1"}]})
    d = s.duplicate(t.id)
    assert d.id != t.id and d.payload == t.payload
    s2 = ImgGenTaskStore.from_list(s.to_list())
    assert [x.name for x in s2.all()] == ["A", "A 副本"]
    assert s2.all()[0].payload["refs"][0]["label"] == "图1"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_imggen/test_imggen_task_store.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 imggen_task_store.py**

```python
"""图片生成任务的类型化存储 + 持久化（镜像 DubTaskStore）。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict

from drama_shot_master.core.video_task_store import _gen_task_id


@dataclass
class ImgGenTask:
    id: str
    name: str
    payload: dict = field(default_factory=dict)
    updated_at: float = 0.0
    last_result: str = ""


class ImgGenTaskStore:
    def __init__(self, tasks: list[ImgGenTask] | None = None):
        self._tasks: list[ImgGenTask] = list(tasks or [])

    def all(self):
        return list(self._tasks)

    def get(self, task_id):
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, *, payload: dict | None = None) -> ImgGenTask:
        t = ImgGenTask(id=_gen_task_id(), name=name,
                       payload=dict(payload or {}), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id, **kw):
        t = self.get(task_id)
        if t is None:
            return
        for k, v in kw.items():
            if hasattr(t, k):
                setattr(t, k, v)
        t.updated_at = time.time()

    def remove(self, task_id):
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def duplicate(self, task_id):
        t = self.get(task_id)
        if t is None:
            return None
        return self.add(f"{t.name} 副本", payload=dict(t.payload))

    def to_list(self):
        return [asdict(t) for t in self._tasks]

    @classmethod
    def from_list(cls, data):
        tasks = [ImgGenTask(id=d.get("id") or _gen_task_id(),
                            name=d.get("name", "图片"),
                            payload=d.get("payload", {}) or {},
                            updated_at=d.get("updated_at", 0.0),
                            last_result=d.get("last_result", ""))
                 for d in (data or [])]
        return cls(tasks)
```

- [ ] **Step 4: 运行确认通过 + 提交**

Run: `python -m pytest tests/test_imggen/test_imggen_task_store.py -q`（2 passed）

```bash
git add drama_shot_master/core/imggen_task_store.py tests/test_imggen/test_imggen_task_store.py
git commit -m "feat(imggen): ImgGenTask/ImgGenTaskStore 类型化任务存储"
```

---

### Task 4: config 图片生成字段

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_imggen/test_imggen_config.py`

- [ ] **Step 1: 写失败测试**

`tests/test_imggen/test_imggen_config.py`：

```python
import json
from drama_shot_master.config import load_config


def test_imggen_config(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.imggen_tasks == []
    assert cfg.imggen_provider == "doubao"
    assert "ark" in cfg.imggen_base_url
    cfg.update_settings(imggen_provider="openai", imggen_model="gpt-image-1",
                        imggen_output_dir="D:/o")
    raw = json.loads(sp.read_text(encoding="utf-8"))
    assert raw["imggen_provider"] == "openai" and raw["imggen_model"] == "gpt-image-1"
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.imggen_provider == "openai" and cfg2.imggen_output_dir == "D:/o"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_imggen/test_imggen_config.py -q`
Expected: FAIL（AttributeError imggen_tasks）

- [ ] **Step 3: 加 config 字段**

`drama_shot_master/config.py` 的 `Config` 字段区（紧接 `dub_sampling` 那组之后）加：

```python
    imggen_tasks: list = field(default_factory=list)
    imggen_provider: str = "doubao"
    imggen_base_url: str = "https://ark.cn-beijing.volces.com"
    imggen_model: str = ""
    imggen_api_key: str = ""
    imggen_output_dir: str = ""
```

`update_settings` 落盘 dict（与 `dub_*` 同块）加：

```python
                "imggen_tasks": self.imggen_tasks,
                "imggen_provider": self.imggen_provider,
                "imggen_base_url": self.imggen_base_url,
                "imggen_model": self.imggen_model,
                "imggen_api_key": self.imggen_api_key,
                "imggen_output_dir": self.imggen_output_dir,
```

`load_config` 读取区（与 `dub_*` 同块）加：

```python
                if "imggen_tasks" in data and isinstance(data["imggen_tasks"], list):
                    cfg.imggen_tasks = data["imggen_tasks"]
                if "imggen_provider" in data and isinstance(data["imggen_provider"], str):
                    cfg.imggen_provider = data["imggen_provider"]
                if "imggen_base_url" in data and isinstance(data["imggen_base_url"], str):
                    cfg.imggen_base_url = data["imggen_base_url"]
                if "imggen_model" in data and isinstance(data["imggen_model"], str):
                    cfg.imggen_model = data["imggen_model"]
                if "imggen_api_key" in data and isinstance(data["imggen_api_key"], str):
                    cfg.imggen_api_key = data["imggen_api_key"]
                if "imggen_output_dir" in data and isinstance(data["imggen_output_dir"], str):
                    cfg.imggen_output_dir = data["imggen_output_dir"]
```

> 说明：`api_keys` 来自 `.env`、`update_settings` 不落盘它；故图片生成的 key 用**独立持久化字段 `imggen_api_key`**，provider 工厂优先用它、为空回退 `.env` 的 `api_keys[prov]`。

- [ ] **Step 4: 运行确认通过（含回归）+ 提交**

Run: `python -m pytest tests/test_imggen/test_imggen_config.py tests/test_config.py -q`（全绿）

```bash
git add drama_shot_master/config.py tests/test_imggen/test_imggen_config.py
git commit -m "feat(imggen): config 增加图片生成任务/provider/base_url/model/输出目录"
```

---

### Task 5: 编辑器 ImgGenPanel

**Files:**
- Create: `drama_shot_master/ui/panels/imggen_panel.py`

UI 任务。先读 `drama_shot_master/ui/panels/dub_panel.py` 作风格参照（信号/worker/授权门用法一致）。

- [ ] **Step 1: 实现 imggen_panel.py**

```python
"""图片生成编辑器：模式自动判定 + 参考图区(@标签) + 画质/比例/数量 + 快捷词 + 生成。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QComboBox, QSpinBox, QScrollArea, QFrame, QInputDialog, QFileDialog,
    QMessageBox, QGridLayout,
)

from drama_shot_master.config import Config
from drama_shot_master.core.imggen_sizes import QUALITIES, RATIOS, resolve_size
from drama_shot_master.core.imggen_presets import QUICK_PROMPTS
from drama_shot_master.providers.image_gen import make_image_provider, ImageGenError
from drama_shot_master.ui.worker import FunctionWorker


class ImgGenPanel(QWidget):
    statusChanged = Signal(str)
    resultReady = Signal(str)
    dirty = Signal()

    def __init__(self, cfg: Config, payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker = None
        self._refs: list[dict] = []     # [{path,label}]
        self._results: list[str] = []
        self._build_ui()
        if payload:
            self.load_payload(payload)
        self._update_mode()

    def _build_ui(self):
        root = QVBoxLayout(self)
        self.mode_lbl = QLabel("模式：文生图")
        self.mode_lbl.setStyleSheet("color:#9aa;")
        root.addWidget(self.mode_lbl)

        # 参考图区
        root.addWidget(QLabel("参考图（点卡片把 @标签 插入提示词）："))
        self.ref_bar = QHBoxLayout()
        add_btn = QPushButton("+ 参考图"); add_btn.clicked.connect(self._add_refs)
        self.ref_bar.addWidget(add_btn)
        self.ref_bar.addStretch(1)
        ref_wrap = QWidget(); ref_wrap.setLayout(self.ref_bar)
        root.addWidget(ref_wrap)

        # 画质/比例/数量
        opt = QHBoxLayout()
        self.quality = QComboBox(); self.quality.addItems(QUALITIES)
        self.ratio = QComboBox(); self.ratio.addItems(RATIOS)
        self.count = QSpinBox(); self.count.setRange(1, 4); self.count.setValue(1)
        for w in (QLabel("画质"), self.quality, QLabel("比例"), self.ratio,
                  QLabel("数量"), self.count):
            opt.addWidget(w)
        opt.addStretch(1)
        root.addLayout(opt)

        # 快捷词按钮
        qrow = QGridLayout()
        for i, (label, text) in enumerate(QUICK_PROMPTS):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, t=text: self._insert(t))
            qrow.addWidget(b, i // 5, i % 5)
        qwrap = QWidget(); qwrap.setLayout(qrow)
        root.addWidget(qwrap)

        self.prompt = QPlainTextEdit(); self.prompt.setPlaceholderText("提示词…")
        self.prompt.textChanged.connect(self._update_mode)
        self.prompt.textChanged.connect(lambda: self.dirty.emit())
        root.addWidget(self.prompt, 1)

        bar = QHBoxLayout()
        self.btn_gen = QPushButton("生成"); self.btn_gen.setObjectName("AccentButton")
        self.btn_gen.clicked.connect(self._generate)
        self.status_lbl = QLabel(""); self.status_lbl.setStyleSheet("color:#888")
        bar.addWidget(self.btn_gen); bar.addWidget(self.status_lbl, 1)
        root.addLayout(bar)

        self.result_row = QHBoxLayout()
        rwrap = QWidget(); rwrap.setLayout(self.result_row)
        root.addWidget(rwrap)
        self._refresh_refs()

    # ---------- 参考图 ----------
    def _add_refs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择参考图", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        for p in paths:
            self._refs.append({"path": p, "label": f"图{len(self._refs)+1}"})
        if paths:
            self._refresh_refs(); self._update_mode(); self.dirty.emit()

    def _refresh_refs(self):
        # 清掉除「+参考图」「stretch」外的卡片（保留 index 0 按钮、末尾 stretch）
        while self.ref_bar.count() > 2:
            it = self.ref_bar.takeAt(1)
            w = it.widget()
            if w:
                w.deleteLater()
        for i, r in enumerate(self._refs):
            self.ref_bar.insertWidget(1 + i, self._ref_card(i, r))

    def _ref_card(self, idx: int, r: dict) -> QWidget:
        card = QFrame(); card.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(card); v.setContentsMargins(4, 4, 4, 4)
        thumb = QLabel(); pm = QPixmap(r["path"])
        if not pm.isNull():
            thumb.setPixmap(pm.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        thumb.setFixedSize(72, 72); thumb.setAlignment(Qt.AlignCenter)
        v.addWidget(thumb)
        lab = QPushButton(f"@{r['label']}")
        lab.clicked.connect(lambda _=False, i=idx: self._insert(f"@{self._refs[i]['label']} "))
        v.addWidget(lab)
        row = QHBoxLayout()
        rn = QPushButton("改名"); rn.clicked.connect(lambda _=False, i=idx: self._rename_ref(i))
        rm = QPushButton("×"); rm.clicked.connect(lambda _=False, i=idx: self._remove_ref(i))
        row.addWidget(rn); row.addWidget(rm)
        v.addLayout(row)
        return card

    def _rename_ref(self, i: int):
        name, ok = QInputDialog.getText(self, "改名", "标签:", text=self._refs[i]["label"])
        if ok and name.strip():
            self._refs[i]["label"] = name.strip()
            self._refresh_refs(); self.dirty.emit()

    def _remove_ref(self, i: int):
        self._refs.pop(i)
        self._refresh_refs(); self._update_mode(); self.dirty.emit()

    def _insert(self, text: str):
        self.prompt.insertPlainText(text)

    def _update_mode(self):
        has_ref = bool(self._refs)
        has_txt = bool(self.prompt.toPlainText().strip())
        mode = ("图文生图" if has_ref and has_txt else
                "图生图" if has_ref else "文生图")
        self.mode_lbl.setText(f"模式：{mode}（自动）")

    # ---------- payload ----------
    def to_payload(self) -> dict:
        return {"prompt": self.prompt.toPlainText(), "refs": list(self._refs),
                "quality": self.quality.currentText(), "ratio": self.ratio.currentText(),
                "n": self.count.value()}

    def load_payload(self, p: dict):
        self.prompt.setPlainText(p.get("prompt", ""))
        self._refs = [dict(r) for r in p.get("refs", []) or []]
        qi = self.quality.findText(p.get("quality", "2K")); self.quality.setCurrentIndex(max(0, qi))
        ri = self.ratio.findText(p.get("ratio", "自动")); self.ratio.setCurrentIndex(max(0, ri))
        self.count.setValue(int(p.get("n", 1) or 1))
        self._refresh_refs(); self._update_mode()

    # ---------- 生成 ----------
    def _generate(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            QMessageBox.warning(self, "需要激活", "授权无效或已过期，无法生成。")
            return
        prompt = self.prompt.toPlainText().strip()
        if not prompt and not self._refs:
            QMessageBox.information(self, "提示", "请填写提示词或添加参考图"); return
        cfg = self.cfg
        size = resolve_size(self.quality.currentText(), self.ratio.currentText())
        n = self.count.value()
        refs = [Path(r["path"]) for r in self._refs]
        out_dir = Path(cfg.imggen_output_dir or ".") / "imggen"
        ts = time.strftime("%Y%m%d_%H%M%S")

        def task():
            provider = make_image_provider(cfg)
            images = provider.generate(prompt, refs, size=size, n=n)
            out_dir.mkdir(parents=True, exist_ok=True)
            paths = []
            for i, data in enumerate(images):
                fp = out_dir / f"img_{ts}_{i+1}.png"
                fp.write_bytes(data)
                paths.append(str(fp))
            return paths

        self.btn_gen.setEnabled(False)
        self.status_lbl.setText("生成中…"); self.statusChanged.emit("RUNNING")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, paths: list):
        self._results = paths
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText(f"完成：{len(paths)} 张")
        self.statusChanged.emit("SUCCESS")
        if paths:
            self.resultReady.emit(paths[0])
        self._show_results(paths)

    def _on_fail(self, err: str):
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText(f"失败：{err}")
        self.statusChanged.emit("FAILED")
        QMessageBox.critical(self, "生成失败", err)

    def _show_results(self, paths: list):
        while self.result_row.count():
            it = self.result_row.takeAt(0); w = it.widget()
            if w:
                w.deleteLater()
        for p in paths:
            lbl = QLabel(); pm = QPixmap(p)
            if not pm.isNull():
                lbl.setPixmap(pm.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl.setToolTip(p)
            self.result_row.addWidget(lbl)
        if paths:
            ob = QPushButton("打开结果"); ob.clicked.connect(lambda: self._open(paths[0]))
            self.result_row.addWidget(ob)
        self.result_row.addStretch(1)

    def _open(self, path: str):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
```

- [ ] **Step 2: 离屏构造校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.config import load_config; from drama_shot_master.ui.panels.imggen_panel import ImgGenPanel; p=ImgGenPanel(load_config()); print('mode', p.mode_lbl.text()); p.load_payload({'prompt':'猫','quality':'2K','ratio':'16:9','n':2,'refs':[]}); print('payload', p.to_payload()['ratio'], p.to_payload()['n']); print('ok')"
```
Expected: 打印 mode、payload 16:9 2、ok，无异常。

- [ ] **Step 3: 提交**

```bash
git add drama_shot_master/ui/panels/imggen_panel.py
git commit -m "feat(ui): 图片生成编辑器 ImgGenPanel(模式自动判定+@参考图+画质/比例/数量+快捷词+生成)"
```

---

### Task 6: 任务窗 + 任务栏

**Files:**
- Create: `drama_shot_master/ui/windows/imggen_task_window.py`
- Create: `drama_shot_master/ui/panels/imggen_task_manager_panel.py`

读 `dub_task_window.py` 与 `dub_task_manager_panel.py` 作模板，把 Dub 换成 ImgGen。

- [ ] **Step 1: imggen_task_window.py**

```python
"""图片生成任务窗：内嵌 ImgGenPanel，转发状态/结果/脏标记/关闭。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.config import Config
from drama_shot_master.core.imggen_task_store import ImgGenTask
from drama_shot_master.ui.panels.imggen_panel import ImgGenPanel
from drama_shot_master.ui.theme import apply_dark_titlebar


class ImgGenTaskWindow(QMainWindow):
    statusChanged = Signal(str, str)
    resultReady = Signal(str, str)
    dirty = Signal(str, dict)
    closed = Signal(str)

    def __init__(self, task: ImgGenTask, cfg: Config, parent=None):
        super().__init__(parent)
        self.task_id = task.id
        self.cfg = cfg
        self.setWindowTitle(f"图片生成 · {task.name}")
        self.resize(720, 780)
        self.panel = ImgGenPanel(cfg, payload=task.payload)
        self.setCentralWidget(self.panel)
        self.panel.statusChanged.connect(lambda s: self.statusChanged.emit(self.task_id, s))
        self.panel.resultReady.connect(lambda p: self.resultReady.emit(self.task_id, p))
        self.panel.dirty.connect(lambda: self.dirty.emit(self.task_id, self.panel.to_payload()))

    def set_title_name(self, name: str):
        self.setWindowTitle(f"图片生成 · {name}")

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_themed", False):
            self._themed = True
            apply_dark_titlebar(self)

    def closeEvent(self, e):
        self.dirty.emit(self.task_id, self.panel.to_payload())
        self.closed.emit(self.task_id)
        super().closeEvent(e)
```

- [ ] **Step 2: imggen_task_manager_panel.py**

复制 `drama_shot_master/ui/panels/dub_task_manager_panel.py` 全文，做如下替换并去掉「模式」列（图片任务无 design/clone 模式）：
- 类名 `DubTaskManagerPanel`→`ImgGenTaskManagerPanel`；`DubTaskStore`→`ImgGenTaskStore`（import 改 `from drama_shot_master.core.imggen_task_store import ImgGenTaskStore`）。
- 表头由 `["名称","模式","状态","最近输出","更新时间"]` 改为 `["名称","状态","最近输出","更新时间"]`（4 列），`refresh()` 里对应去掉 mode 列、列号顺延。
- `_new()`：`self.store.add(name.strip(), payload={"quality":"2K","ratio":"自动","n":1})`（去掉 mode 参数）。
- 其余（新建/打开/复制/删除/重命名、信号 taskRenamed、set_task_status/clear_task_status）保持一致。

> 实现时请逐行核对 dub 版，确保只改上述点；列号顺延别错位。

- [ ] **Step 3: 离屏校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.config import load_config; from drama_shot_master.core.imggen_task_store import ImgGenTaskStore, ImgGenTask; from drama_shot_master.ui.state import AppState; from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel; m=ImgGenTaskManagerPanel(AppState(), load_config(), ImgGenTaskStore(), lambda t:None, lambda i:None, lambda:None); print('mgr ok'); from drama_shot_master.ui.windows.imggen_task_window import ImgGenTaskWindow; w=ImgGenTaskWindow(ImgGenTask(id='1',name='x'), load_config()); print('win ok')"
```
Expected: `mgr ok` / `win ok`。

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/ui/windows/imggen_task_window.py drama_shot_master/ui/panels/imggen_task_manager_panel.py
git commit -m "feat(ui): 图片生成任务窗 + 任务栏"
```

---

### Task 7: 设置对话框 + 菜单

**Files:**
- Create: `drama_shot_master/ui/dialogs/imggen_settings_dialog.py`
- Modify: `drama_shot_master/ui/main_window.py`（设置菜单加「图片生成…」）

- [ ] **Step 1: imggen_settings_dialog.py**

```python
"""图片生成设置：provider / base_url / model / api_key / 输出目录。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QHBoxLayout, QFileDialog, QDialogButtonBox, QWidget, QLabel,
)

from drama_shot_master.config import Config

_PROVIDERS = [("豆包 (ARK)", "doubao"), ("OpenAI", "openai"),
              ("RunningHub (暂未接入)", "runninghub")]


class ImgGenSettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("图片生成设置")
        self.setModal(True)
        self.resize(540, 300)
        root = QVBoxLayout(self)
        f = QFormLayout()
        self.provider = QComboBox()
        for label, key in _PROVIDERS:
            self.provider.addItem(label, key)
        cur = cfg.imggen_provider or "doubao"
        idx = next((i for i, (_l, k) in enumerate(_PROVIDERS) if k == cur), 0)
        self.provider.setCurrentIndex(idx)
        self.base_url = QLineEdit(cfg.imggen_base_url or "")
        self.model = QLineEdit(cfg.imggen_model or "")
        self.model.setPlaceholderText("如豆包 Seedream 模型 id")
        self.api_key = QLineEdit(cfg.imggen_api_key or (cfg.api_keys or {}).get(cur, ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.out_dir = QLineEdit(cfg.imggen_output_dir or "")
        ob = QPushButton("选目录"); ob.clicked.connect(self._pick)
        orow = QHBoxLayout(); orow.addWidget(self.out_dir, 1); orow.addWidget(ob)
        ow = QWidget(); ow.setLayout(orow)
        f.addRow("提供方", self.provider)
        f.addRow("Base URL", self.base_url)
        f.addRow("模型 id", self.model)
        f.addRow("API Key", self.api_key)
        f.addRow("输出目录", ow)
        root.addLayout(f)
        root.addWidget(QLabel("RunningHub 图片工作流暂未接入。"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir.text() or "")
        if d:
            self.out_dir.setText(d)

    def _save(self):
        prov = self.provider.currentData()
        self.cfg.update_settings(
            imggen_provider=prov, imggen_base_url=self.base_url.text().strip(),
            imggen_model=self.model.text().strip(),
            imggen_api_key=self.api_key.text().strip(),
            imggen_output_dir=self.out_dir.text().strip())
        self.accept()
```

> 注：图片生成 key 存独立持久化字段 `imggen_api_key`（Task 4 已加 + 落盘），不走 `api_keys`（那个只从 .env 读、不落盘）。

- [ ] **Step 2: main_window 设置菜单加「图片生成…」**

在设置菜单块（「配音…」`a_dub` 之后）插入：
```python
        a_img = QAction("图片生成…", self)
        a_img.triggered.connect(self._open_imggen_settings)
        sm.addAction(a_img)
```
加方法（`_open_dub_settings` 附近）：
```python
    def _open_imggen_settings(self):
        from drama_shot_master.ui.dialogs.imggen_settings_dialog import ImgGenSettingsDialog
        ImgGenSettingsDialog(self.cfg, parent=self).exec()
```

- [ ] **Step 3: 离屏校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.config import load_config; from drama_shot_master.ui.dialogs.imggen_settings_dialog import ImgGenSettingsDialog; d=ImgGenSettingsDialog(load_config()); print('imggen settings ok')"
```
Expected: `imggen settings ok`。

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/ui/dialogs/imggen_settings_dialog.py drama_shot_master/ui/main_window.py
git commit -m "feat(ui): 图片生成设置对话框 + 设置菜单入口"
```

---

### Task 8: 主窗集成（图片生成 tab + 任务窗管理）

**Files:**
- Modify: `drama_shot_master/ui/main_window.py`

镜像 dub 的 `_open_dub_window` 等一套；图片生成放「图像」组。

- [ ] **Step 1: FUNCS + 分组 + store**

- `FUNCS` 在图像组加 `("图片生成","imggen")`（放 去白边 之后、视频生成 之前），即：
  ```python
  FUNCS = [("拆图", "split"), ("拼图", "combine"), ("去白边", "trim"),
           ("图片生成", "imggen"),
           ("视频生成", "video_gen"), ("配乐", "soundtrack"), ("配音", "dubbing")]
  ```
- `_IMAGE_KEYS` 加 `"imggen"`（让它归「图像」组的分隔逻辑）。
- `is_wide`：`_on_func_changed` 里的 `is_wide` 元组加 `"imggen"`（图片生成是宽面板）。读现有代码确认那行（之前是 `("video_gen","soundtrack","dubbing")`）。
- `__init__`（`self.dub_store=...` 附近）加：
  ```python
  from drama_shot_master.core.imggen_task_store import ImgGenTaskStore
  self.imggen_store = ImgGenTaskStore.from_list(self.cfg.imggen_tasks)
  self._open_imggen_windows: dict = {}
  ```

- [ ] **Step 2: panels 注册（保持索引对齐）**

`self.panels` 列表里，在 trim 面板之后、视频任务面板之前插入 `self._make_imggen_panel()`，使其与 FUNCS 中 `图片生成` 的位置（index 3）一致：
```python
        self.panels = [
            SplitPanel(self.state, self.cfg),
            CombinePanel(self.state, self.cfg),
            TrimPanel(self.state, self.cfg),
            self._make_imggen_panel(),                 # index 3 = 图片生成
            VideoTaskManagerPanel(...),                # 原样
            self._try_make_soundtrack_panel(),
            self._make_dub_panel(),
        ]
```
加方法：
```python
    def _make_imggen_panel(self):
        from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
        return ImgGenTaskManagerPanel(
            self.state, self.cfg, self.imggen_store,
            self._open_imggen_window, self._close_imggen_window,
            self._persist_imggen_tasks)
```

> 校验：FUNCS 与 panels 必须等长且逐项对齐（图片生成都在 index 3）。

- [ ] **Step 3: 任务窗管理方法（镜像 dub）**

```python
    def _imggen_manager(self):
        idx = next(i for i, (_l, k) in enumerate(FUNCS) if k == "imggen")
        return self.panels[idx]

    def _persist_imggen_tasks(self):
        try:
            self.cfg.update_settings(imggen_tasks=self.imggen_store.to_list())
        except Exception:
            pass

    def _open_imggen_window(self, task):
        from drama_shot_master.ui.windows.imggen_task_window import ImgGenTaskWindow
        existing = self._open_imggen_windows.get(task.id)
        if existing is not None:
            existing.raise_(); existing.activateWindow(); return
        win = ImgGenTaskWindow(task, self.cfg)
        win.dirty.connect(self._on_imggen_dirty)
        win.statusChanged.connect(self._on_imggen_status)
        win.resultReady.connect(self._on_imggen_result)
        win.closed.connect(self._on_imggen_window_closed)
        self._open_imggen_windows[task.id] = win
        win.show()

    def _close_imggen_window(self, task_id: str):
        win = self._open_imggen_windows.get(task_id)
        if win is not None:
            win.close()

    def _on_imggen_dirty(self, task_id: str, payload: dict):
        self.imggen_store.update(task_id, payload=payload)
        self._persist_imggen_tasks()

    def _on_imggen_status(self, task_id: str, status: str):
        self._imggen_manager().set_task_status(task_id, status)

    def _on_imggen_result(self, task_id: str, path: str):
        self.imggen_store.update(task_id, last_result=path)
        self._persist_imggen_tasks(); self._imggen_manager().refresh()

    def _on_imggen_window_closed(self, task_id: str):
        self._open_imggen_windows.pop(task_id, None)
        self._imggen_manager().clear_task_status(task_id)

    def _on_imggen_renamed(self, task_id: str, name: str):
        win = self._open_imggen_windows.get(task_id)
        if win is not None:
            win.set_title_name(name)
```

- [ ] **Step 4: taskRenamed 接线 + closeEvent 持久化**

- `_wire`（或现有 dub manager 接线处）加：
  ```python
  self._imggen_manager().taskRenamed.connect(self._on_imggen_renamed)
  ```
- `closeEvent` 里（dub 持久化之后）加：
  ```python
  for win in list(self._open_imggen_windows.values()):
      try:
          self.imggen_store.update(win.task_id, payload=win.panel.to_payload())
      except Exception:
          pass
  self._persist_imggen_tasks()
  ```

- [ ] **Step 5: 离屏整窗校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); import drama_shot_master.ui.main_window as m; w=m.MainWindow(); keys=[k for _,k in m.FUNCS]; print('FUNCS',keys); assert keys.index('imggen')==3 and len(w.panels)==len(m.FUNCS); w._imggen_manager(); idx=keys.index('imggen'); w._on_func_changed(idx); assert not w.thumb.isVisible(); print('imggen wide+aligned ok', len(w.panels))"
```
Expected: `FUNCS [...'imggen'...]`、`imggen wide+aligned ok 7`。

- [ ] **Step 6: 全套回归 + 提交**

Run: `python -m pytest -q`（全绿）

```bash
git add drama_shot_master/ui/main_window.py
git commit -m "feat(ui): 主窗集成图片生成 tab(图像组)+任务窗管理"
```

---

## Self-Review

**Spec 覆盖**：
- 文/图/图文生图自动判定 → Task 5 `_update_mode`。✅
- 豆包 ARK 默认 + OpenAI + RunningHub 占位 + 工厂 → Task 2。✅
- @参考图(加图/自动编号/改名/点卡片插入/全部发送) → Task 5 参考图区 + provider `_build_payload` image 数组。✅
- 画质 1K/2K + 比例(自动/...) + size 映射 → Task 1 `imggen_sizes` + Task 5 下拉。✅
- 数量 1–4 → Task 5 QSpinBox + provider n。✅
- 快捷按钮(9 个, 原文) → Task 1 `QUICK_PROMPTS` + Task 5 按钮行。✅
- 任务栏+任务窗(镜像) → Task 6。✅
- 设置(provider/base_url/model/key/输出目录) → Task 4 config + Task 7 对话框。✅
- 主窗「图像」组宽面板 + 任务窗管理 → Task 8。✅
- 持久化 cfg.imggen_tasks → Task 3 store + Task 4 config + Task 8。✅
- 生成前查授权 → Task 5 `_generate` 开头。✅
- 单测(size/presets/provider payload+parse+factory+stub/store/config) → Task 1/2/3/4。✅

**占位扫描**：`imggen_model` 默认空是有意（设置填，generate 时空则抛友好错）。Task 6 manager 用"复制 dub 版改 N 处"——给了精确改点（类名/import/表头列/_new payload），非模糊占位；Task 8 用现有 dub 方法作平行模板并给完整代码。无 TBD。

**类型/签名一致性**：
- `ImageGenProvider.generate(prompt, references, *, size, n) -> list[bytes]` 在豆包/OpenAI/RunningHub/工厂/Task5 调用处一致。✅
- `resolve_size(quality, ratio)`、`QUICK_PROMPTS`(label,text) 在 Task1 定义、Task5 使用一致。✅
- `ImgGenTask(id,name,payload,updated_at,last_result)` 在 store/window/manager/main_window 一致。✅
- `ImgGenPanel` 信号 `statusChanged(str)/resultReady(str)/dirty()` → 窗口转 `(task_id,…)`，main_window 槽 `_on_imggen_*` 一致。✅
- payload 键 `{prompt,refs:[{path,label}],quality,ratio,n}` 在 panel to/load、store、main_window 一致。✅

**给执行者提醒**：
- Task 7 `update_settings(api_keys=...)`：先核对 `config.py` 的 `update_settings` 落盘 dict 是否含 `api_keys`；若不含，改为 `self.cfg.api_keys=keys` 后再 `update_settings(...)`，确保 key 落盘。
- Task 8 `is_wide` 那行按现有真实写法追加 `"imggen"`（之前是字面元组）。
- Task 6 manager 严格逐行核对 dub 版，去「模式」列后列号顺延别错位。
