# 图像操作界面重构 (v0.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 v0.2 的 6 个独立 Tab 重构为「左目录 / 中共享缩略图 / 右功能切换+参数」的统一三栏桌面布局，加目录记忆，加拼图徽章选择、拆图红线 overlay 预览、白边/网格一键检测。

**Architecture:** 一个全局 `AppState` 持有目录/缩略图缓存/选择/输出目录，4 个功能（反推/拆/拼/裁）共享。右栏用 `QStackedWidget` 装 4 个 `BasePanel` 子类。中栏 `ThumbnailGrid` 用自绘 `ThumbnailDelegate` 画徽章。拆图 overlay 红线坐标用纯函数 `compute_grid_lines()` 计算（可单测）。core/providers/grid_ops 完全不动，只重写 `app/ui/` + `app/config.py` 加 2 字段。

**Tech Stack:** PySide6, Pillow, shot_master.core（loader/border_detector/specs，import 复用），pytest（纯逻辑层）。

**Spec:** `docs/superpowers/specs/2026-05-16-image-ops-redesign.md`

**测试环境注意：** dev 环境（finchat）无 PySide6。纯逻辑文件（config / state / overlay 几何）用 `/root/miniconda3/envs/finchat/bin/python3 -m pytest` 真跑；UI 文件（含 `from PySide6 ...` import）只做 `python -m py_compile` 语法检查，运行验证留给用户手动 smoke。

---

## 文件结构

```
新建:
  app/ui/state.py                    # AppState dataclass + 目录记忆 helper
  app/ui/geometry.py                 # compute_grid_lines() 纯函数（overlay 红线）
  app/ui/thumbnail_delegate.py       # 徽章绘制 QStyledItemDelegate
  app/ui/thumbnail_grid.py           # 中栏缩略图（重写，替代 widgets/thumbnail_list.py）
  app/ui/preview_dialog.py           # 大图 + overlay
  app/ui/panels/__init__.py
  app/ui/panels/base_panel.py        # 抽象基类
  app/ui/panels/split_panel.py
  app/ui/panels/combine_panel.py
  app/ui/panels/trim_panel.py
  app/ui/panels/inference_panel.py
  tests/test_state.py
  tests/test_geometry.py

修改:
  app/config.py                      # +last_input_dir/+last_output_dir 字段+持久化+读取
  app/ui/main_window.py              # 整体重写为三栏
  tests/test_config.py               # +目录记忆字段断言

删除:
  app/ui/tabs/                       # 6 个旧 tab 文件 + __init__.py
  app/ui/widgets/thumbnail_list.py   # 被 thumbnail_grid.py 取代

保留不动:
  app/grid_ops.py / app/core/ / app/providers/ / app/main.py
  app/ui/worker.py                   # FunctionWorker/BatchWorker
  app/ui/widgets/template_form.py    # 反推面板复用
```

---

## Task 1: config.py 加目录记忆字段

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: 在 tests/test_config.py 末尾追加测试**

```python
def test_last_dirs_default_none(tmp_path):
    cfg = load_config(env_path=tmp_path / "no.env",
                      settings_path=tmp_path / "s.json")
    assert cfg.last_input_dir is None
    assert cfg.last_output_dir is None


def test_last_dirs_loaded_from_settings(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    import json as _j
    sj.write_text(_j.dumps({
        "current_provider": "doubao",
        "current_model": "doubao-seed-2-0-pro-260215",
        "last_input_dir": "/data/imgs",
        "last_output_dir": "/data/out",
    }))
    cfg = load_config(env_path=env_file, settings_path=sj)
    assert cfg.last_input_dir == "/data/imgs"
    assert cfg.last_output_dir == "/data/out"


def test_update_settings_persists_last_dirs(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env_file, settings_path=sj)
    cfg.update_settings(last_input_dir="/x/in", last_output_dir="/x/out")
    import json as _j
    data = _j.loads(sj.read_text())
    assert data["last_input_dir"] == "/x/in"
    assert data["last_output_dir"] == "/x/out"
    # 重新加载应保留
    cfg2 = load_config(env_path=env_file, settings_path=sj)
    assert cfg2.last_input_dir == "/x/in"
    assert cfg2.last_output_dir == "/x/out"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m pytest tests/test_config.py -v`
Expected: 3 个新测试 FAIL（`AttributeError: 'Config' object has no attribute 'last_input_dir'`）

- [ ] **Step 3: 改 app/config.py 的 Config dataclass**

在 `ui: dict = field(...)` 这一行**之后**、`def update_settings` 之前，插入两个字段：

```python
    ui: dict = field(default_factory=lambda: {"theme": "light", "preview_thumb_size": 200})
    last_input_dir: Optional[str] = None
    last_output_dir: Optional[str] = None
```

- [ ] **Step 4: 改 update_settings 的持久化 data 字典**

把 `update_settings` 里的 `data = {...}` 改为：

```python
        if self.settings_path:
            data = {
                "current_provider": self.current_provider,
                "current_model": self.current_model,
                "ui": self.ui,
                "last_input_dir": self.last_input_dir,
                "last_output_dir": self.last_output_dir,
            }
            self.settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
```

- [ ] **Step 5: 改 load_config 读取 settings.json 的块**

在 `load_config` 里 `if "ui" in data and isinstance(data["ui"], dict):` 那段**之后**追加：

```python
                if "last_input_dir" in data:
                    cfg.last_input_dir = data["last_input_dir"]
                if "last_output_dir" in data:
                    cfg.last_output_dir = data["last_output_dir"]
```

- [ ] **Step 6: 跑测试确认全过**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m pytest tests/test_config.py -v`
Expected: 全部 PASS（含原有 + 3 新）

- [ ] **Step 7: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): persist last_input_dir/last_output_dir for directory memory"
```

---

## Task 2: app/ui/state.py — 全局 AppState + 目录记忆 helper

**Files:**
- Create: `app/ui/state.py`
- Create: `tests/test_state.py`

> 复用 `shot_master.core.loader.load_directory` 和 `ImageInfo`（spec 第 2.2 节：core 算法 import 复用，不重定义）。

- [ ] **Step 1: 写 tests/test_state.py**

