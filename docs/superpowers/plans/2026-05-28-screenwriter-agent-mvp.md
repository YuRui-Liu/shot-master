# Screenwriter Agent P1 (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地编剧 Agent 的 MVP——独立 FastAPI 子进程（`screenwriter_agent/`），跑通 `创意 → 剧本 → 分镜 → 出图提示词` 四阶段链路；主软件加"编剧"导航项 + 4 步 Wizard 面板（沿用既有面板风格）。

**Architecture:** P1 = "MVP 端到端跑通"。HTTP + SSE 流式；状态全落项目目录（文件系统是唯一真相源）；后端容错修复 + Schema 校验；UI 复用 `TaskWorkspacePage` 主-详 + 现有按钮/列宽/选中样式约定。延后到 P2：warnings 行内高亮、purge_downstream UI、聊天面板美化、storyboard 双视图。延后到 P3：用户级模板编辑、`/project/logs`、user-scope CRUD。

**Tech Stack:** FastAPI + uvicorn[standard] + pydantic≥2 + json5 + httpx；PySide6（既有）；既有 `drama_shot_master.providers.openai_compat`（LLM）、`drama_shot_master.core.template_engine`（模板渲染）复用；非 GPL。

参考 spec：[`docs/superpowers/specs/2026-05-28-screenwriter-agent-design.md`](../specs/2026-05-28-screenwriter-agent-design.md)。

---

## 文件结构总览

```
shot-drama-master/
├── screenwriter_agent/                  【新增】Agent 子进程包
│   ├── __init__.py / __main__.py / config.py / server.py / cli.py
│   ├── core/  (atomic_write / sse / logger / template_loader /
│   │          json_repair / schema_validator / project_scanner / llm_client)
│   ├── routes/ (health / project / ideate / script / storyboard / prompts)
│   ├── models/ (requests / responses / storyboard_schema / idea_schema)
│   └── templates/ (ideate.md / script.md / storyboard.md /
│                   character_ref.md / grid_prompt.md)
├── drama_shot_master/
│   ├── agents/                          【新增】客户端封装
│   │   ├── screenwriter_client.py       (httpx + SSE parsing)
│   │   └── screenwriter_lifecycle.py    (spawn / health-poll / terminate)
│   ├── ui/panels/screenwriter_panel.py  【新增】Wizard 面板
│   ├── config.py                        【改】加 screenwriter_* 字段
│   ├── ui/nav_config.py                 【改】加"编剧"项 + 阶段重排
│   ├── ui/app_shell.py                  【改】注册 screenwriter 页
│   └── main.py                          【改】spawn agent + 退出收尾
├── tests/test_screenwriter_agent/       【新增】单元 + 路由集成 + e2e smoke
└── pyproject.toml                       【改】加 4 个依赖
```

---

## Workstream A: Agent 后端基础设施

### Task 1: pyproject.toml 添加 4 个依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 读 pyproject 现有 dependencies 块**

```bash
grep -nE "dependencies|fastapi|uvicorn|pydantic|json5" pyproject.toml | head
```

- [ ] **Step 2: 加 4 个依赖**

在 `[project] dependencies = [...]` 列表里追加（保持字母序）：

```toml
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    "json5>=0.9",
```

（如果 `httpx` 已在依赖中可不动；spec 7.2 提到但 PySide6 项目可能已 transitively 有。）

- [ ] **Step 3: 跑安装**

```bash
pip install -e . 2>&1 | tail -10
python -c "import fastapi, uvicorn, pydantic, json5; print('all 4 deps importable')"
```

Expected: `all 4 deps importable`。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: 加 fastapi/uvicorn/pydantic≥2/json5 依赖（screenwriter_agent 前置）"
```

Commit message MUST end with: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

---

### Task 2: screenwriter_agent 包骨架 + config

**Files:**
- Create: `screenwriter_agent/__init__.py`
- Create: `screenwriter_agent/__main__.py`
- Create: `screenwriter_agent/config.py`
- Test: `tests/test_screenwriter_agent/__init__.py` (空，标记目录)
- Test: `tests/test_screenwriter_agent/test_config.py`

- [ ] **Step 1: 写失败测试**

`tests/test_screenwriter_agent/test_config.py`:

```python
from screenwriter_agent.config import AgentConfig


def test_default_port_in_valid_range():
    cfg = AgentConfig()
    assert 18430 <= cfg.port < 18500


def test_from_args_overrides_port():
    cfg = AgentConfig.from_args(["--port", "18444"])
    assert cfg.port == 18444


def test_default_models_present():
    cfg = AgentConfig()
    assert set(cfg.default_models.keys()) == {"ideate", "script", "storyboard", "prompts"}
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_config.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 创建包骨架**

`screenwriter_agent/__init__.py`:

```python
"""编剧 Agent：FastAPI 子进程，跑创意→剧本→分镜→出图提示词 四阶段。"""
__version__ = "0.1.0"
```

`screenwriter_agent/__main__.py`:

```python
"""python -m screenwriter_agent 入口。"""
from __future__ import annotations

import sys

from .config import AgentConfig
from .server import run


def main(argv: list[str] | None = None) -> int:
    cfg = AgentConfig.from_args(argv if argv is not None else sys.argv[1:])
    run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`screenwriter_agent/config.py`:

```python
"""运行时配置（命令行参数 + 环境变量 + 默认值）。"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field

# 默认每阶段模型（spec 3.1）
_DEFAULT_MODELS = {
    "ideate":     "doubao-1-5-thinking-pro-250415",
    "script":     "doubao-1-5-thinking-pro-250415",
    "storyboard": "deepseek-v4-pro",
    "prompts":    "deepseek-v4-flash",
}


@dataclass
class AgentConfig:
    """Agent 运行配置。"""
    host: str = "127.0.0.1"
    port: int = 18430
    log_level: str = "info"
    default_models: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_MODELS))

    @classmethod
    def from_args(cls, argv: list[str]) -> "AgentConfig":
        p = argparse.ArgumentParser(prog="screenwriter_agent")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=18430)
        p.add_argument("--log-level", default="info",
                       choices=["debug", "info", "warning", "error"])
        ns = p.parse_args(argv)
        return cls(host=ns.host, port=ns.port, log_level=ns.log_level)
```

- [ ] **Step 4: 创建 tests/test_screenwriter_agent/__init__.py（空文件，标记目录）**

```bash
mkdir -p tests/test_screenwriter_agent
: > tests/test_screenwriter_agent/__init__.py
```

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_config.py -q
```

Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add screenwriter_agent/ tests/test_screenwriter_agent/
git commit -m "feat(screenwriter): 包骨架 + AgentConfig（默认 port 18430, 4 阶段模型预设）"
```

Commit message trailer required.

---

### Task 3: core/atomic_write + core/sse + core/logger 工具层

**Files:**
- Create: `screenwriter_agent/core/__init__.py` (空)
- Create: `screenwriter_agent/core/atomic_write.py`
- Create: `screenwriter_agent/core/sse.py`
- Create: `screenwriter_agent/core/logger.py`
- Test: `tests/test_screenwriter_agent/test_atomic_write.py`
- Test: `tests/test_screenwriter_agent/test_sse_helpers.py`

- [ ] **Step 1: 写失败测试 atomic_write**

`tests/test_screenwriter_agent/test_atomic_write.py`:

```python
from pathlib import Path
import os
import pytest
from screenwriter_agent.core.atomic_write import atomic_write_text


def test_atomic_write_creates_file(tmp_path):
    p = tmp_path / "out.txt"
    atomic_write_text(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"


def test_atomic_write_overwrite_existing(tmp_path):
    p = tmp_path / "out.txt"
    p.write_text("old", encoding="utf-8")
    atomic_write_text(p, "new")
    assert p.read_text(encoding="utf-8") == "new"


def test_atomic_write_does_not_leave_tmp_on_success(tmp_path):
    p = tmp_path / "out.txt"
    atomic_write_text(p, "x")
    assert not (tmp_path / "out.txt.tmp").exists()
```

- [ ] **Step 2: 写失败测试 sse**

`tests/test_screenwriter_agent/test_sse_helpers.py`:

```python
from screenwriter_agent.core.sse import sse_event


def test_sse_event_basic():
    out = sse_event("delta", {"text": "abc"})
    assert "event: delta" in out
    assert "data: " in out
    assert '"text"' in out
    assert "abc" in out
    assert out.endswith("\n\n")


def test_sse_event_unicode_safe():
    out = sse_event("status", {"phase": "生成中"})
    assert "生成中" in out
```

- [ ] **Step 3: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_atomic_write.py tests/test_screenwriter_agent/test_sse_helpers.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 4: 实现 atomic_write**

`screenwriter_agent/core/__init__.py`: 空文件。

`screenwriter_agent/core/atomic_write.py`:

```python
"""原子写入（tmp + os.replace）。POSIX 原子；NTFS 基本原子。"""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """把 content 原子写到 path。中途失败不留半成品。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)
```

- [ ] **Step 5: 实现 sse**

`screenwriter_agent/core/sse.py`:

```python
"""SSE 事件序列化 helpers。spec §3.0 事件协议。"""
from __future__ import annotations

import json
from typing import Any


def sse_event(event: str, data: Any) -> str:
    """构造一个 SSE 块：event: <name>\\ndata: <json>\\n\\n。

    data 序列化用 ensure_ascii=False 让中文直出。
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
```

- [ ] **Step 6: 实现 logger**

`screenwriter_agent/core/logger.py`:

```python
"""按 stage 把单次 LLM 调用记录到 <project_dir>/.agent/logs/<stage>_<ts>.json。
spec §6.5。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .atomic_write import atomic_write_text


def log_stage_call(project_dir: Path, stage: str, payload: dict[str, Any]) -> Path:
    """落盘一次调用日志，返回日志路径。payload 应已含 model / duration_ms 等字段；
    本函数补 ts/stage 字段并写到 .agent/logs/<stage>_<ts>.json。"""
    project_dir = Path(project_dir)
    logs_dir = project_dir / ".agent" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    log_path = logs_dir / f"{stage}_{ts}.json"
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
              "stage": stage, **payload}
    atomic_write_text(log_path, json.dumps(record, ensure_ascii=False, indent=2))
    return log_path
```

- [ ] **Step 7: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_atomic_write.py tests/test_screenwriter_agent/test_sse_helpers.py -q
```

Expected: PASS（5 passed）。

- [ ] **Step 8: Commit**

```bash
git add screenwriter_agent/core/ tests/test_screenwriter_agent/test_atomic_write.py tests/test_screenwriter_agent/test_sse_helpers.py
git commit -m "feat(screenwriter): core 工具层（atomic_write/sse/logger）"
```

Commit message trailer required.

---

### Task 4: core/json_repair（spec §6.2 修复链）

**Files:**
- Create: `screenwriter_agent/core/json_repair.py`
- Test: `tests/test_screenwriter_agent/test_json_repair.py`

- [ ] **Step 1: 写失败测试**

`tests/test_screenwriter_agent/test_json_repair.py`:

