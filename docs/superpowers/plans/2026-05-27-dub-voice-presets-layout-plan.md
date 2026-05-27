# 配音快捷音色提示词 + 界面重排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给配音「音色设计」加可折叠分类快捷提示词（YAML 可配，方言/身份/场合/情感），并把配音任务窗放大到 1100×820、左右两栏重排、底部加「打开输出文件夹」。

**Architecture:** 词条数据由 `core/voice_presets.py`（内置默认）+ `assets/voice_presets.yaml`（开发者可编辑）提供，`load_presets()` 读 YAML 失败则回退默认。`DubPanel` 重排为左右两栏（输入左、可折叠快捷词面板右），插入到当前模式的描述框。

**Tech Stack:** Python, pyyaml, PySide6。

依据 spec：`docs/superpowers/specs/2026-05-27-dub-voice-presets-layout-design.md`。
关键事实：dub 生成落盘到 `Path(cfg.dub_output_dir or ".")/"dub"`（`dub_panel.py:223`）。DubPanel 现有 `_build_design_form`(含 `self.d_style` 音色描述)、`_build_clone_form`(含 `self.c_emo_text` 情感描述)、`current_mode()`、`to_payload/load_payload`、`_wire_dirty`、`_generate`，**这些保留**。`FunctionWorker`、`apply_dark_titlebar` 已有。

---

### Task 1: 词条数据 voice_presets.py + voice_presets.yaml

**Files:**
- Create: `drama_shot_master/core/voice_presets.py`
- Create: `drama_shot_master/assets/voice_presets.yaml`（由默认数据生成）
- Test: `tests/test_dub/test_voice_presets.py`

- [ ] **Step 1: 写失败测试**

`tests/test_dub/test_voice_presets.py`：

```python
from drama_shot_master.core import voice_presets as V


def test_defaults_structure():
    cats, note = V.load_presets()
    names = [n for n, _ in cats]
    assert names == ["方言", "人物身份", "场合", "情感语调"]
    counts = {n: len(items) for n, items in cats}
    assert counts == {"方言": 9, "人物身份": 8, "场合": 6, "情感语调": 8}
    # 每条 (label,text) 且非空
    for _n, items in cats:
        for label, text in items:
            assert label and text
    # 方言含湖南话
    dialects = dict(dict(cats)["方言"])
    assert "湖南话" in dialects and "长沙话" in dialects["湖南话"]
    assert note  # 方言提示非空


def test_load_custom_yaml(tmp_path):
    y = tmp_path / "p.yaml"
    y.write_text(
        "dialect_note: 自定义提示\n"
        "categories:\n"
        "  - name: 测试组\n"
        "    items:\n"
        "      - {label: A, text: 'aaa，'}\n"
        "      - {label: B, text: 'bbb，'}\n", encoding="utf-8")
    cats, note = V.load_presets(y)
    assert cats == [("测试组", [("A", "aaa，"), ("B", "bbb，")])]
    assert note == "自定义提示"


def test_missing_or_bad_yaml_falls_back(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert V.load_presets(missing)[0] == V._DEFAULTS
    bad = tmp_path / "bad.yaml"
    bad.write_text("::: not valid yaml :::\n- [", encoding="utf-8")
    assert V.load_presets(bad)[0] == V._DEFAULTS


def test_skips_empty_items(tmp_path):
    y = tmp_path / "p.yaml"
    y.write_text(
        "categories:\n"
        "  - name: G\n"
        "    items:\n"
        "      - {label: ok, text: 'x，'}\n"
        "      - {label: '', text: 'y，'}\n"      # 跳过(label空)
        "      - {label: nostxt}\n", encoding="utf-8")           # 跳过(无text)
    cats, _ = V.load_presets(y)
    assert cats == [("G", [("ok", "x，")])]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_dub/test_voice_presets.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 voice_presets.py**

```python
"""配音音色设计快捷提示词：内置默认 + 从 YAML 加载(开发者可更新最佳实践)。"""
from __future__ import annotations

from pathlib import Path

_DEFAULT_NOTE = ("提示：方言靠音色描述不一定生效（Qwen3-TTS 方言走预置音色）；"
                 "湖南话官方未列出。")

