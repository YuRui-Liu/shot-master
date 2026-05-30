# 糯米AI欢迎首页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AppShell 启动时展示全画布欢迎首页（深蓝紫调、沉浸光晕、最近项目卡片走马灯、工作流引导条），用户点击项目或新建后过渡到主界面。

**Architecture:** WelcomePage 作为外层 `QStackedWidget` 的 index 0，原主界面（ProjectCommandBar + 侧边栏 + 功能页）为 index 1。启动时显示 index 0；用户进入功能后 fade-out WelcomePage + sidebar slide-in，切换到 index 1。FlowSidebar 新增"首页"按钮，点击后切回 WelcomePage。

**Tech Stack:** PySide6 (QWidget, QPainter, QPropertyAnimation, QGraphicsOpacityEffect, QGraphicsDropShadowEffect), Python 3.10+, pytest + QT_QPA_PLATFORM=offscreen

> **注意（与 spec 的偏差）：** 本计划保留原生 OS 标题栏（不用 FramelessWindowHint），WelcomePage 内有自己的导航条（Logo + 名称 + 全局设置按钮），OS 标题栏通过 `setWindowTitle` 显示应用名。这样改动最小、稳定性最高。

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| **新建** | `drama_shot_master/core/recent_projects.py` | RecentProjectsManager：读写 recent_projects.json，最多 8 条，按时间降序 |
| **新建** | `drama_shot_master/ui/widgets/workflow_strip.py` | WorkflowStrip：纯视觉，底部四步流程条，QPainter 绘制 |
| **新建** | `drama_shot_master/ui/widgets/project_card.py` | ProjectCard：单张项目卡，`clicked = Signal(str)`，支持深度样式 |
| **新建** | `drama_shot_master/ui/pages/welcome_page.py` | WelcomePage：背景渐变+光晕，组合导航栏/Hero/卡片/流程条，发 project_selected / new_project_requested / open_dir_requested / settings_requested |
| **修改** | `drama_shot_master/ui/app_shell.py` | 增加 outer_stack，集成 WelcomePage，transition 动画，连接信号 |
| **修改** | `drama_shot_master/ui/widgets/flow_sidebar.py` | 在顶部增加 homeRequested Signal 和 Home 按钮 |
| **修改** | `drama_shot_master/main.py` | setApplicationName → "糯米AI分镜影视创作台" |
| **新建** | `tests/test_core/test_recent_projects.py` | 纯 Python 测试，无 Qt |
| **新建** | `tests/test_ui/test_welcome_page.py` | Qt 测试，offscreen |

---

## Task 1: RecentProjectsManager

**Files:**
- Create: `drama_shot_master/core/recent_projects.py`
- Test: `tests/test_core/test_recent_projects.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_core/test_recent_projects.py
import json
from pathlib import Path
import pytest
from drama_shot_master.core.recent_projects import RecentProjectsManager


def test_load_empty_when_file_missing(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    assert mgr.load() == []


def test_push_creates_entry(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push("/proj/alpha", "Alpha")
    projects = mgr.load()
    assert len(projects) == 1
    assert projects[0]["path"] == "/proj/alpha"
    assert projects[0]["name"] == "Alpha"


def test_push_deduplicates_by_path(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push("/proj/alpha", "Alpha")
    mgr.push("/proj/alpha", "Alpha v2")
    projects = mgr.load()
    assert len(projects) == 1
    assert projects[0]["name"] == "Alpha v2"


def test_push_trims_to_max(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    for i in range(10):
        mgr.push(f"/proj/{i}", f"Project {i}")
    assert len(mgr.load()) == RecentProjectsManager.MAX


def test_most_recent_first(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push("/proj/old", "Old")
    mgr.push("/proj/new", "New")
    projects = mgr.load()
    assert projects[0]["path"] == "/proj/new"


def test_load_skips_missing_paths(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push(str(tmp_path), "exists")
    mgr.push("/nonexistent/path/xyz", "missing")
    projects = mgr.load()
    assert all(p["path"] == str(tmp_path) for p in projects)
    assert len(projects) == 1


def test_remove_deletes_entry(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push("/proj/alpha", "Alpha")
    mgr.remove("/proj/alpha")
    assert mgr.load() == []


def test_push_without_name_uses_dirname(tmp_path):
    mgr = RecentProjectsManager(tmp_path / "recent.json")
    mgr.push("/some/project/MyDrama")
    projects = mgr.load()
    assert projects[0]["name"] == "MyDrama"
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
python -m pytest tests/test_core/test_recent_projects.py -v
```
预期: `ERROR` — `ModuleNotFoundError: No module named 'drama_shot_master.core.recent_projects'`

- [ ] **Step 3: 实现 RecentProjectsManager**

