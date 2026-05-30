# 配乐 AI 对话面板 实施计划（子项目 #1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 [配乐] 加对话式配乐方向控制——自然语言指令经文本 LLM 归并成结构化「配乐方向」，写入各段 music_prompt（不自动生成），右栏上半常驻 AI 对话面板。

**Architecture:** `ScoringSession.directive`(SoundtrackDirective) 持久化全局方向+对话历史；`directive_composer.synthesize_directive` 用复用的文本 provider 把对话归并成方向；`facade.apply_directive_to_prompts` 纯模板把方向写进各段 prompt；`AIChatPanel` 放右栏垂直分栏上半，编辑器经 FunctionWorker 接线，全程不触发 RunningHub。

**Tech Stack:** Python dataclass / OpenAICompatProvider(.generate images=[] 纯文本) / PySide6(QSplitter/QScrollArea/QTextEdit) / pytest(offscreen)

**Spec:** `docs/superpowers/specs/2026-05-30-soundtrack-ai-dialogue-design.md`

**Branch:** main

---

## File Map

```
新增:
  sound_track_agent/directive_composer.py             # T2: synthesize_directive
  drama_shot_master/ui/widgets/soundtrack_ai_chat.py  # T4: AIChatPanel
  tests/test_sound_track_agent/test_directive_composer.py    # T2
  tests/test_sound_track_agent/test_apply_directive.py       # T3
  tests/test_ui/test_ai_chat_panel.py                        # T4
  tests/test_ui/test_soundtrack_ai_wiring.py                 # T5
改:
  sound_track_agent/session.py        # T1: SoundtrackDirective + ScoringSession.directive
  sound_track_agent/facade.py         # T3: apply_directive_to_prompts
  drama_shot_master/ui/widgets/soundtrack_editor.py  # T5: 右栏垂直分栏 + AI 接线
  tests/test_sound_track_agent/test_session.py        # T1: directive 兼容（追加）
```

---

## Task 1: SoundtrackDirective 数据模型 + ScoringSession.directive

**Files:**
- Modify: `sound_track_agent/session.py`
- Test: `tests/test_sound_track_agent/test_session.py`（追加）

- [ ] **Step 1: 写失败测试** — 追加到 `tests/test_sound_track_agent/test_session.py` 末尾：

```python
def test_soundtrack_directive_roundtrip():
    from sound_track_agent.session import SoundtrackDirective
    d = SoundtrackDirective(
        global_directive="史诗管弦",
        segment_directives={1: "钢琴前奏", 3: "弦乐高潮"},
        conversation=[{"role": "user", "text": "史诗感"},
                      {"role": "assistant", "text": "已更新"}])
    d2 = SoundtrackDirective.from_dict(d.to_dict())
    assert d2.global_directive == "史诗管弦"
    assert d2.segment_directives == {1: "钢琴前奏", 3: "弦乐高潮"}   # int 键还原
    assert d2.conversation[0]["text"] == "史诗感"


def test_soundtrack_directive_from_empty():
    from sound_track_agent.session import SoundtrackDirective
    d = SoundtrackDirective.from_dict({})
    assert d.global_directive == "" and d.segment_directives == {} and d.conversation == []


def test_scoring_session_directive_roundtrip_and_legacy():
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, SoundtrackDirective)
    sess = ScoringSession(source_mp4="/m.mp4", source_hash="h",
                          global_style="末日", frame_rate=24.0,
                          segments=[SegmentScore(0, 0.0, 5.0)])
    sess.directive = SoundtrackDirective(global_directive="史诗")
    sess2 = ScoringSession.from_dict(sess.to_dict())
    assert sess2.directive.global_directive == "史诗"
    # legacy：旧 json 无 directive 字段 → 空 directive，不崩
    legacy = sess.to_dict(); legacy.pop("directive", None)
    sess3 = ScoringSession.from_dict(legacy)
    assert sess3.directive.global_directive == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q -k directive`
Expected: FAIL — `ImportError`/`AttributeError`（SoundtrackDirective 不存在）

- [ ] **Step 3: 加 SoundtrackDirective + 挂到 ScoringSession**

在 `sound_track_agent/session.py`，在 `ScoringSession` 定义**之前**加：