```python
from pathlib import Path
from PIL import Image
import pytest
from app.config import load_config
from app.ui.state import AppState, restore_from_config, remember_dirs


def _mk_imgs(folder: Path, n=3):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (40, 40), (i * 40 % 256, 100, 100)).save(folder / f"i{i}.png")


def test_appstate_defaults():
    s = AppState()
    assert s.current_dir is None
    assert s.images == []
    assert s.selected == []
    assert s.output_dir is None
    assert s.active_function == "inference"


def test_load_dir_populates_images(tmp_path):
    folder = tmp_path / "imgs"
    _mk_imgs(folder, 3)
    s = AppState()
    s.load_dir(folder)
    assert s.current_dir == folder
    assert len(s.images) == 3
    assert all(info.path.suffix == ".png" for info in s.images)


def test_load_missing_dir_clears(tmp_path):
    s = AppState()
    s.load_dir(tmp_path / "nope")   # 不存在
    assert s.current_dir is None
    assert s.images == []


def test_restore_from_config_existing(tmp_path):
    folder = tmp_path / "imgs"
    _mk_imgs(folder, 2)
    out = tmp_path / "out"
    out.mkdir()
    env = tmp_path / ".env"; env.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env, settings_path=sj)
    cfg.update_settings(last_input_dir=str(folder), last_output_dir=str(out))
    s = AppState()
    restore_from_config(s, cfg)
    assert s.current_dir == folder
    assert len(s.images) == 2
    assert s.output_dir == out


def test_restore_from_config_stale_path_ignored(tmp_path):
    env = tmp_path / ".env"; env.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env, settings_path=sj)
    cfg.update_settings(last_input_dir=str(tmp_path / "gone"),
                        last_output_dir=str(tmp_path / "gone_out"))
    s = AppState()
    restore_from_config(s, cfg)   # 路径不存在 → 静默
    assert s.current_dir is None
    assert s.images == []
    assert s.output_dir is None


def test_remember_dirs_writes_config(tmp_path):
    folder = tmp_path / "imgs"; _mk_imgs(folder, 1)
    out = tmp_path / "out"; out.mkdir()
    env = tmp_path / ".env"; env.write_text("DEFAULT_PROVIDER=doubao\n")
    sj = tmp_path / "s.json"
    cfg = load_config(env_path=env, settings_path=sj)
    s = AppState()
    s.current_dir = folder
    s.output_dir = out
    remember_dirs(s, cfg)
    import json as _j
    data = _j.loads(sj.read_text())
    assert data["last_input_dir"] == str(folder)
    assert data["last_output_dir"] == str(out)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m pytest tests/test_state.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ui.state'`）

- [ ] **Step 3: 写 app/ui/state.py**

```python
"""全局 UI 状态 + 目录记忆。

不依赖 PySide6（纯数据 + shot-master core），可单测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shot_master.core.loader import load_directory, ImageInfo

from app.config import Config


@dataclass
class AppState:
    current_dir: Optional[Path] = None
    images: list[ImageInfo] = field(default_factory=list)
    selected: list[int] = field(default_factory=list)  # 含点击顺序
    output_dir: Optional[Path] = None
    active_function: str = "inference"  # inference|split|combine|trim

    def load_dir(self, directory: Path) -> None:
        """加载目录图片。目录不存在则清空（静默）。"""
        directory = Path(directory)
        if not directory.is_dir():
            self.current_dir = None
            self.images = []
            self.selected = []
            return
        self.current_dir = directory
        self.images = load_directory(directory)
        self.selected = []

    def selected_paths(self) -> list[Path]:
        return [self.images[i].path for i in self.selected
                if 0 <= i < len(self.images)]


def restore_from_config(state: AppState, cfg: Config) -> None:
    """启动时按 cfg 的 last_input_dir/last_output_dir 回填。路径失效静默忽略。"""
    if cfg.last_input_dir:
        p = Path(cfg.last_input_dir)
        if p.is_dir():
            state.load_dir(p)
    if cfg.last_output_dir:
        p = Path(cfg.last_output_dir)
        if p.is_dir():
            state.output_dir = p


def remember_dirs(state: AppState, cfg: Config) -> None:
    """把当前目录/输出目录写回 settings.json。"""
    cfg.update_settings(
        last_input_dir=str(state.current_dir) if state.current_dir else None,
        last_output_dir=str(state.output_dir) if state.output_dir else None,
    )
```

- [ ] **Step 4: 跑测试确认全过**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m pytest tests/test_state.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/state.py tests/test_state.py
git commit -m "feat(ui): AppState global state + directory memory helpers"
```

---

## Task 3: app/ui/geometry.py — overlay 红线坐标纯函数

**Files:**
- Create: `app/ui/geometry.py`
- Create: `tests/test_geometry.py`

> 拆图 overlay 预览的红线坐标计算。纯函数，不依赖 Qt/PIL，可单测。数学逻辑参照 spec 第 5.3 节。

- [ ] **Step 1: 写 tests/test_geometry.py**

```python
import pytest
from app.ui.geometry import compute_grid_lines, GridLine


def test_simple_2x2_no_sub_no_margin():
    # 400x400 图，源 2x2，子 1x1，无 margin/gap，显示尺寸=原尺寸
    lines = compute_grid_lines(
        img_w=400, img_h=400,
        src_rows=2, src_cols=2, sub_rows=1, sub_cols=1,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
        gap=0, display_w=400, display_h=400,
    )
    # 源网格：1 条竖实线 x=200，1 条横实线 y=200
    solids = [l for l in lines if l.style == "solid"]
    assert any(l.orientation == "v" and abs(l.pos - 200) < 1 for l in solids)
    assert any(l.orientation == "h" and abs(l.pos - 200) < 1 for l in solids)


def test_scaled_display_halves_positions():
    lines = compute_grid_lines(
        img_w=400, img_h=400,
        src_rows=2, src_cols=2, sub_rows=1, sub_cols=1,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
        gap=0, display_w=200, display_h=200,   # 缩放 0.5
    )
    solids = [l for l in lines if l.style == "solid"]
    assert any(l.orientation == "v" and abs(l.pos - 100) < 1 for l in solids)


def test_margins_offset_grid():
    # 左 margin 20，源 1x1 → 没有内部源线；但 margin 区不算内容
    lines = compute_grid_lines(
        img_w=420, img_h=400,
        src_rows=1, src_cols=2, sub_rows=1, sub_cols=1,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=20,
        gap=0, display_w=420, display_h=400,
    )
    # 内容宽 = 420-20 = 400，2 列 → 内部竖线在 left_margin + 400/2 = 220
    solids = [l for l in lines if l.style == "solid" and l.orientation == "v"]
    assert any(abs(l.pos - 220) < 2 for l in solids)


def test_sub_grid_produces_dashed_lines():
    # 源 4x4，子 2x2 → 子分组虚线在每 2 格处
    lines = compute_grid_lines(
        img_w=400, img_h=400,
        src_rows=4, src_cols=4, sub_rows=2, sub_cols=2,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
        gap=0, display_w=400, display_h=400,
    )
    dashed = [l for l in lines if l.style == "dashed"]
    # 子 2x2 切 4x4 → 子分组边界竖线 1 条 (x=200)，横线 1 条 (y=200)
    assert any(l.orientation == "v" and abs(l.pos - 200) < 1 for l in dashed)
    assert any(l.orientation == "h" and abs(l.pos - 200) < 1 for l in dashed)


def test_tile_count_helper():
    from app.ui.geometry import tile_count
    assert tile_count(4, 4, 2, 2) == 4     # 4x4 切成 2x2 块 = 4 张
    assert tile_count(2, 2, 1, 1) == 4     # 2x2 切成 1x1 = 4 单图
    assert tile_count(1, 3, 1, 1) == 3


def test_invalid_grid_raises():
    with pytest.raises(ValueError):
        compute_grid_lines(
            img_w=400, img_h=400,
            src_rows=3, src_cols=3, sub_rows=2, sub_cols=2,  # 3 不整除 2
            margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
            gap=0, display_w=400, display_h=400,
        )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m pytest tests/test_geometry.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ui.geometry'`）

- [ ] **Step 3: 写 app/ui/geometry.py**

