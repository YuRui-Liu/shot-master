"""AppShell：基于 qfluentwidgets.FluentWindow 的流程式外壳。

侧栏按 nav_config.PHASES 分阶段注册 7 个真实功能页，并把原 MainWindow 的
控制器逻辑（任务窗回调、设置/帮助入口、授权巡检、状态恢复/落盘）整体移植过来，
使 AppShell 成为 MainWindow 的完整 drop-in 替代。

main_window.py 暂作为 fallback 保留（后续阶段移除），逻辑事实源仍以其为准。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
)
from drama_shot_master.ui.nav_config import FUNCS, PHASES, ICONS, LABELS


def _icon(key: str):
    """Resolve a nav_config ICONS string to a FluentIcon member.

    Falls back to FluentIcon.TAG if the name is not found in this version of
    qfluentwidgets (all current names verified present in 1.11.2; kept as
    safety net for future icon renames).
    """
    return getattr(FluentIcon, ICONS[key], FluentIcon.TAG)


class AppShell(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drama-Shot-Master")
        self.resize(1360, 860)
        self.pages: dict[str, QWidget] = {}
        self._phase_of: dict[str, str] = {}
        self._status_text = ""
        self._build_pages()
        self._build_nav()
        self._wire()
        self._restore_state()
        self._install_license_watch()

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #

    def _build_pages(self):
        from drama_shot_master.config import load_config
        from drama_shot_master.ui.state import AppState
        import drama_shot_master.providers  # noqa: F401  触发 provider 注册
        from drama_shot_master.core.video_task_store import VideoTaskStore
        from drama_shot_master.core.dub_task_store import DubTaskStore
        from drama_shot_master.core.imggen_task_store import ImgGenTaskStore
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        from drama_shot_master.ui.panels.split_panel import SplitPanel
        from drama_shot_master.ui.panels.combine_panel import CombinePanel
        from drama_shot_master.ui.panels.trim_panel import TrimPanel
        from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel

        self.cfg = load_config()
        self.state = AppState()
        self.video_store = VideoTaskStore.from_list(self.cfg.video_tasks)
        self.dub_store = DubTaskStore.from_list(self.cfg.dub_tasks)
        self.imggen_store = ImgGenTaskStore.from_list(self.cfg.imggen_tasks)
        self._open_task_windows = {}
        self._open_dub_windows = {}
        self._open_imggen_windows = {}

        builders = {
            "split":   lambda: BatchToolPage(SplitPanel(self.state, self.cfg), self.state, self.cfg),
            "combine": lambda: BatchToolPage(CombinePanel(self.state, self.cfg), self.state, self.cfg),
            "trim":    lambda: BatchToolPage(TrimPanel(self.state, self.cfg), self.state, self.cfg),
            "imggen":  self._make_imggen_panel,
            "video_gen": lambda: VideoTaskManagerPanel(
                self.state, self.cfg, self.video_store,
                self._open_task_window, self._close_task_window, self._persist_tasks),
            "soundtrack": self._try_make_soundtrack_panel,
            "dubbing": self._make_dub_panel,
        }
        for _label, key in FUNCS:
            page = builders[key]()
            page.setObjectName(f"page_{key}")   # FluentWindow 要求唯一 objectName
            self.pages[key] = page

    def _build_nav(self):
        for phase_title, keys in PHASES:
            # Phase section header: non-selectable label item.
            self.navigationInterface.addItem(
                routeKey=f"phase::{phase_title}",
                icon=FluentIcon.TAG,
                text=phase_title,
                onClick=None,
                selectable=False,
                position=NavigationItemPosition.SCROLL,
            )
            for key in keys:
                self.addSubInterface(
                    self.pages[key], _icon(key), LABELS[key],
                    position=NavigationItemPosition.SCROLL,
                )
                self._phase_of[key] = phase_title
            # Visual separator after each phase group.
            self.navigationInterface.addSeparator(
                position=NavigationItemPosition.SCROLL,
            )

        self.navigationInterface.addItem(
            routeKey="settings", icon=FluentIcon.SETTING, text="设置",
            onClick=self._open_settings_menu, selectable=False,
            position=NavigationItemPosition.BOTTOM)
        self.navigationInterface.addItem(
            routeKey="about", icon=FluentIcon.INFO, text="帮助 / 关于",
            onClick=self._open_about, selectable=False,
            position=NavigationItemPosition.BOTTOM)

    def _wire(self):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        for page in self.pages.values():
            panel = page.panel if isinstance(page, BatchToolPage) else page
            if hasattr(panel, "statusMessage"):
                panel.statusMessage.connect(self._set_status)
        self._video_manager().taskRenamed.connect(self._on_task_renamed)
        self._dub_manager().taskRenamed.connect(self._on_dub_renamed)
        self._imggen_manager().taskRenamed.connect(self._on_imggen_renamed)
        self.stackedWidget.currentChanged.connect(self._on_page_changed)

    def _restore_state(self):
        from drama_shot_master.ui.state import restore_from_config
        restore_from_config(self.state, self.cfg)
        if self.state.current_dir:
            self._populate_batch_pages()
        # 恢复上次活跃功能页
        target_key = self.cfg.last_active_function
        key = target_key if target_key in self.pages else FUNCS[0][1]
        self.switchTo(self.pages[key])

    def _populate_batch_pages(self):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        for page in self.pages.values():
            if isinstance(page, BatchToolPage):
                page.populate(self.state.images)

    def _refresh_batch_validity(self):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        for page in self.pages.values():
            if isinstance(page, BatchToolPage):
                page.refresh_validity()

    # ------------------------------------------------------------------ #
    # 导航 / 面包屑 / 状态面
    # ------------------------------------------------------------------ #

    def _current_key(self) -> str:
        cur = self.stackedWidget.currentWidget()
        for key, page in self.pages.items():
            if page is cur:
                return key
        # Default to first functional key if nothing matches yet.
        return FUNCS[0][1]

    def breadcrumb_text(self) -> str:
        key = self._current_key()
        return f"{self._phase_of.get(key, '')} › {LABELS.get(key, '')}"

    def _set_status(self, msg):
        self._status_text = msg

    def _on_page_changed(self, *args):
        self._current_breadcrumb = self.breadcrumb_text()

    def _open_settings_menu(self):
        from qfluentwidgets import RoundMenu, Action
        from PySide6.QtGui import QCursor
        menu = RoundMenu(parent=self)
        for text, fn in [
            ("RunningHub 配置…", self._open_runninghub_settings),
            ("翻译配置…", self._open_translation_settings),
            ("提示词优化配置…", self._open_refine_settings),
            ("配乐…", self._open_soundtrack_settings),
            ("配音…", self._open_dub_settings),
            ("图片生成…", self._open_imggen_settings),
        ]:
            act = Action(text, self); act.triggered.connect(fn)
            menu.addAction(act)
        menu.exec(QCursor.pos())

    # ------------------------------------------------------------------ #
    # 目录 / 设置 / 帮助（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _open_dir(self):
        from PySide6.QtWidgets import QFileDialog
        from drama_shot_master.ui.state import remember_dirs
        start = str(self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "打开目录", start)
        if not d:
            return
        self.state.load_dir(Path(d))
        self._populate_batch_pages()
        remember_dirs(self.state, self.cfg)
        self._set_status(f"已加载 {len(self.state.images)} 张")

    def _set_out_dir(self):
        from PySide6.QtWidgets import QFileDialog
        from drama_shot_master.ui.state import remember_dirs
        start = str(self.state.output_dir or self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "设置输出目录", start)
        if not d:
            return
        self.state.output_dir = Path(d)
        remember_dirs(self.state, self.cfg)
        self._refresh_batch_validity()

    def _open_runninghub_settings(self):
        from drama_shot_master.ui.dialogs.runninghub_settings_dialog import RunningHubSettingsDialog
        RunningHubSettingsDialog(self.cfg, parent=self).exec()

    def _open_translation_settings(self):
        from drama_shot_master.ui.dialogs.translation_settings_dialog import TranslationSettingsDialog
        TranslationSettingsDialog(self.cfg, parent=self).exec()

    def _open_refine_settings(self):
        from drama_shot_master.ui.dialogs.refine_settings_dialog import RefineSettingsDialog
        RefineSettingsDialog(self.cfg, parent=self).exec()

    def _open_soundtrack_settings(self):
        from drama_shot_master.ui.dialogs.soundtrack_settings_dialog import (
            SoundtrackSettingsDialog)
        SoundtrackSettingsDialog(self.cfg, parent=self).exec()

    def _open_dub_settings(self):
        from drama_shot_master.ui.dialogs.dub_settings_dialog import DubSettingsDialog
        DubSettingsDialog(self.cfg, parent=self).exec()

    def _open_imggen_settings(self):
        from drama_shot_master.ui.dialogs.imggen_settings_dialog import ImgGenSettingsDialog
        ImgGenSettingsDialog(self.cfg, parent=self).exec()

    def _open_about(self):
        from drama_shot_master.ui.dialogs.about_dialog import AboutDialog
        AboutDialog(self.cfg, parent=self).exec()

    def _open_help(self):
        """用系统默认浏览器打开内置 HTML 帮助文档。"""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QMessageBox
        help_path = Path(__file__).resolve().parent.parent / "assets" / "help" / "index.html"
        if not help_path.exists():
            QMessageBox.warning(self, "帮助文档缺失", f"未找到帮助文档:\n{help_path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(help_path)))

    # ------------------------------------------------------------------ #
    # 授权巡检（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _install_license_watch(self):
        from drama_shot_master.licensing import manager
        st = manager.status()
        if st.state is manager.LicenseState.VALID and st.days_left <= 7:
            self._set_status(f"授权将于 {st.days_left} 天后到期，请及时续期")
        from PySide6.QtCore import QTimer
        self._lic_timer = QTimer(self)
        self._lic_timer.setInterval(24 * 3600 * 1000)   # 每天复查
        self._lic_timer.timeout.connect(self._check_license_runtime)
        self._lic_timer.start()

    def _check_license_runtime(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            self._open_about()
            if manager.requires_activation(manager.status().state):
                self.close()

    # ------------------------------------------------------------------ #
    # 视频任务窗回调（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _video_manager(self):
        return self.pages["video_gen"]

    def _persist_tasks(self):
        try:
            self.cfg.update_settings(video_tasks=self.video_store.to_list())
        except Exception:
            pass

    def _open_task_window(self, task):
        from drama_shot_master.ui.windows.video_task_window import VideoTaskWindow
        existing = self._open_task_windows.get(task.id)
        if existing is not None:
            existing.raise_(); existing.activateWindow()
            return
        win = VideoTaskWindow(task, self.state, self.cfg)
        win.timelineDirty.connect(self._on_task_dirty)
        win.statusChanged.connect(self._on_task_status)
        win.resultReady.connect(self._on_task_result)
        win.closed.connect(self._on_task_window_closed)
        self._open_task_windows[task.id] = win
        win.show()

    def _close_task_window(self, task_id: str):
        win = self._open_task_windows.get(task_id)
        if win is not None:
            win.close()

    def _on_task_dirty(self, task_id: str, timeline: dict):
        self.video_store.update(task_id, timeline=timeline)
        self._persist_tasks()

    def _on_task_status(self, task_id: str, status: str):
        self._video_manager().set_task_status(task_id, status)

    def _on_task_result(self, task_id: str, mp4: str):
        self.video_store.update(task_id, last_result=mp4)
        self._persist_tasks()
        self._video_manager().refresh()

    def _on_task_window_closed(self, task_id: str):
        self._open_task_windows.pop(task_id, None)
        self._video_manager().clear_task_status(task_id)
        self._video_manager().refresh()

    def _on_task_renamed(self, task_id: str, name: str):
        win = self._open_task_windows.get(task_id)
        if win is not None:
            win.set_title_name(name)

    # ------------------------------------------------------------------ #
    # 配乐 tab helpers（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _try_make_soundtrack_panel(self):
        """try-import 注册配乐面板；agent/面板缺失则返回占位空面板，宿主照常启动。"""
        try:
            from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("配乐面板不可用，已跳过: %s", e)
            from PySide6.QtWidgets import QWidget
            return QWidget()
        self._soundtrack_windows = {}
        return SoundtrackPanel(
            self.state, self.cfg,
            open_window_cb=self._open_soundtrack_window,
            persist_cb=self._persist_soundtrack)

    def _persist_soundtrack(self):
        try:
            self.cfg.update_settings(soundtrack_tasks=self.cfg.soundtrack_tasks)
        except Exception:
            pass

    def _soundtrack_panel(self):
        return self.pages.get("soundtrack")

    def _open_soundtrack_window(self, task: dict):
        from drama_shot_master.ui.windows.soundtrack_task_window import (
            SoundtrackTaskWindow)
        wins = getattr(self, "_soundtrack_windows", None)
        if wins is None:
            wins = self._soundtrack_windows = {}
        tid = task.get("id")
        existing = wins.get(tid)
        if existing is not None:
            existing.raise_(); existing.activateWindow(); return
        work_root = Path(
            getattr(self.cfg, "video_output_dir", "") or ".") / "soundtrack"
        win = SoundtrackTaskWindow(task, self.cfg, work_root=work_root)
        win.statusChanged.connect(self._on_soundtrack_status)
        win.resultReady.connect(self._on_soundtrack_result)
        win.closed.connect(self._on_soundtrack_window_closed)
        wins[tid] = win
        win.show()

    def _on_soundtrack_window_closed(self, task_id: str):
        wins = getattr(self, "_soundtrack_windows", None)
        if wins is not None:
            wins.pop(task_id, None)

    def _on_soundtrack_status(self, task_id: str, status: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["status"] = status
        p = self._soundtrack_panel()
        if hasattr(p, "refresh"):
            p.refresh()

    def _on_soundtrack_result(self, task_id: str, output: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["output"] = output
        self._persist_soundtrack()
        p = self._soundtrack_panel()
        if hasattr(p, "refresh"):
            p.refresh()

    # ------------------------------------------------------------------ #
    # 配音 tab helpers（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _make_dub_panel(self):
        from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
        return DubTaskManagerPanel(
            self.state, self.cfg, self.dub_store,
            self._open_dub_window, self._close_dub_window, self._persist_dub_tasks)

    def _dub_manager(self):
        return self.pages["dubbing"]

    def _persist_dub_tasks(self):
        try:
            self.cfg.update_settings(dub_tasks=self.dub_store.to_list())
        except Exception:
            pass

    def _open_dub_window(self, task):
        from drama_shot_master.ui.windows.dub_task_window import DubTaskWindow
        existing = self._open_dub_windows.get(task.id)
        if existing is not None:
            existing.raise_(); existing.activateWindow(); return
        win = DubTaskWindow(task, self.cfg)
        win.dirty.connect(self._on_dub_dirty)
        win.statusChanged.connect(self._on_dub_status)
        win.resultReady.connect(self._on_dub_result)
        win.closed.connect(self._on_dub_window_closed)
        self._open_dub_windows[task.id] = win
        win.show()

    def _close_dub_window(self, task_id: str):
        win = self._open_dub_windows.get(task_id)
        if win is not None:
            win.close()

    def _on_dub_dirty(self, task_id: str, payload: dict):
        self.dub_store.update(task_id, payload=payload,
                              mode=("design" if payload.get("mode_kind") == "design" else "clone"))
        self._persist_dub_tasks()

    def _on_dub_status(self, task_id: str, status: str):
        self._dub_manager().set_task_status(task_id, status)

    def _on_dub_result(self, task_id: str, flac: str):
        self.dub_store.update(task_id, last_result=flac)
        self._persist_dub_tasks(); self._dub_manager().refresh()

    def _on_dub_window_closed(self, task_id: str):
        self._open_dub_windows.pop(task_id, None)
        self._dub_manager().clear_task_status(task_id)

    def _on_dub_renamed(self, task_id: str, name: str):
        win = self._open_dub_windows.get(task_id)
        if win is not None:
            win.set_title_name(name)

    # ------------------------------------------------------------------ #
    # 图片生成 tab helpers（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _make_imggen_panel(self):
        from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
        return ImgGenTaskManagerPanel(
            self.state, self.cfg, self.imggen_store,
            self._open_imggen_window, self._close_imggen_window,
            self._persist_imggen_tasks)

    def _imggen_manager(self):
        return self.pages["imggen"]

    def _persist_imggen_tasks(self):
        try:
            self.cfg.update_settings(imggen_tasks=self.imggen_store.to_list())
        except Exception:
            pass

    def _open_imggen_window(self, task):
        from drama_shot_master.ui.windows.imggen_task_window import ImgGenTaskWindow
        existing = self._open_imggen_windows.get(task.id)
        if existing is not None:
            existing.raise_(); existing.activateWindow(); return
        win = ImgGenTaskWindow(task, self.cfg)
        win.dirty.connect(self._on_imggen_dirty)
        win.statusChanged.connect(self._on_imggen_status)
        win.resultReady.connect(self._on_imggen_result)
        win.closed.connect(self._on_imggen_window_closed)
        self._open_imggen_windows[task.id] = win
        win.show()

    def _close_imggen_window(self, task_id: str):
        win = self._open_imggen_windows.get(task_id)
        if win is not None:
            win.close()

    def _on_imggen_dirty(self, task_id: str, payload: dict):
        self.imggen_store.update(task_id, payload=payload)
        self._persist_imggen_tasks()

    def _on_imggen_status(self, task_id: str, status: str):
        self._imggen_manager().set_task_status(task_id, status)

    def _on_imggen_result(self, task_id: str, path: str):
        self.imggen_store.update(task_id, last_result=path)
        self._persist_imggen_tasks(); self._imggen_manager().refresh()

    def _on_imggen_window_closed(self, task_id: str):
        self._open_imggen_windows.pop(task_id, None)
        self._imggen_manager().clear_task_status(task_id)

    def _on_imggen_renamed(self, task_id: str, name: str):
        win = self._open_imggen_windows.get(task_id)
        if win is not None:
            win.set_title_name(name)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_titlebar_themed", False):
            self._titlebar_themed = True
            from drama_shot_master.ui.theme import apply_dark_titlebar
            apply_dark_titlebar(self)

    def closeEvent(self, e):
        # 让每个打开的任务窗口存一次 timeline，再整体落盘
        for win in list(self._open_task_windows.values()):
            try:
                self.video_store.update(win.task_id, timeline=win.model.to_dict())
            except Exception:
                pass
        self._persist_tasks()
        # 让每个打开的配音任务窗存一次 payload，再整体落盘
        for win in list(self._open_dub_windows.values()):
            try:
                self.dub_store.update(win.task_id, payload=win.panel.to_payload())
            except Exception:
                pass
        self._persist_dub_tasks()
        # 让每个打开的图片生成任务窗存一次 payload，再整体落盘
        for win in list(self._open_imggen_windows.values()):
            try:
                self.imggen_store.update(win.task_id, payload=win.panel.to_payload())
            except Exception:
                pass
        self._persist_imggen_tasks()
        # 持久化当前活跃 panel
        try:
            self.cfg.update_settings(
                last_active_function=self._current_key() or "inference")
        except Exception:
            pass
        # 关闭软件时删除提交诊断日志（崩溃未正常关闭则保留，便于事后溯源）
        try:
            from drama_shot_master.core import submit_debug
            submit_debug.reset()
        except Exception:
            pass
        super().closeEvent(e)