```python
@dataclass
class SoundtrackDirective:
    """对话式配乐方向：归并后的全局方向 + 分段方向（B 预留）+ 单会话对话历史。"""
    global_directive: str = ""
    segment_directives: dict = field(default_factory=dict)   # {int: str}，B 预留
    conversation: list = field(default_factory=list)          # [{"role","text"}]

    def to_dict(self) -> dict:
        return {
            "global_directive": self.global_directive,
            "segment_directives": {str(k): v
                                   for k, v in self.segment_directives.items()},
            "conversation": list(self.conversation),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SoundtrackDirective":
        if not d:
            return cls()
        return cls(
            global_directive=d.get("global_directive", ""),
            segment_directives={int(k): v
                                for k, v in (d.get("segment_directives") or {}).items()},
            conversation=list(d.get("conversation") or []),
        )
```

在 `ScoringSession` 的字段区，`segments_refined` 之后加：

```python
    directive: "SoundtrackDirective" = field(default_factory=lambda: SoundtrackDirective())
```

`ScoringSession.to_dict` 的返回 dict 里 `"segments_refined": self.segments_refined,` 之后加：

```python
            "directive": self.directive.to_dict(),
```

`ScoringSession.from_dict` 的 `cls(...)` 里 `segments_refined=...` 之后加：

```python
            directive=SoundtrackDirective.from_dict(d.get("directive")),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_session.py -q`
Expected: PASS（含新 3 测试 + 既有 session 测试全绿）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/session.py tests/test_sound_track_agent/test_session.py
git commit -m "feat(soundtrack): + SoundtrackDirective 数据模型 + ScoringSession.directive

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: directive_composer.synthesize_directive（文本 LLM 归并）

**Files:**
- Create: `sound_track_agent/directive_composer.py`
- Test: `tests/test_sound_track_agent/test_directive_composer.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_sound_track_agent/test_directive_composer.py`：

```python
"""directive_composer：对话 → 文本 LLM → 结构化配乐方向。"""
from sound_track_agent.session import SoundtrackDirective
from sound_track_agent.directive_composer import synthesize_directive


class _FakeProvider:
    """模拟 OpenAICompatProvider.generate(images, system_prompt, user_supplement)。"""
    def __init__(self, reply_text):
        self._reply = reply_text
        self.calls = []
    def generate(self, images, system_prompt, user_supplement):
        self.calls.append((list(images), system_prompt, user_supplement))
        return self._reply


def test_first_turn_produces_global_and_appends_conversation():
    p = _FakeProvider('{"global": "史诗管弦, 中速", "segments": {}, "reply": "已更新为史诗管弦"}')
    cur = SoundtrackDirective()
    out = synthesize_directive(p, cur, "史诗感电影配乐", n_segments=5)
    assert out.global_directive == "史诗管弦, 中速"
    assert out.conversation[-2] == {"role": "user", "text": "史诗感电影配乐"}
    assert out.conversation[-1] == {"role": "assistant", "text": "已更新为史诗管弦"}
    # 纯文本调用：images 为空
    assert p.calls[0][0] == []


def test_correction_overrides_previous():
    p = _FakeProvider('{"global": "史诗管弦, 快速, 竹笛", "reply": "已加快并加竹笛"}')
    cur = SoundtrackDirective(global_directive="史诗管弦, 舒缓",
                              conversation=[{"role": "user", "text": "史诗感"},
                                            {"role": "assistant", "text": "ok"}])
    out = synthesize_directive(p, cur, "节奏再快点，加竹笛", n_segments=5)
    assert "快" in out.global_directive and "竹笛" in out.global_directive
    assert len(out.conversation) == 4          # 旧2 + 新2


def test_segment_directives_parsed_as_int_keys():
    p = _FakeProvider('{"global": "管弦", "segments": {"1": "钢琴前奏"}, "reply": "ok"}')
    out = synthesize_directive(p, SoundtrackDirective(), "分段", n_segments=3)
    assert out.segment_directives == {1: "钢琴前奏"}


def test_invalid_json_keeps_old_global_no_crash():
    p = _FakeProvider("抱歉我无法生成 JSON")
    cur = SoundtrackDirective(global_directive="原有方向")
    out = synthesize_directive(p, cur, "随便说点", n_segments=2)
    assert out.global_directive == "原有方向"          # 保留旧
    assert out.conversation[-2]["text"] == "随便说点"   # 指令仍入历史
    assert out.conversation[-1]["role"] == "assistant"  # 有失败提示


def test_json_embedded_in_text_is_extracted():
    p = _FakeProvider('好的~ {"global": "钢琴", "reply": "done"} 以上')
    out = synthesize_directive(p, SoundtrackDirective(), "钢琴风", n_segments=1)
    assert out.global_directive == "钢琴"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_directive_composer.py -q`
