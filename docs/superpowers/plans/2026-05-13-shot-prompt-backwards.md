# Shot-Prompt-Backwards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建本地 Web App，让用户从文件夹选分镜图（4 种输入模式）+ 选反推模板 + 填补充输入 → 多 vision 后端反推 → 输出 ComfyUI LTX 2.3 可用的结构化提示词 md/json；同时整合 shot-master 的拆图/拼图/去白边功能为 Web Tab。

**Architecture:** FastAPI 后端 + 原生 HTML/Alpine.js 前端，零构建链。`VisionProvider` 抽象 4 个后端类。shot-master 通过 `pip install -e ../shot-master` 本地依赖直接 import 复用。批量执行串行 + SSE 进度推送。宫格模式下拆图预览门禁（必须人工确认）才能反推。

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, python-dotenv, Pillow, numpy (via shot-master), Alpine.js, pytest, pytest-asyncio, httpx (test mock), google-genai, openai SDK, anthropic SDK, dashscope SDK.

**Spec:** `需求.md`（项目根目录）

**File Map** (按职责分文件，每文件 < 200 行)：

```
shot-prompt-backwards/
├── pyproject.toml                     # 依赖（含 shot-master 本地路径）
├── .env.example                       # API key 模板
├── .gitignore
├── run.bat / run.sh                   # 一键启动
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI 入口 + 静态文件挂载 + 路由聚合
│   ├── config.py                      # 加载 .env + settings.json
│   ├── api/
│   │   ├── __init__.py
│   │   ├── inference.py               # POST /api/inference
│   │   ├── batch.py                   # POST /api/batch + SSE
│   │   ├── templates.py               # 模板 CRUD
│   │   ├── grid_split.py              # 拆图预览 + 落盘
│   │   ├── grid_combine.py            # 拼图
│   │   ├── border_trim.py             # 去白边
│   │   ├── files.py                   # 列文件夹/缩略图
│   │   └── settings.py                # 设置 API
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                    # VisionProvider(ABC) + ProviderConfig
│   │   ├── gemini.py
│   │   ├── openai_compat.py
│   │   ├── anthropic.py
│   │   ├── qwen_vl.py
│   │   └── factory.py                 # 注册表 + endpoint 预设
│   └── core/
│       ├── __init__.py
│       ├── template_engine.py         # frontmatter 解析 + 渲染
│       ├── output_writer.py           # 写 md/json
│       ├── task_runner.py             # 串行批量 + 事件流
│       └── result_parser.py           # 从 vision 原始文本提取字段
├── web/
│   ├── index.html                     # 单页骨架（Alpine.js）
│   ├── app.js                         # 路由 + 全局状态
│   ├── styles.css
│   └── tabs/
│       ├── inference.html
│       ├── split.html
│       ├── combine.html
│       ├── trim.html
│       ├── templates.html
│       └── settings.html
├── templates/
│   ├── three_frame.md
│   ├── four_frame.md
│   ├── multi_frame_adaptive.md
│   └── single_frame.md
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_template_engine.py
    ├── test_result_parser.py
    ├── test_output_writer.py
    ├── test_task_runner.py
    ├── test_providers/
    │   ├── test_base.py
    │   ├── test_factory.py
    │   ├── test_gemini.py
    │   ├── test_openai_compat.py
    │   ├── test_anthropic.py
    │   └── test_qwen_vl.py
    └── test_api/
        ├── test_inference.py
        ├── test_batch.py
        ├── test_grid_split.py
        ├── test_grid_combine.py
        ├── test_border_trim.py
        ├── test_templates.py
        ├── test_settings.py
        └── test_files.py
```

**Milestone 编号**：
- M1 项目骨架 + 配置层（Task 1-3）
- M2 模板引擎 + 结果解析器（Task 4-6）
- M3 输出写入器（Task 7）
- M4 VisionProvider 抽象 + 工厂（Task 8-9）
- M5 4 个 provider 实现（Task 10-13）
- M6 反推 API（单次）（Task 14）
- M7 批量执行器 + SSE（Task 15-16）
- M8 shot-master 集成（拆图/拼图/去白边 API）（Task 17-19）
- M9 模板/设置/文件 CRUD API（Task 20-22）
- M10 Web UI（Task 23-29）
- M11 启动脚本 + E2E smoke（Task 30-31）
- M12 收尾：UI per-image supplement 选项（Task 32）

---

## M1 · 项目骨架 + 配置层

### Task 1: 创建项目骨架文件

**Files:**
- Create: `shot-prompt-backwards/pyproject.toml`
- Create: `shot-prompt-backwards/.env.example`
- Create: `shot-prompt-backwards/.gitignore`
- Create: `shot-prompt-backwards/README.md`
- Create: `shot-prompt-backwards/app/__init__.py` (空文件)
- Create: `shot-prompt-backwards/app/api/__init__.py` (空文件)
- Create: `shot-prompt-backwards/app/providers/__init__.py` (空文件)
- Create: `shot-prompt-backwards/app/core/__init__.py` (空文件)
- Create: `shot-prompt-backwards/tests/__init__.py` (空文件)
- Create: `shot-prompt-backwards/tests/test_providers/__init__.py` (空文件)
- Create: `shot-prompt-backwards/tests/test_api/__init__.py` (空文件)

- [ ] **Step 1: 写 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "shot-prompt-backwards"
version = "0.1.0"
description = "分镜提示词反推 Web App + shot-master 整合"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "python-dotenv>=1.0",
    "Pillow>=10.0",
    "numpy>=1.24",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "google-genai>=0.3",
    "openai>=1.30",
    "anthropic>=0.30",
    "dashscope>=1.17",
    "shot-master @ file:../shot-master",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.0",
    "httpx>=0.27",
]

[project.scripts]
shot-prompt-backwards = "app.main:run"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
asyncio_mode = "auto"
```

- [ ] **Step 2: 写 .env.example**

```env
# === 默认后端 ===
DEFAULT_PROVIDER=gemini
DEFAULT_MODEL=gemini-2.5-pro

# === Gemini ===
GEMINI_API_KEY=
GEMINI_BASE_URL=

# === OpenAI 兼容（每个 endpoint 一组 key + base_url）===
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DOUBAO_API_KEY=
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
SILICONFLOW_API_KEY=
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
VLLM_API_KEY=EMPTY
VLLM_BASE_URL=http://127.0.0.1:8000/v1

# === Anthropic ===
ANTHROPIC_API_KEY=

# === Qwen-VL (DashScope) ===
DASHSCOPE_API_KEY=

# === 输出 ===
DEFAULT_OUTPUT_DIR=

# === 服务 ===
HOST=127.0.0.1
PORT=7866
```

- [ ] **Step 3: 写 .gitignore**

```gitignore
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
.cache/
.env
settings.json
logs/
output/
.venv/
node_modules/
```

- [ ] **Step 4: 写 README.md（最小可用）**

```markdown
# Shot-Prompt-Backwards

分镜提示词反推 Web App + shot-master 整合工具。

## 安装

```bash
pip install -e ../shot-master   # 先装 shot-master
pip install -e .[dev]
cp .env.example .env            # 编辑填入 API keys
```

## 启动

Windows: 双击 `run.bat`
Linux/Mac: `./run.sh`

浏览器自动打开 http://127.0.0.1:7866

## 测试

```bash
pytest -v
```

## 文档

- 需求规格：`需求.md`
- 实现计划：`docs/superpowers/plans/2026-05-13-shot-prompt-backwards.md`
```

- [ ] **Step 5: 创建所有 __init__.py 空文件**

```bash
touch app/__init__.py app/api/__init__.py app/providers/__init__.py app/core/__init__.py
touch tests/__init__.py tests/test_providers/__init__.py tests/test_api/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example .gitignore README.md app/ tests/
git commit -m "feat: scaffold shot-prompt-backwards project skeleton"
```

---

### Task 2: 实现 config.py（.env + settings.json 加载）

**Files:**
- Create: `app/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写测试 tests/test_config.py**

```python
import json
import os
from pathlib import Path
import pytest
from app.config import Config, load_config


def test_load_config_from_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEFAULT_PROVIDER=anthropic\n"
        "DEFAULT_MODEL=claude-opus-4\n"
        "GEMINI_API_KEY=g-key\n"
        "OPENAI_API_KEY=o-key\n"
        "OPENAI_BASE_URL=https://x.example/v1\n"
        "HOST=0.0.0.0\n"
        "PORT=9000\n"
    )
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.default_provider == "anthropic"
    assert cfg.default_model == "claude-opus-4"
    assert cfg.api_keys["gemini"] == "g-key"
    assert cfg.api_keys["openai"] == "o-key"
    assert cfg.base_urls["openai"] == "https://x.example/v1"
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9000


def test_settings_json_overrides_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\n")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "current_provider": "anthropic",
        "current_model": "claude-opus-4",
    }))
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.current_provider == "anthropic"
    assert cfg.current_model == "claude-opus-4"
    # default_* still from .env
    assert cfg.default_provider == "gemini"


def test_save_settings_persists_changes(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=gemini\n")
    settings_file = tmp_path / "settings.json"
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(current_provider="anthropic", current_model="claude-opus-4")
    assert settings_file.exists()
    data = json.loads(settings_file.read_text())
    assert data["current_provider"] == "anthropic"
    assert data["current_model"] == "claude-opus-4"


def test_missing_env_uses_defaults(tmp_path):
    cfg = load_config(env_path=tmp_path / "nonexistent.env",
                      settings_path=tmp_path / "settings.json")
    assert cfg.default_provider == "gemini"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 7866
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.config'`)

- [ ] **Step 3: 实现 app/config.py**

```python
"""Load configuration from .env and settings.json.

.env: 静态配置（API keys、默认值）；本进程启动时只读
settings.json: 运行时偏好（当前 provider / model / 默认输出策略）；可被 UI 改写
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values


# OpenAI 兼容 endpoints 的 key 名（在 .env 里以 {NAME}_API_KEY / {NAME}_BASE_URL 形式存在）
OPENAI_COMPAT_ENDPOINTS = [
    "openai", "deepseek", "doubao", "openrouter", "siliconflow", "vllm"
]
# 独立 SDK 后端
INDEPENDENT_PROVIDERS = ["gemini", "anthropic", "qwen"]


@dataclass
class Config:
    default_provider: str = "gemini"
    default_model: str = "gemini-2.5-pro"
    current_provider: str = "gemini"
    current_model: str = "gemini-2.5-pro"
    api_keys: dict[str, str] = field(default_factory=dict)
    base_urls: dict[str, str] = field(default_factory=dict)
    default_output_dir: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 7866
    settings_path: Optional[Path] = None
    ui: dict = field(default_factory=lambda: {"theme": "light", "preview_thumb_size": 200})

    def update_settings(self, **kwargs) -> None:
        """更新运行时设置并落盘到 settings.json"""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        if self.settings_path:
            data = {
                "current_provider": self.current_provider,
                "current_model": self.current_model,
                "ui": self.ui,
            }
            self.settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_config(env_path: Path = Path(".env"),
                settings_path: Path = Path("settings.json")) -> Config:
    env = dotenv_values(env_path) if env_path.exists() else {}

    api_keys: dict[str, str] = {}
    base_urls: dict[str, str] = {}
    for name in INDEPENDENT_PROVIDERS:
        key = env.get(f"{name.upper()}_API_KEY") or env.get(f"{name.upper()}_KEY")
        if key:
            api_keys[name] = key
        url = env.get(f"{name.upper()}_BASE_URL")
        if url:
            base_urls[name] = url
    # DashScope key 在 .env 里叫 DASHSCOPE_API_KEY；映射成 provider 名 "qwen"
    if env.get("DASHSCOPE_API_KEY"):
        api_keys["qwen"] = env["DASHSCOPE_API_KEY"]
    for name in OPENAI_COMPAT_ENDPOINTS:
        key = env.get(f"{name.upper()}_API_KEY")
        if key:
            api_keys[name] = key
        url = env.get(f"{name.upper()}_BASE_URL")
        if url:
            base_urls[name] = url

    cfg = Config(
        default_provider=env.get("DEFAULT_PROVIDER", "gemini"),
        default_model=env.get("DEFAULT_MODEL", "gemini-2.5-pro"),
        api_keys=api_keys,
        base_urls=base_urls,
        default_output_dir=env.get("DEFAULT_OUTPUT_DIR") or None,
        host=env.get("HOST", "127.0.0.1"),
        port=int(env.get("PORT", "7866")),
        settings_path=settings_path,
    )
    cfg.current_provider = cfg.default_provider
    cfg.current_model = cfg.default_model

    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
            if isinstance(data, dict):
                if "current_provider" in data:
                    cfg.current_provider = data["current_provider"]
                if "current_model" in data:
                    cfg.current_model = data["current_model"]
                if "ui" in data and isinstance(data["ui"], dict):
                    cfg.ui.update(data["ui"])
        except (json.JSONDecodeError, OSError):
            pass

    return cfg
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_config.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: config loader for .env + settings.json"
```

---

### Task 3: 实现 main.py（FastAPI 入口）

**Files:**
- Create: `app/main.py`
- Create: `tests/test_api/test_health.py`

- [ ] **Step 1: 写测试 tests/test_api/test_health.py**

```python
from fastapi.testclient import TestClient
from app.main import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "provider" in data
    assert "model" in data


def test_root_serves_index_html(tmp_path, monkeypatch):
    # 创建假 web/index.html
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><body>HI</body></html>")
    monkeypatch.chdir(tmp_path)
    # .env 不存在也能跑
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"HI" in resp.content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_health.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.main'`)

- [ ] **Step 3: 实现 app/main.py**

```python
"""FastAPI 入口：路由聚合 + 静态文件挂载 + 启动脚本入口"""
from __future__ import annotations

import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import load_config


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # 清空预览缓存（每次启动都重置）
    cache_dir = Path("app/.cache/preview")
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="Shot-Prompt-Backwards", lifespan=_lifespan)
    app.state.config = cfg

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "provider": cfg.current_provider,
            "model": cfg.current_model,
        }

    # 静态资源
    web_dir = Path("web")
    if web_dir.exists():
        if (web_dir / "index.html").exists():
            @app.get("/")
            async def root():
                return FileResponse(web_dir / "index.html")
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    # 预览缓存（拆图 tile 输出）以静态文件方式暴露
    cache_dir = Path("app/.cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/cache", StaticFiles(directory=str(cache_dir)), name="cache")

    return app


def run():
    """`shot-prompt-backwards` 命令入口（pyproject [project.scripts]）"""
    cfg = load_config()
    url = f"http://{cfg.host}:{cfg.port}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run("app.main:create_app", factory=True,
                host=cfg.host, port=cfg.port, reload=False)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_api/test_health.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 5: 手动 smoke**

Run: `python -m app.main`（按 Ctrl+C 退出）
Expected: uvicorn 启动在 127.0.0.1:7866；浏览器自动打开（无 index.html 也不报错）。

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_api/test_health.py
git commit -m "feat: FastAPI app entry with health endpoint and static mount"
```

---

## M2 · 模板引擎 + 结果解析器

### Task 4: 实现 template_engine.py（frontmatter 解析 + 渲染 + 自动推荐）

**Files:**
- Create: `app/core/template_engine.py`
- Create: `tests/test_template_engine.py`

- [ ] **Step 1: 写测试 tests/test_template_engine.py**

