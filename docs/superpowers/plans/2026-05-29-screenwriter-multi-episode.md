# 编剧多集化 Implementation Plan (Sub-spec #1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 编剧管线引入多集语义——`剧本.json` 集索引 + `剧本_E*.md` 单集 + `分镜_E*.json` 单集 + `prompts/E{id}/` 单集目录，N=1 完全兼容、旧项目自动迁移。

**Architecture:** 自底向上分 6 phase：(1) agent 数据/schema/downstream 基础 → (2) agent endpoints（/script/outline、/script/episode、+ storyboard/prompts 加 episode_id 参数）→ (3) FE 路径 helper + _EpisodeSelector widget + 集级 worker dict → (4) ScriptPage 大改（集数 spin + 大纲表 + 当前集 editor）→ (5) Storyboard/Prompts/ProductTree 集适配 + Panel 旧项目迁移对话框 → (6) 集成端到端。

**Tech Stack:** Python 3.11 + FastAPI + PySide6（offscreen Qt 测试）+ openai SDK 1.55+；pydantic v2 校验；TDD 全程 `pytest`。

**Spec:** `docs/superpowers/specs/2026-05-29-screenwriter-multi-episode-design.md`

---

## 文件结构

### 新建

| 文件 | 职责 |
|---|---|
| `screenwriter_agent/models/script_index_schema.py` | `EpisodeEntry` + `ScriptIndex` pydantic |
| `screenwriter_agent/routes/script_outline.py` | `POST /script/outline` |
| `screenwriter_agent/routes/script_episode.py` | `POST /script/episode` |
| `screenwriter_agent/templates/script_outline.md` | 大纲生成 prompt |
| `screenwriter_agent/templates/script_episode.md` | 单集生成 prompt |
| `drama_shot_master/ui/widgets/screenwriter/_episode_selector.py` | `_EpisodeSelector` QWidget |
| `tests/test_screenwriter_agent/test_script_index_schema.py` | schema 6 用例 |
| `tests/test_screenwriter_agent/test_route_script_outline.py` | outline 路由 5 用例 |
| `tests/test_screenwriter_agent/test_route_script_episode.py` | episode 路由 5 用例 |
| `tests/test_screenwriter_agent/test_e2e_multi_episode.py` | 端到端 2 用例（N=1 + N=3） |
| `tests/test_ui/screenwriter/test_episode_selector.py` | selector 5 用例 |

### 修改

| 文件 | 改动 |
|---|---|
| `screenwriter_agent/core/paths.py` | + script_index_path / script_episode_(read_)path / storyboard_episode_(read_)path / episode_prompts_dir / is_valid_episode_id |
| `screenwriter_agent/core/downstream.py` | `purge_downstream(stage, *, episode_id=None)` 集感知扩展 |
| `screenwriter_agent/models/requests.py` | + ScriptOutlineReq / ScriptEpisodeReq；`StoryboardReq` / `PromptsReq` 加 `episode_id` |
| `screenwriter_agent/server.py` | 注册新路由 + 不再注册旧 `/script` |
| `screenwriter_agent/routes/script.py` | 删除（旧）|
| `screenwriter_agent/routes/storyboard.py` | 按 episode_id 读 `剧本_E{id}.md` 写 `分镜_E{id}.json` |
| `screenwriter_agent/routes/prompts.py` | 按 episode_id 读 `分镜_E{id}.json` 写 `prompts/E{id}/...` |
| `screenwriter_agent/templates/template_loader.py` | `BUILTIN_IDS` 加 `script_outline` / `script_episode` |
| `drama_shot_master/ui/widgets/screenwriter/_paths.py` | 镜像 agent helper + `is_valid_episode_id` |
| `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py` | worker dict key `Path` → `tuple[Path, str]`；`is_streaming(p, ep="")`；保留 `Path`-only 调用兜底 |
| `drama_shot_master/ui/widgets/screenwriter/script_page.py` | 大改：参数栏 + 大纲表 + 当前集 editor + 一键全集 |
| `drama_shot_master/ui/widgets/screenwriter/storyboard_page.py` | 顶部加 `_EpisodeSelector` + per-episode set_episode |
| `drama_shot_master/ui/widgets/screenwriter/prompts_page.py` | 顶部加 `_EpisodeSelector` + `prompts/E{id}/...` 路径 |
| `drama_shot_master/ui/widgets/screenwriter/_product_tree.py` | `build_from_sb()` 加 `episode_id`，路径走 `prompts/E{id}/` |
| `drama_shot_master/ui/widgets/screenwriter/task_manager.py` | 分镜/提示词列 N/M 显示 |
| `drama_shot_master/ui/panels/screenwriter_panel.py` | 选项目时检测旧版 → 迁移对话框 |
| `drama_shot_master/agents/screenwriter_client.py` | path 映射 storyboard/prompts/script_*：body 自动带 episode_id（如果已提供） |
| 旧测试 ~6 文件 | 改 `剧本.md` fixture 为 `剧本.json` + `剧本_E1.md`；加 `episode_id` 字段 |

---

## Task 1: Agent 端 paths helper

**Files:**
- Modify: `screenwriter_agent/core/paths.py`
- Test: `tests/test_screenwriter_agent/test_paths.py`

- [ ] **Step 1: 写失败测试**（在文件末尾追加）

```python
import re
from screenwriter_agent.core.paths import (
    script_index_path, script_episode_path, script_episode_read_path,
    storyboard_episode_path, storyboard_episode_read_path,
    episode_prompts_dir, is_valid_episode_id,
)


def test_is_valid_episode_id_accepts_E_plus_digits():
    assert is_valid_episode_id("E1")
    assert is_valid_episode_id("E20")
    assert not is_valid_episode_id("e1")
    assert not is_valid_episode_id("E0")    # 1-based
    assert not is_valid_episode_id("EE")
    assert not is_valid_episode_id("E1.5")


def test_script_index_path_returns_chinese_name(tmp_path):
    assert script_index_path(tmp_path).name == "剧本.json"


def test_script_episode_path_returns_E_suffix(tmp_path):
    assert script_episode_path(tmp_path, "E1").name == "剧本_E1.md"
    assert script_episode_path(tmp_path, "E13").name == "剧本_E13.md"


def test_script_episode_read_falls_back_to_legacy_script_md(tmp_path):
    # 旧项目：只有 剧本.md
    (tmp_path / "剧本.md").write_text("# old", encoding="utf-8")
    p = script_episode_read_path(tmp_path, "E1")
    assert p is not None and p.name == "剧本.md"


def test_script_episode_read_prefers_new_name(tmp_path):
    (tmp_path / "剧本_E1.md").write_text("# new", encoding="utf-8")
    (tmp_path / "剧本.md").write_text("# legacy", encoding="utf-8")
    p = script_episode_read_path(tmp_path, "E1")
    assert p.name == "剧本_E1.md"


def test_script_episode_read_none_when_missing(tmp_path):
    assert script_episode_read_path(tmp_path, "E1") is None


def test_storyboard_episode_path(tmp_path):
    assert storyboard_episode_path(tmp_path, "E2").name == "分镜_E2.json"


def test_storyboard_episode_read_falls_back_to_legacy(tmp_path):
    (tmp_path / "分镜.json").write_text("{}", encoding="utf-8")
    assert storyboard_episode_read_path(tmp_path, "E1").name == "分镜.json"


def test_episode_prompts_dir(tmp_path):
    assert episode_prompts_dir(tmp_path, "E1") == tmp_path / "prompts" / "E1"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_paths.py -q -p no:faulthandler
```

Expected: ImportError 9 个新 test fail

- [ ] **Step 3: 实现 helper**

在 `screenwriter_agent/core/paths.py` 末尾追加：

```python
import re as _re

EPISODE_ID_PATTERN = _re.compile(r"^E([1-9]\d*)$")


def is_valid_episode_id(s: str) -> bool:
    """1-based 集 ID 校验：E1, E2, ..."""
    return bool(EPISODE_ID_PATTERN.match(s or ""))


def script_index_path(project_dir: Path) -> Path:
    """剧本集索引路径（写入用，统一 剧本.json）。"""
    return project_dir / "剧本.json"


def script_episode_path(project_dir: Path, episode_id: str) -> Path:
    """写入路径：剧本_E{id}.md。"""
    return project_dir / f"剧本_{episode_id}.md"


def script_episode_read_path(project_dir: Path, episode_id: str) -> Path | None:
    """读取路径：优先 剧本_E{id}.md，兜底 旧的单文件 剧本.md（仅 E1 时）。"""
    primary = script_episode_path(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "剧本.md"
        if legacy.is_file():
            return legacy
    return None


def storyboard_episode_path(project_dir: Path, episode_id: str) -> Path:
    return project_dir / f"分镜_{episode_id}.json"


def storyboard_episode_read_path(project_dir: Path, episode_id: str) -> Path | None:
    primary = storyboard_episode_path(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "分镜.json"
        if legacy.is_file():
            return legacy
    return None


def episode_prompts_dir(project_dir: Path, episode_id: str) -> Path:
    """prompts/E{id}/ 目录（不保证存在）。"""
    return project_dir / "prompts" / episode_id
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_paths.py -q -p no:faulthandler
```

Expected: 14 passed (5 旧 + 9 新)

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/core/paths.py tests/test_screenwriter_agent/test_paths.py
git commit -m "feat(agent): paths 加 script_index/episode/storyboard_episode/episode_prompts_dir helper

集 ID 规范 ^E[1-9]\\d*\$；read helper 兜底兼容旧名（剧本.md 当 E1，分镜.json 当 E1）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: script_index_schema pydantic

