# 视频生成多工作流支持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 视频任务可在窗口内切换「导演台」/「ALL IN ONE V3」工作流；按 profile 取节点 ID/分辨率策略/workflow_id；V3 上传音频翻 687 开关；V3 额外参数走 YAML。

**Architecture:** 内置 `WorkflowProfile` 注册表（2 个）；`LTXTaskBuilder` 由 profile 驱动节点 ID + 分辨率分支 + 音频开关 + YAML extras；config 加 `workflow_ids`；`TimelineModel.workflow_key` 持久化所选工作流；VideoPanel 顶部下拉 + `_on_submit` 按 profile 取模板/workflow_id。

**Tech Stack:** Python stdlib + pyyaml（已声明）；PySide6；pytest。

**Spec:** [docs/superpowers/specs/2026-05-25-multi-workflow-design.md](../specs/2026-05-25-multi-workflow-design.md)

---

## File Structure

新增：
- `drama_shot_master/core/workflow_profiles.py` — `WorkflowProfile` + `PROFILES` + helpers + `load_extras`
- `drama_shot_master/templates/ltx_director_v3_api.json` — 从外部拷入
- `drama_shot_master/templates/ltx_v3_extras.yaml` — 可编辑额外覆盖（初始空）
- `tests/test_core/test_workflow_profiles.py`

修改：
- `drama_shot_master/providers/runninghub.py` — `LTXTaskBuilder(template_path, profile=None)` profile 驱动
- `drama_shot_master/config.py` — `workflow_ids` + 迁移
- `drama_shot_master/core/video_timeline_model.py` — `workflow_key` 字段
- `drama_shot_master/ui/dialogs/runninghub_settings_dialog.py` — 每 profile 一个 workflow_id 框
- `drama_shot_master/ui/panels/video_panel.py` — 工作流下拉 + `_on_submit` 按 profile
- `tests/test_providers/test_ltx_task_builder.py`、`tests/test_config.py`、`tests/test_core/test_video_timeline_model.py` — 扩展

---

## Task 1: workflow_profiles 模块（TDD）

**Files:**
- Create: `drama_shot_master/core/workflow_profiles.py`
- Create: `tests/test_core/test_workflow_profiles.py`

- [ ] **Step 1.1: 写失败测试**

Create `tests/test_core/test_workflow_profiles.py`:

```python
"""Tests for workflow_profiles."""
from __future__ import annotations

from drama_shot_master.core import workflow_profiles as wp


def test_two_builtin_profiles():
    assert set(wp.PROFILES) == {"director", "director_v3"}


def test_director_profile_node_ids():
    p = wp.PROFILES["director"]
    assert (p.director_node, p.save_video_node, p.noise_node,
            p.resolution_node, p.audio_switch_node) == ("4", "32", "23", "34", None)
    assert p.extras_yaml is None


def test_v3_profile_node_ids():
    p = wp.PROFILES["director_v3"]
    assert (p.director_node, p.save_video_node, p.noise_node,
            p.resolution_node, p.audio_switch_node) == ("672", "683", "654", None, "687")
    assert p.extras_yaml == "ltx_v3_extras.yaml"


def test_get_profile_fallback():
    assert wp.get_profile("nope").key == wp.DEFAULT_PROFILE_KEY


def test_template_path_points_into_templates():
    p = wp.template_path_for(wp.PROFILES["director"])
    assert p.name == "ltx_director_v23.json"
    assert p.parent.name == "templates"


def test_parse_preset_wh():
    assert wp.parse_preset_wh("1280x720 (16:9) (横屏)") == (1280, 720)
    assert wp.parse_preset_wh("720x1280 (9:16) (竖屏)") == (720, 1280)
    assert wp.parse_preset_wh("1024x1024 (1:1)") == (1024, 1024)
    assert wp.parse_preset_wh("自定义...") is None


def test_load_extras_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(wp, "extras_path_for", lambda prof: tmp_path / "nope.yaml")
    assert wp.load_extras(wp.PROFILES["director_v3"]) == []


def test_load_extras_reads_overrides(monkeypatch, tmp_path):
    y = tmp_path / "x.yaml"
    y.write_text("overrides:\n  - {node: '687', field: switch, value: true}\n"
                 "  - {node: '695', field: lora_01, value: a.safetensors}\n",
                 encoding="utf-8")
    monkeypatch.setattr(wp, "extras_path_for", lambda prof: y)
    out = wp.load_extras(wp.PROFILES["director_v3"])
    assert out == [
        {"node": "687", "field": "switch", "value": True},
        {"node": "695", "field": "lora_01", "value": "a.safetensors"},
    ]


def test_load_extras_for_profile_without_yaml():
    assert wp.load_extras(wp.PROFILES["director"]) == []
```