```python
# drama_shot_master/core/recent_projects.py
"""最近项目列表：读写 recent_projects.json，最多 MAX 条，按最后打开时间降序。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class RecentProjectsManager:
    MAX = 8

    def __init__(self, path: Path):
        self._path = Path(path)

    @classmethod
    def alongside_settings(cls, settings_path: Path) -> "RecentProjectsManager":
        """与 settings.json 同目录。"""
        return cls(Path(settings_path).parent / "recent_projects.json")

    def load(self) -> list[dict]:
        """返回有效项目列表（path 必须存在），按 last_opened 降序。"""
        raw = self._read_raw()
        valid = [p for p in raw if Path(p.get("path", "")).exists()]
        if len(valid) != len(raw):
            self._write_raw(valid)
        return valid

    def push(self, path: str, name: str | None = None) -> None:
        """添加或更新一条记录，移至列表首位，裁剪至 MAX。"""
        path = str(Path(path))
        raw = self._read_raw()
        raw = [p for p in raw if p.get("path") != path]
        entry = {
            "name": name if name is not None else Path(path).name,
            "path": path,
            "last_opened": datetime.now(timezone.utc).isoformat(),
            "shot_count": 0,
        }
        raw.insert(0, entry)
        self._write_raw(raw[:self.MAX])

    def remove(self, path: str) -> None:
        """从列表中删除指定路径。"""
        path = str(Path(path))
        raw = [p for p in self._read_raw() if p.get("path") != path]
        self._write_raw(raw)

    def _read_raw(self) -> list[dict]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _write_raw(self, projects: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(projects, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/test_core/test_recent_projects.py -v
```
预期: 全部 `PASSED`

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/core/recent_projects.py tests/test_core/test_recent_projects.py
git commit -m "feat(welcome): RecentProjectsManager — 最近项目 JSON 读写"
```

---

## Task 2: WorkflowStrip 视觉组件

**Files:**
- Create: `drama_shot_master/ui/widgets/workflow_strip.py`

- [ ] **Step 1: 创建 WorkflowStrip**

```python
# drama_shot_master/ui/widgets/workflow_strip.py
"""底部四步工作流指示条（纯视觉，无交互）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient, QFont,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

_STEPS = [
    ("01", "剧本创作"),
    ("02", "AI 分镜出图"),
    ("03", "生成视频"),
    ("04", "后期配音配乐"),
]

_C_ACTIVE_LABEL = QColor("#c0c8e0")
_C_INACTIVE_LABEL = QColor("#3a4a6a")
_C_ACTIVE_ARROW = QColor("#4a9eff")
_C_INACTIVE_ARROW = QColor("#252540")
_C_DOT_INACTIVE_BG = QColor("#111128")
_C_DOT_INACTIVE_BORDER = QColor("#252540")
_C_LINE = QColor("#1e1e3a")


class WorkflowStrip(QWidget):
    """一行四步流程条，active_index 对应高亮步骤（默认 0 = 剧本创作）。"""

    def __init__(self, active_index: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self._active = active_index
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_active(self, index: int) -> None:
        self._active = index
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cy = h // 2

        # — fading horizontal lines —
        for start_x, end_x in [(0, w // 4), (w * 3 // 4, w)]:
            grad = QLinearGradient(start_x, 0, end_x, 0)
            if start_x == 0:
                grad.setColorAt(0, QColor(0, 0, 0, 0))
                grad.setColorAt(1, _C_LINE)
            else:
                grad.setColorAt(0, _C_LINE)
                grad.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            from PySide6.QtGui import QBrush
            p.setBrush(QBrush(grad))
            p.drawRect(start_x, cy - 1, end_x - start_x, 2)

        # — compute step positions —
        dot_r = 10          # radius of step dot
        font_label = QFont(self.font())
        font_label.setPixelSize(11)
        font_num = QFont(self.font())
        font_num.setPixelSize(9)
        font_num.setBold(True)

        # Measure total content width for centering
        arrow_w = 14
        label_gap = 5
        step_widths = []
        fm_label = self.fontMetrics()
        for _num, label in _STEPS:
            step_widths.append(dot_r * 2 + label_gap + fm_label.horizontalAdvance(label))
        total_w = sum(step_widths) + arrow_w * (len(_STEPS) - 1)
        x = (w - total_w) // 2

        for i, (num, label) in enumerate(_STEPS):
            active = i == self._active
            cx = x + dot_r

            # dot background
            if active:
                grad = QLinearGradient(cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r)
                grad.setColorAt(0, QColor("#4a9eff"))
                grad.setColorAt(1, QColor("#a06cff"))
                from PySide6.QtGui import QBrush
                p.setBrush(QBrush(grad))
                p.setPen(Qt.NoPen)
            else:
                p.setBrush(QColor(_C_DOT_INACTIVE_BG))
                p.setPen(QColor(_C_DOT_INACTIVE_BORDER))

            p.drawEllipse(QPoint(cx, cy), dot_r, dot_r)

            # dot number
            p.setPen(_C_ACTIVE_LABEL if active else _C_INACTIVE_LABEL)
            p.setFont(font_num)
            p.drawText(
                QRect(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2),
                Qt.AlignCenter, num,
            )

            # label
            lx = cx + dot_r + label_gap
            p.setFont(font_label)
            if active:
                font_label.setBold(True)
                p.setFont(font_label)
                p.setPen(_C_ACTIVE_LABEL)
                font_label.setBold(False)
            else:
                p.setPen(_C_INACTIVE_LABEL)

            label_rect = QRect(lx, cy - 10, step_widths[i] - dot_r * 2 - label_gap, 20)
            p.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

            x += step_widths[i]

            # arrow
            if i < len(_STEPS) - 1:
                p.setPen(_C_ACTIVE_ARROW if active else _C_INACTIVE_ARROW)
                p.setFont(QFont(self.font()))
                p.drawText(
                    QRect(x, cy - 10, arrow_w, 20),
                    Qt.AlignCenter, "›",
                )
                x += arrow_w

        p.end()
```

- [ ] **Step 2: 快速烟雾测试（无 display 也能实例化）**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
python -c "
import os; os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
app = QApplication([])
from drama_shot_master.ui.widgets.workflow_strip import WorkflowStrip
w = WorkflowStrip(active_index=0)
assert w.height() == 38
print('WorkflowStrip OK')
"
```
预期: `WorkflowStrip OK`

- [ ] **Step 3: 提交**

```bash
git add drama_shot_master/ui/widgets/workflow_strip.py
git commit -m "feat(welcome): WorkflowStrip — 四步流程条视觉组件"
```

---

## Task 3: ProjectCard 组件

**Files:**
- Create: `drama_shot_master/ui/widgets/project_card.py`
- Test: `tests/test_ui/test_welcome_page.py`（先写 ProjectCard 的测试部分）

- [ ] **Step 1: 写失败测试（ProjectCard 部分）**

```python
# tests/test_ui/test_welcome_page.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


# ── ProjectCard ────────────────────────────────────────────────────────────

def test_project_card_emits_path_on_click():
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    card = ProjectCard({"name": "TestProj", "path": "/some/path", "last_opened": "", "shot_count": 3})
    card.show()
    got = []
    card.clicked.connect(got.append)
    QTest.mouseClick(card, Qt.LeftButton)
    assert got == ["/some/path"]


def test_add_card_emits_empty_string_on_click():
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    card = ProjectCard(None, is_add_button=True)
    card.show()
    got = []
    card.clicked.connect(got.append)
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    QTest.mouseClick(card, Qt.LeftButton)
    assert got == [""]


def test_project_card_depth_opacity():
    _app()
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    far = ProjectCard({"name": "A", "path": "/a", "last_opened": "", "shot_count": 0}, depth="far")
    center = ProjectCard({"name": "B", "path": "/b", "last_opened": "", "shot_count": 0}, depth="center")
    far_effect = far.graphicsEffect()
    center_effect = center.graphicsEffect()
    assert far_effect is None or far_effect.opacity() < 0.6
    assert center_effect is None or center_effect.opacity() >= 0.99
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/test_ui/test_welcome_page.py::test_project_card_emits_path_on_click -v
```
预期: `ERROR` — `No module named 'drama_shot_master.ui.widgets.project_card'`

- [ ] **Step 3: 实现 ProjectCard**

```python
# drama_shot_master/ui/widgets/project_card.py
"""ProjectCard：欢迎首页项目卡片，支持深度样式（far/near/center），点击发 clicked(path)。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QFont, QBrush, QPen,
)
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect, QSizePolicy