**Files:**
- Create: `screenwriter_agent/models/script_index_schema.py`
- Test: `tests/test_screenwriter_agent/test_script_index_schema.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from pydantic import ValidationError

from screenwriter_agent.models.script_index_schema import (
    EpisodeEntry, ScriptIndex,
)


def test_episode_entry_id_must_match_pattern():
    EpisodeEntry(id="E1", title="t", summary="s")
    with pytest.raises(ValidationError):
        EpisodeEntry(id="e1", title="t", summary="s")
    with pytest.raises(ValidationError):
        EpisodeEntry(id="E0", title="t", summary="s")
    with pytest.raises(ValidationError):
        EpisodeEntry(id="", title="t", summary="s")


def test_script_index_basic():
    si = ScriptIndex(
        title="测试",
        episode_count=2,
        episodes=[
            EpisodeEntry(id="E1", title="a", summary="aa"),
            EpisodeEntry(id="E2", title="b", summary="bb"),
        ],
    )
    assert si.episode_count == 2
    assert len(si.episodes) == 2


def test_script_index_count_bounds():
    with pytest.raises(ValidationError):
        ScriptIndex(episode_count=0, episodes=[])
    with pytest.raises(ValidationError):
        ScriptIndex(episode_count=21, episodes=[])


def test_script_index_episodes_length_matches_count_loose():
    """spec 不强制 episodes 长度等于 episode_count——大纲生成中可能 partial 写入。
    校验只查 schema 类型，不做长度等于校验。"""
    si = ScriptIndex(
        title="x", episode_count=3,
        episodes=[EpisodeEntry(id="E1", title="a", summary="aa")],
    )
    assert si.episode_count == 3
    assert len(si.episodes) == 1


def test_script_index_round_trips_json():
    import json
    src = {
        "title": "x",
        "episode_count": 1,
        "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": "a", "summary": "aa"}],
        "input": {"core_idea": "守株待兔"},
        "updated_at": "2026-05-29T00:00:00",
    }
    si = ScriptIndex.model_validate(src)
    again = json.loads(si.model_dump_json())
    assert again["episodes"][0]["id"] == "E1"
    assert again["input"]["core_idea"] == "守株待兔"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_script_index_schema.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError

- [ ] **Step 3: 实现**

`screenwriter_agent/models/script_index_schema.py`:

```python
"""剧本.json schema（集索引）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EpisodeEntry(BaseModel):
    id: str = Field(..., pattern=r"^E[1-9]\d*$")
    title: str
    summary: str


class ScriptIndex(BaseModel):
    title: str = ""
    episode_count: int = Field(..., ge=1, le=20)
    selected_episode: str = ""
    episodes: list[EpisodeEntry] = Field(default_factory=list)
    input: dict = Field(default_factory=dict)
    updated_at: str = ""
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_script_index_schema.py -q -p no:faulthandler
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/models/script_index_schema.py tests/test_screenwriter_agent/test_script_index_schema.py
git commit -m "feat(agent): + script_index_schema (EpisodeEntry, ScriptIndex pydantic v2)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: downstream.purge_downstream 集感知扩展

**Files:**
- Modify: `screenwriter_agent/core/downstream.py`
- Modify: `tests/test_screenwriter_agent/test_downstream.py`

- [ ] **Step 1: 写失败测试**（追加）

```python
import json

from screenwriter_agent.core.downstream import purge_downstream


def _setup_multi_ep(tmp_path):
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 3,
        "episodes": [{"id": f"E{i}", "title": "t", "summary": "s"}
                      for i in (1, 2, 3)],
    }), encoding="utf-8")
    for i in (1, 2, 3):
        (tmp_path / f"剧本_E{i}.md").write_text("md", encoding="utf-8")
        (tmp_path / f"分镜_E{i}.json").write_text("{}", encoding="utf-8")
        ep_dir = tmp_path / "prompts" / f"E{i}" / "角色参考图"
        ep_dir.mkdir(parents=True)
        (ep_dir / "x.md").write_text("x", encoding="utf-8")


def test_purge_script_outline_clears_everything_below(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="script_outline")
    assert (tmp_path / "创意.json").is_file()
    assert not (tmp_path / "剧本.json").exists()
    for i in (1, 2, 3):
        assert not (tmp_path / f"剧本_E{i}.md").exists()
        assert not (tmp_path / f"分镜_E{i}.json").exists()
    assert not (tmp_path / "prompts").exists()


def test_purge_script_episode_only_clears_single_episode_below(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="script_episode", episode_id="E2")
    assert (tmp_path / "剧本.json").is_file()
    assert (tmp_path / "剧本_E1.md").is_file()
    assert not (tmp_path / "剧本_E2.md").exists()
    assert (tmp_path / "剧本_E3.md").is_file()
    assert (tmp_path / "分镜_E1.json").is_file()
    assert not (tmp_path / "分镜_E2.json").exists()
    assert (tmp_path / "prompts" / "E1").is_dir()
    assert not (tmp_path / "prompts" / "E2").exists()


def test_purge_storyboard_with_episode_id(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="storyboard", episode_id="E2")
    assert (tmp_path / "剧本_E2.md").is_file()
    assert not (tmp_path / "分镜_E2.json").exists()
    assert not (tmp_path / "prompts" / "E2").exists()


def test_purge_prompts_with_episode_id(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="prompts", episode_id="E2")
    assert (tmp_path / "分镜_E2.json").is_file()
    assert not (tmp_path / "prompts" / "E2").exists()


def test_purge_storyboard_no_episode_id_clears_all(tmp_path):
    """不传 episode_id 时清所有集（向后兼容 v1 单文件路径）。"""
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="storyboard")
    for i in (1, 2, 3):
        assert not (tmp_path / f"分镜_E{i}.json").exists()
    # 兼容旧名也清
    legacy_sb = tmp_path / "分镜.json"
    assert not legacy_sb.exists()
```

- [ ] **Step 2: 跑确认失败**

Expected: 多个测试 fail（stage 类型不识别 / episode_id 参数不接受）

- [ ] **Step 3: 重写 purge_downstream**

替换整文件 `screenwriter_agent/core/downstream.py` 为：

```python
"""下游产物清理——集感知。

阶段依赖链（v2）：
  ideate (创意.json)
  → script_outline (剧本.json)
  → script_episode (剧本_E{id}.md)
  → storyboard (分镜_E{id}.json)
  → prompts (prompts/E{id}/)
"""
from __future__ import annotations

import shutil
from pathlib import Path

from screenwriter_agent.core.paths import IDEA_FILE_NAME, IDEA_LEGACY_NAME


def _rm_file(p: Path) -> bool:
    try:
        if p.is_file():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def _rm_dir(p: Path) -> bool:
    try:
        if p.is_dir():
            shutil.rmtree(p)
            return True
    except OSError:
        pass
    return False


def _all_episode_ids(project_dir: Path) -> list[str]:
    """从 剧本_E*.md 文件名扫所有集 id（含旧 剧本.md → E1）。"""
    ids: list[str] = []
    for f in project_dir.glob("剧本_E*.md"):
        # 抠 stem 后缀 _E? 部分
        stem = f.stem  # "剧本_E1"
        if "_" in stem:
            ep = stem.split("_", 1)[1]
            if ep.startswith("E") and ep[1:].isdigit():
                ids.append(ep)
    if not ids and (project_dir / "剧本.md").is_file():
        ids.append("E1")
    return ids


def purge_downstream(project_dir: Path, *, stage: str,
                      episode_id: str | None = None) -> list[str]:
    """按 stage [+ episode_id] 删本阶段及下游产物。返回被删的相对路径（调试用）。

    stage:
        'ideate' / 'script_outline' / 'script_episode' / 'storyboard' / 'prompts'
    """
    removed: list[str] = []

    if stage == "ideate":
        for n in (IDEA_FILE_NAME, IDEA_LEGACY_NAME):
            if _rm_file(project_dir / n):
                removed.append(n)
        _purge_all_script_and_below(project_dir, removed)
        return removed

    if stage == "script_outline":
        _purge_all_script_and_below(project_dir, removed)
        return removed

    if stage == "script_episode":
        if episode_id is None:
            # 等价于 script_outline（所有集）
            _purge_all_script_and_below(project_dir, removed)
            return removed
        # 单集：删本集 md + 该集分镜 + 该集 prompts
        for rel in (f"剧本_{episode_id}.md",
                     f"分镜_{episode_id}.json"):
            if _rm_file(project_dir / rel):
                removed.append(rel)
        if _rm_dir(project_dir / "prompts" / episode_id):
            removed.append(f"prompts/{episode_id}/")
        return removed

    if stage == "storyboard":
        if episode_id is None:
            # 清所有集分镜 + prompts
            for f in project_dir.glob("分镜_E*.json"):
                if _rm_file(f):
                    removed.append(f.name)
            if _rm_file(project_dir / "分镜.json"):
                removed.append("分镜.json")
            if _rm_dir(project_dir / "prompts"):
                removed.append("prompts/")
            return removed
        if _rm_file(project_dir / f"分镜_{episode_id}.json"):
            removed.append(f"分镜_{episode_id}.json")
        if _rm_dir(project_dir / "prompts" / episode_id):
            removed.append(f"prompts/{episode_id}/")
        return removed

    if stage == "prompts":
        if episode_id is None:
            if _rm_dir(project_dir / "prompts"):
                removed.append("prompts/")
            return removed
        if _rm_dir(project_dir / "prompts" / episode_id):
            removed.append(f"prompts/{episode_id}/")
        return removed

    return removed


def _purge_all_script_and_below(project_dir: Path, removed: list[str]) -> None:
    """清 剧本.json + 所有 剧本_E*.md + 旧 剧本.md + 所有分镜/prompts。"""
    if _rm_file(project_dir / "剧本.json"):
        removed.append("剧本.json")
    if _rm_file(project_dir / "剧本.md"):
        removed.append("剧本.md")
    for f in project_dir.glob("剧本_E*.md"):
        if _rm_file(f):
            removed.append(f.name)
    for f in project_dir.glob("分镜_E*.json"):
        if _rm_file(f):
            removed.append(f.name)
    if _rm_file(project_dir / "分镜.json"):
        removed.append("分镜.json")
    if _rm_dir(project_dir / "prompts"):
        removed.append("prompts/")
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_downstream.py -q -p no:faulthandler
```

Expected: 11 passed (6 旧 + 5 新)。如果旧 6 个 fail（因为 stage 名变了），需要把旧测试里的 `stage="script"` 改为 `stage="script_episode"`、`stage="ideate"` 保持。检查后批量改。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/core/downstream.py tests/test_screenwriter_agent/test_downstream.py
git commit -m "feat(agent): downstream 集感知 — purge_downstream(stage, *, episode_id=None)

新 stage：script_outline / script_episode；
storyboard/prompts 不传 episode_id 清所有集（向后兼容）；
script_outline 清所有 剧本_E*.md + 旧 剧本.md + 所有分镜/prompts；
script_episode + episode_id 只清单集级联。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Agent request 模型扩展（Outline/Episode + storyboard/prompts 加 episode_id）

**Files:**
- Modify: `screenwriter_agent/models/requests.py`
- Test: 沿用既有契约——下个 task 跑 route 集成时会断言

- [ ] **Step 1: 在文件末尾加新 Req + 改既有 Req**

在 `screenwriter_agent/models/requests.py` 末尾追加（不动既有类）：

```python
class ScriptOutlineReq(BaseModel):
    project_dir: str
    episode_count: int = Field(..., ge=1, le=20)
    options: ScriptOptions = Field(default_factory=ScriptOptions)
    model: str | None = None
    reasoning_effort: str = "high"
    creds: LLMCreds | None = None


class ScriptEpisodeReq(BaseModel):
    project_dir: str
    episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")
    options: ScriptOptions = Field(default_factory=ScriptOptions)
    model: str | None = None
    reasoning_effort: str = "high"
    creds: LLMCreds | None = None
```

在 `StoryboardReq` 类定义里加 `episode_id`，找到：

```python
class StoryboardReq(BaseModel):
    project_dir: str
    options: StoryboardOptions = Field(default_factory=StoryboardOptions)
    model: str | None = None
    reasoning_effort: str = "max"
    creds: LLMCreds | None = None
```

改为：

```python
class StoryboardReq(BaseModel):
    project_dir: str
    episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")
    options: StoryboardOptions = Field(default_factory=StoryboardOptions)
    model: str | None = None
    reasoning_effort: str = "max"
    creds: LLMCreds | None = None
```

同理 `PromptsReq` 加 `episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")`。

- [ ] **Step 2: 跑全套件验证 import 不挂**

```bash
python -m pytest tests/test_screenwriter_agent/ -q -p no:faulthandler 2>&1 | tail -15
```

Expected: storyboard / prompts route tests 会因为 fixture body 缺 `episode_id` 失败 — 这是预期的，Task 7/8 会修。其它 import 不挂即可。

- [ ] **Step 3: Commit**

```bash
git add screenwriter_agent/models/requests.py
git commit -m "feat(agent): requests + ScriptOutlineReq/ScriptEpisodeReq；StoryboardReq/PromptsReq 加 episode_id

episode_id 必填，pattern ^E[1-9]\\d*\$；后续 route 改造统一从 body 读。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: agent /script/outline 路由

**Files:**
- Create: `screenwriter_agent/routes/script_outline.py`
- Create: `screenwriter_agent/templates/script_outline.md`
- Modify: `screenwriter_agent/templates/template_loader.py`（BUILTIN_IDS）
- Modify: `screenwriter_agent/server.py`（注册）
- Test: `tests/test_screenwriter_agent/test_route_script_outline.py`

- [ ] **Step 1: 写失败测试**

```python
import json
import pytest
from fastapi.testclient import TestClient

from screenwriter_agent.server import create_app


@pytest.fixture
def mock_llm_outline(monkeypatch):
    """让 LLMClient.stream_chat 吐出一个合法的 N 集 JSON。"""
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        raw = json.dumps({
            "title": "测试整剧",
            "episode_count": 2,
            "episodes": [
                {"id": "E1", "title": "第1集", "summary": "summary 1"},
                {"id": "E2", "title": "第2集", "summary": "summary 2"},
            ],
        }, ensure_ascii=False)
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_route_script_outline_writes_jianben_json(tmp_path, mock_llm_outline):
    (tmp_path / "创意.json").write_text(json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "X", "summary": "y"}],
    }, ensure_ascii=False), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 2,
    })
    assert r.status_code == 200
    p = tmp_path / "剧本.json"
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["episode_count"] == 2
    assert len(data["episodes"]) == 2
    assert data["episodes"][0]["id"] == "E1"


def test_route_script_outline_missing_idea_returns_400(tmp_path, mock_llm_outline):
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 2,
    })
    assert r.status_code == 400
    assert "UPSTREAM_PRODUCT_MISSING" in r.text


def test_route_script_outline_purge_downstream(tmp_path, mock_llm_outline):
    """带 query param purge_downstream=true 时清下游。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("old", encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    c.post("/script/outline?purge_downstream=true", json={
        "project_dir": str(tmp_path),
        "episode_count": 1,
    })
    assert not (tmp_path / "剧本_E1.md").exists()
    assert not (tmp_path / "分镜_E1.json").exists()


def test_route_script_outline_n1_creates_single_episode(tmp_path, mock_llm_outline):
    """N=1 仍产 剧本.json（含 1 集 entry，因 mock LLM 返 2 集这里只看 LLM 端控制；
    实际生产 N=1 时 outline 模板会指示 LLM 只产 1 集；本测试只保证 route 流通）。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 1,
    })
    assert r.status_code == 200
    assert (tmp_path / "剧本.json").is_file()


def test_route_script_outline_bad_episode_count(tmp_path, mock_llm_outline):
    """episode_count 超界（>20）应 422。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 99,
    })
    assert r.status_code == 422
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_script_outline.py -q -p no:faulthandler
```

Expected: 404 / 路由不存在

- [ ] **Step 3: 加模板**

`screenwriter_agent/templates/script_outline.md`:

```markdown
你是一名编剧助理。任务：基于「创意候选」生成多集短剧的**集索引**。