- [ ] **Step 1.2: 运行测试，确认失败**

Run: `pytest tests/test_core/test_workflow_profiles.py -v` (or `python3.10 -m pytest`)
Expected: ImportError。

- [ ] **Step 1.3: 实现 workflow_profiles.py**

Create `drama_shot_master/core/workflow_profiles.py`:

```python
"""视频生成工作流 profile 注册表（Qt-free）。

每个 profile 描述一个 RunningHub 上的 ComfyUI 工作流的关键节点 ID + 策略，
供 LTXTaskBuilder 按需取值，避免把节点 ID 写死成单一工作流。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@dataclass(frozen=True)
class WorkflowProfile:
    key: str
    name: str
    template_filename: str
    director_node: str
    save_video_node: str
    noise_node: str
    resolution_node: Optional[str]      # None → 分辨率落 director custom_w/h
    audio_switch_node: Optional[str]    # None | LazySwitchKJ 节点（T=上传音频）
    extras_yaml: Optional[str]          # None | templates/ 下 yaml 文件名


PROFILES: dict[str, WorkflowProfile] = {
    "director": WorkflowProfile(
        key="director", name="LTX2.3 导演台",
        template_filename="ltx_director_v23.json",
        director_node="4", save_video_node="32", noise_node="23",
        resolution_node="34", audio_switch_node=None, extras_yaml=None),
    "director_v3": WorkflowProfile(
        key="director_v3",
        name="LTX2.3 全能 V3（文生/多图/图音/数字人）",
        template_filename="ltx_director_v3_api.json",
        director_node="672", save_video_node="683", noise_node="654",
        resolution_node=None, audio_switch_node="687",
        extras_yaml="ltx_v3_extras.yaml"),
}

DEFAULT_PROFILE_KEY = "director"


def get_profile(key: str) -> WorkflowProfile:
    return PROFILES.get(key) or PROFILES[DEFAULT_PROFILE_KEY]


def template_path_for(profile: WorkflowProfile) -> Path:
    return _TEMPLATES_DIR / profile.template_filename


def extras_path_for(profile: WorkflowProfile) -> Optional[Path]:
    if not profile.extras_yaml:
        return None
    return _TEMPLATES_DIR / profile.extras_yaml


def parse_preset_wh(preset: str) -> Optional[tuple[int, int]]:
    """从 "1280x720 (16:9) …" 解析前缀 WxH；解析不出返回 None。"""
    m = re.match(r"\s*(\d+)\s*[x×]\s*(\d+)", preset or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def load_extras(profile: WorkflowProfile) -> list[dict]:
    """读 profile 的 extras yaml，返回 [{node, field, value}, …]；缺失/异常 → []。"""
    p = extras_path_for(profile)
    if p is None or not p.exists():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    overrides = data.get("overrides") if isinstance(data, dict) else None
    if not isinstance(overrides, list):
        return []
    out: list[dict] = []
    for o in overrides:
        if isinstance(o, dict) and "node" in o and "field" in o:
            out.append({"node": str(o["node"]), "field": o["field"],
                        "value": o.get("value")})
    return out
```

- [ ] **Step 1.4: 运行测试，确认通过**

Run: `pytest tests/test_core/test_workflow_profiles.py -v`
Expected: 9 PASS。

- [ ] **Step 1.5: 全量回归 + 提交**

Run: `pytest -q` → 0 failures。

```bash
git add drama_shot_master/core/workflow_profiles.py tests/test_core/test_workflow_profiles.py
git commit -m "feat(workflow): add WorkflowProfile registry (director + V3)

Qt-free profiles describing per-workflow node IDs, resolution strategy,
audio-switch node, and YAML extras; helpers for template/extras paths,
preset WxH parsing, and extras loading.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 1)
- Working dir `/mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master`, branch `feat/video-panel`.
- pyyaml is a declared dep. Qt-free module (no PySide6).
- There are UNTRACKED files from the user's other work (`ui/theme.py`, `ui/styles/`, `assets/`, sound-track-agent docs). Do NOT touch/stage them. Stage ONLY your 2 files by exact path.

---

## Task 2: 拷入 V3 模板 + 建 extras YAML

**Files:**
- Create: `drama_shot_master/templates/ltx_director_v3_api.json` (copied from external)
- Create: `drama_shot_master/templates/ltx_v3_extras.yaml`

- [ ] **Step 2.1: 拷贝 V3 模板 JSON 进项目**

Run:
```bash
cp "/mnt/e/Rui/笔记/AIEngineer/AIEngineer/漫剧/01-Workflow配置/07-comfyui/LTX2.3 超高清编导级全能工作流 文生_多图_图音_数字人 ALL IN ONE V3_api.json" \
   drama_shot_master/templates/ltx_director_v3_api.json