```python
import pytest
from pathlib import Path
from app.core.template_engine import (
    Template, TemplateVariable, load_template, list_templates,
    render_template, recommend_template,
)


SAMPLE_MD = """---
name: 四帧测试
suggest_when: image_count == 4
variables:
  - name: total_seconds
    type: int
    default: 16
    label: 总时长
    required: true
  - name: fps
    type: int
    default: 24
    label: FPS
    required: true
  - name: style_note
    type: textarea
    label: 风格备注
    optional: true
---
你是 LTX 提示词工程师。total={{total_seconds}}s, fps={{fps}}, style={{style_note}}.
"""


def test_load_template(tmp_path):
    p = tmp_path / "four_frame.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    tpl = load_template(p)
    assert tpl.id == "four_frame"
    assert tpl.name == "四帧测试"
    assert tpl.suggest_when == "image_count == 4"
    assert len(tpl.variables) == 3
    assert tpl.variables[0].name == "total_seconds"
    assert tpl.variables[0].type == "int"
    assert tpl.variables[0].default == 16
    assert tpl.variables[0].required is True
    assert tpl.variables[2].optional is True
    assert "你是 LTX 提示词工程师" in tpl.body


def test_render_template_substitutes_placeholders(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    tpl = load_template(p)
    out = render_template(tpl, {"total_seconds": 20, "fps": 30, "style_note": "墨韵"})
    assert "total=20s" in out
    assert "fps=30" in out
    assert "style=墨韵" in out


def test_render_uses_defaults_for_missing(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    tpl = load_template(p)
    out = render_template(tpl, {"style_note": "暗调"})
    assert "total=16s" in out
    assert "fps=24" in out


def test_render_raises_when_required_missing(tmp_path):
    p = tmp_path / "t.md"
    md = SAMPLE_MD.replace("default: 16\n    label: 总时长", "label: 总时长")
    p.write_text(md, encoding="utf-8")
    tpl = load_template(p)
    with pytest.raises(ValueError, match="total_seconds"):
        render_template(tpl, {"fps": 24})


def test_list_templates(tmp_path):
    (tmp_path / "a.md").write_text(SAMPLE_MD.replace("四帧测试", "A"), encoding="utf-8")
    (tmp_path / "b.md").write_text(SAMPLE_MD.replace("四帧测试", "B"), encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("nope")
    tpls = list_templates(tmp_path)
    assert {t.id for t in tpls} == {"a", "b"}


def test_recommend_template_by_image_count(tmp_path):
    t1 = SAMPLE_MD.replace("四帧测试", "三帧").replace(
        "image_count == 4", "image_count == 3"
    )
    t4 = SAMPLE_MD.replace("四帧测试", "四帧")
    tn = SAMPLE_MD.replace("四帧测试", "多帧").replace(
        "image_count == 4", "image_count >= 5"
    )
    (tmp_path / "three.md").write_text(t1, encoding="utf-8")
    (tmp_path / "four.md").write_text(t4, encoding="utf-8")
    (tmp_path / "multi.md").write_text(tn, encoding="utf-8")
    tpls = list_templates(tmp_path)
    assert recommend_template(tpls, image_count=3).id == "three"
    assert recommend_template(tpls, image_count=4).id == "four"
    assert recommend_template(tpls, image_count=7).id == "multi"


def test_recommend_returns_none_when_no_match(tmp_path):
    (tmp_path / "x.md").write_text(SAMPLE_MD.replace("四帧测试", "Only4"), encoding="utf-8")
    tpls = list_templates(tmp_path)
    assert recommend_template(tpls, image_count=99) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_template_engine.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 实现 app/core/template_engine.py**

```python
"""模板加载/渲染/推荐。

模板格式 = YAML frontmatter（--- ... ---） + 正文（jinja-like `{{var}}` 占位符）。
没引 jinja，避免大依赖；占位符替换用简单字符串替换即可。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class TemplateVariable:
    name: str
    type: str = "text"           # int / float / text / textarea / select / file_pick
    default: Any = None
    label: str = ""
    required: bool = False
    optional: bool = False
    options: list[str] = field(default_factory=list)  # for select
    placeholder: str = ""


@dataclass
class Template:
    id: str                       # 文件名去 .md 后缀
    name: str
    body: str
    path: Path
    suggest_when: str = ""        # 条件表达式（image_count, has_script 等）
    variables: list[TemplateVariable] = field(default_factory=list)


def load_template(path: Path) -> Template:
    raw = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(raw)
    if not m:
        # 无 frontmatter：当作纯正文
        return Template(id=path.stem, name=path.stem, body=raw, path=path)
    meta_yaml, body = m.group(1), m.group(2)
    meta = yaml.safe_load(meta_yaml) or {}
    variables = []
    for v in meta.get("variables", []) or []:
        variables.append(TemplateVariable(
            name=v["name"],
            type=v.get("type", "text"),
            default=v.get("default"),
            label=v.get("label", v["name"]),
            required=bool(v.get("required", False)),
            optional=bool(v.get("optional", False)),
            options=v.get("options", []) or [],
            placeholder=v.get("placeholder", ""),
        ))
    return Template(
        id=path.stem,
        name=meta.get("name", path.stem),
        body=body,
        path=path,
        suggest_when=meta.get("suggest_when", ""),
        variables=variables,
    )


def list_templates(directory: Path) -> list[Template]:
    if not directory.exists():
        return []
    return [load_template(p) for p in sorted(directory.glob("*.md"))]


def render_template(tpl: Template, values: dict[str, Any]) -> str:
    """把 {{var}} 替换为 values 中的值；缺失走 default；required 缺失则报错。"""
    resolved: dict[str, Any] = {}
    for var in tpl.variables:
        if var.name in values and values[var.name] not in (None, ""):
            resolved[var.name] = values[var.name]
        elif var.default is not None:
            resolved[var.name] = var.default
        elif var.required and not var.optional:
            raise ValueError(f"required variable missing: {var.name}")
        else:
            resolved[var.name] = ""

    def _sub(match: re.Match) -> str:
        name = match.group(1)
        return str(resolved.get(name, ""))

    return VAR_PATTERN.sub(_sub, tpl.body)


def recommend_template(templates: list[Template],
                       image_count: int,
                       has_script: bool = False) -> Optional[Template]:
    """按 suggest_when 表达式找第一个匹配的模板。

    支持的简易表达式语法：image_count == N / image_count >= N / image_count <= N /
    image_count > N / image_count < N，以及 'has_script'。
    """
    ctx = {"image_count": image_count, "has_script": has_script}
    for tpl in templates:
        if not tpl.suggest_when:
            continue
        expr = tpl.suggest_when.strip()
        try:
            # 仅允许识别变量名 + 比较符 + 数字
            if eval(expr, {"__builtins__": {}}, ctx):
                return tpl
        except Exception:
            continue
    return None
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_template_engine.py -v`
Expected: PASS（7 个测试）

- [ ] **Step 5: Commit**

```bash
git add app/core/template_engine.py tests/test_template_engine.py
git commit -m "feat: template engine with frontmatter parsing and recommendation"
```

---

### Task 5: 创建 4 套内建反推模板

**Files:**
- Create: `templates/single_frame.md`
- Create: `templates/three_frame.md`
- Create: `templates/four_frame.md`
- Create: `templates/multi_frame_adaptive.md`

- [ ] **Step 1: 写 templates/single_frame.md（单帧静态出 prompt）**

```markdown
---
name: 单帧静态
suggest_when: image_count == 1
variables:
  - {name: style_note, type: textarea, label: 风格备注, optional: true, placeholder: 例：中国水墨动画风/明清美学/翡翠蓝灰调}
  - {name: script, type: textarea, label: 剧本/台词, optional: true}
---
你是 ComfyUI 静态图生提示词专家。请为输入的单张图片生成一组中英文双版提示词，
覆盖：主体、动作、外观、环境、镜头语言、光影色彩。

【风格备注】{{style_note}}
【剧本辅助】{{script}}

请输出：
1. 中文 prompt（一段，70-120字）
2. 英文 prompt（一段，70-120字）
3. 负面提示词（标准 SDXL/Flux 负面词集合）
```

- [ ] **Step 2: 写 templates/three_frame.md（拷贝项目原模板核心）**

```markdown
---
name: 三帧首中尾
suggest_when: image_count == 3
variables:
  - {name: total_seconds, type: int, default: 8, label: 总时长(秒)}
  - {name: fps, type: int, default: 30, label: FPS}
  - {name: style_note, type: textarea, label: 风格备注, optional: true}
  - {name: script, type: textarea, label: 剧本/台词, optional: true}
---
你是 LTX-Video 2.3 三帧首中尾视频提示词工程师，为 ComfyUI 工作流
`PromptRelayEncodeTimeline + LTXVAddGuideMulti(num_guides=3)` 生成可粘贴参数。

# 输入
- 图1=首帧，图2=中帧，图3=尾帧
- 总时长 = {{total_seconds}} 秒，fps = {{fps}}
- 风格备注：{{style_note}}
- 剧本：{{script}}

# 必须输出（每字段独立代码块）
1. global_prompt（一句中文 30-60 字）
2. timeline_data（JSON，3 段）
3. local_prompts（用 ` | ` 拼接的 prompt 串）
4. segment_lengths（与 timeline 一致的整数列表）
5. max_frames（total_seconds*fps 向上取 8N+1 的最小值）
6. frame_indices（5 元组，三帧用前 3 个，余下 -1）
7. strengths（开场/收尾 1.0，中间 0.95）
8. epsilon（默认 0.1；强对比 0.001；缓变 0.7）
9. notes（每帧画面要点 + 每段对应剧情/时长）
```

- [ ] **Step 3: 写 templates/four_frame.md**

```markdown
---
name: 四帧
suggest_when: image_count == 4
variables:
  - {name: total_seconds, type: int, default: 16, label: 总时长(秒)}
  - {name: fps, type: int, default: 24, label: FPS}
  - {name: style_note, type: textarea, label: 风格备注, optional: true}
  - {name: script, type: textarea, label: 剧本/台词, optional: true}
---
你是 LTX-Video 2.3 四帧引导视频提示词工程师，为 ComfyUI 工作流
`PromptRelayEncodeTimeline + LTXVAddGuideMulti(num_guides=4)` 生成可粘贴参数。

# 输入
- 图1-图4：按时间顺序的关键帧
- 总时长 = {{total_seconds}} 秒，fps = {{fps}}
- 风格备注：{{style_note}}
- 剧本：{{script}}

# 必须输出（每字段独立代码块）
1. global_prompt（一句中文 30-60 字）
2. timeline_data（JSON，4 段）
3. local_prompts（` | ` 拼接）
4. segment_lengths（与 timeline 一致的整数列表）
5. max_frames（total_seconds*fps 向下取 8 倍数；总和等于此值）
6. frame_indices（5 元组，前 4 个为帧位置，第 5 个 -1）
7. strengths（首尾 1.0，中间 0.95）
8. epsilon
9. notes
```

- [ ] **Step 4: 写 templates/multi_frame_adaptive.md（基于现有模板压缩）**

```markdown
---
name: 多帧自适应
suggest_when: image_count >= 5
variables:
  - {name: total_seconds, type: int, default: 16, label: 总时长(秒)}
  - {name: fps, type: int, default: 24, label: FPS}
  - {name: key_frame_count, type: int, default: 5, label: 关键帧数(2-5)}
  - {name: style_note, type: textarea, label: 风格备注, optional: true}
  - {name: script, type: textarea, label: 剧本/台词, optional: true}
---
你是 LTX-Video 2.3 多帧引导视频提示词工程师。

# 输入
- 1~5 张关键帧（按时间序）
- 总时长 = {{total_seconds}} 秒，fps = {{fps}}，关键帧数 = {{key_frame_count}}
- 风格备注：{{style_note}}
- 剧本：{{script}}

# 硬约束
- max_frames 必须能被 8 整除（不大于 total_seconds * fps）
- frame_idx 必须是 8 的倍数，frame_idx_1 = 0，最后帧 ≤ max_frames - 8
- segment_lengths 各段为 8 的倍数，最后段为 8K+1
- 引导帧 ≤ 5（不足 5 个槽补 -1）

# 必须输出（每字段独立代码块）
1. global_prompt
2. timeline_data（JSON）
3. local_prompts
4. segment_lengths
5. max_frames
6. frame_indices（5 元组）
7. strengths
8. epsilon
9. notes
```

- [ ] **Step 5: Commit**

```bash
git add templates/
git commit -m "feat: 4 built-in inference templates (single/three/four/multi-frame)"
```

---

### Task 6: 实现 result_parser.py（从 vision 原始文本提取字段）

**Files:**
- Create: `app/core/result_parser.py`
- Create: `tests/test_result_parser.py`

- [ ] **Step 1: 写测试 tests/test_result_parser.py**

```python
from app.core.result_parser import parse_result, ParsedResult


RAW = """这是 AI 输出的开场说明。

## 1. global_prompt
```
夕阳下她转身奔跑，长发被风扬起，眼神坚定。
```

## 2. timeline_data
```json
{
  "segments": [
    { "prompt": "画面描述：黄昏沙地，少女转身。", "length": 96, "color": "#4f8edc" },
    { "prompt": "画面发展：风扬起长发。", "length": 96, "color": "#e07b3a" }
  ]
}
```

## 3. local_prompts
```
画面描述：黄昏沙地，少女转身。 | 画面发展：风扬起长发。
```

## 4. segment_lengths
```
96, 96
```

## 5. max_frames
```
192
```

## 6. frame_indices
```
frame_idx_1 = 0
frame_idx_2 = 96
frame_idx_3 = -1
frame_idx_4 = -1
frame_idx_5 = -1
```

## 7. strengths
```
strength_1 = 1.0
strength_2 = 1.0
strength_3 = 0.0
strength_4 = 0.0
strength_5 = 0.0
```

## 8. epsilon
```
0.1
```

## 9. notes
- frame_idx_1 黄昏沙地少女转身
- frame_idx_2 风扬起长发
"""


def test_parse_basic_fields():
    r = parse_result(RAW)
    assert isinstance(r, ParsedResult)
    assert "夕阳下她转身奔跑" in r.global_prompt
    assert "segments" in r.timeline_data
    assert "黄昏沙地" in r.local_prompts
    assert r.segment_lengths == [96, 96]
    assert r.max_frames == 192
    assert r.frame_indices == [0, 96, -1, -1, -1]
    assert r.strengths == [1.0, 1.0, 0.0, 0.0, 0.0]
    assert r.epsilon == 0.1
    assert "frame_idx_1" in r.notes
    assert r.raw == RAW


def test_parse_missing_fields_yields_none():
    r = parse_result("没有任何代码块的文本")
    assert r.global_prompt == ""
    assert r.timeline_data == ""
    assert r.segment_lengths == []
    assert r.max_frames is None
    assert r.frame_indices == []
    assert r.epsilon is None


def test_parse_handles_chinese_field_labels():
    raw = """
## global_prompt
```
hi
```
"""
    r = parse_result(raw)
    assert r.global_prompt == "hi"


def test_parse_frame_indices_robust_to_missing_lines():
    raw = """
## frame_indices
```
frame_idx_1 = 0
frame_idx_2 = 48
```
"""
    r = parse_result(raw)
    # 不足 5 个，补 -1
    assert r.frame_indices == [0, 48, -1, -1, -1]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_result_parser.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/core/result_parser.py**

```python
"""从 vision 模型输出文本提取结构化字段。

策略：按 field 名匹配 markdown 标题或行首关键字，取其后的第一个 ``` 代码块。
若某字段缺失，对应属性为空（''/None/[]），不抛错——保留原文供 UI 编辑。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedResult:
    global_prompt: str = ""
    timeline_data: str = ""              # 原始 JSON 字符串
    local_prompts: str = ""
    segment_lengths: list[int] = field(default_factory=list)
    max_frames: Optional[int] = None
    frame_indices: list[int] = field(default_factory=list)
    strengths: list[float] = field(default_factory=list)
    epsilon: Optional[float] = None
    notes: str = ""
    raw: str = ""


def _extract_block(text: str, field_name: str) -> Optional[str]:
    """匹配 '## N. field_name' 或 '## field_name' 或行首 'field_name:'，
    取其后第一个 ``` 代码块的内容。"""
    pattern = re.compile(
        rf"(?:^|\n)(?:#+\s*\d*\.?\s*{re.escape(field_name)}|{re.escape(field_name)}\s*[:：])"
        rf".*?```[a-zA-Z]*\n(.*?)\n```",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _parse_int_list(s: str) -> list[int]:
    parts = re.split(r"[,，\s]+", s.strip())
    out: list[int] = []
    for p in parts:
        if p.strip():
            try:
                out.append(int(p.strip()))
            except ValueError:
                continue
    return out


def _parse_frame_indices(s: str) -> list[int]:
    """支持两种格式：纯逗号列表 / `frame_idx_1 = N` 多行。补足到 5 位。"""
    if "=" in s:
        idx_map: dict[int, int] = {}
        for line in s.splitlines():
            m = re.match(r"\s*frame_idx_(\d+)\s*=\s*(-?\d+)", line)
            if m:
                idx_map[int(m.group(1))] = int(m.group(2))
        out = [idx_map.get(i, -1) for i in range(1, 6)]
    else:
        out = _parse_int_list(s)
    while len(out) < 5:
        out.append(-1)
    return out[:5]


def _parse_strengths(s: str) -> list[float]:
    if "=" in s:
        idx_map: dict[int, float] = {}
        for line in s.splitlines():
            m = re.match(r"\s*strength_(\d+)\s*=\s*(-?\d+\.?\d*)", line)
            if m:
                idx_map[int(m.group(1))] = float(m.group(2))
        out = [idx_map.get(i, 0.0) for i in range(1, 6)]
    else:
        out = [float(x) for x in re.split(r"[,，\s]+", s.strip()) if x]
    while len(out) < 5:
        out.append(0.0)
    return out[:5]


def parse_result(text: str) -> ParsedResult:
    r = ParsedResult(raw=text)

    if (b := _extract_block(text, "global_prompt")):
        r.global_prompt = b
    if (b := _extract_block(text, "timeline_data")):
        r.timeline_data = b
    if (b := _extract_block(text, "local_prompts")):
        r.local_prompts = b
    if (b := _extract_block(text, "segment_lengths")):
        r.segment_lengths = _parse_int_list(b)
    if (b := _extract_block(text, "max_frames")):
        try:
            r.max_frames = int(b.strip())
        except ValueError:
            pass
    if (b := _extract_block(text, "frame_indices")):
        r.frame_indices = _parse_frame_indices(b)
    if (b := _extract_block(text, "strengths")):
        r.strengths = _parse_strengths(b)
    if (b := _extract_block(text, "epsilon")):
        try:
            r.epsilon = float(b.strip())
        except ValueError:
            pass
    # notes 通常是列表，不在代码块里，取标题后到结尾的所有文本
    m = re.search(r"(?:^|\n)#+\s*\d*\.?\s*notes\b(.*?)(?=\n#+\s|\Z)",
                  text, re.DOTALL | re.IGNORECASE)
    if m:
        r.notes = m.group(1).strip()

    return r
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_result_parser.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 5: Commit**

```bash
git add app/core/result_parser.py tests/test_result_parser.py
git commit -m "feat: vision result parser for LTX prompt fields"
```

---

## M3 · 输出写入器

### Task 7: 实现 output_writer.py（md + json 落盘）

**Files:**
- Create: `app/core/output_writer.py`
- Create: `tests/test_output_writer.py`

- [ ] **Step 1: 写测试 tests/test_output_writer.py**

```python
import json
from pathlib import Path
from app.core.result_parser import ParsedResult
from app.core.output_writer import write_outputs, resolve_output_dir


def _make_result() -> ParsedResult:
    r = ParsedResult(raw="raw text")
    r.global_prompt = "GP"
    r.timeline_data = '{"segments": []}'
    r.local_prompts = "LP"
    r.segment_lengths = [96, 96]
    r.max_frames = 192
    r.frame_indices = [0, 96, -1, -1, -1]
    r.strengths = [1.0, 1.0, 0.0, 0.0, 0.0]
    r.epsilon = 0.1
    r.notes = "n1"
    return r


def test_write_outputs_creates_md_and_json(tmp_path):
    result = _make_result()
    md_path, json_path = write_outputs(
        result=result,
        output_dir=tmp_path,
        base_name="EP01_S03",
        template_id="four_frame",
        provider="gemini",
        model="gemini-2.5-pro",
    )
    assert md_path.exists()
    assert json_path.exists()
    md = md_path.read_text(encoding="utf-8")
    assert "GP" in md
    assert "EP01_S03" in md
    assert "four_frame" in md
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["global_prompt"] == "GP"
    assert data["max_frames"] == 192
    assert data["frame_indices"] == [0, 96, -1, -1, -1]
    assert data["meta"]["template_id"] == "four_frame"


def test_resolve_output_dir_input_sibling(tmp_path):
    img = tmp_path / "EP01_S03.png"
    img.write_bytes(b"")
    out = resolve_output_dir(image_path=img, default_output_dir=None)
    assert out == tmp_path / "_prompts"


def test_resolve_output_dir_explicit(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"")
    out = resolve_output_dir(image_path=img, default_output_dir=str(tmp_path / "out"))
    assert out == tmp_path / "out"


def test_write_outputs_overwrite_existing(tmp_path):
    r = _make_result()
    write_outputs(result=r, output_dir=tmp_path, base_name="x",
                  template_id="t", provider="p", model="m")
    r.global_prompt = "GP2"
    md_path, _ = write_outputs(result=r, output_dir=tmp_path, base_name="x",
                               template_id="t", provider="p", model="m")
    assert "GP2" in md_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_output_writer.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/core/output_writer.py**

```python
"""把 ParsedResult 写为 md + json。

md: 给人看的，含原始 vision 输出 + 解析后的字段块；适合后续手工微调。
json: 给 ComfyUI 工作流读的，纯结构化数据。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.result_parser import ParsedResult


