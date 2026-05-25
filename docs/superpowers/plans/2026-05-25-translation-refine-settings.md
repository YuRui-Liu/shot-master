# 翻译设置 + 提示词优化设置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `设置` 菜单加「翻译配置」「提示词优化配置」两项：前者配 `DEEPLX_URL`；后者配 meta-prompt 路径 + 反推专用 provider（base_url/key/model，支持 ollama qwen / 豆包），与全局 provider 解耦。

**Architecture:** 新增 6 个 Config 字段（落盘 settings.json + .env 兜底 deeplx）；factory 加 ollama preset；两个新 QDialog；`load_refine_meta_prompt` 支持自定义路径；video_panel 反推改用独立 `OpenAICompatProvider`；main_window 加菜单。

**Tech Stack:** PySide6（QDialog/QFormLayout/QComboBox）；openai SDK（chat.completions，已在用）；pytest。

**Spec:** [docs/superpowers/specs/2026-05-25-translation-refine-settings-design.md](../specs/2026-05-25-translation-refine-settings-design.md)

---

## File Structure

修改：
- `drama_shot_master/config.py` — 6 新字段 + update_settings 落盘 + load_config 读取 + os.environ 同步
- `drama_shot_master/providers/factory.py` — ollama preset
- `drama_shot_master/core/prompt_refiner.py` — `load_refine_meta_prompt(path="")`
- `drama_shot_master/ui/panels/video_panel.py` — 反推改用独立 provider
- `drama_shot_master/ui/main_window.py` — 两个菜单项 + 槽
- `tests/test_config.py`、`tests/test_core/test_prompt_refiner.py` — 扩展

新增：
- `drama_shot_master/ui/dialogs/translation_settings_dialog.py`
- `drama_shot_master/ui/dialogs/refine_settings_dialog.py`

---

## Task 1: Config 字段 + factory ollama preset（TDD）

**Files:**
- Modify: `drama_shot_master/config.py`
- Modify: `drama_shot_master/providers/factory.py`
- Test: `tests/test_config.py`

- [ ] **Step 1.1: 写失败测试**

Append to `tests/test_config.py`:

```python
def test_save_load_refine_and_deeplx_fields(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    cfg.update_settings(
        deeplx_url="http://localhost:1188/translate",
        refine_base_url="http://localhost:11434/v1",
        refine_api_key="k",
        refine_model="qwen2.5-vl",
        refine_provider_preset="ollama",
        refine_meta_prompt_path="/custom/meta.md",
    )
    cfg2 = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg2.deeplx_url == "http://localhost:1188/translate"
    assert cfg2.refine_base_url == "http://localhost:11434/v1"
    assert cfg2.refine_api_key == "k"
    assert cfg2.refine_model == "qwen2.5-vl"
    assert cfg2.refine_provider_preset == "ollama"
    assert cfg2.refine_meta_prompt_path == "/custom/meta.md"


def test_deeplx_url_env_fallback_syncs_os_environ(tmp_path, monkeypatch):
    import os
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPLX_URL=http://env.example/translate\n")
    settings_file = tmp_path / "settings.json"   # 无 deeplx_url
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.deeplx_url == "http://env.example/translate"
    assert os.environ.get("DEEPLX_URL") == "http://env.example/translate"


def test_missing_new_fields_default_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    env_file = tmp_path / ".env"; env_file.write_text("")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"current_provider": "gemini"}))
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=env_file, settings_path=settings_file)
    assert cfg.refine_base_url == ""
    assert cfg.refine_model == ""
    assert cfg.refine_provider_preset == "ollama"   # default
    assert cfg.deeplx_url == ""
```

(monkeypatch records DEEPLX_URL at the start of each test, so its env teardown also cleans up the raw `os.environ` write done inside `load_config`.)

- [ ] **Step 1.2: 运行测试，确认失败**

Run: `pytest tests/test_config.py -v -k "refine or deeplx or missing_new"`
Expected: FAIL（字段不存在 / 未读取）。

- [ ] **Step 1.3: 加 Config 字段**

Edit `drama_shot_master/config.py`. In the `Config` dataclass, after the line `last_active_function: str = "inference"`, add:

```python
    # 翻译
    deeplx_url: str = ""
    # 帧提示词优化（refine）独立 provider
    refine_base_url: str = ""
    refine_api_key: str = ""
    refine_model: str = ""
    refine_provider_preset: str = "ollama"
    refine_meta_prompt_path: str = ""
```

- [ ] **Step 1.4: update_settings 落盘新字段**

Edit `drama_shot_master/config.py`. In `update_settings`, the `data = {...}` dict currently ends with `"last_active_function": self.last_active_function,`. Add these entries to the dict (before the closing brace):

```python
                "deeplx_url": self.deeplx_url,
                "refine_base_url": self.refine_base_url,
                "refine_api_key": self.refine_api_key,
                "refine_model": self.refine_model,
                "refine_provider_preset": self.refine_provider_preset,
                "refine_meta_prompt_path": self.refine_meta_prompt_path,
```

- [ ] **Step 1.5: load_config 读取 + .env 兜底 + os.environ 同步**

Edit `drama_shot_master/config.py`.

(a) Add `import os` near the top (after `import json`).

(b) In `load_config`, the `Config(...)` constructor call currently passes several kwargs ending with `settings_path=settings_path,`. Add one kwarg:
```python
        deeplx_url=env.get("DEEPLX_URL") or "",
```

(c) In the settings.json reading block, there's an existing loop:
```python
                for key in ("runninghub_api_key", "runninghub_workflow_id",
                            "runninghub_base_url",
                            "runninghub_template_path", "video_output_dir"):
                    if key in data and isinstance(data[key], str):
                        setattr(cfg, key, data[key])
```
Add a second loop right after it:
```python
                for key in ("deeplx_url", "refine_base_url", "refine_api_key",
                            "refine_model", "refine_provider_preset",
                            "refine_meta_prompt_path"):
                    if key in data and isinstance(data[key], str):
                        setattr(cfg, key, data[key])
```

(d) Just before `return cfg` at the end of `load_config`, add the os.environ sync:
```python
    if cfg.deeplx_url:
        os.environ["DEEPLX_URL"] = cfg.deeplx_url
```

- [ ] **Step 1.6: factory ollama preset**

Edit `drama_shot_master/providers/factory.py`. In `openai_compat_presets()`, the returned dict currently ends with the `"vllm"` entry. Add an `"ollama"` entry to the dict:

```python
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "models": ["qwen2.5-vl", "qwen2.5-vl:7b", "qwen2.5-vl:32b"],
        },
```

Edit `drama_shot_master/config.py`. The `OPENAI_COMPAT_ENDPOINTS` list currently is:
```python
OPENAI_COMPAT_ENDPOINTS = [
    "openai", "deepseek", "doubao", "openrouter", "siliconflow", "vllm"
]
```
Change to add `"ollama"`:
```python
OPENAI_COMPAT_ENDPOINTS = [
    "openai", "deepseek", "doubao", "openrouter", "siliconflow", "vllm", "ollama"
]
```

- [ ] **Step 1.7: 运行测试，确认通过**

Run: `pytest tests/test_config.py -v`
Expected: 全部 PASS（含 3 个新测试 + 原有）。

- [ ] **Step 1.8: 全量回归**

Run: `pytest -q`
Expected: 0 failures（之前基线 + 3 新测试）。

- [ ] **Step 1.9: 提交**

```bash
git add drama_shot_master/config.py drama_shot_master/providers/factory.py tests/test_config.py
git commit -m "feat(settings): add deeplx_url + refine provider config fields + ollama preset

Config gains deeplx_url and refine_{base_url,api_key,model,provider_preset,
meta_prompt_path}; load_config reads them (deeplx falls back to .env and
syncs os.environ); factory gains an ollama openai-compat preset.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 1)

- Working dir `/mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master`, branch `feat/video-panel`. Tree is clean.
- `Config.update_settings` writes a HARDCODED dict — new fields MUST be added there to persist.
- `load_config(env_path, settings_path)` takes explicit paths (tests pass tmp_path).
- The translator (`core/translator.py`) reads `os.environ.get("DEEPLX_URL")`; step 1.5(d) makes the configured URL visible to it.

---

## Task 2: load_refine_meta_prompt 支持自定义路径（TDD）

**Files:**
- Modify: `drama_shot_master/core/prompt_refiner.py`
- Test: `tests/test_core/test_prompt_refiner.py`

- [ ] **Step 2.1: 写失败测试**

Append to `tests/test_core/test_prompt_refiner.py`:

```python
def test_load_meta_default_reads_bundled():
    from drama_shot_master.core.prompt_refiner import load_refine_meta_prompt
    text = load_refine_meta_prompt("")
    assert "global_prompt" in text          # JSON contract marker
    assert "Nothing in this frame is still" in text