Expected: FAIL — `ModuleNotFoundError: ... directive_composer`

- [ ] **Step 3: 实现** — 新建 `sound_track_agent/directive_composer.py`：

```python
"""对话式配乐方向归并：用文本 LLM 把多轮对话 + 新指令归并成结构化方向。

provider 复用 OpenAICompatProvider.generate(images, system_prompt, user_supplement)，
传 images=[] 即纯文本对话。不联网生成音频。
"""
from __future__ import annotations

import json
import re

from sound_track_agent.session import SoundtrackDirective

_SYSTEM = (
    "你是短剧配乐方向助手。根据「当前全局方向 + 历史对话 + 用户新指令」，"
    "归并出更新后的配乐方向。新指令若是修正/覆盖（如把『舒缓』改成『快』），"
    "必须覆盖旧设定而非简单叠加。\n"
    "只输出一个 JSON 对象，不要多余文字，格式：\n"
    '{"global": "整体配乐方向（风格/情绪曲线/乐器/速度）", '
    '"segments": {"段序号": "该段方向"}, "reply": "一句给用户的变更摘要"}\n'
    "segments 可为空对象 {}。"
)


def _parse_json(raw: str):
    """容错解析：直接 loads；失败则抽取第一个 {...} 再 loads；再失败返回 None。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def synthesize_directive(provider, current: SoundtrackDirective,
                         instruction: str, n_segments: int) -> SoundtrackDirective:
    convo = "\n".join(f"{m.get('role')}: {m.get('text')}"
                      for m in current.conversation)
    user = (
        f"当前全局方向：{current.global_directive or '（空）'}\n"
        f"历史对话：\n{convo or '（无）'}\n"
        f"视频共 {n_segments} 段。\n"
        f"用户新指令：{instruction}"
    )
    try:
        raw = provider.generate([], _SYSTEM, user)
    except Exception as e:
        raw = ""
        parsed = None
    else:
        parsed = _parse_json(raw)

    if parsed is None:
        new_global = current.global_directive
        new_segs = dict(current.segment_directives)
        reply = "AI 返回无法解析，配乐方向保持不变，请换个说法重述。"
    else:
        new_global = parsed.get("global") or current.global_directive
        new_segs = {}
        for k, v in (parsed.get("segments") or {}).items():
            try:
                new_segs[int(k)] = v
            except (TypeError, ValueError):
                continue
        if not new_segs:
            new_segs = dict(current.segment_directives)
        reply = parsed.get("reply") or "已更新配乐方向。"

    conversation = list(current.conversation) + [
        {"role": "user", "text": instruction},
        {"role": "assistant", "text": reply},
    ]
    return SoundtrackDirective(global_directive=new_global,
                               segment_directives=new_segs,
                               conversation=conversation)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_directive_composer.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/directive_composer.py tests/test_sound_track_agent/test_directive_composer.py
git commit -m "feat(soundtrack): + directive_composer 文本LLM归并配乐方向（容错JSON）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: facade.apply_directive_to_prompts（方向 → 各段 prompt）

**Files:**
- Modify: `sound_track_agent/facade.py`
- Test: `tests/test_sound_track_agent/test_apply_directive.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_sound_track_agent/test_apply_directive.py`：

```python
"""apply_directive_to_prompts：方向写入各段 music_prompt（纯模板，不联网）。"""
from sound_track_agent.session import (
    ScoringSession, SegmentScore, SoundtrackDirective, EmotionTag)
from sound_track_agent.facade import apply_directive_to_prompts


def _sess():
    return ScoringSession(source_mp4="/m.mp4", source_hash="h",
                          global_style="旧风格", frame_rate=24.0,
                          segments=[SegmentScore(0, 0.0, 5.0),
                                    SegmentScore(1, 5.0, 12.0)])


def test_global_directive_written_to_all_segments():
    s = _sess()
    s.directive = SoundtrackDirective(global_directive="史诗管弦")
    apply_directive_to_prompts(s)
    assert s.global_style == "史诗管弦"                       # 同步单一可信源
    assert "史诗管弦" in s.segments[0].music_prompt
    assert "史诗管弦" in s.segments[1].music_prompt