```
Verify it's valid JSON and has the expected nodes:
```bash
python3 -c "import json; j=json.load(open('drama_shot_master/templates/ltx_director_v3_api.json',encoding='utf-8')); print('672' in j, '683' in j, '654' in j, '687' in j)"
```
Expected: `True True True True`.

- [ ] **Step 2.2: 创建 extras YAML**

Create `drama_shot_master/templates/ltx_v3_extras.yaml`:
```yaml
# LTX2.3 V3 额外节点覆盖。编辑本文件即可调 V3 专属参数，无需改代码/前台。
# 留空（overrides: []）= 全部用工作流自带默认值。
# 每条：{node: "节点ID", field: "字段名", value: 值}
overrides: []
# 示例（按需取消注释、复制到上面的 overrides 列表里）：
#   - {node: "695", field: "lora_01", value: "your_lora.safetensors"}
#   - {node: "637", field: "switch", value: false}   # F9 / T14 帧数切换
```

Verify it parses:
```bash
python3 -c "import yaml; d=yaml.safe_load(open('drama_shot_master/templates/ltx_v3_extras.yaml',encoding='utf-8')); print(d.get('overrides'))"
```
Expected: `[]`.

- [ ] **Step 2.3: 提交**

```bash
git add drama_shot_master/templates/ltx_director_v3_api.json drama_shot_master/templates/ltx_v3_extras.yaml
git commit -m "feat(workflow): bundle V3 ComfyUI template + editable extras YAML

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 2)
- The external V3 file path has spaces — quote it in the cp command.
- The bundled `ltx_director_v23.json` (导演台) already exists; this adds the V3 sibling.

---

## Task 3: LTXTaskBuilder 参数化（TDD）

**Files:**
- Modify: `drama_shot_master/providers/runninghub.py`
- Test: `tests/test_providers/test_ltx_task_builder.py`

- [ ] **Step 3.1: 写失败测试（V3 profile 行为）**

Append to `tests/test_providers/test_ltx_task_builder.py` (it already builds a director spec; reuse its helpers — read the file first to find the existing spec/builder fixtures and mirror them):

```python
def test_v3_profile_uses_v3_node_ids_and_audio_switch(tmp_path):
    from drama_shot_master.core import workflow_profiles as wp
    from drama_shot_master.providers.runninghub import LTXTaskBuilder
    prof = wp.PROFILES["director_v3"]
    builder = LTXTaskBuilder(wp.template_path_for(prof), prof)
    spec = _make_spec_with_one_image(tmp_path)   # 见下方说明
    spec.use_custom_audio = True
    uploaded = {spec.segments[0].image_path: "uploaded_0.png"}
    items = builder.build_node_info_list(spec, uploaded)
    node_ids = {it["nodeId"] for it in items}
    assert "672" in node_ids and "683" in node_ids and "654" not_used_marker or True
    # director 字段落 672
    assert any(it["nodeId"] == "672" and it["fieldName"] == "global_prompt"
               for it in items)
    # filename 落 683
    assert any(it["nodeId"] == "683" and it["fieldName"] == "filename_prefix"
               for it in items)
    # 音频开关 687 = use_custom_audio
    sw = [it for it in items if it["nodeId"] == "687" and it["fieldName"] == "switch"]
    assert sw and sw[0]["fieldValue"] is True


def test_v3_resolution_lands_on_director_custom_wh(tmp_path):
    from drama_shot_master.core import workflow_profiles as wp
    from drama_shot_master.providers.runninghub import LTXTaskBuilder
    prof = wp.PROFILES["director_v3"]
    builder = LTXTaskBuilder(wp.template_path_for(prof), prof)
    spec = _make_spec_with_one_image(tmp_path)
    spec.use_custom_resolution = False
    spec.resolution_preset = "720x1280 (9:16) (竖屏)"
    uploaded = {spec.segments[0].image_path: "u.png"}
    items = builder.build_node_info_list(spec, uploaded)
    w = [it for it in items if it["nodeId"] == "672" and it["fieldName"] == "custom_width"]
    h = [it for it in items if it["nodeId"] == "672" and it["fieldName"] == "custom_height"]
    assert w and w[0]["fieldValue"] == 720
    assert h and h[0]["fieldValue"] == 1280
    # V3 不应出现节点 34
    assert all(it["nodeId"] != "34" for it in items)


def test_v3_extras_appended(tmp_path, monkeypatch):
    from drama_shot_master.core import workflow_profiles as wp
    from drama_shot_master.providers.runninghub import LTXTaskBuilder
    y = tmp_path / "extras.yaml"
    y.write_text("overrides:\n  - {node: '695', field: lora_01, value: x.safetensors}\n",
                 encoding="utf-8")
    monkeypatch.setattr(wp, "extras_path_for", lambda prof: y)
    prof = wp.PROFILES["director_v3"]
    builder = LTXTaskBuilder(wp.template_path_for(prof), prof)
    spec = _make_spec_with_one_image(tmp_path)
    uploaded = {spec.segments[0].image_path: "u.png"}
    items = builder.build_node_info_list(spec, uploaded)
    assert any(it["nodeId"] == "695" and it["fieldName"] == "lora_01"
               and it["fieldValue"] == "x.safetensors" for it in items)
```