def test_load_meta_custom_path(tmp_path):
    from drama_shot_master.core.prompt_refiner import load_refine_meta_prompt
    custom = tmp_path / "my_meta.md"
    custom.write_text("CUSTOM META CONTENT", encoding="utf-8")
    assert load_refine_meta_prompt(str(custom)) == "CUSTOM META CONTENT"


def test_load_meta_missing_raises(tmp_path):
    from drama_shot_master.core.prompt_refiner import load_refine_meta_prompt
    import pytest as _pytest
    with _pytest.raises(FileNotFoundError):
        load_refine_meta_prompt(str(tmp_path / "nope.md"))
```

(`test_load_meta_default_reads_bundled` relies on the cwd being the repo root, which is how pytest runs here.)

- [ ] **Step 2.2: 运行测试，确认失败**

Run: `pytest tests/test_core/test_prompt_refiner.py -v -k load_meta`
Expected: FAIL — `load_refine_meta_prompt()` currently takes no args, so `load_refine_meta_prompt("")` raises TypeError.

- [ ] **Step 2.3: 改 load_refine_meta_prompt 签名**

Edit `drama_shot_master/core/prompt_refiner.py`. Currently:
```python
REFINE_META_PROMPT_PATH = Path("templates/ltx_refine_meta_prompt.md")
```
Rename to:
```python
DEFAULT_REFINE_META_PROMPT_PATH = Path("templates/ltx_refine_meta_prompt.md")
```

And the function currently:
```python
def load_refine_meta_prompt() -> str:
    """读 meta-prompt 文件全文。缺失 → FileNotFoundError。"""
    return REFINE_META_PROMPT_PATH.read_text(encoding="utf-8")
```
Replace with:
```python
def load_refine_meta_prompt(path: str = "") -> str:
    """path 空 → bundled 默认；否则读自定义路径。缺失 → FileNotFoundError。"""
    p = Path(path) if path else DEFAULT_REFINE_META_PROMPT_PATH
    return p.read_text(encoding="utf-8")
```

- [ ] **Step 2.4: 运行测试，确认通过**

Run: `pytest tests/test_core/test_prompt_refiner.py -v`
Expected: 全 PASS（原 9 + 3 新）。

- [ ] **Step 2.5: 全量回归**

Run: `pytest -q`
Expected: 0 failures。

- [ ] **Step 2.6: 提交**

```bash
git add drama_shot_master/core/prompt_refiner.py tests/test_core/test_prompt_refiner.py
git commit -m "feat(refine): load_refine_meta_prompt accepts custom path

Empty path keeps the bundled default; a non-empty path reads a custom
meta-prompt file. Renames REFINE_META_PROMPT_PATH →
DEFAULT_REFINE_META_PROMPT_PATH.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 2)

- `load_refine_meta_prompt` is currently called no-arg in `video_panel._on_refine` (Task 5 updates that call to pass `cfg.refine_meta_prompt_path`).
- The bundled file `templates/ltx_refine_meta_prompt.md` exists and contains `"global_prompt"` and `Nothing in this frame is still`.

---

## Task 3: 翻译设置对话框

**Files:**
- Create: `drama_shot_master/ui/dialogs/translation_settings_dialog.py`

PyQt 不自动化；验收 = 烟测导入。

- [ ] **Step 3.1: 实现 translation_settings_dialog.py**

Create `drama_shot_master/ui/dialogs/translation_settings_dialog.py`:

```python
"""TranslationSettingsDialog：菜单栏「设置 → 翻译配置…」打开。"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QDialogButtonBox,
)

from drama_shot_master.config import Config


class TranslationSettingsDialog(QDialog):
    """配 DEEPLX_URL（用于 prompt 中文预览）。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("翻译配置")
        self.setModal(True)
        self.resize(520, 180)
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://api.deeplx.org/translate（留空则用 .env 的 DEEPLX_URL）")
        form.addRow("DeepLX URL", self.url_edit)
        root.addLayout(form)
        tip = QLabel("公共实例可能不稳定，可改为自部署 "
                     "http://localhost:1188/translate。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888")
        root.addWidget(tip)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_from_cfg(self):
        self.url_edit.setText(self.cfg.deeplx_url)

    def accept(self):
        url = self.url_edit.text().strip()
        self.cfg.update_settings(deeplx_url=url)
        if url:
            os.environ["DEEPLX_URL"] = url
        super().accept()
```

- [ ] **Step 3.2: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.dialogs.translation_settings_dialog import TranslationSettingsDialog; print('ok')"
```
Expected: `ok`（PySide6 不可用则 ast 语法检查，如实报告）。

- [ ] **Step 3.3: 提交**

```bash
git add drama_shot_master/ui/dialogs/translation_settings_dialog.py
git commit -m "feat(settings): add translation (DeepLX URL) settings dialog

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 3)

- Mirror the existing `runninghub_settings_dialog.py` pattern (QDialog + QFormLayout + `cfg.update_settings` on accept). New file only; stage only it.
- On save, also writes `os.environ["DEEPLX_URL"]` so the next translate uses the new URL without restart.

---

## Task 4: 提示词优化设置对话框

**Files:**
- Create: `drama_shot_master/ui/dialogs/refine_settings_dialog.py`

- [ ] **Step 4.1: 实现 refine_settings_dialog.py**

Create `drama_shot_master/ui/dialogs/refine_settings_dialog.py`:

```python
"""RefineSettingsDialog：菜单栏「设置 → 提示词优化配置…」打开。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPushButton, QLabel, QFileDialog, QWidget, QDialogButtonBox, QFrame,
)

from drama_shot_master.config import Config
from drama_shot_master.providers.openai_compat import OpenAICompatProvider
from drama_shot_master.providers.base import ProviderConfig
from drama_shot_master.ui.worker import FunctionWorker

# 预设名 → (base_url, [model 建议])
_PRESETS = {
    "Ollama (本地)": ("http://localhost:11434/v1",
                      ["qwen2.5-vl", "qwen2.5-vl:7b", "qwen2.5-vl:32b"]),
    "豆包 ARK": ("https://ark.cn-beijing.volces.com/api/v3",
                 ["doubao-seed-1-6-vision-250815",
                  "doubao-1-5-vision-pro-32k-250115"]),
    "自定义": ("", []),
}


class RefineSettingsDialog(QDialog):
    """配 meta-prompt 路径 + 反推专用 provider（base_url/key/model）。"""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._worker: FunctionWorker | None = None
        self.setWindowTitle("提示词优化配置")
        self.setModal(True)
        self.resize(560, 360)
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(_PRESETS.keys()))
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        form.addRow("Provider 预设", self.preset_combo)

        self.base_url_edit = QLineEdit()
        form.addRow("Base URL", self.base_url_edit)

        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setMaximumWidth(40)
        self.show_key_btn.toggled.connect(
            lambda on: self.api_key_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        key_row.addWidget(self.api_key_edit, 1)
        key_row.addWidget(self.show_key_btn)
        key_wrap = QWidget(); key_wrap.setLayout(key_row)
        form.addRow("API Key", key_wrap)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("Model", self.model_combo)

        meta_row = QHBoxLayout()
        self.meta_edit = QLineEdit()
        self.meta_edit.setPlaceholderText(
            "留空 = 内置 templates/ltx_refine_meta_prompt.md")
        meta_browse = QPushButton("浏览…")
        meta_browse.clicked.connect(self._browse_meta)
        meta_row.addWidget(self.meta_edit, 1)
        meta_row.addWidget(meta_browse)
        meta_wrap = QWidget(); meta_wrap.setLayout(meta_row)
        form.addRow("Meta-prompt 路径", meta_wrap)

        root.addLayout(form)

        line = QFrame(); line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test)
        self.test_label = QLabel("")
        self.test_label.setTextFormat(Qt.RichText)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_label, 1)
        root.addLayout(test_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_preset_changed(self, name: str):
        base_url, models = _PRESETS.get(name, ("", []))
        if base_url:
            self.base_url_edit.setText(base_url)
        cur = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if cur:
            self.model_combo.setCurrentText(cur)

    def _browse_meta(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 meta-prompt", "", "Markdown (*.md);;All (*)")
        if p:
            self.meta_edit.setText(p)

    def _load_from_cfg(self):
        preset = self.cfg.refine_provider_preset or "Ollama (本地)"
        if preset in _PRESETS:
            self.preset_combo.setCurrentText(preset)
            self._on_preset_changed(preset)
        self.base_url_edit.setText(self.cfg.refine_base_url)
        self.api_key_edit.setText(self.cfg.refine_api_key)
        if self.cfg.refine_model:
            self.model_combo.setCurrentText(self.cfg.refine_model)
        self.meta_edit.setText(self.cfg.refine_meta_prompt_path)

    def _on_test(self):
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        api_key = self.api_key_edit.text().strip() or "ollama"
        if not base_url or not model:
            self.test_label.setText(
                '<span style="color:#f66">需先填 Base URL 和 Model</span>')
            return
        self.test_label.setText("测试中…")
        self.test_btn.setEnabled(False)

        def task():
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                timeout=20.0,
            )
            return resp.choices[0].message.content or "(空响应)"

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(
            lambda _: self._test_done(True, "✓ 连接成功"))
        self._worker.failed.connect(
            lambda e: self._test_done(False, f"✗ {e}"))
        self._worker.start()

    def _test_done(self, ok: bool, msg: str):
        color = "#5fa" if ok else "#f66"
        self.test_label.setText(f'<span style="color:{color}">{msg}</span>')
        self.test_btn.setEnabled(True)

    def accept(self):
        from PySide6.QtWidgets import QMessageBox
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        if not base_url or not model:
            QMessageBox.warning(self, "校验失败", "必须填 Base URL 和 Model")
            return
        self.cfg.update_settings(
            refine_provider_preset=self.preset_combo.currentText(),
            refine_base_url=base_url,
            refine_api_key=self.api_key_edit.text().strip(),
            refine_model=model,
            refine_meta_prompt_path=self.meta_edit.text().strip(),
        )
        super().accept()
```