```python
import pytest
from screenwriter_agent.core.json_repair import RepairResult, repair_json_text


def test_clean_json_passes_through():
    r = repair_json_text('{"a": 1, "b": "x"}')
    assert r.ok is True
    assert r.obj == {"a": 1, "b": "x"}
    assert r.steps == ["strict"]


def test_strips_markdown_codefence():
    raw = '```json\n{"a": 1}\n```'
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1}
    assert "strip_codefence" in r.steps


def test_strips_text_before_brace():
    raw = '这是一段说明文字\n\n{"a": 1}'
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1}


def test_json5_handles_trailing_comma():
    raw = '{"a": 1, "b": [1, 2, 3,],}'
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1, "b": [1, 2, 3]}
    assert "json5" in r.steps


def test_regex_fixes_chinese_quotes():
    raw = '{"a"：1, "b": "x"}'    # 中文冒号
    r = repair_json_text(raw)
    assert r.ok is True and r.obj == {"a": 1, "b": "x"}
    assert "regex" in r.steps


def test_returns_failed_on_garbage():
    r = repair_json_text("this is not json at all")
    assert r.ok is False
    assert r.obj is None
    assert isinstance(r.raw, str)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_json_repair.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现修复链**

`screenwriter_agent/core/json_repair.py`:

```python
"""JSON 容错修复链（spec §6.2）。专给 LLM 输出回收用。

按顺序尝试：strict json → 剥代码栅 → json5 → regex 兜底。
任一步成功立即返回。全失败时 raw_text 保留以供落盘 raw 文件。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepairResult:
    ok: bool
    obj: Any | None = None
    steps: list[str] = field(default_factory=list)
    raw: str = ""              # 原始 text；ok=False 时供落盘
    error: str = ""


_CODEFENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.IGNORECASE)


def _strip_codefence(text: str) -> str:
    """剥 ```json ... ``` 包裹；找第一个 '{' 到最末 '}'。"""
    t = text.strip()
    t = _CODEFENCE_RE.sub("", t).strip()
    # 截取第一个 { 到最末 }
    i = t.find("{")
    j = t.rfind("}")
    if i >= 0 and j > i:
        return t[i:j + 1]
    return t


def _regex_fixup(text: str) -> str:
    """兜底修复：中文标点 / 尾逗号。"""
    # 中文冒号 / 引号 → ASCII
    text = text.replace("：", ":").replace("，", ",")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    # 去除尾逗号 ,] → ] / ,} → }
    text = re.sub(r",(\s*[\]\}])", r"\1", text)
    return text


def repair_json_text(raw: str) -> RepairResult:
    """执行修复链；返回 RepairResult。"""
    steps: list[str] = []
    err = ""

    # Step 1: strict json
    try:
        obj = json.loads(raw)
        return RepairResult(ok=True, obj=obj, steps=["strict"], raw=raw)
    except Exception as e:
        err = str(e)

    # Step 2: 剥代码栅
    cand = _strip_codefence(raw)
    steps.append("strip_codefence")
    try:
        obj = json.loads(cand)
        return RepairResult(ok=True, obj=obj, steps=steps, raw=raw)
    except Exception as e:
        err = str(e)

    # Step 3: json5
    try:
        import json5
        obj = json5.loads(cand)
        steps.append("json5")
        return RepairResult(ok=True, obj=obj, steps=steps, raw=raw)
    except Exception as e:
        err = str(e)

    # Step 4: regex 兜底 → 再 strict
    fixed = _regex_fixup(cand)
    steps.append("regex")
    try:
        obj = json.loads(fixed)
        return RepairResult(ok=True, obj=obj, steps=steps, raw=raw)
    except Exception as e:
        err = str(e)

    return RepairResult(ok=False, obj=None, steps=steps, raw=raw, error=err)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_json_repair.py -q
```

Expected: PASS（6 passed）。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/core/json_repair.py tests/test_screenwriter_agent/test_json_repair.py
git commit -m "feat(screenwriter): json_repair 修复链（strict→strip_codefence→json5→regex）"
```

Commit trailer required.

---

### Task 5: core/schema_validator + models（pydantic 教学系列 02 schema）

**Files:**
- Create: `screenwriter_agent/models/__init__.py` (空)
- Create: `screenwriter_agent/models/storyboard_schema.py`
- Create: `screenwriter_agent/models/idea_schema.py`
- Create: `screenwriter_agent/core/schema_validator.py`
- Test: `tests/test_screenwriter_agent/test_schema_validator.py`

- [ ] **Step 1: 写失败测试**

`tests/test_screenwriter_agent/test_schema_validator.py`:

```python
import pytest
from screenwriter_agent.core.schema_validator import validate_storyboard, ValidationWarn


def _good():
    return {
        "title": "demo",
        "aspectRatio": "9:16",
        "fps": 24,
        "totalDuration": 60,
        "globalStyle": "古风水墨",
        "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾披肩长发"}],
        "shots": [
            {"shotId": "S01", "description": "雨夜画面", "duration": 6,
             "stylePrompt": "古风水墨，雨夜松林，狐妖立于树下", "composition": "中景"},
        ],
    }


def test_valid_storyboard_passes():
    obj, warns = validate_storyboard(_good())
    assert obj is not None
    assert all(w.severity in ("info", "warning") for w in warns)


def test_missing_title_warning_filled():
    bad = _good(); del bad["title"]
    obj, warns = validate_storyboard(bad, fallback_title="from-script.md")
    assert obj is not None
    assert obj["title"] == "from-script.md"
    assert any("title" in w.path for w in warns)


def test_empty_shots_critical():
    bad = _good(); bad["shots"] = []
    with pytest.raises(Exception):
        validate_storyboard(bad)


def test_shot_missing_shotId_autofill():
    bad = _good(); del bad["shots"][0]["shotId"]
    obj, warns = validate_storyboard(bad)
    assert obj["shots"][0]["shotId"].startswith("S01")
    assert any("shotId" in w.path for w in warns)


def test_stylePrompt_must_be_long():
    bad = _good(); bad["shots"][0]["stylePrompt"] = "短"
    obj, warns = validate_storyboard(bad)
    assert any(w.severity in ("warning", "error") and "stylePrompt" in w.path for w in warns)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_schema_validator.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 models + validator**

`screenwriter_agent/models/__init__.py`: 空。

`screenwriter_agent/models/storyboard_schema.py`:

```python
"""教学系列 02 schema：分镜.json 的目标形状。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str
    appearance: str = ""


class Shot(BaseModel):
    shotId: str
    description: str
    duration: float = 3.0
    composition: str = ""
    stylePrompt: str = ""


class Storyboard(BaseModel):
    title: str
    aspectRatio: str = "9:16"
    fps: int = 24
    totalDuration: float = 0.0
    globalStyle: str = ""
    characters: list[Character] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
```

`screenwriter_agent/models/idea_schema.py`:

```python
"""创意候选 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class IdeaCandidate(BaseModel):
    id: str
    title: str
    angle: str = ""
    summary: str = ""
    highlights: str = ""
    est_duration: int = 0


class IdeaFile(BaseModel):
    input: dict
    messages: list[dict] = Field(default_factory=list)
    candidates: list[IdeaCandidate] = Field(default_factory=list)
    selected_id: str = ""
    updated_at: str = ""
```

`screenwriter_agent/core/schema_validator.py`:

```python
"""教学系列 02 schema 校验 + 字段补全。spec §6.2 Step 5/6。

返回 (validated_dict, [ValidationWarn])。critical 字段缺失抛 ValueError。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from screenwriter_agent.models.storyboard_schema import Storyboard


@dataclass
class ValidationWarn:
    path: str
    issue: str
    severity: str = "warning"          # info / warning / error / critical
    suggested_fix: str = ""
    auto_fix_applied: bool = False


_MIN_STYLE_PROMPT_LEN = 30
_MIN_APPEARANCE_LEN = 10


def validate_storyboard(obj: Any,
                        fallback_title: str = "",
                        default_aspect_ratio: str = "9:16",
                        default_fps: int = 24,
                        default_shot_duration: float = 3.0,
                        default_global_style: str = "") -> tuple[dict, list[ValidationWarn]]:
    """字段补全 + Schema 校验。critical 缺失抛 ValueError。"""
    if not isinstance(obj, dict):
        raise ValueError("storyboard must be a JSON object")

    warns: list[ValidationWarn] = []

    # 顶层字段补全
    if not obj.get("title"):
        obj["title"] = fallback_title or "未命名分镜"
        warns.append(ValidationWarn(
            "title", "缺 title，已用剧本/默认值兜底",
            severity="warning", auto_fix_applied=True))

    obj.setdefault("aspectRatio", default_aspect_ratio)
    obj.setdefault("fps", default_fps)
    obj.setdefault("globalStyle", default_global_style)
    obj.setdefault("characters", [])

    shots = obj.get("shots") or []
    if not shots:
        raise ValueError("storyboard.shots is empty (critical)")

    # 镜头逐条补全
    for i, sh in enumerate(shots):
        if not isinstance(sh, dict):
            raise ValueError(f"shots[{i}] must be an object")
        if not sh.get("shotId"):
            sh["shotId"] = f"S01_{i + 1}"
            warns.append(ValidationWarn(
                f"shots[{i}].shotId", "缺 shotId，已按位置补",
                severity="info", auto_fix_applied=True))
        if not sh.get("description"):
            warns.append(ValidationWarn(
                f"shots[{i}].description", "缺 description",
                severity="error"))
        sh.setdefault("duration", default_shot_duration)
        sh.setdefault("composition", "")
        sp = sh.get("stylePrompt", "")
        if len(sp) < _MIN_STYLE_PROMPT_LEN:
            warns.append(ValidationWarn(
                f"shots[{i}].stylePrompt",
                f"过短（<{_MIN_STYLE_PROMPT_LEN} 字），可能锁不住画风",
                severity="warning"))

    # 角色字段
    for i, ch in enumerate(obj["characters"]):
        if not isinstance(ch, dict) or not ch.get("name"):
            warns.append(ValidationWarn(
                f"characters[{i}].name", "无 name", severity="error"))
        if len(ch.get("appearance", "")) < _MIN_APPEARANCE_LEN:
            warns.append(ValidationWarn(
                f"characters[{i}].appearance", "appearance 过短", severity="warning"))

    # totalDuration 推断
    if not obj.get("totalDuration"):
        obj["totalDuration"] = sum(float(s.get("duration", default_shot_duration))
                                   for s in shots)
        warns.append(ValidationWarn(
            "totalDuration", "缺字段，按 shots 时长求和补",
            severity="info", auto_fix_applied=True))

    # pydantic 二次校验（类型）
    sb = Storyboard.model_validate(obj)
    return sb.model_dump(), warns
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_schema_validator.py -q
```

Expected: PASS（5 passed）。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/models/ screenwriter_agent/core/schema_validator.py tests/test_screenwriter_agent/test_schema_validator.py
git commit -m "feat(screenwriter): schema_validator + pydantic models（storyboard/idea）"
```

Commit trailer required.

---

### Task 6: core/template_loader（仅内置 + 项目级覆盖）

**Files:**
- Create: `screenwriter_agent/core/template_loader.py`
- Test: `tests/test_screenwriter_agent/test_template_loader.py`

> MVP 范围：只查内置 + 项目级；user-scope 延后到 P3。

- [ ] **Step 1: 写失败测试**

`tests/test_screenwriter_agent/test_template_loader.py`:

```python
import pytest
from pathlib import Path
from screenwriter_agent.core.template_loader import load_template, BUILTIN_IDS


def test_builtin_ids_set():
    assert set(BUILTIN_IDS) == {"ideate", "script", "storyboard",
                                "character_ref", "grid_prompt"}


def test_load_builtin_returns_text(tmp_path):
    # builtin 路径在 screenwriter_agent/templates/，不存在则跳过该断言
    for tid in BUILTIN_IDS:
        try:
            text, source = load_template(tid, project_dir=tmp_path)
            assert isinstance(text, str) and len(text) > 0
            assert source in ("project", "builtin")
        except FileNotFoundError:
            pytest.skip(f"builtin {tid} not yet written (Task 16)")


def test_project_override_wins(tmp_path):
    proj_tpl = tmp_path / ".agent" / "templates" / "ideate.md"
    proj_tpl.parent.mkdir(parents=True)
    proj_tpl.write_text("override-content", encoding="utf-8")
    text, source = load_template("ideate", project_dir=tmp_path)
    assert text == "override-content"
    assert source == "project"


def test_unknown_id_raises(tmp_path):
    with pytest.raises(ValueError):
        load_template("nonsense", project_dir=tmp_path)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_template_loader.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 template_loader**

`screenwriter_agent/core/template_loader.py`:

```python
"""模板加载（项目级覆盖优先 → 内置兜底）。

P1 不实现 user-scope；P3 加。
"""
from __future__ import annotations

from pathlib import Path

# 5 套内置模板的 id（spec §5.1）
BUILTIN_IDS = ("ideate", "script", "storyboard", "character_ref", "grid_prompt")

_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "templates"