```python
"""拆图 overlay 红线坐标计算（纯函数，不依赖 Qt）。

坐标系：以显示图（display）左上为原点。
- 源网格线：solid（src_rows × src_cols 把内容区均分）
- 子分组线：dashed（每 sub_rows / sub_cols 个源格为一组的边界）
内容区 = 原图去掉四周 margin 后的区域；显示按 display/img 比例缩放。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GridLine:
    orientation: str  # "v" 竖线 | "h" 横线
    pos: float        # 显示坐标系下的 x（竖线）或 y（横线）
    style: str        # "solid" 源网格 | "dashed" 子分组


def tile_count(src_rows: int, src_cols: int,
               sub_rows: int, sub_cols: int) -> int:
    """切出的子图数量 = (src_rows/sub_rows) * (src_cols/sub_cols)。"""
    if src_rows % sub_rows != 0 or src_cols % sub_cols != 0:
        raise ValueError(
            f"子图 {sub_rows}×{sub_cols} 必须能整除源图 {src_rows}×{src_cols}")
    return (src_rows // sub_rows) * (src_cols // sub_cols)


def compute_grid_lines(img_w: int, img_h: int,
                       src_rows: int, src_cols: int,
                       sub_rows: int, sub_cols: int,
                       margin_top: int, margin_right: int,
                       margin_bottom: int, margin_left: int,
                       gap: int,
                       display_w: int, display_h: int) -> list[GridLine]:
    """返回所有红线（已换算到 display 坐标）。

    Raises:
        ValueError: 子网格不能整除源网格。
    """
    if src_rows % sub_rows != 0 or src_cols % sub_cols != 0:
        raise ValueError(
            f"子图 {sub_rows}×{sub_cols} 必须能整除源图 {src_rows}×{src_cols}")

    sx = display_w / img_w
    sy = display_h / img_h

    content_w = img_w - margin_left - margin_right
    content_h = img_h - margin_top - margin_bottom
    if content_w <= 0 or content_h <= 0:
        return []

    cell_w = content_w / src_cols
    cell_h = content_h / src_rows

    lines: list[GridLine] = []

    # 源网格内部竖线（i = 1..src_cols-1）
    for i in range(1, src_cols):
        x_img = margin_left + i * cell_w
        style = "dashed" if (i % sub_cols == 0) else "solid"
        lines.append(GridLine("v", x_img * sx, style))
    # 源网格内部横线
    for j in range(1, src_rows):
        y_img = margin_top + j * cell_h
        style = "dashed" if (j % sub_rows == 0) else "solid"
        lines.append(GridLine("h", y_img * sy, style))

    return lines
```

> 说明：当某条源网格线同时也是子分组边界（`i % sub_cols == 0`）时归为 dashed（子分组优先显示），其余为 solid。`gap` 当前不参与画线（splitter 走白带算法，gap 仅 UI 参考；spec 第 5.3 节）——保留参数位以备后续；测试不依赖 gap 效果。

- [ ] **Step 4: 跑测试确认全过**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m pytest tests/test_geometry.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/geometry.py tests/test_geometry.py
git commit -m "feat(ui): compute_grid_lines pure fn for split overlay preview"
```

---

## Task 4: app/ui/thumbnail_delegate.py — 徽章绘制 delegate

**Files:**
- Create: `app/ui/thumbnail_delegate.py`

> UI 文件，只做 `py_compile` 语法检查（dev 无 PySide6）。无 pytest。

- [ ] **Step 1: 写 app/ui/thumbnail_delegate.py**

```python
"""缩略图徽章 delegate：order 模式下左上角画蓝圈白色序号；multi 模式画蓝色描边。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QFont, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle


BADGE_ROLE = Qt.UserRole + 100      # int 序号，或 None
SELECTED_ROLE = Qt.UserRole + 101   # bool，multi 模式高亮


class ThumbnailDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        rect = option.rect

        selected = index.data(SELECTED_ROLE)
        if selected:
            painter.save()
            pen = QPen(QColor(79, 142, 220))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(2, 2, -2, -2))
            painter.restore()

        badge = index.data(BADGE_ROLE)
        if badge is not None:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            d = 24
            x = rect.left() + 6
            y = rect.top() + 6
            painter.setBrush(QColor(79, 142, 220))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(x, y, d, d)
            painter.setPen(Qt.white)
            f = QFont()
            f.setBold(True)
            f.setPointSize(10)
            painter.setFont(f)
            painter.drawText(QRectF(x, y, d, d), Qt.AlignCenter, str(badge))
            painter.restore()
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/thumbnail_delegate.py`
Expected: 无输出（成功）

- [ ] **Step 3: Commit**

```bash
git add app/ui/thumbnail_delegate.py
git commit -m "feat(ui): thumbnail badge delegate (order number + multi outline)"
```

---

## Task 5: app/ui/thumbnail_grid.py — 中栏缩略图（重写）

**Files:**
- Create: `app/ui/thumbnail_grid.py`

- [ ] **Step 1: 写 app/ui/thumbnail_grid.py**

```python
"""中栏共享缩略图网格。

两种选择模式（由外部 set_mode 切换）：
  - "multi": 点击切换选中，蓝色描边
  - "order": 点击累加序号徽章，再点取消并重排
双击发 previewRequested(int)。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton,
)

from shot_master.core.loader import ImageInfo
from app.ui.thumbnail_delegate import (
    ThumbnailDelegate, BADGE_ROLE, SELECTED_ROLE,
)


THUMB_MIN, THUMB_MAX, THUMB_DEFAULT = 80, 240, 140