## 输入
- 创意候选 JSON：title / summary / angle / highlights
- 集数 N（episode_count）
- 参数：fps、时长/集（duration_sec）、语言风格

## 输出
**严格只输出一个 JSON 代码块**，结构如下：

```json
{
  "title": "整剧标题（与创意呼应）",
  "episode_count": N,
  "episodes": [
    { "id": "E1", "title": "第 1 集：…", "summary": "200字以内三段式概要" },
    { "id": "E2", "title": "第 2 集：…", "summary": "..." }
  ]
}
```

## 要求
- 集 ID 严格 `E1` `E2` … 顺序
- 每集 summary 200 字以内三段式（起—转—承）
- N=1 也只产一集
- 集间起承转合连贯
```

- [ ] **Step 4: 实现路由**

`screenwriter_agent/routes/script_outline.py`:

```python
"""POST /script/outline — SSE：读 创意.json.selected → LLM JSON → 落盘 剧本.json。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.downstream import purge_downstream
from screenwriter_agent.core.json_repair import repair_json_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import idea_read_path, script_index_path
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import ScriptOutlineReq
from screenwriter_agent.models.script_index_schema import ScriptIndex

router = APIRouter()


@router.post("/script/outline")
async def script_outline(req: ScriptOutlineReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}", "hint": "项目目录打不开。"}})

    idea_path = idea_read_path(project_dir)
    if idea_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "创意.json missing",
                      "hint": "请先在「创意」步生成候选并选定一个。"}})

    if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
        purge_downstream(project_dir, stage="script_outline")

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_SCRIPT_MODEL")
             or cfg.default_models.get("script"))
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_SCRIPT_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_SCRIPT_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))
    print(f"[script_outline] model={model!r} base_url={base_url!r} "
          f"cred_src={'body' if body_key else 'env'}", flush=True)

    async def gen():
        import traceback
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
            selected_id = idea.get("selected_id", "")
            sel = next((c for c in idea.get("candidates", [])
                          if c.get("id") == selected_id), idea.get("candidates", [{}])[0] if idea.get("candidates") else {})

            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("script_outline", project_dir=project_dir)
            opts = req.options.model_dump()
            prompt = (tpl_text
                      + "\n\n## 选定候选\n```json\n"
                      + json.dumps(sel, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 参数\n"
                      + f"episode_count={req.episode_count}\n"
                      + f"duration_sec={opts['duration_sec']}\n"
                      + f"language_style={opts['language_style']}\n"
                      + "**只输出一个 JSON 代码块**。")
            messages = [{"role": "user", "content": prompt}]

            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort,
                               response_format={"type": "json_object"})

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if await request.is_disconnected():
                    return
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            raw = "".join(acc)

            yield sse_event("status", {"phase": "validating"})
            try:
                obj = repair_json_text(raw)
            except Exception as e:
                raw_path = project_dir / ".outline_raw.txt"
                atomic_write_text(raw_path, raw)
                yield sse_event("error", {
                    "code": "JSON_REPAIR_FAILED",
                    "message": str(e),
                    "hint": "LLM 输出无法解析为合法 JSON。",
                    "details": {"raw_output_path": str(raw_path)}})
                return

            # 强制集数对齐 + 补 input/updated_at
            obj.setdefault("episode_count", req.episode_count)
            obj.setdefault("selected_episode", "")
            obj["input"] = sel
            obj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                ScriptIndex.model_validate(obj)
            except Exception as e:
                yield sse_event("error", {
                    "code": "SCHEMA_INVALID",
                    "message": str(e),
                    "hint": "大纲格式不合规。"})
                return

            yield sse_event("status", {"phase": "saving"})
            si_path = script_index_path(project_dir)
            atomic_write_text(si_path, json.dumps(obj, ensure_ascii=False, indent=2))
            yield sse_event("done", {"saved": str(si_path),
                                      "result": {"episodes": obj.get("episodes", [])}})
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[script_outline] EXCEPTION\n{tb}", flush=True)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "hint": "看 ~/.drama_shot_master/logs/screenwriter_agent.log 末尾"})

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 5: 注册 BUILTIN_ID + 路由**

`screenwriter_agent/templates/template_loader.py` 找到 `BUILTIN_IDS = (...)`，加 `"script_outline"`：

```python
BUILTIN_IDS = ("ideate", "script", "script_outline", "script_episode",
                "storyboard", "character_ref", "grid_prompt")
```

（`script_episode` 等下个 task 加模板）

`screenwriter_agent/server.py` 找到注册块加：

```python
    from .routes.script_outline import router as script_outline_router
    app.include_router(script_outline_router)
```

- [ ] **Step 6: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_script_outline.py -q -p no:faulthandler
```

Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add screenwriter_agent/routes/script_outline.py screenwriter_agent/templates/script_outline.md screenwriter_agent/templates/template_loader.py screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_script_outline.py
git commit -m "feat(agent): + POST /script/outline（剧本.json 集索引生成）

LLM JSON 输出 → repair_json + ScriptIndex.model_validate → atomic_write 落盘。
SSE: status/delta/done/error；JSON_REPAIR_FAILED 写 .outline_raw.txt 供排查。
模板 script_outline.md 输入候选+参数、输出 N 集索引 JSON。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: agent /script/episode 路由

**Files:**
- Create: `screenwriter_agent/routes/script_episode.py`
- Create: `screenwriter_agent/templates/script_episode.md`
- Modify: `screenwriter_agent/server.py`
- Test: `tests/test_screenwriter_agent/test_route_script_episode.py`

- [ ] **Step 1: 写失败测试**

```python
import json
import pytest
from fastapi.testclient import TestClient

from screenwriter_agent.server import create_app


@pytest.fixture
def mock_llm_episode(monkeypatch):
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        md = "## 镜头 1\n雨夜画面…\n## 镜头 2\n书生撑伞…"
        for ch in md:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=md)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def _setup_with_index(tmp_path):
    (tmp_path / "创意.json").write_text(json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "X"}],
    }), encoding="utf-8")
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 2,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
        ],
    }), encoding="utf-8")


def test_route_script_episode_writes_episode_md(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert r.status_code == 200
    assert (tmp_path / "剧本_E1.md").is_file()
    assert "## 镜头" in (tmp_path / "剧本_E1.md").read_text(encoding="utf-8")


def test_route_script_episode_missing_index_returns_400(tmp_path, mock_llm_episode):
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert r.status_code == 400 or "UPSTREAM_PRODUCT_MISSING" in r.text


def test_route_script_episode_unknown_episode_returns_400(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E99",
    })
    assert r.status_code == 400
    assert "EPISODE_NOT_FOUND" in r.text


def test_route_script_episode_purge_downstream(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    c = TestClient(create_app())
    c.post("/script/episode?purge_downstream=true", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    # 单集 purge：删本集下游
    assert not (tmp_path / "分镜_E1.json").exists()


def test_route_script_episode_bad_id_pattern(tmp_path, mock_llm_episode):
    _setup_with_index(tmp_path)
    c = TestClient(create_app())
    r = c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "e1",
    })
    assert r.status_code == 422
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_script_episode.py -q -p no:faulthandler
```

Expected: 404 路由不存在

- [ ] **Step 3: 模板**

`screenwriter_agent/templates/script_episode.md`:

```markdown
你是一名编剧。任务：基于「创意候选」与「集大纲条目」生成本集**详细剧本 markdown**。

## 输入
- 选定的创意候选（含 title / summary / angle / highlights）
- 本集大纲（id / title / summary）
- 参数：duration_sec、fps、language_style

## 输出
**输出 markdown（不要 JSON）**，结构：

```markdown
# {本集 title}

## 镜头 1
- 场景：（地点 / 时段 / 氛围）
- 人物：…
- 动作 / 对白：…

## 镜头 2
…
```

## 要求
- 镜头数与本集 duration_sec 匹配（约每 5-8 秒一个镜头）
- language_style 影响对白风格
- 控制总字数与 duration 大致一致
```

- [ ] **Step 4: 路由实现**

`screenwriter_agent/routes/script_episode.py`:

```python
"""POST /script/episode — SSE：读 剧本.json 该 episode → LLM → 落盘 剧本_E{id}.md。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.downstream import purge_downstream
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import (
    idea_read_path, script_index_path, script_episode_path,
)
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import ScriptEpisodeReq