def resolve_output_dir(image_path: Optional[Path],
                       default_output_dir: Optional[str]) -> Path:
    """决定输出目录。
    - 优先用 default_output_dir（来自 .env 或显式参数）
    - 否则输出到 image_path 同级的 _prompts/
    """
    if default_output_dir:
        return Path(default_output_dir)
    if image_path is None:
        return Path("output")
    return image_path.parent / "_prompts"


def write_outputs(result: ParsedResult,
                  output_dir: Path,
                  base_name: str,
                  template_id: str,
                  provider: str,
                  model: str) -> tuple[Path, Path]:
    """写 base_name.md 和 base_name.json 到 output_dir。返回 (md_path, json_path)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{base_name}.md"
    json_path = output_dir / f"{base_name}.json"

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_lines = [
        f"# {base_name} · 反推提示词",
        "",
        f"- 模板：`{template_id}`",
        f"- 后端：`{provider}` / 模型：`{model}`",
        f"- 生成时间：{ts}",
        "",
        "## global_prompt",
        "```",
        result.global_prompt,
        "```",
        "",
        "## timeline_data",
        "```json",
        result.timeline_data,
        "```",
        "",
        "## local_prompts",
        "```",
        result.local_prompts,
        "```",
        "",
        "## segment_lengths",
        "```",
        ", ".join(str(x) for x in result.segment_lengths),
        "```",
        "",
        "## max_frames",
        "```",
        str(result.max_frames) if result.max_frames is not None else "",
        "```",
        "",
        "## frame_indices",
        "```",
        "\n".join(f"frame_idx_{i+1} = {v}" for i, v in enumerate(result.frame_indices)),
        "```",
        "",
        "## strengths",
        "```",
        "\n".join(f"strength_{i+1} = {v}" for i, v in enumerate(result.strengths)),
        "```",
        "",
        "## epsilon",
        "```",
        str(result.epsilon) if result.epsilon is not None else "",
        "```",
        "",
        "## notes",
        result.notes,
        "",
        "---",
        "",
        "## 原始模型输出",
        "```",
        result.raw,
        "```",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    data = {
        "global_prompt": result.global_prompt,
        "timeline_data": result.timeline_data,
        "local_prompts": result.local_prompts,
        "segment_lengths": result.segment_lengths,
        "max_frames": result.max_frames,
        "frame_indices": result.frame_indices,
        "strengths": result.strengths,
        "epsilon": result.epsilon,
        "notes": result.notes,
        "meta": {
            "base_name": base_name,
            "template_id": template_id,
            "provider": provider,
            "model": model,
            "generated_at": ts,
        },
    }
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return md_path, json_path
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_output_writer.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 5: Commit**

```bash
git add app/core/output_writer.py tests/test_output_writer.py
git commit -m "feat: write parsed results to md + json with metadata"
```

---

## M4 · VisionProvider 抽象 + 工厂

### Task 8: 实现 providers/base.py

**Files:**
- Create: `app/providers/base.py`
- Create: `tests/test_providers/test_base.py`

- [ ] **Step 1: 写测试 tests/test_providers/test_base.py**

```python
import pytest
from pathlib import Path
from app.providers.base import VisionProvider, ProviderConfig, encode_image_b64


class FakeProvider(VisionProvider):
    def generate(self, images, system_prompt, user_supplement):
        return f"len={len(images)} sp={system_prompt[:5]} us={user_supplement[:5]}"

    @classmethod
    def available_models(cls):
        return ["fake-1", "fake-2"]


def test_provider_config_dataclass():
    cfg = ProviderConfig(api_key="k", base_url="u", model="m")
    assert cfg.api_key == "k"
    assert cfg.model == "m"


def test_provider_interface(tmp_path):
    p = FakeProvider(ProviderConfig(api_key="k", base_url="", model="fake-1"))
    out = p.generate([tmp_path / "a.png"], "system hello", "user hi")
    assert "len=1" in out


def test_encode_image_b64(tmp_path):
    p = tmp_path / "x.png"
    # 1x1 透明 PNG
    p.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    ))
    s = encode_image_b64(p)
    assert s.startswith("iVBORw0KGgo") or len(s) > 20
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_providers/test_base.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/providers/base.py**

```python
"""Vision Provider 抽象接口 + 共用工具。"""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProviderConfig:
    api_key: str
    base_url: str
    model: str
    timeout: float = 60.0


class VisionProvider(ABC):
    """所有 vision 后端的统一接口。

    实现类需要在构造时接受 ProviderConfig。
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        """发送 images 给 vision 模型，返回原始文本输出。"""
        ...

    @classmethod
    @abstractmethod
    def available_models(cls) -> list[str]:
        """该 provider 支持的模型名列表（用于 UI 下拉）。"""
        ...


def encode_image_b64(path: Path) -> str:
    """读图片为 base64 字符串（不含 data URL 前缀）。"""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def mime_from_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_providers/test_base.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 5: Commit**

```bash
git add app/providers/base.py tests/test_providers/test_base.py
git commit -m "feat: VisionProvider abstract base + image encoding util"
```

---

### Task 9: 实现 providers/factory.py（注册表 + endpoint 预设）

**Files:**
- Create: `app/providers/factory.py`
- Create: `tests/test_providers/test_factory.py`

- [ ] **Step 1: 写测试 tests/test_providers/test_factory.py**

```python
import pytest
from app.providers.base import VisionProvider, ProviderConfig
from app.providers import factory
from app.config import Config


class DummyProvider(VisionProvider):
    def generate(self, images, system_prompt, user_supplement):
        return "ok"

    @classmethod
    def available_models(cls):
        return ["dummy-1"]


def test_register_and_get_provider_class():
    factory.register("dummy_test", DummyProvider)
    cls = factory.get_provider_class("dummy_test")
    assert cls is DummyProvider


def test_list_providers_includes_registered():
    factory.register("dummy_list", DummyProvider)
    names = factory.list_providers()
    assert "dummy_list" in names


def test_endpoint_presets_have_required_keys():
    presets = factory.openai_compat_presets()
    for name, info in presets.items():
        assert "base_url" in info
        assert "models" in info
        assert isinstance(info["models"], list)


def test_build_provider_with_config_picks_key():
    factory.register("dummy_build", DummyProvider)
    cfg = Config(
        api_keys={"dummy_build": "k123"},
        base_urls={"dummy_build": "https://x"},
        current_provider="dummy_build",
        current_model="dummy-1",
    )
    p = factory.build_provider(cfg, provider_name="dummy_build", model="dummy-1")
    assert isinstance(p, DummyProvider)
    assert p.config.api_key == "k123"
    assert p.config.model == "dummy-1"


def test_build_provider_raises_when_unknown():
    cfg = Config()
    with pytest.raises(KeyError, match="unknown_xxx"):
        factory.build_provider(cfg, provider_name="unknown_xxx", model="m")


def test_build_provider_raises_when_no_api_key():
    factory.register("dummy_nokey", DummyProvider)
    cfg = Config(api_keys={}, current_provider="dummy_nokey", current_model="dummy-1")
    with pytest.raises(ValueError, match="API key"):
        factory.build_provider(cfg, provider_name="dummy_nokey", model="dummy-1")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_providers/test_factory.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/providers/factory.py**

```python
"""Provider 注册表 + OpenAI 兼容 endpoint 预设。

加新厂商：
- 完全新 SDK → 新建 provider 文件，调 factory.register("name", Cls)
- OpenAI 兼容（base_url + key 即可调） → 直接往 openai_compat_presets 里加一行
"""
from __future__ import annotations

from typing import Type

from app.config import Config
from app.providers.base import VisionProvider, ProviderConfig


_REGISTRY: dict[str, Type[VisionProvider]] = {}


def register(name: str, cls: Type[VisionProvider]) -> None:
    _REGISTRY[name] = cls


def get_provider_class(name: str) -> Type[VisionProvider]:
    if name not in _REGISTRY:
        raise KeyError(name)
    return _REGISTRY[name]


def list_providers() -> list[str]:
    return sorted(_REGISTRY.keys())


def openai_compat_presets() -> dict[str, dict]:
    """OpenAI 兼容 endpoints 的预设。UI 里 'OpenAI 兼容' 选完后，
    具体 endpoint 用这里的 key 名（小写）选。"""
    return {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-vl2", "deepseek-chat"],
        },
        "doubao": {
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "models": ["doubao-vision-pro-32k", "doubao-1-5-vision-pro-32k"],
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "models": [
                "google/gemini-2.5-pro",
                "anthropic/claude-opus-4",
                "openai/gpt-4o",
            ],
        },
        "siliconflow": {
            "base_url": "https://api.siliconflow.cn/v1",
            "models": ["Qwen/Qwen2.5-VL-72B-Instruct"],
        },
        "vllm": {
            "base_url": "http://127.0.0.1:8000/v1",
            "models": [],
        },
    }


def build_provider(cfg: Config,
                   provider_name: str,
                   model: str) -> VisionProvider:
    """从 Config 装配指定 provider。

    provider_name:
      - "gemini" / "anthropic" / "qwen" → 走独立 provider 类
      - "openai" / "deepseek" / "doubao" / "openrouter" / "siliconflow" / "vllm"
        → 全部走 openai_compat 类，但 endpoint 信息从预设拿
    """
    if provider_name in openai_compat_presets():
        cls = get_provider_class("openai_compat")
        preset = openai_compat_presets()[provider_name]
        base_url = cfg.base_urls.get(provider_name) or preset["base_url"]
        api_key = cfg.api_keys.get(provider_name)
        if not api_key:
            raise ValueError(f"missing API key for {provider_name}")
        return cls(ProviderConfig(api_key=api_key, base_url=base_url, model=model))

    cls = get_provider_class(provider_name)
    api_key = cfg.api_keys.get(provider_name)
    if not api_key:
        raise ValueError(f"missing API key for {provider_name}")
    base_url = cfg.base_urls.get(provider_name, "")
    return cls(ProviderConfig(api_key=api_key, base_url=base_url, model=model))
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_providers/test_factory.py -v`
Expected: PASS（6 个测试）

- [ ] **Step 5: Commit**

```bash
git add app/providers/factory.py tests/test_providers/test_factory.py
git commit -m "feat: provider factory + openai-compat endpoint presets"
```

---

## M5 · 4 个 provider 实现

> **测试策略**：所有 provider 的网络层用 `httpx_mock` 或 `unittest.mock` 拦截。不真打 API。
> 实际连通测试在 settings 页里手动跑（M9 task 22）。

### Task 10: 实现 providers/openai_compat.py

**Files:**
- Create: `app/providers/openai_compat.py`
- Create: `tests/test_providers/test_openai_compat.py`

- [ ] **Step 1: 写测试 tests/test_providers/test_openai_compat.py**

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.providers.base import ProviderConfig
from app.providers.openai_compat import OpenAICompatProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_generate_calls_chat_completions(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="sk-test", base_url="https://x.test/v1",
                         model="gpt-4o")
    provider = OpenAICompatProvider(cfg)

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="vision output text"))]

    with patch("app.providers.openai_compat.OpenAI") as MockClient:
        client_instance = MockClient.return_value
        client_instance.chat.completions.create.return_value = fake_resp
        out = provider.generate([img], "sys-prompt", "user-supplement")

    assert out == "vision output text"
    MockClient.assert_called_once_with(api_key="sk-test", base_url="https://x.test/v1")
    call_kwargs = client_instance.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    msgs = call_kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert "sys-prompt" in msgs[0]["content"]
    user_msg = msgs[1]
    assert user_msg["role"] == "user"
    # 多模态 content 是 list，含 text + image_url
    types = [item["type"] for item in user_msg["content"]]
    assert "text" in types
    assert "image_url" in types


def test_generate_with_multiple_images(tmp_path):
    imgs = [_make_image(tmp_path / "a") for _ in range(3)]
    for d in [tmp_path / "a"]:
        d.mkdir(exist_ok=True)
    # 重新建合法路径
    imgs = []
    for i in range(3):
        p = tmp_path / f"img{i}.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        imgs.append(p)

    cfg = ProviderConfig(api_key="k", base_url="u", model="m")
    provider = OpenAICompatProvider(cfg)
    fake_resp = MagicMock(choices=[MagicMock(message=MagicMock(content="out"))])
    with patch("app.providers.openai_compat.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = fake_resp
        provider.generate(imgs, "sp", "us")
        msgs = MockClient.return_value.chat.completions.create.call_args.kwargs["messages"]
        image_items = [i for i in msgs[1]["content"] if i["type"] == "image_url"]
        assert len(image_items) == 3


def test_available_models_returns_empty_list_by_default():
    # 不硬编码具体厂商模型，让 factory 的预设负责
    assert OpenAICompatProvider.available_models() == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_providers/test_openai_compat.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/providers/openai_compat.py**

```python
"""OpenAI 兼容 vision provider。覆盖 OpenAI / DeepSeek / 豆包 / OpenRouter / vLLM 等。"""
from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from app.providers.base import VisionProvider, encode_image_b64, mime_from_suffix


class OpenAICompatProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
        content: list[dict] = []
        if user_supplement:
            content.append({"type": "text", "text": user_supplement})
        for img in images:
            mime = mime_from_suffix(img)
            b64 = encode_image_b64(img)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        resp = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            timeout=self.config.timeout,
        )
        return resp.choices[0].message.content or ""

    @classmethod
    def available_models(cls) -> list[str]:
        # 由 factory.openai_compat_presets() 提供，每个 endpoint 自己一套
        return []
```

- [ ] **Step 4: 在 providers/__init__.py 注册**

修改 `app/providers/__init__.py`：

```python
"""Auto-register all providers on import."""
from app.providers import factory
from app.providers.openai_compat import OpenAICompatProvider

factory.register("openai_compat", OpenAICompatProvider)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_providers/test_openai_compat.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/providers/openai_compat.py app/providers/__init__.py tests/test_providers/test_openai_compat.py
git commit -m "feat: OpenAI-compatible vision provider"
```

---

### Task 11: 实现 providers/gemini.py

**Files:**
- Create: `app/providers/gemini.py`
- Create: `tests/test_providers/test_gemini.py`
- Modify: `app/providers/__init__.py`

- [ ] **Step 1: 写测试 tests/test_providers/test_gemini.py**

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.providers.base import ProviderConfig
from app.providers.gemini import GeminiProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_gemini_generate(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="g-key", base_url="", model="gemini-2.5-pro")
    provider = GeminiProvider(cfg)

    fake_resp = MagicMock(text="gemini output")
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = fake_resp
        out = provider.generate([img], "sys", "user")

    assert out == "gemini output"
    mock_genai.Client.assert_called_once_with(api_key="g-key")
    call_kwargs = mock_genai.Client.return_value.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-pro"
    contents = call_kwargs["contents"]
    # contents 应该是 list，至少含一张图 + 一段文字
    assert len(contents) >= 2


def test_gemini_available_models_lists_known():
    models = GeminiProvider.available_models()
    assert any("gemini" in m.lower() for m in models)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_providers/test_gemini.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/providers/gemini.py**

```python
"""Google Gemini vision provider (google-genai SDK)."""
from __future__ import annotations

from pathlib import Path

from google import genai
from google.genai import types

from app.providers.base import VisionProvider, mime_from_suffix


class GeminiProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        client = genai.Client(api_key=self.config.api_key)

        parts: list = []
        if user_supplement:
            parts.append(user_supplement)
        for img in images:
            mime = mime_from_suffix(img)
            parts.append(types.Part.from_bytes(
                data=img.read_bytes(),
                mime_type=mime,
            ))

        resp = client.models.generate_content(
            model=self.config.model,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        return resp.text or ""

    @classmethod
    def available_models(cls) -> list[str]:
        return [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-3-pro-preview",
        ]
```

- [ ] **Step 4: 注册到 providers/__init__.py**

修改 `app/providers/__init__.py`：

```python
"""Auto-register all providers on import."""
from app.providers import factory
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.gemini import GeminiProvider

factory.register("openai_compat", OpenAICompatProvider)
factory.register("gemini", GeminiProvider)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_providers/test_gemini.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/providers/gemini.py app/providers/__init__.py tests/test_providers/test_gemini.py
git commit -m "feat: Gemini vision provider via google-genai SDK"
```

---

### Task 12: 实现 providers/anthropic.py

**Files:**
- Create: `app/providers/anthropic.py`
- Create: `tests/test_providers/test_anthropic.py`
- Modify: `app/providers/__init__.py`

- [ ] **Step 1: 写测试 tests/test_providers/test_anthropic.py**

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.providers.base import ProviderConfig
from app.providers.anthropic import AnthropicProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_anthropic_generate(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="sk-ant-x", base_url="", model="claude-opus-4")
    provider = AnthropicProvider(cfg)

    fake_text_block = MagicMock(text="claude output")
    fake_resp = MagicMock(content=[fake_text_block])

    with patch("app.providers.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = fake_resp
        out = provider.generate([img], "sys-prompt", "user-supp")

    assert out == "claude output"
    MockClient.assert_called_once_with(api_key="sk-ant-x")
    call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4"
    assert call_kwargs["system"] == "sys-prompt"
    msgs = call_kwargs["messages"]
    user_msg = msgs[0]
    types = [item["type"] for item in user_msg["content"]]
    assert "text" in types
    assert "image" in types


def test_anthropic_available_models():
    models = AnthropicProvider.available_models()
    assert any("claude" in m for m in models)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_providers/test_anthropic.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/providers/anthropic.py**

```python
"""Anthropic Claude vision provider."""
from __future__ import annotations

from pathlib import Path

from anthropic import Anthropic

from app.providers.base import VisionProvider, encode_image_b64, mime_from_suffix


class AnthropicProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        client = Anthropic(api_key=self.config.api_key)
        content: list[dict] = []
        if user_supplement:
            content.append({"type": "text", "text": user_supplement})
        for img in images:
            mime = mime_from_suffix(img)
            b64 = encode_image_b64(img)
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            })

        resp = client.messages.create(
            model=self.config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            timeout=self.config.timeout,
        )
        # Claude response: content is a list of blocks
        parts = []
        for block in resp.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "".join(parts)

    @classmethod
    def available_models(cls) -> list[str]:
        return [
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ]
```

- [ ] **Step 4: 注册**

修改 `app/providers/__init__.py`，追加：

```python
from app.providers.anthropic import AnthropicProvider
factory.register("anthropic", AnthropicProvider)
```

完整文件：

```python
"""Auto-register all providers on import."""
from app.providers import factory
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.gemini import GeminiProvider
from app.providers.anthropic import AnthropicProvider