class ThumbnailGrid(QWidget):
    selectionChanged = Signal(list)     # list[int]，order 模式按点击顺序
    previewRequested = Signal(int)
    thumbSizeChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "multi"
        self._order: list[int] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(8)
        self.list.setIconSize(QSize(THUMB_DEFAULT, THUMB_DEFAULT))
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setItemDelegate(ThumbnailDelegate(self.list))
        self.list.itemClicked.connect(self._on_clicked)
        self.list.itemDoubleClicked.connect(self._on_double)
        layout.addWidget(self.list, 1)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("缩略图大小:"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(THUMB_MIN)
        self.slider.setMaximum(THUMB_MAX)
        self.slider.setValue(THUMB_DEFAULT)
        self.slider.valueChanged.connect(self._on_size)
        bar.addWidget(self.slider, 1)
        clr = QPushButton("清空选择")
        clr.clicked.connect(self.clear_selection)
        bar.addWidget(clr)
        layout.addLayout(bar)

    def set_mode(self, mode: str):
        """'multi' 或 'order'。切换时清空当前选择。"""
        if mode not in ("multi", "order"):
            return
        self._mode = mode
        self.clear_selection()

    def set_thumb_size(self, size: int):
        size = max(THUMB_MIN, min(THUMB_MAX, size))
        self.slider.setValue(size)

    def populate(self, images: list[ImageInfo]):
        self.list.clear()
        self._order = []
        for info in images:
            pix = QPixmap(str(info.path))
            if pix.isNull():
                continue
            pix = pix.scaled(THUMB_MAX, THUMB_MAX,
                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
            it = QListWidgetItem(QIcon(pix), info.path.name)
            it.setData(BADGE_ROLE, None)
            it.setData(SELECTED_ROLE, False)
            sz = self.slider.value()
            it.setSizeHint(QSize(sz + 24, sz + 50))
            self.list.addItem(it)
        self.selectionChanged.emit([])

    def _on_clicked(self, item: QListWidgetItem):
        row = self.list.row(item)
        if self._mode == "multi":
            cur = bool(item.data(SELECTED_ROLE))
            item.setData(SELECTED_ROLE, not cur)
            if not cur:
                self._order.append(row)
            else:
                if row in self._order:
                    self._order.remove(row)
        else:  # order
            if row in self._order:
                self._order.remove(row)
            else:
                self._order.append(row)
            self._refresh_badges()
        self.list.viewport().update()
        self.selectionChanged.emit(list(self._order))

    def _refresh_badges(self):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if i in self._order:
                it.setData(BADGE_ROLE, self._order.index(i) + 1)
            else:
                it.setData(BADGE_ROLE, None)

    def _on_double(self, item: QListWidgetItem):
        self.previewRequested.emit(self.list.row(item))

    def _on_size(self, size: int):
        self.list.setIconSize(QSize(size, size))
        for i in range(self.list.count()):
            self.list.item(i).setSizeHint(QSize(size + 24, size + 50))
        self.thumbSizeChanged.emit(size)

    def clear_selection(self):
        self._order = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setData(BADGE_ROLE, None)
            it.setData(SELECTED_ROLE, False)
        self.list.viewport().update()
        self.selectionChanged.emit([])
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/thumbnail_grid.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add app/ui/thumbnail_grid.py
git commit -m "feat(ui): ThumbnailGrid with multi/order modes + size slider"
```

---

## Task 6: app/ui/preview_dialog.py — 大图 + overlay 红线

**Files:**
- Create: `app/ui/preview_dialog.py`

- [ ] **Step 1: 写 app/ui/preview_dialog.py**

```python
"""大图预览对话框。overlay=split spec 时叠加红线网格。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel

from app.ui.geometry import compute_grid_lines, tile_count


class PreviewDialog(QDialog):
    def __init__(self, image_path: Path,
                 overlay_spec: Optional[dict] = None,
                 parent=None):
        """overlay_spec: None=普通预览；dict 含
        src_rows/src_cols/sub_rows/sub_cols/margin_top/right/bottom/left/gap
        """
        super().__init__(parent)
        self.setWindowTitle(f"预览 · {image_path.name}")
        self.resize(900, 760)
        self._path = image_path
        self._spec = overlay_spec

        layout = QVBoxLayout(self)
        self.hint = QLabel("")
        self.hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.hint)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.canvas, 1)

        self._render()

    def _render(self):
        pix = QPixmap(str(self._path))
        if pix.isNull():
            self.hint.setText("无法加载图片")
            return
        max_w, max_h = 860, 680
        disp = pix.scaled(max_w, max_h, Qt.KeepAspectRatio,
                          Qt.SmoothTransformation)

        if not self._spec:
            self.hint.setText(f"{pix.width()} × {pix.height()}")
            self.canvas.setPixmap(disp)
            return

        s = self._spec
        try:
            n = tile_count(s["src_rows"], s["src_cols"],
                           s["sub_rows"], s["sub_cols"])
        except ValueError as e:
            self.hint.setText(f"⚠ {e}")
            self.hint.setStyleSheet("color:#c01b1b;font-weight:bold")
            self.canvas.setPixmap(disp)
            return
        self.hint.setStyleSheet("")
        self.hint.setText(
            f"源 {s['src_rows']}×{s['src_cols']} → "
            f"子 {s['sub_rows']}×{s['sub_cols']} = 将切出 {n} 张")

        lines = compute_grid_lines(
            img_w=pix.width(), img_h=pix.height(),
            src_rows=s["src_rows"], src_cols=s["src_cols"],
            sub_rows=s["sub_rows"], sub_cols=s["sub_cols"],
            margin_top=s["margin_top"], margin_right=s["margin_right"],
            margin_bottom=s["margin_bottom"], margin_left=s["margin_left"],
            gap=s["gap"],
            display_w=disp.width(), display_h=disp.height(),
        )
        canvas = QPixmap(disp)
        p = QPainter(canvas)
        for ln in lines:
            pen = QPen(QColor(220, 30, 30))
            if ln.style == "dashed":
                pen.setStyle(Qt.DashLine)
                pen.setWidth(1)
            else:
                pen.setWidth(2)
            p.setPen(pen)
            if ln.orientation == "v":
                p.drawLine(int(ln.pos), 0, int(ln.pos), canvas.height())
            else:
                p.drawLine(0, int(ln.pos), canvas.width(), int(ln.pos))
        p.end()
        self.canvas.setPixmap(canvas)
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/preview_dialog.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add app/ui/preview_dialog.py
git commit -m "feat(ui): PreviewDialog with optional split red-line overlay"
```

---

## Task 7: app/ui/panels/base_panel.py — 抽象基类

**Files:**
- Create: `app/ui/panels/__init__.py`（空文件）
- Create: `app/ui/panels/base_panel.py`

- [ ] **Step 1: 创建空 __init__.py**

```bash
touch app/ui/panels/__init__.py
```

- [ ] **Step 2: 写 app/ui/panels/base_panel.py**

```python
"""功能面板抽象基类。每个面板自带参数表单，向 MainWindow 暴露统一接口。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from app.config import Config
from app.ui.state import AppState


class BasePanel(QWidget):
    """子类必须实现 validate/execute/select_mode；可选 preview。"""
    statusMessage = Signal(str)        # 发到状态栏
    validityChanged = Signal()         # 参数变化 → MainWindow 重算执行按钮

    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(parent)
        self.state = state
        self.cfg = cfg

    def select_mode(self) -> str:
        """中栏选择模式：'multi' 或 'order'。"""
        return "multi"

    def validate(self) -> tuple[bool, str]:
        """返回 (可执行?, 原因)。原因在不可执行时显示。"""
        return False, "未实现"

    def execute(self) -> None:
        """执行操作。耗时操作子类自行起 QThread。"""
        raise NotImplementedError

    def preview(self) -> None:
        """可选预览。默认无。"""
        pass

    def has_preview(self) -> bool:
        return False
```

- [ ] **Step 3: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/panels/base_panel.py`
Expected: 无输出

- [ ] **Step 4: Commit**

```bash
git add app/ui/panels/__init__.py app/ui/panels/base_panel.py
git commit -m "feat(ui): BasePanel abstract interface for function panels"
```

---

## Task 8: app/ui/panels/split_panel.py

**Files:**
- Create: `app/ui/panels/split_panel.py`

- [ ] **Step 1: 写 app/ui/panels/split_panel.py**

```python
"""拆图面板：网格参数 + 白边/网格一键检测 + 批量拆。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QPushButton, QHBoxLayout, QMessageBox,
)

from shot_master.core.border_detector import detect_borders, infer_grid

from app.config import Config
from app.grid_ops import make_grid_spec, split_to_files
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.worker import FunctionWorker


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class SplitPanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        root = QVBoxLayout(self)

        grid = QGroupBox("网格")
        gf = QFormLayout(grid)
        self.src_rows = _spin(1, 50, 2)
        self.src_cols = _spin(1, 50, 2)
        self.sub_rows = _spin(1, 50, 1)
        self.sub_cols = _spin(1, 50, 1)
        for w in (self.src_rows, self.src_cols, self.sub_rows, self.sub_cols):
            w.valueChanged.connect(self.validityChanged)
        gf.addRow("源图 行", self.src_rows)
        gf.addRow("源图 列", self.src_cols)
        gf.addRow("子图 行", self.sub_rows)
        gf.addRow("子图 列", self.sub_cols)
        root.addWidget(grid)

        mar = QGroupBox("白边 / 间距")
        mf = QFormLayout(mar)
        self.m_top = _spin(0, 9999, 0)
        self.m_right = _spin(0, 9999, 0)
        self.m_bottom = _spin(0, 9999, 0)
        self.m_left = _spin(0, 9999, 0)
        self.gap = _spin(0, 9999, 0)
        mf.addRow("上", self.m_top)
        mf.addRow("右", self.m_right)
        mf.addRow("下", self.m_bottom)
        mf.addRow("左", self.m_left)
        mf.addRow("间距", self.gap)
        det_row = QHBoxLayout()
        btn_border = QPushButton("检测白边")
        btn_border.clicked.connect(self._detect_borders)
        btn_grid = QPushButton("推断网格")
        btn_grid.clicked.connect(self._infer_grid)
        det_row.addWidget(btn_border)
        det_row.addWidget(btn_grid)
        mf.addRow(det_row)
        root.addWidget(mar)

        out = QGroupBox("输出")
        of = QFormLayout(out)
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        of.addRow("格式", self.fmt)
        root.addWidget(out)
        root.addStretch(1)

    def select_mode(self) -> str:
        return "multi"

    def _first_selected_image(self) -> Path | None:
        paths = self.state.selected_paths()
        return paths[0] if paths else None

    def _detect_borders(self):
        p = self._first_selected_image()
        if not p:
            QMessageBox.information(self, "检测白边", "请先在中间选一张图")
            return
        try:
            m, g = detect_borders(Image.open(p))
        except Exception as e:
            QMessageBox.warning(self, "检测失败", str(e))
            return
        self.m_top.setValue(m.top); self.m_right.setValue(m.right)
        self.m_bottom.setValue(m.bottom); self.m_left.setValue(m.left)
        self.gap.setValue(g)
        self.statusMessage.emit(
            f"白边 上{m.top} 右{m.right} 下{m.bottom} 左{m.left} 间距{g}")

    def _infer_grid(self):
        p = self._first_selected_image()
        if not p:
            QMessageBox.information(self, "推断网格", "请先在中间选一张图")
            return
        try:
            rows, cols = infer_grid(Image.open(p))
        except Exception as e:
            QMessageBox.warning(self, "推断失败", str(e))
            return
        self.src_rows.setValue(rows)
        self.src_cols.setValue(cols)
        self.statusMessage.emit(f"推断网格 {rows}×{cols}")

    def overlay_spec(self) -> dict:
        return dict(
            src_rows=self.src_rows.value(), src_cols=self.src_cols.value(),
            sub_rows=self.sub_rows.value(), sub_cols=self.sub_cols.value(),
            margin_top=self.m_top.value(), margin_right=self.m_right.value(),
            margin_bottom=self.m_bottom.value(), margin_left=self.m_left.value(),
            gap=self.gap.value(),
        )

    def validate(self) -> tuple[bool, str]:
        if not self.state.selected_paths():
            return False, "请先选图"
        if not self.state.output_dir:
            return False, "请先设置输出目录"
        sr, sc = self.src_rows.value(), self.src_cols.value()
        br, bc = self.sub_rows.value(), self.sub_cols.value()
        if sr % br != 0 or sc % bc != 0:
            return False, f"子图 {br}×{bc} 必须整除源图 {sr}×{sc}"
        return True, ""

    def execute(self):
        paths = self.state.selected_paths()
        spec = make_grid_spec(
            self.src_rows.value(), self.src_cols.value(),
            self.sub_rows.value(), self.sub_cols.value(),
            self.m_top.value(), self.m_right.value(),
            self.m_bottom.value(), self.m_left.value(),
            self.gap.value(),
        )
        out_dir = self.state.output_dir
        fmt = self.fmt.currentText()

        def task():
            total = 0
            for p in paths:
                total += len(split_to_files(p, spec, out_dir,
                                            output_format=fmt))
            return total

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(
            lambda n: QMessageBox.information(self, "完成", f"已拆出 {n} 张"))
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "拆图失败", e))
        self._worker.start()
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/panels/split_panel.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add app/ui/panels/split_panel.py
git commit -m "feat(ui): SplitPanel with border/grid auto-detect"
```

---

## Task 9: app/ui/panels/combine_panel.py

**Files:**
- Create: `app/ui/panels/combine_panel.py`

- [ ] **Step 1: 写 app/ui/panels/combine_panel.py**

```python
"""拼图面板：order 模式选图 + R×C 拼接。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QLineEdit, QMessageBox,
)

from app.config import Config
from app.grid_ops import combine_to_file
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.worker import FunctionWorker


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class CombinePanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        root = QVBoxLayout(self)

        box = QGroupBox("拼接参数")
        f = QFormLayout(box)
        self.t_rows = _spin(1, 50, 2)
        self.t_cols = _spin(1, 50, 2)
        self.gap = _spin(0, 999, 4)
        self.scale = QComboBox()
        self.scale.addItems(["letterbox", "crop", "stretch"])
        for w in (self.t_rows, self.t_cols):
            w.valueChanged.connect(self.validityChanged)
        f.addRow("目标 行", self.t_rows)
        f.addRow("目标 列", self.t_cols)
        f.addRow("间距", self.gap)
        f.addRow("缩放", self.scale)
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        f.addRow("格式", self.fmt)
        self.out_name = QLineEdit("combined.png")
        f.addRow("输出文件名", self.out_name)
        root.addWidget(box)
        root.addStretch(1)

    def select_mode(self) -> str:
        return "order"

    def validate(self) -> tuple[bool, str]:
        if not self.state.output_dir:
            return False, "请先设置输出目录"
        need = self.t_rows.value() * self.t_cols.value()
        got = len(self.state.selected)
        if got != need:
            return False, f"需选 {need} 张·当前 {got} 张"
        return True, ""

    def execute(self):
        paths = self.state.selected_paths()
        out = self.state.output_dir / self.out_name.text().strip()
        tr, tc = self.t_rows.value(), self.t_cols.value()
        gap = self.gap.value()
        sm = self.scale.currentText()
        fmt = self.fmt.currentText()

        def task():
            combine_to_file(paths, out, target_rows=tr, target_cols=tc,
                            gap=gap, scale_mode=sm, output_format=fmt)
            return str(out)

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(
            lambda s: QMessageBox.information(self, "完成", f"已生成 {s}"))
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "拼图失败", e))
        self._worker.start()
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/panels/combine_panel.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add app/ui/panels/combine_panel.py
git commit -m "feat(ui): CombinePanel order-mode N→grid"
```

---

## Task 10: app/ui/panels/trim_panel.py

**Files:**
- Create: `app/ui/panels/trim_panel.py`

- [ ] **Step 1: 写 app/ui/panels/trim_panel.py**

```python
"""去白边面板：选中几张裁几张；不选=裁整目录。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox,
    QLineEdit, QMessageBox,
)

from app.config import Config
from app.grid_ops import trim_one, trim_batch
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.worker import FunctionWorker


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class TrimPanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        root = QVBoxLayout(self)
        box = QGroupBox("去白边参数")
        f = QFormLayout(box)
        self.threshold = _spin(0, 255, 240)
        self.max_iter = _spin(1, 20, 5)
        self.suffix = QLineEdit("_trim")
        self.fmt = QComboBox(); self.fmt.addItems(["PNG", "JPG"])
        f.addRow("阈值", self.threshold)
        f.addRow("最大迭代", self.max_iter)
        f.addRow("命名后缀", self.suffix)
        f.addRow("格式", self.fmt)
        root.addWidget(box)
        root.addStretch(1)

    def select_mode(self) -> str:
        return "multi"

    def validate(self) -> tuple[bool, str]:
        if not self.state.output_dir:
            return False, "请先设置输出目录"
        if not self.state.current_dir and not self.state.selected:
            return False, "请先打开目录或选图"
        return True, ""

    def execute(self):
        out = self.state.output_dir
        th = self.threshold.value()
        mi = self.max_iter.value()
        suf = self.suffix.text()
        fmt = self.fmt.currentText()
        sel = self.state.selected_paths()
        src_dir = self.state.current_dir

        def task():
            if sel:
                ext = ".png" if fmt.upper() == "PNG" else ".jpg"
                for p in sel:
                    trim_one(p, out / f"{p.stem}{suf}{ext}",
                             threshold=th, max_iter=mi, output_format=fmt)
                return len(sel)
            files = trim_batch(src_dir, out, threshold=th, max_iter=mi,
                               output_format=fmt, name_suffix=suf)
            return len(files)

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(
            lambda n: QMessageBox.information(self, "完成", f"已处理 {n} 张"))
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "去白边失败", e))
        self._worker.start()
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/panels/trim_panel.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add app/ui/panels/trim_panel.py
git commit -m "feat(ui): TrimPanel selected-or-whole-dir trim"
```

---

## Task 11: app/ui/panels/inference_panel.py

**Files:**
- Create: `app/ui/panels/inference_panel.py`

- [ ] **Step 1: 写 app/ui/panels/inference_panel.py**

```python
"""反推面板：模板 + 补充输入 + 宫格防灾门禁 + 结果可编辑保存。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QGroupBox, QComboBox, QSpinBox, QCheckBox,
    QPlainTextEdit, QPushButton, QHBoxLayout, QMessageBox, QApplication,
)

from app.config import Config
from app.core.output_writer import resolve_output_dir, write_outputs
from app.core.result_parser import parse_result, ParsedResult
from app.core.template_engine import (
    list_templates, render_template, recommend_template, Template,
)
from app.grid_ops import make_grid_spec, split_to_preview_cache
from app.providers import factory
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.widgets.template_form import TemplateFormWidget
from app.ui.worker import FunctionWorker

TEMPLATES_DIR = Path("templates")
PREVIEW_CACHE = Path("app/.cache/preview")


def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    return s


class InferencePanel(BasePanel):
    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self._worker = None
        self._templates: list[Template] = []
        self._result: Optional[ParsedResult] = None
        self._result_md: Optional[Path] = None
        self._result_meta: dict = {}

        root = QVBoxLayout(self)

        mode_box = QGroupBox("模式")
        mf = QFormLayout(mode_box)
        self.mode = QComboBox()
        self.mode.addItems(["单图", "多图", "宫格"])
        self.mode.currentTextChanged.connect(lambda _: self.validityChanged.emit())
        mf.addRow("反推模式", self.mode)
        root.addWidget(mode_box)

        # 宫格参数（仅宫格模式可见）
        self.grid_box = QGroupBox("宫格拆分")
        gf = QFormLayout(self.grid_box)
        self.g_sr = _spin(1, 50, 2)
        self.g_sc = _spin(1, 50, 2)
        self.g_br = _spin(1, 50, 1)
        self.g_bc = _spin(1, 50, 1)
        gf.addRow("源 行", self.g_sr)
        gf.addRow("源 列", self.g_sc)
        gf.addRow("子 行", self.g_br)
        gf.addRow("子 列", self.g_bc)
        self.confirm = QCheckBox("我确认拆图正确，可以送入反推")
        self.confirm.toggled.connect(lambda _: self.validityChanged.emit())
        gf.addRow(self.confirm)
        root.addWidget(self.grid_box)

        tpl_box = QGroupBox("模板")
        tf = QFormLayout(tpl_box)
        self.tpl = QComboBox()
        self.tpl.currentIndexChanged.connect(self._on_tpl_changed)
        tf.addRow("反推模板", self.tpl)
        root.addWidget(tpl_box)

        self.form = TemplateFormWidget()
        root.addWidget(self.form)

        # 结果区
        self.result_box = QGroupBox("结果（可编辑后保存）")
        rf = QFormLayout(self.result_box)
        self.f_global = QPlainTextEdit(); self.f_global.setFixedHeight(50)
        self.f_timeline = QPlainTextEdit(); self.f_timeline.setFixedHeight(70)
        self.f_local = QPlainTextEdit(); self.f_local.setFixedHeight(50)
        self.f_struct = QPlainTextEdit(); self.f_struct.setFixedHeight(70)
        self.f_struct.setReadOnly(True)
        rf.addRow("global_prompt", self.f_global)
        rf.addRow("timeline_data", self.f_timeline)
        rf.addRow("local_prompts", self.f_local)
        rf.addRow("结构字段(只读)", self.f_struct)
        btns = QHBoxLayout()
        b_save = QPushButton("保存覆盖 md+json")
        b_save.clicked.connect(self._save_result)
        b_copy = QPushButton("复制 global_prompt")
        b_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self.f_global.toPlainText()))
        btns.addWidget(b_save); btns.addWidget(b_copy); btns.addStretch(1)
        rf.addRow(btns)
        self.result_box.setVisible(False)
        root.addWidget(self.result_box)
        root.addStretch(1)

        self._reload_templates()
        self.mode.currentTextChanged.connect(self._sync_grid_visible)
        self._sync_grid_visible()

    def _sync_grid_visible(self):
        self.grid_box.setVisible(self.mode.currentText() == "宫格")

    def _reload_templates(self):
        self._templates = list_templates(TEMPLATES_DIR)
        self.tpl.blockSignals(True)
        self.tpl.clear()
        for t in self._templates:
            self.tpl.addItem(f"{t.name} ({t.id})", t.id)
        self.tpl.blockSignals(False)
        self._on_tpl_changed()

    def _current_tpl(self) -> Optional[Template]:
        tid = self.tpl.currentData()
        return next((t for t in self._templates if t.id == tid), None)

    def _on_tpl_changed(self):
        t = self._current_tpl()
        if t:
            self.form.set_variables(t.variables)

    def select_mode(self) -> str:
        return "single" if self.mode.currentText() in ("单图", "宫格") else "multi"

    def validate(self) -> tuple[bool, str]:
        if not self._current_tpl():
            return False, "请先选模板"
        sel = self.state.selected_paths()
        m = self.mode.currentText()
        if m == "宫格":
            if len(sel) != 1:
                return False, "宫格模式请只选 1 张"
            if not self.confirm.isChecked():
                return False, "请先勾选「我确认拆图正确」"
            return True, ""
        if m == "单图" and len(sel) != 1:
            return False, "请选 1 张图"
        if m == "多图" and not sel:
            return False, "请至少选 1 张图"
        return True, ""

    def execute(self):
        tpl = self._current_tpl()
        try:
            system_prompt = render_template(tpl, self.form.get_values())
        except ValueError as e:
            QMessageBox.warning(self, "模板字段缺失", str(e)); return

        sel = self.state.selected_paths()
        if self.mode.currentText() == "宫格":
            spec = make_grid_spec(self.g_sr.value(), self.g_sc.value(),
                                  self.g_br.value(), self.g_bc.value())
            images = split_to_preview_cache(sel[0], spec, PREVIEW_CACHE)
        else:
            images = sel

        cfg = self.cfg
        try:
            provider = factory.build_provider(
                cfg, cfg.current_provider, cfg.current_model)
        except Exception as e:
            QMessageBox.critical(self, "Provider 错误", str(e)); return
        out_dir = (self.state.output_dir
                   or resolve_output_dir(images[0], cfg.default_output_dir))
        base = images[0].stem
        tid = tpl.id

        def task():
            raw = provider.generate(images, system_prompt, "")
            parsed = parse_result(raw)
            md, js = write_outputs(
                result=parsed, output_dir=out_dir, base_name=base,
                template_id=tid, provider=cfg.current_provider,
                model=cfg.current_model)
            return parsed, md

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_done)
        self._worker.failed.connect(
            lambda e: QMessageBox.critical(self, "反推失败", e))
        self._worker.start()

    def _on_done(self, payload):
        parsed, md = payload
        self._result = parsed
        self._result_md = md
        self._result_meta = {
            "template_id": self._current_tpl().id,
            "provider": self.cfg.current_provider,
            "model": self.cfg.current_model,
        }
        self.f_global.setPlainText(parsed.global_prompt)
        self.f_timeline.setPlainText(parsed.timeline_data)
        self.f_local.setPlainText(parsed.local_prompts)
        self.f_struct.setPlainText(json.dumps({
            "segment_lengths": parsed.segment_lengths,
            "max_frames": parsed.max_frames,
            "frame_indices": parsed.frame_indices,
            "strengths": parsed.strengths,
            "epsilon": parsed.epsilon,
        }, indent=2, ensure_ascii=False))
        self.result_box.setVisible(True)
        QMessageBox.information(self, "完成", f"已写入 {md}")

    def _save_result(self):
        if not self._result or not self._result_md:
            return
        self._result.global_prompt = self.f_global.toPlainText()
        self._result.timeline_data = self.f_timeline.toPlainText()
        self._result.local_prompts = self.f_local.toPlainText()
        try:
            write_outputs(
                result=self._result, output_dir=self._result_md.parent,
                base_name=self._result_md.stem,
                template_id=self._result_meta["template_id"],
                provider=self._result_meta["provider"],
                model=self._result_meta["model"])
            QMessageBox.information(self, "已保存", str(self._result_md))
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/panels/inference_panel.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add app/ui/panels/inference_panel.py
git commit -m "feat(ui): InferencePanel with grid safety gate + editable result"
```

---

## Task 12: app/ui/main_window.py — 三栏重写

**Files:**
- Modify: `app/ui/main_window.py`（整体重写）

- [ ] **Step 1: 整体重写 app/ui/main_window.py**

```python
"""主窗口：三栏布局 + 菜单 + 信号总线 + 目录记忆。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QStackedWidget, QButtonGroup, QStatusBar, QProgressBar,
    QFileDialog, QMessageBox,
)

from app.config import load_config
import app.providers  # noqa: F401  触发 provider 注册

from app.ui.state import AppState, restore_from_config, remember_dirs
from app.ui.thumbnail_grid import ThumbnailGrid
from app.ui.preview_dialog import PreviewDialog
from app.ui.panels.inference_panel import InferencePanel
from app.ui.panels.split_panel import SplitPanel
from app.ui.panels.combine_panel import CombinePanel
from app.ui.panels.trim_panel import TrimPanel


FUNCS = [("反推", "inference"), ("拆图", "split"),
         ("拼图", "combine"), ("去白边", "trim")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shot-Prompt-Backwards · 分镜工具")
        self.resize(1360, 860)
        self.cfg = load_config()
        self.state = AppState()

        self._build_ui()
        self._wire()

        # 目录记忆恢复
        restore_from_config(self.state, self.cfg)
        if self.state.current_dir:
            self.dir_label.setText(f"当前目录:\n{self.state.current_dir}")
            self.thumb.populate(self.state.images)
        if self.state.output_dir:
            self.out_label.setText(f"输出目录:\n{self.state.output_dir}")
        self._refresh_counts()
        self._on_func_changed(0)

    def _build_ui(self):
        menu = self.menuBar()
        fm = menu.addMenu("文件")
        a_open = QAction("打开目录…", self); a_open.setShortcut("Ctrl+O")
        a_open.triggered.connect(self._open_dir)
        a_out = QAction("设置输出目录…", self)
        a_out.triggered.connect(self._set_out_dir)
        fm.addAction(a_open); fm.addAction(a_out)
        fm.addSeparator()
        a_quit = QAction("退出", self); a_quit.triggered.connect(self.close)
        fm.addAction(a_quit)

        sp = QSplitter(Qt.Horizontal)

        # 左栏
        left = QWidget(); lv = QVBoxLayout(left)
        self.dir_label = QLabel("当前目录:\n(未打开)")
        self.dir_label.setWordWrap(True)
        b_open = QPushButton("打开目录"); b_open.clicked.connect(self._open_dir)
        self.out_label = QLabel("输出目录:\n(未设置)")
        self.out_label.setWordWrap(True)
        b_out = QPushButton("设置输出目录")
        b_out.clicked.connect(self._set_out_dir)
        self.count_label = QLabel("0 张  已选 0")
        lv.addWidget(self.dir_label); lv.addWidget(b_open)
        lv.addWidget(self.out_label); lv.addWidget(b_out)
        lv.addWidget(self.count_label)
        lv.addStretch(1)
        left.setMinimumWidth(200); left.setMaximumWidth(260)

        # 中栏
        self.thumb = ThumbnailGrid()

        # 右栏
        right = QWidget(); rv = QVBoxLayout(right)
        switch = QHBoxLayout()
        self.func_group = QButtonGroup(self)
        for i, (label, key) in enumerate(FUNCS):
            b = QPushButton(label); b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self.func_group.addButton(b, i)
            switch.addWidget(b)
        rv.addLayout(switch)

        self.stack = QStackedWidget()
        self.panels = [
            InferencePanel(self.state, self.cfg),
            SplitPanel(self.state, self.cfg),
            CombinePanel(self.state, self.cfg),
            TrimPanel(self.state, self.cfg),
        ]
        for p in self.panels:
            self.stack.addWidget(p)
        rv.addWidget(self.stack, 1)

        act = QHBoxLayout()
        self.btn_preview = QPushButton("预览")
        self.btn_preview.clicked.connect(self._do_preview)
        self.btn_exec = QPushButton("执行")
        self.btn_exec.clicked.connect(self._do_execute)
        self.exec_hint = QLabel("")
        self.exec_hint.setStyleSheet("color:#888")
        act.addWidget(self.btn_preview); act.addWidget(self.btn_exec)
        act.addWidget(self.exec_hint, 1)
        rv.addLayout(act)
        right.setMinimumWidth(340); right.setMaximumWidth(420)

        sp.addWidget(left); sp.addWidget(self.thumb); sp.addWidget(right)
        sp.setStretchFactor(0, 0); sp.setStretchFactor(1, 1)
        sp.setStretchFactor(2, 0)
        sp.setSizes([220, 800, 360])
        self.setCentralWidget(sp)

        sb = QStatusBar()
        self.status = QLabel(
            f"后端: {self.cfg.current_provider} · {self.cfg.current_model}")
        self.progress = QProgressBar(); self.progress.setMaximumWidth(180)
        self.progress.hide()
        sb.addWidget(self.status, 1)
        sb.addPermanentWidget(self.progress)
        self.setStatusBar(sb)

        # 应用记忆的缩略图大小
        ts = self.cfg.ui.get("thumb_size")
        if isinstance(ts, int):
            self.thumb.set_thumb_size(ts)

    def _wire(self):
        self.func_group.idClicked.connect(self._on_func_changed)
        self.thumb.selectionChanged.connect(self._on_selection)
        self.thumb.previewRequested.connect(self._on_thumb_double)
        self.thumb.thumbSizeChanged.connect(self._on_thumb_size)
        for p in self.panels:
            p.validityChanged.connect(self._refresh_validity)
            p.statusMessage.connect(self.status.setText)

    # ---- 目录 ----
    def _open_dir(self):
        start = str(self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "打开目录", start)
        if not d:
            return
        self.state.load_dir(Path(d))
        self.dir_label.setText(f"当前目录:\n{self.state.current_dir}")
        self.thumb.populate(self.state.images)
        self._refresh_counts()
        remember_dirs(self.state, self.cfg)
        self.status.setText(f"已加载 {len(self.state.images)} 张")

    def _set_out_dir(self):
        start = str(self.state.output_dir or self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "设置输出目录", start)
        if not d:
            return
        self.state.output_dir = Path(d)
        self.out_label.setText(f"输出目录:\n{d}")
        remember_dirs(self.state, self.cfg)
        self._refresh_validity()

    # ---- 功能切换 ----
    def _on_func_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.state.active_function = FUNCS[idx][1]
        panel = self.panels[idx]
        self.thumb.set_mode(panel.select_mode())
        self.btn_preview.setVisible(panel.has_preview()
                                    or FUNCS[idx][1] == "split")
        self._refresh_validity()

    def _on_selection(self, order: list[int]):
        self.state.selected = list(order)
        self._refresh_counts()
        self._refresh_validity()

    def _refresh_counts(self):
        self.count_label.setText(
            f"{len(self.state.images)} 张  已选 {len(self.state.selected)}")

    def _refresh_validity(self):
        panel = self.panels[self.stack.currentIndex()]
        ok, why = panel.validate()
        self.btn_exec.setEnabled(ok)
        self.exec_hint.setText(why)

    def _on_thumb_size(self, size: int):
        self.cfg.ui["thumb_size"] = size
        self.cfg.update_settings()  # 持久化 ui

    def _on_thumb_double(self, row: int):
        if not (0 <= row < len(self.state.images)):
            return
        path = self.state.images[row].path
        overlay = None
        idx = self.stack.currentIndex()
        if FUNCS[idx][1] == "split":
            overlay = self.panels[idx].overlay_spec()
        PreviewDialog(path, overlay_spec=overlay, parent=self).exec()

    def _do_preview(self):
        idx = self.stack.currentIndex()
        if FUNCS[idx][1] != "split":
            return
        sel = self.state.selected_paths()
        if not sel:
            QMessageBox.information(self, "预览", "请先选一张图")
            return
        PreviewDialog(sel[0],
                      overlay_spec=self.panels[idx].overlay_spec(),
                      parent=self).exec()

    def _do_execute(self):
        panel = self.panels[self.stack.currentIndex()]
        ok, why = panel.validate()
        if not ok:
            QMessageBox.warning(self, "无法执行", why)
            return
        panel.execute()
```

- [ ] **Step 2: 语法检查**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m py_compile app/ui/main_window.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add app/ui/main_window.py
git commit -m "feat(ui): rewrite MainWindow as unified 3-pane + dir memory"
```

---

## Task 13: 删除旧文件 + import 自检

**Files:**
- Delete: `app/ui/tabs/`（整个目录）
- Delete: `app/ui/widgets/thumbnail_list.py`

- [ ] **Step 1: git 删除旧文件**

```bash
git rm -r app/ui/tabs
git rm app/ui/widgets/thumbnail_list.py
```

- [ ] **Step 2: 全量语法检查（确认没有残留 import 旧模块）**

Run:
```bash
/root/miniconda3/envs/finchat/bin/python3 -c "
import ast, sys
from pathlib import Path
bad = []
for p in Path('app').rglob('*.py'):
    src = p.read_text(encoding='utf-8')
    try:
        ast.parse(src)
    except SyntaxError as e:
        bad.append(f'{p}: {e}')
    if 'ui.tabs' in src or 'thumbnail_list' in src:
        bad.append(f'{p}: 仍引用已删除模块')
print('OK' if not bad else '\n'.join(bad))
"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove obsolete tabs/ and thumbnail_list.py"
```

---

## Task 14: 全套测试 + 启动 smoke

**Files:** 无（验证 only）

- [ ] **Step 1: 跑全部纯逻辑测试**

Run: `/root/miniconda3/envs/finchat/bin/python3 -m pytest -q`
Expected: 全绿（原 47 grid_ops/core/providers + 新 test_config 扩充 + test_state 6 + test_geometry 6）。无 fail。

- [ ] **Step 2: 全量 py_compile**

Run:
```bash
cd /mnt/e/Tools/ComfyUI/Assert/Projects/scripts/shot-prompt-backwards
find app -name "*.py" -exec /root/miniconda3/envs/finchat/bin/python3 -m py_compile {} \; && echo "ALL COMPILE OK"
```
Expected: `ALL COMPILE OK`

- [ ] **Step 3: 用户手动 smoke（清单交付给用户执行）**

输出以下清单给用户在 Windows 跑 `run.bat` 后逐项验证：

```
[ ] 启动后若上次有目录 → 缩略图自动出现
[ ] 文件→打开目录 → 中栏出缩略图
[ ] 文件→设置输出目录 → 左栏显示路径
[ ] 关掉重开 → 目录/输出目录自动回来
[ ] 右栏点「拼图」→ 中栏点图出现蓝圈①②③，再点取消重排
[ ] 右栏点「拆图」→ 双击中栏图 → 弹大图带红线网格 + 顶部"将切出N张"
[ ] 拆图面板「推断网格」「检测白边」能一键填参
[ ] 拆图/拼图/去白边 共用同一目录不再重填路径
[ ] 反推「宫格」模式不勾确认 → 执行按钮灰
[ ] 缩略图大小滑块拖动 → 重开后大小记住
```

- [ ] **Step 4: 最终 Commit（若 Step 1/2 有顺带修复）**

```bash
git add -A
git commit -m "test: v0.3 redesign full suite green + smoke checklist"
```
（无改动则跳过）

---

## 验收对照（spec 第 9.1 节）

| 验收项 | Task |
|---|---|
| 启动自动加载上次目录 | 12（restore_from_config 调用）+ 2 |
| 4 功能共享目录不重填 | 2（AppState）+ 12（单一 state 注入 4 panel） |
| 拼图蓝圈①②③再点重排 | 4 + 5 |
| 双击大图 + 拆图红线 + "切出N张" | 3 + 6 + 12 |
| 拆图检测白边/推断网格 | 8 |
| 输出目录全局复用+记忆 | 1 + 2 + 12 |
| 现有 47 + 新增测试全绿 | 14 |
| 4 功能手动 smoke | 14 |