def load_template(tid: str, project_dir: Path) -> tuple[str, str]:
    """返回 (text, source)，source ∈ {'project', 'builtin'}。
    未知 id 抛 ValueError；内置缺失抛 FileNotFoundError。"""
    if tid not in BUILTIN_IDS:
        raise ValueError(f"未知模板 id: {tid}")
    # 1) 项目级覆盖
    proj = Path(project_dir) / ".agent" / "templates" / f"{tid}.md"
    if proj.is_file():
        return proj.read_text(encoding="utf-8"), "project"
    # 2) 内置
    builtin = _BUILTIN_DIR / f"{tid}.md"
    if not builtin.is_file():
        raise FileNotFoundError(f"内置模板缺失: {builtin}")
    return builtin.read_text(encoding="utf-8"), "builtin"
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_template_loader.py -q
```

Expected: PASS (4 — builtin tests skip until Task 16 writes templates)。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/core/template_loader.py tests/test_screenwriter_agent/test_template_loader.py
git commit -m "feat(screenwriter): template_loader（项目级覆盖优先 → 内置兜底，MVP 无 user-scope）"
```

Commit trailer required.

---

### Task 7: core/project_scanner（GET /project 的扫目录逻辑）

**Files:**
- Create: `screenwriter_agent/core/project_scanner.py`
- Test: `tests/test_screenwriter_agent/test_project_scanner.py`

- [ ] **Step 1: 写失败测试**

`tests/test_screenwriter_agent/test_project_scanner.py`:

```python
import json
from pathlib import Path
import pytest

from screenwriter_agent.core.project_scanner import scan_project, ProjectState


def test_empty_dir(tmp_path):
    st = scan_project(tmp_path)
    assert st.status == "empty"
    assert not st.stages["ideate"]["done"]
    assert st.recommended_next == "ideate"


def test_idea_without_selected(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [
            {"id": "c1", "title": "t1"}], "selected_id": ""}),
        encoding="utf-8")
    st = scan_project(tmp_path)
    assert st.status == "ideating"
    assert st.stages["ideate"]["done"] is False


def test_idea_selected_no_script(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [
            {"id": "c1", "title": "t1"}], "selected_id": "c1"}),
        encoding="utf-8")
    st = scan_project(tmp_path)
    assert st.status == "script_pending"
    assert st.stages["ideate"]["done"] is True
    assert st.recommended_next == "script"


def test_full_chain(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t"}],
        "selected_id": "c1"}), encoding="utf-8")
    (tmp_path / "剧本.md").write_text("# 剧本信息\n标题: x\n", encoding="utf-8")
    (tmp_path / "分镜.json").write_text(json.dumps({"title": "x", "shots": [{}]}), encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "S1.md").write_text("p", encoding="utf-8")
    st = scan_project(tmp_path)
    assert st.status == "done"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_project_scanner.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 project_scanner**

`screenwriter_agent/core/project_scanner.py`:

```python
"""扫描项目目录，按 4 阶段产物推断状态（spec §3.2）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectState:
    project_dir: str
    name: str
    status: str = "empty"
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    recommended_next: str = "ideate"
    config_overrides: dict[str, Any] = field(default_factory=dict)


_STAGE_ORDER = ("ideate", "script", "storyboard", "prompts")


def scan_project(project_dir: Path) -> ProjectState:
    """读项目目录，按 4 阶段产物推断状态。不验证文件内容合法性。"""
    project_dir = Path(project_dir).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(str(project_dir))

    stages: dict[str, dict[str, Any]] = {}

    # ideate
    idea_path = project_dir / "idea.json"
    if idea_path.is_file():
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
            selected = bool(idea.get("selected_id"))
            cand_count = len(idea.get("candidates", []))
            summary = (f"候选 {cand_count} 个，已选 {idea['selected_id']}"
                       if selected else f"候选 {cand_count} 个，未选定")
        except Exception:
            selected = False
            summary = "idea.json 解析失败"
        stages["ideate"] = {"done": selected, "file": "idea.json",
                            "summary": summary if selected else None}
    else:
        stages["ideate"] = {"done": False, "file": "idea.json", "summary": None}

    # script
    script_path = project_dir / "剧本.md"
    stages["script"] = {"done": script_path.is_file(), "file": "剧本.md",
                        "summary": _summarize_script(script_path)
                        if script_path.is_file() else None}

    # storyboard
    sb_path = project_dir / "分镜.json"
    stages["storyboard"] = {"done": sb_path.is_file(), "file": "分镜.json",
                            "summary": _summarize_storyboard(sb_path)
                            if sb_path.is_file() else None}

    # prompts
    prompts_dir = project_dir / "prompts"
    has_prompts = prompts_dir.is_dir() and any(prompts_dir.iterdir())
    stages["prompts"] = {"done": has_prompts, "subdir": "prompts/",
                         "summary": f"{len(list(prompts_dir.iterdir()))} 个文件"
                         if has_prompts else None}

    # 推导项目级 status + recommended_next
    status, nxt = _derive_status(stages)

    return ProjectState(
        project_dir=str(project_dir),
        name=project_dir.name,
        status=status,
        stages=stages,
        recommended_next=nxt,
    )


def _derive_status(stages: dict) -> tuple[str, str]:
    """spec §3.2 表。"""
    done = {k: bool(v["done"]) for k, v in stages.items()}
    if not any(done.values()):
        return "empty", "ideate"
    if not done["ideate"]:
        return "ideating", "ideate"
    if not done["script"]:
        return "script_pending", "script"
    if not done["storyboard"]:
        return "storyboard_pending", "storyboard"
    if not done["prompts"]:
        return "prompts_pending", "prompts"
    return "done", "prompts"


def _summarize_script(p: Path) -> str | None:
    try:
        lines = p.read_text(encoding="utf-8").splitlines()[:30]
        for ln in lines:
            ln = ln.strip()
            if ln.startswith("标题") and "：" in ln:
                return ln.split("：", 1)[1].strip()
            if ln.startswith("标题:"):
                return ln.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def _summarize_storyboard(p: Path) -> str | None:
    try:
        sb = json.loads(p.read_text(encoding="utf-8"))
        n = len(sb.get("shots", []))
        return f"{n} 个镜头 · {sb.get('totalDuration', '?')}s"
    except Exception:
        return None
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_project_scanner.py -q
```

Expected: PASS (4 passed)。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/core/project_scanner.py tests/test_screenwriter_agent/test_project_scanner.py
git commit -m "feat(screenwriter): project_scanner（4 阶段状态推断 + summary 提取）"
```

Commit trailer required.

---

### Task 8: core/llm_client（流式 wrapper）

**Files:**
- Create: `screenwriter_agent/core/llm_client.py`
- Test: `tests/test_screenwriter_agent/test_llm_client.py`

> 这个 wrapper 主要做"喂 messages → SSE delta 流"。底层 LLM API 调用复用 `drama_shot_master.providers.openai_compat`；但 openai_compat 现有接口可能是阻塞的（基于 VisionProvider 抽象）——如果不支持原生 stream，我们用 OpenAI Python SDK 直接做 `stream=True`。`OpenAI()` 客户端可以由 cfg 配置 base_url/api_key。MVP 直接用 OpenAI SDK；为 P2 留 hook 切回 openai_compat。

- [ ] **Step 1: 写失败测试（mock OpenAI 客户端）**

`tests/test_screenwriter_agent/test_llm_client.py`:

```python
import pytest
from screenwriter_agent.core.llm_client import LLMClient, StreamChunk


def _fake_stream(text="hello"):
    """模拟 OpenAI SDK 的 chunk iterator：每个 chunk 含 delta.content。"""
    class _D:
        def __init__(self, content): self.content = content
    class _C:
        def __init__(self, content): self.delta = _D(content)
    class _Ch:
        def __init__(self, content): self.choices = [_C(content)]
    for ch in text:
        yield _Ch(ch)
    yield _Ch("")    # 收尾空 chunk


def test_iter_text_chunks_yields_deltas(monkeypatch):
    client = LLMClient(api_key="dummy", base_url="https://example", model="m")
    fake_stream = _fake_stream("abc")
    monkeypatch.setattr(client, "_raw_stream",
                        lambda **kw: fake_stream)
    chunks = list(client.stream_chat([{"role": "user", "content": "x"}]))
    deltas = [c.text for c in chunks if c.kind == "delta"]
    assert "".join(deltas) == "abc"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_llm_client.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 LLMClient**

`screenwriter_agent/core/llm_client.py`:

```python
"""LLM 调用 wrapper（OpenAI 兼容协议）。流式：yield StreamChunk。

api_key/base_url/model 都由调用方按阶段从 cfg 传入；本类是无状态的。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass
class StreamChunk:
    kind: str       # "delta" | "done"
    text: str = ""
    raw: str = ""   # 累计全文（done 时填）


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str,
                 reasoning_effort: str = "high",
                 response_format: dict | None = None,
                 timeout: float = 300.0):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.response_format = response_format
        self.timeout = timeout

    def _raw_stream(self, *, messages: list[dict]) -> Iterator:
        """调底层 OpenAI SDK；测试时被 monkeypatch。"""
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                        timeout=self.timeout)
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if self.response_format:
            kwargs["response_format"] = self.response_format
        return client.chat.completions.create(**kwargs)

    def stream_chat(self, messages: list[dict]) -> Iterator[StreamChunk]:
        """流式调 LLM；逐 chunk yield delta；最后 yield 一个 done 含完整 raw。"""
        acc: list[str] = []
        for ch in self._raw_stream(messages=messages):
            try:
                delta = ch.choices[0].delta
                txt = getattr(delta, "content", "") or ""
            except Exception:
                txt = ""
            if txt:
                acc.append(txt)
                yield StreamChunk(kind="delta", text=txt)
        yield StreamChunk(kind="done", raw="".join(acc))
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_llm_client.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/core/llm_client.py tests/test_screenwriter_agent/test_llm_client.py
git commit -m "feat(screenwriter): LLMClient 流式 wrapper（OpenAI 兼容 + stream=True）"
```

Commit trailer required.

---

### Task 9: server.py + uvicorn 启动入口

**Files:**
- Create: `screenwriter_agent/server.py`
- Test: `tests/test_screenwriter_agent/test_server_startup.py`

- [ ] **Step 1: 写测试**

`tests/test_screenwriter_agent/test_server_startup.py`:

```python
def test_create_app_returns_fastapi():
    from screenwriter_agent.server import create_app
    app = create_app()
    # 必须含 /health 路由（Task 10 加；此时通过空 app + 占位 stub 路由也行）
    paths = {r.path for r in app.routes}
    assert "/health" in paths
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_server_startup.py -q
```

Expected: ModuleNotFoundError 或 AssertionError（无 /health）。

- [ ] **Step 3: 实现 server**

`screenwriter_agent/server.py`:

```python
"""FastAPI app + uvicorn 启动入口。"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import AgentConfig


def create_app(cfg: AgentConfig | None = None) -> FastAPI:
    """构造 FastAPI app；路由由各 router 模块挂载。
    cfg 在路由 handler 内通过 dependency injection 取（暂用 module-level 闭包）。"""
    cfg = cfg or AgentConfig()
    app = FastAPI(title="screenwriter_agent", version="0.1.0")
    app.state.cfg = cfg

    from .routes.health import router as health_router
    app.include_router(health_router)

    return app


def run(cfg: AgentConfig) -> None:
    """启动 uvicorn。端口被占用时往后试到 18439。"""
    import uvicorn
    logging.basicConfig(level=cfg.log_level.upper())
    for offset in range(10):
        port = cfg.port + offset
        try:
            cfg.port = port
            uvicorn.run(create_app(cfg), host=cfg.host, port=port,
                        log_level=cfg.log_level)
            return
        except OSError as e:
            if "address already in use" not in str(e).lower():
                raise
    raise RuntimeError(f"端口 {cfg.port}+1..+9 都被占用")
```

- [ ] **Step 4: 跑测试（依赖 Task 10 的 /health 实际挂载；当前可加一个最小 stub）**

为让 Task 9 独立通过，先在 `screenwriter_agent/routes/__init__.py`（空文件）+ `screenwriter_agent/routes/health.py` 占位：

`screenwriter_agent/routes/__init__.py`: 空。

`screenwriter_agent/routes/health.py`（占位，Task 10 替换）:

```python
"""GET /health（占位；Task 10 实际实现）。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
```

跑：

```bash
python -m pytest tests/test_screenwriter_agent/test_server_startup.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/server.py screenwriter_agent/routes/__init__.py screenwriter_agent/routes/health.py tests/test_screenwriter_agent/test_server_startup.py
git commit -m "feat(screenwriter): server.py FastAPI app + uvicorn run（端口冲突自动 +1..+9）"
```

Commit trailer required.

---

## Workstream B: 路由

### Task 10: /health 路由实测

**Files:**
- Modify: `screenwriter_agent/routes/health.py`
- Test: `tests/test_screenwriter_agent/test_route_health.py`

- [ ] **Step 1: 写测试**

`tests/test_screenwriter_agent/test_route_health.py`:

```python
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_health_returns_status_ok():
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["version"]
    assert set(j["default_models"].keys()) == {"ideate", "script", "storyboard", "prompts"}
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_health.py -q
```

Expected: FAIL（缺 version/default_models）。

- [ ] **Step 3: 完善 health.py**

`screenwriter_agent/routes/health.py`（覆盖占位）:

```python
"""GET /health。返回 status + version + default_models。"""
from fastapi import APIRouter, Request