def test_segment_directive_overrides_global():
    s = _sess()
    s.directive = SoundtrackDirective(global_directive="史诗管弦",
                                      segment_directives={1: "钢琴独奏"})
    apply_directive_to_prompts(s)
    assert "史诗管弦" in s.segments[0].music_prompt
    assert "钢琴独奏" in s.segments[1].music_prompt           # 段1 用分段方向


def test_empty_directive_falls_back_to_global_style():
    s = _sess()
    s.directive = SoundtrackDirective()                       # 空方向
    apply_directive_to_prompts(s)
    assert "旧风格" in s.segments[0].music_prompt             # 退回 session.global_style


def test_does_not_touch_candidates():
    from sound_track_agent.session import BGMCandidate
    s = _sess()
    s.segments[0].candidates = [BGMCandidate(path="/a.mp3", seed=1, prompt="x")]
    s.segments[0].chosen_candidate = 0
    s.directive = SoundtrackDirective(global_directive="新")
    apply_directive_to_prompts(s)
    assert len(s.segments[0].candidates) == 1                 # 不动候选
    assert s.segments[0].chosen_candidate == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_sound_track_agent/test_apply_directive.py -q`
Expected: FAIL — `ImportError`（apply_directive_to_prompts 不存在）

- [ ] **Step 3: 实现** — 在 `sound_track_agent/facade.py` 末尾加：

```python
def apply_directive_to_prompts(session) -> None:
    """把 session.directive 写入各段 music_prompt（纯模板重算，不联网、不生成）。

    effective_style(seg) = directive.segment_directives.get(seg.index)
                           or directive.global_directive or session.global_style
    不触发 RunningHub；不改 candidates/chosen。
    """
    from sound_track_agent.prompt_composer import compose_music_prompt
    d = getattr(session, "directive", None)
    if d is None:
        return
    if d.global_directive:
        session.global_style = d.global_directive
    for seg in session.segments:
        eff = (d.segment_directives.get(seg.index)
               or d.global_directive
               or session.global_style)
        duration = float(seg.t_end) - float(seg.t_start)
        seg.music_prompt = compose_music_prompt(eff, seg.emotion, duration)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_sound_track_agent/test_apply_directive.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add sound_track_agent/facade.py tests/test_sound_track_agent/test_apply_directive.py
git commit -m "feat(soundtrack): + apply_directive_to_prompts（方向写各段prompt，不联网）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: AIChatPanel 组件

**Files:**
- Create: `drama_shot_master/ui/widgets/soundtrack_ai_chat.py`
- Test: `tests/test_ui/test_ai_chat_panel.py`

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_ai_chat_panel.py`：

```python
"""AIChatPanel：渲染对话/方向 + 双按钮 emit + busy 禁用。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.session import SoundtrackDirective
from drama_shot_master.ui.widgets.soundtrack_ai_chat import AIChatPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct(app):
    w = AIChatPanel()
    assert w is not None


def test_set_directive_renders_conversation(app):
    w = AIChatPanel()
    d = SoundtrackDirective(global_directive="史诗管弦",
        conversation=[{"role": "user", "text": "史诗感"},
                      {"role": "assistant", "text": "已更新"}])
    w.set_directive(d)
    assert w._bubble_count() == 2
    assert "史诗管弦" in w._direction_text()


def test_update_only_button_emits_apply_false(app):
    w = AIChatPanel()
    w._input.setPlainText("史诗感")
    got = []
    w.directiveRequested.connect(lambda t, a: got.append((t, a)))
    w.btn_update_only.click()
    assert got == [("史诗感", False)]


def test_update_apply_button_emits_apply_true(app):
    w = AIChatPanel()
    w._input.setPlainText("史诗感")
    got = []
    w.directiveRequested.connect(lambda t, a: got.append((t, a)))
    w.btn_update_apply.click()
    assert got == [("史诗感", True)]


def test_empty_input_does_not_emit(app):
    w = AIChatPanel()
    w._input.setPlainText("   ")
    got = []
    w.directiveRequested.connect(lambda t, a: got.append(1))
    w.btn_update_apply.click()
    assert got == []


def test_set_busy_disables_buttons(app):
    w = AIChatPanel()
    w.set_busy(True)
    assert w.btn_update_apply.isEnabled() is False
    w.set_busy(False)
    assert w.btn_update_apply.isEnabled() is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_ai_chat_panel.py -q`
Expected: FAIL — `ModuleNotFoundError: ... soundtrack_ai_chat`

- [ ] **Step 3: 实现** — 新建 `drama_shot_master/ui/widgets/soundtrack_ai_chat.py`：

```python
"""AIChatPanel：对话式配乐方向面板（右栏上半常驻）。

