# 配音（TTS）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「配音」功能（镜像视频生成的任务栏+任务窗），任务窗支持音色设计与声音克隆(4 情感模式)，经 RunningHub workflow_id + nodeInfoList 提交，产出 FLAC。

**Architecture:** 纯逻辑层 `core/tts_profiles.py` + `providers/tts_builder.py`（构造 nodeInfoList，可单测）；`core/dub_task_store.py`（类型化任务持久化）；`providers/tts_submit.py`（上传+create_task+轮询+下载编排）。UI 层 `ui/panels/dub_panel.py`（编辑器）、`ui/windows/dub_task_window.py`、`ui/panels/dub_task_manager_panel.py`、`ui/dialogs/dub_settings_dialog.py`，在 `main_window.py` 注册为「视频」组的宽面板。

**Tech Stack:** Python, PySide6, RunningHub（`RunningHubClient`）。

依据 spec：`docs/superpowers/specs/2026-05-26-dubbing-tts-design.md`。

参考既有签名：
- `RunningHubClient.upload_file(path)->str`（返回 `openapi/<hash>.ext`）、`create_task(*, workflow_id, node_info_list, webhook_url=None)->task_id`、`query_task(task_id)->dict`（扁平：`status∈QUEUED/RUNNING/SUCCESS/FAILED`，`results=[{url,outputType}]`）、`download_file(url, dest)->Path`。
- `submit_ltx_task` 是同类编排范例（`runninghub.py:558`）。
- `config.Config.update_settings(**kwargs)` + `load_config`（`config.py:71/111`），已持久化 `video_tasks/soundtrack_tasks/workflow_ids`。
- `BasePanel`（`select_mode/validate/execute/has_preview`，信号 `statusMessage/validityChanged`）。
- 任务栏/窗范例：`VideoTaskManagerPanel`、`VideoTaskWindow`、`VideoTaskStore`。

---

### Task 1: TTS profiles + nodeInfoList 构造（纯逻辑）

**Files:**
- Create: `drama_shot_master/core/tts_profiles.py`
- Create: `drama_shot_master/providers/tts_builder.py`
- Test: `tests/test_dub/__init__.py`（空）, `tests/test_dub/test_tts_builder.py`

- [ ] **Step 1: 写失败测试**

`tests/test_dub/__init__.py` 留空。`tests/test_dub/test_tts_builder.py`：

```python
from drama_shot_master.core import tts_profiles as P
from drama_shot_master.providers import tts_builder as B


def _kv(items):
    return {(i["nodeId"], i["fieldName"]): i["fieldValue"] for i in items}


def test_design_node_info():
    m = _kv(B.build_design_node_info("你好世界", "慵懒御姐音", "Auto", P.VOICE_DESIGN))
    assert m[("14", "text")] == "你好世界"
    assert m[("15", "text")] == "慵懒御姐音"
    assert m[("22", "language")] == "Auto"


def test_clone_mode1_default():
    items = B.build_clone_node_info(text="台词", mode=1, emo_alpha=1.0,
                                    speaker_file="openapi/spk.flac", prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("4", "prompt")] == "台词"
    assert m[("10", "audio")] == "openapi/spk.flac"
    # #26 仅「默认声音克隆 1」为 True，其余三组 False
    assert m[("26", "默认声音克隆 1")] is True
    assert m[("26", "文本情绪方案 2")] is False
    assert m[("26", "语音情绪模仿 3")] is False
    assert m[("26", "情感向量方案 4")] is False
    assert m[("1", "emo_alpha")] == 1.0
    # 模式1 无额外情感字段
    assert ("16", "prompt") not in m and ("19", "audio") not in m and ("21", "prompt") not in m


def test_clone_mode2_emo_text():
    items = B.build_clone_node_info(text="台词", mode=2, emo_alpha=0.8,
                                    emo_text="愤怒急促", speaker_file="openapi/spk.flac",
                                    prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("26", "文本情绪方案 2")] is True
    assert m[("26", "默认声音克隆 1")] is False
    assert m[("16", "prompt")] == "愤怒急促"
    assert m[("14", "emo_alpha")] == 0.8


def test_clone_mode3_emo_audio():
    items = B.build_clone_node_info(text="台词", mode=3, emo_alpha=1.0,
                                    speaker_file="openapi/spk.flac",
                                    emo_audio_file="openapi/emo.flac", prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("26", "语音情绪模仿 3")] is True
    assert m[("19", "audio")] == "openapi/emo.flac"
    assert m[("17", "emo_alpha")] == 1.0


def test_clone_mode4_emo_vector():
    items = B.build_clone_node_info(text="台词", mode=4, emo_alpha=1.0,
                                    emo_vector=[0, 0, 0, 0, 0, 0, 0.7, 0],
                                    speaker_file="openapi/spk.flac", prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("26", "情感向量方案 4")] is True
    assert m[("21", "prompt")] == "[0, 0, 0, 0, 0, 0, 0.7, 0]"
    assert m[("20", "emo_alpha")] == 1.0


def test_clone_sampling_written_to_active_branch():
    items = B.build_clone_node_info(text="t", mode=1, emo_alpha=1.0,
                                    speaker_file="openapi/spk.flac",
                                    sampling={"temperature": 0.9, "top_k": 30},
                                    prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("1", "temperature")] == 0.9
    assert m[("1", "top_k")] == 30
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_dub/test_tts_builder.py -q`
Expected: FAIL（`ModuleNotFoundError: drama_shot_master.core.tts_profiles`）

- [ ] **Step 3: 实现 tts_profiles.py**

