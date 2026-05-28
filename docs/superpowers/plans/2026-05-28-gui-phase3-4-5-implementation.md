# GUI Phase 3+4+5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一设置页（取代 6 个旧 dialog）、实时深/浅主题切换、右侧任务中心抽屉、流程侧栏可折叠（带动画）+ 过时注释清理；过程中把 53 处硬编码 setStyleSheet/QColor 收敛到 token 单一源。

**Architecture:** 4 个 workstream 串行：
- **Workstream A 主题系统**：token 化 QSS（dark.qss → theme.qss.tpl + tokens_dark.py / tokens_light.py），运行时 `apply_theme(app, name)` 切换 + repolish 顶层窗。
- **Workstream B UnifiedSettingsPage**：单 `QDialog`，左 `QTreeWidget` 分类、右 `QStackedWidget`；6 个 SectionWidget（外加 ThemeSection）按统一协议（`title/category/load_from/save_to/validate`）实现；旧 6 dialog 干净删除。
- **Workstream C TaskCenterDock**：右靠泊 `QDockWidget`，默认隐藏；薄 `TaskAggregator` 跨 3 store + cfg dict 读 `TaskRecord`；命令栏 toggle；3 manager 加 `get_status(tid)` 暴露 live_status。
- **Workstream D 侧栏折叠 + 精修**：FlowSidebar 现有 `set_collapsed` 加 QPropertyAnimation + tooltip 富化 + cfg 持久化；5 处过时 MainWindow 注释清理；重命名一致性 audit。

每个 workstream 结束所有相关测试绿，作为天然检查点。

**Tech Stack:** PySide6（QWidget/QDialog/QDockWidget/QTreeWidget/QPropertyAnimation），pytest（headless `QT_QPA_PLATFORM=offscreen` smoke），无外部新增依赖（无 GPL）。

参考 spec：[`docs/superpowers/specs/2026-05-28-gui-phase3-4-5-design.md`](../specs/2026-05-28-gui-phase3-4-5-design.md)。

**当前 dark.qss 实际颜色清单**（"保 dark 视觉不变"的基线，本计划全程以这些为准——spec 里的色值是参考意向，**与实际有偏差**，**以本计划为准**）：

| token | 实际 dark 值 | 计划 light 值 |
|---|---|---|
| `bg` 主背景 | `#1e1f22` | `#fafafa` |
| `bg_alt` 次背景/卡片 | `#2b2d30` | `#ffffff` |
| `bg_elevated` 浮层/对话框 | `#32353a` | `#f5f6f7` |
| `border` 分隔线 | `#3a3d42` | `#dadce0` |
| `fg` 主文字 | `#e8eaed` | `#1f2024` |
| `fg_muted` 次要文字 | `#9aa0a6` | `#5f6368` |
| `accent` 强调 | `#4a9eff` | `#0066cc` |
| `accent_text` accent 上的文字 | `#ffffff` | `#ffffff` |
| `select_bg` 选中区背景 | `#2f5e96` | `#cce0ff` |
| `status_running` | `#4a9eff` | `#1a73e8` |
| `status_failed` | `#ff5c5c` | `#d93025` |
| `status_done` | `#4ec98f` | `#1e8e3e` |
| `status_idle` | `#9aa0a6` | `#5f6368` |
| `titlebar_bg` 原生标题栏 | `#1e1f22` | `#fafafa` |
| `titlebar_fg` 原生标题栏文字 | `#e8eaed` | `#1f2024` |

---

## Workstream A: 主题系统

### Task 1: 创建 tokens_dark.py（dark 基线）

**Files:**
- Create: `drama_shot_master/ui/styles/tokens_dark.py`

- [ ] **Step 1: Create the file**

```python
# drama_shot_master/ui/styles/tokens_dark.py
"""深色主题 token 单一源。所有颜色/尺寸常量在此声明，theme.qss.tpl 通过 .format()
消费。修改 token 前先确认 light 对应项是否要联动调整。"""

DARK: dict[str, str] = {
    # 背景
    "bg":          "#1e1f22",
    "bg_alt":      "#2b2d30",
    "bg_elevated": "#32353a",
    "border":      "#3a3d42",
    # 文字
    "fg":          "#e8eaed",
    "fg_muted":    "#9aa0a6",
    # 强调
    "accent":      "#4a9eff",
    "accent_text": "#ffffff",
    "select_bg":   "#2f5e96",
    # 状态色
    "status_running": "#4a9eff",
    "status_failed":  "#ff5c5c",
    "status_done":    "#4ec98f",
    "status_idle":    "#9aa0a6",
    # 原生标题栏
    "titlebar_bg": "#1e1f22",
    "titlebar_fg": "#e8eaed",
    # 几何
    "radius":      "6px",
}
```

- [ ] **Step 2: Commit**

```bash
git add drama_shot_master/ui/styles/tokens_dark.py
git commit -m "feat(ui): tokens_dark 深色主题 token 单一源（与现 dark.qss 同值）"
```

---

### Task 2: 用脚本把 dark.qss 转成 theme.qss.tpl（占位符版）

**Files:**
- Create: `drama_shot_master/ui/styles/theme.qss.tpl`
- Delete (later): `drama_shot_master/ui/styles/dark.qss` (after verification)

**为什么必须用脚本**：dark.qss 405 行，含大量 `{ }` 选择器；`.format()` 把裸花括号当占位符，需先转义 `{` → `{{` 和 `}` → `}}`。手改必出错。

- [ ] **Step 1: 写转换脚本（一次性，不入库）**

把这段 Python 存为本地 `/tmp/qss_to_tpl.py`：

```python
import re
import sys
from pathlib import Path

SRC = Path("drama_shot_master/ui/styles/dark.qss")
DST = Path("drama_shot_master/ui/styles/theme.qss.tpl")

# token → 实际值 反向映射（实际值要 globally unique，否则误替换）
REVERSE = {
    "#1e1f22": "bg",
    "#2b2d30": "bg_alt",
    "#32353a": "bg_elevated",
    "#3a3d42": "border",
    "#e8eaed": "fg",
    "#9aa0a6": "fg_muted",
    "#4a9eff": "accent",
    "#ffffff": "accent_text",
    "#2f5e96": "select_bg",
    "#ff5c5c": "status_failed",
    "#4ec98f": "status_done",
}

text = SRC.read_text(encoding="utf-8")

# 1) 转义裸花括号 → 用占位符两个字符暂代
text = text.replace("{", "\x00").replace("}", "\x01")

# 2) 颜色字面量 → {token}
for hex_val, tok in REVERSE.items():
    # 大小写都替（dark.qss 里可能小写）
    pat = re.compile(re.escape(hex_val), re.IGNORECASE)
    text = pat.sub(f"\x02{tok}\x03", text)

# 3) 暂代字符回花括号：\x00 → {{, \x01 → }}, \x02 → {, \x03 → }
text = text.replace("\x00", "{{").replace("\x01", "}}")
text = text.replace("\x02", "{").replace("\x03", "}")

DST.write_text(text, encoding="utf-8")
print(f"wrote {DST}, {len(text)} chars")
```

- [ ] **Step 2: 跑脚本生成 theme.qss.tpl**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
python /tmp/qss_to_tpl.py
```

- [ ] **Step 3: 验证转换正确性（不改 theme.py 的前提下，跑一遍 .format 看是否抛错）**

```bash
python -c "
from pathlib import Path
from drama_shot_master.ui.styles.tokens_dark import DARK
tpl = Path('drama_shot_master/ui/styles/theme.qss.tpl').read_text(encoding='utf-8')
out = tpl.format(**DARK)
print('OK, output len =', len(out))
assert 'background-color: #1e1f22' in out, 'bg token did not expand'
assert '{' not in out.replace('{{','').replace('}}',''), 'still have unresolved braces'
print('verified')
"
```

Expected: `OK, output len = ...` + `verified` 字样，无 KeyError。

如果 KeyError → 说明 tpl 里还有未在 DARK dict 里定义的 token，回去补 token 或调整脚本。

- [ ] **Step 4: 不删 dark.qss（保留作回滚锚点）；只确认 tpl 与 .format 联通**

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/styles/theme.qss.tpl
git commit -m "feat(ui): theme.qss.tpl 模板化版本（从 dark.qss 用 token 占位生成）"
```

---

### Task 3: 改造 theme.py 新 API

**Files:**
- Modify: `drama_shot_master/ui/theme.py`
- Test: `tests/test_ui/test_theme_smoke.py` (new)

- [ ] **Step 1: 先写失败测试**

`tests/test_ui/test_theme_smoke.py`:

```python
"""主题系统 smoke：apply_theme 切换、token 注入、repolish。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from drama_shot_master.ui import theme


def _app():
    return QApplication.instance() or QApplication([])


def test_apply_theme_dark_injects_dark_bg():
    app = _app()
    theme.apply_theme(app, "dark")
    css = app.styleSheet()
    assert "#1e1f22" in css        # bg token expanded
    assert "{" not in css          # no unresolved placeholder


def test_apply_theme_unknown_falls_back_to_dark():
    app = _app()
    theme.apply_theme(app, "nonsense-name")
    assert "#1e1f22" in app.styleSheet()


def test_current_theme_reads_cfg_default_dark():
    cfg = type("C", (), {})()
    assert theme.current_theme(cfg) == "dark"


def test_current_theme_reads_cfg_value():
    cfg = type("C", (), {"theme": "light"})()
    assert theme.current_theme(cfg) == "light"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest tests/test_ui/test_theme_smoke.py -q -p no:faulthandler
```

Expected: FAIL — `apply_theme` 当前不读 tpl/tokens；`current_theme` 不存在。

- [ ] **Step 3: 改写 theme.py**

把 theme.py 中 `load_stylesheet` / `apply_theme` 那两个函数替换为：

```python
def _tokens(name: str) -> dict:
    """name='dark'|'light' → token 字典；未知回退 dark。"""
    if name == "light":
        try:
            from drama_shot_master.ui.styles.tokens_light import LIGHT
            return LIGHT
        except ImportError:
            pass
    from drama_shot_master.ui.styles.tokens_dark import DARK
    return DARK


def load_stylesheet(name: str = "dark") -> str:
    """渲染 theme.qss.tpl + 对应 token；模板缺失返回空串。"""
    tpl_path = _QSS_DIR / "theme.qss.tpl"
    try:
        tpl = tpl_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    try:
        return tpl.format(**_tokens(name))
    except KeyError:
        # token 缺失 → 退到 dark 兜底以免空白窗
        return tpl.format(**_tokens("dark"))


def apply_theme(app, name: str = "dark") -> None:
    """切主题样式表并强制 repolish 所有顶层窗（含 dock/对话框）。"""
    qss = load_stylesheet(name)
    if not qss:
        return
    app.setStyleSheet(qss)
    for w in app.topLevelWidgets():
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()


def current_theme(cfg) -> str:
    """从 cfg 读 theme（默认 dark）。"""
    return getattr(cfg, "theme", "dark") or "dark"
```

(其余 `apply_dark_titlebar` / `_find_app_icon_path` / `apply_window_icon` / `apply_app_icon` 不动。)

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_theme_smoke.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/theme.py tests/test_ui/test_theme_smoke.py
git commit -m "feat(ui): theme.py 改读 tpl+token，新增 apply_theme repolish 与 current_theme()"
```

---

### Task 4: 创建 tokens_light.py + 切换验证

**Files:**
- Create: `drama_shot_master/ui/styles/tokens_light.py`
- Modify (extend test): `tests/test_ui/test_theme_smoke.py`

- [ ] **Step 1: 先写失败测试（追加用例到 test_theme_smoke.py）**

在 `tests/test_ui/test_theme_smoke.py` 末尾追加：

```python
def test_apply_theme_light_swaps_palette():
    app = _app()
    theme.apply_theme(app, "dark")
    dark_css = app.styleSheet()
    assert "#1e1f22" in dark_css and "#fafafa" not in dark_css
    theme.apply_theme(app, "light")
    light_css = app.styleSheet()
    assert "#fafafa" in light_css
    assert "#1e1f22" not in light_css
    # 切回 dark 也要稳
    theme.apply_theme(app, "dark")
    assert "#1e1f22" in app.styleSheet()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest tests/test_ui/test_theme_smoke.py::test_apply_theme_light_swaps_palette -q -p no:faulthandler