- [ ] **Step 4.2: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.dialogs.refine_settings_dialog import RefineSettingsDialog; print('ok')"
```
Expected: `ok`（或 ast 回退，如实报告）。

- [ ] **Step 4.3: 提交**

```bash
git add drama_shot_master/ui/dialogs/refine_settings_dialog.py
git commit -m "feat(settings): add refine (prompt optimization) settings dialog

Provider preset (Ollama/豆包/自定义) auto-fills base_url + model
suggestions; password API key; meta-prompt path browse; 测试连接 sends a
minimal chat.completions ping on a worker thread.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 4)

- Mirrors `runninghub_settings_dialog.py` (password key field + 👁 toggle + 测试连接 worker + QDialogButtonBox).
- 测试连接 builds a raw `OpenAI` client (chat.completions, text-only "ping") — confirms base_url/key/model reachable. API key defaults to "ollama" when blank (ollama ignores it).
- Stage only the new file.

---

## Task 5: video_panel 反推改用独立 provider

**Files:**
- Modify: `drama_shot_master/ui/panels/video_panel.py`

- [ ] **Step 5.1: 调整 imports**

Edit `drama_shot_master/ui/panels/video_panel.py`. The refine imports added earlier are:
```python
from drama_shot_master.providers import factory
from drama_shot_master.core.prompt_refiner import (
    build_refine_request, parse_refine_response, load_refine_meta_prompt,
)
from drama_shot_master.ui.widgets.refine_review_dialog import (
    RefineReviewDialog, RefineRow,
)
```
Replace the `factory` import line with the explicit provider imports:
```python
from drama_shot_master.providers.openai_compat import OpenAICompatProvider
from drama_shot_master.providers.base import ProviderConfig
from drama_shot_master.core.prompt_refiner import (
    build_refine_request, parse_refine_response, load_refine_meta_prompt,
)
from drama_shot_master.ui.widgets.refine_review_dialog import (
    RefineReviewDialog, RefineRow,
)
```
(Remove `from drama_shot_master.providers import factory` — it was only used by `_on_refine`. Verify no other use of `factory` in this file first; if there is, keep the import.)