_DEFAULTS = [
    ("方言", [
        ("北京话", "用北京话朗读，京味儿胡同腔，自然地道，"),
        ("上海话", "用上海话朗读，吴侬软语，语调婉转，"),
        ("四川话", "用四川话朗读，川渝口音轻快诙谐，"),
        ("粤语", "用粤语朗读，口音正宗自然，"),
        ("南京话", "用南京话朗读，耐心温和，"),
        ("陕西话", "用陕西话朗读，秦腔老陕味道，"),
        ("天津话", "用天津话朗读，相声捧哏味十足，"),
        ("闽南语", "用闽南语/台湾腔朗读，亲切直爽，"),
        ("湖南话", "用湖南话（长沙话）朗读，口音自然浓郁，"),
    ]),
    ("人物身份", [
        ("旁白大叔", "沉稳磁性的中年大叔旁白音，"),
        ("少女", "清亮俏皮的少女声，音调偏高，"),
        ("青年男", "阳光朝气的青年男声，中频清晰，"),
        ("老者", "苍老醇厚的老者声，语速缓慢，"),
        ("御姐", "慵懒高冷的御姐音，气声明显，"),
        ("萝莉", "稚嫩软糯的萝莉音，"),
        ("知性女", "温柔知性的成熟女声，"),
        ("威严男", "低沉威严的男性权威嗓音，"),
    ]),
    ("场合", [
        ("新闻播报", "标准新闻播报腔，吐字清晰语速平稳，"),
        ("有声书", "有声书旁白，娓娓道来富感染力，"),
        ("广告配音", "广告配音，节奏明快富煽动力，"),
        ("客服", "客服音色，亲切耐心微笑感，"),
        ("纪录片", "纪录片解说，沉稳厚重，"),
        ("动画配音", "动画角色配音，夸张生动，"),
    ]),
    ("情感语调", [
        ("温柔", "语气温柔舒缓，"),
        ("激昂", "情绪激昂高亢，语速偏快，"),
        ("悲伤", "悲伤低沉，语速放慢带哽咽感，"),
        ("俏皮", "俏皮活泼，语调上扬，"),
        ("严肃", "严肃郑重，吐字铿锵，"),
        ("慵懒", "慵懒随性，气声放松，"),
        ("紧张", "紧张急促，语速加快，"),
        ("诙谐", "幽默诙谐，带笑意，"),
    ]),
]

_YAML_PATH = Path(__file__).resolve().parent.parent / "assets" / "voice_presets.yaml"


def load_presets(path: Path | None = None) -> tuple[list, str]:
    """返回 (categories, dialect_note)。categories = [(name, [(label,text),...]), ...]。
    读 YAML；缺失/解析失败/结构非法 → 回退内置 _DEFAULTS。"""
    p = path or _YAML_PATH
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _DEFAULTS, _DEFAULT_NOTE
        cats = []
        for c in data.get("categories", []) or []:
            name = c.get("name")
            items = [(it["label"], it["text"])
                     for it in (c.get("items") or [])
                     if isinstance(it, dict) and it.get("label") and it.get("text")]
            if name and items:
                cats.append((name, items))
        if not cats:
            return _DEFAULTS, _DEFAULT_NOTE
        return cats, (data.get("dialect_note") or _DEFAULT_NOTE)
    except Exception:
        return _DEFAULTS, _DEFAULT_NOTE
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_dub/test_voice_presets.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 由默认数据生成 assets/voice_presets.yaml**

Run（保证 YAML 与默认一致，避免手抄）：
```bash
python -c "
import yaml
from drama_shot_master.core.voice_presets import _DEFAULTS, _DEFAULT_NOTE
from pathlib import Path
doc = {'dialect_note': _DEFAULT_NOTE,
       'categories': [{'name': n, 'items': [{'label': l, 'text': t} for l, t in items]}
                      for n, items in _DEFAULTS]}
Path('drama_shot_master/assets/voice_presets.yaml').write_text(
    '# 配音音色设计快捷提示词（开发者可编辑更新；缺失/损坏时回退代码内置默认）\n'
    + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding='utf-8')
print('written')
"
```
然后确认从 YAML 读出的与默认一致：
```bash
python -c "
from drama_shot_master.core.voice_presets import load_presets, _DEFAULTS
cats, note = load_presets()
assert cats == _DEFAULTS, '生成的 YAML 与默认不一致'
print('YAML 与默认一致 OK，分类:', [n for n,_ in cats])
"
```
Expected: `written` 然后 `YAML 与默认一致 OK …`

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/core/voice_presets.py drama_shot_master/assets/voice_presets.yaml tests/test_dub/test_voice_presets.py
git commit -m "feat(dub): 快捷音色提示词数据(内置默认+YAML可配加载)"
```

---

### Task 2: DubPanel 左右两栏重排 + 可折叠快捷词面板 + 打开输出文件夹 + 窗口放大

**Files:**
- Modify: `drama_shot_master/ui/panels/dub_panel.py`
- Modify: `drama_shot_master/ui/windows/dub_task_window.py`

- [ ] **Step 1: 窗口放大到 1100×820**

`drama_shot_master/ui/windows/dub_task_window.py` 把 `self.resize(620, 720)` 改为：
```python
        self.resize(1100, 820)        # 与视频/配乐任务窗一致