# 各深度的不透明度
_DEPTH_OPACITY = {"far": 0.50, "near": 0.72, "center": 1.0, "add": 0.60}
# 各深度的高度比例（相对父容器高度）
_DEPTH_HEIGHT_RATIO = {"far": 0.78, "near": 0.88, "center": 1.0, "add": 0.72}

# 缩略图渐变配色（每次显示固定色，不随机）
_THUMB_COLORS = [
    ("#1a2848", "#2a1848"),  # 蓝紫
    ("#281020", "#1a1030"),  # 深红紫
    ("#102820", "#1a2028"),  # 深绿
    ("#201a10", "#281818"),  # 暖棕
]


class ProjectCard(QWidget):
    """单张项目卡片。

    Args:
        project: 项目信息字典 {"name", "path", "last_opened", "shot_count"}，
                 None 时显示"新建"虚线卡。
        depth:   "far" | "near" | "center" | "add"，控制大小和透明度。
        color_index: 缩略图渐变色序号（0-3），默认 0。
    """

    clicked = Signal(str)  # path（add 卡为空字符串）

    def __init__(
        self,
        project: dict | None = None,
        depth: str = "center",
        color_index: int = 0,
        is_add_button: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._project = project
        self._depth = depth
        self._color_index = color_index % len(_THUMB_COLORS)
        self._is_add = is_add_button or project is None
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        opacity = _DEPTH_OPACITY.get(depth, 1.0)
        if opacity < 0.99:
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(opacity)
            self.setGraphicsEffect(effect)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            path = "" if self._is_add else (self._project or {}).get("path", "")
            self.clicked.emit(path)
        super().mousePressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()

        if self._is_add:
            self._paint_add(p, r)
        else:
            self._paint_project(p, r)
        p.end()

    def _paint_add(self, p: QPainter, r: QRect) -> None:
        # 虚线边框
        pen = QPen(QColor("#252540"))
        pen.setStyle(Qt.DashLine)
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)
        # "＋" 图标
        p.setPen(QColor("#353555"))
        font = QFont(self.font())
        font.setPixelSize(28)
        p.setFont(font)
        p.drawText(QRect(r.x(), r.y(), r.width(), r.height() - 20), Qt.AlignCenter, "＋")
        # "新建项目" 文字
        font.setPixelSize(10)
        p.setFont(font)
        p.drawText(QRect(r.x(), r.bottom() - 28, r.width(), 20), Qt.AlignCenter, "新建项目")

    def _paint_project(self, p: QPainter, r: QRect) -> None:
        # 圆角卡片背景
        colors = _THUMB_COLORS[self._color_index]
        bg_grad = QLinearGradient(r.topLeft(), r.bottomRight())
        bg_grad.setColorAt(0, QColor("#1a1a38"))
        bg_grad.setColorAt(1, QColor("#131328"))
        p.setBrush(QBrush(bg_grad))
        if self._depth == "center":
            p.setPen(QPen(QColor("#4a9eff"), 1))
        else:
            p.setPen(QPen(QColor("#252540"), 1))
        p.drawRoundedRect(r.adjusted(0, 0, -1, -1), 10, 10)

        # 缩略图区域
        meta_h = 44
        thumb_r = QRect(r.x(), r.y(), r.width(), r.height() - meta_h)
        thumb_grad = QLinearGradient(thumb_r.topLeft(), thumb_r.bottomRight())
        thumb_grad.setColorAt(0, QColor(colors[0]))
        thumb_grad.setColorAt(1, QColor(colors[1]))
        p.setBrush(QBrush(thumb_grad))
        p.setPen(Qt.NoPen)
        # 只对缩略图区域 clip（保持顶部圆角）
        clip_path = QPainterPath()  # noqa: F821
        from PySide6.QtGui import QPainterPath
        cp = QPainterPath()
        cp.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 10, 10)
        p.setClipPath(cp)
        p.drawRect(thumb_r)

        # 缩略图底部渐变遮罩
        mask_h = thumb_r.height() // 2
        mask_grad = QLinearGradient(0, thumb_r.bottom() - mask_h, 0, thumb_r.bottom())
        mask_grad.setColorAt(0, QColor(0, 0, 0, 0))
        mask_grad.setColorAt(1, QColor(10, 10, 28, 210))
        p.setBrush(QBrush(mask_grad))
        p.drawRect(QRect(thumb_r.x(), thumb_r.bottom() - mask_h, thumb_r.width(), mask_h))

        # center 卡：AI主创标签
        if self._depth == "center":
            tag_r = QRect(thumb_r.x() + 10, thumb_r.y() + 10, 50, 18)
            p.setBrush(QColor(74, 158, 255, 64))
            p.setPen(QPen(QColor("#4a9eff"), 1))
            p.drawRoundedRect(tag_r, 3, 3)
            p.setPen(QColor("#a0c8ff"))
            font = QFont(self.font())
            font.setPixelSize(9)
            p.setFont(font)
            p.drawText(tag_r, Qt.AlignCenter, "AI 主创")

        p.setClipping(False)

        # Meta 区域（名称 + 信息）
        meta_r = QRect(r.x(), r.bottom() - meta_h, r.width(), meta_h)
        p.setBrush(QColor(13, 13, 30, 230))
        p.setPen(Qt.NoPen)
        # 底部圆角
        bottom_cp = QPainterPath()
        bottom_cp.addRoundedRect(meta_r.x(), meta_r.y(), meta_r.width(), meta_r.height(), 10, 10)
        p.setClipPath(bottom_cp)
        p.drawRect(meta_r)
        p.setClipping(False)

        name = (self._project or {}).get("name", "")
        shot_count = (self._project or {}).get("shot_count", 0)
        last_opened = (self._project or {}).get("last_opened", "")

        font_name = QFont(self.font())
        font_name.setPixelSize(11)
        font_name.setBold(True)
        p.setFont(font_name)
        p.setPen(QColor("#d0d8f0"))
        p.drawText(QRect(meta_r.x() + 10, meta_r.y() + 6, meta_r.width() - 20, 16),
                   Qt.AlignVCenter | Qt.AlignLeft, name)

        # dot + info
        dot_cx = meta_r.x() + 10 + 3
        dot_cy = meta_r.y() + 28
        if self._depth == "center":
            p.setBrush(QColor("#4a9eff"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(dot_cx - 3, dot_cy - 3, 6, 6)

        info_parts = []
        if shot_count:
            info_parts.append(f"{shot_count}张分镜")
        if last_opened:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromisoformat(last_opened)
                delta = (datetime.now(timezone.utc) - dt).days
                if delta == 0:
                    info_parts.append("今天")
                elif delta == 1:
                    info_parts.append("昨天")
                elif delta < 7:
                    info_parts.append(f"{delta}天前")
                else:
                    info_parts.append(f"{delta // 7}周前")
            except Exception:
                pass
        info_text = " · ".join(info_parts)
        font_info = QFont(self.font())
        font_info.setPixelSize(9)
        p.setFont(font_info)
        p.setPen(QColor("#5a6a8a"))
        info_x = (dot_cx + 7) if self._depth == "center" else meta_r.x() + 10
        p.drawText(QRect(info_x, meta_r.y() + 20, meta_r.width() - 20, 16),
                   Qt.AlignVCenter | Qt.AlignLeft, info_text)
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/test_ui/test_welcome_page.py::test_project_card_emits_path_on_click \
                 tests/test_ui/test_welcome_page.py::test_add_card_emits_empty_string_on_click \
                 tests/test_ui/test_welcome_page.py::test_project_card_depth_opacity -v
```
预期: 全部 `PASSED`

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/widgets/project_card.py tests/test_ui/test_welcome_page.py
git commit -m "feat(welcome): ProjectCard — 项目卡片组件（景深样式 + clicked 信号）"
```

---

## Task 4: WelcomePage — 骨架 + 背景绘制

**Files:**
- Create: `drama_shot_master/ui/pages/welcome_page.py`

- [ ] **Step 1: 写失败测试（WelcomePage 实例化）**

在 `tests/test_ui/test_welcome_page.py` 末尾追加：

```python
# ── WelcomePage ────────────────────────────────────────────────────────────

def test_welcome_page_instantiates(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    page = WelcomePage(mgr)
    assert page is not None


def test_welcome_page_has_required_signals(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    page = WelcomePage(mgr)
    for sig_name in ("project_selected", "new_project_requested",
                     "open_dir_requested", "settings_requested"):
        assert hasattr(page, sig_name), f"missing signal: {sig_name}"
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/test_ui/test_welcome_page.py::test_welcome_page_instantiates -v
```
预期: `ERROR` — `No module named 'drama_shot_master.ui.pages.welcome_page'`

- [ ] **Step 3: 创建 WelcomePage 骨架**

```python
# drama_shot_master/ui/pages/welcome_page.py
"""欢迎首页：全画布深蓝紫调，Logo+Hero+最近项目卡片+工作流条。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect, QSize
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient, QBrush, QPen, QFont,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpacerItem,
)

from drama_shot_master.core.recent_projects import RecentProjectsManager
from drama_shot_master.ui.widgets.workflow_strip import WorkflowStrip
from drama_shot_master.ui.widgets.project_card import ProjectCard

# 最多展示卡片数（center + 左右侧）
_MAX_CARDS = 4

# 卡片位置对应的 depth tag（按显示顺序，最多 4 张 + add）
_DEPTH_SEQUENCE = ["far", "near", "center", "near", "add"]


class WelcomePage(QWidget):
    """欢迎首页。与 AppShell 通信通过信号，不持有 AppShell 引用。"""

    project_selected = Signal(str)       # 用户点击已有项目，传目录 path
    new_project_requested = Signal()     # 用户点"新建项目"按钮或 add 卡
    open_dir_requested = Signal()        # 用户点"打开目录"按钮
    settings_requested = Signal()        # 用户点"全局设置"按钮

    def __init__(self, recent_mgr: RecentProjectsManager,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._mgr = recent_mgr
        self.setObjectName("WelcomePage")
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._build_ui()

    # ── build ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_nav_bar())
        root.addWidget(self._make_hero())

        self._cards_area = self._make_cards_area()
        root.addWidget(self._cards_area, 1)

        self._pagination = self._make_pagination()
        root.addWidget(self._pagination)

        root.addWidget(WorkflowStrip(active_index=0))

    def _make_nav_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("WelcomeNavBar")
        bar.setFixedHeight(42)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        # App icon placeholder (colored square)
        icon_lbl = QLabel()
        icon_lbl.setObjectName("WelcomeAppIcon")
        icon_lbl.setFixedSize(20, 20)
        lay.addWidget(icon_lbl)

        name_lbl = QLabel("糯米 AI")
        name_lbl.setObjectName("WelcomeAppName")
        lay.addWidget(name_lbl)

        lay.addStretch(1)

        settings_btn = QPushButton("⚙  全局设置")
        settings_btn.setObjectName("WelcomeSettingsBtn")
        settings_btn.setFixedHeight(26)
        settings_btn.clicked.connect(self.settings_requested)
        lay.addWidget(settings_btn)

        return bar

    def _make_hero(self) -> QWidget:
        hero = QWidget()
        hero.setObjectName("WelcomeHero")
        lay = QVBoxLayout(hero)
        lay.setContentsMargins(0, 24, 0, 16)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)

        title = QLabel("糯米AI分镜影视创作台")
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        subtitle = QLabel("剧本 · 分镜 · 视频 · 后期配音配乐")
        subtitle.setObjectName("WelcomeSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        lay.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setAlignment(Qt.AlignCenter)

        self._btn_new = QPushButton("＋  新建项目")
        self._btn_new.setObjectName("WelcomeBtnPrimary")
        self._btn_new.setFixedHeight(36)
        self._btn_new.clicked.connect(self.new_project_requested)
        btn_row.addWidget(self._btn_new)

        self._btn_open = QPushButton("打开目录")
        self._btn_open.setObjectName("WelcomeBtnSecondary")
        self._btn_open.setFixedHeight(36)
        self._btn_open.clicked.connect(self.open_dir_requested)
        btn_row.addWidget(self._btn_open)

        lay.addLayout(btn_row)
        return hero

    def _make_cards_area(self) -> QWidget:
        w = QWidget()
        w.setObjectName("WelcomeCardsArea")
        self._cards_layout = QHBoxLayout(w)
        self._cards_layout.setContentsMargins(24, 0, 24, 0)
        self._cards_layout.setSpacing(12)
        return w

    def _make_pagination(self) -> QWidget:
        w = QWidget()
        w.setObjectName("WelcomePagination")
        w.setFixedHeight(18)
        self._page_layout = QHBoxLayout(w)
        self._page_layout.setContentsMargins(0, 4, 0, 4)
        self._page_layout.setSpacing(5)
        self._page_layout.setAlignment(Qt.AlignCenter)
        return w

    # ── public API ───────────────────────────────────────────────────────

    def refresh(self) -> None:
        """从 RecentProjectsManager 重新加载最近项目并重建卡片区。"""
        projects = self._mgr.load()
        self._rebuild_cards(projects)
        self._rebuild_pagination(projects)

    # ── private ──────────────────────────────────────────────────────────

    def _rebuild_cards(self, projects: list[dict]) -> None:
        # 清空旧卡片
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not projects:
            empty = QLabel("创建你的第一个项目")
            empty.setObjectName("WelcomeEmptyHint")
            empty.setAlignment(Qt.AlignCenter)
            self._cards_layout.addWidget(empty)
            add_card = ProjectCard(None, depth="add", is_add_button=True)
            add_card.clicked.connect(lambda _: self.new_project_requested.emit())
            self._cards_layout.addWidget(add_card, 1)
            return

        # 最多取 _MAX_CARDS 张
        show = projects[:_MAX_CARDS]
        # 根据数量选深度序列
        if len(show) == 1:
            depths = ["center"]
        elif len(show) == 2:
            depths = ["near", "center"]
        elif len(show) == 3:
            depths = ["far", "near", "center"]
        else:
            depths = ["far", "near", "center", "near"]

        stretch_map = {"far": 65, "near": 85, "center": 140}

        for i, (proj, depth) in enumerate(zip(show, depths)):
            card = ProjectCard(proj, depth=depth, color_index=i)
            card.clicked.connect(self._on_card_clicked)
            self._cards_layout.addWidget(card, stretch_map.get(depth, 85))

        add_card = ProjectCard(None, depth="add", is_add_button=True)
        add_card.clicked.connect(lambda _: self.new_project_requested.emit())
        self._cards_layout.addWidget(add_card, 50)

    def _rebuild_pagination(self, projects: list[dict]) -> None:
        while self._page_layout.count():
            item = self._page_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        count = min(len(projects), _MAX_CARDS)
        if count == 0:
            return
        for i in range(count):
            dot = QLabel()
            dot.setObjectName("PageDotActive" if i == 0 else "PageDot")
            dot.setFixedSize(16 if i == 0 else 6, 6)
            self._page_layout.addWidget(dot)

    def _on_card_clicked(self, path: str) -> None:
        if path:
            self.project_selected.emit(path)
        else:
            self.new_project_requested.emit()

    # ── background painting ──────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background gradient
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, QColor("#0d1020"))
        bg.setColorAt(0.45, QColor("#08090f"))
        bg.setColorAt(1.0, QColor("#100820"))
        p.fillRect(self.rect(), QBrush(bg))

        # Top blue glow
        top_glow = QRadialGradient(w / 2, 0, w * 0.45)
        top_glow.setColorAt(0.0, QColor(74, 158, 255, 35))
        top_glow.setColorAt(0.5, QColor(160, 108, 255, 12))
        top_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRect(int(w * 0.05), -80, int(w * 0.9), 280), QBrush(top_glow))

        # Bottom-left purple glow
        bl_glow = QRadialGradient(int(w * 0.2), h - 40, int(w * 0.25))
        bl_glow.setColorAt(0.0, QColor(160, 108, 255, 20))
        bl_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRect(0, int(h * 0.55), int(w * 0.5), int(h * 0.5)), QBrush(bl_glow))

        # Bottom-right blue glow
        br_glow = QRadialGradient(int(w * 0.85), h - 20, int(w * 0.2))
        br_glow.setColorAt(0.0, QColor(74, 158, 255, 15))
        br_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRect(int(w * 0.6), int(h * 0.6), int(w * 0.45), int(h * 0.45)),
                   QBrush(br_glow))
        p.end()
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/test_ui/test_welcome_page.py::test_welcome_page_instantiates \
                 tests/test_ui/test_welcome_page.py::test_welcome_page_has_required_signals -v
```
预期: 全部 `PASSED`

- [ ] **Step 5: 提交**

```bash
git add drama_shot_master/ui/pages/welcome_page.py
git commit -m "feat(welcome): WelcomePage — 骨架、背景渐变光晕、卡片区布局"
```

---

## Task 5: WelcomePage QSS + refresh 功能测试

**Files:**
- Modify: `drama_shot_master/ui/styles/tokens_dark.py` — 追加欢迎页 token
- Modify: `drama_shot_master/ui/styles/theme.qss.tpl` — 追加欢迎页 QSS

- [ ] **Step 1: 写 refresh 功能测试**

在 `tests/test_ui/test_welcome_page.py` 末尾追加：

```python
def test_welcome_page_refresh_shows_empty_state(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    page = WelcomePage(mgr)
    page.refresh()
    # empty state: 至少有 1 个 widget（empty hint label 或 add card）
    assert page._cards_layout.count() >= 1


def test_welcome_page_refresh_shows_projects(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    mgr = RecentProjectsManager(tmp_path / "r.json")
    mgr.push(str(tmp_path), "TestProj")
    page = WelcomePage(mgr)
    page.refresh()
    # 至少有 1 张 ProjectCard + 1 张 add 卡
    assert page._cards_layout.count() >= 2


def test_welcome_page_project_selected_signal(tmp_path):
    _app()
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    from drama_shot_master.ui.pages.welcome_page import WelcomePage
    from drama_shot_master.ui.widgets.project_card import ProjectCard
    mgr = RecentProjectsManager(tmp_path / "r.json")
    mgr.push(str(tmp_path), "TestProj")
    page = WelcomePage(mgr)
    page.refresh()

    got = []
    page.project_selected.connect(got.append)

    # 找到第一张非 add ProjectCard 并触发 click
    for i in range(page._cards_layout.count()):
        w = page._cards_layout.itemAt(i).widget()
        if isinstance(w, ProjectCard) and not w._is_add:
            w.clicked.emit(str(tmp_path))
            break

    assert got == [str(tmp_path)]
```

- [ ] **Step 2: 运行确认通过（refresh 逻辑已在 Task 4 实现）**

```bash
python -m pytest tests/test_ui/test_welcome_page.py -v
```
预期: 全部 `PASSED`

- [ ] **Step 3: 追加欢迎页 token 到 tokens_dark.py**

在 `drama_shot_master/ui/styles/tokens_dark.py` 的 `DARK` 字典末尾追加：

```python
    # 欢迎首页专属
    "welcome_nav_bg":        "rgba(13,16,32,0.95)",
    "welcome_nav_border":    "#1e1e3a",
    "welcome_app_name_fg":   "#d0d8f0",
    "welcome_title_fg":      "#e8eaed",
    "welcome_subtitle_fg":   "#5a6a8a",
    "welcome_btn_secondary_border": "#2a2a4a",
    "welcome_btn_secondary_fg":     "#9aa0a6",
    "welcome_btn_secondary_bg":     "rgba(19,19,42,0.6)",
    "welcome_page_dot":      "#1e1e3a",
    "welcome_page_dot_active": "#4a9eff",
```

- [ ] **Step 4: 追加欢迎页 QSS 到 theme.qss.tpl**

在 `drama_shot_master/ui/styles/theme.qss.tpl` 末尾追加：

```css
/* ═══════════════════════════════════════════════════
   欢迎首页
   ═══════════════════════════════════════════════════ */

#WelcomeNavBar {{
    background: {welcome_nav_bg};
    border-bottom: 1px solid {welcome_nav_border};
}}

#WelcomeAppIcon {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {accent}, stop:1 #a06cff);
    border-radius: 5px;
}}

#WelcomeAppName {{
    color: {welcome_app_name_fg};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
}}

#WelcomeSettingsBtn {{
    color: {fg_muted};
    background: rgba(26,26,50,0.8);
    border: 1px solid {welcome_btn_secondary_border};
    border-radius: 5px;
    padding: 0 10px;
    font-size: 11px;
}}
#WelcomeSettingsBtn:hover {{ background: {bg_elevated}; }}

#WelcomeTitle {{
    color: {welcome_title_fg};
    font-size: 28px;
    font-weight: 900;
    letter-spacing: 1px;
}}

#WelcomeSubtitle {{
    color: {welcome_subtitle_fg};
    font-size: 12px;
    letter-spacing: 3px;
    text-transform: uppercase;
}}

#WelcomeBtnPrimary {{
    color: white;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {accent}, stop:1 #a06cff);
    border: none;
    border-radius: 18px;
    padding: 0 28px;
    font-size: 13px;
    font-weight: 700;
}}
#WelcomeBtnPrimary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #6ab0ff, stop:1 #b07fff); }}
#WelcomeBtnPrimary:pressed {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #3a8adf, stop:1 #8a5ccf); }}

#WelcomeBtnSecondary {{
    color: {welcome_btn_secondary_fg};
    background: {welcome_btn_secondary_bg};
    border: 1px solid {welcome_btn_secondary_border};
    border-radius: 18px;
    padding: 0 20px;
    font-size: 13px;
}}
#WelcomeBtnSecondary:hover {{ background: rgba(30,30,60,0.8); }}

#WelcomeEmptyHint {{
    color: {fg_muted};
    font-size: 14px;
}}

#PageDot {{
    background: {welcome_page_dot};
    border-radius: 3px;
}}

#PageDotActive {{
    background: {welcome_page_dot_active};
    border-radius: 3px;
}}
```

- [ ] **Step 5: 运行全部测试确认未破坏已有测试**

```bash
python -m pytest tests/test_ui/ -v --tb=short
```
预期: 全部 `PASSED`（新增 + 已有）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/styles/tokens_dark.py \
        drama_shot_master/ui/styles/theme.qss.tpl \
        tests/test_ui/test_welcome_page.py
git commit -m "feat(welcome): WelcomePage QSS token + refresh 逻辑测试"
```

---

## Task 6: AppShell — 集成 WelcomePage（outer_stack）

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`
- Modify: `drama_shot_master/main.py`

- [ ] **Step 1: 修改 main.py — 更新应用名**

在 `drama_shot_master/main.py` 的 `main()` 函数中，将：
```python
    app.setApplicationName("Drama-Shot-Master")
```
改为：
```python
    app.setApplicationName("糯米AI分镜影视创作台")
```

- [ ] **Step 2: 修改 AppShell._build_pages — 创建 RecentProjectsManager**

在 `drama_shot_master/ui/app_shell.py` 的 `_build_pages` 方法中，在 `self.cfg = ...` 行之后追加：

```python
        from drama_shot_master.core.recent_projects import RecentProjectsManager
        from pathlib import Path
        settings_path = self.cfg.settings_path if self.cfg.settings_path else Path("settings.json")
        self.recent_mgr = RecentProjectsManager.alongside_settings(Path(settings_path))
```

- [ ] **Step 3: 修改 AppShell._build_ui — 包裹 outer_stack**

将现有 `_build_ui` 方法中从 `body = QHBoxLayout()` 到 `self.setCentralWidget(central)` 的部分替换为：

```python
    def _build_ui(self):
        from drama_shot_master.ui.pages.welcome_page import WelcomePage
        from PySide6.QtWidgets import QStackedWidget as _QSW

        self.command_bar = ProjectCommandBar()
        self.sidebar = FlowSidebar()
        self.stack = QStackedWidget()
        for _label, key in FUNCS:
            self.stack.addWidget(self.pages[key])

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        body_w = QWidget()
        body_w.setLayout(body)

        main_ui = QWidget()
        root = QVBoxLayout(main_ui)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.command_bar)
        root.addWidget(body_w, 1)

        # outer_stack: 0=欢迎页，1=主界面
        self.welcome_page = WelcomePage(self.recent_mgr)
        self.outer_stack = _QSW()
        self.outer_stack.addWidget(self.welcome_page)   # index 0
        self.outer_stack.addWidget(main_ui)             # index 1
        self.setCentralWidget(self.outer_stack)

        # 任务中心 dock（保持不变）
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
        self.task_center_dock.visibilityChanged.connect(self._persist_dock_visibility)
```

- [ ] **Step 4: 修改 AppShell._wire — 连接欢迎页信号**

在 `_wire` 方法末尾（`self.command_bar.taskCenterToggled.connect(...)` 之后）追加：

```python
        # 欢迎页信号连接
        self.welcome_page.project_selected.connect(self._on_welcome_project_selected)
        self.welcome_page.new_project_requested.connect(self._on_welcome_new_project)
        self.welcome_page.open_dir_requested.connect(self._open_dir)
        self.welcome_page.settings_requested.connect(self._open_unified_settings)
```

- [ ] **Step 5: 追加 AppShell 欢迎页相关方法**

在 `AppShell` 类中追加以下方法（在 `_on_nav_changed` 之前）：

```python
    def show_welcome(self) -> None:
        """切换到欢迎首页（从主界面返回时调用）。"""
        self.welcome_page.refresh()
        self.outer_stack.setCurrentIndex(0)

    def _on_welcome_project_selected(self, path: str) -> None:
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            self.welcome_page.refresh()   # 目录已消失，刷新列表
            return
        self._enter_main_ui()
        # 用现有 _open_dir 逻辑加载目录（需先传路径）
        self._open_dir_path(p)

    def _on_welcome_new_project(self) -> None:
        self._enter_main_ui()
        self._open_dir()   # 弹出目录选择对话框

    def _enter_main_ui(self) -> None:
        """直接切换（无动画），Task 7 会加上动画。"""
        self.outer_stack.setCurrentIndex(1)

    def _open_dir_path(self, path) -> None:
        """加载指定目录（复用 _open_dir 的实际加载逻辑）。"""
        from pathlib import Path
        from drama_shot_master.ui.state import load_images
        p = Path(path)
        self.state.current_dir = p
        self.state.images = load_images(p)
        self.state.selected.clear()
        self.command_bar.set_dir(str(p))
        self._populate_batch_pages()
        self._refresh_counts()
        self.recent_mgr.push(str(p))
```

- [ ] **Step 6: 修改 AppShell._restore_state — 启动时停在欢迎页**

在 `_restore_state` 的最末一行（`self.switchTo(self.pages[key])`）之后追加：

```python
        # 启动时始终先显示欢迎页
        self.welcome_page.refresh()
        self.outer_stack.setCurrentIndex(0)
```

- [ ] **Step 7: 设置窗口标题**

在 `AppShell.__init__` 中将：
```python
        self.setWindowTitle("Drama-Shot-Master")
```
改为：
```python
        self.setWindowTitle("糯米AI分镜影视创作台")
```

- [ ] **Step 8: 烟雾测试（启动不报错）**

```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master
python -c "
import os; os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
app = QApplication([])
from drama_shot_master.ui.app_shell import AppShell
shell = AppShell()
assert shell.outer_stack.currentIndex() == 0, 'should start at welcome page'
assert shell.windowTitle() == '糯米AI分镜影视创作台'
print('AppShell integration OK')
"
```
预期: `AppShell integration OK`

- [ ] **Step 9: 提交**

```bash
git add drama_shot_master/ui/app_shell.py drama_shot_master/main.py
git commit -m "feat(welcome): AppShell 集成欢迎首页 outer_stack，启动落在欢迎页"
```

---

## Task 7: 过渡动画 — WelcomePage fade-out + 侧边栏 slide-in

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: 将 `_enter_main_ui` 替换为带动画版本**

找到 Task 6 Step 5 中追加的 `_enter_main_ui` 方法，替换为：

```python
    def _enter_main_ui(self) -> None:
        """欢迎页 fade-out（250ms）→ 主界面出现 + 侧边栏 slide-in（300ms）。"""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QAbstractAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        effect = QGraphicsOpacityEffect(self.welcome_page)
        effect.setOpacity(1.0)
        self.welcome_page.setGraphicsEffect(effect)

        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(250)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.InQuad)
        fade.finished.connect(self._finish_enter_main_ui)
        fade.start(QAbstractAnimation.DeleteWhenStopped)
        self._fade_anim = fade   # 持有引用防止被 GC

    def _finish_enter_main_ui(self) -> None:
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QAbstractAnimation
        from drama_shot_master.ui.widgets.flow_sidebar import EXPANDED_W

        self.welcome_page.setGraphicsEffect(None)
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(0)
        self.outer_stack.setCurrentIndex(1)

        slide = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        slide.setDuration(300)
        slide.setStartValue(0)
        slide.setEndValue(EXPANDED_W)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        slide.finished.connect(
            lambda: self.sidebar.setMinimumWidth(EXPANDED_W))
        slide.start(QAbstractAnimation.DeleteWhenStopped)
        self._slide_anim = slide
```

- [ ] **Step 2: 烟雾测试（动画不崩溃）**

```bash
python -c "
import os; os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
app = QApplication([])
from drama_shot_master.ui.app_shell import AppShell
shell = AppShell()
shell.show()
# 直接调 _finish_enter_main_ui（跳过动画，测切换逻辑）
shell._finish_enter_main_ui()
assert shell.outer_stack.currentIndex() == 1, 'should be on main UI'
print('Transition OK')
"
```
预期: `Transition OK`

- [ ] **Step 3: 提交**

```bash
git add drama_shot_master/ui/app_shell.py
git commit -m "feat(welcome): 欢迎页 fade-out + 侧边栏 slide-in 过渡动画"
```

---

## Task 8: FlowSidebar — 首页按钮

**Files:**
- Modify: `drama_shot_master/ui/widgets/flow_sidebar.py`

- [ ] **Step 1: 追加 homeRequested 信号与 Home 按钮**

在 `flow_sidebar.py` 中：

1. 在 `class FlowSidebar(QWidget):` 的信号声明处追加：
```python
    homeRequested = Signal()
```

2. 在 `_build` 方法中，在 `lay.addWidget(self.btn_collapse)` 之后立即追加：
```python
        self.btn_home = self._make_item("首页", "home.svg")
        self.btn_home.clicked.connect(self.homeRequested)
        lay.addWidget(self.btn_home)
```

3. 在 `_menu_buttons` 方法中，将返回值改为：
```python
        return [self.btn_home, self.btn_settings, self.btn_help]
```

> **注意：** `home.svg` 需要添加到 `drama_shot_master/assets/icons/`（见 Step 2）。若图标文件缺失，`_make_item` 会静默跳过（现有逻辑 `if p is not None: btn.setIcon(...)`），按钮仍可正常工作。

- [ ] **Step 2: 添加 home.svg 图标**

```bash
cat > /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-drama-master/drama_shot_master/assets/icons/home.svg << 'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
  <polyline points="9 22 9 12 15 12 15 22"/>
</svg>
EOF
```

- [ ] **Step 3: 连接 AppShell — homeRequested → show_welcome**

在 `drama_shot_master/ui/app_shell.py` 的 `_wire` 方法末尾追加：

```python
        self.sidebar.homeRequested.connect(self.show_welcome)
```

- [ ] **Step 4: 更新 FlowSidebar 测试（确认 homeRequested 存在）**

在 `tests/test_ui/test_nav_config.py` 末尾追加（或在 `tests/test_ui/` 目录下独立文件均可）：

```python
def test_flow_sidebar_has_home_requested_signal():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
    sidebar = FlowSidebar()
    assert hasattr(sidebar, "homeRequested")
    assert hasattr(sidebar, "btn_home")
```

- [ ] **Step 5: 运行**

```bash
python -m pytest tests/test_ui/test_nav_config.py -v
```
预期: 全部 `PASSED`

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/ui/widgets/flow_sidebar.py \
        drama_shot_master/assets/icons/home.svg \
        drama_shot_master/ui/app_shell.py \
        tests/test_ui/test_nav_config.py
git commit -m "feat(welcome): FlowSidebar 首页按钮 + homeRequested 信号"
```

---

## Task 9: 收尾接线 — recent_mgr push + 全量回归

**Files:**
- Modify: `drama_shot_master/ui/app_shell.py`

- [ ] **Step 1: _open_dir 打开目录后写入 recent_mgr**

在 `app_shell.py` 中找到 `_open_dir` 方法，在其成功加载目录后（`self.state.current_dir = p` 或等效赋值之后）追加：

```python
        self.recent_mgr.push(str(p))
```

> 同时确认 `_open_dir_path`（Task 6 Step 5 中追加）也调用了 `self.recent_mgr.push(str(p))`（已包含在那步代码里）。

- [ ] **Step 2: show_welcome 刷新列表（含返回主界面 slide-out）**

将 `show_welcome` 方法替换为：

```python
    def show_welcome(self) -> None:
        """从主界面返回欢迎首页（无动画，即时切换）。"""
        self.welcome_page.refresh()
        # 恢复侧边栏正常宽度（可能被动画修改）
        from drama_shot_master.ui.widgets.flow_sidebar import EXPANDED_W
        self.sidebar.setMinimumWidth(EXPANDED_W)
        self.sidebar.setMaximumWidth(EXPANDED_W)
        self.outer_stack.setCurrentIndex(0)
```

- [ ] **Step 3: 运行全量回归测试**

```bash
python -m pytest tests/ -v --tb=short -q
```
预期: 全部 `PASSED`，无 `ERROR`

- [ ] **Step 4: 最终提交**

```bash
git add drama_shot_master/ui/app_shell.py
git commit -m "feat(welcome): 收尾接线 — recent_mgr push + show_welcome 侧边栏复位"
```

---

## 自我审查

### Spec 覆盖检查

| Spec 节 | 覆盖任务 |
|---------|---------|
| 全画布（无侧边栏）启动 | Task 6 outer_stack index 0 |
| 深蓝紫背景 + 光晕 | Task 4 paintEvent |
| 顶部导航栏（Logo + 名称 + 设置按钮） | Task 4 _make_nav_bar |
| Hero 主标题 + 副标题 + 双 CTA | Task 4 _make_hero |
| 卡片景深系统（far/near/center/add） | Task 3 ProjectCard + Task 4 _rebuild_cards |
| 分页圆点（首期仅装饰） | Task 4 _rebuild_pagination |
| 底部工作流条 | Task 2 WorkflowStrip |
| 进入功能页面动画 | Task 7 |
| 侧边栏首页按钮 | Task 8 |
| RecentProjectsManager（最多 8 条） | Task 1 |
| push when _open_dir | Task 9 |
| 空状态引导 | Task 4 _rebuild_cards empty branch |
| 应用名改为糯米AI分镜影视创作台 | Task 6 Step 1 + Step 7 |

### 类型/方法一致性检查

- `RecentProjectsManager.alongside_settings(Path)` — Task 1 定义，Task 6 调用 ✓
- `WelcomePage(recent_mgr)` — Task 4 定义，Task 6 调用 ✓
- `WelcomePage.refresh()` — Task 4 定义，Task 6/9 调用 ✓
- `FlowSidebar.homeRequested` Signal — Task 8 定义，Task 8 Step 3 连接 ✓
- `EXPANDED_W` — flow_sidebar.py 既有常量，Task 7/9 import ✓
- `_enter_main_ui` — Task 6 定义（直接切换版），Task 7 替换为动画版 ✓

### Placeholder 扫描：无 TBD / TODO / 模糊步骤
