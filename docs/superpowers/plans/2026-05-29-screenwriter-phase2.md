# 编剧 Phase 2（6步 Wizard + 分镜图/视频/配音配乐提示词）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将编剧 Wizard 从 4 阶段扩展为 6 阶段（创意→剧本→分镜→分镜图提示词→视频提示词→配音配乐），新建三个 Agent 端点（SSE）+ 三个 UI Page + 公共基类，并在剧本页加推进高亮。

**Architecture:** Agent 层新建 `image_prompts` / `video_prompts` / `audio_prompts` 三条路由，均模仿 `prompts.py` 的 SSE 模式；UI 层抽取 `_BasePromptsPage` 公共基类后派生三个具体页；`ScreenwriterWizardHost` 去掉 `== 4` 硬断言，`ScreenwriterPanel` 换成 6 阶段装配。

**Tech Stack:** FastAPI + PySide6（offscreen QT_QPA_PLATFORM for tests）；pytest + fastapi.testclient；现有 `LLMClient`、`atomic_write_text`、`sse_event`、`_BaseStagePage`、`_EpisodeSelector`、`_UpstreamBanner`、`StreamWorker`。

---

## 文件映射

| 动作 | 路径 |
|------|------|
| 修改 | `drama_shot_master/ui/widgets/screenwriter/wizard_host.py` |
| 修改 | `drama_shot_master/ui/widgets/screenwriter/script_page.py` |
| 修改 | `drama_shot_master/ui/panels/screenwriter_panel.py` |
| 修改 | `screenwriter_agent/templates/template_loader.py` |
| 修改 | `screenwriter_agent/server.py` |
| 新建 | `screenwriter_agent/templates/image_prompts.md` |
| 新建 | `screenwriter_agent/templates/video_prompts.md` |
| 新建 | `screenwriter_agent/templates/audio_prompts.md` |
| 新建 | `screenwriter_agent/routes/image_prompts.py` |
| 新建 | `screenwriter_agent/routes/video_prompts.py` |
| 新建 | `screenwriter_agent/routes/audio_prompts.py` |
| 新建 | `drama_shot_master/ui/widgets/screenwriter/_base_prompts_page.py` |
| 新建 | `drama_shot_master/ui/widgets/screenwriter/image_prompts_page.py` |
| 新建 | `drama_shot_master/ui/widgets/screenwriter/video_prompts_page.py` |
| 新建 | `drama_shot_master/ui/widgets/screenwriter/audio_prompts_page.py` |
| 追加测试 | `tests/test_ui/screenwriter/test_wizard_host.py` |
| 追加测试 | `tests/test_ui/screenwriter/test_script_page.py` |
| 追加测试 | `tests/test_ui/screenwriter/test_screenwriter_panel.py` |
| 追加测试 | `tests/test_screenwriter_agent/test_template_loader.py` |
| 新建测试 | `tests/test_screenwriter_agent/test_route_image_prompts.py` |
| 新建测试 | `tests/test_screenwriter_agent/test_route_video_prompts.py` |
| 新建测试 | `tests/test_screenwriter_agent/test_route_audio_prompts.py` |
| 新建测试 | `tests/test_ui/screenwriter/test_base_prompts_page.py` |
| 新建测试 | `tests/test_ui/screenwriter/test_image_prompts_page.py` |
| 新建测试 | `tests/test_ui/screenwriter/test_video_prompts_page.py` |
| 新建测试 | `tests/test_ui/screenwriter/test_audio_prompts_page.py` |
| 新建测试 | `tests/test_screenwriter_agent/test_e2e_phase2.py` |

---

## Task 1: wizard_host 去掉 `== 4` 断言

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/wizard_host.py:20`
- Test: `tests/test_ui/screenwriter/test_wizard_host.py`

- [ ] **Step 1: 写失败测试（追加到现有文件末尾）**

打开 `tests/test_ui/screenwriter/test_wizard_host.py`，在文件末尾追加：

```python
def test_wizard_host_accepts_6_stages():
    _app()
    pages = [QWidget() for _ in range(6)]
    names = ["创意", "剧本", "分镜", "分镜图", "视频", "配音"]
    host = ScreenwriterWizardHost(pages, names)
    assert host._stack.count() == 6
    assert len(host._buttons) == 6


def test_wizard_host_6th_button_label():
    _app()
    pages = [QWidget() for _ in range(6)]
    names = ["创意", "剧本", "分镜", "分镜图", "视频", "配音"]
    host = ScreenwriterWizardHost(pages, names)
    assert host._buttons[5].text() == "6. 配音"
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_wizard_host.py::test_wizard_host_accepts_6_stages -q -p no:faulthandler
```

期望：FAIL，`AssertionError`（断言 `len(pages) == len(stage_names) == 4` 触发）

- [ ] **Step 3: 修改 wizard_host.py**

打开 `drama_shot_master/ui/widgets/screenwriter/wizard_host.py`，将第 20 行：

```python
        assert len(pages) == len(stage_names) == 4
```

改为：

```python
        assert len(pages) == len(stage_names)
```

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_wizard_host.py -q -p no:faulthandler
```

期望：全绿（原有 3 个 + 新增 2 个 = 5 个）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/wizard_host.py \
        tests/test_ui/screenwriter/test_wizard_host.py
git commit -m "feat(wizard): 去掉 ==4 断言，支持任意阶段数"
```

---

## Task 2: ScriptPage 加 `highlight_generate_button()` + `_idea_hint_banner`

**Files:**
- Modify: `drama_shot_master/ui/widgets/screenwriter/script_page.py`
- Test: `tests/test_ui/screenwriter/test_script_page.py`

- [ ] **Step 1: 写失败测试（追加到 test_script_page.py 末尾）**

```python
def test_highlight_generate_button_shows_banner(tmp_path):
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    assert p._idea_hint_banner.isHidden()
    p.highlight_generate_button("守株待兔")
    assert not p._idea_hint_banner.isHidden()
    assert "守株待兔" in p._idea_hint_banner.text()


def test_highlight_generate_button_changes_style(tmp_path):
    _app()
    _setup_idea(tmp_path)
    p = ScriptPage(_StubClient())
    p.set_project(tmp_path)
    orig_style = p._gen_btn.styleSheet()
    p.highlight_generate_button("test")
    new_style = p._gen_btn.styleSheet()
    assert new_style != orig_style
    assert "#52b788" in new_style or "#2d6a4f" in new_style
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_script_page.py::test_highlight_generate_button_shows_banner -q -p no:faulthandler
```

期望：FAIL，`AttributeError: 'ScriptPage' object has no attribute '_idea_hint_banner'`

- [ ] **Step 3: 修改 script_page.py**

在 `_build_ui` 里，找到 `root.addLayout(self._build_param_bar())` 那行之后、`self._upstream_banner = _UpstreamBanner()` 之前，插入：

```python
        # 创意来源提示条（从创意推进时高亮）
        self._idea_hint_banner = QLabel("")
        self._idea_hint_banner.setStyleSheet(
            "QLabel { background: #1a3a2a; color: #95e5b8; "
            "border: 1px solid #52b788; border-radius: 4px; padding: 4px 8px; }")
        self._idea_hint_banner.hide()
        root.addWidget(self._idea_hint_banner)
```

然后在 `ScriptPage` 类末尾（`set_project` 方法之后）追加：

```python
    def highlight_generate_button(self, idea_title: str = "") -> None:
        """从创意推进过来时调用，高亮生成按钮 + 显示来源提示。"""
        self._gen_btn.setStyleSheet(
            "QPushButton { background: #2d6a4f; color: #95e5b8; "
            "border: 2px solid #52b788; border-radius: 5px; "
            "padding: 4px 14px; font-weight: bold; }")
        if idea_title:
            self._idea_hint_banner.setText(
                f"💡 从「{idea_title}」已选定 · 点击上方按钮开始生成")
            self._idea_hint_banner.show()
        self._gen_btn_highlighted = True
```

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_script_page.py -q -p no:faulthandler
```

期望：全绿

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/script_page.py \
        tests/test_ui/screenwriter/test_script_page.py
git commit -m "feat(script_page): + highlight_generate_button() + _idea_hint_banner"
```

---

## Task 3: screenwriter_panel 推进→剧本触发高亮

**Files:**
- Modify: `drama_shot_master/ui/panels/screenwriter_panel.py`
- Test: `tests/test_ui/screenwriter/test_screenwriter_panel.py`

- [ ] **Step 1: 写失败测试（追加到 test_screenwriter_panel.py 末尾）**

```python
def test_advance_to_script_calls_highlight(tmp_path):
    _app()
    import json
    pA = tmp_path / "A"; pA.mkdir()
    (pA / "创意.json").write_text(json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "守株待兔"}],
    }), encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)
    # 选中项目
    panel._last_selected = pA
    for pg in panel._pages:
        if hasattr(pg, "set_project"):
            pg.set_project(pA)
    # 触发推进到剧本（idx=1）
    panel._on_stage_advance_requested(1)
    script_page = panel._pages[1]
    # banner 应该已显示且含标题
    assert not script_page._idea_hint_banner.isHidden()
    assert "守株待兔" in script_page._idea_hint_banner.text()
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py::test_advance_to_script_calls_highlight -q -p no:faulthandler
```

期望：FAIL（`_idea_hint_banner` 仍为隐藏，因为 `_on_stage_advance_requested` 还没读创意标题）

- [ ] **Step 3: 修改 screenwriter_panel.py**

找到文件末尾的 `_on_stage_advance_requested` 方法，替换为：

```python
    def _on_stage_advance_requested(self, idx: int) -> None:
        """上一阶段「推进」→ 切到 idx + 让目标 page 自动尝试启动生成。"""
        if idx == 1:
            idea_title = self._get_selected_idea_title()
            script_page = self._pages[1]
            if hasattr(script_page, "highlight_generate_button"):
                script_page.highlight_generate_button(idea_title)
        self._wizard_host.set_stage(idx)
        if 0 <= idx < len(self._pages):
            target = self._pages[idx]
            if hasattr(target, "start_generation_if_idle"):
                target.start_generation_if_idle()

    def _get_selected_idea_title(self) -> str:
        """读当前项目的 创意.json 中选定候选的标题。"""
        if self._last_selected is None:
            return ""
        idea_path = self._last_selected / "创意.json"
        if not idea_path.is_file():
            return ""
        try:
            import json
            data = json.loads(idea_path.read_text(encoding="utf-8"))
            sel_id = data.get("selected_id", "")
            for c in data.get("candidates", []):
                if c.get("id") == sel_id:
                    return c.get("title", "")
        except Exception:
            pass
        return ""