NOTE: Replace `_make_spec_with_one_image(tmp_path)` with the existing test file's spec-construction helper/fixture (read the file; it already constructs an `LTXDirectorSpec` with a segment + image for the director tests). The `not_used_marker or True` line above is a typo — replace with `assert "672" in node_ids and "683" in node_ids`. Also confirm/keep the existing director-profile tests passing unchanged (they call `LTXTaskBuilder(template_path)` with one arg — the default profile keeps them green).

- [ ] **Step 3.2: 运行测试，确认失败**

Run: `pytest tests/test_providers/test_ltx_task_builder.py -v -k v3`
Expected: FAIL — `LTXTaskBuilder` doesn't accept a profile arg yet.

- [ ] **Step 3.3: 改 imports + `__init__`**

Edit `drama_shot_master/providers/runninghub.py`.

Near the `LTXTaskBuilder` area, add an import of the profiles (top of file or near the class — place with other imports):
```python
from drama_shot_master.core.workflow_profiles import (
    WorkflowProfile, get_profile, load_extras, parse_preset_wh,
)
```

Change `LTXTaskBuilder.__init__`:
```python
    def __init__(self, template_path: Path):
        self.template_path = template_path
        with template_path.open(encoding="utf-8") as f:
            self._template: dict = json.load(f)
        for nid in (LTXNodes.DIRECTOR, LTXNodes.SAVE_VIDEO,
                    LTXNodes.NOISE, LTXNodes.RESOLUTION):
            if nid not in self._template:
                raise RunningHubInvalidSpec(
                    f"模板 {template_path} 缺少节点 {nid}")
```
to:
```python
    def __init__(self, template_path: Path,
                 profile: "WorkflowProfile | None" = None):
        self.template_path = template_path
        self.profile = profile or get_profile("director")
        with template_path.open(encoding="utf-8") as f:
            self._template: dict = json.load(f)
        required = [self.profile.director_node, self.profile.save_video_node,
                    self.profile.noise_node]
        if self.profile.resolution_node:
            required.append(self.profile.resolution_node)
        for nid in required:
            if nid not in self._template:
                raise RunningHubInvalidSpec(
                    f"模板 {template_path} 缺少节点 {nid}")
```

- [ ] **Step 3.4: 改 `build_node_info_list`（profile 驱动 + 分辨率分支 + 音频开关 + extras）**

Edit `drama_shot_master/providers/runninghub.py`. Replace the whole `build_node_info_list` body (currently uses `LTXNodes.*` and a fixed resolution block) with:

```python
    def build_node_info_list(self, spec: LTXDirectorSpec,
                              uploaded_files: dict[Path, str]) -> list[dict]:
        """生成 nodeInfoList 数组（ID 模式），按 profile 取节点 ID。"""
        self._validate(spec, uploaded_files)
        prof = self.profile
        items: list[dict] = []
        params = self._compute_director_params(spec, uploaded_files)
        for fname in _DIRECTOR_FIELDS:
            if fname in params:
                items.append({"nodeId": prof.director_node,
                              "fieldName": fname, "fieldValue": params[fname]})
        items.append({"nodeId": prof.save_video_node,
                      "fieldName": "filename_prefix",
                      "fieldValue": spec.filename_prefix})
        if spec.noise_seed is not None:
            items.append({"nodeId": prof.noise_node,
                          "fieldName": "noise_seed", "fieldValue": spec.noise_seed})
        items.extend(self._resolution_items(spec))
        if prof.audio_switch_node:
            items.append({"nodeId": prof.audio_switch_node,
                          "fieldName": "switch",
                          "fieldValue": bool(spec.use_custom_audio)})
        for o in load_extras(prof):
            items.append({"nodeId": o["node"], "fieldName": o["field"],
                          "fieldValue": o.get("value")})
        return items

    def _resolution_items(self, spec: LTXDirectorSpec) -> list[dict]:
        prof = self.profile
        if prof.resolution_node:
            # 导演台：覆盖 TTResolutionSelector 节点
            if spec.use_custom_resolution:
                return [
                    {"nodeId": prof.resolution_node,
                     "fieldName": "use_custom_resolution", "fieldValue": True},
                    {"nodeId": prof.resolution_node,
                     "fieldName": "custom_width", "fieldValue": spec.custom_width},
                    {"nodeId": prof.resolution_node,
                     "fieldName": "custom_height", "fieldValue": spec.custom_height},
                ]
            return [{"nodeId": prof.resolution_node,
                     "fieldName": "resolution", "fieldValue": spec.resolution_preset}]
        # V3：无分辨率节点 → 落 director 的 custom_width/custom_height
        if spec.use_custom_resolution:
            w, h = spec.custom_width, spec.custom_height
        else:
            wh = parse_preset_wh(spec.resolution_preset)
            w, h = wh if wh else (spec.custom_width, spec.custom_height)
        return [
            {"nodeId": prof.director_node, "fieldName": "custom_width", "fieldValue": w},
            {"nodeId": prof.director_node, "fieldName": "custom_height", "fieldValue": h},
        ]
```

