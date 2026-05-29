"""ScreenwriterTaskManager：编剧面板左侧任务列表。

与 Dub/ImgGen 范式一致：QTableWidget 4 列（名称/状态点/当前阶段/更新时间）
+ 工具栏 [新建/打开/删除]。多项目并发支持，状态点即时扫文件推断。

持久化：cfg.screenwriter_projects: list[str]（绝对路径）。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QInputDialog, QFileDialog, QMessageBox,
    QLabel,
)
# 预先抓取角色常量，确保 QMessageBox 被 monkeypatch 替换时仍可访问
_ACCEPT_ROLE = QMessageBox.AcceptRole
_DESTRUCTIVE_ROLE = QMessageBox.DestructiveRole
_CANCEL = QMessageBox.Cancel


_STAGE_FILES = (
    # 创意.json 是新名；旧名 idea.json 也接受（_compute_status 内做兜底）
    ("创意", "创意.json"),
    ("剧本", "剧本.md"),
    ("分镜", "分镜.json"),
    ("提示词", "prompts"),     # 目录非空
)


class ScreenwriterTaskManager(QWidget):
    """编剧任务列表（左侧栏）。"""
    taskSelected = Signal(object)         # Path | None
    projectAdded = Signal(object)         # Path
    projectRemoved = Signal(object)       # Path

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._projects: list[Path] = [
            Path(p) for p in (cfg.screenwriter_projects or [])]
        # 询问外部「某项目当前是否有 worker 在跑」的回调（由 ScreenwriterPanel 注入）
        self._active_worker_query = lambda p: False
        self._build_ui()
        self.refresh()
        # 30s 定时刷
        self._timer = QTimer(self)
        self._timer.setInterval(30000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def set_active_worker_query(self, fn) -> None:
        self._active_worker_query = fn

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)
        # 工具栏（按钮文本对齐 ImgGen TaskManager，无 emoji 前缀）
        bar = QHBoxLayout()
        bar.setSpacing(4)
        for txt, slot in (("新建", self._on_new_clicked),
                           ("打开", self._on_open_clicked),
                           ("删除", self._on_delete_clicked)):
            b = QPushButton(txt); b.clicked.connect(slot); bar.addWidget(b)
        bar.addStretch(1)
        v.addLayout(bar)
        # 表格（行号显示——对齐 ImgGen 风格）
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["名称", "状态", "当前阶段", "更新时间"])
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)        # 名称
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # 状态
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)        # 当前阶段
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)        # 更新时间
        self._table.setColumnWidth(2, 90)
        self._table.setColumnWidth(3, 120)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.viewport().installEventFilter(self)
        v.addWidget(self._table, 1)
        # 状态注脚
        self._footer = QLabel("")
        self._footer.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        v.addWidget(self._footer)

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if obj is self._table.viewport() and ev.type() == QEvent.Resize:
            self._fit_name_col()
        return super().eventFilter(obj, ev)

    def _fit_name_col(self) -> None:
        # 名称列只让出"状态"一列；当前阶段+更新时间推到 viewport 外，
        # 由水平滚动条访问。这样 300px 限宽下仍可同时看到名称+状态。
        vw = self._table.viewport().width()
        self._table.setColumnWidth(0, max(100, vw - self._table.columnWidth(1)))

    # —— 数据 ——

    def refresh(self) -> None:
        # 0) 记下当前选中（要在 setRowCount(0) 之前；否则之后 _selected_project 是 None）
        prev_selected = self._selected_project()
        # 1) 剪枝：清掉已不存在的目录
        valid: list[Path] = []
        for p in self._projects:
            if p.is_dir():
                valid.append(p)
        if len(valid) != len(self._projects):
            self._projects = valid
            self._save()
        # 2) 重绘表格——blockSignals 包住，防止 setRowCount(0)/insertRow 触发
        #    itemSelectionChanged 把 taskSelected(None) 误发出去（→ 4 子面板被清掉）
        self._table.blockSignals(True)
        try:
            self._table.setRowCount(0)
            for p in self._projects:
                row = self._table.rowCount()
                self._table.insertRow(row)
                self._table.setItem(row, 0, QTableWidgetItem(p.name))
                dots, current_stage = self._compute_status(p)
                self._table.setItem(row, 1, QTableWidgetItem(dots))
                self._table.setItem(row, 2, QTableWidgetItem(current_stage))
                mtime = self._dir_mtime(p)
                self._table.setItem(row, 3, QTableWidgetItem(mtime))
            # 3) 还原选中（仍 blockSignals）
            if prev_selected is not None and prev_selected in self._projects:
                idx = self._projects.index(prev_selected)
                self._table.selectRow(idx)
        finally:
            self._table.blockSignals(False)
        self._footer.setText(f"{len(self._projects)} 个项目")
        self._fit_name_col()

    def _compute_status(self, p: Path) -> tuple[str, str]:
        import json as _j
        from drama_shot_master.ui.widgets.screenwriter._paths import idea_exists_in
        # 读 剧本.json 确定总集数
        si_path = p / "剧本.json"
        total = 1
        episodes: list[str] = []
        if si_path.is_file():
            try:
                si = _j.loads(si_path.read_text(encoding="utf-8"))
                total = max(1, si.get("episode_count", 1))
                episodes = [e["id"] for e in si.get("episodes", [])]
            except Exception:
                pass
        if not episodes and (p / "剧本.md").is_file():
            episodes = ["E1"]
        if not episodes:
            total = 1
            episodes = []

        dots: list[str] = []
        last_done_idx = -1
        # 创意
        if idea_exists_in(p):
            dots.append("✓"); last_done_idx = 0
        else:
            dots.append("○")
        # 剧本（多集 → 看 剧本_E*.md 全到齐）
        if episodes:
            script_done = sum(
                1 for ep in episodes
                if (p / f"剧本_{ep}.md").is_file()
                or (ep == "E1" and (p / "剧本.md").is_file()))
            if script_done == total:
                dots.append("✓"); last_done_idx = 1
            elif script_done > 0:
                dots.append(f"{script_done}/{total}")
            else:
                dots.append("○")
        else:
            dots.append("○")
        # 分镜
        if episodes:
            sb_done = sum(
                1 for ep in episodes
                if (p / f"分镜_{ep}.json").is_file()
                or (ep == "E1" and (p / "分镜.json").is_file()))
            if sb_done == total:
                dots.append("✓"); last_done_idx = 2
            elif sb_done > 0:
                dots.append(f"{sb_done}/{total}")
            else:
                dots.append("○")
        else:
            if (p / "分镜.json").is_file():
                dots.append("✓"); last_done_idx = 2
            else:
                dots.append("○")
        # 提示词
        if episodes:
            pr_done = sum(
                1 for ep in episodes
                if (p / "prompts" / ep).is_dir()
                and any((p / "prompts" / ep).iterdir()))
        else:
            pr_done = 1 if ((p / "prompts").is_dir() and any((p / "prompts").iterdir())) else 0
            total_pr = 1
        if episodes:
            total_pr = total
        if pr_done == total_pr and pr_done > 0:
            dots.append("✓"); last_done_idx = 3
        elif pr_done > 0:
            dots.append(f"{pr_done}/{total_pr}")
        else:
            dots.append("○")

        # streaming 覆盖
        if self._active_worker_query(p):
            return " ".join(dots), "生成中"
        if last_done_idx == 3:
            return " ".join(dots), "已完成"
        # 下一步提示
        next_labels = ["创意", "剧本", "分镜", "提示词"]
        next_idx = last_done_idx + 1
        if next_idx < len(next_labels):
            return " ".join(dots), f"待 {next_labels[next_idx]}"
        return " ".join(dots), "已完成"

    def _dir_mtime(self, p: Path) -> str:
        try:
            ts = p.stat().st_mtime
        except OSError:
            return ""
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M")

    # —— 工具栏 actions ——

    def _on_new_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, "新建编剧项目", "项目名：")
        if not ok or not name.strip():
            return
        base = Path(self._cfg.screenwriter_project_root
                    or Path.home() / "drama-projects")
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "失败", f"创建 base 目录失败：{e}")
            return
        new_dir = base / name.strip()
        if new_dir.exists():
            QMessageBox.warning(self, "同名", f"{new_dir} 已存在")
            return
        try:
            new_dir.mkdir(parents=True)
        except OSError as e:
            QMessageBox.warning(self, "失败", str(e)); return
        self._add_project(new_dir)

    def _on_open_clicked(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择项目目录")
        if not d:
            return
        p = Path(d)
        if p in self._projects:
            QMessageBox.information(self, "已在列表",
                                       f"{p} 已经在任务列表里")
            return
        self._add_project(p)

    def _on_delete_clicked(self) -> None:
        p = self._selected_project()
        if p is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除项目")
        box.setText(f"确认删除「{p.name}」？")
        btn_listonly = box.addButton("仅从列表移除", _ACCEPT_ROLE)
        btn_purge = box.addButton("连同目录删除", _DESTRUCTIVE_ROLE)
        box.addButton(_CANCEL)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_listonly or clicked == "仅从列表移除":
            self._remove_from_list(p)
            return
        if clicked is btn_purge or clicked == "连同目录删除":
            if self._active_worker_query(p):
                QMessageBox.warning(self, "项目仍在生成",
                                       "请先停止当前阶段")
                return
            try:
                shutil.rmtree(p)
            except OSError as e:
                QMessageBox.warning(self, "删除失败", str(e)); return
            self._remove_from_list(p)

    def _selected_project(self) -> Path | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._projects):
            return self._projects[idx]
        return None

    def _add_project(self, p: Path) -> None:
        if p in self._projects:
            return
        self._projects.append(p)
        self._save()
        self.refresh()
        self.projectAdded.emit(p)

    def _remove_from_list(self, p: Path) -> None:
        if p in self._projects:
            self._projects.remove(p)
            self._save()
            self.refresh()
            self.projectRemoved.emit(p)

    def _save(self) -> None:
        self._cfg.update_settings(
            screenwriter_projects=[str(p) for p in self._projects])

    def _on_selection_changed(self) -> None:
        p = self._selected_project()
        self.taskSelected.emit(p)