```

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py -q -p no:faulthandler
```

期望：全绿

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/screenwriter_panel.py \
        tests/test_ui/screenwriter/test_screenwriter_panel.py
git commit -m "feat(panel): 推进→剧本时读创意标题并触发 highlight_generate_button"
```

---

## Task 4: 三个 Agent 模板文件 + template_loader 注册

**Files:**
- Create: `screenwriter_agent/templates/image_prompts.md`
- Create: `screenwriter_agent/templates/video_prompts.md`
- Create: `screenwriter_agent/templates/audio_prompts.md`
- Modify: `screenwriter_agent/templates/template_loader.py`
- Test: `tests/test_screenwriter_agent/test_template_loader.py`

- [ ] **Step 1: 写失败测试（追加到 test_template_loader.py 末尾）**

```python
def test_new_builtin_ids_registered():
    assert "image_prompts" in tl.BUILTIN_IDS
    assert "video_prompts" in tl.BUILTIN_IDS
    assert "audio_prompts" in tl.BUILTIN_IDS


def test_image_prompts_template_loadable(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    text, src = tl.load_template("image_prompts")
    assert src == "builtin"
    assert "SeedDream" in text or "Panel" in text or "宫格" in text


def test_video_prompts_template_loadable(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    text, src = tl.load_template("video_prompts")
    assert src == "builtin"
    assert "LTX" in text or "global_prompt" in text


def test_audio_prompts_template_loadable(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "GLOBAL_TEMPLATE_DIR", tmp_path / "global")
    text, src = tl.load_template("audio_prompts")
    assert src == "builtin"
    assert "音色" in text or "BGM" in text
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_screenwriter_agent/test_template_loader.py::test_new_builtin_ids_registered -q -p no:faulthandler
```

期望：FAIL，`AssertionError`（新 ID 未注册）

- [ ] **Step 3: 修改 template_loader.py 的 BUILTIN_IDS**

将：
```python
BUILTIN_IDS = ("ideate", "script", "script_outline", "script_episode",
                "storyboard", "character_ref", "grid_prompt")
```
改为：
```python
BUILTIN_IDS = ("ideate", "script", "script_outline", "script_episode",
                "storyboard", "character_ref", "grid_prompt",
                "image_prompts", "video_prompts", "audio_prompts")
```

- [ ] **Step 4: 新建 `screenwriter_agent/templates/image_prompts.md`**

```markdown
你是一名专业分镜图提示词工程师。任务：根据分镜 JSON 为每组镜头生成 SeedDream 多格提示词。

## 输入
- 分镜 JSON（包含 characters + shots）
- 格式：9宫格 / 4宫格 / 单帧（由调用方在 "格式" 字段指定）
- 参数：style_extra（画风额外描述）

## 输出格式
对每组镜头输出一段完整的 SeedDream prompt，格式严格如下：

## 第N组（M宫格）S{start}-S{end}
**角色参考：** {角色名}_ref
**提示词：**
Panel 1: {描述}. Panel 2: {描述}. Panel 3: {描述}...

## 要求
- 每 Panel 用句号 + 空格分隔，保持英文描述
- 每组必须包含构图类型（中景/近景/远景/特写）+ 光线描述 + 氛围词
- 风格统一贯穿全部 Panel（古风水墨 / 现代写实 / 赛博朋克 等）
- 每组不超过 1500 字符
- 输出纯 Markdown，不要包含 JSON、代码块
- 所有组按顺序连续输出，不要有额外分割线
```

- [ ] **Step 5: 新建 `screenwriter_agent/templates/video_prompts.md`**

```markdown
你是一名 LTX-2.3 视频提示词专家。任务：根据分镜 JSON 生成 global_prompt 和每个镜头的 local_prompt。

## 输入
- 分镜 JSON（包含 globalStyle + characters + shots）
- 参数：video_model（默认 LTX-2.3）、aspect_ratio、fps

## 输出格式（严格 JSON，不要包含任何 Markdown 代码块标记）
{
  "global_prompt": "整体风格描述，包含视觉风格/色调/摄影基调，面向 LTX-2.3",
  "shots": [
    {"shot_id": "S01", "local_prompt": "Camera: ..., Subject: ..., Action: ..., Lighting: ...", "duration": 4.5},
    ...
  ]
}

## LTX-2.3 提示词规范
- global_prompt：风格词 + 技术参数（如 9:16 portrait, cinematic, 24fps）+ 整体色调（如 warm amber, cool blue）
- local_prompt 固定结构：Camera: {摄像机动作}, Subject: {主体描述}, Action: {动作/状态}, Lighting: {光线}, Mood: {情绪}
- duration：直接从 shot.duration 取，单位秒，类型为数字
- shot_id：与输入 shots[i].shotId 对应
- 输出必须是合法 JSON，不得有尾逗号或注释
```

- [ ] **Step 6: 新建 `screenwriter_agent/templates/audio_prompts.md`**

```markdown
你是一名专业配音配乐顾问。任务：根据分镜 JSON 和剧本生成角色音色卡 + 分镜配音配乐匹配表。

## 输入
- 分镜 JSON（包含 characters + shots + description）
- 剧本 md（提取台词，如果提供）

## 输出格式（Markdown）

# 配音配乐提示词 {episode_id}

## 角色音色卡

### {角色名}（{角色类型}）
- 性别：{性别} · 年龄：{年龄估计}
- 语调：{语调特点}
- 情绪范围：{情绪1} / {情绪2} / {情绪3}
- 声线描述：{声线参考，如「中音偏低，略带沙哑，犹如深秋落叶」}

## 分镜配音配乐匹配表

| ID | 角色 | 台词/旁白 | 音效提示 | BGM情绪 |
|---|---|---|---|---|
| S01 | {角色或旁白OS} | {台词文本，无台词写（无台词）} | {音效描述，如「雨声·风声」} | {BGM情绪词，如「悲切·慢板」} |

## 要求
- 从剧本 md 中按时序匹配每个 shot 对应的台词
- 若无台词则标「（无台词）」并给情绪/音效建议
- BGM情绪词用中文（悲切/温柔/紧张/欢快/静默/庄严 等）
- 音效提示用简短中文描述，多个用「·」连接
- 完整输出全部镜头行，不要省略
```

- [ ] **Step 7: 运行验证 PASS**

```
python -m pytest tests/test_screenwriter_agent/test_template_loader.py -q -p no:faulthandler
```

期望：全绿（注意旧的 `test_builtin_ids_set` 会因为新 ID 而需要更新——该测试检查精确集合，需同步修改该测试）

找到 `test_template_loader.py` 中的 `test_builtin_ids_set` 测试，将其更新为：

```python
def test_builtin_ids_set():
    assert set(tl.BUILTIN_IDS) == {"ideate", "script", "script_outline",
                                   "script_episode", "storyboard",
                                   "character_ref", "grid_prompt",
                                   "image_prompts", "video_prompts", "audio_prompts"}
```

再次运行确认全绿。

- [ ] **Step 8: Commit**

```bash
git add screenwriter_agent/templates/template_loader.py \
        screenwriter_agent/templates/image_prompts.md \
        screenwriter_agent/templates/video_prompts.md \
        screenwriter_agent/templates/audio_prompts.md \
        tests/test_screenwriter_agent/test_template_loader.py
git commit -m "feat(templates): + image_prompts/video_prompts/audio_prompts 模板 + BUILTIN_IDS 注册"
```

---

## Task 5: POST /image_prompts 路由

**Files:**
- Create: `screenwriter_agent/routes/image_prompts.py`
- Modify: `screenwriter_agent/server.py`
- Create: `tests/test_screenwriter_agent/test_route_image_prompts.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_screenwriter_agent/test_route_image_prompts.py`：

```python
"""POST /image_prompts 路由测试。"""
import json
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def _setup_storyboard(tmp_path):
    sb = {
        "title": "守株待兔",
        "globalStyle": "古风水墨，淡雅，柔光",
        "characters": [{"name": "周翠英", "appearance": "白衣长裙，黑发及腰"}],
        "shots": [
            {"shotId": "S01", "duration": 4, "composition": "远景",
             "description": "雨夜松林，女子伫立", "stylePrompt": "古风水墨"},
            {"shotId": "S02", "duration": 3, "composition": "中景",
             "description": "女子转身，衣袂飘动", "stylePrompt": "古风水墨"},
        ],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def mock_llm_image(monkeypatch):
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        raw = (
            "## 第1组（9宫格）S01-S02\n"
            "**角色参考：** 周翠英_ref\n"
            "**提示词：**\n"
            "Panel 1: Ancient ink painting, rainy night pine forest, woman in white standing. "
            "Panel 2: Medium shot, woman turning, robes flowing, warm light."
        )
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_route_image_prompts_writes_md(tmp_path, mock_llm_image):
    _setup_storyboard(tmp_path)
    c = TestClient(create_app())
    r = c.post("/image_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "image_prompts_E1.md").is_file()
    content = (tmp_path / "image_prompts_E1.md").read_text(encoding="utf-8")
    assert len(content) > 0


def test_route_image_prompts_sse_done_event(tmp_path, mock_llm_image):
    _setup_storyboard(tmp_path)
    c = TestClient(create_app())
    r = c.post("/image_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert "event: done" in r.text
    assert "image_prompts_E1.md" in r.text


def test_route_image_prompts_missing_storyboard_returns_400(tmp_path, mock_llm_image):
    c = TestClient(create_app())
    r = c.post("/image_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 400
    assert "UPSTREAM_PRODUCT_MISSING" in r.text


def test_route_image_prompts_bad_project_dir(mock_llm_image):
    c = TestClient(create_app())
    r = c.post("/image_prompts", json={
        "project_dir": "/nonexistent/path_xyz", "episode_id": "E1", "options": {}})
    assert r.status_code == 400
    assert "PROJECT_DIR_NOT_FOUND" in r.text


def test_route_image_prompts_sse_delta_events(tmp_path, mock_llm_image):
    _setup_storyboard(tmp_path)
    c = TestClient(create_app())
    r = c.post("/image_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert "event: delta" in r.text
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_screenwriter_agent/test_route_image_prompts.py -q -p no:faulthandler
```

期望：FAIL，路由 `/image_prompts` 返回 404

- [ ] **Step 3: 新建 `screenwriter_agent/routes/image_prompts.py`**

```python
"""POST /image_prompts — SSE：读分镜JSON → LLM 生成分镜图提示词 → 落盘。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import storyboard_episode_read_path
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import PromptsReq

router = APIRouter()


@router.post("/image_prompts")
async def image_prompts(req: PromptsReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": str(project_dir), "hint": "项目目录不存在。"}})
    sb_path = storyboard_episode_read_path(project_dir, req.episode_id)
    if sb_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": f"分镜_{req.episode_id}.json missing",
                      "hint": "请先在「分镜」步生成该集。"}})

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_SCRIPT_MODEL")
             or cfg.default_models.get("script"))
    creds = req.creds or None
    api_key = ((creds.api_key if creds else None)
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = ((creds.base_url if creds else None)
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))

    async def gen():
        import traceback
        try:
            sb = json.loads(sb_path.read_text(encoding="utf-8"))
            tpl, _ = load_template("image_prompts", project_dir=project_dir)
            opts = req.options.model_dump() if req.options else {}
            grid_mode = opts.get("grid_mode", "9")
            style_extra = opts.get("style_extra", "")
            prompt = (
                tpl
                + "\n\n## 分镜数据\n```json\n"
                + json.dumps(sb, ensure_ascii=False, indent=2)
                + "\n```\n\n"
                + f"格式: {grid_mode}宫格\n"
                + f"style_extra: {style_extra}\n"
            )
            messages = [{"role": "user", "content": prompt}]
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)
            yield sse_event("status", {"phase": "generating"})
            acc: list[str] = []
            for c in client.stream_chat(messages):
                if await request.is_disconnected():
                    return
                if c.kind == "delta":
                    acc.append(c.text)
                    yield sse_event("delta", {"text": c.text})
            text = "".join(acc)
            out_path = project_dir / f"image_prompts_{req.episode_id}.md"
            atomic_write_text(out_path, text)
            yield sse_event("done", {
                "saved": str(out_path),
                "episode_id": req.episode_id,
            })
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[image_prompts] EXCEPTION\n{tb}", flush=True)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "hint": "查看 agent log",
            })

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: 在 server.py 注册路由**

在 `create_app()` 里 `from .routes.prompts import ...` 那行之后，追加：

```python
    from .routes.image_prompts import router as image_prompts_router
    app.include_router(image_prompts_router)
```

- [ ] **Step 5: 运行验证 PASS**

```
python -m pytest tests/test_screenwriter_agent/test_route_image_prompts.py -q -p no:faulthandler
```

期望：5 个全绿

- [ ] **Step 6: Commit**

```bash
git add screenwriter_agent/routes/image_prompts.py \
        screenwriter_agent/server.py \
        tests/test_screenwriter_agent/test_route_image_prompts.py
git commit -m "feat(agent): + POST /image_prompts SSE 路由"
```

---

## Task 6: POST /video_prompts 路由

**Files:**
- Create: `screenwriter_agent/routes/video_prompts.py`
- Modify: `screenwriter_agent/server.py`
- Create: `tests/test_screenwriter_agent/test_route_video_prompts.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_screenwriter_agent/test_route_video_prompts.py`：

```python
"""POST /video_prompts 路由测试。"""
import json
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def _setup_storyboard(tmp_path):
    sb = {
        "title": "守株待兔",
        "globalStyle": "古风水墨，淡雅，柔光",
        "characters": [{"name": "周翠英", "appearance": "白衣长裙"}],
        "shots": [
            {"shotId": "S01", "duration": 4.5, "composition": "远景",
             "description": "雨夜松林", "stylePrompt": "古风水墨"},
            {"shotId": "S02", "duration": 3.0, "composition": "中景",
             "description": "女子转身", "stylePrompt": "古风水墨"},
        ],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def mock_llm_video(monkeypatch):
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        raw = json.dumps({
            "global_prompt": "Ancient ink painting style, 9:16 portrait, cinematic, 24fps, warm amber tones",
            "shots": [
                {"shot_id": "S01", "local_prompt": "Camera: slow push in, Subject: woman in white, Action: standing still, Lighting: soft moonlight, Mood: melancholic", "duration": 4.5},
                {"shot_id": "S02", "local_prompt": "Camera: medium shot static, Subject: woman turning, Action: robes flowing, Lighting: warm candlelight, Mood: longing", "duration": 3.0},
            ],
        }, ensure_ascii=False)
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_route_video_prompts_writes_json_and_md(tmp_path, mock_llm_video):
    _setup_storyboard(tmp_path)
    c = TestClient(create_app())
    r = c.post("/video_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "video_prompts_E1.json").is_file()
    assert (tmp_path / "video_prompts_E1.md").is_file()


def test_route_video_prompts_json_structure(tmp_path, mock_llm_video):
    _setup_storyboard(tmp_path)
    c = TestClient(create_app())
    c.post("/video_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    obj = json.loads((tmp_path / "video_prompts_E1.json").read_text(encoding="utf-8"))
    assert "global_prompt" in obj
    assert "shots" in obj
    assert len(obj["shots"]) >= 1
    assert "shot_id" in obj["shots"][0]
    assert "local_prompt" in obj["shots"][0]


def test_route_video_prompts_missing_storyboard_returns_400(tmp_path, mock_llm_video):
    c = TestClient(create_app())
    r = c.post("/video_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 400
    assert "UPSTREAM_PRODUCT_MISSING" in r.text


def test_route_video_prompts_bad_project_dir(mock_llm_video):
    c = TestClient(create_app())
    r = c.post("/video_prompts", json={
        "project_dir": "/nonexistent/path_xyz", "episode_id": "E1", "options": {}})
    assert r.status_code == 400
    assert "PROJECT_DIR_NOT_FOUND" in r.text


def test_route_video_prompts_md_contains_global_prompt(tmp_path, mock_llm_video):
    _setup_storyboard(tmp_path)
    c = TestClient(create_app())
    c.post("/video_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    md = (tmp_path / "video_prompts_E1.md").read_text(encoding="utf-8")
    assert "global_prompt" in md
    assert "S01" in md
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_screenwriter_agent/test_route_video_prompts.py -q -p no:faulthandler
```

期望：FAIL，404

- [ ] **Step 3: 新建 `screenwriter_agent/routes/video_prompts.py`**

```python
"""POST /video_prompts — SSE：读分镜JSON → LLM 生成 LTX-2.3 提示词 → 落盘 JSON+MD。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.json_repair import repair_json_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import storyboard_episode_read_path
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import PromptsReq

router = APIRouter()


@router.post("/video_prompts")
async def video_prompts(req: PromptsReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": str(project_dir), "hint": "项目目录不存在。"}})
    sb_path = storyboard_episode_read_path(project_dir, req.episode_id)
    if sb_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": f"分镜_{req.episode_id}.json missing",
                      "hint": "请先在「分镜」步生成该集。"}})

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_SCRIPT_MODEL")
             or cfg.default_models.get("script"))
    creds = req.creds or None
    api_key = ((creds.api_key if creds else None)
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = ((creds.base_url if creds else None)
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))

    async def gen():
        import traceback
        try:
            sb = json.loads(sb_path.read_text(encoding="utf-8"))
            tpl, _ = load_template("video_prompts", project_dir=project_dir)
            opts = req.options.model_dump() if req.options else {}
            aspect_ratio = opts.get("aspect_ratio", "9:16") if isinstance(opts, dict) else "9:16"
            prompt = (
                tpl
                + "\n\n## 分镜数据\n```json\n"
                + json.dumps(sb, ensure_ascii=False, indent=2)
                + "\n```\n\n"
                + f"video_model: LTX-2.3\n"
                + f"aspect_ratio: {aspect_ratio}\n"
                + f"fps: 24\n"
            )
            messages = [{"role": "user", "content": prompt}]
            client = LLMClient(
                api_key=api_key, base_url=base_url, model=model,
                reasoning_effort=req.reasoning_effort,
                response_format={"type": "json_object"})
            yield sse_event("status", {"phase": "generating"})
            acc: list[str] = []
            for c in client.stream_chat(messages):
                if await request.is_disconnected():
                    return
                if c.kind == "delta":
                    acc.append(c.text)
                    yield sse_event("delta", {"text": c.text})
            raw = "".join(acc)
            result = repair_json_text(raw)
            if not result.ok:
                yield sse_event("error", {
                    "code": "JSON_REPAIR_FAILED",
                    "message": result.error,
                    "hint": "LLM 返回非合法 JSON，请重试",
                })
                return
            obj = result.obj

            json_path = project_dir / f"video_prompts_{req.episode_id}.json"
            atomic_write_text(json_path,
                              json.dumps(obj, ensure_ascii=False, indent=2))

            # 生成 Markdown
            lines = [
                f"# 视频提示词 {req.episode_id}\n\n",
                f"## global_prompt\n\n{obj.get('global_prompt', '')}\n\n",
                "## 镜头提示词\n\n",
                "| ID | local_prompt | 时长(s) |\n",
                "|---|---|---|\n",
            ]
            for s in obj.get("shots", []):
                sid = s.get("shot_id", "")
                lp = s.get("local_prompt", "")
                dur = s.get("duration", "")
                lines.append(f"| {sid} | {lp} | {dur} |\n")
            md_path = project_dir / f"video_prompts_{req.episode_id}.md"
            atomic_write_text(md_path, "".join(lines))

            yield sse_event("done", {
                "saved_json": str(json_path),
                "saved_md": str(md_path),
                "episode_id": req.episode_id,
            })
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[video_prompts] EXCEPTION\n{tb}", flush=True)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "hint": "查看 agent log",
            })

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: 在 server.py 注册路由**

在 image_prompts 那行之后追加：

```python
    from .routes.video_prompts import router as video_prompts_router
    app.include_router(video_prompts_router)
```

- [ ] **Step 5: 运行验证 PASS**

```
python -m pytest tests/test_screenwriter_agent/test_route_video_prompts.py -q -p no:faulthandler
```

期望：5 个全绿

- [ ] **Step 6: Commit**

```bash
git add screenwriter_agent/routes/video_prompts.py \
        screenwriter_agent/server.py \
        tests/test_screenwriter_agent/test_route_video_prompts.py
git commit -m "feat(agent): + POST /video_prompts SSE 路由（JSON+MD 双产物）"
```

---

## Task 7: POST /audio_prompts 路由

**Files:**
- Create: `screenwriter_agent/routes/audio_prompts.py`
- Modify: `screenwriter_agent/server.py`
- Create: `tests/test_screenwriter_agent/test_route_audio_prompts.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_screenwriter_agent/test_route_audio_prompts.py`：

```python
"""POST /audio_prompts 路由测试。"""
import json
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def _setup_full(tmp_path):
    sb = {
        "title": "守株待兔",
        "globalStyle": "古风",
        "characters": [
            {"name": "周翠英", "appearance": "白衣"},
            {"name": "李书生", "appearance": "青衫"},
        ],
        "shots": [
            {"shotId": "S01", "duration": 4, "composition": "远景",
             "description": "雨夜", "stylePrompt": "古风"},
            {"shotId": "S02", "duration": 3, "composition": "中景",
             "description": "对话", "stylePrompt": "古风"},
        ],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text(
        "# 守株待兔 E1\n\n## 镜头S01\n旁白OS: 世人皆说守株待兔是愚...\n\n## 镜头S02\n李书生: 姑娘留步。\n",
        encoding="utf-8")


@pytest.fixture
def mock_llm_audio(monkeypatch):
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        raw = (
            "# 配音配乐提示词 E1\n\n"
            "## 角色音色卡\n\n"
            "### 周翠英（女主）\n"
            "- 性别：女 · 年龄：25岁\n"
            "- 语调：清冽柔和\n"
            "- 情绪范围：平静 / 悲切 / 坚定\n"
            "- 声线描述：中音偏高，清澈如泉\n\n"
            "## 分镜配音配乐匹配表\n\n"
            "| ID | 角色 | 台词/旁白 | 音效提示 | BGM情绪 |\n"
            "|---|---|---|---|---|\n"
            "| S01 | 旁白OS | 世人皆说守株待兔是愚... | 雨声·风声 | 悲切·慢板 |\n"
            "| S02 | 李书生 | 姑娘留步。 | — | 温柔·中板 |\n"
        )
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_route_audio_prompts_writes_md(tmp_path, mock_llm_audio):
    _setup_full(tmp_path)
    c = TestClient(create_app())
    r = c.post("/audio_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "audio_prompts_E1.md").is_file()
    content = (tmp_path / "audio_prompts_E1.md").read_text(encoding="utf-8")
    assert len(content) > 0


def test_route_audio_prompts_missing_storyboard_returns_400(tmp_path, mock_llm_audio):
    c = TestClient(create_app())
    r = c.post("/audio_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 400
    assert "UPSTREAM_PRODUCT_MISSING" in r.text


def test_route_audio_prompts_no_script_still_generates(tmp_path, mock_llm_audio):
    """缺剧本 md 时降级不报错，仍能生成 audio_prompts_E1.md。"""
    sb = {
        "title": "x", "globalStyle": "古风",
        "characters": [{"name": "周翠英", "appearance": "白衣"}],
        "shots": [{"shotId": "S01", "duration": 4, "composition": "远景",
                   "description": "雨夜", "stylePrompt": "古风"}],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    # 故意不写 剧本_E1.md
    c = TestClient(create_app())
    r = c.post("/audio_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "audio_prompts_E1.md").is_file()
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_screenwriter_agent/test_route_audio_prompts.py -q -p no:faulthandler
```

期望：FAIL，404

- [ ] **Step 3: 新建 `screenwriter_agent/routes/audio_prompts.py`**

```python
"""POST /audio_prompts — SSE：读分镜JSON + 剧本md → LLM 生成配音配乐提示词 → 落盘。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screenwriter_agent.core.atomic_write import atomic_write_text
from screenwriter_agent.core.llm_client import LLMClient
from screenwriter_agent.core.paths import (
    storyboard_episode_read_path,
    script_episode_read_path,
)
from screenwriter_agent.core.sse import sse_event
from screenwriter_agent.core.template_loader import load_template
from screenwriter_agent.models.requests import PromptsReq

router = APIRouter()


@router.post("/audio_prompts")
async def audio_prompts(req: PromptsReq, request: Request):
    project_dir = Path(req.project_dir)
    if not project_dir.is_dir():
        return JSONResponse(status_code=400, content={
            "error": {"code": "PROJECT_DIR_NOT_FOUND",
                      "message": str(project_dir), "hint": "项目目录不存在。"}})
    sb_path = storyboard_episode_read_path(project_dir, req.episode_id)
    if sb_path is None:
        return JSONResponse(status_code=400, content={
            "error": {"code": "UPSTREAM_PRODUCT_MISSING",
                      "message": f"分镜_{req.episode_id}.json missing",
                      "hint": "请先在「分镜」步生成该集。"}})

    cfg = request.app.state.cfg
    model = (req.model
             or os.environ.get("SCREENWRITER_SCRIPT_MODEL")
             or cfg.default_models.get("script"))
    creds = req.creds or None
    api_key = ((creds.api_key if creds else None)
               or os.environ.get("SCREENWRITER_LLM_API_KEY", ""))
    base_url = ((creds.base_url if creds else None)
                or os.environ.get("SCREENWRITER_LLM_BASE_URL",
                                   "https://api.deepseek.com"))

    async def gen():
        import traceback
        try:
            sb = json.loads(sb_path.read_text(encoding="utf-8"))
            tpl, _ = load_template("audio_prompts", project_dir=project_dir)

            # 剧本 md（可选，缺失时降级）
            script_md = ""
            script_path = script_episode_read_path(project_dir, req.episode_id)
            if script_path is not None:
                try:
                    script_md = script_path.read_text(encoding="utf-8")
                except Exception:
                    pass

            prompt = (
                tpl
                + "\n\n## 分镜数据\n```json\n"
                + json.dumps(sb, ensure_ascii=False, indent=2)
                + "\n```\n\n"
            )
            if script_md:
                prompt += f"## 剧本\n\n{script_md}\n\n"
            else:
                prompt += "## 剧本\n\n（无剧本，请根据分镜描述推断台词）\n\n"
            prompt += f"episode_id: {req.episode_id}\n"

            messages = [{"role": "user", "content": prompt}]
            client = LLMClient(api_key=api_key, base_url=base_url, model=model,
                               reasoning_effort=req.reasoning_effort)
            yield sse_event("status", {"phase": "generating"})
            acc: list[str] = []
            for c in client.stream_chat(messages):
                if await request.is_disconnected():
                    return
                if c.kind == "delta":
                    acc.append(c.text)
                    yield sse_event("delta", {"text": c.text})
            text = "".join(acc)
            out_path = project_dir / f"audio_prompts_{req.episode_id}.md"
            atomic_write_text(out_path, text)
            yield sse_event("done", {
                "saved": str(out_path),
                "episode_id": req.episode_id,
            })
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[audio_prompts] EXCEPTION\n{tb}", flush=True)
            yield sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "hint": "查看 agent log",
            })

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: 在 server.py 注册路由**