会话区 + 当前方向块 + 输入框 + 双按钮。不直接调 LLM/生成——只发
directiveRequested(instruction, apply_prompts) 信号，由编辑器接线处理。
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPlainTextEdit,
    QPushButton, QFrame,
)


class AIChatPanel(QWidget):
    directiveRequested = Signal(str, bool)   # (instruction, apply_prompts)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel("🤖 AI 配乐")
        title.setStyleSheet("font-weight:600;color:#4a83f0;")
        root.addWidget(title)

        # 会话区
        self._chat_area = QScrollArea()
        self._chat_area.setWidgetResizable(True)
        self._chat_host = QWidget()
        self._chat_lay = QVBoxLayout(self._chat_host)
        self._chat_lay.setContentsMargins(2, 2, 2, 2)
        self._chat_lay.setSpacing(5)
        self._chat_lay.addStretch(1)
        self._chat_area.setWidget(self._chat_host)
        root.addWidget(self._chat_area, 1)

        # 当前方向块
        dir_box = QFrame()
        dir_box.setStyleSheet("background:#1a1a2a;border-radius:4px;")
        dl = QVBoxLayout(dir_box)
        dl.setContentsMargins(6, 4, 6, 4)
        dl.addWidget(QLabel("📋 当前配乐方向"))
        self._dir_label = QLabel("（空，发指令开始）")
        self._dir_label.setWordWrap(True)
        self._dir_label.setStyleSheet("color:#cdd6f4;")
        dl.addWidget(self._dir_label)
        root.addWidget(dir_box)

        # 输入框
        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("用自然语言描述/修改配乐…")
        self._input.setMaximumHeight(60)
        root.addWidget(self._input)

        # 双按钮
        btns = QHBoxLayout()
        self.btn_update_only = QPushButton("仅更新方向")
        self.btn_update_only.clicked.connect(lambda: self._emit(False))
        self.btn_update_apply = QPushButton("更新并写入 prompt")
        self.btn_update_apply.setObjectName("AccentButton")
        self.btn_update_apply.clicked.connect(lambda: self._emit(True))
        btns.addWidget(self.btn_update_only)
        btns.addWidget(self.btn_update_apply)
        root.addLayout(btns)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#a6adc8;font-size:11px;")
        root.addWidget(self._status)

    def _emit(self, apply_prompts: bool):
        text = self._input.toPlainText().strip()
        if not text:
            return
        self.directiveRequested.emit(text, apply_prompts)

    def set_directive(self, directive):
        # 重建对话气泡
        while self._chat_lay.count() > 1:      # 保留末尾 stretch
            item = self._chat_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for m in (getattr(directive, "conversation", None) or []):
            self._add_bubble(m.get("role", ""), m.get("text", ""))
        g = getattr(directive, "global_directive", "") or "（空，发指令开始）"
        self._dir_label.setText(g)

    def _add_bubble(self, role: str, text: str):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        if role == "user":
            lbl.setStyleSheet(
                "background:#3b6fd4;color:#fff;border-radius:7px;padding:5px 8px;")
            lbl.setAlignment(Qt.AlignRight)
        else:
            lbl.setStyleSheet(
                "background:#313145;color:#cdd6f4;border-radius:7px;padding:5px 8px;")
        self._chat_lay.insertWidget(self._chat_lay.count() - 1, lbl)

    def set_busy(self, on: bool):
        self.btn_update_only.setEnabled(not on)
        self.btn_update_apply.setEnabled(not on)
        self._input.setEnabled(not on)
        self._status.setText("AI 思考中…" if on else "")

    def append_error(self, msg: str):
        self._status.setText(msg)

    # 测试辅助
    def _bubble_count(self) -> int:
        return self._chat_lay.count() - 1      # 去掉 stretch

    def _direction_text(self) -> str:
        return self._dir_label.text()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_ai_chat_panel.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_ai_chat.py tests/test_ui/test_ai_chat_panel.py
git commit -m "feat(soundtrack): + AIChatPanel 对话面板（会话/方向/双按钮）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: SoundtrackEditor 右栏分栏 + AI 接线

**Files:**
- Modify: `drama_shot_master/ui/widgets/soundtrack_editor.py`
- Test: `tests/test_ui/test_soundtrack_ai_wiring.py`