```python
"""TTS 工作流 profile：workflow_id + 角色→节点号 映射。节点号默认值来自工作流分析，
可被 cfg 覆盖（见 dub_settings）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TTSProfile:
    key: str
    name: str
    workflow_id: str
    nodes: dict = field(default_factory=dict)   # 角色 -> 节点号(str)


VOICE_DESIGN = TTSProfile(
    key="voice_design", name="音色设计",
    workflow_id="2059260167811850242",
    nodes={"text": "14", "style": "15", "voice_design": "22"},
)

VOICE_CLONE = TTSProfile(
    key="voice_clone", name="声音克隆",
    workflow_id="2058388078015901697",
    nodes={
        "text": "4", "speaker_audio": "10",
        "emo_text": "16", "emo_audio": "19", "emo_vector": "21",
        "bypasser": "26",
        "branch_default": "1", "branch_emo_text": "14",
        "branch_emo_audio": "17", "branch_emo_vector": "20",
    },
)

# 情感模式 -> (活动分支角色, #26 组标题)
CLONE_MODES = {
    1: ("branch_default", "默认声音克隆 1"),
    2: ("branch_emo_text", "文本情绪方案 2"),
    3: ("branch_emo_audio", "语音情绪模仿 3"),
    4: ("branch_emo_vector", "情感向量方案 4"),
}
ALL_GROUP_TITLES = [t for _r, t in CLONE_MODES.values()]

# 情感向量分量标签（顺序固定）
EMO_VECTOR_LABELS = ["Happy", "Angry", "Sad", "Fear", "Hate", "Low", "Surprise", "Neutral"]


def with_overrides(prof: TTSProfile, workflow_id: str | None,
                   node_overrides: dict | None) -> TTSProfile:
    """用 cfg 里的覆盖值生成新 profile（不改原对象）。"""
    nodes = dict(prof.nodes)
    if node_overrides:
        nodes.update({k: str(v) for k, v in node_overrides.items()})
    return TTSProfile(prof.key, prof.name,
                      workflow_id or prof.workflow_id, nodes)
```

- [ ] **Step 4: 实现 tts_builder.py**

```python
"""把配音输入构造成 RunningHub nodeInfoList（[{nodeId,fieldName,fieldValue}]）。纯函数。"""
from __future__ import annotations

from drama_shot_master.core.tts_profiles import (
    TTSProfile, CLONE_MODES, ALL_GROUP_TITLES,
)


def build_design_node_info(text: str, style: str, language: str,
                           prof: TTSProfile) -> list[dict]:
    n = prof.nodes
    return [
        {"nodeId": n["text"], "fieldName": "text", "fieldValue": text},
        {"nodeId": n["style"], "fieldName": "text", "fieldValue": style},
        {"nodeId": n["voice_design"], "fieldName": "language", "fieldValue": language},
    ]


def build_clone_node_info(*, text: str, mode: int, emo_alpha: float,
                          speaker_file: str,
                          emo_text: str = "",
                          emo_vector: list | None = None,
                          emo_audio_file: str | None = None,
                          sampling: dict | None = None,
                          prof: TTSProfile) -> list[dict]:
    if mode not in CLONE_MODES:
        raise ValueError(f"未知情感模式: {mode}")
    n = prof.nodes
    branch_role, active_title = CLONE_MODES[mode]
    branch = n[branch_role]
    items: list[dict] = [
        {"nodeId": n["text"], "fieldName": "prompt", "fieldValue": text},
        {"nodeId": n["speaker_audio"], "fieldName": "audio", "fieldValue": speaker_file},
    ]
    # #26 组开关：仅当前模式组 True
    for title in ALL_GROUP_TITLES:
        items.append({"nodeId": n["bypasser"], "fieldName": title,
                      "fieldValue": title == active_title})
    items.append({"nodeId": branch, "fieldName": "emo_alpha", "fieldValue": emo_alpha})
    if mode == 2:
        items.append({"nodeId": n["emo_text"], "fieldName": "prompt", "fieldValue": emo_text})
    elif mode == 3:
        if not emo_audio_file:
            raise ValueError("模式3 需要 emo_audio_file")
        items.append({"nodeId": n["emo_audio"], "fieldName": "audio",
                      "fieldValue": emo_audio_file})
    elif mode == 4:
        vec = list(emo_vector or [0] * 8)
        items.append({"nodeId": n["emo_vector"], "fieldName": "prompt",
                      "fieldValue": "[" + ", ".join(str(x) for x in vec) + "]"})
    if sampling:
        for k, v in sampling.items():
            items.append({"nodeId": branch, "fieldName": k, "fieldValue": v})
    return items
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_dub/test_tts_builder.py -q`
Expected: PASS（6 passed）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/core/tts_profiles.py drama_shot_master/providers/tts_builder.py tests/test_dub/__init__.py tests/test_dub/test_tts_builder.py
git commit -m "feat(tts): TTS profiles + nodeInfoList 构造(音色设计/声音克隆4模式)"
```

---

### Task 2: DubTask 存储

**Files:**
- Create: `drama_shot_master/core/dub_task_store.py`
- Test: `tests/test_dub/test_dub_task_store.py`

- [ ] **Step 1: 写失败测试**

`tests/test_dub/test_dub_task_store.py`：

```python
from drama_shot_master.core.dub_task_store import DubTask, DubTaskStore


def test_add_and_get():
    s = DubTaskStore()
    t = s.add("配音A", mode="clone", payload={"text": "hi"})
    assert isinstance(t, DubTask) and t.name == "配音A" and t.mode == "clone"
    assert s.get(t.id) is t
    assert t.payload["text"] == "hi"


def test_update_and_remove():
    s = DubTaskStore()
    t = s.add("A", mode="design", payload={})
    s.update(t.id, name="B", last_result="/x/o.flac")
    assert s.get(t.id).name == "B"
    assert s.get(t.id).last_result == "/x/o.flac"
    s.remove(t.id)
    assert s.get(t.id) is None


def test_duplicate():
    s = DubTaskStore()
    t = s.add("A", mode="clone", payload={"text": "hi", "mode": 2})
    d = s.duplicate(t.id)
    assert d.id != t.id and d.payload == t.payload and d.mode == t.mode
    assert "副本" in d.name or d.name != t.name


def test_to_from_list_roundtrip():
    s = DubTaskStore()
    s.add("A", mode="design", payload={"text": "t", "style": "s", "language": "Auto"})
    s.add("B", mode="clone", payload={"text": "x", "mode": 4})
    data = s.to_list()
    s2 = DubTaskStore.from_list(data)
    assert [t.name for t in s2.all()] == ["A", "B"]
    assert s2.all()[1].payload["mode"] == 4
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_dub/test_dub_task_store.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 dub_task_store.py**

