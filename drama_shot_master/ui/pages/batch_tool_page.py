"""BatchToolPage：批处理功能（拆图/拼图/去白边）的主区页。

按已确认 mockup（docs/explorer/batch-tools-redesign-confirm.html）布局：
  - 顶部 toolbar：工具标题（mode 角标） + 输出目录显示/选择
  - 中栏 grid-col：网格头（源图 + 模式角标 + 打开目录/全选/清空）+ ThumbnailGrid
  - 右栏 panel-col：参数面板头（标题 + 预览叠加 tag）+ BasePanel
  - 底部 execbar：批量进度条 + 预览/执行 + 校验提示

BasePanel 的 validate/execute/select_mode/has_preview/overlay_spec 契约保持不变；
颜色全部靠全局 QSS（按 objectName 上色），本页不内联硬编码颜色（仅校验提示用
token 区分 ok/warn）。所有原有方法/信号/属性（thumb/panel/btn_preview/btn_exec/
exec_hint/populate/selected_order/refresh_validity/_do_preview/_on_thumb_double/
_do_execute）保持兼容。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QMessageBox,
    QFrame, QScrollArea, QProgressBar, QFileDialog,
)

from drama_shot_master.config import Config
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.thumbnail_grid import ThumbnailGrid
from drama_shot_master.ui.preview_dialog import PreviewDialog
from drama_shot_master.ui.theme import _tokens, current_theme

# 工具 → 中栏头部 mode 角标文案
_MODE_TAG = {"multi": "多选", "order": "顺序"}
# 面板类名 → 工具标题（参数面板头用）
_TOOL_TITLE = {
    "SplitPanel": "拆图参数",
    "CombinePanel": "拼接参数",
    "TrimPanel": "去白边参数",
}
# 面板类名 → 执行按钮文案
_EXEC_LABEL = {
    "SplitPanel": "执行拆图",
    "CombinePanel": "执行拼接",
    "TrimPanel": "执行去白边",
}


class BatchToolPage(QWidget):
    def __init__(self, panel: BasePanel, state: AppState, cfg: Config,
                 parent=None):
        super().__init__(parent)
        self.panel = panel
        self.state = state
        self.cfg = cfg
        self._mode = panel.select_mode()

        self.thumb = ThumbnailGrid()
        self.thumb.set_mode(self._mode)

        self.setObjectName("BatchToolPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_execbar())

        # ---- 信号接线（与旧版完全一致）----
        self.btn_preview.clicked.connect(self._do_preview)
        self.btn_exec.clicked.connect(self._do_execute)
        self.thumb.selectionChanged.connect(self._on_selection)
        self.thumb.previewRequested.connect(self._on_thumb_double)
        if hasattr(panel, "validityChanged"):
            panel.validityChanged.connect(self.refresh_validity)
        self.btn_preview.setVisible(panel.has_preview())
        self.refresh_validity()
        self._sync_outdir()

    # ------------------------------------------------------------------ #
    # 构建：顶部工具栏
    # ------------------------------------------------------------------ #
    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("BatchToolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(14)

        title = QLabel(_TOOL_TITLE.get(type(self.panel).__name__, "批处理"))
        title.setObjectName("BatchToolTitle")
        lay.addWidget(title)
        lay.addStretch(1)

        out_lbl = QLabel("输出目录")
        out_lbl.setObjectName("BatchOutLabel")
        self.out_path = QLabel("（未设置）")
        self.out_path.setObjectName("BatchOutPath")
        self.out_path.setMinimumWidth(160)
        self.out_path.setMaximumWidth(320)
        self.out_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_outdir = QPushButton("选择…")
        self.btn_outdir.setObjectName("BatchOutPick")
        self.btn_outdir.clicked.connect(self._pick_output_dir)
        lay.addWidget(out_lbl)
        lay.addWidget(self.out_path)
        lay.addWidget(self.btn_outdir)
        return bar

    # ------------------------------------------------------------------ #
    # 构建：中栏（网格）+ 右栏（参数面板）
    # ------------------------------------------------------------------ #
    def _build_body(self) -> QWidget:
        body = QWidget()
        body.setObjectName("BatchBody")
        lay = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_grid_col(), 1)
        lay.addWidget(self._build_panel_col())
        return body

    def _build_grid_col(self) -> QWidget:
        col = QFrame()
        col.setObjectName("BatchGridCol")
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QFrame()
        head.setObjectName("BatchGridHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 10, 16, 10)
        hl.setSpacing(10)
        t = QLabel("源图")
        t.setObjectName("BatchGridHeadTitle")
        self.mode_tag = QLabel(_MODE_TAG.get(self._mode, "多选"))
        self.mode_tag.setObjectName("BatchModeTag")
        hl.addWidget(t)
        hl.addWidget(self.mode_tag)
        hl.addStretch(1)

        btn_open = QPushButton("打开目录…")
        btn_open.setObjectName("BatchMiniBtn")
        btn_open.clicked.connect(self._open_dir)
        hl.addWidget(btn_open)
        if self._mode == "multi":
            self.btn_select_all = QPushButton("全选")
            self.btn_select_all.setObjectName("BatchMiniBtn")
            self.btn_select_all.clicked.connect(self._select_all)
            hl.addWidget(self.btn_select_all)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("BatchMiniBtn")
        self.btn_clear.clicked.connect(self.thumb.clear_selection)
        hl.addWidget(self.btn_clear)

        v.addWidget(head)
        v.addWidget(self.thumb, 1)
        return col

    def _build_panel_col(self) -> QWidget:
        col = QFrame()
        col.setObjectName("BatchPanelCol")
        col.setMinimumWidth(340)
        col.setMaximumWidth(420)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QFrame()
        head.setObjectName("BatchPanelHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 11, 16, 11)
        hl.setSpacing(8)
        t = QLabel(_TOOL_TITLE.get(type(self.panel).__name__, "参数"))
        t.setObjectName("BatchPanelHeadTitle")
        hl.addWidget(t)
        hl.addStretch(1)
        if self.panel.has_preview():
            tag = QLabel("支持预览叠加")
            tag.setObjectName("BatchPanelHeadTag")
            hl.addWidget(tag)
        v.addWidget(head)

        # 参数面板放进可滚动区，长面板不被压扁
        scroll = QScrollArea()
        scroll.setObjectName("BatchPanelScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.panel)
        v.addWidget(scroll, 1)
        return col

    # ------------------------------------------------------------------ #
    # 构建：底部执行栏
    # ------------------------------------------------------------------ #
    def _build_execbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("BatchExecBar")
        v = QVBoxLayout(bar)
        v.setContentsMargins(16, 11, 16, 11)
        v.setSpacing(10)

        # 进度行
        prog = QHBoxLayout()
        prog.setSpacing(10)
        pl = QLabel("批量进度")
        pl.setObjectName("BatchProgLabel")
        self.progress = QProgressBar()
        self.progress.setObjectName("BatchProgressBar")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_text = QLabel("")
        self.progress_text.setObjectName("BatchProgText")
        prog.addWidget(pl)
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.progress_text)
        v.addLayout(prog)

        # 按钮行
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_preview = QPushButton("预览（叠加网格 / 白边）")
        self.btn_preview.setObjectName("BatchPreviewButton")
        self.btn_exec = QPushButton(
            _EXEC_LABEL.get(type(self.panel).__name__, "执行"))
        self.btn_exec.setObjectName("AccentButton")
        self.exec_hint = QLabel("")
        self.exec_hint.setObjectName("BatchExecHint")
        row.addWidget(self.btn_preview)
        row.addWidget(self.btn_exec)
        row.addStretch(1)
        row.addWidget(self.exec_hint)
        v.addLayout(row)
        return bar

    # ------------------------------------------------------------------ #
    # 行为
    # ------------------------------------------------------------------ #
    def populate(self, images):
        self.thumb.populate(images)
        self.refresh_validity()

    def selected_order(self) -> list[int]:
        return self.thumb.selected_order()

    def _on_selection(self, order):
        self.state.selected = list(order)
        self._update_mode_tag()
        self.refresh_validity()

    def _update_mode_tag(self):
        n = len(self.state.selected)
        base = _MODE_TAG.get(self._mode, "多选")
        if n:
            self.mode_tag.setText(f"{base} · 已选 {n} 张")
        else:
            self.mode_tag.setText(base)

    def refresh_validity(self):
        ok, why = self.panel.validate()
        self.btn_exec.setEnabled(ok)
        self.exec_hint.setText(why)
        _t = _tokens(current_theme(self.cfg))
        # ok 且有提示 → 绿色（done）；否则用 muted（提示是"原因"，多为待补全）
        color = _t.get("status_done", "#4ec98f") if ok else _t.get("fg_muted", "#9aa0a6")
        self.exec_hint.setProperty("validityOk", "true" if ok else "false")
        self.exec_hint.setStyleSheet(f"color:{color}")

    # ---- toolbar / gridhead 自包含动作 ----
    def _sync_outdir(self):
        if self.state.output_dir:
            self.out_path.setText(str(self.state.output_dir))
        else:
            self.out_path.setText("（未设置）")

    def _pick_output_dir(self):
        start = str(self.state.output_dir or self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "设置输出目录", start)
        if not d:
            return
        self.state.output_dir = Path(d)
        self._sync_outdir()
        self.refresh_validity()

    def _open_dir(self):
        start = str(self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "打开目录", start)
        if not d:
            return
        self.state.load_dir(Path(d))
        self.populate(self.state.images)

    def _select_all(self):
        """multi 模式全选当前所有缩略图。"""
        if self._mode != "multi":
            return
        lst = self.thumb.list
        from drama_shot_master.ui.thumbnail_delegate import SELECTED_ROLE
        order = []
        for i in range(lst.count()):
            it = lst.item(i)
            it.setData(SELECTED_ROLE, True)
            order.append(i)
        self.thumb._order = order
        self.thumb._anchor = order[-1] if order else None
        lst.viewport().update()
        self.thumb.selectionChanged.emit(list(order))

    def _do_preview(self):
        sel = self.state.selected_paths()
        if not sel:
            QMessageBox.information(self, "预览", "请先选一张图")
            return
        PreviewDialog(sel[0], overlay_spec=self.panel.overlay_spec(),
                      parent=self).exec()

    def _on_thumb_double(self, row: int):
        if not (0 <= row < len(self.state.images)):
            return
        path = self.state.images[row].path
        PreviewDialog(path, overlay_spec=self.panel.overlay_spec(),
                      parent=self).exec()

    def _do_execute(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            QMessageBox.warning(self, "需要激活", "请先在「关于」中激活。")
            return
        ok, why = self.panel.validate()
        if not ok:
            QMessageBox.warning(self, "无法执行", why)
            return
        self.panel.execute()