(The old inline resolution block + trailing CreateVideo.audio comment are removed/replaced by `_resolution_items`. Keep `_compute_director_params`, `_build_segments_payload`, `_validate` etc. unchanged.)

- [ ] **Step 3.5: 修正测试占位 + 运行**

Fix the Step 3.1 typo (`not_used_marker or True` → `"672" in node_ids and "683" in node_ids`) and wire `_make_spec_with_one_image` to the existing helper. Then:

Run: `pytest tests/test_providers/test_ltx_task_builder.py -v`
Expected: existing director tests still PASS + 3 new V3 tests PASS.

- [ ] **Step 3.6: 全量回归 + 提交**

Run: `pytest -q` → 0 failures。

```bash
git add drama_shot_master/providers/runninghub.py tests/test_providers/test_ltx_task_builder.py
git commit -m "feat(workflow): drive LTXTaskBuilder by WorkflowProfile

Node IDs, resolution strategy (selector node vs director custom_w/h),
audio-switch override, and YAML extras now come from the profile.
profile defaults to director (backward-compatible 1-arg construction).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 3)
- Read `tests/test_providers/test_ltx_task_builder.py` first — reuse its existing `LTXDirectorSpec` construction (the user recently refactored this file). Existing director tests must keep passing via the default profile.
- `LTXDirectorSpec` fields: `resolution_preset`, `use_custom_resolution`, `custom_width`, `custom_height`, `use_custom_audio`, `noise_seed`, `filename_prefix`, `segments` (each with `image_path`).
- Importing workflow_profiles into runninghub.py: no cycle (workflow_profiles imports only stdlib + yaml).
- Don't touch the user's untracked files.

---

## Task 4: config workflow_ids + 迁移（TDD）

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 4.1: 写失败测试**

Append to `tests/test_config.py`:

```python
def test_workflow_ids_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(workflow_ids={"director": "A", "director_v3": "B"})
    cfg2 = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg2.workflow_ids == {"director": "A", "director_v3": "B"}


def test_migrate_old_workflow_id(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(_json.dumps({"runninghub_workflow_id": "OLD"}))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.workflow_ids.get("director") == "OLD"
```

- [ ] **Step 4.2: 运行测试，确认失败**

Run: `pytest tests/test_config.py -v -k "workflow_ids or migrate_old_workflow"`
Expected: FAIL。

- [ ] **Step 4.3: 加字段 + 落盘 + 读取 + 迁移**

Edit `drama_shot_master/config.py`.

(a) In `Config` dataclass, after `video_tasks: list = field(default_factory=list)`, add:
```python
    workflow_ids: dict = field(default_factory=dict)
```

(b) In `update_settings`, add to the persisted dict:
```python
                "workflow_ids": self.workflow_ids,
```

(c) In `load_config`, in the settings.json read block, after the video_tasks read, add:
```python
                if "workflow_ids" in data and isinstance(data["workflow_ids"], dict):
                    cfg.workflow_ids = data["workflow_ids"]
```

(d) Near the end of `load_config`, before `return cfg` (alongside the other migrations), add:
```python
    if not cfg.workflow_ids and cfg.runninghub_workflow_id:
        cfg.workflow_ids = {"director": cfg.runninghub_workflow_id}
```

- [ ] **Step 4.4: 运行测试 + 全量回归 + 提交**

Run: `pytest tests/test_config.py -v` → PASS。 `pytest -q` → 0 failures。

```bash
git add drama_shot_master/config.py tests/test_config.py
git commit -m "feat(workflow): per-profile workflow_ids config + migrate old id

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 4)
- `config.py` already persists `video_tasks` and migrates `video_timeline_cache` near the end of load_config — add the workflow_ids read + migration in the same regions.

---

## Task 5: TimelineModel.workflow_key（TDD）

**Files:**
- Modify: `drama_shot_master/core/video_timeline_model.py`
- Test: `tests/test_core/test_video_timeline_model.py`