from screenwriter_agent import __version__

router = APIRouter()


@router.get("/health")
def health(request: Request):
    cfg = request.app.state.cfg
    return {
        "status": "ok",
        "version": __version__,
        "default_models": cfg.default_models,
    }
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_health.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/routes/health.py tests/test_screenwriter_agent/test_route_health.py
git commit -m "feat(screenwriter): /health 返回 version + default_models"
```

Commit trailer required.

---

### Task 11: GET /project 路由

**Files:**
- Create: `screenwriter_agent/routes/project.py`
- Modify: `screenwriter_agent/server.py` (注册 router)
- Test: `tests/test_screenwriter_agent/test_route_project.py`

- [ ] **Step 1: 写测试**

`tests/test_screenwriter_agent/test_route_project.py`:

```python
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_project_dir_not_found_400(tmp_path):
    c = TestClient(create_app())
    r = c.get("/project", params={"dir": str(tmp_path / "ghost")})
    assert r.status_code == 400
    j = r.json()
    assert j["error"]["code"] == "PROJECT_DIR_NOT_FOUND"


def test_project_empty_dir_returns_state(tmp_path):
    c = TestClient(create_app())
    r = c.get("/project", params={"dir": str(tmp_path)})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "empty"
    assert j["stages"]["ideate"]["done"] is False
    assert j["recommended_next"] == "ideate"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_project.py -q
```

Expected: 404 from FastAPI（路由不存在）。

- [ ] **Step 3: 实现 routes/project.py**

```python
"""GET /project — 扫描项目目录返回阶段状态。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from screenwriter_agent.core.project_scanner import scan_project

router = APIRouter()


@router.get("/project")
def get_project(dir: str):
    p = Path(dir)
    if not p.is_dir():
        return JSONResponse(
            status_code=400,
            content={"error": {
                "code": "PROJECT_DIR_NOT_FOUND",
                "message": f"path not a directory: {dir}",
                "hint": "选的路径打不开，确认一下是不是被改名或挪走了？",
                "details": {}}})
    st = scan_project(p)
    return {
        "project_dir": st.project_dir,
        "name": st.name,
        "status": st.status,
        "stages": st.stages,
        "recommended_next": st.recommended_next,
        "config_overrides": st.config_overrides,
    }
```

修改 `screenwriter_agent/server.py`，在 `create_app` 注册 project router：

```python
    from .routes.project import router as project_router
    app.include_router(project_router)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_project.py -q
```

Expected: PASS (2 passed)。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/routes/project.py screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_project.py
git commit -m "feat(screenwriter): GET /project 扫描状态接口（spec §3.2）"
```

Commit trailer required.

---

### Task 12: POST /ideate/chat (SSE) + /ideate/select

**Files:**
- Create: `screenwriter_agent/routes/ideate.py`
- Create: `screenwriter_agent/models/requests.py`（如不存在）
- Modify: `screenwriter_agent/server.py`
- Test: `tests/test_screenwriter_agent/test_route_ideate.py`

- [ ] **Step 1: 写测试**

`tests/test_screenwriter_agent/test_route_ideate.py`:

```python
import json
from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


class _StubChunk:
    def __init__(self, content):
        self.choices = [type("C", (), {"delta": type("D", (), {"content": content})()})]


def _fake_llm_stream(text: str):
    for ch in text:
        yield _StubChunk(ch)
    yield _StubChunk("")


def test_ideate_select_writes_selected_id(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t1"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select", json={"project_dir": str(tmp_path),
                                       "selected_id": "c1"})
    assert r.status_code == 200
    on_disk = json.loads((tmp_path / "idea.json").read_text(encoding="utf-8"))
    assert on_disk["selected_id"] == "c1"


def test_ideate_select_unknown_id_400(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/ideate/select", json={"project_dir": str(tmp_path),
                                       "selected_id": "nope"})
    assert r.status_code == 400
```

> SSE chat 流的完整 e2e 留给 Task 23 端到端 smoke；本任务只测 select 子接口。

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_ideate.py -q
```

Expected: FAIL（路由 404）。

- [ ] **Step 3: 实现 routes/ideate.py + models/requests.py**

`screenwriter_agent/models/requests.py`（新建或追加）:

```python
"""路由请求体 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class IdeateContext(BaseModel):
    core_idea: str = ""
    genre_tags: list[str] = Field(default_factory=list)
    format: str = "短剧"
    tone_tags: list[str] = Field(default_factory=list)
    visual_style: str = ""
    candidate_count: int = 3
    duration_sec: int = 60
    extra_constraints: str = ""


class ChatMessage(BaseModel):
    role: str           # "user" | "assistant" | "system"
    content: str


class IdeateChatReq(BaseModel):
    project_dir: str
    context: IdeateContext
    messages: list[ChatMessage] = Field(default_factory=list)
    model: str | None = None
    reasoning_effort: str = "high"
    auto_save_idea_json: bool = True


class IdeateSelectReq(BaseModel):
    project_dir: str
    selected_id: str
```

`screenwriter_agent/routes/ideate.py`:

```python
"""POST /ideate/chat (SSE) + /ideate/select。spec §3.3/§3.4。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import IdeateChatReq, IdeateSelectReq

router = APIRouter()


@router.post("/ideate/select")
def ideate_select(req: IdeateSelectReq):
    p = Path(req.project_dir)
    idea_path = p / "idea.json"
    if not idea_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "idea.json not found",
                      "hint": "还没有候选，请先发起创意对话生成候选。"}})
    try:
        idea = json.loads(idea_path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": f"idea.json parse: {e}", "hint": ""}})
    ids = {c.get("id") for c in idea.get("candidates", [])}
    if req.selected_id not in ids:
        return JSONResponse(status_code=400, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": f"selected_id {req.selected_id} not in candidates",
                      "hint": "候选 id 不存在；可能候选已被替换。"}})
    idea["selected_id"] = req.selected_id
    idea["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    atomic_write_text(idea_path, json.dumps(idea, ensure_ascii=False, indent=2))
    selected = next(c for c in idea["candidates"] if c["id"] == req.selected_id)
    return {"saved": str(idea_path), "selected": selected}


@router.post("/ideate/chat")
async def ideate_chat(req: IdeateChatReq, request: Request):
    """SSE：渲染模板 → 喂 LLM → 流式吐出 → done 时落盘 idea.json。"""
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"path not found: {req.project_dir}",
                      "hint": "项目目录打不开。"}})

    cfg = request.app.state.cfg
    model = req.model or cfg.default_models.get("ideate")

    async def gen():
        from screenwriter_agent.core.llm_client import LLMClient
        # MVP：api_key/base_url 留给客户端注入；这里用环境兜底
        import os
        api_key = os.environ.get("SCREENWRITER_LLM_API_KEY", "")
        base_url = os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                  "https://api.deepseek.com")
        try:
            yield sse_event("status", {"phase": "thinking"})
            # 渲染模板
            tpl_text, _src = load_template("ideate", project_dir=project_dir)
            ctx = req.context.model_dump()
            ctx_block = json.dumps(ctx, ensure_ascii=False, indent=2)
            system_msg = {"role": "system", "content":
                          tpl_text + "\n\n## 当前 context\n```json\n"
                          + ctx_block + "\n```"}
            messages = [system_msg] + [m.model_dump() for m in req.messages]
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for chunk in client.stream_chat(messages):
                if chunk.kind == "delta":
                    acc.append(chunk.text)
                    yield sse_event("delta", {"text": chunk.text})
            raw = "".join(acc)

            # 解析候选（简化版：让 LLM 输出标记格式 "候选 1｜标题：..."；
            # 实际解析延后到 P2 精修，MVP 把原文挂进 raw_text 字段）
            yield sse_event("status", {"phase": "saving"})
            if req.auto_save_idea_json:
                idea = {
                    "input": req.context.model_dump(),
                    "messages": [m.model_dump() for m in req.messages]
                                + [{"role": "assistant", "content": raw}],
                    "candidates": _parse_candidates_loose(raw),
                    "selected_id": "",
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                idea_path = project_dir / "idea.json"
                atomic_write_text(
                    idea_path, json.dumps(idea, ensure_ascii=False, indent=2))
                yield sse_event("done", {"saved": str(idea_path),
                                          "result": {"candidates": idea["candidates"],
                                                     "raw_text": raw,
                                                     "warnings": []}})
            else:
                yield sse_event("done", {"saved": None,
                                          "result": {"raw_text": raw, "warnings": []}})
        except Exception as e:
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "hint": "出了点意外，再试一次或换模型。"})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _parse_candidates_loose(raw: str) -> list[dict]:
    """MVP 简化解析：按 '候选 N' / 'c1 / c2 / c3' 等启发式切段。
    不严格——精修留 P2。"""
    import re
    out = []
    # 按 "候选 1" 切
    parts = re.split(r"(?:^|\n)\s*[#＃]*\s*候选\s*([0-9]+)", raw)
    if len(parts) >= 3:
        for i in range(1, len(parts), 2):
            idx = parts[i].strip()
            body = parts[i + 1].strip()
            out.append({"id": f"c{idx}", "title": _first_line(body, "标题"),
                        "angle": _extract(body, "切入角度"),
                        "summary": _extract(body, "摘要|核心"),
                        "highlights": _extract(body, "亮点|看点"),
                        "est_duration": 60})
    return out


def _first_line(text: str, key: str = "") -> str:
    for ln in text.splitlines():
        if key and key in ln:
            return ln.split("：" if "：" in ln else ":", 1)[-1].strip()
    return text.splitlines()[0].strip() if text else ""


def _extract(text: str, key_re: str) -> str:
    import re
    m = re.search(rf"(?:{key_re})\s*[：:]\s*(.+?)(?=\n[#＃]|\n[一二三四]、|\Z)",
                  text, re.DOTALL)
    return m.group(1).strip() if m else ""
```

注册 router 到 `server.py`:

```python
    from .routes.ideate import router as ideate_router
    app.include_router(ideate_router)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_ideate.py -q
```

Expected: PASS (2 passed)。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/routes/ideate.py screenwriter_agent/models/requests.py screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_ideate.py
git commit -m "feat(screenwriter): /ideate/chat (SSE) + /ideate/select；MVP 候选解析启发式"
```

Commit trailer required.

---

### Task 13: POST /script (SSE)

**Files:**
- Create: `screenwriter_agent/routes/script.py`
- Modify: `screenwriter_agent/server.py`
- Modify: `screenwriter_agent/models/requests.py` (加 ScriptReq)
- Test: `tests/test_screenwriter_agent/test_route_script.py`

- [ ] **Step 1: 写测试**

`tests/test_screenwriter_agent/test_route_script.py`:

```python
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_script_missing_idea_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/script", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in ("UPSTREAM_PRODUCT_MISSING", "PROJECT_DIR_NOT_FOUND")


def test_script_unselected_idea_400(tmp_path):
    (tmp_path / "idea.json").write_text(json.dumps({
        "input": {}, "messages": [], "candidates": [{"id": "c1", "title": "t"}],
        "selected_id": ""}), encoding="utf-8")
    c = TestClient(create_app())
    r = c.post("/script", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 400
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_script.py -q
```

Expected: 404 路由不存在。

- [ ] **Step 3: 加 ScriptReq schema 到 models/requests.py**

```python
class ScriptOptions(BaseModel):
    length_preset: str = "完整版"
    language_style: str = "口语化"
    fps: int = 24
    duration_sec: int = 60


class ScriptReq(BaseModel):
    project_dir: str
    options: ScriptOptions = Field(default_factory=ScriptOptions)
    model: str | None = None
    reasoning_effort: str = "high"
```

- [ ] **Step 4: 实现 routes/script.py**

```python
"""POST /script — SSE：读 idea.json.selected → LLM → 落盘 剧本.md。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import ScriptReq

