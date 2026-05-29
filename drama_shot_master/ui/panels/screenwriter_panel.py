"""ScreenwriterPanel：编剧面板（任务栏化）。

左 ScreenwriterTaskManager + 右 ScreenwriterWizardHost。
4 个子面板单例：IdeatePage / ScriptPage / StoryboardPage / PromptsPage。
切换任务 → 全 page 统一 try_release + set_project；任一拒 → 回滚。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QSplitter, QMessageBox,
)

from drama_shot_master.agents.screenwriter_client import ScreenwriterClient
from drama_shot_master.ui.widgets.screenwriter.task_manager import ScreenwriterTaskManager
from drama_shot_master.ui.widgets.screenwriter.wizard_host import ScreenwriterWizardHost
from drama_shot_master.ui.widgets.screenwriter.ideate_page import IdeatePage
from drama_shot_master.ui.widgets.screenwriter.script_page import ScriptPage
from drama_shot_master.ui.widgets.screenwriter.storyboard_page import StoryboardPage
from drama_shot_master.ui.widgets.screenwriter.prompts_page import PromptsPage
from drama_shot_master.ui.widgets.screenwriter.video_prompt_page import VideoPromptPage
from drama_shot_master.ui.widgets.screenwriter.audio_prompt_page import AudioPromptPage


_STAGE_NAMES = ["创意", "剧本", "分镜", "分镜图提示词", "视频提示词", "配音配乐"]


class ScreenwriterPanel(QWidget):
    """编剧面板入口（任务栏化）。"""
    statusMessage = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._client = ScreenwriterClient(
            base_url=f"http://127.0.0.1:{cfg.screenwriter_agent_port}",
            cfg=cfg)  # cfg 注入 → stream_post 自动注 LLM creds + model 到 body
        self._last_selected: Path | None = None
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        # 左
        from drama_shot_master.ui.widgets.collapsible_task_bar import CollapsibleTaskBar
        self._task_manager = ScreenwriterTaskManager(self._cfg)
        self._task_bar = CollapsibleTaskBar(
            self._task_manager, splitter, manager_index=0, expanded_width=280)
        splitter.addWidget(self._task_bar)
        self._task_manager.icon_rail_updated.connect(
            lambda: self._task_bar._icon_rail.refresh(
                self._task_manager.icon_rail_items()))
        self._task_bar._icon_rail.item_clicked.connect(
            self._task_manager.select_by_id)
        # 右
        ideate = IdeatePage(self._client)
        script = ScriptPage(self._client)
        storyboard = StoryboardPage(self._client)
        prompts = PromptsPage(self._client)
        video_prompt = VideoPromptPage(self._client)
        audio_prompt = AudioPromptPage(self._client)
        self._pages = [ideate, script, storyboard, prompts, video_prompt, audio_prompt]
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
                pg.stageAdvanceRequested.connect(self._on_stage_advance_requested)

    def _on_task_selected(self, path: Path | None) -> None:
        if path is not None:
            self._migrate_legacy_if_needed(path)
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

    def _migrate_legacy_if_needed(self, project_dir: Path) -> None:
        """检测旧版单集结构（剧本.md 存在 + 剧本.json 不存在），询问是否迁移。"""
        si = project_dir / "剧本.json"
        legacy_md = project_dir / "剧本.md"
        if si.is_file() or not legacy_md.is_file():
            return
        ans = QMessageBox.question(
            self, "检测到旧版单集剧本",
            f"项目 {project_dir.name} 为旧版单集结构。\n"
            "是否迁移为多集结构？\n\n"
            "[是] = 自动建 剧本.json（1 集）+ 重命名 剧本.md → 剧本_E1.md\n"
            "[否] = 保持只读浏览",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        import json as _j
        md_text = legacy_md.read_text(encoding="utf-8")
        title = project_dir.name
        for line in md_text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        si_data = {
            "title": title,
            "episode_count": 1,
            "selected_episode": "E1",
            "episodes": [{"id": "E1", "title": title, "summary": ""}],
            "input": {},
            "updated_at": "",
        }
        si.write_text(_j.dumps(si_data, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        target = project_dir / "剧本_E1.md"
        legacy_md.rename(target)
        legacy_sb = project_dir / "分镜.json"
        if legacy_sb.is_file():
            legacy_sb.rename(project_dir / "分镜_E1.json")

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

    def _on_stage_advance_requested(self, idx: int) -> None:
        """上一阶段「推进」→ 切到 idx + 让目标 page 自动尝试启动生成。
        page 自身判断 upstream/output/state，决定是否真跑（修「推进了但不生成」bug）。
        """
        self._wizard_host.set_stage(idx)
        if 0 <= idx < len(self._pages):
            target = self._pages[idx]
            if hasattr(target, "start_generation_if_idle"):
                target.start_generation_if_idle()