```

- [ ] **Step 2: dub_panel 增加导入 + 折叠组件 + 调色板/插入/打开目录**

`drama_shot_master/ui/panels/dub_panel.py` 顶部导入区，把 widgets 导入补上 `QToolButton, QScrollArea`（若已在则跳过），并加 `QUrl/QDesktopServices` 用到时局部导入即可。在导入区之后、`class DubPanel` 之前，加折叠组件：

```python
from PySide6.QtWidgets import QGridLayout


class _CollapsibleGroup(QWidget):
    """折叠分组：标题 QToolButton 切换内容显隐；set_buttons 建 4 列流式网格。"""

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        self.head = QToolButton()
        self.head.setText(title)
        self.head.setCheckable(True)
        self.head.setChecked(expanded)
        self.head.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.head.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.head.setStyleSheet("QToolButton{border:none; font-weight:600; color:#9aa;}")
        self.body = QWidget()
        self._grid = QGridLayout(self.body)
        self._grid.setContentsMargins(8, 2, 0, 6); self._grid.setSpacing(4)
        self.body.setVisible(expanded)
        v.addWidget(self.head); v.addWidget(self.body)
        self.head.toggled.connect(self._on_toggle)

    def _on_toggle(self, on: bool):
        self.head.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)

    def set_buttons(self, widgets: list):
        for i, w in enumerate(widgets):
            self._grid.addWidget(w, i // 4, i % 4)   # 4 列流式
```

- [ ] **Step 3: 重排 _build_ui 为左右两栏 + 底部三按钮**

把 `dub_panel.py` 的 `_build_ui` 主体（mode 行之后的 stack 与底部 bar）改为左右两栏布局。将原来的：
```python
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_design_form())   # idx0
        self.stack.addWidget(self._build_clone_form())    # idx1
        self.stack.setCurrentIndex(1)
        root.addWidget(self.stack, 1)
        self.mode_group.idClicked.connect(self.stack.setCurrentIndex)
        self.mode_group.idClicked.connect(lambda *_: self.dirty.emit())
        self._wire_dirty()
```
替换为：
```python
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_design_form())   # idx0
        self.stack.addWidget(self._build_clone_form())    # idx1
        self.stack.setCurrentIndex(1)
        self.mode_group.idClicked.connect(self.stack.setCurrentIndex)
        self.mode_group.idClicked.connect(lambda *_: self.dirty.emit())
        self._wire_dirty()

        cols = QHBoxLayout()
        cols.addWidget(self.stack, 3)                     # 左栏：输入
        cols.addWidget(self._build_palette(), 0)          # 右栏：快捷词
        root.addLayout(cols, 1)
```
并把底部 bar 段（`bar = QHBoxLayout()` … `root.addLayout(bar)`）中加入「打开输出文件夹」按钮——在 `self.btn_open`（打开结果）之后插入：
```python
        self.btn_open_dir = QPushButton("打开输出文件夹")
        self.btn_open_dir.clicked.connect(self._open_output_dir)