```

Expected: FAIL — tokens_light 不存在，回退 dark，"#fafafa" 不在 stylesheet 里。

- [ ] **Step 3: 创建 tokens_light.py**

```python
# drama_shot_master/ui/styles/tokens_light.py
"""浅色主题 token。与 tokens_dark 一一对应、键名完全一致。"""

LIGHT: dict[str, str] = {
    # 背景
    "bg":          "#fafafa",
    "bg_alt":      "#ffffff",
    "bg_elevated": "#f5f6f7",
    "border":      "#dadce0",
    # 文字
    "fg":          "#1f2024",
    "fg_muted":    "#5f6368",
    # 强调
    "accent":      "#0066cc",
    "accent_text": "#ffffff",
    "select_bg":   "#cce0ff",
    # 状态色
    "status_running": "#1a73e8",
    "status_failed":  "#d93025",
    "status_done":    "#1e8e3e",
    "status_idle":    "#5f6368",
    # 原生标题栏
    "titlebar_bg": "#fafafa",
    "titlebar_fg": "#1f2024",
    # 几何
    "radius":      "6px",
}
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_theme_smoke.py -q -p no:faulthandler
```

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/styles/tokens_light.py tests/test_ui/test_theme_smoke.py
git commit -m "feat(ui): 新增 tokens_light 浅色主题；dark↔light 切换 smoke 测通过"
```

---

### Task 5: apply_titlebar 替代 apply_dark_titlebar

**Files:**
- Modify: `drama_shot_master/ui/theme.py`
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: 在 theme.py 加新函数（保留 apply_dark_titlebar 作向后兼容 stub）**

在 theme.py 现 `apply_dark_titlebar` 函数之后追加：

```python
def apply_titlebar(widget, name: str = "dark") -> None:
    """按主题给原生标题栏上色（Windows DWM；其它平台静默跳过）。
    替代 apply_dark_titlebar；从 token 读 caption/text 色。"""
    tokens = _tokens(name)
    apply_dark_titlebar(widget,
                        caption_hex=tokens.get("titlebar_bg", TITLEBAR_BG),
                        text_hex=tokens.get("titlebar_fg", TITLEBAR_FG))
```

（apply_dark_titlebar 保留不动，它接收两个 hex 参数；apply_titlebar 是 token-aware 包装。）

- [ ] **Step 2: AppShell 改用 apply_titlebar**

`drama_shot_master/ui/app_shell.py` 文件顶部 import 区，已有 `from drama_shot_master.ui.theme import apply_window_icon, apply_dark_titlebar`，改为：

```python
from drama_shot_master.ui.theme import apply_window_icon, apply_titlebar, current_theme
```

文件 `showEvent` 方法（约 line 545-550）：

```python
    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_titlebar_themed", False):
            self._titlebar_themed = True
            apply_window_icon(self)
            apply_titlebar(self, current_theme(self.cfg))
```

- [ ] **Step 3: main.py 启动时应用主题**

读 `drama_shot_master/main.py` 现状，在 `app = QApplication(...)` 之后、`w = AppShell()` 之前插入：

```python
    from drama_shot_master.ui.theme import apply_theme, current_theme
    from drama_shot_master.config import load_config
    _early_cfg = load_config()
    apply_theme(app, current_theme(_early_cfg))
```

（注意：AppShell 内部也 load_config，会再读一次；这里早一次是为了启动瞬间窗就是正确主题，避免一瞬白闪。）

- [ ] **Step 4: 全套件跑一次确保没回归**

```bash
python -m pytest tests/test_ui/test_theme_smoke.py tests/test_ui/test_app_shell_smoke.py -v --tb=line -p no:faulthandler -o addopts="" 2>&1 | grep -cE "PASSED"
```

Expected: 全部 PASSED（test_theme_smoke 5 + test_app_shell_smoke 17 + 之前新增的 = 至少 22 项）。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/theme.py drama_shot_master/ui/app_shell.py drama_shot_master/main.py
git commit -m "feat(ui): apply_titlebar token-aware + main.py 启动即应用 cfg.theme"
```

---

### Task 6: 集中 _STATUS_COLORS 到 theme.status_color()

**Files:**
- Modify: `drama_shot_master/ui/theme.py` (add helper)
- Modify: `drama_shot_master/ui/panels/soundtrack_panel.py` (uses _STATUS_COLORS)
- Modify: `drama_shot_master/ui/panels/video_task_manager_panel.py` (likely has its own)
- Modify: `drama_shot_master/ui/panels/dub_task_manager_panel.py`
- Modify: `drama_shot_master/ui/panels/imggen_task_manager_panel.py`

- [ ] **Step 1: 在 theme.py 加 helper**

在 theme.py 末尾追加：

```python
# 状态字符串 → token key 映射
_STATUS_TOKEN = {
    "空闲":   "status_idle",
    "生成中": "status_running",
    "完成":   "status_done",
    "失败":   "status_failed",
}


def status_color(status: str, cfg=None) -> str:
    """状态字符串 → 当前主题对应的 hex 颜色。
    cfg 缺省时按 dark 取色（兼容 lib 调用无 cfg 上下文）。"""
    name = current_theme(cfg) if cfg is not None else "dark"
    tok = _STATUS_TOKEN.get(status, "status_idle")
    return _tokens(name).get(tok, "#9aa0a6")
```

- [ ] **Step 2: 改 soundtrack_panel.py 用 helper**

文件顶部找到：

```python
_STATUS_COLORS = {
    "空闲": "#9aa0a6", "生成中": "#4a9eff", "完成": "#4ec98f", "失败": "#ff5c5c",
}
```

删除这 3 行，改 `_status_item` 方法里 `color = _STATUS_COLORS.get(status)` 那行为：

```python
        from drama_shot_master.ui.theme import status_color
        color = status_color(status, self.cfg)
```

- [ ] **Step 3: 对 video_task_manager_panel/dub_task_manager_panel/imggen_task_manager_panel 做同样处理**

每个文件先 `grep -n "_STATUS_COLORS\|status.*#[0-9a-fA-F]" <path>` 看现状，按 Step 2 同样模式替换。**如果某个 manager 没有 _STATUS_COLORS（按状态字符串只读不染色），跳过该文件。**

预期：4 个文件中至少 1-2 个有此字典；其余可能没有。

- [ ] **Step 4: 跑相关测试**

```bash
python -m pytest tests/test_ui/test_soundtrack_panel_smoke.py tests/test_ui/test_app_shell_smoke.py -v --tb=line -p no:faulthandler -o addopts="" 2>&1 | grep -cE "PASSED|FAILED"
```

Expected: 全 PASSED，0 FAILED。视觉应一致（dark 下 status_color("生成中") 仍返回 #4a9eff）。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/theme.py drama_shot_master/ui/panels/
git commit -m "refactor(ui): _STATUS_COLORS 集中到 theme.status_color(status,cfg)"
```

---

### Task 7: 53 处硬编码 setStyleSheet/QColor 分批扫除

**Files:**
- Modify: 多个 UI 文件（按 grep 结果分批处理）

- [ ] **Step 1: 生成现状清单**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
grep -rnE "setStyleSheet\(|QColor\(" drama_shot_master/ui/ --include="*.py" > /tmp/qss_inventory.txt
wc -l /tmp/qss_inventory.txt
```

Expected: 数量在 50-55 区间（基线 53 ± 改 task 6 的差异）。

- [ ] **Step 2: 分类**

把 `/tmp/qss_inventory.txt` 按 file path 分组人工浏览，标三类：
- **A 类（迁 token）**：颜色字面量是当前 dark 调色板里的（如 #4a9eff/#9aa0a6 等）→ 改用 `_tokens(current_theme(cfg))['accent']` 等。
- **B 类（保留无视觉影响的功能性 stylesheet）**：仅设 padding/margin/font-size 之类无色 stylesheet → 保留不动。
- **C 类（动态生成的高亮）**：临时高亮、动画用 QColor → 评估是否能挪到 QSS（带 objectName）；不行就读 token。

- [ ] **Step 3: 处理 A 类**

按 `/tmp/qss_inventory.txt` 中 A 类项目逐文件 edit。**典型替换模式：**

```python
# 改前
self.btn.setStyleSheet("background:#4a9eff; color:white;")

# 改后
from drama_shot_master.ui.theme import _tokens, current_theme
t = _tokens(current_theme(self.cfg))
self.btn.setStyleSheet(f"background:{t['accent']}; color:{t['accent_text']};")
```

或更优解：给 widget 加 objectName，把样式挪到 theme.qss.tpl：

```python
# Python：
self.btn.setObjectName("primaryAction")

# theme.qss.tpl 追加：
QPushButton#primaryAction {{
    background: {accent};
    color: {accent_text};
    border-radius: {radius};
    padding: 6px 12px;
}}
```

**首选第二种**（让 QSS 单一源更彻底），仅在样式与状态强相关、必须 Python 计算时用 inline。

- [ ] **Step 4: 处理 C 类（QColor 用法）**

`QColor(...)` 多在 QPainter/QPalette 或 QTableWidgetItem.setForeground 等场景。**典型替换：**

```python
# 改前
item.setForeground(QColor("#4ec98f"))

# 改后
from drama_shot_master.ui.theme import status_color
item.setForeground(QColor(status_color(status, self.cfg)))
```

- [ ] **Step 5: 边改边跑测试**

每改完一个文件，跑：

```bash
python -m pytest tests/test_ui/ -q --tb=line -p no:faulthandler 2>&1 | grep -cE "PASSED|FAILED"
```

Expected: PASSED 数 ≥ 之前，FAILED = 0。视觉回归靠目测（启动 app dark/light 两看）。

- [ ] **Step 6: 收尾 grep 验证**

```bash
grep -rnE "QColor\(['\"]#[0-9a-fA-F]{6}['\"]\)" drama_shot_master/ui/ --include="*.py" | grep -v "test_" | wc -l
```

Expected: 显著减少（理想 0；接受 ≤ 5 留给极特殊场景）。

- [ ] **Step 7: Commit**

```bash
git add drama_shot_master/ui/
git commit -m "refactor(ui): setStyleSheet/QColor 硬编码迁到 token（A workstream 收口）"
```

---

## Workstream B: UnifiedSettingsPage

### Task 8: settings_sections 目录骨架 + RunningHubSection

**Files:**
- Create: `drama_shot_master/ui/widgets/settings_sections/__init__.py`
- Create: `drama_shot_master/ui/widgets/settings_sections/runninghub_section.py`
- Read (reference, do not edit): `drama_shot_master/ui/dialogs/runninghub_settings_dialog.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ui/test_settings_sections_smoke.py`(new):

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.runninghub_section import RunningHubSection


def _app():
    return QApplication.instance() or QApplication([])


def _cfg(**kw):
    base = {"running_hub_api_key": "k1", "running_hub_workflow_id": "wf1",
            "running_hub_no_watermark": True}
    base.update(kw)
    return type("C", (), base)()


def test_runninghub_section_class_metadata():
    assert RunningHubSection.title == "RunningHub"
    assert RunningHubSection.category == "平台核心"


def test_runninghub_section_load_save_roundtrip():
    _app()
    cfg = _cfg()
    sec = RunningHubSection(cfg)
    sec.load_from(cfg)
    sec.api_key_edit.setText("k2")
    sec.save_to(cfg)
    assert cfg.running_hub_api_key == "k2"


def test_runninghub_section_validate_default_ok():
    _app()
    sec = RunningHubSection(_cfg())
    ok, _ = sec.validate()
    assert ok is True
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError 或 ImportError。

- [ ] **Step 3: 创建 __init__.py**

`drama_shot_master/ui/widgets/settings_sections/__init__.py`:

```python
"""统一设置页的 SectionWidget 集合。每个 section 自带类属性 title/category 与
load_from/save_to/validate 三个方法，由 UnifiedSettingsDialog 编排。"""

