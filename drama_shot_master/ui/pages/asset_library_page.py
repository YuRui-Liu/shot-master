# drama_shot_master/ui/pages/asset_library_page.py
"""资源库新页：角色/场景/道具三类 @ref 参考图管理（接 compass.ref_index）。

3 个 tab（角色/场景/道具）对应 compass characters/scenes/props 三份
ref_index.json；每 tab 一个网格，每条 ref = 一张卡（名 + @名_ref.png +
状态 就绪✓/生成中⟳/缺图○）。顶部完备性条读 completeness_check 显示
N/M 就绪 + 缺图数。工具栏（导入图/批量生成缺图/从剧本提取）只发信号不接后端。

视觉规格见 docs/explorer/asset-library-confirm.html：navy/蓝(#4a9eff)/紫调，
纯色 + 细边框 + 描边表达层级（不依赖 QSS 渐变，规避 Win11 渲染坑）。

阶段C Wave1：独立新页，不碰 app_shell / nav_config / flow_sidebar（Wave2 接线）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTabWidget, QScrollArea, QFrame, QSizePolicy,
)

from drama_shot_master.core.compass import paths as _paths
from drama_shot_master.core.compass.ref_index import (
    load_ref_index, RefIndex, READY_STATUS,
)

# 三类资源 → (内部 kind 键, tab 中文标题)
_KINDS: tuple[tuple[str, str], ...] = (
    ("characters", "角色"),
    ("scenes", "场景"),
    ("props", "道具"),
)

# 状态归一：ref_index status → 卡片三态展示键
_GENERATING = "generating"
_EMPTY = "empty"


def _norm_status(raw: str) -> str:
    """ref_index 原始 status → 卡片三态（ready / generating / empty）。

    ready → 就绪✓；generating → 生成中⟳；其余（pending/empty/空）→ 缺图○。
    """
    s = (raw or "").strip().lower()
    if s == READY_STATUS:
        return READY_STATUS
    if s == _GENERATING:
        return _GENERATING
    return _EMPTY


# 三态 → 卡片右上角徽标文案
_STATUS_BADGE = {
    READY_STATUS: "✓ 就绪",
    _GENERATING: "⟳ 生成中",
    _EMPTY: "○ 缺图",
}
# 三态 → 缩略图占位符
_STATUS_PLACEHOLDER = {
    READY_STATUS: "👤",
    _GENERATING: "⟳",
    _EMPTY: "+",
}


class RefCard(QFrame):
    """单条 ref 卡片：缩略图占位 + 名 + @名_ref.png + 状态徽标。

    纯色 + 细边框；不依赖 QSS 渐变。卡片不接后端，操作通过页面级信号上抛。
    """

    def __init__(self, name: str, status: str, ref_filename: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ref_name = name
        self.ref_status = status  # 已归一的三态键
        self.setObjectName("AssetRefCard")
        self.setProperty("status", status)
        self.setFixedHeight(184)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._build_ui(name, status, ref_filename)

    def _build_ui(self, name: str, status: str, ref_filename: str) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 缩略图区（占位）：状态徽标右上角
        thumb = QFrame(self)
        thumb.setObjectName("AssetRefThumb")
        thumb.setFixedHeight(118)
        tlay = QVBoxLayout(thumb)
        tlay.setContentsMargins(7, 7, 7, 7)

        badge = QLabel(_STATUS_BADGE.get(status, _STATUS_BADGE[_EMPTY]), thumb)
        badge.setObjectName("AssetRefBadge")
        badge.setProperty("status", status)
        badge.setAlignment(Qt.AlignRight | Qt.AlignTop)
        tlay.addWidget(badge, 0, Qt.AlignRight | Qt.AlignTop)

        ph = QLabel(_STATUS_PLACEHOLDER.get(status, "+"), thumb)
        ph.setObjectName("AssetRefPlaceholder")
        ph.setAlignment(Qt.AlignCenter)
        tlay.addWidget(ph, 1)

        lay.addWidget(thumb)

        # 卡片正文：名 + @名_ref.png 引用
        body = QFrame(self)
        body.setObjectName("AssetRefBody")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(10, 9, 10, 9)
        blay.setSpacing(4)

        nm = QLabel(name, body)
        nm.setObjectName("AssetRefName")
        blay.addWidget(nm)

        ref_text = ref_filename or f"@{name}_ref.png"
        if status == _EMPTY:
            ref_text = "未生成 · 出图前需补"
        ref_lbl = QLabel(ref_text, body)
        ref_lbl.setObjectName("AssetRefFilename")
        ref_lbl.setProperty("status", status)
        blay.addWidget(ref_lbl)

        lay.addWidget(body, 1)


class AssetLibraryPage(QWidget):
    """资源库页：角色/场景/道具三 tab + 完备性条 + 工具栏。

    与下游通信仅通过信号（不接后端）：
    - importRequested：导入图
    - generateRequested(str)：批量生成缺图 / 单条生成（带 name，批量时为空串）
    - extractRequested：从剧本提取
    """

    importRequested = Signal()
    generateRequested = Signal(str)
    extractRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("AssetLibraryPage")
        self._project_dir: Optional[Path] = None
        # kind → RefIndex
        self._indexes: dict[str, RefIndex] = {k: RefIndex() for k, _ in _KINDS}
        # kind → 网格容器 + 网格布局
        self._grids: dict[str, QGridLayout] = {}
        self._grid_hosts: dict[str, QWidget] = {}
        self._build_ui()

    # ---- UI 搭建 ------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())
        root.addWidget(self._make_toolbar())

        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("AssetLibraryTabs")
        for kind, title in _KINDS:
            host = self._make_grid_tab(kind)
            self._tabs.addTab(host, title)
        root.addWidget(self._tabs, 1)

    def _make_header(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("AssetLibraryHeader")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(12)

        ttl = QLabel("资源库", bar)
        ttl.setObjectName("AssetLibraryTitle")
        lay.addWidget(ttl)

        lay.addStretch(1)

        self.completenessLabel = QLabel("", bar)
        self.completenessLabel.setObjectName("AssetCompletenessLabel")
        lay.addWidget(self.completenessLabel)

        self._refresh_completeness()
        return bar

    def _make_toolbar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("AssetLibraryToolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 9, 18, 9)
        lay.setSpacing(9)

        src = QLabel("来源：从剧本/风格圣经自动提取 + 手动", bar)
        src.setObjectName("AssetToolbarSource")
        lay.addWidget(src)
        lay.addStretch(1)

        self.importBtn = QPushButton("⤓  导入图", bar)
        self.importBtn.setObjectName("AssetImportBtn")
        self.importBtn.clicked.connect(self.importRequested)
        lay.addWidget(self.importBtn)

        self.generateBtn = QPushButton("⟳  批量生成缺图", bar)
        self.generateBtn.setObjectName("AssetGenerateBtn")
        # 批量生成缺图：name 留空串（下游按当前 tab 缺图集合处理）
        self.generateBtn.clicked.connect(lambda: self.generateRequested.emit(""))
        lay.addWidget(self.generateBtn)

        self.extractBtn = QPushButton("＋  从剧本提取", bar)
        self.extractBtn.setObjectName("AssetExtractBtn")
        self.extractBtn.setProperty("primary", True)
        self.extractBtn.clicked.connect(self.extractRequested)
        lay.addWidget(self.extractBtn)

        return bar

    def _make_grid_tab(self, kind: str) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setObjectName("AssetGridScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        host = QWidget()
        host.setObjectName("AssetGridHost")
        grid = QGridLayout(host)
        grid.setContentsMargins(18, 12, 18, 18)
        grid.setSpacing(13)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._grids[kind] = grid
        self._grid_hosts[kind] = host
        scroll.setWidget(host)
        return scroll

    # ---- 数据加载 -----------------------------------------------------

    def set_project(self, project_dir: Optional[Union[str, Path]]) -> None:
        """切项目：读三类 ref_index.json 填充网格；空/缺失降级空网格不崩。"""
        self._project_dir = Path(project_dir) if project_dir else None
        for kind, _ in _KINDS:
            self._indexes[kind] = self._load_kind(kind)
            self._rebuild_grid(kind)
        self._refresh_completeness()

    def _load_kind(self, kind: str) -> RefIndex:
        """读某资源种类的 ref_index；无项目/无文件/坏 JSON → 空索引不崩。"""
        if self._project_dir is None:
            return RefIndex()
        try:
            path = _paths.ref_index_path(self._project_dir, kind)
        except ValueError:
            return RefIndex()
        return load_ref_index(path)

    def _rebuild_grid(self, kind: str) -> None:
        """按当前索引重建某 tab 网格（清旧卡 → 逐条建卡，每行 5 列）。"""
        grid = self._grids[kind]
        # 清空旧卡
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        cols = 5
        for i, entry in enumerate(self._indexes[kind].entries):
            status = _norm_status(entry.status)
            ref_fn = ""
            if entry.path:
                ref_fn = f"@{Path(entry.path).name}"
            card = RefCard(entry.name, status, ref_fn, parent=self._grid_hosts[kind])
            grid.addWidget(card, i // cols, i % cols)

    # ---- 完备性 -------------------------------------------------------

    def _refresh_completeness(self) -> None:
        ready, total = self.completeness()
        miss = self.missing_count()
        if total == 0:
            self.completenessLabel.setText("完备性：暂无资源")
        else:
            self.completenessLabel.setText(
                f"完备性：{ready}/{total} 就绪 · {miss} 项缺图"
            )

    def completeness(self) -> tuple[int, int]:
        """返回 (就绪数, 总数)：跨三类汇总。

        就绪判定按 status==ready（纯逻辑，不强依赖文件落盘存在，
        因 set_project 时缩略图可能尚未生成到盘）。
        """
        ready = 0
        total = 0
        for kind, _ in _KINDS:
            for e in self._indexes[kind].entries:
                total += 1
                if _norm_status(e.status) == READY_STATUS:
                    ready += 1
        return ready, total

    def missing_count(self) -> int:
        """缺图数 = 总数 - 就绪数（generating/empty/pending 均计缺）。"""
        ready, total = self.completeness()
        return total - ready

    def completeness_text(self) -> str:
        return self.completenessLabel.text()

    # ---- 查询辅助（供测试 / Wave2 接线） -----------------------------

    def card_count(self, kind: str) -> int:
        """某 tab 卡片数 = 该类 ref_index 条目数。"""
        idx = self._indexes.get(kind)
        return len(idx.entries) if idx is not None else 0

    def card_statuses(self, kind: str) -> list[str]:
        """某 tab 各卡归一后的三态键（顺序与索引一致）。"""
        idx = self._indexes.get(kind)
        if idx is None:
            return []
        return [_norm_status(e.status) for e in idx.entries]

    def request_generate(self, name: str) -> None:
        """单条生成入口：上抛 generateRequested(name)。"""
        self.generateRequested.emit(name)