- [ ] **Step 5.1: 写失败测试**

Append to `tests/test_core/test_video_timeline_model.py`:

```python
def test_workflow_key_default_and_roundtrip():
    from drama_shot_master.core.video_timeline_model import TimelineModel
    m = TimelineModel()
    assert m.workflow_key == "director"
    m.workflow_key = "director_v3"
    d = m.to_dict()
    assert d["workflow_key"] == "director_v3"
    m2 = TimelineModel.from_dict(d)
    assert m2.workflow_key == "director_v3"


def test_workflow_key_missing_defaults_director():
    from drama_shot_master.core.video_timeline_model import TimelineModel
    m = TimelineModel.from_dict({"segments": []})
    assert m.workflow_key == "director"
```

- [ ] **Step 5.2: 运行，确认失败**

Run: `pytest tests/test_core/test_video_timeline_model.py -v -k workflow_key`
Expected: FAIL（字段不存在 / 不在 dict）。

- [ ] **Step 5.3: 加字段 + 序列化**

Edit `drama_shot_master/core/video_timeline_model.py`.

(a) In the `TimelineModel` dataclass fields (after `use_custom_audio: bool = False`), add:
```python
    workflow_key: str = "director"
```

(b) In `to_dict`, add to the returned dict (after `"use_custom_audio": self.use_custom_audio,`):
```python
            "workflow_key": self.workflow_key,
```

(c) In `from_dict`, after `m.use_custom_audio = bool(data.get("use_custom_audio", False))`, add:
```python
        m.workflow_key = data.get("workflow_key", "director")
```

- [ ] **Step 5.4: 运行 + 回归 + 提交**

Run: `pytest tests/test_core/test_video_timeline_model.py -v` → PASS。 `pytest -q` → 0 failures。

```bash
git add drama_shot_master/core/video_timeline_model.py tests/test_core/test_video_timeline_model.py
git commit -m "feat(workflow): persist workflow_key on TimelineModel

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 5)
- `TimelineModel` is a `@dataclass`; `workflow_key` is task-level metadata persisted with the timeline (so reopening a task restores its chosen workflow).

---

## Task 6: RunningHub 设置 — 每 profile 一个 workflow_id 框

**Files:**
- Modify: `drama_shot_master/ui/dialogs/runninghub_settings_dialog.py`

- [ ] **Step 6.1: 读现状 + 替换单 workflow_id 框为按 profile 生成**

Edit `drama_shot_master/ui/dialogs/runninghub_settings_dialog.py`. Read the file. It currently has a single `self.workflow_id_edit` (QLineEdit) with row "Workflow ID", loaded from `cfg.runninghub_workflow_id` and saved in `accept()`.

Replace the single field with one QLineEdit per built-in profile:

(a) Add import:
```python
from drama_shot_master.core.workflow_profiles import PROFILES
```

(b) In `_build_ui`, replace the single Workflow ID row:
```python
        self.workflow_id_edit = QLineEdit()
        self.workflow_id_edit.setPlaceholderText("平台已保存的工作流 ID（必填）")
        form.addRow("Workflow ID", self.workflow_id_edit)
```
with a dict of edits, one per profile:
```python
        self.workflow_id_edits: dict[str, QLineEdit] = {}
        for key, prof in PROFILES.items():
            edit = QLineEdit()
            edit.setPlaceholderText(f"{prof.name} 的 workflow_id")
            self.workflow_id_edits[key] = edit
            form.addRow(f"{prof.name} workflow_id", edit)
```

(c) In `_load_from_cfg`, replace the line setting `self.workflow_id_edit` with:
```python
        wf_ids = dict(self.cfg.workflow_ids or {})
        if "director" not in wf_ids and self.cfg.runninghub_workflow_id:
            wf_ids["director"] = self.cfg.runninghub_workflow_id
        for key, edit in self.workflow_id_edits.items():
            edit.setText(wf_ids.get(key, ""))
```

(d) In `accept`, replace the workflow-id validation/save. The current code validates `wf_id` non-empty and saves `runninghub_workflow_id=wf_id`. Replace with: collect all profile ids, require the director one non-empty (keep back-compat), and save the dict:
```python
        wf_ids = {key: edit.text().strip()
                  for key, edit in self.workflow_id_edits.items()}
        if not wf_ids.get("director"):
            QMessageBox.warning(self, "校验失败", "必须填「导演台」的 workflow_id")
            return
        # …existing api_key/base_url/template/video_out collection…
        self.cfg.update_settings(
            runninghub_api_key=api_key,
            runninghub_base_url=base_url,
            runninghub_workflow_id=wf_ids["director"],   # 旧字段保持兼容
            workflow_ids=wf_ids,
            runninghub_template_path=template_path,
            video_output_dir=video_out,
        )
        super().accept()
