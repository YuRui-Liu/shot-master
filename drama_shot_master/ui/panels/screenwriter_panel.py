"""ScreenwriterPanel：编剧面板（任务栏化）。

左 ScreenwriterTaskManager + 右 ScreenwriterWizardHost。
4 个子面板单例：IdeatePage / ScriptPage / StoryboardPage / PromptsPage。
切换任务 → 全 page 统一 try_release + set_project；任一拒 → 回滚。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QSplitter,
)

from drama_shot_master.agents.screenwriter_client import ScreenwriterClient
from drama_shot_master.ui.widgets.screenwriter.task_manager import ScreenwriterTaskManager
from drama_shot_master.ui.widgets.screenwriter.wizard_host import ScreenwriterWizardHost
from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage
from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage
from drama_shot_master.ui.widgets.screenwriter.storyboard_page import StoryboardPage
from drama_shot_master.ui.widgets.screenwriter.prompts_page import PromptsPage


_STAGE_NAMES = ["创意", "剧本", "分镜", "提示词"]


class ScreenwriterPanel(QWidget):
    """编剧面板入口（任务栏化）。"""
    statusMessage = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._client = ScreenwriterClient(
            base_url=f"http://127.0.0.1:{cfg.screenwriter_agent_port}")
        self._last_selected: Path | None = None
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        # 左
        self._task_manager = ScreenwriterTaskManager(self._cfg)
        self._task_manager.setMaximumWidth(300)
        self._task_manager.setMinimumWidth(220)
        splitter.addWidget(self._task_manager)
        # 右
        ideate = IdeatePage(self._client)
        script = ScriptPage(self._client)
        storyboard = StoryboardPage(self._client)
        prompts = PromptsPage(self._client)
        self._pages = [ideate, script, storyboard, prompts]
        self._wizard_host = ScreenwriterWizardHost(
            self._pages, stage_names=_STAGE_NAMES)
        splitter.addWidget(self._wizard_host)
        splitter.setSizes([280, 900])
        h.addWidget(splitter)

    def _wire_signals(self) -> None:
        self._task_manager.taskSelected.connect(self._on_task_selected)
        self._task_manager.set_active_worker_query(self._any_page_streaming)
        for pg in self._pages:
            if hasattr(pg, "projectStateChanged"):
                pg.projectStateChanged.connect(self._task_manager.refresh)
            if hasattr(pg, "statusMessage"):
                pg.statusMessage.connect(self.statusMessage)
            if hasattr(pg, "stageAdvanceRequested"):
                pg.stageAdvanceRequested.connect(self._wizard_host.set_stage)

    def _on_task_selected(self, path: Path | None) -> None:
        # 统一切换：先全员 try_release，全 OK 才推进
        for pg in self._pages:
            if hasattr(pg, "try_release") and not pg.try_release():
                # 回滚 task manager 选择
                self._restore_selection()
                return
        for pg in self._pages:
            if hasattr(pg, "set_project"):
                pg.set_project(path)
        self._last_selected = path

    def _restore_selection(self) -> None:
        """try_release 拒绝时，把表格选择还原到 _last_selected。"""
        tm = self._task_manager
        if self._last_selected is None:
            tm._table.clearSelection()
            return
        for row in range(tm._table.rowCount()):
            item = tm._table.item(row, 0)
            if item and item.text() == self._last_selected.name:
                # blockSignals 防止 _on_selection_changed 再触发一遍
                tm._table.blockSignals(True)
                tm._table.selectRow(row)
                tm._table.blockSignals(False)
                return

    def _any_page_streaming(self, project_dir: Path) -> bool:
        for pg in self._pages:
            if hasattr(pg, "is_streaming") and pg.is_streaming(project_dir):
                return True
        return False