```python
    from .routes.audio_prompts import router as audio_prompts_router
    app.include_router(audio_prompts_router)
```

- [ ] **Step 5: 运行验证 PASS**

```
python -m pytest tests/test_screenwriter_agent/test_route_audio_prompts.py -q -p no:faulthandler
```

期望：3 个全绿

- [ ] **Step 6: Commit**

```bash
git add screenwriter_agent/routes/audio_prompts.py \
        screenwriter_agent/server.py \
        tests/test_screenwriter_agent/test_route_audio_prompts.py
git commit -m "feat(agent): + POST /audio_prompts SSE 路由（音色卡+分镜匹配表）"
```

---

## Task 8: `_BasePromptsPage` 共用基类

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/_base_prompts_page.py`
- Create: `tests/test_ui/screenwriter/test_base_prompts_page.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_ui/screenwriter/test_base_prompts_page.py`：

```python
"""_BasePromptsPage smoke 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QLabel

from drama_shot_master.ui.widgets.screenwriter._base_prompts_page import _BasePromptsPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


class _ConcretePromptsPage(_BasePromptsPage):
    """最小具体实现，用于 smoke 测试基类。"""

    def _endpoint(self) -> str:
        return "/image_prompts"

    def _output_filename(self, ep: str) -> str:
        return f"image_prompts_{ep}.md"

    def _build_result_widget(self):
        return QLabel("result")

    def _on_partial(self, data: dict) -> None:
        pass


def test_base_prompts_page_builds_without_crash():
    _app()
    p = _ConcretePromptsPage(_StubClient())
    assert p is not None
    assert hasattr(p, "_gen_btn")
    assert hasattr(p, "_stop_btn")
    assert hasattr(p, "_upstream_banner")


def test_base_prompts_page_upstream_banner_hidden_initially():
    _app()
    p = _ConcretePromptsPage(_StubClient())
    assert p._upstream_banner.isHidden()


def test_base_prompts_page_episode_selector_exists():
    _app()
    p = _ConcretePromptsPage(_StubClient())
    assert hasattr(p, "_episode_selector")
    assert p._episode_selector is not None


def test_base_prompts_page_set_project_none_disables_gen():
    _app()
    p = _ConcretePromptsPage(_StubClient())
    p.set_project(None)
    assert not p._gen_btn.isEnabled()


def test_base_prompts_page_set_project_missing_storyboard_shows_banner(tmp_path):
    _app()
    # 不创建分镜文件
    p = _ConcretePromptsPage(_StubClient())
    p.set_project(tmp_path)
    # 上游 banner 应显示（分镜缺失）
    assert not p._upstream_banner.isHidden()
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_base_prompts_page.py -q -p no:faulthandler
```

期望：FAIL，无法 import `_BasePromptsPage`

- [ ] **Step 3: 新建 `drama_shot_master/ui/widgets/screenwriter/_base_prompts_page.py`**

```python
"""_BasePromptsPage：Stage 4/5/6 共用基类。