```python
"""配音任务的类型化存储 + 持久化（镜像 VideoTaskStore）。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict

from drama_shot_master.core.video_task_store import _gen_task_id


@dataclass
class DubTask:
    id: str
    name: str
    mode: str                       # "design" | "clone"
    payload: dict = field(default_factory=dict)
    updated_at: float = 0.0
    last_result: str = ""


class DubTaskStore:
    def __init__(self, tasks: list[DubTask] | None = None):
        self._tasks: list[DubTask] = list(tasks or [])

    def all(self) -> list[DubTask]:
        return list(self._tasks)

    def get(self, task_id: str) -> DubTask | None:
        return next((t for t in self._tasks if t.id == task_id), None)

    def add(self, name: str, *, mode: str, payload: dict | None = None) -> DubTask:
        t = DubTask(id=_gen_task_id(), name=name, mode=mode,
                    payload=dict(payload or {}), updated_at=time.time())
        self._tasks.append(t)
        return t

    def update(self, task_id: str, **kw) -> None:
        t = self.get(task_id)
        if t is None:
            return
        for k, v in kw.items():
            if hasattr(t, k):
                setattr(t, k, v)
        t.updated_at = time.time()

    def remove(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def duplicate(self, task_id: str) -> DubTask | None:
        t = self.get(task_id)
        if t is None:
            return None
        return self.add(f"{t.name} 副本", mode=t.mode, payload=dict(t.payload))

    def to_list(self) -> list[dict]:
        return [asdict(t) for t in self._tasks]

    @classmethod
    def from_list(cls, data: list[dict]) -> "DubTaskStore":
        tasks = []
        for d in data or []:
            tasks.append(DubTask(
                id=d.get("id") or _gen_task_id(),
                name=d.get("name", "配音"),
                mode=d.get("mode", "clone"),
                payload=d.get("payload", {}) or {},
                updated_at=d.get("updated_at", 0.0),
                last_result=d.get("last_result", ""),
            ))
        return cls(tasks)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_dub/test_dub_task_store.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/dub_task_store.py tests/test_dub/test_dub_task_store.py
git commit -m "feat(dub): DubTask/DubTaskStore 类型化任务存储"
```

---

### Task 3: config 配音字段 + 持久化

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_dub/test_dub_config.py`

- [ ] **Step 1: 写失败测试**

`tests/test_dub/test_dub_config.py`：

```python
import json
from drama_shot_master.config import load_config


def test_dub_fields_default_and_persist(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    # 默认值
    assert cfg.dub_tasks == []
    assert isinstance(cfg.dub_workflow_ids, dict)
    assert isinstance(cfg.dub_sampling, dict)
    # 写入后能从磁盘读回
    cfg.update_settings(dub_tasks=[{"id": "1", "name": "A", "mode": "clone",
                                    "payload": {}, "updated_at": 0, "last_result": ""}],
                        dub_output_dir="D:/out")
    raw = json.loads(sp.read_text(encoding="utf-8"))
    assert raw["dub_tasks"][0]["name"] == "A"
    assert raw["dub_output_dir"] == "D:/out"
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.dub_tasks[0]["name"] == "A"
    assert cfg2.dub_output_dir == "D:/out"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_dub/test_dub_config.py -q`
Expected: FAIL（`AttributeError: 'Config' object has no attribute 'dub_tasks'` 或 KeyError）

- [ ] **Step 3: 加 config 字段**

在 `drama_shot_master/config.py` 的 `Config` dataclass 字段区（紧接 `soundtrack_tasks: list = field(default_factory=list)` 之后）加：

```python
    dub_tasks: list = field(default_factory=list)
    dub_workflow_ids: dict = field(default_factory=lambda: {
        "voice_design": "2059260167811850242",
        "voice_clone": "2058388078015901697",
    })
    dub_node_profiles: dict = field(default_factory=dict)   # 角色→节点号 覆盖（可选）
    dub_output_dir: str = ""
    dub_sampling: dict = field(default_factory=lambda: {
        "top_k": 30, "top_p": 0.8, "temperature": 0.8, "num_beams": 3,
        "max_mel_tokens": 1500,
    })
```

在 `update_settings` 的落盘 dict（与 `"soundtrack_tasks": self.soundtrack_tasks,` 同块）加：

```python
                "dub_tasks": self.dub_tasks,
                "dub_workflow_ids": self.dub_workflow_ids,
                "dub_node_profiles": self.dub_node_profiles,
                "dub_output_dir": self.dub_output_dir,
                "dub_sampling": self.dub_sampling,
```

在 `load_config` 读取区（与 `if "soundtrack_tasks" in data …` 同块）加：

```python
                if "dub_tasks" in data and isinstance(data["dub_tasks"], list):
                    cfg.dub_tasks = data["dub_tasks"]
                if "dub_workflow_ids" in data and isinstance(data["dub_workflow_ids"], dict):
                    cfg.dub_workflow_ids = data["dub_workflow_ids"]
                if "dub_node_profiles" in data and isinstance(data["dub_node_profiles"], dict):
                    cfg.dub_node_profiles = data["dub_node_profiles"]
                if "dub_output_dir" in data and isinstance(data["dub_output_dir"], str):
                    cfg.dub_output_dir = data["dub_output_dir"]
                if "dub_sampling" in data and isinstance(data["dub_sampling"], dict):
                    cfg.dub_sampling = data["dub_sampling"]
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_dub/test_dub_config.py -q`
Expected: PASS（1 passed）。并跑 `python -m pytest tests/test_config.py -q` 确认无回归。

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/config.py tests/test_dub/test_dub_config.py
git commit -m "feat(dub): config 增加配音任务/workflow_id/节点profile/输出目录/采样默认"
```

---

### Task 4: TTS 提交编排（上传+create_task+轮询+下载）

**Files:**
- Create: `drama_shot_master/providers/tts_submit.py`
- Test: `tests/test_dub/test_tts_submit.py`

- [ ] **Step 1: 写失败测试（用假 client）**

`tests/test_dub/test_tts_submit.py`：

```python
from pathlib import Path
from drama_shot_master.providers import tts_submit


class FakeClient:
    def __init__(self):
        self.uploaded = []
        self.created = None
        self._polls = 0

    def upload_file(self, path):
        self.uploaded.append(Path(path).name)
        return f"openapi/{Path(path).name}"

    def create_task(self, *, workflow_id, node_info_list, webhook_url=None):
        self.created = (workflow_id, node_info_list)
        return "task-1"

    def query_task(self, task_id):
        self._polls += 1
        if self._polls >= 2:
            return {"status": "SUCCESS", "results": [{"url": "http://x/o.flac"}]}
        return {"status": "RUNNING", "results": None}

    def download_file(self, url, dest):
        Path(dest).write_bytes(b"flac")
        return Path(dest)


def test_submit_uploads_and_downloads(tmp_path):
    c = FakeClient()
    node_info = [{"nodeId": "4", "fieldName": "prompt", "fieldValue": "hi"}]
    out = tts_submit.submit_and_wait(
        c, workflow_id="WF", node_info_list=node_info,
        upload_paths=[tmp_path / "spk.flac"], out_path=tmp_path / "result.flac",
        poll_interval=0)
    assert out == tmp_path / "result.flac" and out.read_bytes() == b"flac"
    assert c.created[0] == "WF"
    assert "spk.flac" in c.uploaded


def test_submit_returns_upload_map(tmp_path):
    # 上传应返回 path->fileName，便于调用方把 fileName 填进 nodeInfoList
    c = FakeClient()
    mp = tts_submit.upload_all(c, [tmp_path / "a.flac", tmp_path / "b.flac"])
    assert mp[tmp_path / "a.flac"] == "openapi/a.flac"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_dub/test_tts_submit.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 tts_submit.py**

```python
"""配音提交编排：上传音频 → create_task → 轮询 → 下载 FLAC。
与 submit_ltx_task 同思路，但音频上传由调用方先做（因 nodeInfoList 里要用 fileName）。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable


def upload_all(client, paths: list[Path]) -> dict[Path, str]:
    """上传若干本地文件，返回 path -> RunningHub fileName(含 openapi/ 前缀)。"""
    out: dict[Path, str] = {}
    for p in paths:
        p = Path(p)
        out[p] = client.upload_file(p)
    return out


def submit_and_wait(client, *, workflow_id: str, node_info_list: list[dict],
                    upload_paths: list[Path] | None = None,
                    out_path: Path,
                    timeout: float = 1200.0, poll_interval: float = 6.0,
                    progress_cb: Callable[[str], None] | None = None,
                    cancel_check: Callable[[], bool] | None = None) -> Path:
    """注意：若 nodeInfoList 里引用了上传文件的 fileName，调用方应先 upload_all 拿到
    fileName 填进 node_info_list，再调本函数（此处 upload_paths 仅用于"提交前确保已上传"
    的场景，通常传 None）。返回下载到的 FLAC 路径。"""
    if upload_paths:
        upload_all(client, upload_paths)
    task_id = client.create_task(workflow_id=workflow_id, node_info_list=node_info_list)
    deadline = time.time() + timeout
    while True:
        if cancel_check and cancel_check():
            raise RuntimeError("已取消")
        d = client.query_task(task_id)
        status = d.get("status", "UNKNOWN")
        if progress_cb:
            progress_cb(status)
        if status == "SUCCESS":
            results = d.get("results") or []
            if not results:
                raise RuntimeError("任务成功但无输出")
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            return client.download_file(results[0]["url"], out_path)
        if status == "FAILED":
            raise RuntimeError(f"任务失败: {d.get('failedReason') or d.get('errorMessage')}")
        if time.time() > deadline:
            raise RuntimeError("超时")
        if poll_interval:
            time.sleep(poll_interval)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_dub/test_tts_submit.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/providers/tts_submit.py tests/test_dub/test_tts_submit.py
git commit -m "feat(tts): 提交编排 upload_all + submit_and_wait(轮询+下载)"
```

---

### Task 5: DubPanel 编辑器（模式切换 + 两套表单 + 生成）

**Files:**
- Create: `drama_shot_master/ui/panels/dub_panel.py`

UI 任务，离屏构造校验 + 手动验证。

- [ ] **Step 1: 实现 dub_panel.py**

```python
"""配音编辑器：顶部单选 音色设计/声音克隆 + 对应表单 + 生成。内嵌于 DubTaskWindow。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QButtonGroup, QRadioButton, QStackedWidget,
    QLineEdit, QFileDialog, QDoubleSpinBox, QGroupBox, QMessageBox,
)