factory.register("openai_compat", OpenAICompatProvider)
factory.register("gemini", GeminiProvider)
factory.register("anthropic", AnthropicProvider)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_providers/test_anthropic.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/providers/anthropic.py app/providers/__init__.py tests/test_providers/test_anthropic.py
git commit -m "feat: Anthropic Claude vision provider"
```

---

### Task 13: 实现 providers/qwen_vl.py

**Files:**
- Create: `app/providers/qwen_vl.py`
- Create: `tests/test_providers/test_qwen_vl.py`
- Modify: `app/providers/__init__.py`

- [ ] **Step 1: 写测试 tests/test_providers/test_qwen_vl.py**

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.providers.base import ProviderConfig
from app.providers.qwen_vl import QwenVLProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_qwen_generate(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="ds-key", base_url="", model="qwen-vl-max-latest")
    provider = QwenVLProvider(cfg)

    fake_resp = MagicMock(
        status_code=200,
        output=MagicMock(choices=[MagicMock(message=MagicMock(content=[{"text": "qwen out"}]))]),
    )
    with patch("app.providers.qwen_vl.MultiModalConversation") as MockMM:
        MockMM.call.return_value = fake_resp
        out = provider.generate([img], "sys", "user")

    assert "qwen out" in out
    call_kwargs = MockMM.call.call_args.kwargs
    assert call_kwargs["api_key"] == "ds-key"
    assert call_kwargs["model"] == "qwen-vl-max-latest"
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_qwen_available_models():
    models = QwenVLProvider.available_models()
    assert any("qwen" in m.lower() for m in models)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_providers/test_qwen_vl.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/providers/qwen_vl.py**

```python
"""阿里 Qwen-VL via DashScope SDK。"""
from __future__ import annotations

from pathlib import Path

from dashscope import MultiModalConversation

from app.providers.base import VisionProvider


class QwenVLProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        user_content: list[dict] = []
        for img in images:
            user_content.append({"image": str(img.absolute())})
        if user_supplement:
            user_content.append({"text": user_supplement})

        resp = MultiModalConversation.call(
            api_key=self.config.api_key,
            model=self.config.model,
            messages=[
                {"role": "system", "content": [{"text": system_prompt}]},
                {"role": "user", "content": user_content},
            ],
        )
        if getattr(resp, "status_code", 0) != 200:
            raise RuntimeError(f"DashScope error: {getattr(resp, 'message', resp)}")

        parts: list[str] = []
        for item in resp.output.choices[0].message.content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts)

    @classmethod
    def available_models(cls) -> list[str]:
        return [
            "qwen-vl-max-latest",
            "qwen-vl-plus-latest",
            "qwen3-vl-235b-a22b-instruct",
        ]
```

- [ ] **Step 4: 注册**

修改 `app/providers/__init__.py`：

```python
"""Auto-register all providers on import."""
from app.providers import factory
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.gemini import GeminiProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.qwen_vl import QwenVLProvider

factory.register("openai_compat", OpenAICompatProvider)
factory.register("gemini", GeminiProvider)
factory.register("anthropic", AnthropicProvider)
factory.register("qwen", QwenVLProvider)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_providers/test_qwen_vl.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/providers/qwen_vl.py app/providers/__init__.py tests/test_providers/test_qwen_vl.py
git commit -m "feat: Qwen-VL provider via DashScope SDK"
```

---

## M6 · 反推 API（单次）

### Task 14: 实现 api/inference.py 单次反推路由

**Files:**
- Create: `app/api/inference.py`
- Modify: `app/main.py`（注册路由）
- Create: `tests/test_api/test_inference.py`

- [ ] **Step 1: 写测试 tests/test_api/test_inference.py**

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import create_app


SAMPLE_TPL = """---
name: Four
suggest_when: image_count == 4
variables:
  - {name: total_seconds, type: int, default: 16, label: T}
---
You are LTX engineer. T={{total_seconds}}.
"""

FAKE_OUTPUT = """## 1. global_prompt
```
GP HERE
```
## 2. timeline_data
```json
{"segments": []}
```
## 5. max_frames
```
192
```
"""


def _setup_env(tmp_path, monkeypatch):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "four.md").write_text(SAMPLE_TPL, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
    )
    monkeypatch.chdir(tmp_path)


def test_inference_single_image_success(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    app = create_app()
    client = TestClient(app)

    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/inference", json={
            "images": [str(img)],
            "template_id": "four",
            "supplement": {"total_seconds": 20},
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["global_prompt"] == "GP HERE"
    assert data["max_frames"] == 192
    assert "md_path" in data
    assert "json_path" in data
    assert Path(data["md_path"]).exists()
    assert Path(data["json_path"]).exists()


def test_inference_template_not_found(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    img = tmp_path / "x.png"
    img.write_bytes(b"\x00")
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/inference", json={
        "images": [str(img)],
        "template_id": "nonexistent",
        "supplement": {},
    })
    assert resp.status_code == 400
    assert "template" in resp.json()["detail"].lower()


def test_inference_image_not_found(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/inference", json={
        "images": [str(tmp_path / "missing.png")],
        "template_id": "four",
        "supplement": {},
    })
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower() or "exists" in resp.json()["detail"].lower()


def test_inference_provider_override(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nGEMINI_API_KEY=k\nANTHROPIC_API_KEY=ak\n"
    )
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    app = create_app()
    client = TestClient(app)
    with patch("app.providers.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = MagicMock(
            content=[MagicMock(text=FAKE_OUTPUT)]
        )
        resp = client.post("/api/inference", json={
            "images": [str(img)],
            "template_id": "four",
            "supplement": {},
            "override": {"provider": "anthropic", "model": "claude-opus-4-7"},
        })
    assert resp.status_code == 200
    assert resp.json()["meta"]["provider"] == "anthropic"
    assert resp.json()["meta"]["model"] == "claude-opus-4-7"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_inference.py -v`
Expected: FAIL (路由不存在)

- [ ] **Step 3: 实现 app/api/inference.py**

```python
"""POST /api/inference — 单次反推"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import Config
from app.core.output_writer import resolve_output_dir, write_outputs
from app.core.result_parser import parse_result
from app.core.template_engine import list_templates, render_template
from app.providers import factory


router = APIRouter()


class Override(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


class InferenceRequest(BaseModel):
    images: list[str]
    template_id: str
    supplement: dict = {}
    override: Optional[Override] = None
    output_dir: Optional[str] = None
    base_name: Optional[str] = None


@router.post("/api/inference")
async def inference(req: InferenceRequest, request: Request):
    cfg: Config = request.app.state.config

    # 校验图片
    image_paths = [Path(p) for p in req.images]
    for p in image_paths:
        if not p.exists():
            raise HTTPException(400, f"image not found: {p}")

    # 找模板
    tpls = list_templates(Path("templates"))
    matched = [t for t in tpls if t.id == req.template_id]
    if not matched:
        raise HTTPException(400, f"template '{req.template_id}' not found")
    tpl = matched[0]

    # 渲染 system_prompt
    try:
        system_prompt = render_template(tpl, req.supplement)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 选 provider/model（override 优先）
    provider_name = (req.override and req.override.provider) or cfg.current_provider
    model = (req.override and req.override.model) or cfg.current_model

    try:
        provider = factory.build_provider(cfg, provider_name=provider_name, model=model)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"provider build failed: {e}")

    # 调用 vision
    try:
        raw = provider.generate(image_paths, system_prompt, "")
    except Exception as e:
        raise HTTPException(502, f"vision API error: {e}")

    parsed = parse_result(raw)

    # 落盘
    base_name = req.base_name or image_paths[0].stem
    if req.output_dir:
        out_dir = Path(req.output_dir)
    else:
        out_dir = resolve_output_dir(image_paths[0], cfg.default_output_dir)
    md_path, json_path = write_outputs(
        result=parsed,
        output_dir=out_dir,
        base_name=base_name,
        template_id=tpl.id,
        provider=provider_name,
        model=model,
    )

    return {
        "global_prompt": parsed.global_prompt,
        "timeline_data": parsed.timeline_data,
        "local_prompts": parsed.local_prompts,
        "segment_lengths": parsed.segment_lengths,
        "max_frames": parsed.max_frames,
        "frame_indices": parsed.frame_indices,
        "strengths": parsed.strengths,
        "epsilon": parsed.epsilon,
        "notes": parsed.notes,
        "raw": parsed.raw,
        "md_path": str(md_path),
        "json_path": str(json_path),
        "meta": {
            "template_id": tpl.id,
            "provider": provider_name,
            "model": model,
        },
    }
```

- [ ] **Step 4: 注册路由到 app/main.py**

修改 `app/main.py` 的 `create_app()`，在 health 路由之后追加：

```python
    # 业务路由
    from app.api import inference as inference_api
    app.include_router(inference_api.router)
```

并确保 `import app.providers`（触发自动注册）也在 create_app 中：

```python
def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="Shot-Prompt-Backwards", lifespan=_lifespan)
    app.state.config = cfg

    # 触发 provider 注册
    import app.providers  # noqa: F401

    @app.get("/api/health")
    async def health():
        ...
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_inference.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/inference.py app/main.py tests/test_api/test_inference.py
git commit -m "feat: POST /api/inference for single-shot prompt reverse engineering"
```

---

## M7 · 批量执行器 + SSE

### Task 15: 实现 core/task_runner.py

**Files:**
- Create: `app/core/task_runner.py`
- Create: `tests/test_task_runner.py`

- [ ] **Step 1: 写测试 tests/test_task_runner.py**

```python
import asyncio
import pytest
from app.core.task_runner import TaskRunner, TaskItem, TaskEvent


def _make_items(n):
    return [TaskItem(idx=i, payload={"i": i}) for i in range(n)]


@pytest.mark.asyncio
async def test_runner_executes_all_items_serially():
    items = _make_items(3)
    order = []

    async def worker(item):
        order.append(item.idx)
        return {"ok": True, "i": item.payload["i"]}

    runner = TaskRunner(items=items, worker=worker)
    events = []
    async for ev in runner.stream():
        events.append(ev)

    assert order == [0, 1, 2]
    types = [e.type for e in events]
    assert types.count("progress") == 3
    assert types.count("item_done") == 3
    assert types[-1] == "complete"
    complete = events[-1]
    assert complete.payload["ok"] == 3
    assert complete.payload["failed"] == 0


@pytest.mark.asyncio
async def test_runner_continues_on_item_failure():
    items = _make_items(3)

    async def worker(item):
        if item.idx == 1:
            raise RuntimeError("boom")
        return {"ok": True}

    runner = TaskRunner(items=items, worker=worker)
    events = []
    async for ev in runner.stream():
        events.append(ev)

    item_dones = [e for e in events if e.type == "item_done"]
    assert len(item_dones) == 3
    assert item_dones[1].payload["status"] == "failed"
    assert "boom" in item_dones[1].payload["error"]
    assert item_dones[0].payload["status"] == "ok"
    assert item_dones[2].payload["status"] == "ok"
    complete = events[-1]
    assert complete.payload["ok"] == 2
    assert complete.payload["failed"] == 1


@pytest.mark.asyncio
async def test_runner_emits_progress_before_each_item():
    items = _make_items(2)

    async def worker(item):
        return {"ok": True}

    runner = TaskRunner(items=items, worker=worker)
    events = []
    async for ev in runner.stream():
        events.append(ev)

    # 期望顺序：progress(0) → item_done(0) → progress(1) → item_done(1) → complete
    assert [e.type for e in events] == ["progress", "item_done", "progress", "item_done", "complete"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_task_runner.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 app/core/task_runner.py**

```python
"""串行批量执行器 + 事件流。

为 API 层（batch.py）提供 async iterator，每个事件就是 SSE 一行。
失败不中断后续；item_done.status='failed' 时携带 error。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, AsyncIterator


@dataclass
class TaskItem:
    idx: int
    payload: dict
    base_name: str = ""


@dataclass
class TaskEvent:
    type: str            # "progress" | "item_done" | "complete"
    payload: dict


class TaskRunner:
    def __init__(self,
                 items: list[TaskItem],
                 worker: Callable[[TaskItem], Awaitable[dict]]):
        self.items = items
        self.worker = worker

    async def stream(self) -> AsyncIterator[TaskEvent]:
        ok = 0
        failed = 0
        total = len(self.items)
        for item in self.items:
            yield TaskEvent(type="progress", payload={
                "idx": item.idx, "total": total, "base_name": item.base_name,
                "status": "running",
            })
            try:
                result = await self.worker(item)
                ok += 1
                yield TaskEvent(type="item_done", payload={
                    "idx": item.idx, "total": total, "base_name": item.base_name,
                    "status": "ok", "result": result,
                })
            except Exception as e:
                failed += 1
                yield TaskEvent(type="item_done", payload={
                    "idx": item.idx, "total": total, "base_name": item.base_name,
                    "status": "failed", "error": str(e),
                })
        yield TaskEvent(type="complete", payload={"ok": ok, "failed": failed, "total": total})
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_task_runner.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 5: Commit**

```bash
git add app/core/task_runner.py tests/test_task_runner.py
git commit -m "feat: serial task runner with event stream"
```

---

### Task 16: 实现 api/batch.py（POST + SSE 流）

**Files:**
- Create: `app/api/batch.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_batch.py`

- [ ] **Step 1: 写测试 tests/test_api/test_batch.py**

```python
import json
import re
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import create_app


SAMPLE_TPL = """---
name: Single
suggest_when: image_count == 1
variables: []
---
You are an image describer.
"""

FAKE_OUTPUT = """## 1. global_prompt
```
GP
```
"""


def _setup(tmp_path, monkeypatch, n_images=3):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "single.md").write_text(SAMPLE_TPL, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
    )
    folder = tmp_path / "imgs"
    folder.mkdir()
    for i in range(n_images):
        (folder / f"ep01_s{i:02d}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    monkeypatch.chdir(tmp_path)
    return folder


def test_batch_creates_task_and_streams_events(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch, n_images=2)
    app = create_app()
    client = TestClient(app)

    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/batch", json={
            "folder": str(folder),
            "template_id": "single",
            "supplement": {},
        })
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]
        assert task_id

        # 读 SSE
        with client.stream("GET", f"/api/batch/{task_id}/stream") as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")

    # body 是 SSE 格式： "event: progress\ndata: {...}\n\n..."
    events = re.findall(r"event:\s*(\S+)\s*\ndata:\s*({.*?})\s*\n\n", body)
    assert len(events) >= 4   # 2 progress + 2 item_done + 1 complete
    types = [e[0] for e in events]
    assert types.count("progress") == 2
    assert types.count("item_done") == 2
    assert "complete" in types
    last = json.loads(events[-1][1])
    assert last["ok"] == 2
    assert last["failed"] == 0


def test_batch_invalid_folder(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/batch", json={
        "folder": str(tmp_path / "no_such_folder"),
        "template_id": "single",
        "supplement": {},
    })
    assert resp.status_code == 400


def test_batch_per_image_supplement(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch, n_images=2)
    # 为 ep01_s00.png 配一份同名 .md（作为剧本）
    (folder / "ep01_s00.md").write_text("这是 ep01_s00 的剧本", encoding="utf-8")
    # 为 ep01_s01.png 配一份同名 .json
    (folder / "ep01_s01.json").write_text('{"style_note": "暗调"}', encoding="utf-8")

    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/batch", json={
            "folder": str(folder),
            "template_id": "single",
            "supplement": {},
            "per_image_supplement": True,
        })
        task_id = resp.json()["task_id"]
        with client.stream("GET", f"/api/batch/{task_id}/stream") as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")
    # 验证 2 张都成功
    import re as _re, json as _json
    events = _re.findall(r"event:\s*(\S+)\s*\ndata:\s*({.*?})\s*\n\n", body)
    last = _json.loads(events[-1][1])
    assert last["ok"] == 2


def test_batch_skips_existing_outputs(tmp_path, monkeypatch):
    folder = _setup(tmp_path, monkeypatch, n_images=2)
    out = folder / "_prompts"
    out.mkdir()
    # 让 ep01_s00.md 已经存在
    (out / "ep01_s00.md").write_text("preexisting", encoding="utf-8")
    (out / "ep01_s00.json").write_text("{}", encoding="utf-8")

    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        resp = client.post("/api/batch", json={
            "folder": str(folder),
            "template_id": "single",
            "supplement": {},
            "skip_existing": True,
        })
        task_id = resp.json()["task_id"]
        with client.stream("GET", f"/api/batch/{task_id}/stream") as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")

    events = re.findall(r"event:\s*(\S+)\s*\ndata:\s*({.*?})\s*\n\n", body)
    # 应该有 1 个被 skip，1 个被处理
    item_dones = [json.loads(e[1]) for e in events if e[0] == "item_done"]
    statuses = [d["status"] for d in item_dones]
    assert "skipped" in statuses
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_batch.py -v`
Expected: FAIL (路由不存在)

- [ ] **Step 3: 实现 app/api/batch.py**

```python
"""POST /api/batch — 创建批量任务；GET /api/batch/{id}/stream — SSE 进度流"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import Config
from app.core.output_writer import resolve_output_dir, write_outputs
from app.core.result_parser import parse_result
from app.core.task_runner import TaskItem, TaskRunner
from app.core.template_engine import list_templates, render_template
from app.providers import factory


router = APIRouter()


class BatchRequest(BaseModel):
    folder: str
    template_id: str
    supplement: dict = {}                  # 默认复用同一份
    per_image_supplement: bool = False     # True → 优先查找与图片同名的 .md/.json/.txt
    output_dir: Optional[str] = None
    skip_existing: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None


def _per_image_supplement(img: Path, base: dict) -> dict:
    """寻找与图片同名的 .json / .md / .txt 注入 supplement。
    .json: 整体 merge 进 supplement
    .md/.txt: 内容塞进 supplement['script']（如果 base 已有不覆盖）
    """
    result = dict(base)
    json_p = img.with_suffix(".json")
    if json_p.exists():
        try:
            data = json.loads(json_p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    result.setdefault(k, v)
        except Exception:
            pass
    for ext in (".md", ".txt"):
        p = img.with_suffix(ext)
        if p.exists() and not result.get("script"):
            result["script"] = p.read_text(encoding="utf-8")
            break
    return result


@dataclass
class _PendingTask:
    request: BatchRequest
    cfg: Config


_pending: dict[str, _PendingTask] = {}


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)


@router.post("/api/batch")
async def create_batch(req: BatchRequest, request: Request):
    folder = Path(req.folder)
    if not folder.is_dir():
        raise HTTPException(400, f"folder not found: {folder}")
    tpls = [t for t in list_templates(Path("templates")) if t.id == req.template_id]
    if not tpls:
        raise HTTPException(400, f"template '{req.template_id}' not found")

    task_id = uuid.uuid4().hex
    _pending[task_id] = _PendingTask(request=req, cfg=request.app.state.config)
    return {"task_id": task_id}