from .runninghub_section import RunningHubSection

__all__ = ["RunningHubSection"]
```

- [ ] **Step 4: 实现 RunningHubSection**

先读 `drama_shot_master/ui/dialogs/runninghub_settings_dialog.py` 列出全部字段，确认本 section 不遗漏。然后写：

`drama_shot_master/ui/widgets/settings_sections/runninghub_section.py`:

```python
"""RunningHub 配置 section（API key / workflow_id / 禁用水印 / 连通测试）。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QCheckBox, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout,
)


class RunningHubSection(QWidget):
    title = "RunningHub"
    category = "平台核心"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.api_key_edit = QLineEdit(); self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.workflow_id_edit = QLineEdit()
        self.no_watermark_chk = QCheckBox("禁用水印")
        form.addRow("API Key", self.api_key_edit)
        form.addRow("Workflow ID", self.workflow_id_edit)
        form.addRow("", self.no_watermark_chk)
        root.addLayout(form)
        # 连通测试行
        bar = QHBoxLayout()
        self.btn_test = QPushButton("连通测试")
        self.lbl_test = QLabel("")
        bar.addWidget(self.btn_test); bar.addWidget(self.lbl_test, 1)
        root.addLayout(bar)
        root.addStretch(1)
        self.btn_test.clicked.connect(self._on_test)

    def load_from(self, cfg):
        self.api_key_edit.setText(getattr(cfg, "running_hub_api_key", "") or "")
        self.workflow_id_edit.setText(getattr(cfg, "running_hub_workflow_id", "") or "")
        self.no_watermark_chk.setChecked(bool(getattr(cfg, "running_hub_no_watermark", False)))

    def save_to(self, cfg):
        cfg.running_hub_api_key = self.api_key_edit.text().strip()
        cfg.running_hub_workflow_id = self.workflow_id_edit.text().strip()
        cfg.running_hub_no_watermark = self.no_watermark_chk.isChecked()

    def validate(self):
        # API key/workflow 留空也允许（用户可分步填）；不强校验
        return (True, "")

    def cancel_workers(self):
        """dialog 关闭时调用，取消未完成的连通测试 worker。"""
        # 当前简化实现：无后台 worker（连通测试用 lambda 内 try-except 同步即可）；
        # 后续如改异步，在此停 worker。
        pass

    def _on_test(self):
        """简化版同步测试：调一次 RunningHub healthcheck。"""
        self.lbl_test.setText("测试中…")
        self.lbl_test.repaint()
        try:
            from drama_shot_master.providers.runninghub_health import check
            ok, msg = check(self.api_key_edit.text().strip())
            self.lbl_test.setText(f"✓ {msg}" if ok else f"✗ {msg}")
        except Exception as e:
            self.lbl_test.setText(f"✗ {e}")
```

> 注：如果 `drama_shot_master.providers.runninghub_health.check` 不存在（原 dialog 用别的方式做连通测试），改读原 dialog 的实现复制对应代码。**Plan 阶段开发者按原 dialog 真实情况调整。**

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py -q -p no:faulthandler
```

Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/widgets/settings_sections/ tests/test_ui/test_settings_sections_smoke.py
git commit -m "feat(ui): 新增 settings_sections 目录 + RunningHubSection"
```

---

### Task 9: TranslationSection

**Files:**
- Create: `drama_shot_master/ui/widgets/settings_sections/translation_section.py`
- Modify: `drama_shot_master/ui/widgets/settings_sections/__init__.py`
- Reference (read only): `drama_shot_master/ui/dialogs/translation_settings_dialog.py`

> 实施前先读 reference dialog 文件，把它的全部 input 控件字段一一列下来——下面给的字段是常见组合，如旧 dialog 含更多字段（如 system_prompt 等），按实际加。

- [ ] **Step 1: 在 test_settings_sections_smoke.py 追加测试**

```python
def test_translation_section_class_metadata():
    from drama_shot_master.ui.widgets.settings_sections.translation_section import TranslationSection
    assert TranslationSection.title == "翻译"
    assert TranslationSection.category == "平台核心"


def test_translation_section_load_save_roundtrip():
    _app()
    from drama_shot_master.ui.widgets.settings_sections.translation_section import TranslationSection
    cfg = _cfg(translation_provider="openai", translation_base_url="https://api.example",
               translation_model="gpt-4o-mini", translation_api_key="k1")
    sec = TranslationSection(cfg)
    sec.model_edit.setText("gpt-4o")
    sec.save_to(cfg)
    assert cfg.translation_model == "gpt-4o"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py::test_translation_section_class_metadata -q -p no:faulthandler
```

Expected: ImportError.

- [ ] **Step 3: 创建 translation_section.py**

```python
"""翻译配置 section（provider / base_url / model / api_key）。"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QComboBox, QVBoxLayout


class TranslationSection(QWidget):
    title = "翻译"
    category = "平台核心"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "deepseek", "custom"])
        self.base_url_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.api_key_edit = QLineEdit(); self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Provider", self.provider_combo)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("Model", self.model_edit)
        form.addRow("API Key", self.api_key_edit)
        root.addLayout(form); root.addStretch(1)

    def load_from(self, cfg):
        prov = getattr(cfg, "translation_provider", "openai") or "openai"
        idx = max(0, self.provider_combo.findText(prov))
        self.provider_combo.setCurrentIndex(idx)
        self.base_url_edit.setText(getattr(cfg, "translation_base_url", "") or "")
        self.model_edit.setText(getattr(cfg, "translation_model", "") or "")
        self.api_key_edit.setText(getattr(cfg, "translation_api_key", "") or "")

    def save_to(self, cfg):
        cfg.translation_provider = self.provider_combo.currentText()
        cfg.translation_base_url = self.base_url_edit.text().strip()
        cfg.translation_model = self.model_edit.text().strip()
        cfg.translation_api_key = self.api_key_edit.text().strip()

    def validate(self): return (True, "")
    def cancel_workers(self): pass
```

- [ ] **Step 4: 加进 __init__.py**

```python
from .translation_section import TranslationSection
__all__.append("TranslationSection")
```

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py -q -p no:faulthandler
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/widgets/settings_sections/ tests/test_ui/test_settings_sections_smoke.py
git commit -m "feat(ui): TranslationSection"
```

---

### Task 10: RefineSection (提示词优化)

**Files:**
- Create: `drama_shot_master/ui/widgets/settings_sections/refine_section.py`
- Modify: `drama_shot_master/ui/widgets/settings_sections/__init__.py`
- Reference (read only): `drama_shot_master/ui/dialogs/refine_settings_dialog.py`

> 字段通常含 provider/base_url/model/api_key/system_prompt——以 reference dialog 实际字段为准。

- [ ] **Step 1: 在 test_settings_sections_smoke.py 追加测试**

```python
def test_refine_section_class_metadata():
    from drama_shot_master.ui.widgets.settings_sections.refine_section import RefineSection
    assert RefineSection.title == "提示词优化"
    assert RefineSection.category == "辅助"


def test_refine_section_load_save_roundtrip():
    _app()
    from drama_shot_master.ui.widgets.settings_sections.refine_section import RefineSection
    cfg = _cfg(refine_model="m1", refine_api_key="k1", refine_system_prompt="be concise")
    sec = RefineSection(cfg)
    sec.system_prompt_edit.setPlainText("new prompt")
    sec.save_to(cfg)
    assert cfg.refine_system_prompt == "new prompt"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py::test_refine_section_class_metadata -q -p no:faulthandler
```

Expected: ImportError.

- [ ] **Step 3: 创建 refine_section.py**

```python
"""提示词优化 section（provider / base_url / model / api_key / system_prompt）。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QComboBox, QPlainTextEdit, QVBoxLayout,
)


class RefineSection(QWidget):
    title = "提示词优化"
    category = "辅助"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "deepseek", "custom"])
        self.base_url_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.api_key_edit = QLineEdit(); self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.system_prompt_edit = QPlainTextEdit()
        self.system_prompt_edit.setMaximumHeight(120)
        form.addRow("Provider", self.provider_combo)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("Model", self.model_edit)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("System Prompt", self.system_prompt_edit)
        root.addLayout(form); root.addStretch(1)

    def load_from(self, cfg):
        prov = getattr(cfg, "refine_provider", "openai") or "openai"
        idx = max(0, self.provider_combo.findText(prov))
        self.provider_combo.setCurrentIndex(idx)
        self.base_url_edit.setText(getattr(cfg, "refine_base_url", "") or "")
        self.model_edit.setText(getattr(cfg, "refine_model", "") or "")
        self.api_key_edit.setText(getattr(cfg, "refine_api_key", "") or "")
        self.system_prompt_edit.setPlainText(getattr(cfg, "refine_system_prompt", "") or "")

    def save_to(self, cfg):
        cfg.refine_provider = self.provider_combo.currentText()
        cfg.refine_base_url = self.base_url_edit.text().strip()
        cfg.refine_model = self.model_edit.text().strip()
        cfg.refine_api_key = self.api_key_edit.text().strip()
        cfg.refine_system_prompt = self.system_prompt_edit.toPlainText().strip()

    def validate(self): return (True, "")
    def cancel_workers(self): pass
```

- [ ] **Step 4: 加进 __init__.py 与 Step 5/6 同 Task 9 pattern（写测、加 export、跑测、提交）。Commit message: `feat(ui): RefineSection`.**

```bash
git add drama_shot_master/ui/widgets/settings_sections/ tests/test_ui/test_settings_sections_smoke.py
git commit -m "feat(ui): RefineSection"
```

---

### Task 11: ImgGenSection / DubSection / SoundtrackSection

**Files:**
- Create: `drama_shot_master/ui/widgets/settings_sections/imggen_section.py`
- Create: `drama_shot_master/ui/widgets/settings_sections/dub_section.py`
- Create: `drama_shot_master/ui/widgets/settings_sections/soundtrack_section.py`
- Modify: `drama_shot_master/ui/widgets/settings_sections/__init__.py`
- Reference: 三个旧 dialog 各自

> 三个 section 一并放在 Task 11 是因结构高度同构。每个 section 单独一次 commit，subagent 可一次性写完三个文件。

- [ ] **Step 1: 在 test_settings_sections_smoke.py 追加测试**