```
(Keep the other fields exactly as the existing `accept` collects them; only the workflow-id part changes. Read the method and adapt precisely — don't drop api_key/base_url/template/video_out handling.)

- [ ] **Step 6.2: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.dialogs.runninghub_settings_dialog import RunningHubSettingsDialog; print('ok')"
```
Expected: `ok`（或 ast 回退）。

- [ ] **Step 6.3: 全量回归 + 提交**

Run: `pytest -q` → 0 failures。

```bash
git add drama_shot_master/ui/dialogs/runninghub_settings_dialog.py
git commit -m "feat(workflow): per-profile workflow_id fields in RunningHub settings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 6)
- The dialog already has `cfg.workflow_ids` available (Task 4). Director id stays mirrored into `runninghub_workflow_id` for back-compat.
- Read `accept` and `_load_from_cfg` fully before editing; preserve the api_key/base_url/template/video_out logic.

---

## Task 7: VideoPanel 工作流下拉 + `_on_submit` 按 profile

**Files:**
- Modify: `drama_shot_master/ui/panels/video_panel.py`

- [ ] **Step 7.1: imports**

Edit `drama_shot_master/ui/panels/video_panel.py`. Add:
```python
from drama_shot_master.core.workflow_profiles import (
    PROFILES, get_profile, template_path_for,
)
```
Ensure `QComboBox` is imported from PySide6.QtWidgets (add to the existing import list if missing).

- [ ] **Step 7.2: 加工作流下拉到 toolbar**

Edit `drama_shot_master/ui/panels/video_panel.py`. In `_build_ui`, the pool toolbar adds buttons then `pool_toolbar.addStretch(1)` then Add Text/Audio/Refine. Insert a workflow selector at the LEFT of the toolbar (before the import buttons), or right after the stretch. Add after `pool_toolbar = QHBoxLayout()` creation, before adding the import buttons:
```python
        self.workflow_combo = QComboBox()
        for key, prof in PROFILES.items():
            self.workflow_combo.addItem(prof.name, key)
        pool_toolbar.addWidget(QLabel("工作流"))
        pool_toolbar.addWidget(self.workflow_combo)
```
(Ensure `QLabel` is imported.) Then in `_wire`, connect:
```python
        self.workflow_combo.currentIndexChanged.connect(self._on_workflow_changed)
```
And add the slot + an init sync. In `__init__` after `_refresh_all()` (or in a refresh), set the combo to `self.model.workflow_key`:
```python
    def _sync_workflow_combo(self):
        idx = self.workflow_combo.findData(self.model.workflow_key)
        if idx >= 0:
            self.workflow_combo.blockSignals(True)
            self.workflow_combo.setCurrentIndex(idx)
            self.workflow_combo.blockSignals(False)

    def _on_workflow_changed(self, _idx: int):
        key = self.workflow_combo.currentData()
        if key:
            self.model.workflow_key = key
```
Call `self._sync_workflow_combo()` at the end of `__init__` (after the model is set and UI built).

- [ ] **Step 7.3: 改 `_on_submit` 按 profile**

Edit `drama_shot_master/ui/panels/video_panel.py`. The current `_on_submit` resolves `template_path = resolve_template_path(self.cfg)` and uses `workflow_id=cfg.runninghub_workflow_id` + `builder = LTXTaskBuilder(template_path)`. Replace the relevant lines:

Current (around the resolve block + task closure):
```python
            api_key = resolve_api_key(self.cfg)
            template_path = resolve_template_path(self.cfg)
            out_dir = resolve_video_output_dir(self.cfg, self.state.output_dir)
```
Change to (resolve profile + per-profile workflow_id):
```python
            api_key = resolve_api_key(self.cfg)
            out_dir = resolve_video_output_dir(self.cfg, self.state.output_dir)
        profile = get_profile(self.model.workflow_key)
        template_path = template_path_for(profile)
        wf_id = (self.cfg.workflow_ids or {}).get(profile.key) or (
            self.cfg.runninghub_workflow_id if profile.key == "director" else "")
        if not wf_id:
            QMessageBox.warning(
                self, "未配置 workflow_id",
                f"请在「设置 → RunningHub」填「{profile.name}」的 workflow_id")
            return
```
(Keep the surrounding try/except for `resolve_*`. Note: `template_path` now comes from the profile, not `resolve_template_path`. Leave `resolve_template_path` import as-is if still referenced elsewhere; if unused now, remove its import.)

Then in the `task()` closure, change the builder + workflow_id:
```python
        def task():
            with RunningHubClient(api_key,
                                    base_url=cfg.runninghub_base_url) as client:
                builder = LTXTaskBuilder(template_path, profile)
                handle = submit_ltx_task(
                    client, spec, builder,
                    workflow_id=wf_id,
                    upload_progress_cb=lambda d, t, p: self._post(
                        "upload", (d, t, p.name)),
                )
                return handle.wait_for_result(
                    timeout=1800, poll_interval=8,
                    progress_cb=lambda s: self._post("status", s),
                    cancel_check=lambda: cancel_flag["v"],
                )