router = APIRouter()


@router.post("/script")
async def script(req: ScriptReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"path not found: {req.project_dir}",
                      "hint": "项目目录打不开。"}})
    idea_path = project_dir / "idea.json"
    if not idea_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "idea.json missing",
                      "hint": "请先在「创意」步生成候选并选定一个。"}})
    try:
        idea = json.loads(idea_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "idea.json parse failed",
                      "hint": ""}})
    if not idea.get("selected_id"):
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "no selected candidate",
                      "hint": "请先回到「创意」步骤选定一个候选。"}})

    sel = next((c for c in idea["candidates"]
                if c["id"] == idea["selected_id"]), None)
    if not sel:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "selected_id not in candidates",
                      "hint": ""}})

    cfg = request.app.state.cfg
    model = req.model or cfg.default_models.get("script")

    async def gen():
        try:
            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("script", project_dir=project_dir)
            opts = req.options.model_dump()
            prompt = (tpl_text
                      + "\n\n## 选定候选\n```json\n"
                      + json.dumps(sel, ensure_ascii=False, indent=2)
                      + "\n```\n\n## 原始输入\n```json\n"
                      + json.dumps(idea.get("input", {}), ensure_ascii=False, indent=2)
                      + f"\n```\n\n## 参数\nfps={opts['fps']}, "
                      + f"duration_sec={opts['duration_sec']}, "
                      + f"length_preset={opts['length_preset']}, "
                      + f"language_style={opts['language_style']}\n")
            messages = [{"role": "user", "content": prompt}]

            api_key = os.environ.get("SCREENWRITER_LLM_API_KEY", "")
            base_url = os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                      "https://api.deepseek.com")
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            md = "".join(acc)

            yield sse_event("status", {"phase": "saving"})
            script_path = project_dir / "剧本.md"
            atomic_write_text(script_path, md)
            # 简单 summary：扫"# 剧本信息"块
            summary = {"shot_count": md.count("## 镜头"),
                       "total_duration": opts["duration_sec"],
                       "title": sel.get("title", "")}
            yield sse_event("done", {"saved": str(script_path),
                                      "result": {"summary": summary, "warnings": []}})
        except Exception as e:
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": str(e), "hint": ""})

    return StreamingResponse(gen(), media_type="text/event-stream")
```

注册到 `server.py`:

```python
    from .routes.script import router as script_router
    app.include_router(script_router)
```

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_script.py -q
```

Expected: PASS (2 passed)。

- [ ] **Step 6: Commit**

```bash
git add screenwriter_agent/routes/script.py screenwriter_agent/models/requests.py screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_script.py
git commit -m "feat(screenwriter): /script (SSE) — idea.selected → 剧本.md"
```

Commit trailer required.

---

### Task 14: POST /storyboard (SSE + repair + validate)

**Files:**
- Create: `screenwriter_agent/routes/storyboard.py`
- Modify: `screenwriter_agent/server.py`
- Modify: `screenwriter_agent/models/requests.py` (StoryboardReq)
- Test: `tests/test_screenwriter_agent/test_route_storyboard.py`

- [ ] **Step 1: 写测试 + StoryboardReq**

加到 `models/requests.py`:

```python
class StoryboardOptions(BaseModel):
    aspect_ratio: str = "9:16"
    fps: int = 24
    shot_duration_default: float = 3.0
    density: str = "常规"


class StoryboardReq(BaseModel):
    project_dir: str
    options: StoryboardOptions = Field(default_factory=StoryboardOptions)
    model: str | None = None
    reasoning_effort: str = "max"
```

`tests/test_screenwriter_agent/test_route_storyboard.py`:

```python
from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_storyboard_missing_script_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/storyboard", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in ("UPSTREAM_PRODUCT_MISSING", "PROJECT_DIR_NOT_FOUND")
```

> 完整 e2e（含修复+校验+落盘）在 Task 23。

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_storyboard.py -q
```

Expected: 404。

- [ ] **Step 3: 实现 routes/storyboard.py**

```python
"""POST /storyboard — SSE：读剧本.md → LLM JSON → 修复 + 校验 → 落盘 分镜.json。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.json_repair import repair_json_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.schema_validator import validate_storyboard
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import StoryboardReq

router = APIRouter()


@router.post("/storyboard")
async def storyboard(req: StoryboardReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}",
                      "hint": "项目目录打不开。"}})
    script_path = project_dir / "剧本.md"
    if not script_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "剧本.md missing",
                      "hint": "请先在「剧本」步生成剧本。"}})

    cfg = request.app.state.cfg
    model = req.model or cfg.default_models.get("storyboard")

    async def gen():
        try:
            yield sse_event("status", {"phase": "thinking"})
            tpl_text, _ = load_template("storyboard", project_dir=project_dir)
            md = script_path.read_text(encoding="utf-8")
            opts = req.options.model_dump()
            prompt = (tpl_text
                      + "\n\n## 剧本.md（输入）\n"
                      + md
                      + f"\n\n## 参数\nfps={opts['fps']}, "
                      + f"aspect_ratio={opts['aspect_ratio']}, "
                      + f"default_duration={opts['shot_duration_default']}, "
                      + f"density={opts['density']}\n\n"
                      + "**只输出一个 JSON 代码块**。")
            messages = [{"role": "user", "content": prompt}]

            api_key = os.environ.get("SCREENWRITER_LLM_API_KEY", "")
            base_url = os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                      "https://api.deepseek.com")
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort,
                               response_format={"type": "json_object"})

            yield sse_event("status", {"phase": "streaming"})
            acc: list[str] = []
            for ch in client.stream_chat(messages):
                if ch.kind == "delta":
                    acc.append(ch.text)
                    yield sse_event("delta", {"text": ch.text})
            raw = "".join(acc)

            yield sse_event("status", {"phase": "validating"})
            rr = repair_json_text(raw)
            if not rr.ok:
                # 落盘 raw，按 spec §6.6
                ts = time.strftime("%Y%m%dT%H%M%S")
                raw_path = project_dir / f"分镜_raw_{ts}.txt"
                atomic_write_text(raw_path, raw)
                yield sse_event("error", {
                    "code": "JSON_REPAIR_FAILED",
                    "message": rr.error,
                    "hint": "模型这次没给出 JSON，原始输出存到了 raw 文件，可换模型再试。",
                    "details": {"raw_output_path": str(raw_path),
                                "repair_steps_tried": rr.steps}})
                return

            # 校验 + 字段补全
            try:
                validated, warns = validate_storyboard(
                    rr.obj,
                    fallback_title=_extract_title_from_script(md),
                    default_aspect_ratio=opts["aspect_ratio"],
                    default_fps=opts["fps"],
                    default_shot_duration=opts["shot_duration_default"])
            except ValueError as e:
                yield sse_event("error", {
                    "code": "SCHEMA_VALIDATION_FAILED",
                    "message": str(e), "hint": "分镜数据缺关键字段，请重试。"})
                return

            yield sse_event("status", {"phase": "saving"})
            sb_path = project_dir / "分镜.json"
            atomic_write_text(sb_path, json.dumps(validated,
                                                   ensure_ascii=False, indent=2))
            yield sse_event("done", {
                "saved": str(sb_path),
                "result": validated,
                "warnings": [w.__dict__ for w in warns],
            })
        except Exception as e:
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": str(e), "hint": ""})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _extract_title_from_script(md: str) -> str:
    for ln in md.splitlines()[:30]:
        ln = ln.strip()
        for tag in ("标题：", "标题:"):
            if ln.startswith(tag):
                return ln[len(tag):].strip()
    return ""
```

注册到 `server.py`：

```python
    from .routes.storyboard import router as storyboard_router
    app.include_router(storyboard_router)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_storyboard.py -q
```

Expected: PASS (1 passed)。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/routes/storyboard.py screenwriter_agent/models/requests.py screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_storyboard.py
git commit -m "feat(screenwriter): /storyboard (SSE) — 剧本.md → repair → validate → 分镜.json"
```

Commit trailer required.

---

### Task 15: POST /prompts (SSE multi-product)

**Files:**
- Create: `screenwriter_agent/routes/prompts.py`
- Modify: `screenwriter_agent/server.py`
- Modify: `screenwriter_agent/models/requests.py` (PromptsReq)
- Test: `tests/test_screenwriter_agent/test_route_prompts.py`

- [ ] **Step 1: 写 PromptsReq + 测试**

加到 `models/requests.py`:

```python
class PromptsOptions(BaseModel):
    grid_mode: str = "9"                  # "single" | "4" | "9"
    include_character_refs: bool = True
    style_extra: str = ""
    negative_preset: str = "标准 SDXL"
    quality_boost: bool = True


class PromptsReq(BaseModel):
    project_dir: str
    options: PromptsOptions = Field(default_factory=PromptsOptions)
    model: str | None = None
    reasoning_effort: str = "high"
```

`tests/test_screenwriter_agent/test_route_prompts.py`:

```python
from pathlib import Path
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def test_prompts_missing_storyboard_400(tmp_path):
    c = TestClient(create_app())
    r = c.post("/prompts", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in ("UPSTREAM_PRODUCT_MISSING", "PROJECT_DIR_NOT_FOUND")
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_prompts.py -q
```

Expected: 404。

- [ ] **Step 3: 实现 routes/prompts.py**

```python
"""POST /prompts — SSE：分镜.json → 角色参考图 + N 宫格分镜图提示词。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import PromptsReq

router = APIRouter()


@router.post("/prompts")
async def prompts(req: PromptsReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": f"{req.project_dir}", "hint": "项目目录打不开。"}})
    sb_path = project_dir / "分镜.json"
    if not sb_path.is_file():
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": "分镜.json missing",
                      "hint": "请先在「分镜」步生成分镜.json。"}})
    try:
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(status_code=500, content={
            "error": {"code": "INTERNAL_ERROR",
                      "message": "分镜.json parse failed", "hint": ""}})

    cfg = request.app.state.cfg
    model = req.model or cfg.default_models.get("prompts")

    async def gen():
        try:
            api_key = os.environ.get("SCREENWRITER_LLM_API_KEY", "")
            base_url = os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                      "https://api.deepseek.com")
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)
            opts = req.options.model_dump()
            saved_paths: list[str] = []

            # 1) 角色参考图（每个 character 一份 .md）
            if opts["include_character_refs"]:
                tpl_text, _ = load_template("character_ref", project_dir=project_dir)
                for ch in sb.get("characters", []):
                    name = ch.get("name", "")
                    if not name:
                        continue
                    yield sse_event("status", {"phase": "streaming"})
                    prompt = (tpl_text
                              + "\n\n## 角色\n```json\n"
                              + json.dumps(ch, ensure_ascii=False, indent=2)
                              + "\n```\n## 全局风格\n"
                              + sb.get("globalStyle", "")
                              + f"\n## 风格补充\n{opts['style_extra']}\n")
                    acc: list[str] = []
                    for c in client.stream_chat([{"role": "user", "content": prompt}]):
                        if c.kind == "delta":
                            acc.append(c.text)
                    out_md = "".join(acc)
                    ref_dir = project_dir / "prompts" / "角色参考图"
                    ref_path = ref_dir / f"{name}_ref.md"
                    atomic_write_text(ref_path, out_md)
                    saved_paths.append(str(ref_path))
                    yield sse_event("partial", {"saved": str(ref_path),
                                                "kind": "character_ref"})

            # 2) N 宫格分镜图（按 grid_mode 分组）
            tpl_grid, _ = load_template("grid_prompt", project_dir=project_dir)
            grid_size = {"single": 1, "4": 4, "9": 9}.get(opts["grid_mode"], 9)
            shots = sb.get("shots", [])
            groups = [shots[i:i + grid_size] for i in range(0, len(shots), grid_size)]
            for gi, grp in enumerate(groups, start=1):
                yield sse_event("status", {"phase": "streaming"})
                prompt = (tpl_grid
                          + "\n\n## 全局风格\n"
                          + sb.get("globalStyle", "")
                          + f"\n## grid_mode\n{opts['grid_mode']}\n"
                          + f"## quality_boost\n{opts['quality_boost']}\n"
                          + f"## negative_preset\n{opts['negative_preset']}\n"
                          + f"## 风格补充\n{opts['style_extra']}\n"
                          + "## 本组镜头\n```json\n"
                          + json.dumps(grp, ensure_ascii=False, indent=2)
                          + "\n```\n")
                acc: list[str] = []
                for c in client.stream_chat([{"role": "user", "content": prompt}]):
                    if c.kind == "delta":
                        acc.append(c.text)
                sheet_md = "".join(acc)
                sheet_path = project_dir / "prompts" / "N宫格" / f"S{gi}.md"
                atomic_write_text(sheet_path, sheet_md)
                saved_paths.append(str(sheet_path))
                yield sse_event("partial", {"saved": str(sheet_path),
                                            "kind": "grid_prompt"})

            yield sse_event("done", {"saved": saved_paths, "result": {
                "character_refs": len(sb.get("characters", [])) if opts["include_character_refs"] else 0,
                "grid_sheets": len(groups)}, "warnings": []})
        except Exception as e:
            yield sse_event("error", {"code": "INTERNAL_ERROR",
                                       "message": str(e), "hint": ""})

    return StreamingResponse(gen(), media_type="text/event-stream")