- [ ] **Step 5.2: 改 _on_refine 的 provider + meta 加载**

Edit `drama_shot_master/ui/panels/video_panel.py`. The current `_on_refine` head is:
```python
    def _on_refine(self):
        if not self.model.segments:
            QMessageBox.information(self, "无内容", "时间轴为空，先添加分镜段")
            return
        try:
            provider = factory.build_provider(
                self.cfg, self.cfg.current_provider, self.cfg.current_model)
        except Exception as e:
            QMessageBox.critical(self, "Provider 错误", str(e))
            return
        try:
            system_prompt = load_refine_meta_prompt()
        except FileNotFoundError:
            QMessageBox.critical(
                self, "缺少 meta-prompt",
                "templates/ltx_refine_meta_prompt.md 不存在")
            return
        req = build_refine_request(self.model)
```
Replace that head with:
```python
    def _on_refine(self):
        if not self.model.segments:
            QMessageBox.information(self, "无内容", "时间轴为空，先添加分镜段")
            return
        if not self.cfg.refine_base_url or not self.cfg.refine_model:
            QMessageBox.warning(
                self, "未配置",
                "请先在「设置 → 提示词优化配置」填 Base URL 和 Model")
            return
        provider = OpenAICompatProvider(ProviderConfig(
            api_key=self.cfg.refine_api_key or "ollama",
            base_url=self.cfg.refine_base_url,
            model=self.cfg.refine_model))
        try:
            system_prompt = load_refine_meta_prompt(self.cfg.refine_meta_prompt_path)
        except FileNotFoundError:
            QMessageBox.critical(
                self, "缺少 meta-prompt",
                f"找不到 meta-prompt 文件："
                f"{self.cfg.refine_meta_prompt_path or 'templates/ltx_refine_meta_prompt.md'}")
            return
        req = build_refine_request(self.model)
```
(The rest of `_on_refine` — the `task()` closure, status set, worker start — stays unchanged.)

- [ ] **Step 5.3: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.panels.video_panel import VideoPanel; print('ok')"
```
Expected: `ok`（或 ast 回退）。

- [ ] **Step 5.4: 全量回归**

Run: `pytest -q`
Expected: 0 failures。

- [ ] **Step 5.5: 提交**

```bash
git add drama_shot_master/ui/panels/video_panel.py
git commit -m "feat(refine): use dedicated refine provider config in video panel

_on_refine now builds an OpenAICompatProvider from cfg.refine_* instead of
the global current_provider, loads the meta-prompt from cfg.refine_meta_prompt_path,
and guides the user to 提示词优化配置 when unset.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 5)

- Tasks 1 (cfg fields) + 2 (meta path) are prerequisites — both landed.
- The `_on_refine_done` / `_on_refine_failed` methods are NOT changed.
- `OpenAICompatProvider(ProviderConfig(api_key, base_url, model))` — `ProviderConfig` is a dataclass in `providers/base.py` with `timeout` defaulting to 60.

---

## Task 6: main_window 菜单两项

**Files:**
- Modify: `drama_shot_master/ui/main_window.py`

- [ ] **Step 6.1: imports**

Edit `drama_shot_master/ui/main_window.py`. Near the existing import:
```python
from drama_shot_master.ui.dialogs.runninghub_settings_dialog import RunningHubSettingsDialog
```
Add:
```python
from drama_shot_master.ui.dialogs.translation_settings_dialog import TranslationSettingsDialog
from drama_shot_master.ui.dialogs.refine_settings_dialog import RefineSettingsDialog
```

- [ ] **Step 6.2: 菜单项**

Edit `drama_shot_master/ui/main_window.py`. Current settings menu block in `_build_ui`:
```python
        sm = menu.addMenu("设置")
        a_rh = QAction("RunningHub 配置…", self)
        a_rh.triggered.connect(self._open_runninghub_settings)
        sm.addAction(a_rh)
```
Replace with:
```python
        sm = menu.addMenu("设置")
        a_rh = QAction("RunningHub 配置…", self)
        a_rh.triggered.connect(self._open_runninghub_settings)
        sm.addAction(a_rh)
        a_tr = QAction("翻译配置…", self)
        a_tr.triggered.connect(self._open_translation_settings)
        sm.addAction(a_tr)
        a_rf = QAction("提示词优化配置…", self)
        a_rf.triggered.connect(self._open_refine_settings)
        sm.addAction(a_rf)
```