from drama_shot_master.config import Config
from drama_shot_master.core import tts_profiles as P
from drama_shot_master.providers import tts_builder as B
from drama_shot_master.providers import tts_submit
from drama_shot_master.ui.worker import FunctionWorker


class DubPanel(QWidget):
    statusChanged = Signal(str)            # 状态文字
    resultReady = Signal(str)              # FLAC 路径
    dirty = Signal()                       # 输入变化(用于持久化)

    def __init__(self, cfg: Config, payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker = None
        self._build_ui()
        if payload:
            self.load_payload(payload)

    def _build_ui(self):
        root = QVBoxLayout(self)
        # 顶部模式单选
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.rb_design = QRadioButton("音色设计")
        self.rb_clone = QRadioButton("声音克隆")
        self.rb_clone.setChecked(True)
        self.mode_group.addButton(self.rb_design, 0)
        self.mode_group.addButton(self.rb_clone, 1)
        mode_row.addWidget(self.rb_design)
        mode_row.addWidget(self.rb_clone)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_design_form())   # idx0
        self.stack.addWidget(self._build_clone_form())    # idx1
        self.stack.setCurrentIndex(1)
        root.addWidget(self.stack, 1)
        self.mode_group.idClicked.connect(self.stack.setCurrentIndex)
        self.mode_group.idClicked.connect(lambda *_: self.dirty.emit())

        bar = QHBoxLayout()
        self.btn_gen = QPushButton("生成"); self.btn_gen.setObjectName("AccentButton")
        self.btn_gen.clicked.connect(self._generate)
        self.status_lbl = QLabel(""); self.status_lbl.setStyleSheet("color:#888")
        self.btn_open = QPushButton("打开结果"); self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_result)
        bar.addWidget(self.btn_gen); bar.addWidget(self.btn_open)
        bar.addWidget(self.status_lbl, 1)
        root.addLayout(bar)
        self._last_result = ""

    def _build_design_form(self):
        w = QWidget(); f = QFormLayout(w)
        self.d_text = QPlainTextEdit(); self.d_text.setFixedHeight(90)
        self.d_style = QPlainTextEdit(); self.d_style.setFixedHeight(70)
        self.d_lang = QComboBox(); self.d_lang.addItems(["Auto", "中文", "English", "日本語"])
        f.addRow("要合成文本", self.d_text)
        f.addRow("音色描述", self.d_style)
        f.addRow("语言", self.d_lang)
        return w

    def _build_clone_form(self):
        w = QWidget(); v = QVBoxLayout(w)
        f = QFormLayout()
        self.c_text = QPlainTextEdit(); self.c_text.setFixedHeight(80)
        self.c_speaker = QLineEdit(); self.c_speaker.setReadOnly(True)
        spk_btn = QPushButton("选参考音频")
        spk_btn.clicked.connect(lambda: self._pick_file(self.c_speaker))
        spk_row = QHBoxLayout(); spk_row.addWidget(self.c_speaker, 1); spk_row.addWidget(spk_btn)
        spk_wrap = QWidget(); spk_wrap.setLayout(spk_row)
        self.c_alpha = QDoubleSpinBox(); self.c_alpha.setRange(0.0, 2.0)
        self.c_alpha.setSingleStep(0.05); self.c_alpha.setValue(1.0)
        f.addRow("要合成文本", self.c_text)
        f.addRow("说话人参考音频", spk_wrap)
        f.addRow("情感强度", self.c_alpha)
        v.addLayout(f)

        # 4 选 1 情感子模式
        emo_box = QGroupBox("情感模式")
        ev = QVBoxLayout(emo_box)
        self.emo_group = QButtonGroup(self)
        labels = {1: "默认(随参考音频)", 2: "文本情绪", 3: "语音情绪模仿", 4: "情感向量"}
        for mid, txt in labels.items():
            rb = QRadioButton(txt)
            if mid == 1:
                rb.setChecked(True)
            self.emo_group.addButton(rb, mid)
            ev.addWidget(rb)
        v.addWidget(emo_box)

        self.emo_stack = QStackedWidget()
        # mode1 空
        self.emo_stack.addWidget(QWidget())
        # mode2 情感描述
        m2 = QWidget(); m2f = QFormLayout(m2)
        self.c_emo_text = QPlainTextEdit(); self.c_emo_text.setFixedHeight(60)
        m2f.addRow("情感描述", self.c_emo_text)
        self.emo_stack.addWidget(m2)
        # mode3 情感参考音频
        m3 = QWidget(); m3f = QFormLayout(m3)
        self.c_emo_audio = QLineEdit(); self.c_emo_audio.setReadOnly(True)
        ea_btn = QPushButton("选情感音频")
        ea_btn.clicked.connect(lambda: self._pick_file(self.c_emo_audio))
        ea_row = QHBoxLayout(); ea_row.addWidget(self.c_emo_audio, 1); ea_row.addWidget(ea_btn)
        ea_wrap = QWidget(); ea_wrap.setLayout(ea_row)
        m3f.addRow("情感参考音频", ea_wrap)
        self.emo_stack.addWidget(m3)
        # mode4 情感向量 8 维
        m4 = QWidget(); m4f = QFormLayout(m4)
        self.c_vec = []
        for lbl in P.EMO_VECTOR_LABELS:
            sb = QDoubleSpinBox(); sb.setRange(0.0, 1.0); sb.setSingleStep(0.05)
            self.c_vec.append(sb)
            m4f.addRow(lbl, sb)
        self.emo_stack.addWidget(m4)
        v.addWidget(self.emo_stack)
        # emo 子模式 id(1..4) -> stack idx(0..3)
        self.emo_group.idClicked.connect(lambda mid: self.emo_stack.setCurrentIndex(mid - 1))
        self.emo_group.idClicked.connect(lambda *_: self.dirty.emit())
        return w

    def _pick_file(self, line: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择音频", "", "音频 (*.wav *.flac *.mp3 *.m4a)")
        if p:
            line.setText(p); self.dirty.emit()

    # ---------- payload (持久化) ----------
    def current_mode(self) -> str:
        return "design" if self.rb_design.isChecked() else "clone"

    def to_payload(self) -> dict:
        if self.current_mode() == "design":
            return {"mode_kind": "design",
                    "text": self.d_text.toPlainText(),
                    "style": self.d_style.toPlainText(),
                    "language": self.d_lang.currentText()}
        return {"mode_kind": "clone",
                "text": self.c_text.toPlainText(),
                "speaker": self.c_speaker.text(),
                "alpha": self.c_alpha.value(),
                "emo_mode": self.emo_group.checkedId(),
                "emo_text": self.c_emo_text.toPlainText(),
                "emo_audio": self.c_emo_audio.text(),
                "emo_vector": [sb.value() for sb in self.c_vec]}

    def load_payload(self, p: dict):
        kind = p.get("mode_kind", "clone")
        if kind == "design":
            self.rb_design.setChecked(True); self.stack.setCurrentIndex(0)
            self.d_text.setPlainText(p.get("text", ""))
            self.d_style.setPlainText(p.get("style", ""))
            i = self.d_lang.findText(p.get("language", "Auto"))
            if i >= 0:
                self.d_lang.setCurrentIndex(i)
        else:
            self.rb_clone.setChecked(True); self.stack.setCurrentIndex(1)
            self.c_text.setPlainText(p.get("text", ""))
            self.c_speaker.setText(p.get("speaker", ""))
            self.c_alpha.setValue(float(p.get("alpha", 1.0)))
            mid = int(p.get("emo_mode", 1) or 1)
            btn = self.emo_group.button(mid)
            if btn:
                btn.setChecked(True); self.emo_stack.setCurrentIndex(mid - 1)
            self.c_emo_text.setPlainText(p.get("emo_text", ""))
            self.c_emo_audio.setText(p.get("emo_audio", ""))
            for sb, val in zip(self.c_vec, p.get("emo_vector", []) or []):
                sb.setValue(float(val))

    # ---------- 生成 ----------
    def _profiles(self):
        ids = self.cfg.dub_workflow_ids
        nodes = self.cfg.dub_node_profiles or {}
        design = P.with_overrides(P.VOICE_DESIGN, ids.get("voice_design"),
                                  nodes.get("voice_design"))
        clone = P.with_overrides(P.VOICE_CLONE, ids.get("voice_clone"),
                                 nodes.get("voice_clone"))
        return design, clone

    def _generate(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            QMessageBox.warning(self, "需要激活", "授权无效或已过期，无法生成。")
            return
        design, clone = self._profiles()
        payload = self.to_payload()
        out_dir = Path(self.cfg.dub_output_dir or ".") / "dub"
        ts = __import__("time").strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"dub_{ts}.flac"
        sampling = dict(self.cfg.dub_sampling or {})
        api_key = self.cfg.runninghub_api_key
        base_url = self.cfg.runninghub_base_url

        if payload["mode_kind"] == "design":
            if not payload["text"].strip():
                QMessageBox.information(self, "提示", "请填写要合成的文本"); return
            wf = design.workflow_id
            node_info = B.build_design_node_info(
                payload["text"], payload["style"], payload["language"], design)

            def task():
                from drama_shot_master.providers.runninghub import RunningHubClient
                with RunningHubClient(api_key, base_url=base_url) as client:
                    return tts_submit.submit_and_wait(
                        client, workflow_id=wf, node_info_list=node_info, out_path=out_path)
        else:
            if not payload["text"].strip() or not payload["speaker"]:
                QMessageBox.information(self, "提示", "请填写文本并选择说话人参考音频"); return
            mode = int(payload["emo_mode"])
            if mode == 3 and not payload["emo_audio"]:
                QMessageBox.information(self, "提示", "语音情绪模仿需选择情感参考音频"); return
            wf = clone.workflow_id
            spk = Path(payload["speaker"])
            emo_audio = Path(payload["emo_audio"]) if (mode == 3 and payload["emo_audio"]) else None

            def task():
                from drama_shot_master.providers.runninghub import RunningHubClient
                with RunningHubClient(api_key, base_url=base_url) as client:
                    uploads = [spk] + ([emo_audio] if emo_audio else [])
                    mp = tts_submit.upload_all(client, uploads)
                    node_info = B.build_clone_node_info(
                        text=payload["text"], mode=mode, emo_alpha=payload["alpha"],
                        speaker_file=mp[spk],
                        emo_text=payload["emo_text"],
                        emo_vector=payload["emo_vector"],
                        emo_audio_file=mp.get(emo_audio) if emo_audio else None,
                        sampling=sampling, prof=clone)
                    return tts_submit.submit_and_wait(
                        client, workflow_id=wf, node_info_list=node_info, out_path=out_path)

        self.btn_gen.setEnabled(False)
        self.status_lbl.setText("提交中…"); self.statusChanged.emit("RUNNING")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, path):
        self._last_result = str(path)
        self.btn_gen.setEnabled(True); self.btn_open.setEnabled(True)
        self.status_lbl.setText(f"完成: {path}")
        self.statusChanged.emit("SUCCESS"); self.resultReady.emit(str(path))

    def _on_fail(self, err: str):
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText(f"失败: {err}")
        self.statusChanged.emit("FAILED")
        QMessageBox.critical(self, "生成失败", err)

    def _open_result(self):
        if not self._last_result:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_result))