```

注册到 `server.py`:

```python
    from .routes.prompts import router as prompts_router
    app.include_router(prompts_router)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_route_prompts.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add screenwriter_agent/routes/prompts.py screenwriter_agent/models/requests.py screenwriter_agent/server.py tests/test_screenwriter_agent/test_route_prompts.py
git commit -m "feat(screenwriter): /prompts (SSE multi-product) — 角色参考图 + N 宫格分镜图"
```

Commit trailer required.

---

## Workstream C: 模板

### Task 16: 5 套内置模板

**Files:**
- Create: `screenwriter_agent/templates/ideate.md`
- Create: `screenwriter_agent/templates/script.md`
- Create: `screenwriter_agent/templates/storyboard.md`
- Create: `screenwriter_agent/templates/character_ref.md`
- Create: `screenwriter_agent/templates/grid_prompt.md`

> 模板是 prompt 文本，长度 ~50-200 行/份，质量决定 LLM 输出质量。**请严格按 spec §5.2-5.6 的改写要点撰写**：保留教学系列原型的核心指令（题材识别 / 4 段式输出 / globalStyle 锁画风 / few-shot），按 spec 注明的"改/加/删"要点调整；如本机有 `漫剧/剧本/教学系列/01-03 *.md` 原型，**先读取参考**再撰写。

- [ ] **Step 1: 检查是否有教学系列原型可参考**

```bash
ls "漫剧/剧本/教学系列/" 2>/dev/null && echo "FOUND prototypes" || echo "NO prototypes; build from spec §5"
```

- [ ] **Step 2: 撰写 ideate.md（spec §5.2）**

`screenwriter_agent/templates/ideate.md` 应包含：
- 角色定义：「你是一名短剧编剧」
- 题材识别（成语典故触发额外约束的指令）
- 风格定位 / 钩子结构
- 4 段式输出格式：标题 / 切入角度 / 摘要 / 看点
- 多轮意图识别指令（"再生一个 / 深入第 N 个 / 改成 X"——识别意图、保留未涉及候选、只更新涉及候选）
- 不要"等我发题目"——Agent 第一轮就给完整 context
- 输出固定标题 `候选 1｜标题：xxx` 等便于解析

- [ ] **Step 3: 撰写 script.md（spec §5.3）**

应包含：
- 整体风格 / 钩子结构
- 镜头格式（时长/画面/旁白/字幕/音效）
- 旁白语速估算 + 镜头节奏 3-6 秒（由 duration_sec / 镜头数自适应）
- 固定 md 头部块 `# 剧本信息`（标题/题材类型/总时长/画面风格基调），便于 Agent 解析
- 固定锚点 `## 镜头 01 / ## 镜头 02 ...`

- [ ] **Step 4: 撰写 storyboard.md（spec §5.4）**

应包含：
- 全局设定 / 角色固定外貌 / globalStyle / stylePrompt 写法
- 镜头切分规则
- 输出 JSON 结构（教学系列 02 schema）
- 头部明确"**只输出一个 JSON 代码块**"
- 末尾嵌入一段示例 JSON（few-shot）

- [ ] **Step 5: 撰写 character_ref.md（spec §5.5）**

几乎完整移植教学系列 03 A；明确每段头部用 `### 角色：<name>` 便于 Agent 按角色 split。

- [ ] **Step 6: 撰写 grid_prompt.md（spec §5.6）**

包含：分组规则（按 grid_mode）/ 每段必含小节 / 像素尺寸参考 / `style_extra` 注入"画风锁定"段尾 / `quality_boost=true` 时追加预设画质词 / `negative_preset` 注入负面词段。

- [ ] **Step 7: 验证 template_loader 能加载所有 5 个**

```bash
python -c "
from pathlib import Path
from screenwriter_agent.core.template_loader import load_template, BUILTIN_IDS
for tid in BUILTIN_IDS:
    text, src = load_template(tid, project_dir=Path('/tmp'))
    assert src == 'builtin' and len(text) > 100, f'{tid} too short: {len(text)}'
    print(f'{tid}: {len(text)} chars (builtin)')
print('all 5 templates loaded')
"
```

Expected: 5 行 `<name>: <N> chars (builtin)` + `all 5 templates loaded`。

- [ ] **Step 8: 跑 template_loader 测试再次确认（builtin skip 现解除）**

```bash
python -m pytest tests/test_screenwriter_agent/test_template_loader.py -q
```

Expected: 全部 PASS（不再 skip）。

- [ ] **Step 9: Commit**

```bash
git add screenwriter_agent/templates/
git commit -m "feat(screenwriter): 5 套内置模板（ideate/script/storyboard/character_ref/grid_prompt）"
```

Commit trailer required.

---

## Workstream D: 主软件集成

### Task 17: screenwriter_lifecycle（spawn / health-poll / terminate）

**Files:**
- Create: `drama_shot_master/agents/__init__.py`（空）
- Create: `drama_shot_master/agents/screenwriter_lifecycle.py`
- Test: `tests/test_screenwriter_agent/test_lifecycle.py`

- [ ] **Step 1: 写测试**

`tests/test_screenwriter_agent/test_lifecycle.py`:

```python
def test_lifecycle_module_importable():
    from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
    lc = ScreenwriterLifecycle()
    assert hasattr(lc, "spawn") and hasattr(lc, "terminate") and hasattr(lc, "port")
```

> Spawn 子进程的实测留给 Task 23 e2e；本任务只测可导入与接口存在。

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_lifecycle.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现**

`drama_shot_master/agents/__init__.py`: 空。

`drama_shot_master/agents/screenwriter_lifecycle.py`:

```python
"""Spawn screenwriter_agent 子进程；监控健康；优雅退出。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


class ScreenwriterLifecycle:
    """单例：主软件启动时 spawn agent；退出时 terminate。"""

    def __init__(self, base_port: int = 18430, log_dir: Path | None = None):
        self.base_port = base_port
        self.port = base_port
        self._proc: subprocess.Popen | None = None
        self._log_dir = log_dir or (Path.home() / ".drama_shot_master" / "logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._port_file = self._log_dir / ".screenwriter_port"
        self._pid_file = self._log_dir / ".screenwriter.pid"

    def spawn(self) -> int:
        """Spawn agent 子进程；返回实际端口。已运行则 no-op。"""
        if self._proc is not None and self._proc.poll() is None:
            return self.port
        log_path = self._log_dir / "screenwriter_agent.log"
        log_f = open(log_path, "ab")
        env = os.environ.copy()
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "screenwriter_agent",
             "--port", str(self.base_port)],
            stdout=log_f, stderr=subprocess.STDOUT,
            env=env, close_fds=True)
        self.port = self.base_port  # 端口冲突时 agent 自己 +1..+9，端口写到 .port 文件
        self._pid_file.write_text(str(self._proc.pid))
        # 给 1 秒等 agent 起来
        time.sleep(1.0)
        return self.port

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def terminate(self, timeout: float = 5.0) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is not None:
            self._proc = None
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=2.0)
        self._proc = None
        try:
            self._pid_file.unlink()
        except OSError:
            pass

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_lifecycle.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/agents/ tests/test_screenwriter_agent/test_lifecycle.py
git commit -m "feat(screenwriter): drama_shot_master.agents.ScreenwriterLifecycle（spawn/terminate）"
```

Commit trailer required.

---

### Task 18: ScreenwriterClient（httpx + SSE 解析）

**Files:**
- Create: `drama_shot_master/agents/screenwriter_client.py`
- Test: `tests/test_screenwriter_agent/test_client_sse.py`

- [ ] **Step 1: 写测试（用 mock SSE 字符串测试解析器）**

`tests/test_screenwriter_agent/test_client_sse.py`:

```python
from drama_shot_master.agents.screenwriter_client import parse_sse_lines


def test_parse_sse_events():
    raw = (
        "event: status\n"
        'data: {"phase": "thinking"}\n'
        "\n"
        "event: delta\n"
        'data: {"text": "hi"}\n'
        "\n"
        "event: done\n"
        'data: {"saved": "/x.json"}\n'
        "\n"
    )
    events = list(parse_sse_lines(raw.splitlines(keepends=True)))
    assert [e["event"] for e in events] == ["status", "delta", "done"]
    assert events[1]["data"]["text"] == "hi"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_screenwriter_agent/test_client_sse.py -q
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现**

`drama_shot_master/agents/screenwriter_client.py`:

```python
"""主软件用的 Agent 客户端：httpx + 简单 SSE 解析。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def parse_sse_lines(lines: Iterable[str]) -> Iterator[dict]:
    """把 SSE 文本（按行）解析为 {event, data:dict} 序列。"""
    cur_event = ""
    cur_data: list[str] = []
    for ln in lines:
        ln = ln.rstrip("\n").rstrip("\r")
        if not ln:
            if cur_event:
                try:
                    data = json.loads("\n".join(cur_data)) if cur_data else {}
                except Exception:
                    data = {}
                yield {"event": cur_event, "data": data}
            cur_event = ""
            cur_data = []
            continue
        if ln.startswith("event:"):
            cur_event = ln[len("event:"):].strip()
        elif ln.startswith("data:"):
            cur_data.append(ln[len("data:"):].strip())


class ScreenwriterClient:
    """主软件单例。负责发请求 + 解析 SSE。"""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def health(self) -> dict:
        import httpx
        return httpx.get(f"{self.base_url}/health", timeout=3.0).json()

    def scan_project(self, project_dir: Path) -> dict:
        import httpx
        r = httpx.get(f"{self.base_url}/project",
                      params={"dir": str(project_dir)}, timeout=5.0)
        return r.json()

    def ideate_select(self, project_dir: Path, selected_id: str) -> dict:
        import httpx
        r = httpx.post(f"{self.base_url}/ideate/select",
                       json={"project_dir": str(project_dir),
                             "selected_id": selected_id}, timeout=5.0)
        return r.json()

    def stream_post(self, path: str, body: dict) -> Iterator[dict]:
        """POST + SSE 流；yield {event,data} dict。"""
        import httpx
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{self.base_url}{path}", json=body) as resp:
                resp.raise_for_status()
                yield from parse_sse_lines(resp.iter_lines())
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_screenwriter_agent/test_client_sse.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/agents/screenwriter_client.py tests/test_screenwriter_agent/test_client_sse.py
git commit -m "feat(screenwriter): ScreenwriterClient（httpx + SSE 解析）"
```

Commit trailer required.

---

### Task 19: drama_shot_master/config.py 添加 screenwriter 配置项

**Files:**
- Modify: `drama_shot_master/config.py`

- [ ] **Step 1: 读现有 Config 字段**

```bash
grep -nE "@dataclass|^    [a-z_]+:.*=" drama_shot_master/config.py | head -20
```

- [ ] **Step 2: 加新字段**

在 `Config` dataclass 中追加（保持与同类字段风格一致）：

```python
    # screenwriter_agent
    screenwriter_agent_port: int = 18430
    screenwriter_llm_api_key: str = ""
    screenwriter_llm_base_url: str = "https://api.deepseek.com"
    screenwriter_models: dict[str, str] = field(default_factory=lambda: {
        "ideate":     "doubao-1-5-thinking-pro-250415",
        "script":     "doubao-1-5-thinking-pro-250415",
        "storyboard": "deepseek-v4-pro",
        "prompts":    "deepseek-v4-flash",
    })
    screenwriter_project_root: str = ""    # 默认空，UI 提示选目录
```

如有 `to_dict` / `from_dict` 序列化函数，确保新字段也参与。

- [ ] **Step 3: 烟雾测试**

```bash
python -c "
from drama_shot_master.config import load_config
cfg = load_config()
assert hasattr(cfg, 'screenwriter_models')
assert cfg.screenwriter_agent_port == 18430
print('ok')
"
```

Expected: `ok`。

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/config.py
git commit -m "config: 加 screenwriter_agent 相关配置项（port/api_key/models/project_root）"
```

Commit trailer required.

---

### Task 20: nav_config 加"编剧"项 + 阶段重排

**Files:**
- Modify: `drama_shot_master/ui/nav_config.py`
- Test: `tests/test_ui/test_nav_config.py`

- [ ] **Step 1: 写/更新测试**

加到 `tests/test_ui/test_nav_config.py`（或新文件）：

```python
def test_screenwriter_in_funcs():
    from drama_shot_master.ui.nav_config import FUNCS
    keys = [k for _, k in FUNCS]
    assert "screenwriter" in keys
    # 应该是第一项（视觉次序上的"剧本筹备"在前）
    assert keys[0] == "screenwriter"


def test_screenwriter_in_phases_drama_prep():
    from drama_shot_master.ui.nav_config import PHASES
    cats = [t for t, _ in PHASES]
    assert any("剧本筹备" in t for t in cats)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_nav_config.py -q
```

Expected: FAIL。

- [ ] **Step 3: 改 nav_config.py**

读现状：

```bash
sed -n '1,40p' drama_shot_master/ui/nav_config.py
```

替换 `FUNCS`：

```python
FUNCS = [
    ("编剧", "screenwriter"),
    ("拆图", "split"),
    ("拼图", "combine"),
    ("裁边", "trim"),
    ("出图", "imggen"),
    ("生视频", "video_gen"),
    ("配音", "dubbing"),
    ("配乐", "soundtrack"),
]
```

替换 `PHASES`：

```python
PHASES = [
    ("① 剧本筹备", ["screenwriter"]),
    ("② 素材准备", ["split", "combine", "trim"]),
    ("③ 分镜创作", ["imggen"]),
    ("④ 视频出片", ["video_gen", "dubbing", "soundtrack"]),
]
```

如有 `TASK_KEYS` 集合，加 `"screenwriter"`：

```python
TASK_KEYS = {"imggen", "video_gen", "soundtrack", "dubbing", "screenwriter"}
```

如有 `ICONS` 字典，加入：

```python
ICONS = {
    "screenwriter": "edit.svg",
    ...其余保留
}
```

- [ ] **Step 4: 加 icon 资源**

```bash
ls drama_shot_master/assets/icons/edit.svg 2>/dev/null \
    || echo "需要补一份同风格 SVG；放到 assets/icons/edit.svg"
```

如缺，从 `assets/icons/` 现有 SVG（如 cut.svg / palette.svg）参考粗细/线条权重，写一个 24×24 编辑铅笔图标。**最小可用方案**（无需精修）：

`drama_shot_master/assets/icons/edit.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 20h9"/>
  <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>
</svg>
```

（lucide-icons 风格的 pen-line 图标）

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/test_nav_config.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/nav_config.py drama_shot_master/assets/icons/edit.svg tests/test_ui/test_nav_config.py
git commit -m "nav: 加'编剧'功能项 + '①剧本筹备'阶段（其它阶段编号顺延）+ edit.svg 图标"
```

Commit trailer required.

---

### Task 21: screenwriter_panel — 项目列表 + Wizard 主-详（沿用其它面板风格）

**Files:**
- Create: `drama_shot_master/ui/panels/screenwriter_panel.py`
- Test: `tests/test_ui/test_screenwriter_panel_smoke.py`

> **本面板必须沿用既有 UI 约定**（参见 spec §7.4）：QHBoxLayout + stretch 后置；按钮命名"新建/打开/删除"；任务表 4 列（名称/状态/最近输出/更新时间）；`_fit_name_col` 让名称+状态占满 viewport；状态色用 `status_color(status, cfg)`；详情区是 Wizard（QStackedWidget 4 子面板：创意/剧本/分镜/提示词）。
>
> MVP 版 Wizard 子面板用最简单的"上方提示文本 + 中间 QPlainTextEdit 编辑器 + 下方两个按钮（生成 / 打开输出目录）"——P2 才做聊天面板美化、warnings 行内高亮等。

- [ ] **Step 1: 写 smoke 测试**

`tests/test_ui/test_screenwriter_panel_smoke.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_panel_constructs(tmp_path):
    _app()
    cfg = type("C", (), {"screenwriter_project_root": str(tmp_path),
                         "screenwriter_models": {}})()
    panel = ScreenwriterPanel(cfg=cfg, client=None, lifecycle=None)
    # 必备控件
    assert hasattr(panel, "table")
    assert hasattr(panel, "btn_new")
    assert hasattr(panel, "btn_open")
    assert hasattr(panel, "btn_del")
    assert hasattr(panel, "wizard")          # QStackedWidget
    assert panel.wizard.count() == 4         # 4 阶段


def test_panel_table_cols(tmp_path):
    _app()
    cfg = type("C", (), {"screenwriter_project_root": str(tmp_path),
                         "screenwriter_models": {}})()
    panel = ScreenwriterPanel(cfg=cfg, client=None, lifecycle=None)
    hdr = panel.table.horizontalHeaderItem
    assert hdr(0).text() == "名称"
    assert hdr(1).text() == "状态"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_screenwriter_panel_smoke.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 panel（约 200-300 行）**

`drama_shot_master/ui/panels/screenwriter_panel.py` 关键骨架：

```python
"""ScreenwriterPanel：编剧 Wizard 面板（项目列表 + 4 阶段详情）。

沿用 video/imggen/soundtrack 面板的"主-详 + viewport eventFilter + 名称列吃可见区"约定。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget, QLabel, QPlainTextEdit, QMessageBox,
)

from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.theme import status_color


_STAGE_NAMES = ("创意", "剧本", "分镜", "提示词")


class ScreenwriterPanel(BasePanel):
    """编剧面板。"""

    statusMessage = Signal(str)

    def __init__(self, cfg, client, lifecycle, state=None, parent=None):
        # BasePanel.__init__ 需要 state 和 cfg；按其它面板的调用方式
        super().__init__(state, cfg, parent)
        self._client = client          # ScreenwriterClient
        self._lifecycle = lifecycle    # ScreenwriterLifecycle
        self._current_project: Path | None = None
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self):
        return False, "请通过列表管理编剧项目"

    def execute(self):
        raise NotImplementedError

    def _build_ui(self):
        root = QVBoxLayout(self)
        # 顶部按钮
        bar = QHBoxLayout()
        self.btn_new = QPushButton("新建")
        self.btn_open = QPushButton("打开项目目录…")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        # 项目列表（4 列）
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "最近输出", "更新时间"])
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 150)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        root.addWidget(self.table, 1)
        self.table.viewport().installEventFilter(self)

        # Wizard 区（4 阶段子面板）
        self.wizard = QStackedWidget()
        for name in _STAGE_NAMES:
            w = QWidget()
            v = QVBoxLayout(w)
            v.addWidget(QLabel(f"阶段：{name}（MVP 占位）"))
            edit = QPlainTextEdit()
            edit.setPlaceholderText(f"{name} 阶段产物预览/编辑（MVP 简版）")
            v.addWidget(edit, 1)
            row = QHBoxLayout()
            btn_gen = QPushButton(f"生成 {name}")
            btn_open = QPushButton("打开输出目录")
            row.addWidget(btn_gen)
            row.addWidget(btn_open)
            row.addStretch(1)
            v.addLayout(row)
            self.wizard.addWidget(w)
        root.addWidget(self.wizard, 1)

        # 绑定
        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_del.clicked.connect(self._on_del)
        self.table.itemSelectionChanged.connect(self._on_row_selected)

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport():
            if ev.type() == QEvent.Resize:
                self._fit_name_col()
            elif ev.type() == QEvent.MouseButtonPress:
                if not self.table.indexAt(ev.pos()).isValid():
                    return True
        return super().eventFilter(obj, ev)

    def _fit_name_col(self):
        vw = self.table.viewport().width()
        self.table.setColumnWidth(0, max(150, vw - self.table.columnWidth(1)))

    # ---- 项目管理（MVP：用文件夹扫描 cfg.screenwriter_project_root）----

    def _project_root(self) -> Path:
        return Path(getattr(self.cfg, "screenwriter_project_root", "") or "")

    def refresh(self):
        self.table.setRowCount(0)
        root = self._project_root()
        if not root.is_dir():
            return
        for sub in sorted([p for p in root.iterdir() if p.is_dir()]):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(sub.name))
            # MVP：状态拉自 Agent /project；若 client 无 → 显示"未知"
            status_str = "未知"
            if self._client is not None:
                try:
                    st = self._client.scan_project(sub)
                    status_str = st.get("status", "未知")
                except Exception:
                    pass
            si = QTableWidgetItem(status_str)
            si.setForeground(QColor(status_color(status_str, self.cfg)))
            self.table.setItem(r, 1, si)
            self.table.setItem(r, 2, QTableWidgetItem("—"))
            self.table.setItem(r, 3, QTableWidgetItem(""))
        self._fit_name_col()

    def _on_new(self):
        root = self._project_root()
        if not root.is_dir():
            QMessageBox.information(self, "未配置目录",
                                    "请在设置里指定编剧项目目录（screenwriter_project_root）")
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建编剧项目", "项目名:")
        if not ok or not name.strip():
            return
        new_dir = root / name.strip()
        try:
            new_dir.mkdir(exist_ok=False)
        except FileExistsError:
            QMessageBox.warning(self, "已存在", "项目名已存在")
            return
        self.refresh()

    def _on_open(self):
        d = QFileDialog.getExistingDirectory(self, "打开编剧项目目录")
        if not d:
            return
        self.cfg.update_settings(screenwriter_project_root=d) if hasattr(
            self.cfg, "update_settings") else None
        self.refresh()

    def _on_del(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r, 0).text()
        if QMessageBox.question(
                self, "删除", f"确定删除项目「{name}」（连同目录）？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        import shutil
        shutil.rmtree(self._project_root() / name, ignore_errors=True)
        self.refresh()

    def _on_row_selected(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r, 0).text()
        self._current_project = self._project_root() / name
        # 切到 recommended_next 对应的 wizard 页
        idx = 0
        if self._client is not None:
            try:
                st = self._client.scan_project(self._current_project)
                idx = {"ideate": 0, "script": 1,
                       "storyboard": 2, "prompts": 3}.get(
                    st.get("recommended_next", "ideate"), 0)
            except Exception:
                pass
        self.wizard.setCurrentIndex(idx)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_screenwriter_panel_smoke.py -q -p no:faulthandler
```

Expected: PASS (2 passed)。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/screenwriter_panel.py tests/test_ui/test_screenwriter_panel_smoke.py
git commit -m "feat(ui): ScreenwriterPanel — 项目列表 + 4 阶段 Wizard（MVP 简版；沿用 viewport eventFilter + status_color）"
```

Commit trailer required.

---

### Task 22: AppShell + main.py 接入

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Modify: `drama_shot_master/main.py`

- [ ] **Step 1: AppShell 注册 screenwriter page**

读 `app_shell.py` 的 `_build_pages` 现状，加入 `screenwriter`：

```python
        builders = {
            "screenwriter": self._make_screenwriter_page,    # 新增
            "split": ...,
            ...
        }
```

加方法 `_make_screenwriter_page`:

```python
    def _make_screenwriter_page(self):
        from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel
        # client/lifecycle 由 main.py 注入到 self；面板可能在两者未就绪时被构建（启动竞速）
        return ScreenwriterPanel(
            cfg=self.cfg,
            client=getattr(self, "screenwriter_client", None),
            lifecycle=getattr(self, "screenwriter_lifecycle", None),
            state=self.state,
        )
```

- [ ] **Step 2: main.py 启动时 spawn agent + 创建 client**

读 `main.py`，在 `w = AppShell()` 之前/之后加：

```python
    from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
    from drama_shot_master.agents.screenwriter_client import ScreenwriterClient

    lifecycle = ScreenwriterLifecycle(base_port=app_cfg.screenwriter_agent_port)
    lifecycle.spawn()
    client = ScreenwriterClient(lifecycle.base_url())

    w = AppShell()
    w.screenwriter_lifecycle = lifecycle
    w.screenwriter_client = client
```

并在窗口 close 时收尾：

```python
    # 已有 app.exec() 之后
    try:
        ret = app.exec()
    finally:
        lifecycle.terminate()
    sys.exit(ret)
```

> 注：如果 AppShell 构建 page 在 lifecycle/client 注入之前，面板会拿到 None——这是 MVP 接受的（refresh/scan 自动 noop）。**改进**：把 `_make_screenwriter_page` 内部 lazy 读 `getattr(self, "screenwriter_client", None)`，每次 refresh 时重新拿一次最新引用；或在 lifecycle 注入后调一次 `self.pages["screenwriter"].refresh()`。简化：注入后强制刷新。

```python
    w.screenwriter_lifecycle = lifecycle
    w.screenwriter_client = client
    if "screenwriter" in w.pages:
        # 注入到已构建的 panel
        panel = w.pages["screenwriter"]
        panel._client = client
        panel._lifecycle = lifecycle
        panel.refresh()
```

- [ ] **Step 3: 跑 app_shell smoke**

```bash
python -m pytest tests/test_ui/test_app_shell_smoke.py -q -p no:faulthandler 2>&1 | tail -3
```

Expected: PASS（含新的 page）。

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/ui/app_shell.py drama_shot_master/main.py
git commit -m "feat(ui): AppShell 注册 screenwriter page + main.py spawn/terminate lifecycle"
```

Commit trailer required.

---

## Workstream E: 验收

### Task 23: 端到端 smoke + 全量验收

**Files:**
- Create: `tests/test_screenwriter_agent/test_e2e_smoke.py`

- [ ] **Step 1: 写 e2e smoke（mock LLM）**

`tests/test_screenwriter_agent/test_e2e_smoke.py`:

```python
"""端到端 smoke：mock LLM 输出，依次跑 4 阶段，断言产物落盘 + 内容形状合规。"""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from screenwriter_agent.server import create_app


_STORYBOARD_JSON = {
    "title": "demo",
    "aspectRatio": "9:16",
    "fps": 24,
    "totalDuration": 12,
    "globalStyle": "古风水墨",
    "characters": [{"name": "狐妖", "appearance": "白衣红眼狐尾披肩长发"}],
    "shots": [
        {"shotId": "S01", "description": "雨夜画面", "duration": 6,
         "stylePrompt": "古风水墨，雨夜松林，狐妖立于树下，整体调性沉静"},
        {"shotId": "S02", "description": "书生撑伞", "duration": 6,
         "stylePrompt": "古风水墨，雨夜书生撑伞踱步，整体调性温润"},
    ],
}


@pytest.fixture
def mock_llm(monkeypatch):
    """把 LLMClient.stream_chat 替换为返回写死内容的迭代器。"""
    from screenwriter_agent.core import llm_client

    def _fake_stream(self, messages):
        # 根据 prompt 内容猜阶段：
        text = ""
        last = messages[-1]["content"] if messages else ""
        if "候选" in last or "ideate" in last.lower():
            text = "候选 1｜标题：躺平农夫\n切入角度：反转命运\n摘要：xxx\n看点：yyy\n\n候选 2｜标题：xxx"
        elif "镜头 01" in last or "剧本" in last:
            text = "# 剧本信息\n标题: demo\n## 镜头 01\n..."
        elif "JSON" in last or "json_object" in str(messages):
            text = "```json\n" + json.dumps(_STORYBOARD_JSON, ensure_ascii=False) + "\n```"
        else:
            text = "角色参考图提示词或 N 宫格 prompt 占位"
        from screenwriter_agent.core.llm_client import StreamChunk
        for ch in text:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=text)

    monkeypatch.setattr(llm_client.LLMClient, "stream_chat", _fake_stream)