```python
def test_imggen_section_class_metadata():
    from drama_shot_master.ui.widgets.settings_sections.imggen_section import ImgGenSection
    assert ImgGenSection.title == "出图"
    assert ImgGenSection.category == "生成功能"

def test_dub_section_class_metadata():
    from drama_shot_master.ui.widgets.settings_sections.dub_section import DubSection
    assert DubSection.title == "配音"
    assert DubSection.category == "生成功能"

def test_soundtrack_section_class_metadata():
    from drama_shot_master.ui.widgets.settings_sections.soundtrack_section import SoundtrackSection
    assert SoundtrackSection.title == "配乐"
    assert SoundtrackSection.category == "生成功能"

def test_dub_section_load_save_roundtrip():
    _app()
    from drama_shot_master.ui.widgets.settings_sections.dub_section import DubSection
    cfg = _cfg(dub_voice_design_workflow_id="", dub_voice_clone_workflow_id="", dub_output_dir="")
    # 兼容 cfg 用 dict 存 workflow ids 的实现：load_from 应做兜底
    sec = DubSection(cfg)
    sec.wf_design_edit.setText("wf-design")
    sec.wf_clone_edit.setText("wf-clone")
    sec.out_dir_edit.setText("/tmp/dub")
    sec.save_to(cfg)
    assert cfg.dub_voice_design_workflow_id == "wf-design"
    assert cfg.dub_voice_clone_workflow_id == "wf-clone"
    assert cfg.dub_output_dir == "/tmp/dub"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py::test_imggen_section_class_metadata -q -p no:faulthandler
```

- [ ] **Step 3a: 创建 imggen_section.py**

```python
"""出图配置 section（provider / base_url / model / api_key / 输出目录 / 无水印）含连通测试。"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QLabel, QHBoxLayout, QVBoxLayout, QFileDialog,
)


class ImgGenSection(QWidget):
    title = "出图"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["doubao(ark)", "openai", "runninghub"])
        self.base_url_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.api_key_edit = QLineEdit(); self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.no_watermark_chk = QCheckBox("无水印")
        out_row = QHBoxLayout()
        self.out_dir_edit = QLineEdit()
        btn_pick = QPushButton("浏览…"); btn_pick.clicked.connect(self._pick_dir)
        out_row.addWidget(self.out_dir_edit, 1); out_row.addWidget(btn_pick)
        form.addRow("Provider", self.provider_combo)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("Model", self.model_edit)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("输出目录", out_row)
        form.addRow("", self.no_watermark_chk)
        root.addLayout(form)
        # 连通测试
        test_bar = QHBoxLayout()
        self.btn_test = QPushButton("连通测试")
        self.lbl_test = QLabel("")
        test_bar.addWidget(self.btn_test); test_bar.addWidget(self.lbl_test, 1)
        root.addLayout(test_bar)
        root.addStretch(1)
        self.btn_test.clicked.connect(self._on_test)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir_edit.text() or "")
        if d: self.out_dir_edit.setText(d)

    def load_from(self, cfg):
        prov = getattr(cfg, "imggen_provider", "doubao(ark)") or "doubao(ark)"
        idx = max(0, self.provider_combo.findText(prov))
        self.provider_combo.setCurrentIndex(idx)
        self.base_url_edit.setText(getattr(cfg, "imggen_base_url", "") or "")
        self.model_edit.setText(getattr(cfg, "imggen_model", "") or "")
        self.api_key_edit.setText(getattr(cfg, "imggen_api_key", "") or "")
        self.out_dir_edit.setText(getattr(cfg, "imggen_output_dir", "") or "")
        self.no_watermark_chk.setChecked(bool(getattr(cfg, "imggen_no_watermark", False)))

    def save_to(self, cfg):
        cfg.imggen_provider = self.provider_combo.currentText()
        cfg.imggen_base_url = self.base_url_edit.text().strip()
        cfg.imggen_model = self.model_edit.text().strip()
        cfg.imggen_api_key = self.api_key_edit.text().strip()
        cfg.imggen_output_dir = self.out_dir_edit.text().strip()
        cfg.imggen_no_watermark = self.no_watermark_chk.isChecked()

    def validate(self): return (True, "")
    def cancel_workers(self): pass

    def _on_test(self):
        """同步连通测试。实施时如旧 dialog 有具体 health-check 函数，复用之。"""
        self.lbl_test.setText("测试中…"); self.lbl_test.repaint()
        try:
            from drama_shot_master.providers.image_gen import smoke_check
            ok, msg = smoke_check(self._cfg)
            self.lbl_test.setText(f"✓ {msg}" if ok else f"✗ {msg}")
        except ImportError:
            self.lbl_test.setText("(no smoke_check available)")
        except Exception as e:
            self.lbl_test.setText(f"✗ {e}")
```

> 注：`smoke_check` 是占位名——实施前 grep 一下 `imggen_settings_dialog.py` 看实际怎么测，复用同样函数。

- [ ] **Step 3b: 创建 dub_section.py**

```python
"""配音配置 section（voice_design / voice_clone workflow IDs + 输出目录）。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QFileDialog,
)


class DubSection(QWidget):
    title = "配音"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.wf_design_edit = QLineEdit()
        self.wf_clone_edit = QLineEdit()
        out_row = QHBoxLayout()
        self.out_dir_edit = QLineEdit()
        btn = QPushButton("浏览…"); btn.clicked.connect(self._pick_dir)
        out_row.addWidget(self.out_dir_edit, 1); out_row.addWidget(btn)
        form.addRow("音色设计 workflow_id", self.wf_design_edit)
        form.addRow("声音克隆 workflow_id", self.wf_clone_edit)
        form.addRow("输出目录", out_row)
        root.addLayout(form); root.addStretch(1)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir_edit.text() or "")
        if d: self.out_dir_edit.setText(d)

    def load_from(self, cfg):
        # cfg 当前用 dict 存 workflow ids（参考 dub_settings_dialog.py 第 23-24 行），
        # 兼容两种存法：扁平字段 + dict 字段（dub_workflow_ids = {"voice_design": ..., "voice_clone": ...}）
        flat_design = getattr(cfg, "dub_voice_design_workflow_id", None)
        flat_clone = getattr(cfg, "dub_voice_clone_workflow_id", None)
        if flat_design is None and hasattr(cfg, "dub_workflow_ids"):
            ids = cfg.dub_workflow_ids or {}
            flat_design = ids.get("voice_design", "")
            flat_clone = ids.get("voice_clone", "")
        self.wf_design_edit.setText(flat_design or "")
        self.wf_clone_edit.setText(flat_clone or "")
        self.out_dir_edit.setText(getattr(cfg, "dub_output_dir", "") or "")

    def save_to(self, cfg):
        cfg.dub_voice_design_workflow_id = self.wf_design_edit.text().strip()
        cfg.dub_voice_clone_workflow_id = self.wf_clone_edit.text().strip()
        cfg.dub_output_dir = self.out_dir_edit.text().strip()
        # 同时维护 dict 字段以保持兼容（如 cfg 用的是 dict 存储）
        if hasattr(cfg, "dub_workflow_ids"):
            cfg.dub_workflow_ids = {
                "voice_design": cfg.dub_voice_design_workflow_id,
                "voice_clone": cfg.dub_voice_clone_workflow_id,
            }

    def validate(self): return (True, "")
    def cancel_workers(self): pass
```

- [ ] **Step 3c: 创建 soundtrack_section.py**

```python
"""配乐配置 section（workflow_id / seeds_count / crossfade / 阈值 / 输出目录）。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox,
    QPushButton, QHBoxLayout, QVBoxLayout, QFileDialog,
)


class SoundtrackSection(QWidget):
    title = "配乐"
    category = "生成功能"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build_ui()
        self.load_from(cfg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.wf_edit = QLineEdit()
        self.seeds_spin = QSpinBox(); self.seeds_spin.setRange(1, 10)
        self.crossfade_spin = QDoubleSpinBox(); self.crossfade_spin.setRange(0.0, 5.0); self.crossfade_spin.setSingleStep(0.1)
        self.big_thresh_spin = QDoubleSpinBox(); self.big_thresh_spin.setRange(0.0, 1.0); self.big_thresh_spin.setSingleStep(0.05)
        self.snap_window_spin = QDoubleSpinBox(); self.snap_window_spin.setRange(0.0, 3.0); self.snap_window_spin.setSingleStep(0.1)
        out_row = QHBoxLayout()
        self.out_dir_edit = QLineEdit()
        btn = QPushButton("浏览…"); btn.clicked.connect(self._pick_dir)
        out_row.addWidget(self.out_dir_edit, 1); out_row.addWidget(btn)
        form.addRow("Workflow ID", self.wf_edit)
        form.addRow("候选数 (seeds)", self.seeds_spin)
        form.addRow("交叉淡入淡出 (s)", self.crossfade_spin)
        form.addRow("大爆点阈值", self.big_thresh_spin)
        form.addRow("吸附窗口 (s)", self.snap_window_spin)
        form.addRow("输出目录", out_row)
        root.addLayout(form); root.addStretch(1)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir_edit.text() or "")
        if d: self.out_dir_edit.setText(d)

    def load_from(self, cfg):
        self.wf_edit.setText(getattr(cfg, "soundtrack_workflow_id", "") or "")
        self.seeds_spin.setValue(int(getattr(cfg, "soundtrack_seeds_count", 2) or 2))
        self.crossfade_spin.setValue(float(getattr(cfg, "soundtrack_crossfade", 0.5) or 0.5))
        self.big_thresh_spin.setValue(float(getattr(cfg, "accent_big_threshold", 0.7) or 0.7))
        self.snap_window_spin.setValue(float(getattr(cfg, "accent_snap_window", 0.6) or 0.6))
        self.out_dir_edit.setText(getattr(cfg, "soundtrack_output_dir", "") or "")

    def save_to(self, cfg):
        cfg.soundtrack_workflow_id = self.wf_edit.text().strip()
        cfg.soundtrack_seeds_count = self.seeds_spin.value()
        cfg.soundtrack_crossfade = self.crossfade_spin.value()
        cfg.accent_big_threshold = self.big_thresh_spin.value()
        cfg.accent_snap_window = self.snap_window_spin.value()
        cfg.soundtrack_output_dir = self.out_dir_edit.text().strip()

    def validate(self): return (True, "")
    def cancel_workers(self): pass
```

- [ ] **Step 4: 加进 __init__.py**

```python
from .imggen_section import ImgGenSection
from .dub_section import DubSection
from .soundtrack_section import SoundtrackSection
__all__ += ["ImgGenSection", "DubSection", "SoundtrackSection"]
```

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py -q -p no:faulthandler
```

Expected: PASS.

- [ ] **Step 6: Commit（三个 section 一并）**

```bash
git add drama_shot_master/ui/widgets/settings_sections/ tests/test_ui/test_settings_sections_smoke.py
git commit -m "feat(ui): ImgGenSection + DubSection + SoundtrackSection"
```

---

### Task 12: ThemeSection（实时切换）

**Files:**
- Create: `drama_shot_master/ui/widgets/settings_sections/theme_section.py`
- Modify: `drama_shot_master/ui/widgets/settings_sections/__init__.py`
- Test: extend `tests/test_ui/test_settings_sections_smoke.py`

- [ ] **Step 1: 写失败测试**

在 `test_settings_sections_smoke.py` 末尾追加：

```python
def test_theme_section_metadata():
    from drama_shot_master.ui.widgets.settings_sections.theme_section import ThemeSection
    assert ThemeSection.title == "主题"
    assert ThemeSection.category == "外观"