顶部 _EpisodeSelector + _UpstreamBanner + 流式状态标 + [生成] / [中止] + 结果区。
子类必须实现：_endpoint / _output_filename / _build_result_widget / _on_partial。
"""
from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from drama_shot_master.ui.widgets.screenwriter.base_stage_page import _BaseStagePage
from drama_shot_master.ui.widgets.screenwriter._episode_selector import _EpisodeSelector
from drama_shot_master.ui.widgets.screenwriter._upstream_banner import _UpstreamBanner
from drama_shot_master.ui.widgets.screenwriter.stream_worker import StreamWorker
from screenwriter_agent.core.paths import storyboard_episode_read_path


class _BasePromptsPage(_BaseStagePage):
    """Stage 4/5/6 分镜图/视频/配音配乐提示词共用基类。"""

    def __init__(self, client, parent=None):
        super().__init__(client, parent)
        self._current_episode: str = "E1"
        self._build_ui()
        self.set_project(None)

    # ── 子类必须实现 ──────────────────────────────────────────────────────

    @abstractmethod
    def _endpoint(self) -> str:
        """Agent 路由路径，如 '/image_prompts'。"""

    @abstractmethod
    def _output_filename(self, ep: str) -> str:
        """产物文件名，如 'image_prompts_E1.md'。"""

    @abstractmethod
    def _build_result_widget(self) -> QWidget:
        """构建并返回结果显示区域 widget。"""

    @abstractmethod
    def _on_partial(self, data: dict) -> None:
        """处理 SSE partial / delta 事件，更新结果区。"""

    # ── 公共 UI 构建 ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # 集数选择
        self._episode_selector = _EpisodeSelector()
        self._episode_selector.episodeChanged.connect(self._on_episode_changed)
        root.addWidget(self._episode_selector)

        # 上游缺失 banner
        self._upstream_banner = _UpstreamBanner()
        root.addWidget(self._upstream_banner)

        # 参数栏（子类可 override _build_param_bar 追加额外控件）
        param_bar = self._build_param_bar()
        if param_bar is not None:
            root.addLayout(param_bar)

        # 结果区（子类实现）
        self._result_widget = self._build_result_widget()
        root.addWidget(self._result_widget, 1)

        # 动作栏
        root.addLayout(self._build_action_bar())

    def _build_param_bar(self) -> QHBoxLayout | None:
        """默认参数栏：流式状态标 + [生成] + [中止]。子类可 override 以追加控件。"""
        bar = QHBoxLayout()
        self._stream_label = QLabel("")
        self._stream_label.setStyleSheet("color: #4a9eff")
        bar.addWidget(self._stream_label)
        bar.addStretch(1)
        self._gen_btn = QPushButton("生成提示词")
        self._gen_btn.setEnabled(False)
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        bar.addWidget(self._gen_btn)
        self._stop_btn = QPushButton("▣ 中止")
        self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._stop_stream)
        bar.addWidget(self._stop_btn)
        return bar

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进 →")
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        bar.addWidget(self._advance_btn)
        return bar

    # ── set_project / episode ──────────────────────────────────────────────

    def set_project(self, path: Path | None) -> None:
        self._project_dir = path
        self._episode_selector.set_project(path)
        if path is None:
            self._upstream_banner.hide_banner()
            self._gen_btn.setEnabled(False)
            return
        ep = self._episode_selector.current_episode() or "E1"
        self._current_episode = ep
        self._check_upstream(path, ep)

    def _check_upstream(self, project_dir: Path, ep: str) -> None:
        sb = storyboard_episode_read_path(project_dir, ep)
        if sb is None:
            self._upstream_banner.show_missing(
                stage_name="分镜", expected_file=f"分镜_{ep}.json")
            self._gen_btn.setEnabled(False)
        else:
            self._upstream_banner.hide_banner()
            self._gen_btn.setEnabled(True)

    def _on_episode_changed(self, ep: str) -> None:
        self._current_episode = ep
        if self._project_dir is not None:
            self._check_upstream(self._project_dir, ep)

    # ── 生成 / 中止 ────────────────────────────────────────────────────────

    def _on_generate_clicked(self) -> None:
        if self._project_dir is None:
            return
        ep = self._current_episode or "E1"
        body = {
            "project_dir": str(self._project_dir),
            "episode_id": ep,
            "options": self._build_options(),
        }
        key = (self._project_dir, ep)
        old = self._workers.get(key)
        if old and old.isRunning():
            return
        worker = StreamWorker(
            self._client, self._endpoint(), body, params=None,
            project_dir=self._project_dir)
        worker.event.connect(self._on_sse_event)
        worker.finished_ok.connect(self._on_stream_done_signal)
        worker.failed.connect(self._on_stream_failed)
        self._workers[key] = worker
        self._gen_btn.hide()
        self._stop_btn.show()
        self._stream_label.setText("生成中…")
        worker.start()

    def _build_options(self) -> dict:
        """默认空 options；子类 override 以注入格式参数等。"""
        return {}

    def _stop_stream(self) -> None:
        if self._project_dir is None:
            return
        ep = self._current_episode or "E1"
        w = self._workers.get((self._project_dir, ep))
        if w:
            w.stop()
        self._stop_btn.hide()
        self._gen_btn.show()
        self._stream_label.setText("已中止")

    def _on_sse_event(self, event: str, data: dict, proj_dir_str: str) -> None:
        if self._project_dir is None or str(self._project_dir) != proj_dir_str:
            return
        if event in ("delta", "partial"):
            self._on_partial(data)
        elif event == "status":
            phase = data.get("phase", "")
            self._stream_label.setText(f"状态: {phase}")
        elif event == "done":
            self._stream_label.setText("完成 ✓")
            self.projectStateChanged.emit()
        elif event == "error":
            msg = data.get("message", "未知错误")
            self._stream_label.setText(f"错误: {msg}")

    def _on_stream_done_signal(self, proj_dir_str: str) -> None:
        if self._project_dir and str(self._project_dir) == proj_dir_str:
            self._stop_btn.hide()
            self._gen_btn.show()

    def _on_stream_failed(self, msg: str, proj_dir_str: str) -> None:
        if self._project_dir and str(self._project_dir) == proj_dir_str:
            self._stream_label.setText(f"失败: {msg}")
            self._stop_btn.hide()
            self._gen_btn.show()

    def _on_advance_clicked(self) -> None:
        idx = self._advance_target_stage()
        self.stageAdvanceRequested.emit(idx)

    def _advance_target_stage(self) -> int:
        """子类 override 以返回推进到的阶段索引；默认 +1（相对于子类不知道自己的编号，
        所以返回一个哨兵值 -1，由 panel 决定）。"""
        return -1
```

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_base_prompts_page.py -q -p no:faulthandler
```

期望：5 个全绿

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/_base_prompts_page.py \
        tests/test_ui/screenwriter/test_base_prompts_page.py
git commit -m "feat(ui): + _BasePromptsPage 共用基类（Stage 4/5/6）"
```

---

## Task 9: ImagePromptsPage（Stage 4）

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/image_prompts_page.py`
- Create: `tests/test_ui/screenwriter/test_image_prompts_page.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_ui/screenwriter/test_image_prompts_page.py`：

```python
"""ImagePromptsPage 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.image_prompts_page import ImagePromptsPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _setup_storyboard(tmp_path):
    sb = {
        "title": "x", "globalStyle": "古风",
        "characters": [{"name": "周翠英", "appearance": "白衣"}],
        "shots": [{"shotId": "S01", "duration": 4, "composition": "远景",
                   "description": "雨夜", "stylePrompt": "古风"}],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")


def test_image_prompts_page_builds_without_crash():
    _app()
    p = ImagePromptsPage(_StubClient())
    assert p is not None
    assert hasattr(p, "_gen_btn")


def test_image_prompts_page_upstream_banner_shows_without_storyboard(tmp_path):
    _app()
    p = ImagePromptsPage(_StubClient())
    p.set_project(tmp_path)
    assert not p._upstream_banner.isHidden()


def test_image_prompts_page_gen_btn_enabled_with_storyboard(tmp_path):
    _app()
    _setup_storyboard(tmp_path)
    p = ImagePromptsPage(_StubClient())
    p.set_project(tmp_path)
    assert p._gen_btn.isEnabled()


def test_image_prompts_page_grid_buttons_exist():
    _app()
    p = ImagePromptsPage(_StubClient())
    assert hasattr(p, "_btn_9grid")
    assert hasattr(p, "_btn_4grid")
    assert hasattr(p, "_btn_single")


def test_image_prompts_page_endpoint():
    _app()
    p = ImagePromptsPage(_StubClient())
    assert p._endpoint() == "/image_prompts"
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_image_prompts_page.py -q -p no:faulthandler
```

期望：FAIL，无法 import `ImagePromptsPage`

- [ ] **Step 3: 新建 `drama_shot_master/ui/widgets/screenwriter/image_prompts_page.py`**

```python
"""ImagePromptsPage：Stage 4 分镜图提示词子面板。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QGroupBox, QPlainTextEdit, QApplication,
)

from drama_shot_master.ui.widgets.screenwriter._base_prompts_page import _BasePromptsPage


class ImagePromptsPage(_BasePromptsPage):

    def __init__(self, client, parent=None):
        self._grid_mode: str = "9"
        self._group_editors: list[QPlainTextEdit] = []
        self._current_editor: QPlainTextEdit | None = None
        super().__init__(client, parent)

    # ── 子类实现 ───────────────────────────────────────────────────────────

    def _endpoint(self) -> str:
        return "/image_prompts"

    def _output_filename(self, ep: str) -> str:
        return f"image_prompts_{ep}.md"

    def _build_result_widget(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._groups_layout = QVBoxLayout(container)
        self._groups_layout.setSpacing(6)
        self._groups_layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _on_partial(self, data: dict) -> None:
        text = data.get("text", "")
        if not text:
            return
        # 若当前没有编辑器（首次 delta），创建第一组
        if self._current_editor is None:
            self._current_editor = self._add_group_editor(group_index=1)
        self._current_editor.insertPlainText(text)

    # ── 额外控件：格式选择 ─────────────────────────────────────────────────

    def _build_param_bar(self) -> QHBoxLayout:
        bar = super()._build_param_bar()  # type: ignore[assignment]
        # 在生成按钮之前插入格式按钮组
        # 通过重新构建格式选择栏
        fmt_bar = QHBoxLayout()
        fmt_bar.addWidget(QLabel("格式:"))
        self._btn_9grid = QPushButton("9宫格")
        self._btn_9grid.setCheckable(True)
        self._btn_9grid.setChecked(True)
        self._btn_4grid = QPushButton("4宫格")
        self._btn_4grid.setCheckable(True)
        self._btn_single = QPushButton("单帧")
        self._btn_single.setCheckable(True)
        for btn, mode in ((self._btn_9grid, "9"), (self._btn_4grid, "4"),
                          (self._btn_single, "single")):
            btn.clicked.connect(lambda _checked, m=mode: self._set_grid_mode(m))
            fmt_bar.addWidget(btn)
        # 将格式栏插入到 stream_label 之前（通过重建）
        # 注意：_build_param_bar 已经构建了 bar，这里直接在末尾前插格式控件
        # 实际做法：重写整个 param bar
        full_bar = QHBoxLayout()
        full_bar.addLayout(fmt_bar)
        full_bar.addStretch(1)
        full_bar.addWidget(self._stream_label)
        full_bar.addWidget(self._gen_btn)
        full_bar.addWidget(self._stop_btn)
        return full_bar

    def _set_grid_mode(self, mode: str) -> None:
        self._grid_mode = mode
        for btn, m in ((self._btn_9grid, "9"), (self._btn_4grid, "4"),
                       (self._btn_single, "single")):
            btn.setChecked(m == mode)

    def _build_options(self) -> dict:
        return {"grid_mode": self._grid_mode, "style_extra": ""}

    # ── 辅助：动态添加分组卡片 ─────────────────────────────────────────────

    def _add_group_editor(self, group_index: int) -> QPlainTextEdit:
        box = QGroupBox(f"第{group_index}组")
        v = QVBoxLayout(box)
        editor = QPlainTextEdit()
        editor.setPlaceholderText("生成的提示词将显示在此…")
        copy_btn = QPushButton("📋 复制此组")
        copy_btn.setFixedWidth(90)
        copy_btn.clicked.connect(
            lambda _=False, e=editor: QApplication.clipboard().setText(
                e.toPlainText()))
        v.addWidget(editor)
        v.addWidget(copy_btn)
        # 插在 stretch 之前
        idx = self._groups_layout.count() - 1
        self._groups_layout.insertWidget(idx, box)
        self._group_editors.append(editor)
        return editor
```

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_image_prompts_page.py -q -p no:faulthandler
```

期望：5 个全绿

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/image_prompts_page.py \
        tests/test_ui/screenwriter/test_image_prompts_page.py
git commit -m "feat(ui): + ImagePromptsPage Stage 4（分镜图提示词，格式选择+分组卡片）"
```

---

## Task 10: VideoPromptsPage（Stage 5）

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/video_prompts_page.py`
- Create: `tests/test_ui/screenwriter/test_video_prompts_page.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_ui/screenwriter/test_video_prompts_page.py`：

```python
"""VideoPromptsPage 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.video_prompts_page import VideoPromptsPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _setup_storyboard(tmp_path):
    sb = {
        "title": "x", "globalStyle": "古风",
        "characters": [{"name": "周翠英", "appearance": "白衣"}],
        "shots": [{"shotId": "S01", "duration": 4, "composition": "远景",
                   "description": "雨夜", "stylePrompt": "古风"}],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")


def test_video_prompts_page_builds_without_crash():
    _app()
    p = VideoPromptsPage(_StubClient())
    assert p is not None


def test_video_prompts_page_upstream_banner_shows_without_storyboard(tmp_path):
    _app()
    p = VideoPromptsPage(_StubClient())
    p.set_project(tmp_path)
    assert not p._upstream_banner.isHidden()


def test_video_prompts_page_has_global_prompt_edit():
    _app()
    p = VideoPromptsPage(_StubClient())
    assert hasattr(p, "_global_edit")


def test_video_prompts_page_has_shots_table():
    _app()
    p = VideoPromptsPage(_StubClient())
    assert hasattr(p, "_table")
    assert p._table.columnCount() == 4


def test_video_prompts_page_export_buttons_exist():
    _app()
    p = VideoPromptsPage(_StubClient())
    assert hasattr(p, "_export_json_btn")
    assert hasattr(p, "_export_md_btn")
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_video_prompts_page.py -q -p no:faulthandler
```

期望：FAIL，无法 import `VideoPromptsPage`

- [ ] **Step 3: 新建 `drama_shot_master/ui/widgets/screenwriter/video_prompts_page.py`**

```python
"""VideoPromptsPage：Stage 5 视频提示词子面板。"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QHeaderView,
)

from drama_shot_master.ui.widgets.screenwriter._base_prompts_page import _BasePromptsPage


class VideoPromptsPage(_BasePromptsPage):

    def __init__(self, client, parent=None):
        self._accumulated_text: str = ""
        super().__init__(client, parent)

    # ── 子类实现 ───────────────────────────────────────────────────────────

    def _endpoint(self) -> str:
        return "/video_prompts"

    def _output_filename(self, ep: str) -> str:
        return f"video_prompts_{ep}.json"

    def _build_result_widget(self) -> QWidget:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        # global_prompt 区块
        gp_bar = QHBoxLayout()
        gp_bar.addWidget(QLabel("🌐 global_prompt"))
        self._copy_global_btn = QPushButton("📋 复制")
        self._copy_global_btn.setFixedWidth(64)
        self._copy_global_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self._global_edit.toPlainText()))
        gp_bar.addWidget(self._copy_global_btn)
        gp_bar.addStretch(1)
        v.addLayout(gp_bar)

        self._global_edit = QPlainTextEdit()
        self._global_edit.setPlaceholderText("global_prompt 将在生成完成后显示…")
        self._global_edit.setMaximumHeight(72)
        v.addWidget(self._global_edit)

        # shots 表格
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ID", "local_prompt", "时长(s)", "⧉"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self._table.setColumnWidth(3, 28)
        v.addWidget(self._table, 1)

        return container

    def _on_partial(self, data: dict) -> None:
        # delta 事件：累积文本，完成后解析
        text = data.get("text", "")
        if text:
            self._accumulated_text += text

    def _on_sse_event(self, event: str, data: dict, proj_dir_str: str) -> None:
        super()._on_sse_event(event, data, proj_dir_str)
        if event == "done" and self._project_dir and str(self._project_dir) == proj_dir_str:
            # 尝试从产物文件加载并渲染
            ep = self._current_episode or "E1"
            json_path = self._project_dir / f"video_prompts_{ep}.json"
            if json_path.is_file():
                try:
                    obj = json.loads(json_path.read_text(encoding="utf-8"))
                    self._render_result(obj)
                except Exception:
                    pass

    def _render_result(self, obj: dict) -> None:
        self._global_edit.setPlainText(obj.get("global_prompt", ""))
        shots = obj.get("shots", [])
        self._table.setRowCount(0)
        for row, s in enumerate(shots):
            self._table.insertRow(row)
            self._table.setItem(row, 0,
                QTableWidgetItem(s.get("shot_id", "")))
            lp_item = QTableWidgetItem(s.get("local_prompt", ""))
            self._table.setItem(row, 1, lp_item)
            self._table.setItem(row, 2,
                QTableWidgetItem(str(s.get("duration", ""))))
            self._add_copy_btn(row)

    def _add_copy_btn(self, row: int) -> None:
        btn = QPushButton("⧉")
        btn.setFixedWidth(24)
        btn.clicked.connect(lambda _=False, r=row: self._copy_shot_row(r))
        self._table.setCellWidget(row, 3, btn)

    def _copy_shot_row(self, row: int) -> None:
        sid_item = self._table.item(row, 0)
        lp_item = self._table.item(row, 1)
        dur_item = self._table.item(row, 2)
        sid = sid_item.text() if sid_item else ""
        lp = lp_item.text() if lp_item else ""
        dur = dur_item.text() if dur_item else ""
        QApplication.clipboard().setText(f"{sid}: {lp}（{dur}s）")
        btn = self._table.cellWidget(row, 3)
        if btn:
            btn.setText("✓")
            QTimer.singleShot(500, lambda: btn.setText("⧉"))

    # ── 动作栏（含导出按钮）─────────────────────────────────────────────────

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._export_json_btn = QPushButton("💾 .json")
        self._export_json_btn.clicked.connect(self._on_export_json)
        bar.addWidget(self._export_json_btn)
        self._export_md_btn = QPushButton("📄 .md")
        self._export_md_btn.clicked.connect(self._on_export_md)
        bar.addWidget(self._export_md_btn)
        bar.addStretch(1)
        self._advance_btn = QPushButton("推进到配音配乐 →")
        self._advance_btn.clicked.connect(self._on_advance_clicked)
        bar.addWidget(self._advance_btn)
        return bar

    def _on_export_json(self) -> None:
        if self._project_dir is None:
            return
        ep = self._current_episode or "E1"
        p = self._project_dir / f"video_prompts_{ep}.json"
        if p.is_file():
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _on_export_md(self) -> None:
        if self._project_dir is None:
            return
        ep = self._current_episode or "E1"
        p = self._project_dir / f"video_prompts_{ep}.md"
        if p.is_file():
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
```

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_video_prompts_page.py -q -p no:faulthandler
```

期望：5 个全绿

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/video_prompts_page.py \
        tests/test_ui/screenwriter/test_video_prompts_page.py
git commit -m "feat(ui): + VideoPromptsPage Stage 5（global_prompt + shots 表格 + ⧉复制）"
```

---

## Task 11: AudioPromptsPage（Stage 6）

**Files:**
- Create: `drama_shot_master/ui/widgets/screenwriter/audio_prompts_page.py`
- Create: `tests/test_ui/screenwriter/test_audio_prompts_page.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_ui/screenwriter/test_audio_prompts_page.py`：

```python
"""AudioPromptsPage 测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter.audio_prompts_page import AudioPromptsPage


def _app():
    return QApplication.instance() or QApplication([])


class _StubClient:
    pass


def _setup_storyboard(tmp_path):
    sb = {
        "title": "x", "globalStyle": "古风",
        "characters": [{"name": "周翠英", "appearance": "白衣"}],
        "shots": [{"shotId": "S01", "duration": 4, "composition": "远景",
                   "description": "雨夜", "stylePrompt": "古风"}],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")


def test_audio_prompts_page_builds_without_crash():
    _app()
    p = AudioPromptsPage(_StubClient())
    assert p is not None


def test_audio_prompts_page_upstream_banner_shows_without_storyboard(tmp_path):
    _app()
    p = AudioPromptsPage(_StubClient())
    p.set_project(tmp_path)
    assert not p._upstream_banner.isHidden()


def test_audio_prompts_page_has_shot_table():
    _app()
    p = AudioPromptsPage(_StubClient())
    assert hasattr(p, "_shot_table")
    assert p._shot_table.columnCount() == 5


def test_audio_prompts_page_export_md_button_exists():
    _app()
    p = AudioPromptsPage(_StubClient())
    assert hasattr(p, "_export_md_btn")


def test_audio_prompts_page_complete_button_exists():
    _app()
    p = AudioPromptsPage(_StubClient())
    assert hasattr(p, "_complete_btn")
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_audio_prompts_page.py -q -p no:faulthandler
```

期望：FAIL，无法 import `AudioPromptsPage`

- [ ] **Step 3: 新建 `drama_shot_master/ui/widgets/screenwriter/audio_prompts_page.py`**

```python
"""AudioPromptsPage：Stage 6 配音配乐提示词子面板。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)
from PySide6.QtCore import Qt

from drama_shot_master.ui.widgets.screenwriter._base_prompts_page import _BasePromptsPage


class AudioPromptsPage(_BasePromptsPage):

    def __init__(self, client, parent=None):
        self._voice_cards_container: QWidget | None = None
        self._voice_grid: QGridLayout | None = None
        super().__init__(client, parent)

    # ── 子类实现 ───────────────────────────────────────────────────────────

    def _endpoint(self) -> str:
        return "/audio_prompts"

    def _output_filename(self, ep: str) -> str:
        return f"audio_prompts_{ep}.md"

    def _build_result_widget(self) -> QWidget:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # 音色卡区（两列 grid，上方）
        voice_scroll = QScrollArea()
        voice_scroll.setWidgetResizable(True)
        voice_scroll.setMaximumHeight(220)
        self._voice_cards_container = QWidget()
        self._voice_grid = QGridLayout(self._voice_cards_container)
        self._voice_grid.setSpacing(6)
        voice_scroll.setWidget(self._voice_cards_container)
        v.addWidget(QLabel("🎤 角色音色卡"))
        v.addWidget(voice_scroll)

        # 分镜配音匹配表（下方，全宽）
        v.addWidget(QLabel("📋 分镜配音配乐匹配表"))
        self._shot_table = QTableWidget(0, 5)
        self._shot_table.setHorizontalHeaderLabels(
            ["ID", "角色", "台词/旁白", "音效提示", "BGM情绪"])
        hdr = self._shot_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.Interactive)
        v.addWidget(self._shot_table, 1)

        return container

    def _on_partial(self, data: dict) -> None:
        # 流式 delta：暂时不做实时渲染（内容为 Markdown 全文，done 后解析）
        pass

    def _on_sse_event(self, event: str, data: dict, proj_dir_str: str) -> None:
        super()._on_sse_event(event, data, proj_dir_str)
        if event == "done" and self._project_dir and str(self._project_dir) == proj_dir_str:
            ep = self._current_episode or "E1"
            md_path = self._project_dir / f"audio_prompts_{ep}.md"
            if md_path.is_file():
                try:
                    text = md_path.read_text(encoding="utf-8")
                    self._render_from_md(text)
                except Exception:
                    pass

    def _render_from_md(self, text: str) -> None:
        """简单解析 Markdown，渲染音色卡 + 匹配表。"""
        import re
        # 清空
        if self._voice_grid:
            while self._voice_grid.count():
                item = self._voice_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self._shot_table.setRowCount(0)

        # 解析音色卡（### 开头的 section）
        character_sections = re.findall(
            r"###\s+(.+?)\n(.*?)(?=###|\n## |\Z)", text, re.DOTALL)
        col = 0
        for i, (char_name, char_body) in enumerate(character_sections):
            card = self._make_voice_card(char_name.strip(), char_body.strip())
            if self._voice_grid:
                self._voice_grid.addWidget(card, i // 2, i % 2)

        # 解析表格行 | S01 | ... |
        rows = re.findall(r"\|\s*(S\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|",
                          text)
        for row_idx, (shot_id, role, dialogue, sfx, bgm) in enumerate(rows):
            self._shot_table.insertRow(row_idx)
            for col_idx, val in enumerate((shot_id, role, dialogue, sfx, bgm)):
                self._shot_table.setItem(row_idx, col_idx, QTableWidgetItem(val))

    def _make_voice_card(self, name: str, body: str) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(
            "QFrame { border-left: 3px solid #5e60ce; "
            "background: #1e1e2e; border-radius: 4px; }")
        v = QVBoxLayout(card)
        title = QLabel(f"<b>{name}</b>")
        title.setStyleSheet("color: #c0b5f0; padding: 2px 4px;")
        v.addWidget(title)
        editor = QPlainTextEdit(body)
        editor.setStyleSheet("background: transparent; color: #ccc; border: none;")
        editor.setMaximumHeight(80)
        v.addWidget(editor)
        return card

    # ── 动作栏 ──────────────────────────────────────────────────────────────

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._export_md_btn = QPushButton("📄 导出 Markdown")
        self._export_md_btn.clicked.connect(self._on_export_md)
        bar.addWidget(self._export_md_btn)
        bar.addStretch(1)
        self._complete_btn = QPushButton("✓ 完成")
        self._complete_btn.clicked.connect(self._on_complete)
        bar.addWidget(self._complete_btn)
        return bar

    def _on_export_md(self) -> None:
        if self._project_dir is None:
            return
        ep = self._current_episode or "E1"
        p = self._project_dir / f"audio_prompts_{ep}.md"
        if p.is_file():
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _on_complete(self) -> None:
        self.statusMessage.emit("配音配乐提示词已完成 ✓")
```

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_audio_prompts_page.py -q -p no:faulthandler
```

期望：5 个全绿

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/screenwriter/audio_prompts_page.py \
        tests/test_ui/screenwriter/test_audio_prompts_page.py
git commit -m "feat(ui): + AudioPromptsPage Stage 6（音色卡两列+分镜匹配表）"
```

---

## Task 12: 接入 screenwriter_panel（6 步 Wizard）

**Files:**
- Modify: `drama_shot_master/ui/panels/screenwriter_panel.py`
- Test: `tests/test_ui/screenwriter/test_screenwriter_panel.py`

- [ ] **Step 1: 写失败测试（追加到 test_screenwriter_panel.py 末尾）**

```python
def test_panel_has_6_stages():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    assert len(panel._pages) == 6
    assert panel._wizard_host._stack.count() == 6
    assert len(panel._wizard_host._buttons) == 6


def test_panel_6th_button_label_is_配音配乐():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    assert panel._wizard_host._buttons[5].text() == "6. 配音配乐"


def test_panel_4th_button_label_is_分镜图提示词():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    assert panel._wizard_host._buttons[3].text() == "4. 分镜图提示词"
```

- [ ] **Step 2: 运行验证 FAIL**

```
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py::test_panel_has_6_stages -q -p no:faulthandler
```

期望：FAIL，`assert 4 == 6`

- [ ] **Step 3: 修改 screenwriter_panel.py**

**3a. 在文件顶部 import 块末尾追加三行 import：**

```python
from drama_shot_master.ui.widgets.screenwriter.image_prompts_page import ImagePromptsPage
from drama_shot_master.ui.widgets.screenwriter.video_prompts_page import VideoPromptsPage
from drama_shot_master.ui.widgets.screenwriter.audio_prompts_page import AudioPromptsPage
```

**3b. 将：**

```python
_STAGE_NAMES = ["创意", "剧本", "分镜", "提示词"]
```

改为：

```python
_STAGE_NAMES = ["创意", "剧本", "分镜", "分镜图提示词", "视频提示词", "配音配乐"]
```

**3c. 在 `_build_ui` 的 `prompts = PromptsPage(self._client)` 那行之后追加：**

```python
        image_prompts_pg = ImagePromptsPage(self._client)
        video_prompts_pg = VideoPromptsPage(self._client)
        audio_prompts_pg = AudioPromptsPage(self._client)
        self._pages = [ideate, script, storyboard, prompts,
                       image_prompts_pg, video_prompts_pg, audio_prompts_pg]
```

并将原来的：

```python
        self._pages = [ideate, script, storyboard, prompts]
```

这行删除（它已被上面的新行替代）。

**注意：** `prompts`（PromptsPage）保留为第4个页（Stage 4 索引 3），`image_prompts_pg` 为索引 4，`video_prompts_pg` 为索引 5，`audio_prompts_pg` 为索引 6。但 spec 要求 Stage 4 = 分镜图提示词。

重新对照 spec：`_STAGE_NAMES = ["创意", "剧本", "分镜", "分镜图提示词", "视频提示词", "配音配乐"]`，共 6 个，PromptsPage（旧提示词页）不在新 6 阶段中。正确的 `_pages` 应为：

```python
        self._pages = [ideate, script, storyboard,
                       image_prompts_pg, video_prompts_pg, audio_prompts_pg]
```

`prompts`（旧 PromptsPage）不再加入 wizard，可保留变量但不注册。更新后 `_STAGE_NAMES` 6 项与 `_pages` 6 项一一对应。

- [ ] **Step 4: 运行验证 PASS**

```
python -m pytest tests/test_ui/screenwriter/test_screenwriter_panel.py -q -p no:faulthandler
```

注意：`test_task_selection_propagates_to_all_pages` 和 `test_panel_builds_with_splitter_and_4_pages` 会因为页数变化而失败，需同步更新：

将 `test_panel_builds_with_splitter_and_4_pages` 中的断言改为：

```python
    assert panel._wizard_host._stack.count() == 6
```

将 `test_task_selection_propagates_to_all_pages` 中的 `range(4)` 改为 `range(6)` 并删去 `PromptsPage placeholder` 注释（新的 6 个页都有 `_project_dir`）。

再次运行确认全绿。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/screenwriter_panel.py \
        tests/test_ui/screenwriter/test_screenwriter_panel.py
git commit -m "feat(panel): Wizard 扩展为 6 阶段（分镜图/视频/配音配乐提示词）"
```

---

## Task 13: 端到端集成测试

**Files:**
- Create: `tests/test_screenwriter_agent/test_e2e_phase2.py`

- [ ] **Step 1: 新建测试文件**

新建 `tests/test_screenwriter_agent/test_e2e_phase2.py`：

```python
"""Phase 2 三个新端点端到端（mock LLM）。"""
import json
import pytest
from fastapi.testclient import TestClient
from screenwriter_agent.server import create_app


def _setup(tmp_path):
    sb = {
        "title": "守株待兔",
        "globalStyle": "古风水墨",
        "characters": [{"name": "周翠英", "appearance": "白衣长裙"},
                       {"name": "李书生", "appearance": "青衫"}],
        "shots": [
            {"shotId": "S01", "duration": 4, "composition": "远景",
             "description": "雨夜松林", "stylePrompt": "古风水墨"},
            {"shotId": "S02", "duration": 3, "composition": "中景",
             "description": "对话", "stylePrompt": "古风水墨"},
        ],
    }
    (tmp_path / "分镜_E1.json").write_text(
        json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "剧本_E1.md").write_text(
        "# 守株待兔 E1\n\n## 镜头S01\n旁白OS: 世人皆说守株待兔是愚...\n\n## 镜头S02\n李书生: 姑娘留步。\n",
        encoding="utf-8")


@pytest.fixture
def mock_llm_all(monkeypatch):
    def _stream(self, messages):
        from screenwriter_agent.core.llm_client import StreamChunk
        content = " ".join(m.get("content", "") for m in messages)
        if "Panel" in content or "宫格" in content or "SeedDream" in content:
            raw = (
                "## 第1组（9宫格）S01-S02\n"
                "**角色参考：** 周翠英_ref\n"
                "**提示词：**\n"
                "Panel 1: Ancient ink, rainy forest. Panel 2: Woman turning."
            )
        elif "global_prompt" in content or "LTX" in content:
            raw = json.dumps({
                "global_prompt": "Ancient ink painting, 9:16, cinematic",
                "shots": [
                    {"shot_id": "S01", "local_prompt": "Camera: slow push in, Subject: woman, Action: standing", "duration": 4},
                    {"shot_id": "S02", "local_prompt": "Camera: static, Subject: couple, Action: talking", "duration": 3},
                ],
            }, ensure_ascii=False)
        else:
            raw = (
                "# 配音配乐提示词 E1\n\n"
                "## 角色音色卡\n\n"
                "### 周翠英（女主）\n"
                "- 性别：女 · 年龄：25岁\n"
                "- 语调：清冽柔和\n\n"
                "## 分镜配音配乐匹配表\n\n"
                "| ID | 角色 | 台词/旁白 | 音效提示 | BGM情绪 |\n"
                "|---|---|---|---|---|\n"
                "| S01 | 旁白OS | 世人皆说... | 雨声 | 悲切 |\n"
            )
        for ch in raw:
            yield StreamChunk(kind="delta", text=ch)
        yield StreamChunk(kind="done", raw=raw)
    monkeypatch.setattr(
        "screenwriter_agent.core.llm_client.LLMClient.stream_chat", _stream)


def test_e2e_image_prompts(tmp_path, mock_llm_all):
    _setup(tmp_path)
    c = TestClient(create_app())
    r = c.post("/image_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "image_prompts_E1.md").is_file()
    content = (tmp_path / "image_prompts_E1.md").read_text(encoding="utf-8")
    assert len(content) > 10


def test_e2e_video_prompts(tmp_path, mock_llm_all):
    _setup(tmp_path)
    c = TestClient(create_app())
    r = c.post("/video_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "video_prompts_E1.json").is_file()
    assert (tmp_path / "video_prompts_E1.md").is_file()
    obj = json.loads((tmp_path / "video_prompts_E1.json").read_text(encoding="utf-8"))
    assert "global_prompt" in obj
    assert len(obj.get("shots", [])) == 2


def test_e2e_audio_prompts(tmp_path, mock_llm_all):
    _setup(tmp_path)
    c = TestClient(create_app())
    r = c.post("/audio_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "audio_prompts_E1.md").is_file()
    content = (tmp_path / "audio_prompts_E1.md").read_text(encoding="utf-8")
    assert len(content) > 10


def test_e2e_all_three_endpoints_in_sequence(tmp_path, mock_llm_all):
    """三个端点顺序调用，互不干扰。"""
    _setup(tmp_path)
    c = TestClient(create_app())
    for endpoint in ("/image_prompts", "/audio_prompts"):
        r = c.post(endpoint, json={
            "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
        assert r.status_code == 200, f"{endpoint} failed: {r.text[:200]}"
    r = c.post("/video_prompts", json={
        "project_dir": str(tmp_path), "episode_id": "E1", "options": {}})
    assert r.status_code == 200
    assert (tmp_path / "image_prompts_E1.md").is_file()
    assert (tmp_path / "video_prompts_E1.json").is_file()
    assert (tmp_path / "audio_prompts_E1.md").is_file()
```

- [ ] **Step 2: 运行验证（此时应 PASS，因为路由已在 Task 5-7 注册）**

```
python -m pytest tests/test_screenwriter_agent/test_e2e_phase2.py -q -p no:faulthandler
```

期望：4 个全绿

- [ ] **Step 3: 运行完整测试套件确认零回归**

```
python -m pytest tests/ -q -p no:faulthandler --tb=short 2>&1 | tail -20
```

期望：新增约 33 个测试全绿，原有测试零回归。

- [ ] **Step 4: Commit**

```bash
git add tests/test_screenwriter_agent/test_e2e_phase2.py
git commit -m "test(e2e): Phase 2 三端点端到端集成测试"
```

---

## 验收 Checklist

运行以下命令验证所有新测试：

```bash
python -m pytest \
  tests/test_ui/screenwriter/test_wizard_host.py \
  tests/test_ui/screenwriter/test_script_page.py \
  tests/test_ui/screenwriter/test_screenwriter_panel.py \
  tests/test_screenwriter_agent/test_template_loader.py \
  tests/test_screenwriter_agent/test_route_image_prompts.py \
  tests/test_screenwriter_agent/test_route_video_prompts.py \
  tests/test_screenwriter_agent/test_route_audio_prompts.py \
  tests/test_ui/screenwriter/test_base_prompts_page.py \
  tests/test_ui/screenwriter/test_image_prompts_page.py \
  tests/test_ui/screenwriter/test_video_prompts_page.py \
  tests/test_ui/screenwriter/test_audio_prompts_page.py \
  tests/test_screenwriter_agent/test_e2e_phase2.py \
  -v -p no:faulthandler 2>&1 | tail -40
```

全套零回归验证：

```bash
python -m pytest tests/ -q -p no:faulthandler --tb=short 2>&1 | tail -10
```
