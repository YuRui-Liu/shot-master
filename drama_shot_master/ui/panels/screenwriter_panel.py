"""ScreenwriterPanel：编剧 Wizard 面板（项目列表 + 4 阶段详情）。

布局：内嵌 QSplitter，左 master（按钮 + 项目列表）/ 右 detail（阶段标签 + Wizard）。
沿用 video/imggen/soundtrack 面板的"viewport eventFilter + 名称列吃可见区
+ blank-click swallow"约定。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget, QLabel, QPlainTextEdit, QMessageBox, QInputDialog,
    QSplitter, QButtonGroup,
)

from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.theme import status_color


_STAGE_NAMES = ("创意", "剧本", "分镜", "提示词")
# 阶段索引 → 对应产物路径（相对项目目录）
_STAGE_PRODUCTS = (
    ("idea.json", None),                 # 创意：单文件
    ("剧本.md", None),                    # 剧本：单文件
    ("分镜.json", None),                  # 分镜：单文件
    (None, "prompts"),                    # 提示词：子目录
)


class ScreenwriterPanel(BasePanel):
    """编剧面板。内嵌 master-detail，左项目列表 / 右 Wizard。"""

    statusMessage = Signal(str)

    def __init__(self, cfg, client, lifecycle, state=None, parent=None):
        super().__init__(state, cfg, parent)
        self._client = client
        self._lifecycle = lifecycle
        self._current_project: Path | None = None
        self._build_ui()
        self.refresh()

    def select_mode(self) -> str:
        return "none"

    def validate(self):
        return False, "请通过列表管理编剧项目"

    def execute(self):
        raise NotImplementedError

    # —— UI 构造 ————————————————————————————————————————————

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_master())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setSizes([290, 900])
        root.addWidget(splitter)

    def _build_master(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(290)
        w.setMaximumWidth(360)
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        # 顶部按钮
        bar = QHBoxLayout()
        self.btn_new = QPushButton("新建")
        self.btn_open = QPushButton("打开项目目录…")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_new, self.btn_open, self.btn_del):
            bar.addWidget(b)
        bar.addStretch(1)
        v.addLayout(bar)

        # 项目列表（4 列；只读除名称外）
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "状态", "最近输出", "更新时间"])
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)        # 名称
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # 状态
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)        # 最近输出
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)        # 更新时间
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 130)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        # 双击触发编辑——名称列允许内联改名；其它列项已 setFlags(~Editable) 拦截
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                    | QAbstractItemView.EditKeyPressed)
        v.addWidget(self.table, 1)
        self.table.viewport().installEventFilter(self)

        self.btn_new.clicked.connect(self._on_new)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_del.clicked.connect(self._on_del)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.itemChanged.connect(self._on_item_changed)
        return w

    def _build_detail(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(6)

        # 当前项目标题
        self.lbl_project = QLabel("未选择项目")
        self.lbl_project.setObjectName("detailTaskName")
        v.addWidget(self.lbl_project)

        # 4 阶段标签（可点击手动切换）
        stage_bar = QHBoxLayout()
        self.stage_btns: list[QPushButton] = []
        self._stage_group = QButtonGroup(self)
        self._stage_group.setExclusive(True)
        for i, name in enumerate(_STAGE_NAMES, start=1):
            b = QPushButton(f"{i}. {name}")
            b.setCheckable(True)
            b.setObjectName("stageTab")
            self.stage_btns.append(b)
            self._stage_group.addButton(b, i - 1)
            b.clicked.connect(lambda _=False, idx=i - 1: self._switch_stage(idx))
            stage_bar.addWidget(b)
        stage_bar.addStretch(1)
        v.addLayout(stage_bar)

        # Wizard 区（4 阶段子面板）；记录每页 widget 以便绑定按钮
        self.wizard = QStackedWidget()
        self._stage_edits: list[QPlainTextEdit] = []
        for stage_idx, name in enumerate(_STAGE_NAMES):
            page = QWidget()
            pv = QVBoxLayout(page)
            pv.setContentsMargins(0, 0, 0, 0)
            pv.addWidget(QLabel(f"阶段：{name}（MVP 占位）"))
            edit = QPlainTextEdit()
            edit.setPlaceholderText(f"{name} 阶段产物预览/编辑（MVP 简版）")
            self._stage_edits.append(edit)
            pv.addWidget(edit, 1)
            row = QHBoxLayout()
            btn_gen = QPushButton(f"生成 {name}")
            btn_open_out = QPushButton("打开输出目录")
            btn_gen.clicked.connect(
                lambda _=False, i=stage_idx: self._on_generate_stage(i))
            btn_open_out.clicked.connect(self._on_open_output)
            row.addWidget(btn_gen)
            row.addWidget(btn_open_out)
            row.addStretch(1)
            pv.addLayout(row)
            self.wizard.addWidget(page)
        v.addWidget(self.wizard, 1)
        self.stage_btns[0].setChecked(True)
        return w

    # —— 表格 helpers ——————————————————————————————————————

    @staticmethod
    def _ro(text: str) -> QTableWidgetItem:
        """只读单元格。"""
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport():
            if ev.type() == QEvent.Resize:
                self._fit_name_col()
            elif ev.type() == QEvent.MouseButtonPress:
                if not self.table.indexAt(ev.pos()).isValid():
                    return True
        return super().eventFilter(obj, ev)

    def _fit_name_col(self):
        vw = self.table.viewport().width()
        self.table.setColumnWidth(0, max(150, vw - self.table.columnWidth(1)))

    # —— 项目管理 ——————————————————————————————————————————

    def _project_root(self) -> Path:
        return Path(getattr(self.cfg, "screenwriter_project_root", "") or "")

    def refresh(self):
        self.table.blockSignals(True)            # 程序填充别触发 itemChanged
        self.table.setRowCount(0)
        root = self._project_root()
        if root.is_dir():
            for sub in sorted([p for p in root.iterdir() if p.is_dir()]):
                r = self.table.rowCount()
                self.table.insertRow(r)
                # 名称列可编辑（内联改名）
                name_item = QTableWidgetItem(sub.name)
                name_item.setData(Qt.UserRole, sub.name)
                self.table.setItem(r, 0, name_item)
                # 状态
                status_str = "未知"
                if self._client is not None:
                    try:
                        st = self._client.scan_project(sub)
                        status_str = st.get("status", "未知")
                    except Exception:
                        pass
                si = self._ro(status_str)
                try:
                    si.setForeground(QColor(status_color(status_str, self.cfg)))
                except Exception:
                    pass
                self.table.setItem(r, 1, si)
                self.table.setItem(r, 2, self._ro("—"))
                self.table.setItem(r, 3, self._ro(""))
        self.table.blockSignals(False)
        self._fit_name_col()

    def _on_new(self):
        root = self._project_root()
        if not root.is_dir():
            QMessageBox.information(
                self, "未配置目录",
                "请在「设置 → 编剧」里指定项目目录，或点上面「打开项目目录…」选一个。")
            return
        name, ok = QInputDialog.getText(self, "新建编剧项目", "项目名:")
        if not ok or not name.strip():
            return
        new_dir = root / name.strip()
        try:
            new_dir.mkdir(exist_ok=False)
        except FileExistsError:
            QMessageBox.warning(self, "已存在", "项目名已存在")
            return
        self.refresh()

    def _on_open(self):
        d = QFileDialog.getExistingDirectory(self, "打开编剧项目目录")
        if not d:
            return
        if hasattr(self.cfg, "update_settings"):
            self.cfg.update_settings(screenwriter_project_root=d)
        else:
            self.cfg.screenwriter_project_root = d
        self.refresh()

    def _on_del(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r, 0).text()
        if QMessageBox.question(
                self, "删除", f"确定删除项目「{name}」（连同目录）？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        shutil.rmtree(self._project_root() / name, ignore_errors=True)
        self._current_project = None
        self.lbl_project.setText("未选择项目")
        self.refresh()

    def _on_item_changed(self, item: QTableWidgetItem):
        """名称列内联改名 → 重命名子目录。"""
        if item.column() != 0:
            return
        old_name = item.data(Qt.UserRole)
        new_name = item.text().strip()
        if not old_name or not new_name or old_name == new_name:
            return
        old_dir = self._project_root() / old_name
        new_dir = self._project_root() / new_name
        if new_dir.exists():
            QMessageBox.warning(self, "已存在", "项目名已存在，撤销改名")
            item.setText(old_name)
            return
        try:
            old_dir.rename(new_dir)
            item.setData(Qt.UserRole, new_name)
            if self._current_project == old_dir:
                self._current_project = new_dir
                self.lbl_project.setText(new_name)
        except OSError as e:
            QMessageBox.warning(self, "改名失败", str(e))
            item.setText(old_name)

    def _on_row_selected(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r, 0).text()
        self._current_project = self._project_root() / name
        self.lbl_project.setText(name)
        # 默认跳到 recommended_next
        idx = 0
        if self._client is not None:
            try:
                st = self._client.scan_project(self._current_project)
                idx = {"ideate": 0, "script": 1,
                       "storyboard": 2, "prompts": 3}.get(
                    st.get("recommended_next", "ideate"), 0)
            except Exception:
                pass
        self._switch_stage(idx)

    def _switch_stage(self, idx: int):
        """统一阶段切换入口；用户可手动随意跳。"""
        if not 0 <= idx < len(self.stage_btns):
            return
        self.wizard.setCurrentIndex(idx)
        btn = self.stage_btns[idx]
        if not btn.isChecked():
            btn.setChecked(True)

    # —— Wizard 按钮回调 ——————————————————————————————————

    def _on_generate_stage(self, stage_idx: int):
        """生成当前阶段产物（MVP 占位：仅状态提示）。"""
        if self._current_project is None:
            QMessageBox.information(self, "未选项目", "请先在左侧选一个项目")
            return
        if self._client is None:
            QMessageBox.information(
                self, "Agent 未就绪",
                "screenwriter_agent 子进程未启动，请检查启动日志。")
            return
        QMessageBox.information(
            self, "生成（MVP）",
            f"阶段「{_STAGE_NAMES[stage_idx]}」的真实生成 SSE 流接入留 P2；\n"
            "当前已有 client/lifecycle，后端 endpoint 已可手动 curl 测试。")

    def _on_open_output(self):
        """打开当前阶段产物所在目录（用系统资源管理器）。"""
        if self._current_project is None or not self._current_project.is_dir():
            QMessageBox.information(self, "未选项目", "请先在左侧选一个项目")
            return
        idx = self.wizard.currentIndex()
        file_name, subdir_name = _STAGE_PRODUCTS[idx]
        # 优先打开"包含产物的目录"；MVP 直接打开项目根
        target = self._current_project
        if subdir_name:
            sub = self._current_project / subdir_name
            if sub.exists():
                target = sub
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