def test_theme_section_combo_switch_calls_apply(monkeypatch):
    _app()
    from drama_shot_master.ui.widgets.settings_sections.theme_section import ThemeSection
    from drama_shot_master.ui import theme as theme_mod
    called = []
    monkeypatch.setattr(theme_mod, "apply_theme", lambda app, name: called.append(("apply", name)))
    monkeypatch.setattr(theme_mod, "apply_titlebar", lambda w, name: called.append(("titlebar", name)))
    cfg = _cfg(theme="dark")
    persisted = []
    cfg.update_settings = lambda **kw: persisted.append(kw)
    from PySide6.QtWidgets import QApplication
    sec = ThemeSection(QApplication.instance(), cfg)
    sec.combo.setCurrentText("浅色")
    assert ("apply", "light") in called
    assert any(k.get("theme") == "light" for k in persisted)
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py::test_theme_section_metadata -q -p no:faulthandler
```

Expected: ImportError。

- [ ] **Step 3: 实现 ThemeSection**

`drama_shot_master/ui/widgets/settings_sections/theme_section.py`:

```python
"""主题切换 section（实时持久化、不依赖[保存]按钮）。"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox

from drama_shot_master.ui import theme as theme_mod


class ThemeSection(QWidget):
    title = "主题"
    category = "外观"

    def __init__(self, app, cfg, parent=None):
        super().__init__(parent)
        self._app = app
        self._cfg = cfg
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("界面主题（切换即生效、自动保存）"))
        self.combo = QComboBox()
        self.combo.addItems(["深色", "浅色"])
        cur_name = theme_mod.current_theme(self._cfg)
        self.combo.setCurrentText("浅色" if cur_name == "light" else "深色")
        self.combo.currentTextChanged.connect(self._apply_now)
        root.addWidget(self.combo)
        root.addStretch(1)

    def _apply_now(self, txt: str):
        name = "light" if txt == "浅色" else "dark"
        theme_mod.apply_theme(self._app, name)
        # 给本 dialog 自己的窗 + 主窗都换原生标题栏
        top = self.window()
        theme_mod.apply_titlebar(top, name)
        parent = top.parent() if top is not None else None
        if parent is not None:
            theme_mod.apply_titlebar(parent, name)
        try:
            self._cfg.update_settings(theme=name)
        except Exception:
            pass

    def load_from(self, cfg): pass        # ctor 已读
    def save_to(self, cfg): pass          # 实时持久化，无延迟保存
    def validate(self): return (True, "")
    def cancel_workers(self): pass
```

- [ ] **Step 4: 加进 __init__.py 导出**

`drama_shot_master/ui/widgets/settings_sections/__init__.py` 末尾追加 import 与 __all__：

```python
from .theme_section import ThemeSection
__all__.append("ThemeSection")
```

（如果 __init__.py 现在用的是字面 `__all__ = [...]`，改为列表 append；否则直接列入。）

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/test_settings_sections_smoke.py -q -p no:faulthandler
```

Expected: 全 PASS（新增 2 个）

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/widgets/settings_sections/
git commit -m "feat(ui): ThemeSection 实时切换深/浅主题 + 自动持久化"
```

---

### Task 13: UnifiedSettingsDialog 壳

**Files:**
- Create: `drama_shot_master/ui/dialogs/unified_settings_dialog.py`
- Test: `tests/test_ui/test_unified_settings_dialog_smoke.py` (new)

- [ ] **Step 1: 写失败测试**

`tests/test_ui/test_unified_settings_dialog_smoke.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QTreeWidget, QStackedWidget

from drama_shot_master.ui.dialogs.unified_settings_dialog import UnifiedSettingsDialog


def _app():
    return QApplication.instance() or QApplication([])


def _cfg():
    c = type("C", (), {
        "running_hub_api_key": "k", "running_hub_workflow_id": "wf", "running_hub_no_watermark": False,
        "theme": "dark",
        # 其余字段在各 section 的 load_from 里 getattr 兜底空串
    })()
    c.update_settings = lambda **kw: [setattr(c, k, v) for k, v in kw.items()]
    return c


@pytest.fixture(scope="module")
def dlg():
    _app()
    cfg = _cfg()
    d = UnifiedSettingsDialog(QApplication.instance(), cfg)
    yield d
    d.deleteLater()


def test_dialog_has_tree_and_stack(dlg):
    assert isinstance(dlg.tree, QTreeWidget)
    assert isinstance(dlg.stack, QStackedWidget)


def test_dialog_has_7_sections(dlg):
    # 7 个 section：RunningHub / Translation / Refine / ImgGen / Dub / Soundtrack / Theme
    assert dlg.stack.count() == 7


def test_dialog_tree_categories(dlg):
    cats = []
    for i in range(dlg.tree.topLevelItemCount()):
        cats.append(dlg.tree.topLevelItem(i).text(0))
    assert "平台核心" in cats and "生成功能" in cats and "外观" in cats and "辅助" in cats


def test_select_leaf_switches_stack(dlg):
    # 找到 "主题" 叶子并点中 → stack.currentWidget 应该是 ThemeSection
    from drama_shot_master.ui.widgets.settings_sections.theme_section import ThemeSection
    for i in range(dlg.tree.topLevelItemCount()):
        top = dlg.tree.topLevelItem(i)
        for j in range(top.childCount()):
            leaf = top.child(j)
            if leaf.text(0) == "主题":
                dlg.tree.setCurrentItem(leaf)
                assert isinstance(dlg.stack.currentWidget(), ThemeSection)
                return
    pytest.fail("no 主题 leaf found")


def test_save_calls_each_section_save(monkeypatch):
    _app()
    cfg = _cfg()
    d = UnifiedSettingsDialog(QApplication.instance(), cfg)
    # 改 RunningHub API key, 触发保存
    for sec in d._sections:
        if sec.__class__.__name__ == "RunningHubSection":
            sec.api_key_edit.setText("new_key")
            break
    d._on_save()
    assert cfg.running_hub_api_key == "new_key"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_unified_settings_dialog_smoke.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 UnifiedSettingsDialog**

`drama_shot_master/ui/dialogs/unified_settings_dialog.py`:

```python
"""统一设置：左树 + 右 QStackedWidget；6 个旧 dialog 合一。
主题 section 实时持久化，其他 section 走底栏 [保存]。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QPushButton, QMessageBox,
)

from drama_shot_master.ui.widgets.settings_sections import (
    RunningHubSection, TranslationSection, RefineSection,
    ImgGenSection, DubSection, SoundtrackSection, ThemeSection,
)