```
(`profile` and `wf_id` and `template_path` are captured by the closure; they're locals in `_on_submit`. `cfg`/`cancel_flag` capture stays as-is.)

- [ ] **Step 7.4: 烟测导入 + 回归**

Run:
```bash
python -c "from drama_shot_master.ui.panels.video_panel import VideoPanel; print('ok')"
```
Expected: `ok`（或 ast 回退）。

Run: `pytest -q` → 0 failures。

- [ ] **Step 7.5: 提交**

```bash
git add drama_shot_master/ui/panels/video_panel.py
git commit -m "feat(workflow): video panel workflow dropdown + profile-aware submit

A 工作流 dropdown bound to model.workflow_key; _on_submit resolves the
profile, its bundled template and per-profile workflow_id, and builds the
LTXTaskBuilder with that profile.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 7)
- Tasks 1/3/4/5 landed: profiles, builder(profile), cfg.workflow_ids, model.workflow_key all exist.
- The dropdown writes `model.workflow_key`; it persists via the existing window deactivate/close persistence (multi-task feature). No extra persistence wiring needed.
- `resolve_video_output_dir` / `resolve_api_key` stay. `resolve_template_path` is replaced by `template_path_for(profile)` for submission.
- Read `_on_submit` fully first; preserve the `spec = self.model.to_ltx_spec(out_dir)` and `_cancel_flag` setup.

---

## Task 8: 手测清单（end-of-feature）

**Files:** 无代码变更。

- [ ] **Step 8.1: 交回用户手测清单**（spec §7.4）

1. 设置 → RunningHub：出现「导演台 workflow_id」「V3 workflow_id」两个框；各填。
2. 任务窗口顶部「工作流」下拉切到 V3 → 关窗重开仍是 V3。
3. V3 任务提交 → 用 V3 workflow_id + 672/683/654 节点；正常出片。
4. V3 勾「启用音频轨」+ 上传音频提交 → 节点 687 switch=True 生效（上传音频路径）。
5. 编辑 `templates/ltx_v3_extras.yaml` 加一条 override 提交 → 生效。
6. 切回导演台任务 → 行为与之前一致（4/32/23/34）。
7. 旧 settings.json（只有 runninghub_workflow_id）启动 → 自动迁成 workflow_ids["director"]，导演台照常。

报告：全过 DONE；任一异常 DONE_WITH_CONCERNS + 具体步。

---

## Self-Review 记录

- **Spec coverage:**
  - §5.1 workflow_profiles → Task 1
  - §3/§7 V3 模板 + extras yaml → Task 2
  - §5.2 builder 参数化（节点/分辨率/音频开关/extras） → Task 3
  - §5.4 config workflow_ids + 迁移 → Task 4
  - §5.6 TimelineModel.workflow_key → Task 5
  - §5.5 设置每 profile workflow_id → Task 6
  - §5.7 下拉 + 提交改造 → Task 7
  - §6 错误处理（未配 id / 缺模板 / extras 缺失 / 旧任务默认 / 迁移） → Task 7（未配 id）+ Task 3（缺模板 RunningHubInvalidSpec、extras 安全跳过）+ Task 5（默认 director）+ Task 4（迁移）
  - §7 测试 → Task 1/3/4/5；§7.4 手测 → Task 8
- **Placeholder scan:** Task 3.1 测试里显式标注了一个 typo（`not_used_marker or True`）要在 3.5 改掉，并要求把 `_make_spec_with_one_image` 接到现有 fixture——这是给实现者的明确指令，不是占位遗漏。其余无 TBD。
- **Type consistency:**
  - `WorkflowProfile` 字段（director_node/save_video_node/noise_node/resolution_node/audio_switch_node/extras_yaml）Task 1 定义 → Task 3 用一致。
  - `get_profile/template_path_for/load_extras/parse_preset_wh`（Task 1）→ Task 3/7 调用一致。
  - `LTXTaskBuilder(template_path, profile=None)`（Task 3）→ Task 7 调 `LTXTaskBuilder(template_path, profile)`；旧 1-arg 调用仍兼容。
  - `cfg.workflow_ids: dict`（Task 4）→ Task 6/7 读写一致。
  - `TimelineModel.workflow_key`（Task 5）→ Task 7 读写一致。
  - `PROFILES`（Task 1）→ Task 6/7 遍历一致。