```

- [ ] **Step 2: 离屏构造校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.config import load_config; from drama_shot_master.ui.panels.dub_panel import DubPanel; p=DubPanel(load_config()); print('payload', p.to_payload()['mode_kind']); p.load_payload({'mode_kind':'clone','emo_mode':4,'emo_vector':[0,0,0,0,0,0,0.7,0]}); print('ok')"
```
Expected: 打印 `payload clone` 和 `ok`，无异常。

- [ ] **Step 3: 提交**

```bash
git add drama_shot_master/ui/panels/dub_panel.py
git commit -m "feat(ui): 配音编辑器 DubPanel(模式切换+音色设计/克隆4模式表单+生成)"
```

---

### Task 6: DubTaskWindow + DubTaskManagerPanel

**Files:**
- Create: `drama_shot_master/ui/windows/dub_task_window.py`
- Create: `drama_shot_master/ui/panels/dub_task_manager_panel.py`

参考 `drama_shot_master/ui/windows/video_task_window.py` 与 `drama_shot_master/ui/panels/video_task_manager_panel.py` 的现有实现（读它们照搬结构，仅把 timeline/VideoPanel 换成 payload/DubPanel）。

- [ ] **Step 1: 实现 dub_task_window.py**

```python
"""配音任务窗：标题=任务名，内嵌 DubPanel；转发状态/结果/脏标记/关闭信号。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

from drama_shot_master.config import Config
from drama_shot_master.core.dub_task_store import DubTask
from drama_shot_master.ui.panels.dub_panel import DubPanel
from drama_shot_master.ui.theme import apply_dark_titlebar


class DubTaskWindow(QMainWindow):
    statusChanged = Signal(str, str)       # (task_id, status)
    resultReady = Signal(str, str)         # (task_id, flac_path)
    dirty = Signal(str, dict)              # (task_id, payload)
    closed = Signal(str)                   # (task_id)

    def __init__(self, task: DubTask, cfg: Config, parent=None):
        super().__init__(parent)
        self.task_id = task.id
        self.cfg = cfg
        self.setWindowTitle(f"配音 · {task.name}")
        self.resize(620, 720)
        self.panel = DubPanel(cfg, payload=task.payload)
        self.setCentralWidget(self.panel)
        self.panel.statusChanged.connect(lambda s: self.statusChanged.emit(self.task_id, s))
        self.panel.resultReady.connect(lambda p: self.resultReady.emit(self.task_id, p))
        self.panel.dirty.connect(self._on_dirty)

    def _on_dirty(self):
        self.dirty.emit(self.task_id, self.panel.to_payload())

    def set_title_name(self, name: str):
        self.setWindowTitle(f"配音 · {name}")

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

- [ ] **Step 2: 实现 dub_task_manager_panel.py**

```python
"""配音任务栏：任务表 + 新建/打开/复制/删除。镜像 VideoTaskManagerPanel。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QInputDialog, QMessageBox, QHeaderView,
)

from drama_shot_master.config import Config
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState


class DubTaskManagerPanel(BasePanel):
    taskRenamed = Signal(str, str)

    def __init__(self, state: AppState, cfg: Config, store: DubTaskStore,
                 open_window_cb, close_window_cb, persist_cb, parent=None):
        super().__init__(state, cfg, parent)
        self.store = store
        self._open_cb = open_window_cb
        self._close_cb = close_window_cb
        self._persist = persist_cb
        self._live_status: dict[str, str] = {}
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self):
        return True, ""

    def _build_ui(self):
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        for txt, slot in (("新建", self._new), ("打开", self._open),
                          ("复制", self._dup), ("删除", self._del),
                          ("重命名", self._rename)):
            b = QPushButton(txt); b.clicked.connect(slot); bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "模式", "状态", "最近输出", "更新时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.doubleClicked.connect(lambda *_: self._open())
        root.addWidget(self.table, 1)

    def _selected_id(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        it = self.table.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def refresh(self):
        import time
        tasks = self.store.all()
        self.table.setRowCount(len(tasks))
        for r, t in enumerate(tasks):
            name = QTableWidgetItem(t.name); name.setData(Qt.UserRole, t.id)
            mode = "音色设计" if t.mode == "design" else "声音克隆"
            status = self._live_status.get(t.id, "—")
            updated = time.strftime("%m-%d %H:%M", time.localtime(t.updated_at)) if t.updated_at else ""
            for c, val in enumerate([name, QTableWidgetItem(mode),
                                     QTableWidgetItem(status),
                                     QTableWidgetItem(t.last_result),
                                     QTableWidgetItem(updated)]):
                self.table.setItem(r, c, val)

    def set_task_status(self, task_id: str, status: str):
        self._live_status[task_id] = status
        self.refresh()

    def clear_task_status(self, task_id: str):
        self._live_status.pop(task_id, None)
        self.refresh()

    def _new(self):
        name, ok = QInputDialog.getText(self, "新建配音任务", "名称:")
        if not ok or not name.strip():
            return
        t = self.store.add(name.strip(), mode="clone", payload={"mode_kind": "clone"})
        self._persist(); self.refresh(); self._open_cb(t)

    def _open(self):
        tid = self._selected_id()
        if tid:
            self._open_cb(self.store.get(tid))

    def _dup(self):
        tid = self._selected_id()
        if tid:
            self.store.duplicate(tid); self._persist(); self.refresh()

    def _del(self):
        tid = self._selected_id()
        if not tid:
            return
        if QMessageBox.question(self, "删除", "确定删除该任务？") == QMessageBox.Yes:
            self._close_cb(tid); self.store.remove(tid); self._persist(); self.refresh()

    def _rename(self):
        tid = self._selected_id()
        if not tid:
            return
        t = self.store.get(tid)
        name, ok = QInputDialog.getText(self, "重命名", "名称:", text=t.name)
        if ok and name.strip():
            self.store.update(tid, name=name.strip()); self._persist()
            self.refresh(); self.taskRenamed.emit(tid, name.strip())
```

- [ ] **Step 3: 离屏构造校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.config import load_config; from drama_shot_master.core.dub_task_store import DubTaskStore; from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel; from drama_shot_master.ui.state import AppState; p=DubTaskManagerPanel(AppState(), load_config(), DubTaskStore(), lambda t:None, lambda i:None, lambda:None); print('mgr ok'); from drama_shot_master.core.dub_task_store import DubTask; from drama_shot_master.ui.windows.dub_task_window import DubTaskWindow; w=DubTaskWindow(DubTask(id='1',name='x',mode='clone'), load_config()); print('win ok')"
```
Expected: `mgr ok` 和 `win ok`。

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/ui/windows/dub_task_window.py drama_shot_master/ui/panels/dub_task_manager_panel.py
git commit -m "feat(ui): 配音任务窗 DubTaskWindow + 任务栏 DubTaskManagerPanel"
```

---

### Task 7: 配音设置对话框 + 菜单

**Files:**
- Create: `drama_shot_master/ui/dialogs/dub_settings_dialog.py`
- Modify: `drama_shot_master/ui/main_window.py`（设置菜单加「配音…」）

- [ ] **Step 1: 实现 dub_settings_dialog.py**

```python
"""配音设置：两个 workflow_id + 输出目录 + 采样默认。节点号 profile 高级用户可在
 settings.json 的 dub_node_profiles 手改，这里不做复杂表单。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QDialogButtonBox, QLabel,
)

