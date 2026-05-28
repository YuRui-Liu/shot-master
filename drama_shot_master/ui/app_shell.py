"""AppShell：基于原生 QMainWindow 的流程式外壳。

侧栏(FlowSidebar)按 nav_config.PHASES 分阶段渲染 7 个真实功能页，顶部全局命令栏
横跨内容区；并把原 MainWindow 的控制器逻辑（任务窗回调、设置/帮助入口、授权巡检、
状态恢复/落盘）整体移植过来，使 AppShell 成为 MainWindow 的完整 drop-in 替代。

main_window.py 暂作为 fallback 保留（后续阶段移除），逻辑事实源仍以其为准。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QMenu,
)
from PySide6.QtGui import QAction, QCursor
from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
from drama_shot_master.ui.widgets.project_command_bar import ProjectCommandBar
from drama_shot_master.ui.theme import apply_window_icon, apply_titlebar, current_theme
from drama_shot_master.ui.nav_config import FUNCS, PHASES, LABELS


class AppShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drama-Shot-Master")
        self.resize(1360, 860)
        self.pages = {}
        self._phase_of = {k: t for t, ks in PHASES for k in ks}
        self._status_text = ""
        self._build_pages()
        self._build_ui()
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

        self.cfg = load_config()
        self.state = AppState()
        self.video_store = VideoTaskStore.from_list(self.cfg.video_tasks)
        self.dub_store = DubTaskStore.from_list(self.cfg.dub_tasks)
        self.imggen_store = ImgGenTaskStore.from_list(self.cfg.imggen_tasks)

        builders = {
            "split":   lambda: BatchToolPage(SplitPanel(self.state, self.cfg), self.state, self.cfg),
            "combine": lambda: BatchToolPage(CombinePanel(self.state, self.cfg), self.state, self.cfg),
            "trim":    lambda: BatchToolPage(TrimPanel(self.state, self.cfg), self.state, self.cfg),
            "imggen":  self._make_imggen_page,
            "video_gen": self._make_video_page,
            "soundtrack": self._make_soundtrack_page,
            "dubbing": self._make_dub_page,
        }
        for _label, key in FUNCS:
            page = builders[key]()
            page.setObjectName(f"page_{key}")   # 稳定 objectName，便于 QSS 选择与 findChild
            self.pages[key] = page

    def _build_ui(self):
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

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.command_bar)
        root.addWidget(body_w, 1)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

    def _wire(self):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        for page in self.pages.values():
            # BatchToolPage→page.panel；TaskWorkspacePage→page.manager；manager 页→page 本身
            panel = getattr(page, "panel", None)
            src = panel if panel is not None else getattr(page, "manager", page)
            if hasattr(src, "statusMessage"):
                src.statusMessage.connect(self._set_status)
            if isinstance(page, BatchToolPage):
                page.thumb.selectionChanged.connect(self._refresh_counts)
        self.sidebar.currentChanged.connect(self._on_nav_changed)
        self.sidebar.settingsRequested.connect(self._open_unified_settings)
        self.sidebar.helpRequested.connect(self._open_help_menu)
        self.command_bar.openDirRequested.connect(self._open_dir)
        self.command_bar.setOutputRequested.connect(self._set_out_dir)
        self.stack.currentChanged.connect(self._on_page_changed)

    def _on_nav_changed(self, key: str):
        self.switchTo(self.pages[key])

    def switchTo(self, page):
        self.stack.setCurrentWidget(page)
        key = self._key_of(page)
        if key:
            self.sidebar.set_active(key)

    def _key_of(self, page):
        for k, p in self.pages.items():
            if p is page:
                return k
        return None

    def _restore_state(self):
        from drama_shot_master.ui.state import restore_from_config
        restore_from_config(self.state, self.cfg)
        if self.state.current_dir:
            self._populate_batch_pages()
        if self.state.current_dir:
            self.command_bar.set_dir(str(self.state.current_dir))
        if self.state.output_dir:
            self.command_bar.set_output(str(self.state.output_dir))
        self._refresh_counts()
        # 恢复上次活跃功能页
        target_key = self.cfg.last_active_function
        key = target_key if target_key in self.pages else FUNCS[0][1]
        self.switchTo(self.pages[key])

    def _refresh_counts(self, *args):
        self.command_bar.set_count(
            f"{len(self.state.images)} 张  已选 {len(self.state.selected)}")

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
        return self._key_of(self.stack.currentWidget()) or FUNCS[0][1]

    def breadcrumb_text(self) -> str:
        key = self._current_key()
        return f"{self._phase_of.get(key, '')} › {LABELS.get(key, '')}"

    def _set_status(self, msg):
        self._status_text = msg

    def _on_page_changed(self, *args):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        page = self.stack.currentWidget()
        if isinstance(page, BatchToolPage):
            self.state.selected = page.selected_order()
        self._refresh_counts()

    def _open_unified_settings(self):
        from drama_shot_master.ui.dialogs.unified_settings_dialog import UnifiedSettingsDialog
        from PySide6.QtWidgets import QApplication
        UnifiedSettingsDialog(QApplication.instance(), self.cfg, parent=self).exec()

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
        self.command_bar.set_dir(f"{self.state.current_dir}")
        self._refresh_counts()
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
        self.command_bar.set_output(f"{self.state.output_dir}")

    def _open_about(self):
        from drama_shot_master.ui.dialogs.about_dialog import AboutDialog
        AboutDialog(self.cfg, parent=self).exec()

    def _open_help_menu(self):
        menu = QMenu(self)
        a_help = QAction("帮助文档", self); a_help.triggered.connect(self._open_help)
        a_about = QAction("关于…", self); a_about.triggered.connect(self._open_about)
        menu.addAction(a_help); menu.addAction(a_about)
        menu.exec(QCursor.pos())

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

    def _make_video_page(self):
        from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
        from drama_shot_master.ui.panels.video_panel import VideoPanel
        from drama_shot_master.core.video_timeline_model import TimelineModel

        manager = VideoTaskManagerPanel(
            self.state, self.cfg, self.video_store, None, None, self._persist_tasks)

        def editor_factory(task):
            return VideoPanel(self.state, self.cfg,
                              TimelineModel.from_dict(task.timeline))

        def wire_editor(editor, task):
            tid = task.id
            editor.submitStarted.connect(lambda: self._on_task_status(tid, "生成中"))
            editor.submitDone.connect(
                lambda mp4: (self._on_task_status(tid, "完成"),
                             self._on_task_result(tid, mp4)))
            editor.submitFailed.connect(lambda e: self._on_task_status(tid, "失败"))

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.model.to_dict(),
            on_persist=self._on_task_dirty,
            title_for=lambda task: f"视频任务 · {task.name}",
        )
        manager.taskRenamed.connect(self._on_task_renamed)
        manager.taskDeleted.connect(page.discard_editor)
        return page

    def _video_manager(self):
        return self.pages["video_gen"].manager

    def _persist_tasks(self):
        try:
            self.cfg.update_settings(video_tasks=self.video_store.to_list())
        except Exception:
            pass

    def _on_task_dirty(self, task_id: str, timeline: dict):
        self.video_store.update(task_id, timeline=timeline)
        self._persist_tasks()

    def _on_task_status(self, task_id: str, status: str):
        self._video_manager().set_task_status(task_id, status)

    def _on_task_result(self, task_id: str, mp4: str):
        self.video_store.update(task_id, last_result=mp4)
        self._persist_tasks()
        self._video_manager().refresh()

    def _on_task_renamed(self, task_id: str, name: str):
        page = self.pages.get("video_gen")
        if page is not None and hasattr(page, "update_task_name"):
            page.update_task_name(task_id, name)

    # ------------------------------------------------------------------ #
    # 配乐 tab helpers（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _make_soundtrack_page(self):
        """try-import 兜底装配配乐主-详页；agent/控件缺失则返回占位空面板。"""
        try:
            from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
            from drama_shot_master.ui.widgets.soundtrack_editor import SoundtrackEditor
            from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("配乐面板不可用，已跳过: %s", e)
            from PySide6.QtWidgets import QWidget
            return QWidget()
        work_root = Path(getattr(self.cfg, "video_output_dir", "") or ".") / "soundtrack"
        manager = SoundtrackPanel(self.state, self.cfg, None, self._persist_soundtrack)

        def editor_factory(view):
            return SoundtrackEditor(view.payload, self.cfg, work_root)

        def wire_editor(editor, view):
            # SoundtrackEditor 信号自带 task_id（不靠 factory-time 闭包），故直接 connect
            # 2-arg 方法；与 dub/imggen 走 lambda 的写法不同。
            editor.statusChanged.connect(self._on_soundtrack_status)   # (task_id,status)
            editor.resultReady.connect(self._on_soundtrack_result)     # (task_id,output)

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.to_payload(),
            on_persist=self._on_soundtrack_dirty,
            title_for=lambda view: f"配乐 · {view.name}",
        )
        manager.taskRenamed.connect(self._on_soundtrack_renamed)
        manager.taskDeleted.connect(page.discard_editor)
        return page

    def _persist_soundtrack(self):
        try:
            self.cfg.update_settings(soundtrack_tasks=self.cfg.soundtrack_tasks)
        except Exception:
            pass

    def _soundtrack_panel(self):
        """返回 manager（SoundtrackPanel）；兜底裸 QWidget 时返回 None。"""
        p = self.pages.get("soundtrack")
        return getattr(p, "manager", None)

    def _on_soundtrack_dirty(self, task_id: str, payload: dict):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t.update(payload)        # mp4/style/output_dir
                break
        self._persist_soundtrack()

    def _on_soundtrack_renamed(self, task_id: str, name: str):
        page = self.pages.get("soundtrack")
        if page is not None and hasattr(page, "update_task_name"):
            page.update_task_name(task_id, name)

    def _on_soundtrack_status(self, task_id: str, status: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["status"] = status
                break
        m = self._soundtrack_panel()
        if m is not None and hasattr(m, "refresh"):
            m.refresh()

    def _on_soundtrack_result(self, task_id: str, output: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["output"] = output
                break
        self._persist_soundtrack()
        m = self._soundtrack_panel()
        if m is not None and hasattr(m, "refresh"):
            m.refresh()

    # ------------------------------------------------------------------ #
    # 配音 tab helpers（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _make_dub_page(self):
        from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        from drama_shot_master.ui.panels.dub_task_manager_panel import DubTaskManagerPanel
        from drama_shot_master.ui.panels.dub_panel import DubPanel

        manager = DubTaskManagerPanel(
            self.state, self.cfg, self.dub_store, None, None, self._persist_dub_tasks)

        def editor_factory(task):
            return DubPanel(self.cfg, payload=task.payload)

        def wire_editor(editor, task):
            tid = task.id
            editor.statusChanged.connect(lambda s: self._on_dub_status(tid, s))
            editor.resultReady.connect(lambda p: self._on_dub_result(tid, p))
            editor.dirty.connect(lambda: self._on_dub_dirty(tid, editor.to_payload()))

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.to_payload(),
            on_persist=self._on_dub_dirty,
            title_for=lambda task: f"配音 · {task.name}",
        )
        manager.taskRenamed.connect(self._on_dub_renamed)
        manager.taskDeleted.connect(page.discard_editor)
        return page

    def _dub_manager(self):
        return self.pages["dubbing"].manager

    def _persist_dub_tasks(self):
        try:
            self.cfg.update_settings(dub_tasks=self.dub_store.to_list())
        except Exception:
            pass

    def _on_dub_dirty(self, task_id: str, payload: dict):
        self.dub_store.update(task_id, payload=payload,
                              mode=("design" if payload.get("mode_kind") == "design" else "clone"))
        self._persist_dub_tasks()

    def _on_dub_status(self, task_id: str, status: str):
        self._dub_manager().set_task_status(task_id, status)

    def _on_dub_result(self, task_id: str, flac: str):
        self.dub_store.update(task_id, last_result=flac)
        self._persist_dub_tasks(); self._dub_manager().refresh()

    def _on_dub_renamed(self, task_id, name):
        self.pages["dubbing"].update_task_name(task_id, name)

    # ------------------------------------------------------------------ #
    # 图片生成 tab helpers（移植自 MainWindow）
    # ------------------------------------------------------------------ #

    def _make_imggen_page(self):
        from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
        from drama_shot_master.ui.panels.imggen_task_manager_panel import ImgGenTaskManagerPanel
        from drama_shot_master.ui.panels.imggen_panel import ImgGenPanel

        manager = ImgGenTaskManagerPanel(
            self.state, self.cfg, self.imggen_store, None, None, self._persist_imggen_tasks)

        def editor_factory(task):
            return ImgGenPanel(self.cfg, payload=task.payload)

        def wire_editor(editor, task):
            tid = task.id
            editor.statusChanged.connect(lambda s: self._on_imggen_status(tid, s))
            editor.resultReady.connect(lambda p: self._on_imggen_result(tid, p))
            editor.dirty.connect(lambda: self._on_imggen_dirty(tid, editor.to_payload()))

        page = TaskWorkspacePage(
            manager=manager,
            editor_factory=editor_factory,
            wire_editor=wire_editor,
            payload_of=lambda ed: ed.to_payload(),
            on_persist=self._on_imggen_dirty,
            title_for=lambda task: f"图片生成 · {task.name}",
            detached_size=(720, 780),
        )
        manager.taskRenamed.connect(self._on_imggen_renamed)
        manager.taskDeleted.connect(page.discard_editor)
        return page

    def _imggen_manager(self):
        return self.pages["imggen"].manager

    def _persist_imggen_tasks(self):
        try:
            self.cfg.update_settings(imggen_tasks=self.imggen_store.to_list())
        except Exception:
            pass

    def _on_imggen_dirty(self, task_id: str, payload: dict):
        self.imggen_store.update(task_id, payload=payload)
        self._persist_imggen_tasks()

    def _on_imggen_status(self, task_id: str, status: str):
        self._imggen_manager().set_task_status(task_id, status)

    def _on_imggen_result(self, task_id: str, path: str):
        self.imggen_store.update(task_id, last_result=path)
        self._persist_imggen_tasks(); self._imggen_manager().refresh()

    def _on_imggen_renamed(self, task_id, name):
        self.pages["imggen"].update_task_name(task_id, name)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_titlebar_themed", False):
            self._titlebar_themed = True
            apply_window_icon(self)
            apply_titlebar(self, current_theme(self.cfg))

    def closeEvent(self, e):
        # 让视频任务页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        vp = self.pages.get("video_gen")
        if vp is not None and hasattr(vp, "flush_all"):
            vp.flush_all()
        self._persist_tasks()
        # 让配音任务页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        dp = self.pages.get("dubbing")
        if dp is not None and hasattr(dp, "flush_all"):
            dp.flush_all()
        self._persist_dub_tasks()
        # 让图片生成页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        ip = self.pages.get("imggen")
        if ip is not None and hasattr(ip, "flush_all"):
            ip.flush_all()
        self._persist_imggen_tasks()
        # 让配乐页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        sp = self.pages.get("soundtrack")
        if sp is not None and hasattr(sp, "flush_all"):
            sp.flush_all()
        self._persist_soundtrack()
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