- [ ] **Step 6.3: 槽方法**

Edit `drama_shot_master/ui/main_window.py`. Find the existing `_open_runninghub_settings` method:
```python
    def _open_runninghub_settings(self):
        RunningHubSettingsDialog(self.cfg, parent=self).exec()
```
Add right after it:
```python
    def _open_translation_settings(self):
        TranslationSettingsDialog(self.cfg, parent=self).exec()

    def _open_refine_settings(self):
        RefineSettingsDialog(self.cfg, parent=self).exec()
```

- [ ] **Step 6.4: 烟测导入**

Run:
```bash
python -c "from drama_shot_master.ui.main_window import MainWindow; print('ok')"
```
Expected: `ok`（或 ast 回退）。

- [ ] **Step 6.5: 全量回归**

Run: `pytest -q`
Expected: 0 failures。

- [ ] **Step 6.6: 提交**

```bash
git add drama_shot_master/ui/main_window.py
git commit -m "feat(settings): add 翻译配置 + 提示词优化配置 menu entries

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

## Context (Task 6)

- The settings menu currently only has RunningHub. `_open_runninghub_settings` shows the dialog-open pattern to mirror.
- Tasks 3 + 4 created the dialog classes being imported.

---

## Task 7: 手测清单（end-of-feature）

**Files:** 无代码变更。

- [ ] **Step 7.1: 把手测清单交回用户**（spec §7.3）

1. 设置 → 翻译配置：填一个 DeepLX URL 保存；prompt 框点「译」用新 URL（改错 URL 验证生效）。
2. 设置 → 提示词优化配置：选 Ollama 预设 → base_url 自动填 localhost:11434/v1；填 model=qwen2.5-vl；测试连接（本地 ollama 起着时 ✓）。
3. 切「豆包 ARK」预设 → base_url 自动变；填豆包 key + 视觉模型；测试连接 ✓。
4. Meta-prompt 路径留空 → 反推用内置；填自定义 md → 反推用它。
5. 视频面板「✨ 优化提示词」→ 用 refine 配置；未配 base_url/model 时提示去设置。
6. 重启应用 → 配置持久化（看 settings.json 有 deeplx_url / refine_* 字段）。

报告：全过 DONE；任一异常 DONE_WITH_CONCERNS + 具体步。

---

## Self-Review 记录

- **Spec coverage:**
  - §4.1 Config 6 字段 + update_settings + load_config + .env 兜底 + os.environ → Task 1
  - §4.2 ollama preset + OPENAI_COMPAT_ENDPOINTS → Task 1.6
  - §4.3 翻译对话框 → Task 3
  - §4.4 refine 对话框（预设/base_url/key/model/meta/测试连接） → Task 4
  - §4.5 load_refine_meta_prompt(path) → Task 2
  - §4.6 video_panel 改独立 provider → Task 5
  - §4.7 菜单 → Task 6
  - §6 错误处理 → Task 4（测试连接/校验）+ Task 5（未配/缺meta）+ Task 1（老配置默认）
  - §7.1 config 测试 → Task 1.1；§7.2 refiner 测试 → Task 2.1；§7.3 手测 → Task 7
- **Placeholder scan:** 无 TBD/"similar to"；每个代码 step 给完整代码或精确 before/after。
- **Type consistency:**
  - `load_refine_meta_prompt(path: str = "") -> str`（Task 2）→ Task 5 调 `load_refine_meta_prompt(self.cfg.refine_meta_prompt_path)` 一致。
  - Config 字段名 `deeplx_url / refine_base_url / refine_api_key / refine_model / refine_provider_preset / refine_meta_prompt_path`（Task 1）→ Task 3/4/5 引用一致。
  - `OpenAICompatProvider(ProviderConfig(api_key, base_url, model))`（Task 4 test + Task 5）签名一致（base.py 现有）。
  - 菜单槽 `_open_translation_settings / _open_refine_settings`（Task 6.2 connect ↔ 6.3 def）一致。
  - 对话框类名 `TranslationSettingsDialog`（Task 3）/ `RefineSettingsDialog`（Task 4）→ Task 6 import 一致。