def test_e2e_chain(tmp_path, mock_llm, monkeypatch):
    monkeypatch.setenv("SCREENWRITER_LLM_API_KEY", "dummy")
    monkeypatch.setenv("SCREENWRITER_LLM_BASE_URL", "https://example.com")
    c = TestClient(create_app())

    # 1) /ideate/chat
    r = c.post("/ideate/chat", json={
        "project_dir": str(tmp_path),
        "context": {"core_idea": "古风狐妖", "candidate_count": 2},
        "messages": [{"role": "user", "content": "出 2 个候选"}],
    })
    assert r.status_code == 200
    assert (tmp_path / "idea.json").is_file()

    # 2) /ideate/select
    idea = json.loads((tmp_path / "idea.json").read_text(encoding="utf-8"))
    if idea.get("candidates"):
        cid = idea["candidates"][0]["id"]
        r = c.post("/ideate/select", json={
            "project_dir": str(tmp_path), "selected_id": cid})
        assert r.status_code == 200

    # 3) /script
    r = c.post("/script", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "剧本.md").is_file()

    # 4) /storyboard
    r = c.post("/storyboard", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "分镜.json").is_file()
    sb = json.loads((tmp_path / "分镜.json").read_text(encoding="utf-8"))
    assert sb["title"] == "demo"
    assert len(sb["shots"]) == 2

    # 5) /prompts
    r = c.post("/prompts", json={"project_dir": str(tmp_path), "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "prompts").is_dir()
    # 至少有一份 N 宫格输出
    n_grid = list((tmp_path / "prompts" / "N宫格").glob("S*.md")) if (tmp_path / "prompts" / "N宫格").is_dir() else []
    assert len(n_grid) >= 1
```

- [ ] **Step 2: 跑 e2e**

```bash
python -m pytest tests/test_screenwriter_agent/test_e2e_smoke.py -q
```

Expected: PASS。

- [ ] **Step 3: 全 screenwriter 测试套件**

```bash
python -m pytest tests/test_screenwriter_agent/ -q -p no:faulthandler 2>&1 | tail -5
```

Expected: 全 PASS (大约 30+ 测试)，0 FAILED。

- [ ] **Step 4: UI smoke 套件不回归**

```bash
python -m pytest tests/test_ui/ -q -p no:faulthandler 2>&1 | tail -5
```

Expected: PASS count ≥ 之前，0 FAILED（新增 screenwriter_panel_smoke 算上）。

- [ ] **Step 5: 全局 acceptance**

```bash
echo "=== 1. screenwriter 包就位 ==="
ls screenwriter_agent/server.py screenwriter_agent/routes/health.py \
   screenwriter_agent/templates/ideate.md

echo "=== 2. nav 含 screenwriter ==="
python -c "from drama_shot_master.ui.nav_config import FUNCS; \
  print('编剧 in funcs:', 'screenwriter' in [k for _,k in FUNCS])"

echo "=== 3. 5 套模板都加载得到 ==="
python -c "
from pathlib import Path
from screenwriter_agent.core.template_loader import load_template, BUILTIN_IDS
for tid in BUILTIN_IDS:
    text, _ = load_template(tid, project_dir=Path('/tmp'))
    print(tid, len(text), 'chars')
"

echo "=== 4. agent 能 spawn（spawn → /health → terminate） ==="
python -c "
import time
from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
from drama_shot_master.agents.screenwriter_client import ScreenwriterClient
lc = ScreenwriterLifecycle(base_port=18439)
try:
    lc.spawn()
    time.sleep(2)
    c = ScreenwriterClient(lc.base_url())
    h = c.health()
    assert h['status'] == 'ok'
    print('health ok:', h['version'])
finally:
    lc.terminate()
print('lifecycle ok')
"
```

Expected: 全 ok（无异常 / KeyError / Connection refused）。

- [ ] **Step 6: 验收 commit**

```bash
git add tests/test_screenwriter_agent/test_e2e_smoke.py
git commit -m "test(screenwriter): e2e smoke 跑通 4 阶段 mock LLM 链路 + 全局 acceptance 验收"
```

Commit trailer required.

---

## Self-Review

**1. Spec coverage 核对：**

| Spec 节 | 覆盖任务 |
|---|---|
| §2 架构 | Task 2 包骨架；Task 9 server；Task 17 lifecycle；Task 22 主软件接入 |
| §3.1 /health | Task 10 |
| §3.2 /project | Task 11；§3.2 status 推导 → Task 7 project_scanner |
| §3.3 /ideate/chat | Task 12 |
| §3.4 /ideate/select | Task 12 |
| §3.5 /script | Task 13 |
| §3.6 /storyboard | Task 14 |
| §3.7 /prompts | Task 15 |
| §3.8 /templates | **延后到 P3**（spec § 7.8） |
| §3.9 取消 | 简化：MVP 客户端断连即终止（FastAPI 默认行为）；细化留 P2 |
| §3.10 purge_downstream | **延后到 P2**（UI 重做按钮属 P2） |
| §4 数据流时序 | Task 23 e2e 走通主线；边界场景部分（手工编辑/并发写）由原子写覆盖 |
| §5.1-5.7 5 套模板 | Task 16 |
| §6.1 错误码 | Task 12-15 各路由按需返回；MVP 实现 ~8 个常用 code |
| §6.2 JSON 修复链 | Task 4 |
| §6.3 warnings 分级 | Task 5 实现 info/warning/error；critical 抛 ValueError |
| §6.4 重试 | UI 侧实现，本 MVP 不强约束 |
| §6.5 日志 | Task 3 logger（route 内调用，MVP 暂不强制；P2 加） |
| §6.6 raw 保留 | Task 14 实现失败时落 `分镜_raw_<ts>.txt` |
| §7.1 包结构 | Tasks 2/3/4/5/6/7/8/9/10-15/16 全覆盖 |
| §7.2 依赖 | Task 1 |
| §7.3 主软件对接面 | Tasks 17/18/19/20/21/22 |
| §7.4 UI 风格一致性 | Task 21 显式遵循（4 列表 + viewport eventFilter + status_color） |
| §7.5 AgentClient API | Task 18 |
| §7.6 进程生命周期 | Task 17 |
| §7.7 测试策略 | Tasks 4/5/6/7/8 单元；Tasks 10-15 路由集成；Task 23 e2e |
| §7.8 P1 范围 | 本计划全覆盖 |
| §7.9 风险 | spawn `.pid` 文件 → Task 17 |

**P1 显式延后（spec § 7.8）：**
- /templates 路由（P3 user-scope CRUD）
- /project/logs（P3）
- warnings 行内高亮、storyboard 双视图、聊天面板美化、purge_downstream UI（P2）

**2. Placeholder 扫描：** 无 TBD/TODO/"similar to"——所有任务自包含代码。Task 16 模板内容指定为"按 spec §5 撰写"，但该 spec 提供了"保留/改/加/删"具体改写要点，subagent 可据此完整撰写；如本机有教学系列原型，先读再写质量更高。

**3. Type consistency：**
- `LLMClient.stream_chat(messages) -> Iterator[StreamChunk]` 全程一致（Task 8 定义；Tasks 12-15 + Task 23 mock 一致使用）。
- `ProjectState` 字段（status / stages / recommended_next / config_overrides）Task 7 定义、Task 11 透传一致。
- `RepairResult.ok/obj/steps/raw/error` Task 4 定义、Task 14 使用一致。
- `validate_storyboard(...) -> (dict, list[ValidationWarn])` Task 5 定义、Task 14 使用一致。
- `ScreenwriterLifecycle.spawn/terminate/base_url` Task 17 定义、Task 22 使用一致。
- `ScreenwriterClient.scan_project/ideate_select/stream_post + parse_sse_lines` Task 18 定义、Task 21 + Task 22 使用一致。
- 模板 id 集合 `BUILTIN_IDS` Task 6 定义、Tasks 12-16 引用一致。