from drama_shot_master.config import Config


class DubSettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("配音设置")
        self.setModal(True)
        self.resize(520, 280)
        root = QVBoxLayout(self)
        f = QFormLayout()
        ids = cfg.dub_workflow_ids or {}
        self.wf_design = QLineEdit(ids.get("voice_design", ""))
        self.wf_clone = QLineEdit(ids.get("voice_clone", ""))
        self.out_dir = QLineEdit(cfg.dub_output_dir or "")
        out_btn = QPushButton("选目录"); out_btn.clicked.connect(self._pick_dir)
        out_row = QHBoxLayout(); out_row.addWidget(self.out_dir, 1); out_row.addWidget(out_btn)
        from PySide6.QtWidgets import QWidget
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        f.addRow("音色设计 workflow_id", self.wf_design)
        f.addRow("声音克隆 workflow_id", self.wf_clone)
        f.addRow("输出目录", out_wrap)
        root.addLayout(f)
        root.addWidget(QLabel("高级：节点号映射可在 settings.json 的 dub_node_profiles 手改"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir.text() or "")
        if d:
            self.out_dir.setText(d)

    def _save(self):
        self.cfg.update_settings(
            dub_workflow_ids={"voice_design": self.wf_design.text().strip(),
                              "voice_clone": self.wf_clone.text().strip()},
            dub_output_dir=self.out_dir.text().strip())
        self.accept()
```

- [ ] **Step 2: main_window 设置菜单加「配音…」**

在 `drama_shot_master/ui/main_window.py` 的设置菜单块（`a_st`「配乐…」之后）插入：

```python
        a_dub = QAction("配音…", self)
        a_dub.triggered.connect(self._open_dub_settings)
        sm.addAction(a_dub)
```

并加方法（`_open_soundtrack_settings` 附近）：

```python
    def _open_dub_settings(self):
        from drama_shot_master.ui.dialogs.dub_settings_dialog import DubSettingsDialog
        DubSettingsDialog(self.cfg, parent=self).exec()
```

- [ ] **Step 3: 离屏校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); from drama_shot_master.config import load_config; from drama_shot_master.ui.dialogs.dub_settings_dialog import DubSettingsDialog; d=DubSettingsDialog(load_config()); print('dub settings ok')"
```
Expected: `dub settings ok`。

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/ui/dialogs/dub_settings_dialog.py drama_shot_master/ui/main_window.py
git commit -m "feat(ui): 配音设置对话框 + 设置菜单入口"
```

---

### Task 8: 主窗集成（配音 tab + 任务窗管理）

**Files:**
- Modify: `drama_shot_master/ui/main_window.py`

参考主窗里视频生成的 `_open_task_window/_close_task_window/_persist_tasks/_on_task_*` 与 `_try_make_soundtrack_panel` 实现，做平行的配音版。

- [ ] **Step 1: FUNCS + 分组 + store**

`main_window.py`：
- `FUNCS` 视频组末尾加 `("配音", "dubbing")`：
  ```python
  FUNCS = [("拆图", "split"), ("拼图", "combine"), ("去白边", "trim"),
           ("视频生成", "video_gen"), ("配乐", "soundtrack"), ("配音", "dubbing")]
  ```
- `_VIDEO_KEYS` 加 `"dubbing"`：`_VIDEO_KEYS = {"video_gen", "soundtrack", "dubbing"}`
- `_on_func_changed` 里 `is_wide` 判断已用 `_VIDEO_KEYS`？若它是写死的 `("video_gen","soundtrack")`，改为 `FUNCS[idx][1] in _VIDEO_KEYS`（读现有代码确认；保持与现状一致）。
- `__init__` 中（`self.video_store = …` 附近）加：
  ```python
  from drama_shot_master.core.dub_task_store import DubTaskStore
  self.dub_store = DubTaskStore.from_list(self.cfg.dub_tasks)
  self._open_dub_windows: dict = {}
  ```

- [ ] **Step 2: panels 注册配音任务栏**

`self.panels` 列表末尾（`self._try_make_soundtrack_panel()` 之后）加：
```python
            self._make_dub_panel(),
```
并加方法：
```python
    def _make_dub_panel(self):
        from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
        return DubTaskManagerPanel(
            self.state, self.cfg, self.dub_store,
            self._open_dub_window, self._close_dub_window, self._persist_dub_tasks)
```

> 注意：FUNCS 与 panels 必须索引一一对应——「配音」是 FUNCS 第 6 项(idx5)，`_make_dub_panel()` 也必须是 panels 第 6 项。

- [ ] **Step 3: 配音任务窗管理方法**

加（仿视频版）：
```python
    def _dub_manager(self):
        idx = next(i for i, (_l, k) in enumerate(FUNCS) if k == "dubbing")
        return self.panels[idx]

    def _persist_dub_tasks(self):
        try:
            self.cfg.update_settings(dub_tasks=self.dub_store.to_list())
        except Exception:
            pass

    def _open_dub_window(self, task):
        from drama_shot_master.ui.windows.dub_task_window import DubTaskWindow
        existing = self._open_dub_windows.get(task.id)
        if existing is not None:
            existing.raise_(); existing.activateWindow(); return
        win = DubTaskWindow(task, self.cfg)
        win.dirty.connect(self._on_dub_dirty)
        win.statusChanged.connect(self._on_dub_status)
        win.resultReady.connect(self._on_dub_result)
        win.closed.connect(self._on_dub_window_closed)
        self._open_dub_windows[task.id] = win
        win.show()

    def _close_dub_window(self, task_id: str):
        win = self._open_dub_windows.get(task_id)
        if win is not None:
            win.close()

    def _on_dub_dirty(self, task_id: str, payload: dict):
        self.dub_store.update(task_id, payload=payload,
                              mode=("design" if payload.get("mode_kind") == "design" else "clone"))
        self._persist_dub_tasks()

    def _on_dub_status(self, task_id: str, status: str):
        self._dub_manager().set_task_status(task_id, status)

    def _on_dub_result(self, task_id: str, flac: str):
        self.dub_store.update(task_id, last_result=flac)
        self._persist_dub_tasks(); self._dub_manager().refresh()

    def _on_dub_window_closed(self, task_id: str):
        self._open_dub_windows.pop(task_id, None)
        self._dub_manager().clear_task_status(task_id)
```

- [ ] **Step 4: taskRenamed 接线 + 关闭时持久化**

- 在 `_wire`（或 panels 接线处）加：找到配音 manager，连 `taskRenamed`：
  ```python
  self._dub_manager().taskRenamed.connect(self._on_dub_renamed)
  ```
  并加：
  ```python
  def _on_dub_renamed(self, task_id: str, name: str):
      win = self._open_dub_windows.get(task_id)
      if win is not None:
          win.set_title_name(name)
  ```
- 在 `closeEvent` 里（视频持久化之后）加配音持久化：
  ```python
  for win in list(self._open_dub_windows.values()):
      try:
          self.dub_store.update(win.task_id, payload=win.panel.to_payload())
      except Exception:
          pass
  self._persist_dub_tasks()
  ```

- [ ] **Step 5: 离屏整窗校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtWidgets import QApplication; a=QApplication([]); import drama_shot_master.ui.main_window as m; w=m.MainWindow(); keys=[k for _,k in m.FUNCS]; print('FUNCS', keys); assert 'dubbing' in keys and len(w.panels)==len(m.FUNCS); print('panels aligned', len(w.panels)); w._dub_manager(); print('dub manager ok')"
```
Expected: `FUNCS [...'dubbing']`、`panels aligned 6`、`dub manager ok`。

- [ ] **Step 6: 全套回归 + 提交**

Run: `python -m pytest -q`（应全绿，无回归）

```bash
git add drama_shot_master/ui/main_window.py
git commit -m "feat(ui): 主窗集成配音 tab + 任务窗管理(开/关/持久化/重命名)"
```

---

## Self-Review

**Spec 覆盖**：
- 音色设计(文本/音色描述/语言) → Task 1 `build_design_node_info` + Task 5 设计表单。✅
- 声音克隆 4 模式(文本/参考音频/情感强度 + 子模式额外字段) → Task 1 `build_clone_node_info` + Task 5 克隆表单。✅
- #26 组开关(仅当前模式 True) → Task 1（已断言）。✅
- 节点映射(4/10/16/19/21/26/1/14/17/20；设计 14/15/22) → Task 1 profiles。✅
- 任务栏 + 任务窗(镜像视频) → Task 6。✅
- 配音设置(workflow_id/输出目录；节点 profile 可配) → Task 3 config + Task 7 对话框（节点 profile 走 settings.json 手改）。✅
- 持久化 `cfg.dub_tasks` → Task 2 store + Task 3 config + Task 8 接线。✅
- 主窗作为「视频」组宽面板 → Task 8（_VIDEO_KEYS 加 dubbing）。✅
- 提交(上传音频→覆盖 LoadAudio；create_task；轮询下载) → Task 4 + Task 5 `_generate`。✅
- 进阶采样进设置当默认、写活动分支 → Task 1(sampling 参数) + Task 3(dub_sampling)。✅
- 分散校验(生成前查授权) → Task 5 `_generate` 开头。✅
- 单测(builder 各模式/store/config/submit) → Task 1/2/3/4。✅

**占位扫描**：无 TBD/TODO。Task 8 要求执行者读现有视频版方法照搬（给了完整平行代码），并提醒确认 `is_wide` 现有写法——这是"按现状适配"而非占位。

**类型/签名一致性**：
- `build_clone_node_info(*, text, mode, emo_alpha, speaker_file, emo_text="", emo_vector=None, emo_audio_file=None, sampling=None, prof)` 在 Task 5 `_generate` 调用处参数名一致。✅
- `TTSProfile.nodes` 角色键（text/style/voice_design；text/speaker_audio/emo_text/emo_audio/emo_vector/bypasser/branch_*）在 profiles 与 builder 间一致。✅
- `DubTask(id,name,mode,payload,updated_at,last_result)` 在 store/window/manager/main_window 间字段一致。✅
- `DubPanel` 信号 `statusChanged(str)/resultReady(str)/dirty()` → 窗口转成 `(task_id, …)`，与 main_window 槽 `_on_dub_*` 签名一致。✅
- `tts_submit.submit_and_wait(client,*,workflow_id,node_info_list,upload_paths=None,out_path,...)` 与 Task 5 调用一致（克隆里先 `upload_all` 再传 fileName 进 node_info）。✅

**给执行者的提醒**：`RunningHubClient` 构造参数名以现有 `runninghub.py` 为准（Task 5 用 `api_key=cfg.runninghub_api_key`，执行时核对实际构造签名，不符则按现有用法调整）。