```
并把它加进 bar：`bar.addWidget(self.btn_gen); bar.addWidget(self.btn_open); bar.addWidget(self.btn_open_dir)` 然后 `bar.addWidget(self.status_lbl, 1)`。

- [ ] **Step 4: 实现 _build_palette / _insert_preset / _open_output_dir**

在 `dub_panel.py` 的 `DubPanel` 内（`_wire_dirty` 附近）加：

```python
    def _build_palette(self) -> QWidget:
        from drama_shot_master.core.voice_presets import load_presets
        cats, note = load_presets()
        wrap = QWidget(); wrap.setFixedWidth(300)
        outer = QVBoxLayout(wrap); outer.setContentsMargins(6, 0, 0, 0)
        outer.addWidget(QLabel("快捷音色提示词"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget(); iv = QVBoxLayout(inner); iv.setContentsMargins(0, 0, 0, 0)
        note_lbl = QLabel(note); note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet("color:#888; font-size:9pt;")
        iv.addWidget(note_lbl)
        expand_default = {"方言", "情感语调"}
        for name, items in cats:
            grp = _CollapsibleGroup(name, expanded=(name in expand_default))
            btns = []
            for label, text in items:
                b = QPushButton(label)
                b.clicked.connect(lambda _=False, t=text: self._insert_preset(t))
                btns.append(b)
            grp.set_buttons(btns)
            iv.addWidget(grp)
        iv.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return wrap

    def _insert_preset(self, text: str):
        # 音色设计→音色描述；声音克隆→情感描述
        target = self.d_style if self.current_mode() == "design" else self.c_emo_text
        target.insertPlainText(text)

    def _open_output_dir(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        d = Path(self.cfg.dub_output_dir or ".") / "dub"
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
```

- [ ] **Step 5: 离屏构造校验**

Run:
```bash
QT_QPA_PLATFORM=offscreen python -c "
from PySide6.QtWidgets import QApplication
a=QApplication([])
from drama_shot_master.config import load_config
from drama_shot_master.ui.panels.dub_panel import DubPanel
p=DubPanel(load_config())
# 设计模式：点一个方言按钮的插入逻辑（直接调 _insert_preset）
p.rb_design.setChecked(True)
p._insert_preset('用粤语朗读，口音正宗自然，')
assert '粤语' in p.d_style.toPlainText()
# 克隆模式插到情感描述
p.rb_clone.setChecked(True)
p._insert_preset('语气温柔舒缓，')
assert '温柔' in p.c_emo_text.toPlainText()
assert p.btn_open_dir is not None
print('palette insert + open-dir OK')
from drama_shot_master.ui.windows.dub_task_window import DubTaskWindow
from drama_shot_master.core.dub_task_store import DubTask
w=DubTaskWindow(DubTask(id='1',name='x',mode='clone'), load_config())
print('dub window size:', w.size().width(), w.size().height())
assert (w.size().width(), w.size().height())==(1100,820)
print('OK')
" 2>&1 | grep -v "qt.qpa\|^QND\|propagateSizeHints"
```
Expected: `palette insert + open-dir OK` / `dub window size: 1100 820` / `OK`

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/panels/dub_panel.py drama_shot_master/ui/windows/dub_task_window.py
git commit -m "feat(ui): 配音窗1100x820+左右两栏，可折叠快捷音色提示词面板，加打开输出文件夹"
```

---

## Self-Review

**Spec 覆盖**：
- 快捷词 YAML 可配加载 + 内置兜底 → Task 1（voice_presets.py + yaml + load_presets，含缺失/损坏/自定义/跳空项测试）。✅
- 4 分类词条（方言9含湖南话/身份8/场合6/情感8）+ 方言提示 → Task 1 `_DEFAULTS` + 测试。✅
- 窗口 1100×820 → Task 2 Step1。✅
- 左右两栏重排 → Task 2 Step3。✅
- 右栏可折叠分组（方言/情感默认展开） → `_CollapsibleGroup` + `_build_palette` expand_default。✅
- 点按钮插入到 音色描述/情感描述 → `_insert_preset`（design→d_style, clone→c_emo_text）。✅
- 打开输出文件夹 → `_open_output_dir`（与 _generate 落盘 `dub_output_dir/dub` 一致）。✅
- QScrollArea 兜底 → `_build_palette` 内 scroll。✅
- 保持信号/持久化不变（插入触发 textChanged→dirty 自动存）→ d_style/c_emo_text 已在 `_wire_dirty` 连了 textChanged，插入即标脏。✅

**占位扫描**：无 TBD。`_CollapsibleGroup` 已是完整可用代码（__init__ 建 QGridLayout(self.body)，set_buttons 仅 addWidget）。

**类型/签名一致性**：`load_presets(path=None)->(cats,note)`，`cats=[(name,[(label,text)])]` 在 Task1 定义、Task2 `_build_palette` 消费一致；`_insert_preset(text)` 用 `self.d_style`/`self.c_emo_text`/`current_mode()`（均 DubPanel 既有）；`btn_open_dir`/`_open_output_dir` 一致；窗口 resize 数值与视频窗一致。

**给实现者提醒**：在 `dub_panel.py` 的 QtWidgets 导入里补 `QToolButton, QScrollArea, QGridLayout`（`Qt`、`QLabel`、`QPushButton`、`QVBoxLayout`、`QHBoxLayout` 已有）。`_CollapsibleGroup` 直接照抄即可。