@router.get("/api/batch/{task_id}/stream")
async def stream_batch(task_id: str):
    if task_id not in _pending:
        raise HTTPException(404, "task not found")
    task = _pending.pop(task_id)
    req = task.request
    cfg = task.cfg

    folder = Path(req.folder)
    images = _list_images(folder)
    tpl = [t for t in list_templates(Path("templates")) if t.id == req.template_id][0]
    out_dir = Path(req.output_dir) if req.output_dir else resolve_output_dir(images[0] if images else None, cfg.default_output_dir)

    provider_name = req.provider or cfg.current_provider
    model = req.model or cfg.current_model

    items = [TaskItem(idx=i, payload={"image": img}, base_name=img.stem)
             for i, img in enumerate(images)]

    async def worker(item: TaskItem) -> dict:
        img: Path = item.payload["image"]
        if req.skip_existing and (out_dir / f"{img.stem}.md").exists() and (out_dir / f"{img.stem}.json").exists():
            return {"status": "skipped", "md_path": str(out_dir / f"{img.stem}.md"),
                    "json_path": str(out_dir / f"{img.stem}.json")}
        effective_supp = _per_image_supplement(img, req.supplement) if req.per_image_supplement else req.supplement
        try:
            system_prompt = render_template(tpl, effective_supp)
        except ValueError as e:
            raise RuntimeError(f"template render: {e}")
        provider = factory.build_provider(cfg, provider_name=provider_name, model=model)
        raw = provider.generate([img], system_prompt, "")
        parsed = parse_result(raw)
        md_path, json_path = write_outputs(
            result=parsed, output_dir=out_dir,
            base_name=img.stem, template_id=tpl.id,
            provider=provider_name, model=model,
        )
        return {"md_path": str(md_path), "json_path": str(json_path),
                "global_prompt": parsed.global_prompt}

    runner = TaskRunner(items=items, worker=worker)

    async def event_gen():
        async for ev in runner.stream():
            # SSE 协议: event: <type>\ndata: <json>\n\n
            payload = json.dumps(ev.payload, ensure_ascii=False)
            yield f"event: {ev.type}\ndata: {payload}\n\n"

    # 注：worker 里如果遇到 skip，会把 result 包装。但 runner 把它当 "ok" 算成功。
    # 我们用一个小包装把 result.status=='skipped' 的 item_done 二次改写。
    async def event_gen_patched():
        async for ev in runner.stream():
            if ev.type == "item_done" and ev.payload.get("status") == "ok":
                inner = ev.payload.get("result", {})
                if isinstance(inner, dict) and inner.get("status") == "skipped":
                    ev.payload["status"] = "skipped"
            payload = json.dumps(ev.payload, ensure_ascii=False)
            yield f"event: {ev.type}\ndata: {payload}\n\n"

    return StreamingResponse(event_gen_patched(), media_type="text/event-stream")