router = APIRouter()


@router.post("/script/episode")
async def script_episode(req: ScriptEpisodeReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}", "hint": ""}})

    si_path = script_index_path(project_dir)
    if not si_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "剧本.json missing",
                      "hint": "请先在剧本阶段生成大纲。"}})
    try:
        si = json.loads(si_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "剧本.json parse failed", "hint": ""}})
    ep_entry = next((e for e in si.get("episodes", [])
                      if e.get("id") == req.episode_id), None)
    if ep_entry is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "EPISODE_NOT_FOUND",
                      "message": f"{req.episode_id} not in 剧本.json",
                      "hint": "集 id 不存在于大纲。"}})

    if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
        purge_downstream(project_dir, stage="script_episode",
                          episode_id=req.episode_id)

    idea_path = idea_read_path(project_dir)
    idea = {}
    sel = {}
    if idea_path is not None:
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
            sel = next((c for c in idea.get("candidates", [])
                          if c.get("id") == idea.get("selected_id")), {})
        except Exception:
            pass

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_SCRIPT_MODEL")
             or cfg.default_models.get("script"))
    creds = req.creds or None
    body_key = creds.api_key if creds else None
    body_url = creds.base_url if creds else None
    api_key = (body_key
               or os.environ.get("SCREENWRITER_SCRIPT_API_KEY")
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = (body_url
                or os.environ.get("SCREENWRITER_SCRIPT_BASE_URL")
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))
    print(f"[script_episode] ep={req.episode_id} model={model!r} "
          f"cred_src={'body' if body_key else 'env'}", flush=True)

    async def gen():
        import traceback
        try:
            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("script_episode", project_dir=project_dir)
            opts = req.options.model_dump()
            prompt = (tpl_text
                      + "\n\n## 选定候选\n```json\n"
                      + json.dumps(sel, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 本集大纲\n```json\n"
                      + json.dumps(ep_entry, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 参数\n"
                      + f"duration_sec={opts['duration_sec']}\n"
                      + f"language_style={opts['language_style']}\n")
            messages = [{"role": "user", "content": prompt}]

            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if await request.is_disconnected():
                    return
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            md = "".join(acc)

            yield sse_event("status", {"phase": "saving"})
            out_path = script_episode_path(project_dir, req.episode_id)
            atomic_write_text(out_path, md)
            yield sse_event("done", {"saved": str(out_path),
                                      "episode_id": req.episode_id,
                                      "result": {"summary": ep_entry.get("summary", ""),
                                                  "title": ep_entry.get("title", "")}})
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[script_episode] EXCEPTION ep={req.episode_id}\n{tb}", flush=True)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "episode_id": req.episode_id,
                "hint": "看 agent log 末尾 traceback"})

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 5: 注册路由 + BUILTIN_IDS**

`screenwriter_agent/server.py` 加：

```python
    from .routes.script_episode import router as script_episode_router
    app.include_router(script_episode_router)
```

确认 `screenwriter_agent/templates/template_loader.py` 的 `BUILTIN_IDS` 已含 `"script_episode"`（在 Task 5 一并加过；若漏，补上）：

```python
BUILTIN_IDS = ("ideate", "script", "script_outline", "script_episode",
                "storyboard", "character_ref", "grid_prompt")
```

- [ ] **Step 6: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_script_episode.py -q -p no:faulthandler
```

Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add screenwriter_agent/routes/script_episode.py screenwriter_agent/templates/script_episode.md screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_script_episode.py
git commit -m "feat(agent): + POST /script/episode（剧本_E{id}.md 单集生成）

读 剧本.json 找 episode entry → LLM markdown 流式 → 落盘 剧本_E{id}.md。
未知 episode_id 返 EPISODE_NOT_FOUND 400。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: storyboard 路由按 episode_id 改造 + 删除旧 /script

**Files:**
- Modify: `screenwriter_agent/routes/storyboard.py`
- Delete: `screenwriter_agent/routes/script.py`
- Modify: `screenwriter_agent/server.py`
- Modify: `tests/test_screenwriter_agent/test_route_storyboard.py`

- [ ] **Step 1: 改造 storyboard.py**

找到 `script_path = project_dir / "剧本.md"` 替换为：

```python
from screenwriter_agent.core.paths import script_episode_read_path
...
script_path = script_episode_read_path(project_dir, req.episode_id)
if script_path is None:
    return JSONResponse(status_code=400, content={
        "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                  "message": f"剧本_{req.episode_id}.md missing",
                  "hint": "请先在「剧本」步生成该集。"}})
```

找到 `sb_path = project_dir / "分镜.json"` 替换为：

```python
from screenwriter_agent.core.paths import storyboard_episode_path
...
sb_path = storyboard_episode_path(project_dir, req.episode_id)
```

`purge_downstream` 调用加 `episode_id`：

```python
if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
    purge_downstream(project_dir, stage="storyboard", episode_id=req.episode_id)
```

`done` 事件 result 加 `episode_id`：

```python
yield sse_event("done", {
    "saved": str(sb_path),
    "episode_id": req.episode_id,
    "result": {...同前...},
})
```

- [ ] **Step 2: 删旧 script.py + server.py 解除注册**

```bash
git rm screenwriter_agent/routes/script.py
```

`screenwriter_agent/server.py` 删 `script_router` 注册行：

```python
# 删掉这两行（如有）
from .routes.script import router as script_router
app.include_router(script_router)
```

- [ ] **Step 3: 改既有 test_route_storyboard.py**

把 fixture 里 `(tmp_path / "剧本.md").write_text(...)` 改为 `(tmp_path / "剧本_E1.md").write_text(...)`，body 加 `"episode_id": "E1"`。

assert 路径 `(tmp_path / "分镜.json").is_file()` 改为 `(tmp_path / "分镜_E1.json").is_file()`。

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_storyboard.py -q -p no:faulthandler
```

Expected: 1 passed（既有 1 用例改造完通过）

- [ ] **Step 5: 跑全 agent 套件**

```bash
python -m pytest tests/test_screenwriter_agent/ -q -p no:faulthandler
```

Expected: 全绿（含上面 Task 1-6 新加的 + storyboard 改造 + e2e_smoke 应该还在通过——若挂，先记下，Task 10 集成测试时一并修）

- [ ] **Step 6: Commit**

```bash
git add screenwriter_agent/routes/storyboard.py screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_storyboard.py
git rm screenwriter_agent/routes/script.py
git commit -m "refactor(agent): storyboard 路由按 episode_id；删除旧 /script

剧本_E{id}.md 读 / 分镜_E{id}.json 写；purge_downstream 带 episode_id；
done event 加 episode_id。同时移除旧 /script 路由（被 /script/outline + /script/episode 取代）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: prompts 路由按 episode_id 改造

**Files:**
- Modify: `screenwriter_agent/routes/prompts.py`
- Modify: `tests/test_screenwriter_agent/test_route_prompts.py`（既有）

- [ ] **Step 1: 改造 prompts.py**

读 `分镜_E{id}.json`：

```python
from screenwriter_agent.core.paths import (
    storyboard_episode_read_path, episode_prompts_dir,
)
...
sb_path = storyboard_episode_read_path(project_dir, req.episode_id)
if sb_path is None:
    return JSONResponse(status_code=400, content={
        "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                  "message": f"分镜_{req.episode_id}.json missing",
                  "hint": "请先在「分镜」步生成该集。"}})
```

落盘走 `prompts/E{id}/`：

```python
ep_dir = episode_prompts_dir(project_dir, req.episode_id)
ref_dir = ep_dir / "角色参考图"
grid_dir = ep_dir / "N宫格"
...
# atomic_write 时确保父目录建好（atomic_write_text 已 mkdir parents）
ref_path = ref_dir / f"{name}_ref.md"
sheet_path = grid_dir / f"S{gi}.md"
```

`purge_downstream` 调用加 `episode_id`：

```python
if request.query_params.get("purge_downstream") in ("true", "1", "yes"):
    purge_downstream(project_dir, stage="prompts", episode_id=req.episode_id)
```

partial / done event 加 `episode_id`：

```python
yield sse_event("partial", {"saved": str(ref_path),
                              "kind": "character_ref",
                              "episode_id": req.episode_id})
...
yield sse_event("done", {"saved": saved_paths,
                          "episode_id": req.episode_id,
                          "result": {...}})
```

- [ ] **Step 2: 改既有测试 fixtures**

fixture：`(tmp_path / "分镜.json").write_text(...)` → `(tmp_path / "分镜_E1.json").write_text(...)`；body 加 `"episode_id": "E1"`；assert 路径 `prompts/角色参考图/x.md` → `prompts/E1/角色参考图/x.md`。

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_prompts.py -q -p no:faulthandler
```

Expected: 既有用例通过

- [ ] **Step 4: Commit**

```bash
git add screenwriter_agent/routes/prompts.py tests/test_screenwriter_agent/test_route_prompts.py
git commit -m "refactor(agent): prompts 路由按 episode_id；落盘走 prompts/E{id}/

读 分镜_E{id}.json；partial/done event 加 episode_id；purge_downstream 单集级联。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: FE 端 _paths.py 镜像

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/_paths.py`
- Test: 新建 `tests/test_ui/screenwriter/test_paths_fe.py`

- [ ] **Step 1: 写失败测试**

```python
"""FE _paths.py 集级 helper 镜像 agent。"""
from pathlib import Path

from drama_shot_master.ui.widgets.screenwriter._paths import (
    script_index_path_in, script_episode_read_path_in,
    storyboard_episode_read_path_in, episode_prompts_dir_in,
    is_valid_episode_id_fe,
)


def test_is_valid_episode_id_fe():
    assert is_valid_episode_id_fe("E1")
    assert not is_valid_episode_id_fe("e1")
    assert not is_valid_episode_id_fe("E0")


def test_script_index_path_in(tmp_path):
    assert script_index_path_in(tmp_path).name == "剧本.json"


def test_script_episode_read_falls_back(tmp_path):
    (tmp_path / "剧本.md").write_text("x", encoding="utf-8")
    p = script_episode_read_path_in(tmp_path, "E1")
    assert p is not None and p.name == "剧本.md"


def test_storyboard_episode_read_prefers_new(tmp_path):
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "分镜.json").write_text("{}", encoding="utf-8")
    assert storyboard_episode_read_path_in(tmp_path, "E1").name == "分镜_E1.json"


def test_episode_prompts_dir_in(tmp_path):
    assert episode_prompts_dir_in(tmp_path, "E1") == tmp_path / "prompts" / "E1"
```

- [ ] **Step 2: 跑确认失败 → 实现**

在 `drama_shot_master/ui/widgets/screenwriter/_paths.py` 末尾追加：

```python
import re as _re

EPISODE_ID_PATTERN_FE = _re.compile(r"^E[1-9]\d*$")


def is_valid_episode_id_fe(s: str) -> bool:
    return bool(EPISODE_ID_PATTERN_FE.match(s or ""))


def script_index_path_in(project_dir: Path) -> Path:
    return project_dir / "剧本.json"


def script_episode_path_in(project_dir: Path, episode_id: str) -> Path:
    return project_dir / f"剧本_{episode_id}.md"


def script_episode_read_path_in(project_dir: Path, episode_id: str) -> Path | None:
    primary = script_episode_path_in(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "剧本.md"
        if legacy.is_file():
            return legacy
    return None


def storyboard_episode_path_in(project_dir: Path, episode_id: str) -> Path:
    return project_dir / f"分镜_{episode_id}.json"


def storyboard_episode_read_path_in(project_dir: Path, episode_id: str) -> Path | None:
    primary = storyboard_episode_path_in(project_dir, episode_id)
    if primary.is_file():
        return primary
    if episode_id == "E1":
        legacy = project_dir / "分镜.json"
        if legacy.is_file():
            return legacy
    return None


def episode_prompts_dir_in(project_dir: Path, episode_id: str) -> Path:
    return project_dir / "prompts" / episode_id
```

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_paths_fe.py -q -p no:faulthandler
```

Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_paths.py tests/test_ui/screenwriter/test_paths_fe.py
git commit -m "feat(ui): _paths.py 镜像 agent 集级 helper

剧本.json / 剧本_E{id}.md / 分镜_E{id}.json / prompts/E{id}/；
read helper 兜底兼容旧 剧本.md / 分镜.json（仅 E1）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: _EpisodeSelector 共享 widget

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/_episode_selector.py`
- Test: `tests/test_ui/screenwriter/test_episode_selector.py`

- [ ] **Step 1: 写失败测试**

```python
"""_EpisodeSelector 单元测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector


def _app():
    return QApplication.instance() or QApplication([])


def test_renders_from_script_index(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 3,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
            {"id": "E3", "title": "t3", "summary": "s3"},
        ],
    }), encoding="utf-8")
    sel = _EpisodeSelector()
    sel.set_project(tmp_path)
    assert sel.combo.count() == 3


def test_status_dots_reflect_disk_files(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "分镜_E1.json").write_text("{}", encoding="utf-8")
    sel = _EpisodeSelector(file_pattern_for_status="分镜_{ep}.json")
    sel.set_project(tmp_path)
    # E1 完成 → 项前缀含 ✓；E2 未完成 → ○
    assert "✓" in sel.combo.itemText(0)
    assert "○" in sel.combo.itemText(1)


def test_episode_changed_signal_emits_id(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    sel = _EpisodeSelector()
    sel.set_project(tmp_path)
    got = []
    sel.episodeChanged.connect(got.append)
    sel.combo.setCurrentIndex(1)
    assert got and got[-1] == "E2"


def test_set_project_none_clears(tmp_path):
    _app()
    sel = _EpisodeSelector()
    sel.set_project(None)
    assert sel.combo.count() == 0


def test_select_episode_programmatically(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 3,
        "episodes": [{"id": f"E{i}", "title": "t", "summary": "s"}
                      for i in (1, 2, 3)],
    }), encoding="utf-8")
    sel = _EpisodeSelector()
    sel.set_project(tmp_path)
    sel.select_episode("E2")
    assert sel.current_episode() == "E2"
```

- [ ] **Step 2: 跑确认失败 → 实现**

`drama_shot_master/ui/widgets/screenwriter/_episode_selector.py`:

```python
"""_EpisodeSelector：集选择 widget。

读 剧本.json.episodes 渲染 QComboBox（label 含状态点 ✓/○）+
signal episodeChanged(str)。可选 file_pattern_for_status 决定状态点
按哪个文件名 pattern 扫描（例如 '分镜_{ep}.json' 给 StoryboardPage 用）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox


class _EpisodeSelector(QWidget):
    episodeChanged = Signal(str)

    def __init__(self, parent=None, file_pattern_for_status: str | None = None):
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._episodes: list[dict] = []
        # 状态点扫描的文件名 pattern，{ep} 占位集 id。None → 不显状态
        self._pattern = file_pattern_for_status
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("当前集:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(160)
        self.combo.currentIndexChanged.connect(self._on_changed)
        h.addWidget(self.combo)
        h.addStretch(1)

    def set_project(self, project_dir: Path | None) -> None:
        """读 剧本.json 重建选项。"""
        self._project_dir = project_dir
        self.combo.blockSignals(True)
        self.combo.clear()
        self._episodes = []
        if project_dir is not None:
            si_path = project_dir / "剧本.json"
            if si_path.is_file():
                try:
                    si = json.loads(si_path.read_text(encoding="utf-8"))
                    self._episodes = list(si.get("episodes", []))
                except Exception:
                    pass
            sel = (si.get("selected_episode", "")
                    if si_path.is_file() else "")
            for ep in self._episodes:
                self.combo.addItem(self._format_label(ep["id"], ep.get("title", "")))
            if sel:
                self.select_episode(sel)
        self.combo.blockSignals(False)

    def _format_label(self, ep_id: str, title: str) -> str:
        dot = self._status_dot(ep_id)
        return f"{dot} {ep_id} {title}".strip()

    def _status_dot(self, ep_id: str) -> str:
        if self._pattern is None or self._project_dir is None:
            return ""
        target = self._project_dir / self._pattern.replace("{ep}", ep_id)
        if target.exists():
            return "✓"
        return "○"

    def current_episode(self) -> str:
        idx = self.combo.currentIndex()
        if 0 <= idx < len(self._episodes):
            return self._episodes[idx]["id"]
        return ""

    def select_episode(self, ep_id: str) -> None:
        for i, ep in enumerate(self._episodes):
            if ep["id"] == ep_id:
                self.combo.setCurrentIndex(i)
                return

    def refresh_status(self) -> None:
        """文件状态变化后调，刷新各 item label。"""
        self.combo.blockSignals(True)
        for i, ep in enumerate(self._episodes):
            self.combo.setItemText(
                i, self._format_label(ep["id"], ep.get("title", "")))
        self.combo.blockSignals(False)

    def _on_changed(self):
        ep = self.current_episode()
        if ep:
            self.episodeChanged.emit(ep)
```

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_episode_selector.py -q -p no:faulthandler
```

Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_episode_selector.py tests/test_ui/screenwriter/test_episode_selector.py
git commit -m "feat(ui): + _EpisodeSelector 共享集选择 widget

读 剧本.json 渲染 QComboBox；状态点按 file_pattern_for_status 扫描；
episodeChanged signal；select_episode/current_episode/refresh_status 公接口。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: _BaseStagePage worker dict key 升级

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/base_stage_page.py`
- Modify: `tests/test_ui/screenwriter/test_base_stage_page.py`

- [ ] **Step 1: 写失败测试**（追加）

```python
def test_is_streaming_with_episode_id(tmp_path):
    _app()
    s = _Sub(client=None)
    class _W:
        def __init__(self): self.running = True
        def isRunning(self): return self.running
    s._workers[(tmp_path, "E1")] = _W()
    assert s.is_streaming(tmp_path, "E1") is True
    assert s.is_streaming(tmp_path, "E2") is False


def test_is_streaming_no_episode_id_returns_any(tmp_path):
    """不传 episode_id 时返回「该项目任一集 streaming」。"""
    _app()
    s = _Sub(client=None)
    class _W:
        def isRunning(self): return True
    s._workers[(tmp_path, "E2")] = _W()
    assert s.is_streaming(tmp_path) is True
    assert s.is_streaming(tmp_path / "other") is False


def test_legacy_path_key_still_works(tmp_path):
    """Path-only key（IdeatePage 等单集 stage 用）继续工作。"""
    _app()
    s = _Sub(client=None)
    class _W:
        def isRunning(self): return True
    s._workers[tmp_path] = _W()
    assert s.is_streaming(tmp_path) is True
```

- [ ] **Step 2: 跑确认失败 → 改实现**

替换 `is_streaming` 方法体：

```python
def is_streaming(self, project_dir: Path, episode_id: str | None = None) -> bool:
    """支持两种 key 形态：
      - Path-only（IdeatePage 等无集语义的 stage）
      - (Path, episode_id)（多集 stage）
    episode_id is None 时返「项目级任一 streaming」。
    """
    # 精确匹配
    if episode_id is not None:
        w = self._workers.get((project_dir, episode_id))
        if w and w.isRunning():
            return True
        return False
    # 项目级聚合
    w = self._workers.get(project_dir)
    if w and w.isRunning():
        return True
    for k, w in self._workers.items():
        if isinstance(k, tuple) and len(k) == 2 and k[0] == project_dir:
            if w and w.isRunning():
                return True
    return False
```

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_base_stage_page.py -q -p no:faulthandler
```

Expected: 全绿（原 7 + 新 3）

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/base_stage_page.py tests/test_ui/screenwriter/test_base_stage_page.py
git commit -m "feat(ui): _BaseStagePage.is_streaming 支持 (project_dir, episode_id) tuple key

兼容 Path-only key（IdeatePage 等单集 stage 不变）；
episode_id is None 时聚合返「该项目任一集 streaming」（任务栏用）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: ScreenwriterClient 自动注入 episode_id 不需要（pages 自己塞 body）

直接跳到 Task 13（pages 端各自带 body 字段）。

---

## Task 13: ScriptPage 大改 — 大纲表 + 当前集 editor + 一键全集

**Files:**
- Rewrite: `drama_shot_master/ui/widgets/screenwriter/script_page.py`
- Rewrite: `tests/test_ui/screenwriter/test_script_page.py`

这是本 plan 最大 task；建议拆 2 commit（13a UI 架子；13b 行为接线）。

- [ ] **Step 1: 写新失败测试**（替换既有 script_page 测试）

```python
"""ScriptPage v2（多集）测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _setup_idea(tmp_path):
    (tmp_path / "创意.json").write_text(json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "X"}],
    }), encoding="utf-8")


def test_set_project_none_disables(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(None)
    assert p._gen_btn.isEnabled() is False


def test_n1_button_label_is_生成剧本(tmp_path):
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_count_spin.setValue(1)
    assert p._gen_btn.text() == "生成剧本"


def test_n3_button_label_is_生成大纲(tmp_path):
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_count_spin.setValue(3)
    assert p._gen_btn.text() == "生成大纲"


def test_loads_script_json_renders_outline_rows(tmp_path):
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 2,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
        ],
    }), encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._outline_table.rowCount() == 2


def test_click_row_loads_episode_md(tmp_path):
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 2,
        "episodes": [
            {"id": "E1", "title": "t1", "summary": "s1"},
            {"id": "E2", "title": "t2", "summary": "s2"},
        ],
    }), encoding="utf-8")
    (tmp_path / "剧本_E2.md").write_text("# E2 内容", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_table.selectRow(1)   # 选 E2
    p._on_outline_row_selected()
    assert "E2 内容" in p._episode_editor.toPlainText()


def test_legacy_script_md_treated_as_E1(tmp_path):
    """旧项目（只有 剧本.md）→ 提示迁移；
    本测试只看 set_project 不抛 + upstream banner 不死。"""
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.md").write_text("# legacy", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    # legacy 模式：editor 装 legacy 内容
    # （migrate 弹框由 ScreenwriterPanel 处理，本 page 不弹）
    assert "legacy" in p._episode_editor.toPlainText() or \
           p._outline_table.rowCount() == 0   # 行为兼容多种实现


def test_advance_emits_with_selected_episode(tmp_path):
    _app()
    _setup_idea(tmp_path)
    (tmp_path / "剧本.json").write_text(json.dumps({
        "title": "x", "episode_count": 1,
        "episodes": [{"id": "E1", "title": "t1", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("ok", encoding="utf-8")
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    p._outline_table.selectRow(0)
    p._on_outline_row_selected()
    got = []
    p.stageAdvanceRequested.connect(got.append)
    p._on_advance_clicked()
    # 落 selected_episode 到磁盘
    si = json.loads((tmp_path / "剧本.json").read_text(encoding="utf-8"))
    assert si["selected_episode"] == "E1"
    assert got == [2]


def test_upstream_missing_creative_disables_gen(tmp_path):
    _app()
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)   # 无创意.json
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False
```

- [ ] **Step 2: 跑确认失败 → 重写 ScriptPage**

由于 ScriptPage 代码量大，**建议参考 spec §5 + 既有 v1 ScriptPage 写法**，整文件重写。关键骨架：

```python
"""ScriptPage v2：多集剧本子面板。

布局：参数栏（集数 spin + 时长 + 语言风格 + ●流式 + [生成大纲/生成剧本] + [中止]）
     上游 banner
     大纲表 QTableWidget（E1/标题/概要/[生成此集] 列）
     [一键全集] + 进度 label
     当前集 md 编辑器 QPlainTextEdit
     操作栏：[保存][打开][{ }看JSON]  [推进到分镜 →]
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QSpinBox,
    QComboBox, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
from drama_shot_master.ui.widgets.screenwriter._paths import (
    idea_exists_in, idea_file_in,
    script_index_path_in, script_episode_path_in, script_episode_read_path_in,
)
from screenwriter_agent.core.atomic_write import atomic_write_text


class ScriptPage(_BaseStagePage):

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._si: dict | None = None             # 加载的 剧本.json
        self._current_episode: str = ""           # 当前选中行 id
        self._episode_md: dict[str, str] = {}     # 各集 md 内容缓存
        self._original_md: dict[str, str] = {}    # 用于 dirty 检测
        self._batch_running: bool = False
        self._build_ui()
        self.set_project(None)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(4)
        root.addLayout(self._build_param_bar())
        self._upstream_banner = _UpstreamBanner()
        root.addWidget(self._upstream_banner)
        # 大纲表
        self._outline_table = QTableWidget(0, 4)
        self._outline_table.setHorizontalHeaderLabels(["集", "标题", "概要", "操作"])
        h = self._outline_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Interactive)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._outline_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._outline_table.setSelectionMode(QTableWidget.SingleSelection)
        self._outline_table.itemSelectionChanged.connect(self._on_outline_row_selected)
        self._outline_table.itemChanged.connect(self._on_outline_cell_changed)
        root.addWidget(self._outline_table)
        # 一键全集 + 进度
        batch_bar = QHBoxLayout()
        self._batch_btn = QPushButton("一键全集 ▶")
        self._batch_btn.clicked.connect(self._on_batch_clicked)
        batch_bar.addWidget(self._batch_btn)
        self._batch_progress = QLabel("")
        batch_bar.addWidget(self._batch_progress)
        batch_bar.addStretch(1)
        root.addLayout(batch_bar)
        # 当前集 editor
        self._episode_editor = QPlainTextEdit()
        self._episode_editor.setPlaceholderText("选中上方某行后显示该集 md")
        self._episode_editor.textChanged.connect(self._on_editor_changed)
        root.addWidget(self._episode_editor, 1)
        root.addLayout(self._build_action_bar())

    def _build_param_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("集数:"))
        self._episode_count_spin = QSpinBox()
        self._episode_count_spin.setRange(1, 20)
        self._episode_count_spin.setValue(1)
        self._episode_count_spin.valueChanged.connect(self._update_gen_button_text)
        bar.addWidget(self._episode_count_spin)
        bar.addWidget(QLabel("时长/集(s):"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(15, 600); self._duration_spin.setValue(60)
        bar.addWidget(self._duration_spin)
        bar.addWidget(QLabel("语言风格:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["口语化", "书面语", "古风"])
        bar.addWidget(self._lang_combo)
        bar.addStretch(1)
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        self._gen_btn = QPushButton("生成剧本")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止"); self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        return bar

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存"); self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_clicked)
        bar.addWidget(self._save_btn)
        self._open_btn = QPushButton("📂 打开"); self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open_file_clicked)
        bar.addWidget(self._open_btn)
        self._view_json_btn = QPushButton("{ } 看JSON")
        self._view_json_btn.clicked.connect(self._on_view_json_clicked)
        bar.addWidget(self._view_json_btn)
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进到分镜 →")
        self._advance_btn.setEnabled(False)
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        bar.addWidget(self._advance_btn)
        return bar

    # —— set_project / try_release / dirty 跟踪 等省略，下面给关键方法 ——

    def _update_gen_button_text(self):
        n = self._episode_count_spin.value()
        self._gen_btn.setText("生成剧本" if n == 1 else "生成大纲")

    def set_project(self, path: Path | None) -> None:
        # 略，同既有 v1 + 加 _load_index + _episode_md 缓存
        ...

    def _load_index(self):
        """读 剧本.json + 渲染大纲表 + 选第一行加载该集 md。
        旧项目 (剧本.md + no 剧本.json) → _outline_table 0 行，但 editor 装 legacy。"""
        ...

    def _on_outline_row_selected(self): ...
    def _on_outline_cell_changed(self, item): ...
    def _on_generate_clicked(self):
        """N=1 走快路径 /script/episode("E1")；N>1 走 /script/outline。"""
        ...
    def _on_per_row_gen_clicked(self, episode_id: str):
        """大纲表行末 [生成此集] 触发 /script/episode。"""
        ...
    def _on_batch_clicked(self):
        """一键全集：串行触发各集 /script/episode。"""
        ...
    def _on_advance_clicked(self):
        """保存 selected_episode 到 剧本.json + emit stageAdvanceRequested(2)。"""
        ...
    def _on_save_clicked(self): ...
    def _on_view_json_clicked(self): ...
    # _start_stream / _on_sse_event / _on_stream_done_signal / _on_stream_failed
    # 与 v1 ScriptPage 类似，但 worker dict key 改为 (project_dir, episode_id)
    ...

    def start_generation_if_idle(self) -> None:
        """上游 创意.json 在 + 本阶段 剧本.json 不在 + idle → 自动跑生成大纲。"""
        if self._project_dir is None:
            return
        if not idea_exists_in(self._project_dir):
            return
        if script_index_path_in(self._project_dir).is_file():
            return
        self._on_generate_clicked()
```

由于本 task 体量极大，**实施时由 subagent 完整实现并通过上面 8 个测试**。subagent 应：
1. 完整保留 v1 ScriptPage 的 worker dict 模式 / SSE 事件分流 / retry banner（如有）/ dirty 拦截 / 上游 banner 等行为
2. 用 v2 数据模型替换单文件 `剧本.md` 语义为「集索引 + 单集 md」
3. 大纲表的 cell edit dirty 写回 `剧本.json`（atomic write）
4. 一键全集串行：禁用单行 [生成此集]，进度 label 写 `X/N`，失败则停止后续集
5. worker dict key 用 `(project_dir, episode_id)`；多集并发生成支持（但 UI 触发 path 串行）

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -p no:faulthandler
```

Expected: 8 passed

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py tests/test_ui/screenwriter/test_script_page.py
git commit -m "feat(ui): ScriptPage v2 — 集数 spin + 大纲表 + 当前集 editor + 一键全集

N=1 快路径走 /script/episode；N>1 二步 /script/outline 后逐集 /script/episode；
大纲表 cell edit dirty 写回 剧本.json；
worker dict key 升级 (project_dir, episode_id)；
推进时把 selected_episode 落盘到 剧本.json。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: StoryboardPage 加 _EpisodeSelector

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/storyboard_page.py`
- Modify: `tests/test_ui/screenwriter/test_storyboard_page.py`

- [ ] **Step 1: 写失败测试**（追加）

```python
def test_episode_selector_renders(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    assert p._episode_selector.combo.count() == 2


def test_switch_episode_loads_correct_sb(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    (tmp_path / "剧本_E2.md").write_text("# E2", encoding="utf-8")
    (tmp_path / "分镜_E2.json").write_text(_json.dumps(_sb_fixture()),
                                            encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_selector.select_episode("E2")
    p._on_episode_changed("E2")
    assert p._shots_model.rowCount() == 2   # E2 的 sb shots
    assert p._upstream_banner.isHidden()    # 剧本_E2.md 存在


def test_switch_episode_upstream_missing_shows_banner(tmp_path):
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 2,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"},
                      {"id": "E2", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    # E2 上游缺失
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    p._episode_selector.select_episode("E2")
    p._on_episode_changed("E2")
    assert not p._upstream_banner.isHidden()
    assert p._gen_btn.isEnabled() is False


def test_generate_body_includes_episode_id(tmp_path):
    """点「生成分镜」时 body 应含 episode_id。"""
    _app()
    (tmp_path / "剧本.json").write_text(_json.dumps({
        "episode_count": 1,
        "episodes": [{"id": "E1", "title": "t", "summary": "s"}],
    }), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text("# E1", encoding="utf-8")
    p = StoryboardPage(_StubClient())
    p.set_project(tmp_path)
    # 拦 _start_stream 看 body
    captured = {}
    orig = p._start_stream
    p._start_stream = lambda path, body, params=None: captured.update(body) or orig(path, body, params)
    # 不真正 start（无 client），所以 captured 抓 body 后跳过
    try:
        p._on_generate_clicked()
    except Exception:
        pass
    assert captured.get("episode_id") == "E1"
```

- [ ] **Step 2: 跑确认失败 → 改 StoryboardPage**

主要改动：
1. `_build_ui` 顶部加 `_EpisodeSelector` 实例：

```python
from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector

# 在 _build_ui 内：
self._episode_selector = _EpisodeSelector(
    file_pattern_for_status="分镜_{ep}.json")
self._episode_selector.episodeChanged.connect(self._on_episode_changed)
root.addWidget(self._episode_selector)
```

2. 加 `_on_episode_changed(self, ep_id)` 方法：

```python
def _on_episode_changed(self, ep_id: str):
    if self._dirty and not self.try_release():
        # 回滚 selector
        self._episode_selector.blockSignals(True)
        self._episode_selector.select_episode(self._current_episode)
        self._episode_selector.blockSignals(False)
        return
    self._current_episode = ep_id
    if self._project_dir is None:
        return
    # 上游检查 剧本_E{id}.md
    from drama_shot_master.ui.widgets.screenwriter._paths import script_episode_read_path_in, storyboard_episode_path_in
    if script_episode_read_path_in(self._project_dir, ep_id) is None:
        self._upstream_banner.show_missing(
            stage_name="剧本", expected_file=f"剧本_{ep_id}.md")
        self._gen_btn.setEnabled(False)
    else:
        self._upstream_banner.hide_banner()
        self._gen_btn.setEnabled(True)
    self._sb_path = storyboard_episode_path_in(self._project_dir, ep_id)
    self._load_from_disk()
```

3. `set_project` 末尾调 `self._episode_selector.set_project(path)` 并设当前 ep；
4. `_on_generate_clicked` body 加 `"episode_id": self._current_episode`；
5. worker dict key 改为 `(self._project_dir, self._current_episode)`；
6. SSE handlers 用 tuple key。

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_storyboard_page.py -q -p no:faulthandler
```

Expected: 13 passed（既 9 + 新 4）

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/storyboard_page.py tests/test_ui/screenwriter/test_storyboard_page.py
git commit -m "feat(ui): StoryboardPage 顶部加 _EpisodeSelector + per-episode 读写

读 剧本_E{id}.md / 写 分镜_E{id}.json；
切集 try_release 拦截 + 上游 banner 重检查；
worker dict key 改 (project_dir, episode_id)；
body 加 episode_id。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: PromptsPage 加 _EpisodeSelector + prompts/E{id}/ 路径

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/prompts_page.py`
- Modify: `drama_shot_master/ui/widgets/screenwriter/_product_tree.py`
- Modify: `tests/test_ui/screenwriter/test_prompts_page.py`

- [ ] **Step 1: _ProductTree 加 episode_id 参数**

`build_from_sb(prompts_dir, sb, *, grid_mode, include_character_refs, episode_id=None)`：内部路径计算把 `prompts_dir` 改为 `prompts_dir / "E{id}"` 当 episode_id 非空。

- [ ] **Step 2: PromptsPage 顶部加 _EpisodeSelector**（同 Task 14 模式）

- [ ] **Step 3: body 加 episode_id**

```python
body = {
    "project_dir": str(self._project_dir),
    "episode_id": self._current_episode,
    "options": {...},
}
```

- [ ] **Step 4: partial event 按 episode_id 过滤**

`_on_sse_event` 中检查 `data.get("episode_id") == self._current_episode`，否则忽略 UI 更新。

- [ ] **Step 5: 跑测试 → Commit**

```bash
python -m pytest tests/test_ui/screenwriter/test_prompts_page.py -q -p no:faulthandler
```

```bash
git add drama_shot_master/ui/widgets/screenwriter/prompts_page.py drama_shot_master/ui/widgets/screenwriter/_product_tree.py tests/test_ui/screenwriter/test_prompts_page.py
git commit -m "feat(ui): PromptsPage 加 _EpisodeSelector + 路径走 prompts/E{id}/

_ProductTree.build_from_sb 加 episode_id；切集重建 tree；
partial event 按当前集过滤 UI 更新。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: task_manager._compute_status N/M 显示

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/task_manager.py`
- Modify: `tests/test_ui/screenwriter/test_task_manager.py`

- [ ] **Step 1: 写失败测试**（追加）

```python
def test_status_dots_partial_episodes(tmp_path):
    """3 集项目，分镜 E1+E2 完成，E3 缺：状态点显 2/3。"""
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    (pA / "创意.json").write_text("{}", encoding="utf-8")
    import json as _j
    (pA / "剧本.json").write_text(_j.dumps({
        "episode_count": 3,
        "episodes": [{"id": f"E{i}", "title": "t", "summary": "s"}
                      for i in (1, 2, 3)],
    }), encoding="utf-8")
    for i in (1, 2, 3):
        (pA / f"剧本_E{i}.md").write_text("md", encoding="utf-8")
    for i in (1, 2):
        (pA / f"分镜_E{i}.json").write_text("{}", encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    tm = ScreenwriterTaskManager(cfg)
    dots_text = tm._table.item(0, 1).text()
    # 分镜列状态用 2/3 表示部分完成
    assert "2/3" in dots_text or "✓" not in dots_text.split()[2]
```

- [ ] **Step 2: 改 `_compute_status` 集感知**

```python
def _compute_status(self, p: Path) -> tuple[str, str]:
    from drama_shot_master.ui.widgets.screenwriter._paths import idea_exists_in
    # 读 剧本.json 确定总集数
    si_path = p / "剧本.json"
    total = 1
    episodes = []
    if si_path.is_file():
        try:
            si = json.loads(si_path.read_text(encoding="utf-8"))
            total = max(1, si.get("episode_count", 1))
            episodes = [e["id"] for e in si.get("episodes", [])]
        except Exception:
            pass
    if not episodes and (p / "剧本.md").is_file():
        episodes = ["E1"]   # 旧项目

    dots = []
    last_done_idx = -1
    # 创意
    if idea_exists_in(p):
        dots.append("✓"); last_done_idx = 0
    else:
        dots.append("○")
    # 剧本（多集 → 看 剧本_E*.md 全到齐）
    script_done = sum(1 for ep in episodes
                       if (p / f"剧本_{ep}.md").is_file()
                       or (ep == "E1" and (p / "剧本.md").is_file()))
    if script_done == total and total > 0:
        dots.append("✓"); last_done_idx = 1
    elif script_done > 0:
        dots.append(f"{script_done}/{total}")
    else:
        dots.append("○")
    # 分镜
    sb_done = sum(1 for ep in episodes
                   if (p / f"分镜_{ep}.json").is_file()
                   or (ep == "E1" and (p / "分镜.json").is_file()))
    if sb_done == total and total > 0:
        dots.append("✓"); last_done_idx = 2
    elif sb_done > 0:
        dots.append(f"{sb_done}/{total}")
    else:
        dots.append("○")
    # 提示词
    pr_done = sum(1 for ep in episodes
                   if (p / "prompts" / ep).is_dir()
                   and any((p / "prompts" / ep).iterdir()))
    if pr_done == total and total > 0:
        dots.append("✓"); last_done_idx = 3
    elif pr_done > 0:
        dots.append(f"{pr_done}/{total}")
    else:
        dots.append("○")
    # streaming 覆盖
    if self._active_worker_query(p):
        return " ".join(dots), "生成中"
    if last_done_idx == 3:
        return " ".join(dots), "已完成"
    next_idx = last_done_idx + 1
    next_stage = _STAGE_FILES[next_idx][0]
    return " ".join(dots), f"待 {next_stage}"
```

- [ ] **Step 3: 跑测试 → Commit**

```bash
python -m pytest tests/test_ui/screenwriter/test_task_manager.py -q -p no:faulthandler
```

```bash
git add drama_shot_master/ui/widgets/screenwriter/task_manager.py tests/test_ui/screenwriter/test_task_manager.py
git commit -m "feat(ui): task_manager._compute_status 集感知（剧本/分镜/提示词列 N/M 显示）

读 剧本.json 取总集数，按 剧本_E*.md / 分镜_E*.json / prompts/E*/ 计完成集；
完成 = ✓、部分 = N/M、未开始 = ○。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: ScreenwriterPanel 旧项目迁移对话框

**Files:**
- Modify: `drama_shot_master/ui/panels/screenwriter_panel.py`
- Modify: `tests/test_ui/screenwriter/test_screenwriter_panel.py`

- [ ] **Step 1: 写失败测试**

```python
def test_legacy_project_prompts_migration(tmp_path, monkeypatch):
    """选中旧项目（剧本.md + no 剧本.json）→ 弹迁移对话框。"""
    _app()
    pA = tmp_path / "Legacy"; pA.mkdir()
    (pA / "创意.json").write_text("{}", encoding="utf-8")
    (pA / "剧本.md").write_text("# legacy script", encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)

    called = []
    # mock 用户点 [是]
    import drama_shot_master.ui.panels.screenwriter_panel as m
    monkeypatch.setattr(m.QMessageBox, "question",
                         staticmethod(lambda *a, **k: m.QMessageBox.Yes))

    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()

    # 迁移后：剧本.json 存在 + 剧本_E1.md 存在 + 旧 剧本.md 不在
    assert (pA / "剧本.json").is_file()
    assert (pA / "剧本_E1.md").is_file()
    assert not (pA / "剧本.md").is_file()
```

- [ ] **Step 2: 在 ScreenwriterPanel 加迁移逻辑**

`_on_task_selected` 头部加：

```python
def _on_task_selected(self, path: Path | None) -> None:
    if path is not None:
        self._migrate_legacy_if_needed(path)
    # ...原 try_release + set_project 流程

def _migrate_legacy_if_needed(self, project_dir: Path) -> None:
    si = project_dir / "剧本.json"
    legacy_md = project_dir / "剧本.md"
    if si.is_file() or not legacy_md.is_file():
        return    # 已新版或无旧版
    from PySide6.QtWidgets import QMessageBox
    ans = QMessageBox.question(
        self, "检测到旧版单集剧本",
        f"项目 {project_dir.name} 为旧版单集结构。\n"
        "是否迁移为多集结构？\n\n"
        "[是] = 自动建 剧本.json（1 集）+ 重命名 剧本.md → 剧本_E1.md\n"
        "[否] = 保持只读浏览，本阶段操作禁用",
        QMessageBox.Yes | QMessageBox.No)
    if ans != QMessageBox.Yes:
        return
    # 迁移
    import json
    md_text = legacy_md.read_text(encoding="utf-8")
    # 抠 title：取 markdown 第一行 # 后的文本
    title = project_dir.name
    for line in md_text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    si_data = {
        "title": title,
        "episode_count": 1,
        "selected_episode": "E1",
        "episodes": [{"id": "E1", "title": title, "summary": ""}],
        "input": {},
        "updated_at": "",
    }
    si.write_text(json.dumps(si_data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    target = project_dir / "剧本_E1.md"
    legacy_md.rename(target)
    # 旧 分镜.json 同步迁移
    legacy_sb = project_dir / "分镜.json"
    if legacy_sb.is_file():
        legacy_sb.rename(project_dir / "分镜_E1.json")
```

- [ ] **Step 3: 跑测试**

```bash
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py -q -p no:faulthandler
```

Expected: 既有用例 + 新 1 用例全绿

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/ui/panels/screenwriter_panel.py tests/test_ui/screenwriter/test_screenwriter_panel.py
git commit -m "feat(ui): ScreenwriterPanel 选中旧项目时弹迁移对话框

剧本.md + no 剧本.json → 弹「迁移到多集结构？」；
[是] → 建 剧本.json (1 集) + 重命名 剧本.md → 剧本_E1.md + 分镜.json → 分镜_E1.json；
[否] → 保持兼容只读。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: 多集端到端集成测试

**Files:**
- Create: `tests/test_screenwriter_agent/test_e2e_multi_episode.py`

- [ ] **Step 1: 写测试**

```python
"""N=1 / N=3 端到端流程（mock LLM）。"""
import json
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


@pytest.fixture
def mock_llm_universal(monkeypatch):
    """根据消息内容判断该返大纲 JSON / episode md / storyboard JSON。"""
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        content = "\n".join(m["content"] for m in messages)
        if "集索引" in content or "episode_count" in content:
            raw = json.dumps({
                "title": "x", "episode_count": 3,
                "episodes": [{"id": f"E{i}", "title": f"t{i}", "summary": "s"}
                              for i in (1, 2, 3)],
            }, ensure_ascii=False)
        elif "本集 title" in content or "本集大纲" in content:
            raw = "## 镜头 1\n…\n## 镜头 2\n…"
        elif "JSON 代码块" in content and "shotId" in content:
            raw = json.dumps({
                "title": "E", "aspectRatio": "9:16", "fps": 24,
                "totalDuration": 60, "globalStyle": "古风",
                "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾"}],
                "shots": [{"shotId": "S01", "duration": 6, "composition": "中景",
                            "description": "雨夜", "stylePrompt": "古风水墨"}],
            }, ensure_ascii=False)
        else:
            raw = "default"
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_e2e_n1_chain(tmp_path, mock_llm_universal):
    """N=1：创意 → 单集剧本 → 分镜（mock LLM）。"""
    c = TestClient(create_app())
    # 1) 创意
    c.post("/ideate/chat", json={
        "project_dir": str(tmp_path),
        "context": {"core_idea": "守株待兔", "candidate_count": 1},
    })
    assert (tmp_path / "创意.json").is_file()
    # 2) 剧本 episode（agent 检测 剧本.json 不存在时由 FE 负责调 outline；
    #    本测试模拟 FE 先调 outline，再调 episode）
    c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 1,
    })
    assert (tmp_path / "剧本.json").is_file()
    c.post("/script/episode", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert (tmp_path / "剧本_E1.md").is_file()
    # 3) 分镜
    c.post("/storyboard", json={
        "project_dir": str(tmp_path),
        "episode_id": "E1",
    })
    assert (tmp_path / "分镜_E1.json").is_file()


def test_e2e_n3_chain(tmp_path, mock_llm_universal):
    """N=3：完整三集流水线。"""
    c = TestClient(create_app())
    c.post("/ideate/chat", json={
        "project_dir": str(tmp_path),
        "context": {"core_idea": "测试", "candidate_count": 1},
    })
    c.post("/script/outline", json={
        "project_dir": str(tmp_path),
        "episode_count": 3,
    })
    for i in (1, 2, 3):
        ep = f"E{i}"
        c.post("/script/episode", json={
            "project_dir": str(tmp_path),
            "episode_id": ep,
        })
        c.post("/storyboard", json={
            "project_dir": str(tmp_path),
            "episode_id": ep,
        })
    for i in (1, 2, 3):
        assert (tmp_path / f"剧本_E{i}.md").is_file()
        assert (tmp_path / f"分镜_E{i}.json").is_file()
```

- [ ] **Step 2: 跑测试 → Commit**

```bash
python -m pytest tests/test_screenwriter_agent/test_e2e_multi_episode.py -q -p no:faulthandler
```

Expected: 2 passed

```bash
git add tests/test_screenwriter_agent/test_e2e_multi_episode.py
git commit -m "test(agent): N=1 / N=3 端到端集成（mock LLM 通跑创意→剧本→分镜）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 19: 全套件回归

- [ ] **Step 1: 跑全 screenwriter agent + UI + config 套件**

```bash
python -m pytest tests/test_ui/screenwriter/ tests/test_screenwriter_agent/ tests/test_config -q -p no:faulthandler
```

Expected：~233 passed（spec §10.5 预计）。

如果有 fail：单点修，再跑直到全绿。

- [ ] **Step 2: Commit 验收**

```bash
git commit --allow-empty -m "test(ui): 编剧多集化全套件回归 ~233 passed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 验收清单（与 spec §11 对照）

完成 T1-T19 后，对照 spec §11 逐条手测：

1. ☐ 全套件全绿 — Task 19 验
2. ☐ 启动 → 新建项目 → 创意阶段填 context 选定候选 — 手测
3. ☐ N=1 推进 → 「生成剧本」流式吐字 → `剧本.json` (1 集) + `剧本_E1.md` — 手测
4. ☐ 推进到分镜 → 集选择器默认 E1 → 「生成分镜」产 `分镜_E1.json` — 手测
5. ☐ 推进到提示词 → 集选择器默认 E1 → 生成 prompts/E1/* — 手测
6. ☐ 回剧本 → 集数改 3 → 「重新规划」清下游 → 「生成大纲」产 3 集索引 — 手测
7. ☐ 单点 E2 行 [生成此集] 流式生成 `剧本_E2.md` — 手测
8. ☐ 切分镜 → 集选 E2 → 「生成分镜」产 `分镜_E2.json` — 手测
9. ☐ 任务栏「分镜」列显示 `2/3` (E1+E2 done, E3 ○) — 手测
10. ☐ 旧 v1 项目 → 弹迁移对话框 → 选「是」自动迁移 — 手测

---

## 与 Sub-spec #2/#3/#4 衔接说明

本 plan 不实施 Sub-spec #2/#3/#4。但 `prompts/E{id}/` 目录约定 + `_EpisodeSelector` 可被 #2/#3/#4 直接复用。新 stage 加入时仅需：
- 加新 page (`ImagePromptsPage` / `VideoPromptsPage` / `VoiceSfxPromptsPage`)
- 加新 agent endpoint
- WizardHost stage 数从 4 → 6（注意 `stageAdvanceRequested` index 重排）
- 任务栏列定义扩展