说明：先读文件确认 `_inspector_container` 的构建位置（在 `_build_daw_main` 内，`setFixedWidth(280)` 处）。

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_ui/test_soundtrack_ai_wiring.py`：

```python
"""SoundtrackEditor AI 接线：面板存在 + 指令→方向→写prompt→刷新（mock worker 同步）。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(tmp_path):
    from drama_shot_master.config import Config
    c = Config(); c.settings_path = tmp_path / "s.json"
    return c


def _ed(tmp_path):
    mp4 = tmp_path / "raw.mp4"; mp4.write_bytes(b"x")
    return SoundtrackEditor({"id": "t1", "name": "t", "mp4": str(mp4),
                             "style": "x", "output_dir": str(tmp_path)},
                            _cfg(tmp_path), tmp_path)


def test_ai_chat_panel_exists(tmp_path):
    _app()
    ed = _ed(tmp_path)
    assert ed._ai_chat is not None


def test_directive_requested_without_session_shows_error(tmp_path):
    _app()
    ed = _ed(tmp_path)
    ed._session = None
    errs = []
    ed._ai_chat.append_error = lambda m: errs.append(m)
    ed._on_directive_requested("史诗感", True)
    assert errs and "session" in errs[0].lower() or errs   # 有错误提示，不崩


def test_directive_built_apply_writes_prompts(tmp_path):
    _app()
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, SoundtrackDirective)
    ed = _ed(tmp_path)
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="旧",
        frame_rate=24.0, segments=[SegmentScore(0, 0.0, 5.0)])
    new_dir = SoundtrackDirective(global_directive="史诗管弦",
        conversation=[{"role": "user", "text": "史诗"},
                      {"role": "assistant", "text": "ok"}])
    ed._on_directive_built(new_dir, apply_prompts=True)
    assert ed._session.directive.global_directive == "史诗管弦"
    assert "史诗管弦" in ed._session.segments[0].music_prompt   # 已写入
    assert ed._session.global_style == "史诗管弦"


def test_directive_built_no_apply_keeps_prompts(tmp_path):
    _app()
    from sound_track_agent.session import (
        ScoringSession, SegmentScore, SoundtrackDirective)
    ed = _ed(tmp_path)
    seg = SegmentScore(0, 0.0, 5.0); seg.music_prompt = "原prompt"
    ed._session = ScoringSession(source_mp4="", source_hash="", global_style="旧",
        frame_rate=24.0, segments=[seg])
    ed._on_directive_built(SoundtrackDirective(global_directive="史诗"),
                           apply_prompts=False)
    assert ed._session.directive.global_directive == "史诗"   # 方向更新
    assert ed._session.segments[0].music_prompt == "原prompt"  # prompt 不动
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_ai_wiring.py -q`
Expected: FAIL — `AttributeError: ... '_ai_chat'`

- [ ] **Step 3: 右栏改垂直分栏 + 建 AIChatPanel**

在 `drama_shot_master/ui/widgets/soundtrack_editor.py` 的 `_build_daw_main` 里，找到现有 Inspector 容器构建：

```python
        self._inspector_container = QWidget()
        self._inspector_container.setFixedWidth(280)
        ic_lay = QVBoxLayout(self._inspector_container)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        self._current_inspector = EmptyInspector()
        ic_lay.addWidget(self._current_inspector)
        main_h.addWidget(self._inspector_container)
```

替换为（右栏 = 垂直分栏：上 AIChatPanel + 下 Inspector）：

```python
        from PySide6.QtWidgets import QSplitter
        from drama_shot_master.ui.widgets.soundtrack_ai_chat import AIChatPanel
        right_col = QSplitter(Qt.Vertical)
        right_col.setFixedWidth(300)
        self._ai_chat = AIChatPanel()
        self._ai_chat.directiveRequested.connect(self._on_directive_requested)
        right_col.addWidget(self._ai_chat)
        self._inspector_container = QWidget()
        ic_lay = QVBoxLayout(self._inspector_container)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        self._current_inspector = EmptyInspector()
        ic_lay.addWidget(self._current_inspector)
        right_col.addWidget(self._inspector_container)
        right_col.setStretchFactor(0, 1)
        right_col.setStretchFactor(1, 1)
        main_h.addWidget(right_col)
```

（`Qt` 已在文件顶部 import；若 `QSplitter` 未导入则用上面的局部 import。）

- [ ] **Step 4: __init__ 加 worker 句柄 + 载入已有 directive**

在 `__init__` 的 `self._overlay = OverlayMixer(self)` 之后加：

```python
        self._dir_worker = None
```

在 `_try_load_existing` 末尾（`self._refresh_track_view()` 之后）加：

```python
        if self._session is not None and getattr(self, "_ai_chat", None):
            self._ai_chat.set_directive(self._session.directive)
```

- [ ] **Step 5: 加接线方法**

在 `_resolve_video_source` 附近加：

```python
    def _on_directive_requested(self, instruction: str, apply_prompts: bool):
        if self._session is None:
            self._ai_chat.append_error("尚无 session，请先「开始配乐」生成段落。")
            return
        if self._dir_worker is not None and self._dir_worker.isRunning():
            return
        from sound_track_agent.provider import build_soundtrack_provider
        provider = build_soundtrack_provider(self.cfg)
        cur = self._session.directive
        n = len(self._session.segments)

        def task():
            from sound_track_agent import directive_composer
            return directive_composer.synthesize_directive(
                provider, cur, instruction, n)

        self._ai_chat.set_busy(True)
        self._dir_worker = FunctionWorker(task)
        self._dir_worker.finished_with_result.connect(
            lambda d: self._on_directive_built(d, apply_prompts))
        self._dir_worker.failed.connect(
            lambda err: (self._ai_chat.set_busy(False),
                         self._ai_chat.append_error(f"AI 失败：{err}")))
        self._dir_worker.start()

    def _on_directive_built(self, new_dir, apply_prompts: bool):
        self._session.directive = new_dir
        if apply_prompts:
            from sound_track_agent.facade import apply_directive_to_prompts
            apply_directive_to_prompts(self._session)
        self._persist_session()
        self._ai_chat.set_directive(new_dir)
        self._ai_chat.set_busy(False)
        self._refresh_inspector()
        self._refresh_track_view()
```

- [ ] **Step 6: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ui/test_soundtrack_ai_wiring.py tests/test_ui/test_soundtrack_editor_daw_smoke.py -q`
Expected: PASS（4 新 wiring + 既有 daw smoke 全绿）

- [ ] **Step 7: 提交**

```bash
git add drama_shot_master/ui/widgets/soundtrack_editor.py tests/test_ui/test_soundtrack_ai_wiring.py
git commit -m "feat(soundtrack): 右栏垂直分栏 + AI 对话接线（指令→方向→写prompt，不生成）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 全套回归

- [ ] **Step 1: 配乐 agent + AI 子项目测试**

Run:
```bash
python -m pytest tests/test_sound_track_agent/ -q -p no:cacheprovider
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_ui/test_ai_chat_panel.py tests/test_ui/test_soundtrack_ai_wiring.py \
  tests/test_ui/test_soundtrack_play_mode.py tests/test_ui/test_soundtrack_editor_daw_smoke.py \
  tests/test_ui/daw/ -q -p no:cacheprovider
```
Expected: 全绿

- [ ] **Step 2: 最终提交（若有零散修复）**

```bash
git add -A && git commit -m "test(soundtrack): AI 对话子项目#1 全套回归绿

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review 记录

- **Spec 覆盖**：数据模型→T1；directive_composer→T2；apply_directive_to_prompts→T3；AIChatPanel→T4；右栏分栏+接线+持久化+不触发RunningHub→T5。✓
- **类型一致**：`SoundtrackDirective(global_directive/segment_directives/conversation)` T1 定义，T2/T3/T4/T5 一致；`synthesize_directive(provider,current,instruction,n_segments)` T2 定义、T5 调用一致；`apply_directive_to_prompts(session)` T3 定义、T5 调用一致；`directiveRequested(str,bool)` T4 定义、T5 连接一致；`set_directive/set_busy/append_error` T4 定义、T5 调用一致。✓
- **provider 简化**：spec 写「新增 _build_text_provider」，实改为复用 `build_soundtrack_provider` + `generate([], sys, user)` 纯文本调用（更简，满足"复用 deepseek/refine 配置"意图）。已在 T5 反映。
- **无占位符**：所有步骤含完整代码。✓
- **既有 API**：`compose_music_prompt(global_style, emotion, duration)`、`OpenAICompatProvider.generate(images, system_prompt, user_supplement)`、`FunctionWorker(task).finished_with_result/failed`、`build_soundtrack_provider(cfg)` 均现有。✓
```