```

- [ ] **Step 4: 注册路由到 app/main.py**

修改 `app/main.py` `create_app()` 路由聚合区：

```python
    from app.api import inference as inference_api
    from app.api import batch as batch_api
    app.include_router(inference_api.router)
    app.include_router(batch_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_batch.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/batch.py app/main.py tests/test_api/test_batch.py
git commit -m "feat: batch inference API with SSE progress stream"
```

---

## M8 · shot-master 集成（拆图 / 拼图 / 去白边）

> **前提**：`pyproject.toml` 已经把 shot-master 加为本地依赖（Task 1 已写）。本节直接 import。

### Task 17: 实现 api/grid_split.py（拆图预览 + 拆图落盘）

**Files:**
- Create: `app/api/grid_split.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_grid_split.py`

> shot-master API 已确认：
> `shot_master.core.specs.GridSpec(src_rows, src_cols, sub_rows, sub_cols, margins=Margins(...), gap=0, target_aspect=AspectRatio.auto())`
> `shot_master.core.splitter.split_image(src: PIL.Image, spec: GridSpec) -> list[PIL.Image]`
> `shot_master.core.saver.save_image(img, path, output_format, bg=(255,255,255))`

- [ ] **Step 1: 写测试 tests/test_api/test_grid_split.py**

```python
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _make_grid(tmp_path, w=400, h=400, color=(200, 30, 30)) -> Path:
    img = Image.new("RGB", (w, h), color)
    p = tmp_path / "grid.png"
    img.save(p)
    return p


def test_preview_returns_tile_urls(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    img = _make_grid(tmp_path)

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/preview", json={
        "image_path": str(img),
        "src_rows": 2, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "tiles" in data
    assert len(data["tiles"]) == 4
    for t in data["tiles"]:
        assert t.startswith("/cache/preview/")


def test_preview_invalid_grid(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    img = _make_grid(tmp_path)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/preview", json={
        "image_path": str(img),
        "src_rows": 3, "src_cols": 3,
        "sub_rows": 2, "sub_cols": 2,  # 3 不能整除 2
    })
    assert resp.status_code == 400


def test_split_saves_files_to_output_dir(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    img = _make_grid(tmp_path, w=400, h=400)
    out = tmp_path / "split_out"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/split", json={
        "image_path": str(img),
        "output_dir": str(out),
        "src_rows": 2, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1,
        "output_format": "PNG",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["files"]) == 4
    for f in data["files"]:
        assert Path(f).exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_grid_split.py -v`
Expected: FAIL (路由不存在)

- [ ] **Step 3: 实现 app/api/grid_split.py**

```python
"""POST /api/grid/preview  → 临时拆图（用于反推前的人工确认）
POST /api/grid/split    → 拆图落盘到指定目录
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image

from shot_master.core.specs import GridSpec, Margins, AspectRatio
from shot_master.core.splitter import split_image
from shot_master.core.saver import save_image
from shot_master.core.exceptions import (
    SplitGridError, MarginsTooLargeError, CellTooSmallError, AspectCropError,
)


router = APIRouter()
PREVIEW_DIR = Path("app/.cache/preview")


class GridPreviewRequest(BaseModel):
    image_path: str
    src_rows: int
    src_cols: int
    sub_rows: int = 1
    sub_cols: int = 1
    margin_top: int = 0
    margin_right: int = 0
    margin_bottom: int = 0
    margin_left: int = 0
    gap: int = 0


class GridSplitRequest(GridPreviewRequest):
    output_dir: str
    output_format: str = "PNG"   # PNG / JPG
    name_prefix: str = ""        # 默认 = 输入图 stem


def _spec_from_req(req: GridPreviewRequest) -> GridSpec:
    return GridSpec(
        src_rows=req.src_rows,
        src_cols=req.src_cols,
        sub_rows=req.sub_rows,
        sub_cols=req.sub_cols,
        margins=Margins(top=req.margin_top, right=req.margin_right,
                        bottom=req.margin_bottom, left=req.margin_left),
        gap=req.gap,
        target_aspect=AspectRatio.auto(),
    )


def _load_src(path_str: str) -> Image.Image:
    p = Path(path_str)
    if not p.exists():
        raise HTTPException(400, f"image not found: {p}")
    return Image.open(p)


@router.post("/api/grid/preview")
async def preview(req: GridPreviewRequest):
    src = _load_src(req.image_path)
    spec = _spec_from_req(req)
    try:
        tiles = split_image(src, spec)
    except (SplitGridError, MarginsTooLargeError, CellTooSmallError, AspectCropError) as e:
        raise HTTPException(400, str(e))

    # 缓存目录：基于 image_path + spec hash
    key_src = f"{req.image_path}|{spec.src_rows}x{spec.src_cols}|{spec.sub_rows}x{spec.sub_cols}|{spec.margins}|{spec.gap}"
    hsh = hashlib.md5(key_src.encode("utf-8")).hexdigest()[:12]
    out_dir = PREVIEW_DIR / hsh
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清空旧 tile（避免上次 N 张大、本次 N 张小残留）
    for old in out_dir.glob("tile_*.png"):
        old.unlink()

    urls: list[str] = []
    for i, tile in enumerate(tiles):
        fname = f"tile_{i}.png"
        save_image(tile, out_dir / fname, "PNG")
        urls.append(f"/cache/preview/{hsh}/{fname}")
    return {"tiles": urls, "cache_key": hsh}


@router.post("/api/grid/split")
async def split(req: GridSplitRequest):
    src_path = Path(req.image_path)
    src = _load_src(req.image_path)
    spec = _spec_from_req(req)
    try:
        tiles = split_image(src, spec)
    except (SplitGridError, MarginsTooLargeError, CellTooSmallError, AspectCropError) as e:
        raise HTTPException(400, str(e))

    out_dir = Path(req.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = req.name_prefix or src_path.stem
    fmt = req.output_format.upper()
    ext = ".png" if fmt == "PNG" else ".jpg"
    saved: list[str] = []
    for i, tile in enumerate(tiles):
        out_path = out_dir / f"{prefix}_{i+1}{ext}"
        save_image(tile, out_path, fmt)
        saved.append(str(out_path))
    return {"files": saved}
```

- [ ] **Step 4: 注册路由到 app/main.py**

```python
    from app.api import grid_split as grid_split_api
    app.include_router(grid_split_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_grid_split.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/grid_split.py app/main.py tests/test_api/test_grid_split.py
git commit -m "feat: grid split API (preview + persist) reusing shot-master"
```

---

### Task 18: 实现 api/grid_combine.py（拼图）

**Files:**
- Create: `app/api/grid_combine.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_grid_combine.py`

- [ ] **Step 1: 写测试 tests/test_api/test_grid_combine.py**

```python
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _make_imgs(tmp_path, n, w=100, h=100) -> list[Path]:
    paths = []
    for i in range(n):
        img = Image.new("RGB", (w, h), (i * 50 % 256, 100, 100))
        p = tmp_path / f"img{i}.png"
        img.save(p)
        paths.append(p)
    return paths


def test_combine_2x2(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    imgs = _make_imgs(tmp_path, 4)
    out = tmp_path / "out.png"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/combine", json={
        "images": [str(p) for p in imgs],
        "output_path": str(out),
        "target_rows": 2, "target_cols": 2,
        "gap": 4,
        "output_format": "PNG",
    })
    assert resp.status_code == 200
    assert out.exists()
    result = Image.open(out)
    # 2x2 with gap=4: width ≈ 2*100 + 1*4 = 204
    assert result.width == 204
    assert result.height == 204


def test_combine_count_mismatch(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    imgs = _make_imgs(tmp_path, 3)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/grid/combine", json={
        "images": [str(p) for p in imgs],
        "output_path": str(tmp_path / "out.png"),
        "target_rows": 2, "target_cols": 2,
        "gap": 0,
    })
    assert resp.status_code == 400
    assert "expected" in resp.json()["detail"].lower() or "count" in resp.json()["detail"].lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_grid_combine.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 app/api/grid_combine.py**

```python
"""POST /api/grid/combine — 多张图按 R×C 网格合并"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image

from shot_master.core.specs import CombineSpec, AspectRatio, ScaleMode
from shot_master.core.combiner import combine_images
from shot_master.core.saver import save_image
from shot_master.core.exceptions import CombineCountError


router = APIRouter()


class GridCombineRequest(BaseModel):
    images: list[str]
    output_path: str
    target_rows: int
    target_cols: int
    gap: int = 0
    scale_mode: str = "letterbox"      # letterbox / crop / stretch
    target_aspect_w: int = 0
    target_aspect_h: int = 0
    bg_r: int = 255
    bg_g: int = 255
    bg_b: int = 255
    bg_a: int = 255
    output_format: str = "PNG"


@router.post("/api/grid/combine")
async def combine(req: GridCombineRequest):
    imgs: list[Image.Image] = []
    for s in req.images:
        p = Path(s)
        if not p.exists():
            raise HTTPException(400, f"image not found: {p}")
        imgs.append(Image.open(p))

    scale = {
        "letterbox": ScaleMode.LETTERBOX,
        "crop": ScaleMode.CROP,
        "stretch": ScaleMode.STRETCH,
    }.get(req.scale_mode, ScaleMode.LETTERBOX)

    aspect = AspectRatio(req.target_aspect_w, req.target_aspect_h)
    spec = CombineSpec(
        target_rows=req.target_rows,
        target_cols=req.target_cols,
        gap=req.gap,
        target_aspect=aspect,
        scale_mode=scale,
    )
    bg = (req.bg_r, req.bg_g, req.bg_b, req.bg_a)
    try:
        merged = combine_images(imgs, spec, bg)
    except CombineCountError as e:
        raise HTTPException(400, str(e))

    out_path = Path(req.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_image(merged, out_path, req.output_format, bg=(req.bg_r, req.bg_g, req.bg_b))
    return {"output_path": str(out_path),
            "size": [merged.width, merged.height]}
```

- [ ] **Step 4: 注册路由到 app/main.py**

```python
    from app.api import grid_combine as grid_combine_api
    app.include_router(grid_combine_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_grid_combine.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/grid_combine.py app/main.py tests/test_api/test_grid_combine.py
git commit -m "feat: grid combine API reusing shot-master combiner"
```

---

### Task 19: 实现 api/border_trim.py（去白边）

**Files:**
- Create: `app/api/border_trim.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_border_trim.py`

- [ ] **Step 1: 写测试 tests/test_api/test_border_trim.py**

```python
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _img_with_white_border(tmp_path, content_w=80, content_h=80, border=20) -> Path:
    total_w = content_w + 2 * border
    total_h = content_h + 2 * border
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    inner = Image.new("RGB", (content_w, content_h), (50, 50, 200))
    canvas.paste(inner, (border, border))
    p = tmp_path / "bordered.png"
    canvas.save(p)
    return p


def test_trim_single_image(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    src = _img_with_white_border(tmp_path)
    out = tmp_path / "trimmed.png"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/border/trim", json={
        "image_path": str(src),
        "output_path": str(out),
        "threshold": 240,
    })
    assert resp.status_code == 200
    assert out.exists()
    trimmed = Image.open(out)
    assert trimmed.width <= 90  # 80~90 都可接受
    assert trimmed.height <= 90


def test_trim_batch(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "in"
    folder.mkdir()
    for i in range(3):
        canvas = Image.new("RGB", (120, 120), (255, 255, 255))
        canvas.paste(Image.new("RGB", (80, 80), (i * 50 % 256, 100, 100)), (20, 20))
        canvas.save(folder / f"img{i}.png")
    out_dir = tmp_path / "out"

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/border/trim_batch", json={
        "folder": str(folder),
        "output_dir": str(out_dir),
        "threshold": 240,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["files"]) == 3
    for f in data["files"]:
        assert Path(f).exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_border_trim.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 app/api/border_trim.py**

```python
"""POST /api/border/trim     — 单图去白边
POST /api/border/trim_batch — 批量去白边
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image

from shot_master.core.aspect_ops import trim_white_edges
from shot_master.core.saver import save_image


router = APIRouter()


class TrimRequest(BaseModel):
    image_path: str
    output_path: str
    threshold: int = 240
    max_iter: int = 5
    output_format: str = "PNG"


class TrimBatchRequest(BaseModel):
    folder: str
    output_dir: str
    threshold: int = 240
    max_iter: int = 5
    output_format: str = "PNG"
    name_suffix: str = ""           # "" → 覆盖式同名；"_trim" → 加后缀


@router.post("/api/border/trim")
async def trim(req: TrimRequest):
    src = Path(req.image_path)
    if not src.exists():
        raise HTTPException(400, f"image not found: {src}")
    img = Image.open(src)
    trimmed = trim_white_edges(img, threshold=req.threshold, max_iter=req.max_iter)
    out = Path(req.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_image(trimmed, out, req.output_format)
    return {"output_path": str(out),
            "size": [trimmed.width, trimmed.height]}


SUPPORTED = {".png", ".jpg", ".jpeg", ".webp"}


@router.post("/api/border/trim_batch")
async def trim_batch(req: TrimBatchRequest):
    folder = Path(req.folder)
    if not folder.is_dir():
        raise HTTPException(400, f"folder not found: {folder}")
    out_dir = Path(req.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in SUPPORTED:
            continue
        img = Image.open(p)
        trimmed = trim_white_edges(img, threshold=req.threshold, max_iter=req.max_iter)
        name = f"{p.stem}{req.name_suffix}.png" if req.output_format.upper() == "PNG" else f"{p.stem}{req.name_suffix}.jpg"
        out = out_dir / name
        save_image(trimmed, out, req.output_format)
        saved.append(str(out))
    return {"files": saved}
```

- [ ] **Step 4: 注册路由**

```python
    from app.api import border_trim as border_trim_api
    app.include_router(border_trim_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_border_trim.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/border_trim.py app/main.py tests/test_api/test_border_trim.py
git commit -m "feat: border trim API (single + batch) reusing shot-master"
```

---

## M9 · 模板 / 设置 / 文件 CRUD API

### Task 20: 实现 api/templates.py（模板 CRUD）

**Files:**
- Create: `app/api/templates.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_templates.py`

- [ ] **Step 1: 写测试 tests/test_api/test_templates.py**

```python
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


SAMPLE = """---
name: T1
suggest_when: image_count == 1
variables: []
---
body line
"""


def _setup(tmp_path, monkeypatch):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "t1.md").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)


def test_list_templates(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "t1"
    assert data[0]["name"] == "T1"


def test_get_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/templates/t1")
    assert resp.status_code == 200
    data = resp.json()
    assert "body line" in data["body"]
    assert data["suggest_when"] == "image_count == 1"


def test_recommend_template_endpoint(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/templates/recommend?image_count=1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "t1"


def test_create_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/templates", json={
        "id": "new1",
        "raw_markdown": "---\nname: New\nvariables: []\n---\nhello",
    })
    assert resp.status_code == 200
    assert (tmp_path / "templates" / "new1.md").exists()


def test_update_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.put("/api/templates/t1", json={
        "raw_markdown": "---\nname: T1Modified\nvariables: []\n---\nnew body"
    })
    assert resp.status_code == 200
    assert "T1Modified" in (tmp_path / "templates" / "t1.md").read_text(encoding="utf-8")


def test_delete_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.delete("/api/templates/t1")
    assert resp.status_code == 200
    assert not (tmp_path / "templates" / "t1.md").exists()


def test_create_conflict(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/templates", json={
        "id": "t1",
        "raw_markdown": "---\nname: x\n---\n",
    })
    assert resp.status_code == 409
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_templates.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 app/api/templates.py**

```python
"""模板 CRUD：列表 / 详情 / 创建 / 更新 / 删除 / 推荐"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.template_engine import list_templates, load_template, recommend_template


router = APIRouter()
TEMPLATES_DIR = Path("templates")
ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


class CreateRequest(BaseModel):
    id: str
    raw_markdown: str


class UpdateRequest(BaseModel):
    raw_markdown: str


def _template_to_dict(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "body": t.body,
        "suggest_when": t.suggest_when,
        "variables": [
            {
                "name": v.name, "type": v.type, "default": v.default,
                "label": v.label, "required": v.required, "optional": v.optional,
                "options": v.options, "placeholder": v.placeholder,
            }
            for v in t.variables
        ],
        "raw_markdown": t.path.read_text(encoding="utf-8"),
    }


@router.get("/api/templates")
async def list_all():
    return [_template_to_dict(t) for t in list_templates(TEMPLATES_DIR)]


@router.get("/api/templates/recommend")
async def recommend(image_count: int = 1, has_script: bool = False):
    tpls = list_templates(TEMPLATES_DIR)
    matched = recommend_template(tpls, image_count=image_count, has_script=has_script)
    if not matched:
        return {"id": None}
    return _template_to_dict(matched)


@router.get("/api/templates/{tpl_id}")
async def get_one(tpl_id: str):
    p = TEMPLATES_DIR / f"{tpl_id}.md"
    if not p.exists():
        raise HTTPException(404, f"template '{tpl_id}' not found")
    return _template_to_dict(load_template(p))


@router.post("/api/templates")
async def create(req: CreateRequest):
    if not ID_RE.match(req.id):
        raise HTTPException(400, "id may only contain a-z A-Z 0-9 _ -")
    p = TEMPLATES_DIR / f"{req.id}.md"
    if p.exists():
        raise HTTPException(409, f"template '{req.id}' already exists")
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(req.raw_markdown, encoding="utf-8")
    return _template_to_dict(load_template(p))


@router.put("/api/templates/{tpl_id}")
async def update(tpl_id: str, req: UpdateRequest):
    p = TEMPLATES_DIR / f"{tpl_id}.md"
    if not p.exists():
        raise HTTPException(404, f"template '{tpl_id}' not found")
    p.write_text(req.raw_markdown, encoding="utf-8")
    return _template_to_dict(load_template(p))


@router.delete("/api/templates/{tpl_id}")
async def delete(tpl_id: str):
    p = TEMPLATES_DIR / f"{tpl_id}.md"
    if not p.exists():
        raise HTTPException(404, f"template '{tpl_id}' not found")
    p.unlink()
    return {"deleted": tpl_id}
```

- [ ] **Step 4: 注册路由**

```python
    from app.api import templates as templates_api
    app.include_router(templates_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_templates.py -v`
Expected: PASS（7 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/templates.py app/main.py tests/test_api/test_templates.py
git commit -m "feat: template CRUD API"
```

---

### Task 21: 实现 api/files.py（文件夹列表 + 缩略图）

**Files:**
- Create: `app/api/files.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_files.py`

- [ ] **Step 1: 写测试 tests/test_api/test_files.py**

```python
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def _make_imgs(folder, n=3):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (50, 50), (i*30 % 256, 100, 100)).save(folder / f"img{i}.png")


def test_list_images_in_folder(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "data"
    _make_imgs(folder, n=3)
    (folder / "ignore.txt").write_text("nope")

    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/files/list", params={"folder": str(folder)})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    for it in items:
        assert it["name"].endswith(".png")
        assert "path" in it
        assert "size" in it


def test_list_folder_not_found(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/files/list", params={"folder": str(tmp_path / "nope")})
    assert resp.status_code == 400


def test_thumbnail_endpoint(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "data"
    _make_imgs(folder, n=1)
    target = folder / "img0.png"

    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/files/thumbnail", params={"path": str(target), "size": 32})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_files.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 app/api/files.py**

```python
"""GET /api/files/list      — 列文件夹中的图片
GET /api/files/thumbnail — 返回缩略图（内存生成，PNG 流）
"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from PIL import Image


router = APIRouter()
SUPPORTED = {".png", ".jpg", ".jpeg", ".webp"}


@router.get("/api/files/list")
async def list_files(folder: str = Query(...)):
    p = Path(folder)
    if not p.is_dir():
        raise HTTPException(400, f"folder not found: {folder}")
    items = []
    for entry in sorted(p.iterdir()):
        if entry.is_file() and entry.suffix.lower() in SUPPORTED:
            try:
                stat = entry.stat()
                size = stat.st_size
            except OSError:
                size = 0
            items.append({
                "name": entry.name,
                "path": str(entry.absolute()),
                "size": size,
            })
    return {"folder": str(p.absolute()), "items": items}


@router.get("/api/files/thumbnail")
async def thumbnail(path: str = Query(...), size: int = Query(160)):
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(400, f"file not found: {path}")
    try:
        img = Image.open(p)
    except Exception as e:
        raise HTTPException(400, f"not an image: {e}")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    fmt = "PNG" if p.suffix.lower() == ".png" else "JPEG"
    if fmt == "JPEG" and img.mode in ("RGBA", "LA"):
        img = img.convert("RGB")
    img.save(buf, fmt)
    buf.seek(0)
    return StreamingResponse(buf, media_type=f"image/{fmt.lower()}")
```

- [ ] **Step 4: 注册路由**

```python
    from app.api import files as files_api
    app.include_router(files_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_files.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/files.py app/main.py tests/test_api/test_files.py
git commit -m "feat: files list + thumbnail API"
```

---

### Task 22: 实现 api/settings.py（运行时配置读写 + 后端测试连通）

**Files:**
- Create: `app/api/settings.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_settings.py`

- [ ] **Step 1: 写测试 tests/test_api/test_settings.py**

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import create_app


def _setup(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
        "ANTHROPIC_API_KEY=ak\n"
    )
    monkeypatch.chdir(tmp_path)


def test_get_settings_returns_current(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_provider"] == "gemini"
    assert data["current_model"] == "gemini-2.5-pro"
    assert "providers" in data
    # 至少列出注册的几个
    names = {p["name"] for p in data["providers"]}
    assert "gemini" in names
    assert "anthropic" in names
    assert "openai_compat" in names


def test_update_settings_persists(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    resp = client.put("/api/settings", json={
        "current_provider": "anthropic",
        "current_model": "claude-opus-4-7",
    })
    assert resp.status_code == 200
    assert (tmp_path / "settings.json").exists()
    resp2 = client.get("/api/settings")
    assert resp2.json()["current_provider"] == "anthropic"


def test_ping_provider_success(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text="pong")
        resp = client.post("/api/settings/ping", json={
            "provider": "gemini", "model": "gemini-2.5-pro",
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ping_provider_failure(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.side_effect = RuntimeError("auth fail")
        resp = client.post("/api/settings/ping", json={
            "provider": "gemini", "model": "gemini-2.5-pro",
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "auth fail" in resp.json()["error"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api/test_settings.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 app/api/settings.py**

```python
"""GET /api/settings      — 当前配置 + 可用 provider 列表
PUT /api/settings      — 切换当前 provider/model（写 settings.json）
POST /api/settings/ping — 用 1×1 像素图测试 provider 连通性
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from PIL import Image

from app.providers import factory
from app.providers.base import VisionProvider


router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    current_provider: Optional[str] = None
    current_model: Optional[str] = None


class PingRequest(BaseModel):
    provider: str
    model: str


def _enumerate_providers() -> list[dict]:
    """枚举注册过的 provider + openai-compat 的所有 endpoint 子项。"""
    out = []
    for name in factory.list_providers():
        cls = factory.get_provider_class(name)
        if name == "openai_compat":
            for endpoint, preset in factory.openai_compat_presets().items():
                out.append({
                    "name": endpoint,
                    "kind": "openai_compat",
                    "models": preset["models"],
                    "base_url": preset["base_url"],
                })
        else:
            out.append({
                "name": name,
                "kind": name,
                "models": cls.available_models(),
                "base_url": "",
            })
    return out


@router.get("/api/settings")
async def get_settings(request: Request):
    cfg = request.app.state.config
    return {
        "current_provider": cfg.current_provider,
        "current_model": cfg.current_model,
        "default_provider": cfg.default_provider,
        "default_model": cfg.default_model,
        "default_output_dir": cfg.default_output_dir,
        "host": cfg.host,
        "port": cfg.port,
        "ui": cfg.ui,
        "providers": _enumerate_providers(),
        "configured_keys": sorted(cfg.api_keys.keys()),
    }


@router.put("/api/settings")
async def update_settings(req: UpdateSettingsRequest, request: Request):
    cfg = request.app.state.config
    updates = {}
    if req.current_provider is not None:
        updates["current_provider"] = req.current_provider
    if req.current_model is not None:
        updates["current_model"] = req.current_model
    cfg.update_settings(**updates)
    return {"current_provider": cfg.current_provider,
            "current_model": cfg.current_model}


@router.post("/api/settings/ping")
async def ping(req: PingRequest, request: Request):
    cfg = request.app.state.config
    # 1×1 透明 PNG
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, "PNG")
    tmp = Path("app/.cache/ping.png")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(buf.getvalue())
    try:
        provider = factory.build_provider(cfg, provider_name=req.provider, model=req.model)
        provider.generate([tmp], "回答一个字: ok", "")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 4: 注册路由**

```python
    from app.api import settings as settings_api
    app.include_router(settings_api.router)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api/test_settings.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 6: Commit**

```bash
git add app/api/settings.py app/main.py tests/test_api/test_settings.py
git commit -m "feat: settings GET/PUT + provider ping"
```

---

## M10 · Web UI（原生 HTML + Alpine.js）

> **UI 设计原则**：单 SPA-style 页面 + 顶部 6 个 Tab 切换；每个 Tab 一个 Alpine `x-data` component；全局没有 build step；CSS 用一个 styles.css。
>
> **每个 Tab 的 HTML 不嵌入 index.html 而是单独文件**，在 app.js 启动时 `fetch + innerHTML`。

### Task 23: Web 骨架（index.html + app.js + styles.css）

**Files:**
- Create: `web/index.html`
- Create: `web/app.js`
- Create: `web/styles.css`
- Modify: `app/main.py`（如果之前没挂 web 目录则补上）

- [ ] **Step 1: 写 web/index.html**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Shot-Prompt-Backwards</title>
  <link rel="stylesheet" href="/static/styles.css">
  <script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
</head>
<body>
  <header class="topbar">
    <h1>Shot-Prompt-Backwards</h1>
    <nav class="tabs" x-data="{tab: 'inference'}">
      <button :class="{active: tab==='inference'}" @click="tab='inference'; window.dispatchEvent(new CustomEvent('tab-changed', {detail: 'inference'}))">反推</button>
      <button :class="{active: tab==='split'}"     @click="tab='split';     window.dispatchEvent(new CustomEvent('tab-changed', {detail: 'split'}))">拆图</button>
      <button :class="{active: tab==='combine'}"   @click="tab='combine';   window.dispatchEvent(new CustomEvent('tab-changed', {detail: 'combine'}))">拼图</button>
      <button :class="{active: tab==='trim'}"      @click="tab='trim';      window.dispatchEvent(new CustomEvent('tab-changed', {detail: 'trim'}))">去白边</button>
      <button :class="{active: tab==='templates'}" @click="tab='templates'; window.dispatchEvent(new CustomEvent('tab-changed', {detail: 'templates'}))">模板</button>
      <button :class="{active: tab==='settings'}"  @click="tab='settings';  window.dispatchEvent(new CustomEvent('tab-changed', {detail: 'settings'}))">设置</button>
    </nav>
  </header>
  <main id="tab-content"></main>
  <script src="/static/app.js" type="module"></script>
</body>
</html>
```

- [ ] **Step 2: 写 web/styles.css**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; background: #f5f6f8; color: #222; }
.topbar { background: #fff; border-bottom: 1px solid #e1e3e7; padding: 12px 20px; display: flex; align-items: center; gap: 24px; }
.topbar h1 { font-size: 18px; margin: 0; }
.tabs { display: flex; gap: 4px; }
.tabs button { background: transparent; border: 1px solid transparent; padding: 6px 14px; cursor: pointer; border-radius: 6px; color: #555; }
.tabs button.active { background: #4f8edc; color: white; }
.tabs button:hover:not(.active) { background: #eef2f7; }
main { max-width: 1200px; margin: 24px auto; padding: 0 20px; }
.card { background: #fff; border: 1px solid #e1e3e7; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.card h2 { margin: 0 0 12px; font-size: 16px; color: #333; }
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.row label { min-width: 100px; color: #555; }
input[type=text], input[type=number], select, textarea { padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px; }
textarea { width: 100%; min-height: 80px; font-family: inherit; }
button.primary { background: #4f8edc; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }
button.primary:disabled { background: #c7d3e6; cursor: not-allowed; }
button.secondary { background: #eef2f7; color: #333; border: 1px solid #d1d5db; padding: 6px 12px; border-radius: 4px; cursor: pointer; }
.thumbs { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; }
.thumb { border: 1px solid #d1d5db; border-radius: 4px; overflow: hidden; }
.thumb img { width: 100%; height: 120px; object-fit: cover; display: block; }
.thumb .name { font-size: 12px; padding: 4px 6px; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.alert-warn { background: #fff7e6; border: 1px solid #f0c14b; padding: 10px 14px; border-radius: 4px; color: #8a6d3b; margin: 8px 0; }
.alert-err  { background: #fde2e2; border: 1px solid #d9534f; padding: 10px 14px; border-radius: 4px; color: #b32420; margin: 8px 0; }
.alert-ok   { background: #e0f4e0; border: 1px solid #5cb85c; padding: 10px 14px; border-radius: 4px; color: #3c763d; margin: 8px 0; }
.progress { background: #eef2f7; border-radius: 4px; overflow: hidden; height: 20px; }
.progress .bar { background: #4f8edc; height: 100%; transition: width 0.3s; }
.result-field { margin-bottom: 12px; }
.result-field label { font-weight: bold; color: #333; display: block; margin-bottom: 4px; }
.result-field .actions { display: flex; gap: 8px; }
.copy-btn { background: #eef2f7; border: 1px solid #d1d5db; padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 12px; }
.dot-ok    { color: #5cb85c; }
.dot-fail  { color: #d9534f; }
.dot-skip  { color: #888; }
.dot-run   { color: #4f8edc; }
```

- [ ] **Step 3: 写 web/app.js（路由 + 加载 tab 片段）**

```javascript
// app.js — 顶层路由：监听 tab-changed，把 web/tabs/<name>.html 注入 #tab-content
const TAB_BASE = "/static/tabs";
const tabCache = {};

async function loadTab(name) {
  let html = tabCache[name];
  if (!html) {
    const resp = await fetch(`${TAB_BASE}/${name}.html`);
    if (!resp.ok) {
      document.getElementById("tab-content").innerHTML = `<div class="card alert-err">加载 ${name} 失败</div>`;
      return;
    }
    html = await resp.text();
    tabCache[name] = html;
  }
  document.getElementById("tab-content").innerHTML = html;
  // 让 Alpine 处理新插入的节点
  if (window.Alpine) window.Alpine.initTree(document.getElementById("tab-content"));
}

window.addEventListener("tab-changed", (e) => loadTab(e.detail));

// 初始加载默认 tab
window.addEventListener("DOMContentLoaded", () => {
  loadTab("inference");
});

// ============== 共用工具 ==============
window.api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async put(url, body) {
    const r = await fetch(url, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async del(url) {
    const r = await fetch(url, {method: "DELETE"});
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  copy(text) {
    navigator.clipboard.writeText(text);
  },
};
```

- [ ] **Step 4: 验证骨架加载**

Run: 启动 `python -m app.main`，浏览器打开 `http://127.0.0.1:7866`。
Expected:
- 顶部 6 个 Tab 按钮可点击
- 切换时不报错（即便 tabs/*.html 还不存在也只是 alert-err，不崩）

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/app.js web/styles.css
git commit -m "feat: web UI skeleton with 6 tabs and Alpine.js routing"
```

---

### Task 24: web/tabs/inference.html — 反推 Tab（含防灾门禁）

**Files:**
- Create: `web/tabs/inference.html`

- [ ] **Step 1: 写完整 inference.html**

```html
<div x-data="inferenceTab()" x-init="init()">

  <div class="card">
    <h2>1. 输入模式</h2>
    <div class="row">
      <label><input type="radio" value="grid" x-model="mode"> 拼接宫格图</label>
      <label><input type="radio" value="multi" x-model="mode"> 多张独立图</label>
      <label><input type="radio" value="single" x-model="mode"> 单张图</label>
      <label><input type="radio" value="batch" x-model="mode"> 文件夹批量</label>
    </div>
  </div>

  <div class="card">
    <h2>2. 选图</h2>
    <div class="row">
      <input type="text" x-model="folderPath" placeholder="输入文件夹路径..." style="width: 400px">
      <button class="secondary" @click="loadFolder()">浏览</button>
    </div>
    <div class="thumbs" x-show="files.length">
      <template x-for="(f, i) in files" :key="f.path">
        <div class="thumb"
             :style="selected.includes(f.path) ? 'outline: 3px solid #4f8edc' : ''"
             @click="toggleSelect(f.path)">
          <img :src="`/api/files/thumbnail?path=${encodeURIComponent(f.path)}&size=200`">
          <div class="name" x-text="f.name"></div>
        </div>
      </template>
    </div>
    <p x-show="!files.length" style="color:#888; margin-top:8px">还没有选文件夹或文件夹为空</p>
  </div>

  <!-- ========== 仅宫格模式：拆图预览（防灾门禁） ========== -->
  <div class="card" x-show="mode === 'grid'">
    <h2>3. 拆图预览（必须人工确认）</h2>
    <div class="row">
      <label>网格规格</label>
      <input type="number" x-model.number="grid.src_rows" min="1" style="width:60px"> ×
      <input type="number" x-model.number="grid.src_cols" min="1" style="width:60px"> 源
      <span style="margin:0 8px">→</span>
      <input type="number" x-model.number="grid.sub_rows" min="1" style="width:60px"> ×
      <input type="number" x-model.number="grid.sub_cols" min="1" style="width:60px"> 子
    </div>
    <div class="row">
      <button class="secondary" @click="previewSplit()" :disabled="!selected.length || mode!=='grid'">▶ 预览拆图</button>
      <span x-show="splitPreviewError" class="alert-err" x-text="splitPreviewError"></span>
    </div>
    <div class="thumbs" x-show="tiles.length">
      <template x-for="(t, i) in tiles" :key="t">
        <div class="thumb"><img :src="t"><div class="name" x-text="`tile ${i+1}`"></div></div>
      </template>
    </div>
    <div x-show="tiles.length" class="alert-warn">
      ⚠️ 请人眼检查拆图是否正确。错误的拆图会让 vision 模型反推错误结果。
    </div>
    <div class="row" x-show="tiles.length">
      <label><input type="checkbox" x-model="splitConfirmed"> 我确认拆图正确，可以送入反推</label>
    </div>
  </div>

  <div class="card">
    <h2 x-text="mode === 'grid' ? '4. 反推模板' : '3. 反推模板'"></h2>
    <div class="row">
      <select x-model="templateId" @change="onTemplateChange()">
        <template x-for="t in templates"><option :value="t.id" x-text="`${t.name} (${t.id})`"></option></template>
      </select>
      <span style="color:#888; font-size:13px" x-show="recommendedId">推荐: <span x-text="recommendedId"></span></span>
    </div>
  </div>

  <div class="card" x-show="currentTemplate">
    <h2 x-text="mode === 'grid' ? '5. 补充输入' : '4. 补充输入'"></h2>
    <template x-for="v in currentTemplate?.variables || []">
      <div class="row">
        <label x-text="v.label + (v.required?' *':'')"></label>
        <template x-if="v.type==='int' || v.type==='float'">
          <input type="number" x-model.number="supplement[v.name]" :placeholder="v.placeholder || v.default" style="width:140px">
        </template>
        <template x-if="v.type==='text'">
          <input type="text" x-model="supplement[v.name]" :placeholder="v.placeholder" style="width:400px">
        </template>
        <template x-if="v.type==='textarea'">
          <textarea x-model="supplement[v.name]" :placeholder="v.placeholder"></textarea>
        </template>
        <template x-if="v.type==='select'">
          <select x-model="supplement[v.name]">
            <template x-for="opt in v.options"><option :value="opt" x-text="opt"></option></template>
          </select>
        </template>
      </div>
    </template>
  </div>

  <div class="card">
    <h2 x-text="mode === 'grid' ? '6. 反推执行' : '5. 反推执行'"></h2>
    <div class="row">
      <button class="primary" @click="runInference()"
              :disabled="!canRun()" x-text="loading ? '反推中…' : '🚀 开始反推'"></button>
      <span style="color:#888; font-size:13px" x-text="canRunReason()"></span>
    </div>
    <div x-show="error" class="alert-err" x-text="error"></div>
  </div>

  <div class="card" x-show="result">
    <h2>结果（可编辑后重保存）</h2>
    <template x-for="field in ['global_prompt','timeline_data','local_prompts','notes']">
      <div class="result-field">
        <label x-text="field"></label>
        <textarea x-model="result[field]"></textarea>
        <div class="actions">
          <button class="copy-btn" @click="api.copy(result[field] || '')">复制</button>
        </div>
      </div>
    </template>
    <div class="result-field">
      <label>segment_lengths / max_frames / frame_indices / strengths / epsilon</label>
      <pre x-text="JSON.stringify({segment_lengths: result.segment_lengths, max_frames: result.max_frames, frame_indices: result.frame_indices, strengths: result.strengths, epsilon: result.epsilon}, null, 2)"></pre>
    </div>
    <div class="row">
      <button class="primary" @click="saveResult()">💾 保存覆盖 md+json</button>
      <span x-show="result.md_path" style="color:#888; font-size:13px">已保存: <span x-text="result.md_path"></span></span>
    </div>
  </div>

</div>

<script>
function inferenceTab() {
  return {
    mode: 'multi',
    folderPath: '',
    files: [],
    selected: [],
    grid: {src_rows: 2, src_cols: 2, sub_rows: 1, sub_cols: 1},
    tiles: [],
    splitPreviewError: '',
    splitConfirmed: false,
    templates: [],
    templateId: '',
    recommendedId: '',
    currentTemplate: null,
    supplement: {},
    loading: false,
    error: '',
    result: null,

    async init() {
      this.templates = await api.get('/api/templates');
      if (this.templates.length && !this.templateId) {
        this.templateId = this.templates[0].id;
        this.onTemplateChange();
      }
    },
    async loadFolder() {
      if (!this.folderPath.trim()) return;
      try {
        const r = await api.get(`/api/files/list?folder=${encodeURIComponent(this.folderPath)}`);
        this.files = r.items;
        this.selected = [];
      } catch (e) {
        this.error = String(e);
      }
    },
    toggleSelect(path) {
      if (this.mode === 'single' || this.mode === 'grid') {
        this.selected = [path];
        this.tiles = [];
        this.splitConfirmed = false;
      } else if (this.mode === 'multi') {
        if (this.selected.includes(path)) {
          this.selected = this.selected.filter(p => p !== path);
        } else {
          this.selected.push(path);
        }
      } else if (this.mode === 'batch') {
        // batch 模式不走选择，整文件夹
      }
      this.autoRecommend();
    },
    async autoRecommend() {
      const count = this.mode === 'grid'
        ? (this.grid.sub_rows && this.grid.sub_cols ? (this.grid.src_rows/this.grid.sub_rows) * (this.grid.src_cols/this.grid.sub_cols) : 1)
        : this.selected.length || 1;
      try {
        const r = await api.get(`/api/templates/recommend?image_count=${count}`);
        if (r.id) {
          this.recommendedId = r.id;
          this.templateId = r.id;
          this.onTemplateChange();
        }
      } catch {}
    },
    async onTemplateChange() {
      this.currentTemplate = this.templates.find(t => t.id === this.templateId) || null;
      this.supplement = {};
      if (this.currentTemplate) {
        for (const v of this.currentTemplate.variables) {
          if (v.default !== null && v.default !== undefined) {
            this.supplement[v.name] = v.default;
          }
        }
      }
    },
    async previewSplit() {
      if (!this.selected.length) return;
      this.splitPreviewError = '';
      try {
        const r = await api.post('/api/grid/preview', {
          image_path: this.selected[0],
          src_rows: this.grid.src_rows,
          src_cols: this.grid.src_cols,
          sub_rows: this.grid.sub_rows,
          sub_cols: this.grid.sub_cols,
        });
        this.tiles = r.tiles;
        this.splitConfirmed = false;
        this.autoRecommend();
      } catch (e) {
        this.splitPreviewError = String(e);
        this.tiles = [];
      }
    },
    canRun() {
      if (this.loading) return false;
      if (this.mode === 'grid') {
        return this.selected.length === 1 && this.splitConfirmed && this.templateId;
      }
      if (this.mode === 'batch') return !!this.folderPath && this.templateId;
      return this.selected.length > 0 && this.templateId;
    },
    canRunReason() {
      if (this.mode === 'grid' && this.tiles.length && !this.splitConfirmed) return '请先勾选「我确认拆图正确」';
      if (this.mode === 'grid' && !this.tiles.length) return '请先点击「预览拆图」';
      return '';
    },
    async runInference() {
      this.error = '';
      this.loading = true;
      this.result = null;
      try {
        if (this.mode === 'batch') {
          // 跳转批量逻辑（在本 tab 内显示进度）
          await this._runBatch();
        } else {
          let images;
          if (this.mode === 'grid') {
            // 拆图后的 tiles 是 /cache/preview/<hash>/tile_N.png；服务端需要本地路径
            // 让 inference API 自己再拆一次更稳：传原图 + grid 参数交给一个 helper... 这里简化：
            // 由于 tiles URL 已经是 web/cache 暴露的实际文件，可以转换成 absolute path
            // 为简化：再次调用 /api/grid/preview 触发服务端缓存，复用其物理路径
            const previewResp = await api.post('/api/grid/preview', {
              image_path: this.selected[0],
              src_rows: this.grid.src_rows, src_cols: this.grid.src_cols,
              sub_rows: this.grid.sub_rows, sub_cols: this.grid.sub_cols,
            });
            // tile URL → 本地文件路径
            images = previewResp.tiles.map(u => {
              // /cache/preview/<hash>/tile_0.png → app/.cache/preview/<hash>/tile_0.png
              return u.replace('/cache/', 'app/.cache/');
            });
          } else {
            images = this.selected;
          }
          const r = await api.post('/api/inference', {
            images, template_id: this.templateId, supplement: this.supplement,
          });
          this.result = r;
        }
      } catch (e) {
        this.error = String(e);
      } finally {
        this.loading = false;
      }
    },
    async _runBatch() {
      const r = await api.post('/api/batch', {
        folder: this.folderPath, template_id: this.templateId,
        supplement: this.supplement, skip_existing: true,
      });
      const taskId = r.task_id;
      const evt = new EventSource(`/api/batch/${taskId}/stream`);
      this.result = {batch: true, items: [], done: false, ok: 0, failed: 0};
      evt.addEventListener('progress', (e) => {
        const d = JSON.parse(e.data);
        this.result.items.push({...d, type: 'progress'});
      });
      evt.addEventListener('item_done', (e) => {
        const d = JSON.parse(e.data);
        this.result.items.push({...d, type: 'item_done'});
      });
      evt.addEventListener('complete', (e) => {
        const d = JSON.parse(e.data);
        this.result.ok = d.ok; this.result.failed = d.failed; this.result.done = true;
        evt.close();
      });
    },
    async saveResult() {
      if (!this.result || this.result.batch) return;
      // 调一个简化的 save 路由：复用 inference 的写盘逻辑，让前端直接发改过的字段
      // 这里走 inference 的 raw 字段 + 解析结果二次落盘——简化版直接重发同一个原始文本
      // v1.0: 把 result 编辑后的字段写回 md/json
      const r = await fetch('/api/inference/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          md_path: this.result.md_path,
          json_path: this.result.json_path,
          fields: {
            global_prompt: this.result.global_prompt,
            timeline_data: this.result.timeline_data,
            local_prompts: this.result.local_prompts,
            segment_lengths: this.result.segment_lengths,
            max_frames: this.result.max_frames,
            frame_indices: this.result.frame_indices,
            strengths: this.result.strengths,
            epsilon: this.result.epsilon,
            notes: this.result.notes,
          },
          meta: this.result.meta,
        }),
      });
      if (!r.ok) {
        alert('保存失败: ' + (await r.text()));
      } else {
        alert('已保存');
      }
    },
  };
}
</script>
```

- [ ] **Step 2: 添加 /api/inference/save 路由（支持二次编辑保存）**

修改 `app/api/inference.py` 末尾追加：

```python
class SaveRequest(BaseModel):
    md_path: str
    json_path: str
    fields: dict
    meta: dict


@router.post("/api/inference/save")
async def save_edited(req: SaveRequest):
    md_path = Path(req.md_path)
    json_path = Path(req.json_path)
    if not md_path.parent.exists():
        raise HTTPException(400, f"md path's parent missing: {md_path.parent}")

    # 用 fields + meta 重建 ParsedResult，复用 output_writer
    from app.core.result_parser import ParsedResult
    r = ParsedResult(raw=req.fields.get("raw", ""))
    r.global_prompt = req.fields.get("global_prompt", "")
    r.timeline_data = req.fields.get("timeline_data", "")
    r.local_prompts = req.fields.get("local_prompts", "")
    r.segment_lengths = req.fields.get("segment_lengths", []) or []
    r.max_frames = req.fields.get("max_frames")
    r.frame_indices = req.fields.get("frame_indices", []) or []
    r.strengths = req.fields.get("strengths", []) or []
    r.epsilon = req.fields.get("epsilon")
    r.notes = req.fields.get("notes", "")

    out_dir = md_path.parent
    base_name = md_path.stem
    new_md, new_json = write_outputs(
        result=r, output_dir=out_dir, base_name=base_name,
        template_id=req.meta.get("template_id", ""),
        provider=req.meta.get("provider", ""),
        model=req.meta.get("model", ""),
    )
    return {"md_path": str(new_md), "json_path": str(new_json)}
```

并写一个最小测试 `tests/test_api/test_inference_save.py`：

```python
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


def test_save_edited_overwrites_md_json(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DEFAULT_PROVIDER=gemini\n")
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "_prompts"
    out.mkdir()
    md = out / "x.md"
    md.write_text("old")
    js = out / "x.json"
    js.write_text("{}")

    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/inference/save", json={
        "md_path": str(md),
        "json_path": str(js),
        "fields": {
            "global_prompt": "NEW GP",
            "timeline_data": "{}",
            "local_prompts": "LP",
            "segment_lengths": [10],
            "max_frames": 10,
            "frame_indices": [0, -1, -1, -1, -1],
            "strengths": [1, 0, 0, 0, 0],
            "epsilon": 0.1,
            "notes": "n",
        },
        "meta": {"template_id": "t", "provider": "p", "model": "m"},
    })
    assert resp.status_code == 200
    assert "NEW GP" in md.read_text(encoding="utf-8")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["global_prompt"] == "NEW GP"
```

- [ ] **Step 3: 运行测试**

Run: `pytest tests/test_api/test_inference_save.py -v`
Expected: PASS（1 个测试）

- [ ] **Step 4: 手动 smoke：浏览器测反推 tab**

启动 `python -m app.main` → 浏览器 → 反推 Tab：
- 切换 4 种模式都不报错
- 输入文件夹路径 + 点「浏览」能加载缩略图
- 宫格模式：选一张图 → 预览拆图 → 不勾选确认时按钮 disabled

- [ ] **Step 5: Commit**

```bash
git add web/tabs/inference.html app/api/inference.py tests/test_api/test_inference_save.py
git commit -m "feat: inference web tab with split-preview safety gate + edit-save endpoint"
```

---

### Task 25: web/tabs/split.html — 拆图 Tab

**Files:**
- Create: `web/tabs/split.html`

- [ ] **Step 1: 写 split.html**

```html
<div x-data="splitTab()">
  <div class="card">
    <h2>拆图（R×C 网格 → 子网格切分，落盘）</h2>
    <div class="row">
      <label>源图路径</label>
      <input type="text" x-model="imagePath" style="width:500px" placeholder="例：D:/img/grid.png">
    </div>
    <div class="row">
      <label>源网格</label>
      <input type="number" x-model.number="srcRows" min="1" style="width:80px"> ×
      <input type="number" x-model.number="srcCols" min="1" style="width:80px">
      <label style="margin-left:20px">子网格</label>
      <input type="number" x-model.number="subRows" min="1" style="width:80px"> ×
      <input type="number" x-model.number="subCols" min="1" style="width:80px">
    </div>
    <div class="row">
      <label>输出目录</label>
      <input type="text" x-model="outputDir" style="width:500px">
    </div>
    <div class="row">
      <label>命名前缀</label>
      <input type="text" x-model="namePrefix" placeholder="默认 = 源图文件名">
      <label style="margin-left:20px">格式</label>
      <select x-model="outputFormat"><option>PNG</option><option>JPG</option></select>
    </div>
    <div class="row">
      <button class="secondary" @click="preview()">▶ 预览</button>
      <button class="primary" @click="run()" :disabled="loading">💾 拆分并落盘</button>
    </div>
    <div x-show="error" class="alert-err" x-text="error"></div>
    <div x-show="saved.length" class="alert-ok">已保存 <span x-text="saved.length"></span> 张</div>
    <div class="thumbs" x-show="tiles.length">
      <template x-for="(t, i) in tiles" :key="t">
        <div class="thumb"><img :src="t"><div class="name" x-text="`tile ${i+1}`"></div></div>
      </template>
    </div>
  </div>
</div>
<script>
function splitTab() {
  return {
    imagePath: '', outputDir: '', namePrefix: '', outputFormat: 'PNG',
    srcRows: 2, srcCols: 2, subRows: 1, subCols: 1,
    tiles: [], saved: [], error: '', loading: false,
    async preview() {
      this.error = ''; this.tiles = [];
      try {
        const r = await api.post('/api/grid/preview', {
          image_path: this.imagePath,
          src_rows: this.srcRows, src_cols: this.srcCols,
          sub_rows: this.subRows, sub_cols: this.subCols,
        });
        this.tiles = r.tiles;
      } catch (e) { this.error = String(e); }
    },
    async run() {
      this.error = ''; this.saved = []; this.loading = true;
      try {
        const r = await api.post('/api/grid/split', {
          image_path: this.imagePath,
          output_dir: this.outputDir,
          src_rows: this.srcRows, src_cols: this.srcCols,
          sub_rows: this.subRows, sub_cols: this.subCols,
          output_format: this.outputFormat,
          name_prefix: this.namePrefix,
        });
        this.saved = r.files;
      } catch (e) { this.error = String(e); }
      finally { this.loading = false; }
    },
  };
}
</script>
```

- [ ] **Step 2: 手动 smoke**

切到拆图 Tab，准备一张测试网格图，输入路径 + 输出目录 → 预览 → 落盘 → 检查输出目录。

- [ ] **Step 3: Commit**

```bash
git add web/tabs/split.html
git commit -m "feat: split tab UI"
```

---

### Task 26: web/tabs/combine.html — 拼图 Tab

**Files:**
- Create: `web/tabs/combine.html`

- [ ] **Step 1: 写 combine.html**

```html
<div x-data="combineTab()" x-init="init()">
  <div class="card">
    <h2>拼图（N 张图 → R×C 网格）</h2>
    <div class="row">
      <label>选择文件夹</label>
      <input type="text" x-model="folder" style="width:500px">
      <button class="secondary" @click="loadFolder()">浏览</button>
    </div>
    <div class="thumbs" x-show="files.length">
      <template x-for="(f, i) in files" :key="f.path">
        <div class="thumb"
             :style="getOrder(f.path) >= 0 ? 'outline: 3px solid #4f8edc' : ''"
             @click="toggle(f.path)">
          <img :src="`/api/files/thumbnail?path=${encodeURIComponent(f.path)}&size=200`">
          <div class="name">
            <span x-show="getOrder(f.path)>=0" x-text="`#${getOrder(f.path)+1}`" style="color:#4f8edc;font-weight:bold"></span>
            <span x-text="f.name"></span>
          </div>
        </div>
      </template>
    </div>
    <div class="row">
      <label>目标网格</label>
      <input type="number" x-model.number="targetRows" min="1" style="width:80px"> ×
      <input type="number" x-model.number="targetCols" min="1" style="width:80px">
      <label style="margin-left:20px">间距</label>
      <input type="number" x-model.number="gap" min="0" style="width:80px">
      <label style="margin-left:20px">缩放</label>
      <select x-model="scaleMode">
        <option value="letterbox">letterbox</option>
        <option value="crop">crop</option>
        <option value="stretch">stretch</option>
      </select>
    </div>
    <div class="row">
      <label>输出路径</label>
      <input type="text" x-model="outputPath" style="width:500px">
      <label style="margin-left:20px">格式</label>
      <select x-model="outputFormat"><option>PNG</option><option>JPG</option></select>
    </div>
    <div class="row">
      <button class="primary" @click="run()" :disabled="loading || selected.length === 0">💾 拼接</button>
      <span x-text="`${selected.length} / ${targetRows*targetCols} 张`"></span>
    </div>
    <div x-show="error" class="alert-err" x-text="error"></div>
    <div x-show="result" class="alert-ok">已生成: <span x-text="result"></span></div>
  </div>
</div>
<script>
function combineTab() {
  return {
    folder: '', files: [], selected: [],
    targetRows: 2, targetCols: 2, gap: 4, scaleMode: 'letterbox',
    outputPath: '', outputFormat: 'PNG',
    result: '', error: '', loading: false,
    init() {},
    async loadFolder() {
      try {
        const r = await api.get(`/api/files/list?folder=${encodeURIComponent(this.folder)}`);
        this.files = r.items;
        this.selected = [];
      } catch (e) { this.error = String(e); }
    },
    getOrder(path) { return this.selected.indexOf(path); },
    toggle(path) {
      const idx = this.selected.indexOf(path);
      if (idx >= 0) this.selected.splice(idx, 1);
      else this.selected.push(path);
    },
    async run() {
      this.error = ''; this.result = ''; this.loading = true;
      try {
        const r = await api.post('/api/grid/combine', {
          images: this.selected,
          output_path: this.outputPath,
          target_rows: this.targetRows,
          target_cols: this.targetCols,
          gap: this.gap,
          scale_mode: this.scaleMode,
          output_format: this.outputFormat,
        });
        this.result = r.output_path;
      } catch (e) { this.error = String(e); }
      finally { this.loading = false; }
    },
  };
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add web/tabs/combine.html
git commit -m "feat: combine tab UI with click-order selection"
```

---

### Task 27: web/tabs/trim.html — 去白边 Tab

**Files:**
- Create: `web/tabs/trim.html`

- [ ] **Step 1: 写 trim.html**

```html
<div x-data="trimTab()">
  <div class="card">
    <h2>去白边</h2>
    <div class="row">
      <label>模式</label>
      <label><input type="radio" value="single" x-model="mode"> 单图</label>
      <label><input type="radio" value="batch" x-model="mode"> 批量</label>
    </div>
    <template x-if="mode==='single'">
      <div>
        <div class="row">
          <label>源图</label>
          <input type="text" x-model="src" style="width:500px">
        </div>
        <div class="row">
          <label>输出</label>
          <input type="text" x-model="out" style="width:500px">
        </div>
      </div>
    </template>
    <template x-if="mode==='batch'">
      <div>
        <div class="row">
          <label>源文件夹</label>
          <input type="text" x-model="srcFolder" style="width:500px">
        </div>
        <div class="row">
          <label>输出文件夹</label>
          <input type="text" x-model="outFolder" style="width:500px">
        </div>
        <div class="row">
          <label>命名后缀</label>
          <input type="text" x-model="nameSuffix" placeholder="留空 = 同名覆盖；建议 _trim">
        </div>
      </div>
    </template>
    <div class="row">
      <label>阈值</label>
      <input type="number" x-model.number="threshold" min="0" max="255" style="width:80px">
      <label style="margin-left:20px">迭代次数</label>
      <input type="number" x-model.number="maxIter" min="1" max="10" style="width:80px">
      <label style="margin-left:20px">格式</label>
      <select x-model="outputFormat"><option>PNG</option><option>JPG</option></select>
    </div>
    <div class="row">
      <button class="primary" @click="run()" :disabled="loading">💾 执行</button>
    </div>
    <div x-show="error" class="alert-err" x-text="error"></div>
    <div x-show="result" class="alert-ok" x-text="result"></div>
  </div>
</div>
<script>
function trimTab() {
  return {
    mode: 'single', src: '', out: '', srcFolder: '', outFolder: '', nameSuffix: '_trim',
    threshold: 240, maxIter: 5, outputFormat: 'PNG',
    result: '', error: '', loading: false,
    async run() {
      this.error = ''; this.result = ''; this.loading = true;
      try {
        if (this.mode === 'single') {
          const r = await api.post('/api/border/trim', {
            image_path: this.src, output_path: this.out,
            threshold: this.threshold, max_iter: this.maxIter,
            output_format: this.outputFormat,
          });
          this.result = `已保存 ${r.output_path}（${r.size[0]}×${r.size[1]}）`;
        } else {
          const r = await api.post('/api/border/trim_batch', {
            folder: this.srcFolder, output_dir: this.outFolder,
            threshold: this.threshold, max_iter: this.maxIter,
            output_format: this.outputFormat, name_suffix: this.nameSuffix,
          });
          this.result = `已保存 ${r.files.length} 张`;
        }
      } catch (e) { this.error = String(e); }
      finally { this.loading = false; }
    },
  };
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add web/tabs/trim.html
git commit -m "feat: border trim tab UI"
```

---

### Task 28: web/tabs/templates.html — 模板 Tab

**Files:**
- Create: `web/tabs/templates.html`

- [ ] **Step 1: 写 templates.html**

```html
<div x-data="templatesTab()" x-init="init()">
  <div class="card">
    <h2>模板列表</h2>
    <ul>
      <template x-for="t in templates" :key="t.id">
        <li style="padding:6px 0; display:flex; gap:8px; align-items:center;">
          <button class="secondary" @click="edit(t)" x-text="`${t.name} (${t.id})`"></button>
          <button class="copy-btn" @click="delTpl(t.id)">删除</button>
        </li>
      </template>
    </ul>
    <button class="primary" @click="newTpl()">+ 新建模板</button>
  </div>
  <div class="card" x-show="editing">
    <h2 x-text="isNew ? '新建模板' : `编辑：${editing?.id}`"></h2>
    <div class="row" x-show="isNew">
      <label>模板 ID</label>
      <input type="text" x-model="newId" placeholder="例：my_six_frame">
    </div>
    <div class="row">
      <textarea x-model="raw" style="min-height:400px; font-family: monospace; font-size:13px"></textarea>
    </div>
    <div class="row">
      <button class="primary" @click="save()">💾 保存</button>
      <button class="secondary" @click="cancel()">取消</button>
    </div>
    <div x-show="error" class="alert-err" x-text="error"></div>
  </div>
</div>
<script>
function templatesTab() {
  return {
    templates: [], editing: null, isNew: false, newId: '', raw: '', error: '',
    async init() { this.templates = await api.get('/api/templates'); },
    edit(t) {
      this.editing = t; this.isNew = false;
      this.raw = t.raw_markdown; this.newId = '';
    },
    newTpl() {
      this.editing = {id:'', name:'', raw_markdown:''}; this.isNew = true; this.newId = '';
      this.raw = `---\nname: 新模板\nsuggest_when: image_count == 1\nvariables:\n  - {name: style_note, type: textarea, label: 风格备注, optional: true}\n---\n你是 ...`;
    },
    async save() {
      this.error = '';
      try {
        if (this.isNew) {
          if (!this.newId) { this.error = '请填模板 ID'; return; }
          await api.post('/api/templates', {id: this.newId, raw_markdown: this.raw});
        } else {
          await api.put(`/api/templates/${this.editing.id}`, {raw_markdown: this.raw});
        }
        this.templates = await api.get('/api/templates');
        this.cancel();
      } catch (e) { this.error = String(e); }
    },
    cancel() { this.editing = null; this.isNew = false; },
    async delTpl(id) {
      if (!confirm(`删除模板 ${id}？`)) return;
      try {
        await api.del(`/api/templates/${id}`);
        this.templates = await api.get('/api/templates');
      } catch (e) { this.error = String(e); }
    },
  };
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add web/tabs/templates.html
git commit -m "feat: templates CRUD tab UI"
```

---

### Task 29: web/tabs/settings.html — 设置 Tab

**Files:**
- Create: `web/tabs/settings.html`

- [ ] **Step 1: 写 settings.html**

```html
<div x-data="settingsTab()" x-init="init()">
  <div class="card">
    <h2>当前后端</h2>
    <div class="row">
      <label>Provider</label>
      <select x-model="currentProvider" @change="onProviderChange()">
        <template x-for="p in providers"><option :value="p.name" x-text="`${p.name}（${p.kind}）`"></option></template>
      </select>
      <label style="margin-left:20px">Model</label>
      <select x-model="currentModel">
        <template x-for="m in currentModels"><option :value="m" x-text="m"></option></template>
      </select>
    </div>
    <div class="row">
      <button class="primary" @click="save()">💾 保存</button>
      <button class="secondary" @click="ping()">🔌 测试连通</button>
      <span x-show="pingResult==='ok'" class="dot-ok">✓ 连通</span>
      <span x-show="pingResult==='fail'" class="dot-fail">✗ <span x-text="pingError"></span></span>
    </div>
    <div x-show="saved" class="alert-ok">已保存</div>
  </div>
  <div class="card">
    <h2>已配置的 API Key</h2>
    <ul>
      <template x-for="k in configuredKeys" :key="k"><li>● <span x-text="k"></span></li></template>
    </ul>
    <p style="color:#888; font-size:13px">需要新增/修改 API Key 请编辑项目根目录的 <code>.env</code>，重启服务生效。</p>
  </div>
  <div class="card">
    <h2>当前默认输出目录</h2>
    <p x-text="defaultOutputDir || '（未设置，将输出到输入图片同目录的 _prompts/）'"></p>
  </div>
</div>
<script>
function settingsTab() {
  return {
    currentProvider: '', currentModel: '', providers: [], currentModels: [],
    configuredKeys: [], defaultOutputDir: '',
    pingResult: '', pingError: '', saved: false,
    async init() {
      const d = await api.get('/api/settings');
      this.currentProvider = d.current_provider;
      this.currentModel = d.current_model;
      this.providers = d.providers;
      this.configuredKeys = d.configured_keys;
      this.defaultOutputDir = d.default_output_dir || '';
      this.onProviderChange();
    },
    onProviderChange() {
      const p = this.providers.find(p => p.name === this.currentProvider);
      this.currentModels = p ? p.models : [];
    },
    async save() {
      this.saved = false;
      await api.put('/api/settings', {
        current_provider: this.currentProvider,
        current_model: this.currentModel,
      });
      this.saved = true;
      setTimeout(() => this.saved = false, 2000);
    },
    async ping() {
      this.pingResult = ''; this.pingError = '';
      try {
        const r = await api.post('/api/settings/ping', {
          provider: this.currentProvider, model: this.currentModel,
        });
        if (r.ok) this.pingResult = 'ok';
        else { this.pingResult = 'fail'; this.pingError = r.error; }
      } catch (e) {
        this.pingResult = 'fail'; this.pingError = String(e);
      }
    },
  };
}
</script>
```

- [ ] **Step 2: 手动 smoke**

启动 → 设置 Tab → 切换 provider/model → 保存 → 重启服务 → 验证持久化 → 测试连通。

- [ ] **Step 3: Commit**

```bash
git add web/tabs/settings.html
git commit -m "feat: settings tab UI"
```

---

## M11 · 启动脚本 + E2E smoke

### Task 30: 写启动脚本（Windows + Linux/Mac）

**Files:**
- Create: `run.bat`
- Create: `run.sh`

- [ ] **Step 1: 写 run.bat**

```bat
@echo off
setlocal

REM 检查 .env 是否存在
if not exist .env (
    echo [WARN] .env 不存在，先拷贝 .env.example 并填写 API Key
    copy .env.example .env
    notepad .env
)

REM 检查 shot-master 是否已装
python -c "import shot_master" 2>NUL
if errorlevel 1 (
    echo [INFO] 安装本地 shot-master...
    pip install -e ..\shot-master
)

REM 检查本项目依赖
python -c "import fastapi" 2>NUL
if errorlevel 1 (
    echo [INFO] 安装本项目依赖...
    pip install -e .
)

REM 启动
python -m app.main

endlocal
```

- [ ] **Step 2: 写 run.sh**

```bash
#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
  echo "[WARN] .env 不存在，从 .env.example 创建"
  cp .env.example .env
  echo "请编辑 .env 填写 API Key 后再次运行"
  exit 1
fi

if ! python -c "import shot_master" 2>/dev/null; then
  echo "[INFO] 安装本地 shot-master..."
  pip install -e ../shot-master
fi

if ! python -c "import fastapi" 2>/dev/null; then
  echo "[INFO] 安装本项目依赖..."
  pip install -e .
fi

python -m app.main
```

- [ ] **Step 3: 赋予执行权限**

```bash
chmod +x run.sh
```

- [ ] **Step 4: Commit**

```bash
git add run.bat run.sh
git commit -m "feat: one-click startup scripts for win/linux"
```

---

### Task 31: E2E smoke 测试

**Files:**
- Create: `tests/test_e2e_smoke.py`

> 目的：跑完整调用链一次（不真打 vision API），验证所有路由协作正常。

- [ ] **Step 1: 写 E2E 测试**

```python
"""端到端 smoke：模拟用户从浏览启动 → 选模板 → 单图反推 → 编辑 → 保存。
所有 vision 调用 mock；shot-master 真实跑（不 mock）。"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


FAKE_OUTPUT = """## 1. global_prompt
```
夕阳下少女转身
```
## 5. max_frames
```
192
```
"""


def test_e2e_full_loop(tmp_path, monkeypatch):
    # 准备 env + 模板
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "single.md").write_text(
        "---\nname: Single\nsuggest_when: image_count == 1\nvariables: []\n---\nbody",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "DEFAULT_PROVIDER=gemini\nDEFAULT_MODEL=gemini-2.5-pro\nGEMINI_API_KEY=k\n"
    )
    monkeypatch.chdir(tmp_path)

    img = tmp_path / "shot.png"
    Image.new("RGB", (200, 200), (100, 100, 200)).save(img)

    app = create_app()
    client = TestClient(app)

    # 1. 健康检查
    assert client.get("/api/health").status_code == 200

    # 2. 列模板
    tpls = client.get("/api/templates").json()
    assert any(t["id"] == "single" for t in tpls)

    # 3. 推荐模板
    rec = client.get("/api/templates/recommend?image_count=1").json()
    assert rec["id"] == "single"

    # 4. 列文件夹
    folder_list = client.get(
        "/api/files/list", params={"folder": str(tmp_path)}
    ).json()
    assert any(it["name"] == "shot.png" for it in folder_list["items"])

    # 5. 单次反推
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = MagicMock(text=FAKE_OUTPUT)
        infer = client.post("/api/inference", json={
            "images": [str(img)],
            "template_id": "single",
            "supplement": {},
        }).json()
    assert infer["global_prompt"] == "夕阳下少女转身"
    assert infer["max_frames"] == 192
    md_path = Path(infer["md_path"])
    json_path = Path(infer["json_path"])
    assert md_path.exists() and json_path.exists()

    # 6. 编辑后保存
    edited = client.post("/api/inference/save", json={
        "md_path": str(md_path),
        "json_path": str(json_path),
        "fields": {**infer, "global_prompt": "EDITED"},
        "meta": infer["meta"],
    }).json()
    assert "EDITED" in Path(edited["md_path"]).read_text(encoding="utf-8")

    # 7. 拆图（用 shot-master 真实跑）
    preview = client.post("/api/grid/preview", json={
        "image_path": str(img),
        "src_rows": 2, "src_cols": 2,
        "sub_rows": 1, "sub_cols": 1,
    }).json()
    assert len(preview["tiles"]) == 4

    # 8. 设置 GET/PUT
    settings = client.get("/api/settings").json()
    assert settings["current_provider"] == "gemini"
    client.put("/api/settings", json={"current_model": "gemini-3-pro-preview"})
    assert client.get("/api/settings").json()["current_model"] == "gemini-3-pro-preview"
```

- [ ] **Step 2: 运行 E2E**

Run: `pytest tests/test_e2e_smoke.py -v`
Expected: PASS（1 个测试，约 1-3 秒）

- [ ] **Step 3: 跑全部测试**

Run: `pytest -v`
Expected: 全绿，无 fail。

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_smoke.py
git commit -m "test: end-to-end smoke covering full request loop"
```

---

### Task 32: 反推 Tab UI 增加 per_image_supplement 选项

**Files:**
- Modify: `web/tabs/inference.html`

> 让用户在"文件夹批量"模式下能勾选"按文件名规则逐项映射"，把同名 .md/.json/.txt 自动注入到 supplement。

- [ ] **Step 1: 修改 inference.html 的 `inferenceTab()` 数据**

在 `data` 对象里添加：

```js
    perImageSupplement: false,
```

- [ ] **Step 2: 修改 inference.html 在「输入模式」card 后面、模板 card 前面新增一节**

```html
  <div class="card" x-show="mode === 'batch'">
    <h2>批量复用策略</h2>
    <div class="row">
      <label>
        <input type="checkbox" x-model="perImageSupplement">
        按文件名规则逐项映射（同名 .md / .json / .txt 自动注入）
      </label>
    </div>
    <p style="color:#888; font-size: 12px">
      勾选后：对每张图片，会尝试读取同目录、同文件名（仅扩展名不同）的 .md / .txt 当作剧本，
      或 .json 整体合并进补充输入。未勾选则全部使用上面"补充输入"区填的同一份。
    </p>
  </div>
```

- [ ] **Step 3: 修改 `_runBatch()` 方法，把字段传给后端**

```js
    async _runBatch() {
      const r = await api.post('/api/batch', {
        folder: this.folderPath,
        template_id: this.templateId,
        supplement: this.supplement,
        per_image_supplement: this.perImageSupplement,
        skip_existing: true,
      });
      // ... 其他逻辑不变
    },
```

- [ ] **Step 4: 手动 smoke**

启动 → 反推 Tab → 切到文件夹批量 → 准备一个含图 + 同名 .md 的文件夹 → 勾选"按文件名映射" → 反推 → 后端 logs 看到 supplement 已注入。

- [ ] **Step 5: Commit**

```bash
git add web/tabs/inference.html
git commit -m "feat: per-image supplement option in batch mode UI"
```

---

## 总结

**Task 完成后的状态**：
- 11 个 milestone × 32 个 Task 全部完成
- 单元测试 + API 测试 + E2E smoke 总计 ≥ 60 个测试用例
- `python -m app.main` 一条命令启动；浏览器开 `http://127.0.0.1:7866` 即可用
- 4 种输入模式 + 4 个 vision provider + 4 套模板 + 6 个 Tab 全部可用
- shot-master 通过本地 pip install -e 复用，零代码拷贝
- 防灾门禁：宫格模式必须先预览拆图 + 勾选确认才能反推
- 批量模式：SSE 进度推送，单条失败不影响后续，已存在文件自动 skip

**验收对照需求文档第 11 节**（每条都已被某个 Task 覆盖）：

| 验收项 | 实现 Task |
|---|---|
| 4 种输入模式可用 | Task 24 |
| Gemini + OpenAI 兼容 + Anthropic 三个跑通 | Task 10/11/12 |
| Qwen-VL 实现且 mock 通过 | Task 13 |
| 宫格模式防灾门禁 | Task 24（canRun / splitConfirmed 逻辑） |
| 批量处理 ≥10 张 + SSE | Task 15/16 |
| 反推结果可编辑 + 保存 + 复制 | Task 24（saveResult + copy） |
| 拆图/拼图/去白边等价 | Task 17/18/19 + 25/26/27 |
| 模板可在 Web 内增删改 | Task 20 + 28 |
| 设置页切换后端 + 测试连通 | Task 22 + 29 |
| tests/ 全部通过 | Task 31 |