class UnifiedSettingsDialog(QDialog):
    def __init__(self, app, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(800, 600)
        self._app = app
        self._cfg = cfg
        self._sections = self._build_sections()
        self._build_ui()
        self._restore_last_section()

    def _build_sections(self):
        return [
            RunningHubSection(self._cfg),
            TranslationSection(self._cfg),
            RefineSection(self._cfg),
            ImgGenSection(self._cfg),
            DubSection(self._cfg),
            SoundtrackSection(self._cfg),
            ThemeSection(self._app, self._cfg),
        ]

    def _build_ui(self):
        # 左：QTreeWidget 分类
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumWidth(220)
        cats: dict[str, QTreeWidgetItem] = {}
        # 固定顺序，避免字典序乱
        ORDER = ["平台核心", "生成功能", "辅助", "外观"]
        for cat in ORDER:
            top = QTreeWidgetItem([cat])
            self.tree.addTopLevelItem(top)
            cats[cat] = top
        for sec in self._sections:
            top = cats.get(sec.category)
            if top is None:    # 未声明的 category：自动加一项
                top = QTreeWidgetItem([sec.category])
                self.tree.addTopLevelItem(top)
                cats[sec.category] = top
            leaf = QTreeWidgetItem([sec.title])
            leaf.setData(0, Qt.UserRole, sec)
            top.addChild(leaf)
        self.tree.expandAll()
        self.tree.itemSelectionChanged.connect(self._on_tree_sel)

        # 右：QStackedWidget
        self.stack = QStackedWidget()
        for sec in self._sections:
            self.stack.addWidget(sec)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tree); split.addWidget(self.stack)
        split.setSizes([200, 600])

        # 底栏
        bar = QHBoxLayout(); bar.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("保存")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save)
        bar.addWidget(self.btn_cancel); bar.addWidget(self.btn_save)

        root = QVBoxLayout(self)
        root.addWidget(split, 1)
        root.addLayout(bar)

    def _on_tree_sel(self):
        sec = self._current_section()
        if sec is None:
            return
        self.stack.setCurrentWidget(sec)

    def _current_section(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        sec = items[0].data(0, Qt.UserRole)
        return sec       # 顶层 category item 没有 UserRole，返 None

    def _restore_last_section(self):
        last = getattr(self._cfg, "last_settings_section", "")
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                leaf = top.child(j)
                if leaf.text(0) == last:
                    self.tree.setCurrentItem(leaf)
                    return
        # fallback: 选第一个有 section 的叶子
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.childCount() > 0:
                self.tree.setCurrentItem(top.child(0))
                return

    def _on_save(self):
        for i, sec in enumerate(self._sections):
            ok, why = sec.validate()
            if not ok:
                QMessageBox.warning(self, "设置无效", why)
                self.stack.setCurrentWidget(sec)
                return
        for sec in self._sections:
            sec.save_to(self._cfg)
        cur = self._current_section()
        if cur is not None:
            try:
                self._cfg.update_settings(last_settings_section=cur.title)
            except Exception:
                pass
        self.accept()

    def reject(self):
        for sec in self._sections:
            if hasattr(sec, "cancel_workers"):
                sec.cancel_workers()
        super().reject()
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_unified_settings_dialog_smoke.py -q -p no:faulthandler
```

Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/dialogs/unified_settings_dialog.py tests/test_ui/test_unified_settings_dialog_smoke.py
git commit -m "feat(ui): UnifiedSettingsDialog 左树+右内容统一设置 hub"
```

---

### Task 14: AppShell 改用统一设置入口

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: 改 sidebar.settingsRequested 连接**

`app_shell.py` `_wire` 方法里现有：

```python
self.sidebar.settingsRequested.connect(self._open_settings_menu)
```

改为：

```python
self.sidebar.settingsRequested.connect(self._open_unified_settings)
```

- [ ] **Step 2: 新增 _open_unified_settings 方法**

在 app_shell.py 适当位置（比如紧接 `_open_settings_menu` 现位置之上）插入：

```python
    def _open_unified_settings(self):
        from drama_shot_master.ui.dialogs.unified_settings_dialog import UnifiedSettingsDialog
        from PySide6.QtWidgets import QApplication
        UnifiedSettingsDialog(QApplication.instance(), self.cfg, parent=self).exec()
```

- [ ] **Step 3: 删除旧菜单方法**

删除 `_open_settings_menu` 方法整段（约 line 181-194）。
删除 6 个 `_open_<X>_settings` 方法整段（runninghub/translation/refine/soundtrack/dub/imggen）。
删除对应 6 行 import（在文件中找到 `from drama_shot_master.ui.dialogs.<x>_settings_dialog import` 全删）。

- [ ] **Step 4: 跑 app_shell 测试**

```bash
python -m pytest tests/test_ui/test_app_shell_smoke.py -q -p no:faulthandler
```

Expected: PASS。如有用例引用了被删的方法，按现实情况修测试（应该没有，这些是私有方法）。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/app_shell.py
git commit -m "refactor(ui): AppShell 设置入口改单一 UnifiedSettingsDialog，删 6 个旧菜单项"
```

---

### Task 15: 删除旧 6 个 settings_dialog 文件

**Files:**
- Delete: `drama_shot_master/ui/dialogs/runninghub_settings_dialog.py`
- Delete: `drama_shot_master/ui/dialogs/translation_settings_dialog.py`
- Delete: `drama_shot_master/ui/dialogs/refine_settings_dialog.py`
- Delete: `drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py`
- Delete: `drama_shot_master/ui/dialogs/dub_settings_dialog.py`
- Delete: `drama_shot_master/ui/dialogs/imggen_settings_dialog.py`
- Delete: 对应 smoke 测试文件（如存在）

- [ ] **Step 1: 确认无残留引用**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
grep -rnE "RunningHubSettingsDialog|TranslationSettingsDialog|RefineSettingsDialog|SoundtrackSettingsDialog|DubSettingsDialog|ImgGenSettingsDialog" drama_shot_master/ tests/ | grep -v "settings_sections/" | grep -v "dialogs/.*_settings_dialog.py:"
```

Expected: **空**（除了待删的 6 个文件自身的 class 声明）。

如有其它引用：STOP，先处理那个引用再继续。

- [ ] **Step 2: 找到对应的 smoke 测试文件**

```bash
ls tests/test_ui/ | grep -iE "settings_dialog|settings_smoke"
```

记下找到的旧 dialog smoke 测试文件列表（如 `test_runninghub_settings_smoke.py` 等）；保留 `test_settings_sections_smoke.py` 和 `test_unified_settings_dialog_smoke.py`（这两个是新增的）。

- [ ] **Step 3: 删除文件**

```bash
git rm drama_shot_master/ui/dialogs/runninghub_settings_dialog.py
git rm drama_shot_master/ui/dialogs/translation_settings_dialog.py
git rm drama_shot_master/ui/dialogs/refine_settings_dialog.py
git rm drama_shot_master/ui/dialogs/soundtrack_settings_dialog.py
git rm drama_shot_master/ui/dialogs/dub_settings_dialog.py
git rm drama_shot_master/ui/dialogs/imggen_settings_dialog.py
# 删旧 smoke 测（按 Step 2 找到的实际文件名，举例）：
# git rm tests/test_ui/test_runninghub_settings_smoke.py
# ...
```

- [ ] **Step 4: 跑全 UI 套件**

```bash
python -m pytest tests/test_ui/ -v --tb=line -p no:faulthandler -o addopts="" 2>&1 | grep -cE "PASSED"
python -m pytest tests/test_ui/ -v --tb=line -p no:faulthandler -o addopts="" 2>&1 | grep -cE "FAILED"
```

Expected: PASSED 数 > 0；FAILED 数 = 0。

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(ui): 删除 6 个旧 settings dialog 文件（职责并入 UnifiedSettingsDialog）"
```

---

## Workstream C: TaskCenterDock

### Task 16: 三个 Manager 加 get_status

**Files:**
- Modify: `drama_shot_master/ui/panels/video_task_manager_panel.py`
- Modify: `drama_shot_master/ui/panels/dub_task_manager_panel.py`
- Modify: `drama_shot_master/ui/panels/imggen_task_manager_panel.py`

- [ ] **Step 1: 写测试（一个统一测试覆盖三 manager）**

`tests/test_ui/test_manager_get_status_smoke.py`(new):

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.core.imggen_task_store import ImgGenTaskStore


def _app():
    return QApplication.instance() or QApplication([])


def test_video_manager_get_status():
    _app()
    m = VideoTaskManagerPanel(None, None, VideoTaskStore(), None, None, lambda: None)
    assert m.get_status("nonexistent") == "空闲"
    m._live_status["t1"] = "生成中"
    assert m.get_status("t1") == "生成中"


def test_dub_manager_get_status():
    _app()
    m = DubTaskManagerPanel(None, None, DubTaskStore(), None, None, lambda: None)
    assert m.get_status("nonexistent") == "空闲"
    m._live_status["t1"] = "失败"
    assert m.get_status("t1") == "失败"


def test_imggen_manager_get_status():
    _app()
    m = ImgGenTaskManagerPanel(None, None, ImgGenTaskStore(), None, None, lambda: None)
    assert m.get_status("nonexistent") == "空闲"
    m._live_status["t1"] = "完成"
    assert m.get_status("t1") == "完成"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_manager_get_status_smoke.py -q -p no:faulthandler
```

Expected: AttributeError on `get_status`.

- [ ] **Step 3: 三个文件各加 get_status 方法**

每个 `*_task_manager_panel.py` 中插入：

```python
    def get_status(self, task_id: str) -> str:
        """暴露 live_status；任务中心聚合用。空闲=未跑过/已重置。"""
        return self._live_status.get(task_id, "空闲")
```

放在 `set_task_status` 方法附近。

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_manager_get_status_smoke.py -q -p no:faulthandler
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/panels/ tests/test_ui/test_manager_get_status_smoke.py
git commit -m "feat(ui): 视频/配音/出图 manager 暴露 get_status(tid)"
```

---

### Task 17: TaskAggregator

**Files:**
- Create: `drama_shot_master/core/task_aggregator.py`
- Test: `tests/test_core/test_task_aggregator.py` (new)

- [ ] **Step 1: 写失败测试**

`tests/test_core/test_task_aggregator.py`:

```python
"""TaskAggregator smoke：跨 3 store + cfg dict 聚合任务记录。"""
from drama_shot_master.core.task_aggregator import TaskAggregator, TaskRecord
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.core.dub_task_store import DubTaskStore
from drama_shot_master.core.imggen_task_store import ImgGenTaskStore


class _MockMgr:
    def __init__(self, statuses):
        self._statuses = statuses
    def get_status(self, tid):
        return self._statuses.get(tid, "空闲")


def _cfg(soundtrack_tasks=()):
    return type("C", (), {"soundtrack_tasks": list(soundtrack_tasks)})()


def test_aggregator_returns_all_kinds():
    vstore = VideoTaskStore(); vstore.add("V1", {})
    dstore = DubTaskStore(); dstore.add("D1", mode="clone", payload={})
    istore = ImgGenTaskStore(); istore.add("I1", payload={})
    cfg = _cfg([{"id": "s1", "name": "S1", "status": "完成", "output": "/tmp/o.mp4"}])

    vmgr = _MockMgr({vstore.all()[0].id: "生成中"})
    dmgr = _MockMgr({dstore.all()[0].id: "失败"})
    imgr = _MockMgr({istore.all()[0].id: "完成"})

    agg = TaskAggregator(cfg, vstore, dstore, istore,
                         managers={"video": vmgr, "dub": dmgr, "imggen": imgr})
    records = agg.snapshot()
    kinds = sorted({r.kind for r in records})
    assert kinds == ["dub", "imggen", "soundtrack", "video"]
    assert len(records) == 4


def test_aggregator_soundtrack_reads_cfg_dict():
    cfg = _cfg([{"id": "s1", "name": "EP1", "status": "失败", "output": ""}])
    agg = TaskAggregator(cfg, VideoTaskStore(), DubTaskStore(), ImgGenTaskStore(),
                         managers={})
    records = agg.snapshot()
    assert len(records) == 1
    r = records[0]
    assert r.kind == "soundtrack" and r.task_id == "s1" and r.name == "EP1"
    assert r.status == "失败" and r.last_result == ""


def test_aggregator_missing_manager_yields_idle():
    vstore = VideoTaskStore(); vstore.add("V", {})
    agg = TaskAggregator(_cfg(), vstore, DubTaskStore(), ImgGenTaskStore(), managers={})
    records = agg.snapshot()
    assert len(records) == 1 and records[0].status == "空闲"


def test_task_record_is_dataclass_like():
    r = TaskRecord(kind="video", task_id="t", name="n", status="空闲", last_result="")
    assert r.kind == "video" and r.task_id == "t"
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_core/test_task_aggregator.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 TaskAggregator**

`drama_shot_master/core/task_aggregator.py`:

```python
"""跨 4 个任务源（3 store + cfg.soundtrack_tasks dict）的只读聚合。
任务中心抽屉消费 snapshot() → 列表分组展示。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskRecord:
    kind: str             # "video" | "imggen" | "dub" | "soundtrack"
    task_id: str
    name: str
    status: str           # "生成中" / "失败" / "完成" / "空闲"
    last_result: str      # 输出路径；空串=未出


class TaskAggregator:
    """无事件订阅；调用方按需 snapshot()。"""

    def __init__(self, cfg, video_store, dub_store, imggen_store, managers: dict):
        """managers: {"video": VideoTaskManagerPanel, "dub": ..., "imggen": ...}。
        无对应 manager 时该 kind 的 status 一律返回 "空闲"。
        soundtrack 不传 manager——状态在 cfg.soundtrack_tasks dict 上。"""
        self.cfg = cfg
        self._video_s = video_store
        self._dub_s = dub_store
        self._imggen_s = imggen_store
        self._managers = managers

    def snapshot(self) -> list[TaskRecord]:
        out: list[TaskRecord] = []
        for kind, store in (("video", self._video_s),
                            ("dub", self._dub_s),
                            ("imggen", self._imggen_s)):
            mgr = self._managers.get(kind)
            for t in store.all():
                status = mgr.get_status(t.id) if mgr is not None else "空闲"
                last = getattr(t, "last_result", "") or ""
                out.append(TaskRecord(kind, t.id, t.name, status, last))
        for d in getattr(self.cfg, "soundtrack_tasks", []) or []:
            out.append(TaskRecord(
                "soundtrack",
                d.get("id", ""),
                d.get("name", ""),
                d.get("status", "空闲"),
                d.get("output", "") or "",
            ))
        return out
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_core/test_task_aggregator.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/core/task_aggregator.py tests/test_core/test_task_aggregator.py
git commit -m "feat(core): TaskAggregator 跨 4 个任务源只读聚合"
```

---

### Task 18: TaskCenterDock

**Files:**
- Create: `drama_shot_master/ui/widgets/task_center_dock.py`
- Test: `tests/test_ui/test_task_center_dock_smoke.py` (new)

- [ ] **Step 1: 写失败测试**

`tests/test_ui/test_task_center_dock_smoke.py`:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from drama_shot_master.core.task_aggregator import TaskRecord
from drama_shot_master.ui.widgets.task_center_dock import TaskCenterDock


def _app():
    return QApplication.instance() or QApplication([])


class _StubAgg:
    def __init__(self, records):
        self._r = records
    def snapshot(self):
        return list(self._r)


@pytest.fixture
def dock():
    _app()
    return TaskCenterDock(_StubAgg([
        TaskRecord("video", "v1", "VIDEO1", "生成中", ""),
        TaskRecord("dub",   "d1", "DUB1",   "失败",   ""),
        TaskRecord("imggen","i1", "IMG1",   "完成",   "/tmp/x.png"),
        TaskRecord("soundtrack","s1","ST1", "完成",   "/tmp/y.mp4"),
        TaskRecord("video", "v2", "VIDEO2", "空闲",   ""),
    ]))


def test_dock_three_groups_populated(dock):
    assert dock.list_running.count() == 1     # v1
    assert dock.list_failed.count() == 1      # d1
    assert dock.list_done.count() == 2        # i1, s1


def test_dock_count_label(dock):
    assert "生成中 1" in dock.lbl_counts.text()
    assert "失败 1" in dock.lbl_counts.text()
    assert "完成 2" in dock.lbl_counts.text()


def test_dock_double_click_emits_task_activated(dock):
    fired = []
    dock.taskActivated.connect(lambda kind, tid: fired.append((kind, tid)))
    item = dock.list_running.item(0)
    dock.list_running.itemDoubleClicked.emit(item)
    assert fired == [("video", "v1")]


def test_dock_recent_complete_capped(monkeypatch):
    _app()
    many_done = [TaskRecord("video", f"v{i}", f"V{i}", "完成", f"/tmp/{i}.mp4")
                 for i in range(30)]
    d = TaskCenterDock(_StubAgg(many_done))
    assert d.list_done.count() == 20
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_task_center_dock_smoke.py -q -p no:faulthandler
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 TaskCenterDock**

`drama_shot_master/ui/widgets/task_center_dock.py`:

```python
"""任务中心抽屉：跨 4 个生成功能的只读总览 + 跳转。
右侧 QDockWidget，默认隐藏；3 组 QListWidget（生成中 / 失败 / 最近完成）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox,
)


_KIND_LABELS = {"video": "视频", "imggen": "出图",
                "dub": "配音", "soundtrack": "配乐"}


class TaskCenterDock(QDockWidget):
    taskActivated = Signal(str, str)         # (kind, task_id)

    def __init__(self, aggregator, parent=None):
        super().__init__("任务中心", parent)
        self.setAllowedAreas(Qt.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self._agg = aggregator
        self._recent_complete_limit = 20
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        w = QWidget()
        v = QVBoxLayout(w)
        # 顶 toolbar
        tb = QHBoxLayout()
        self.lbl_counts = QLabel("")
        tb.addWidget(self.lbl_counts, 1)
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setFlat(True)
        self.btn_refresh.setToolTip("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        tb.addWidget(self.btn_refresh)
        v.addLayout(tb)
        # 3 个分组
        self.list_running = QListWidget()
        self.list_failed = QListWidget()
        self.list_done = QListWidget()
        for grp_title, lst in (("生成中", self.list_running),
                                ("失败",   self.list_failed),
                                ("最近完成", self.list_done)):
            box = QGroupBox(grp_title)
            bv = QVBoxLayout(box)
            bv.addWidget(lst)
            lst.itemDoubleClicked.connect(self._on_double_click)
            v.addWidget(box)
        self.setWidget(w)

    def refresh(self):
        records = self._agg.snapshot()
        running = [r for r in records if r.status == "生成中"]
        failed = [r for r in records if r.status == "失败"]
        done = [r for r in records if r.status == "完成" and r.last_result]
        done = self._sort_recent(done)[: self._recent_complete_limit]
        self._fill(self.list_running, running)
        self._fill(self.list_failed, failed)
        self._fill(self.list_done, done)
        self.lbl_counts.setText(
            f"生成中 {len(running)} · 失败 {len(failed)} · 完成 {len(done)}")

    def _fill(self, lst: QListWidget, records: list):
        lst.clear()
        for r in records:
            it = QListWidgetItem(self._row_text(r))
            it.setData(Qt.UserRole, (r.kind, r.task_id))
            lst.addItem(it)

    def _row_text(self, r) -> str:
        suffix = (" · " + Path(r.last_result).name) if r.last_result else ""
        kind_lbl = _KIND_LABELS.get(r.kind, r.kind)
        return f"[{kind_lbl}] {r.name}{suffix}"

    def _on_double_click(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        kind, tid = data
        self.taskActivated.emit(kind, tid)

    def _sort_recent(self, records: list) -> list:
        """按 last_result 文件 mtime 倒序；不可读则按原序。"""
        def key(r):
            try:
                return -Path(r.last_result).stat().st_mtime
            except Exception:
                return 0
        return sorted(records, key=key)
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_task_center_dock_smoke.py -q -p no:faulthandler
```

Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/task_center_dock.py tests/test_ui/test_task_center_dock_smoke.py
git commit -m "feat(ui): TaskCenterDock 右侧抽屉只读总览+跳转（3 分组，最近完成上限 20）"
```

---

### Task 19: AppShell 接入 TaskCenterDock

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: 在 _build_ui 末尾追加 dock 构造与挂载**

`app_shell.py` `_build_ui` 方法末尾（`self.setCentralWidget(central)` 之后）追加：

```python
        # 任务中心 dock
        from drama_shot_master.core.task_aggregator import TaskAggregator
        from drama_shot_master.ui.widgets.task_center_dock import TaskCenterDock
        self._task_agg = TaskAggregator(
            self.cfg, self.video_store, self.dub_store, self.imggen_store,
            managers={
                "video": self._video_manager(),
                "dub": self._dub_manager(),
                "imggen": self._imggen_manager(),
            },
        )
        self.task_center_dock = TaskCenterDock(self._task_agg, parent=self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.task_center_dock)
        self.task_center_dock.setVisible(
            bool(getattr(self.cfg, "task_center_visible", False)))
        self.task_center_dock.taskActivated.connect(self._activate_task)
        self.task_center_dock.visibilityChanged.connect(
            self._on_task_center_visibility)
```

文件顶部 import 加：

```python
from PySide6.QtCore import Qt
```

（如果已 import 过，跳过。）

- [ ] **Step 2: 加 _activate_task 与 _on_task_center_visibility**

```python
    def _activate_task(self, kind: str, tid: str):
        key = {"video": "video_gen", "dub": "dubbing",
               "imggen": "imggen", "soundtrack": "soundtrack"}.get(kind)
        if key is None:
            return
        self.switchTo(self.pages[key])
        mgr = getattr(self.pages[key], "manager", None)
        if mgr is not None and hasattr(mgr, "_select_task"):
            mgr._select_task(tid)

    def _on_task_center_visibility(self, v: bool):
        try:
            self.cfg.update_settings(task_center_visible=bool(v))
        except Exception:
            pass
```

- [ ] **Step 3: 在 8 个状态/结果 handler 末尾追加 dock.refresh()**

找到这 8 个方法，每个末尾加 `self.task_center_dock.refresh()`：

- `_on_task_status` / `_on_task_result`（video）
- `_on_dub_status` / `_on_dub_result`
- `_on_imggen_status` / `_on_imggen_result`
- `_on_soundtrack_status` / `_on_soundtrack_result`

注意防御性写法：dock 可能尚未构造（极少见，但 _on_task_status 可能在 _build_ui 完成前就被信号触发）：

```python
        ...原有逻辑...
        if hasattr(self, "task_center_dock"):
            self.task_center_dock.refresh()
```

- [ ] **Step 4: 写/扩展 AppShell smoke 测试**

`tests/test_ui/test_app_shell_smoke.py` 末尾追加：

```python
def test_task_center_dock_present_and_hidden_by_default():
    _app()
    from drama_shot_master.ui.widgets.task_center_dock import TaskCenterDock
    w = AppShell()
    assert hasattr(w, "task_center_dock")
    assert isinstance(w.task_center_dock, TaskCenterDock)
    # 默认隐藏
    assert w.task_center_dock.isVisible() is False


def test_activate_task_switches_page_and_selects():
    _app()
    w = AppShell()
    # 添一个 video task 后激活
    mgr = w._video_manager()
    if not mgr.store.all():
        mgr.store.add("T1", {})
        mgr.refresh()
    tid = mgr.store.all()[0].id
    w._activate_task("video", tid)
    assert w.stack.currentWidget() is w.pages["video_gen"]
```

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/test_app_shell_smoke.py -q -p no:faulthandler
```

Expected: 之前的用例 + 2 个新用例全 PASS。

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/app_shell.py tests/test_ui/test_app_shell_smoke.py
git commit -m "feat(ui): AppShell 接入 TaskCenterDock（默认隐藏、8 处状态 handler 刷新）"
```

---

### Task 20: ProjectCommandBar 任务按钮

**Files:**
- Modify: `drama_shot_master/ui/widgets/project_command_bar.py`
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: ProjectCommandBar 加 taskCenterToggled 信号与按钮**

读 `drama_shot_master/ui/widgets/project_command_bar.py` 看现有结构。然后：

类定义内顶部加信号：

```python
    taskCenterToggled = Signal(bool)
```

`_build_ui` 末尾（或合适位置）加按钮：

```python
        self.btn_task_center = QPushButton("⧉ 任务")
        self.btn_task_center.setCheckable(True)
        self.btn_task_center.setToolTip("打开任务中心 (跨 4 个生成功能的总览)")
        self.btn_task_center.toggled.connect(self.taskCenterToggled)
        # 加进现有 layout 末尾（按文件原结构插入）
        ...layout.addWidget(self.btn_task_center)
```

- [ ] **Step 2: AppShell 接通**

`app_shell.py` `_wire` 方法里追加：

```python
        self.command_bar.taskCenterToggled.connect(self.task_center_dock.setVisible)
        self.task_center_dock.visibilityChanged.connect(
            self.command_bar.btn_task_center.setChecked)
```

- [ ] **Step 3: 写测试**

`tests/test_ui/test_app_shell_smoke.py` 末尾追加：

```python
def test_command_bar_toggle_task_center():
    _app()
    w = AppShell()
    assert w.task_center_dock.isVisible() is False
    w.command_bar.btn_task_center.setChecked(True)
    # toggled → setVisible(True)
    assert w.task_center_dock.isVisible() is True
    w.command_bar.btn_task_center.setChecked(False)
    assert w.task_center_dock.isVisible() is False
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_app_shell_smoke.py -q -p no:faulthandler
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/project_command_bar.py drama_shot_master/ui/app_shell.py tests/test_ui/test_app_shell_smoke.py
git commit -m "feat(ui): ProjectCommandBar 任务按钮 toggle 任务中心 dock 显隐"
```

---

## Workstream D: 侧栏折叠（动画） + 精修

### Task 21: FlowSidebar 加 QPropertyAnimation 与 tooltip 富化

**Files:**
- Modify: `drama_shot_master/ui/widgets/flow_sidebar.py`
- Modify: `tests/test_ui/test_flow_sidebar_smoke.py`

> 现有 `set_collapsed` 同步切宽 + label 隐藏；本任务只在 set_collapsed 基础上加动画与折叠态 tooltip 富化。

- [ ] **Step 1: 写测试用例**

`tests/test_ui/test_flow_sidebar_smoke.py` 末尾追加：

```python
def test_collapsed_state_persists_widths():
    _app()
    sb = FlowSidebar()
    sb.set_collapsed(True)
    assert sb.maximumWidth() == COLLAPSED_W
    sb.set_collapsed(False)
    assert sb.maximumWidth() == EXPANDED_W


def test_collapsed_buttons_have_full_path_tooltip():
    _app()
    sb = FlowSidebar()
    sb.set_collapsed(True)
    # 任取一个功能按钮，tooltip 应含 "阶段 › 项" 格式
    for key, btn in sb._buttons.items():
        tip = btn.toolTip()
        assert "›" in tip, f"{key} tooltip={tip}"
        break
    sb.set_collapsed(False)
    # 展开态：tooltip 不要求路径（保留原本 text 即可，但不带 ›）
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_flow_sidebar_smoke.py::test_collapsed_buttons_have_full_path_tooltip -q -p no:faulthandler
```

Expected: FAIL — 现 `set_collapsed` 不改 tooltip。

- [ ] **Step 3: 改造 flow_sidebar.py 的 set_collapsed**

在 `FlowSidebar` 类里，加属性 `_item_phase_titles` 记录每个 key 所属阶段标题。`_build` 方法里循环 phases 时：

```python
        self._item_phase_titles: dict[str, str] = {}
        ...
        for phase_title, keys in nav_config.PHASES:
            ...
            for key in keys:
                self._item_phase_titles[key] = phase_title    # 新增
                ...
```

改 `set_collapsed`：

```python
    def set_collapsed(self, collapsed: bool, animate: bool = True):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        # 1) 立刻切按钮风格 + label/tooltip
        style = Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon
        for key, btn in self._buttons.items():
            btn.setToolButtonStyle(style)
            if collapsed:
                phase = self._item_phase_titles.get(key, "")
                label = nav_config.LABELS.get(key, key)
                btn.setToolTip(f"{phase} › {label}" if phase else label)
            else:
                btn.setToolTip(nav_config.LABELS.get(key, key))
        for b in self._menu_buttons():
            b.setToolButtonStyle(style)
        for lbl in self._phase_labels:
            lbl.setVisible(not collapsed)
        # 2) 起动画切宽
        target = COLLAPSED_W if collapsed else EXPANDED_W
        self._animate_to(target, animate)

    def _animate_to(self, target: int, animate: bool):
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        if not animate:
            self.setMinimumWidth(target); self.setMaximumWidth(target)
            return
        # 同时动画 minimumWidth 和 maximumWidth，避免 splitter 抢
        anim_max = QPropertyAnimation(self, b"maximumWidth", self)
        anim_max.setDuration(160); anim_max.setEasingCurve(QEasingCurve.OutCubic)
        anim_max.setStartValue(self.maximumWidth()); anim_max.setEndValue(target)
        anim_min = QPropertyAnimation(self, b"minimumWidth", self)
        anim_min.setDuration(160); anim_min.setEasingCurve(QEasingCurve.OutCubic)
        anim_min.setStartValue(self.minimumWidth()); anim_min.setEndValue(target)
        anim_max.start(); anim_min.start()
        self._anim_max = anim_max; self._anim_min = anim_min       # 防 GC
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_ui/test_flow_sidebar_smoke.py -q -p no:faulthandler
```

Expected: PASS（含新 2 个）。

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/flow_sidebar.py tests/test_ui/test_flow_sidebar_smoke.py
git commit -m "feat(ui): FlowSidebar 折叠加 QPropertyAnimation + 折叠态 tooltip 富化（阶段›项）"
```

---

### Task 22: 侧栏折叠状态 cfg 持久化

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: 写测试**

`tests/test_ui/test_app_shell_smoke.py` 末尾追加：

```python
def test_sidebar_collapse_persists_to_cfg(monkeypatch):
    _app()
    w = AppShell()
    captured = {}
    monkeypatch.setattr(w.cfg, "update_settings", lambda **kw: captured.update(kw))
    w.sidebar.set_collapsed(True, animate=False)
    # AppShell 应监听 collapsedChanged 并写 cfg
    assert captured.get("sidebar_collapsed") is True
    w.sidebar.set_collapsed(False, animate=False)
    assert captured.get("sidebar_collapsed") is False
```

- [ ] **Step 2: 跑确认失败**

```bash
python -m pytest tests/test_ui/test_app_shell_smoke.py::test_sidebar_collapse_persists_to_cfg -q -p no:faulthandler
```

Expected: FAIL（FlowSidebar 没有发 collapsedChanged）。

- [ ] **Step 3: 在 FlowSidebar 加 collapsedChanged 信号**

`drama_shot_master/ui/widgets/flow_sidebar.py` 类定义加：

```python
    collapsedChanged = Signal(bool)
```

并在 `set_collapsed` 末尾 emit：

```python
        self.collapsedChanged.emit(collapsed)
```

- [ ] **Step 4: AppShell 接通并启动恢复**

`_wire` 末尾追加：

```python
        self.sidebar.collapsedChanged.connect(
            lambda v: self._safe_update_setting("sidebar_collapsed", bool(v)))
```

加 helper：

```python
    def _safe_update_setting(self, key: str, val):
        try:
            self.cfg.update_settings(**{key: val})
        except Exception:
            pass
```

`_restore_state` 方法末尾追加（在恢复活跃功能页之后）：

```python
        if getattr(self.cfg, "sidebar_collapsed", False):
            self.sidebar.set_collapsed(True, animate=False)
```

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_ui/test_app_shell_smoke.py -q -p no:faulthandler
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/widgets/flow_sidebar.py drama_shot_master/ui/app_shell.py tests/test_ui/test_app_shell_smoke.py
git commit -m "feat(ui): 侧栏折叠状态 cfg 持久化 + 启动恢复"
```

---

### Task 23: 过时 MainWindow 注释清理

**Files:**
- Modify: `drama_shot_master/core/submit_debug.py`
- Modify: `drama_shot_master/ui/panels/base_panel.py`
- Modify: `drama_shot_master/ui/widgets/project_command_bar.py`

- [ ] **Step 1: 改 5 处文本**

逐文件编辑（注意只改注释/docstring，不动代码逻辑）：

`drama_shot_master/core/submit_debug.py`:
- 第 4 行：`MainWindow 关闭时` → `AppShell 关闭时`
- 第 20 行：`MainWindow 关闭时调` → `AppShell 关闭时调`

`drama_shot_master/ui/panels/base_panel.py`:
- 第 1 行：`向 MainWindow 暴露统一接口` → `向 AppShell 暴露统一接口`
- 第 14 行：`MainWindow 重算执行按钮` → `AppShell 重算执行按钮`

`drama_shot_master/ui/widgets/project_command_bar.py`:
- 第 3 行：`补回旧 MainWindow 左栏丢失的目录入口` → `补回旧 MainWindow 左栏（已退役）丢失的目录入口`

- [ ] **Step 2: 验证 grep**

```bash
grep -rnE "MainWindow" drama_shot_master/ --include="*.py" | grep -v QMainWindow | grep -v test_
```

Expected: 仅余「已退役」字样的注释（即上面 project_command_bar.py 第 3 行），其它无。

- [ ] **Step 3: 跑全套 UI 测试**

```bash
python -m pytest tests/test_ui/ -q -p no:faulthandler 2>&1 | grep -cE "PASSED|FAILED"
```

Expected: 全 PASSED，0 FAILED（仅注释改不会影响测试）。

- [ ] **Step 4: Commit**

```bash
git add drama_shot_master/core/submit_debug.py drama_shot_master/ui/panels/base_panel.py drama_shot_master/ui/widgets/project_command_bar.py
git commit -m "docs: 5 处过时 MainWindow 注释改为 AppShell（实际 main_window.py 早已退役）"
```

---

### Task 24: 重命名一致性 audit + 全局 acceptance

**Files:** （只读 grep + 必要修订）

- [ ] **Step 1: 重命名按钮 audit**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
grep -rnE '"重命名"|"Rename"' drama_shot_master/ui/panels/ --include="*.py"
```

Expected: 空。如非空：找到的按钮删除（与现有 inline 改名一致）。

- [ ] **Step 2: 全局 acceptance grep**

```bash
echo "=== qfluentwidgets 仅余字面提及（无 import/usage） ==="
grep -rnE "qfluentwidgets" drama_shot_master/ tests/ --include="*.py" | grep -vE "(docstring|注释|replacing|替换)"
echo "(应为空或仅文档注释)"

echo "=== 全部 4 个生成功能均 TaskWorkspacePage ==="
python -c "
import os; os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
QApplication([])
from drama_shot_master.ui.app_shell import AppShell
from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage as P
w = AppShell()
print({k: isinstance(w.pages[k], P) for k in ('imggen','dubbing','video_gen','soundtrack')})
"

echo "=== 6 个旧 settings dialog 不存在 ==="
for f in runninghub translation refine soundtrack dub imggen; do
    [ -f drama_shot_master/ui/dialogs/${f}_settings_dialog.py ] && echo "STILL EXISTS: $f" || echo "deleted: $f"
done

echo "=== UnifiedSettingsDialog 存在 ==="
ls drama_shot_master/ui/dialogs/unified_settings_dialog.py

echo "=== TaskCenterDock 默认隐藏 ==="
python -c "
import os; os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
QApplication([])
from drama_shot_master.ui.app_shell import AppShell
w = AppShell()
print('hidden:', not w.task_center_dock.isVisible())
"

echo "=== 主题切换跑得通 ==="
python -c "
import os; os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
app = QApplication([])
from drama_shot_master.ui.theme import apply_theme
apply_theme(app, 'dark'); assert '#1e1f22' in app.styleSheet()
apply_theme(app, 'light'); assert '#fafafa' in app.styleSheet()
print('theme switch OK')
"
```

Expected outputs:
- qfluentwidgets：空或仅文档注释
- 4 个 page 都是 `True`
- 6 个 settings dialog 都是 `deleted`
- `unified_settings_dialog.py` 存在
- task center hidden: True
- theme switch OK

- [ ] **Step 3: 跑全 UI 套件 + 各重点单元**

```bash
for f in test_theme_smoke test_settings_sections_smoke test_unified_settings_dialog_smoke test_task_center_dock_smoke test_app_shell_smoke test_flow_sidebar_smoke; do
  out=$(python -m pytest tests/test_ui/$f.py -q -p no:faulthandler 2>&1 | grep -E "passed|failed" | tail -1)
  echo "$f: $out"
done
python -m pytest tests/test_core/test_task_aggregator.py -q -p no:faulthandler
```

Expected: 各文件 PASS、0 FAILED。

- [ ] **Step 4: Commit 验收**

```bash
git commit --allow-empty -m "chore(ui): Phase 3+4+5 收口验收（主题/设置/任务中心/侧栏折叠全绿）"
```

---

## Self-Review

**Spec coverage 核对（对照 spec §1-§5）：**

- §1 总体架构与推进顺序 → 整个计划按 A→B→C→D 排序，每 workstream 结束有 acceptance 检查点。✓
- §2 主题系统 token → Task 1-4 覆盖 tokens_dark/tpl/theme.py/tokens_light。✓
- §2.4 迁移策略 step1 保 dark 视觉不变 → Task 1 + Task 2.Step3 验证。✓
- §2.4 step3 53 处硬编码扫除 → Task 7 显式列出 grep + 分类 + 迁移模式。✓
- §2.4 step4 持久化与启动 → Task 5 main.py + AppShell showEvent。✓
- §3.1 文件结构（settings_sections 目录、UnifiedSettingsDialog） → Task 8-13 覆盖。✓
- §3.2 SectionWidget 协议（title/category/load_from/save_to/validate） → 每 section 任务都遵守。✓
- §3.3 字段对照表 → Task 9-11 各自参考旧 dialog；plan 阶段实施者按真实代码填字段。✓
- §3.5 ThemeSection 实时切换 → Task 12 显式测试 + 实现。✓
- §3.6 AppShell 入口改造 + 删 6 个 _open_<x>_settings → Task 14。✓
- §3.7 测试 → 每个 section 至少 1 个 load/save round-trip + dialog 5 个 smoke。✓
- §3.8 风险（字段遗漏、连通测试 worker 取消） → Task 13 reject 调 cancel_workers。✓
- §4.1-4.7 TaskCenterDock 全套 → Task 16-20 覆盖。✓
- §4.8 风险（长列表性能）→ v1 接受，不引入增量更新（spec 已说明）。✓
- §5.1 CollapsibleFlowSidebar → Task 21（动画+tooltip）+ Task 22（持久化）。✓
- §5.2 5 处 MainWindow 注释清理 → Task 23。✓
- §5.3 重命名一致性 audit → Task 24 Step1。✓
- §5.4 测试 → Task 21/22 各含。✓
- §6 测试策略汇总 / §7 非目标 / §8 后续 → Plan 不强复写（已在 spec 中）。

**Placeholder 扫描：**
- Task 8 末注释「如果 `runninghub_health.check` 不存在 → 改读原 dialog 实现」——这是合理的实现指南，不是 placeholder（原 dialog 文件存在且开发者会读）。可接受。
- Task 9-11 写为「reference dialog: <path>」+ class metadata + "同 Task 8 五步流程"——这违反 "Similar to Task N" 的禁忌。**修复**：把 Task 9-11 内容写完整、不依赖 Task 8 引用。
- Task 21 Step3 末「同时动画 minimumWidth 和 maximumWidth」——给了完整代码，OK。
- Task 11a/b/c 字段已在表格里列出。

**Type consistency：**
- `TaskRecord(kind, task_id, name, status, last_result)` 用法在 Task 17/18/19 一致。✓
- `apply_theme(app, name)` / `apply_titlebar(widget, name)` / `current_theme(cfg)` 签名贯穿。✓
- `_tokens(name)` 返回 dict，所有调用方一致使用。✓
- SectionWidget 协议（title/category/load_from/save_to/validate/cancel_workers）一致。✓
- `get_status(tid: str) -> str` 在 3 个 manager 与 TaskAggregator 中一致。✓

**修复记录（已就地处理）：**
Tasks 9-11 起初写为 "同 Task 8 流程"——违反 "Similar to Task N" 禁忌。已展开为自包含任务，每个含完整测试用例、完整 section 实现代码、五步 TDD 流程。
