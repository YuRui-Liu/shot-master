"""AppShell：基于原生 QMainWindow 的流程式外壳。

侧栏(FlowSidebar)按 nav_config.PHASES 分阶段渲染 8 个真实功能页，顶部全局命令栏
横跨内容区；并把原 MainWindow 的控制器逻辑（任务窗回调、设置/帮助入口、授权巡检、
状态恢复/落盘）整体移植过来，使 AppShell 成为 MainWindow 的完整 drop-in 替代。

main_window.py 暂作为 fallback 保留（后续阶段移除），逻辑事实源仍以其为准。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QMenu,
)
from PySide6.QtGui import QAction, QCursor
from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
from drama_shot_master.ui.widgets.project_command_bar import ProjectCommandBar
from drama_shot_master.ui.theme import apply_window_icon, apply_titlebar, current_theme
from drama_shot_master.ui import nav_config
from drama_shot_master.ui.nav_config import NAV_ITEMS, LABELS


class AppShell(QMainWindow):
    def __init__(self, cfg=None):
        super().__init__()
        self.setWindowTitle("糯米AI分镜影视创作台")
        self.resize(1360, 860)
        # self.pages: 扁平 nav_key → 页（含容器页）。键序=NAV_ITEMS。
        self.pages = {}
        # self._func_pages: 底层 8 个真实 panel 页（key 不变），供接线/任务激活取 manager。
        self._func_pages = {}
        # nav_key → 面包屑前缀（阶段标题 / NAV 显示名）；phase_of 兼容扁平 key。
        self._phase_of = {k: nav_config.phase_of(k) for _l, k in NAV_ITEMS}
        self._status_text = ""
        # main.py 传入已 spawn 过 lifecycle 并反写过端口的 cfg；
        # 没传则 _build_pages 自己 load_config() 兜底（兼容旧入口）
        self._injected_cfg = cfg
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

        self.cfg = self._injected_cfg if self._injected_cfg is not None else load_config()
        from drama_shot_master.core.recent_projects import RecentProjectsManager
        settings_path = self.cfg.settings_path if self.cfg.settings_path else Path("settings.json")
        self.recent_mgr = RecentProjectsManager.alongside_settings(Path(settings_path))
        self.state = AppState()
        self.video_store = VideoTaskStore.from_list(self.cfg.video_tasks)
        self.dub_store = DubTaskStore.from_list(self.cfg.dub_tasks)
        self.imggen_store = ImgGenTaskStore.from_list(self.cfg.imggen_tasks)

        builders = {
            "screenwriter": self._make_screenwriter_page,    # 编剧 Agent
            "split":   lambda: BatchToolPage(SplitPanel(self.state, self.cfg), self.state, self.cfg),
            "combine": lambda: BatchToolPage(CombinePanel(self.state, self.cfg), self.state, self.cfg),
            "trim":    lambda: BatchToolPage(TrimPanel(self.state, self.cfg), self.state, self.cfg),
            "imggen":  self._make_imggen_page,
            "video_gen": self._make_video_page,
            "soundtrack": self._make_soundtrack_page,
            "dubbing": self._make_dub_page,
        }
        # 1) 构造 8 个底层真实页存入 self._func_pages（key 不变）。
        from drama_shot_master.ui.nav_config import FUNCS
        for _label, key in FUNCS:
            page = builders[key]()
            page.setObjectName(f"page_{key}")   # 稳定 objectName，便于 QSS 选择与 findChild
            self._func_pages[key] = page

        # 2) 组装容器页 / 新页。
        from drama_shot_master.ui.pages.storyboard_page import StoryboardPage
        from drama_shot_master.ui.pages.video_post_page import VideoPostPage
        from drama_shot_master.ui.pages.overview_page import OverviewPage
        from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage

        storyboard = StoryboardPage()
        storyboard.set_tabs([
            (k, label, self._func_pages[k]) for k, label in nav_config.STORYBOARD_TABS
        ])
        video_post = VideoPostPage()
        video_post.set_tabs([
            (k, label, self._func_pages[k]) for k, label in nav_config.VIDEOPOST_TABS
        ])
        overview = OverviewPage()
        asset_library = AssetLibraryPage()

        # 3) 扁平导航页字典（键序=NAV_ITEMS）。剧本创作/视频生成直接复用底层页。
        self.pages = {
            "overview": overview,
            "screenwriter": self._func_pages["screenwriter"],
            "asset_library": asset_library,
            "storyboard": storyboard,
            "video_gen": self._func_pages["video_gen"],
            "video_post": video_post,
        }
        for _label, key in NAV_ITEMS:
            self.pages[key].setObjectName(f"page_{key}")

    def _build_ui(self):
        self.command_bar = ProjectCommandBar()
        self.sidebar = FlowSidebar()
        self.stack = QStackedWidget()
        for _label, key in NAV_ITEMS:
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
        from drama_shot_master.ui.pages.welcome_page import WelcomePage
        self.welcome_page = WelcomePage(self.recent_mgr)
        self.outer_stack = QStackedWidget()
        self.outer_stack.addWidget(self.welcome_page)   # index 0
        self.outer_stack.addWidget(main_ui)             # index 1
        self.setCentralWidget(self.outer_stack)

        # 任务中心 dock
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
        # 当用户从 dock 标题栏 X 直接关掉时，持久化 visibility（_toggle_task_center
        # 走 toggled 信号路径，不覆盖此场景）
        self.task_center_dock.visibilityChanged.connect(self._persist_dock_visibility)

    def _wire(self):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        # 遍历底层 8 页（含嵌套在容器页里的）接 statusMessage / 网格选择。
        for page in self._func_pages.values():
            # BatchToolPage→page.panel；TaskWorkspacePage→page.manager；manager 页→page 本身
            panel = getattr(page, "panel", None)
            src = panel if panel is not None else getattr(page, "manager", page)
            if hasattr(src, "statusMessage"):
                src.statusMessage.connect(self._set_status)
            if isinstance(page, BatchToolPage):
                page.thumb.selectionChanged.connect(self._refresh_counts)

        # 概览页：阶段卡点击 → 跳对应 nav 页；风格圣经编辑暂 noop 日志。
        overview = self.pages.get("overview")
        if overview is not None:
            if hasattr(overview, "stageActivated"):
                overview.stageActivated.connect(self._on_overview_stage)
            if hasattr(overview, "styleBibleEditRequested"):
                overview.styleBibleEditRequested.connect(
                    lambda: self._log_noop("styleBibleEditRequested"))
        # 资源库三信号暂 noop 日志（Wave2b 接后端）。
        al = self.pages.get("asset_library")
        if al is not None:
            for sig_name in ("importRequested", "extractRequested"):
                sig = getattr(al, sig_name, None)
                if sig is not None:
                    sig.connect(lambda n=sig_name: self._log_noop(n))
            if hasattr(al, "generateRequested"):
                al.generateRequested.connect(
                    lambda name: self._log_noop(f"generateRequested({name})"))

        self.sidebar.currentChanged.connect(self._on_nav_changed)
        self.sidebar.settingsRequested.connect(self._open_unified_settings)
        self.sidebar.helpRequested.connect(self._open_help_menu)
        self.command_bar.openDirRequested.connect(self._open_dir)
        self.command_bar.setOutputRequested.connect(self._set_out_dir)
        self.stack.currentChanged.connect(self._on_page_changed)

        # 任务中心 toggle：用户点按钮 → 我们包一层处理（先记 geom 再切显隐 → 再还原），
        # 不直接连 dock.setVisible，避免 dock 撑窗后 visibilityChanged 抓到的几何不是用户原始尺寸。
        self.command_bar.taskCenterToggled.connect(self._toggle_task_center)
        # 同步按钮 checked 状态（用户从 dock 标题栏 X 关闭时也要同步按钮态）
        self.task_center_dock.visibilityChanged.connect(
            self.command_bar.btn_task_center.setChecked)

        # 欢迎页信号连接
        self.welcome_page.project_selected.connect(self._on_welcome_project_selected)
        self.welcome_page.new_project_requested.connect(self._on_welcome_new_project)
        self.welcome_page.open_dir_requested.connect(self._open_dir)
        self.welcome_page.settings_requested.connect(self._open_unified_settings)
        self.sidebar.homeRequested.connect(self.show_welcome)

    # ------------------------------------------------------------------ #
    # 欢迎首页 ↔ 主界面 切换
    # ------------------------------------------------------------------ #

    def show_welcome(self) -> None:
        """从主界面返回欢迎首页（无动画，即时切换）。"""
        self.welcome_page.refresh()
        # 恢复侧边栏正常宽度（可能被 slide-in 动画改成 0）
        from drama_shot_master.ui.widgets.flow_sidebar import EXPANDED_W
        self.sidebar.setMinimumWidth(EXPANDED_W)
        self.sidebar.setMaximumWidth(EXPANDED_W)
        self.outer_stack.setCurrentIndex(0)

    def _on_welcome_project_selected(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            self.welcome_page.refresh()   # 目录已消失，刷新列表
            return
        self._enter_main_ui()
        # 打开项目走 罗盘项目 scope（load_project + 概览 + 门禁），
        # 不再用批处理 _open_dir_path 污染 current_dir（红线：物理分离）。
        self._load_project_into_ui(p)

    def _on_welcome_new_project(self) -> None:
        from PySide6.QtCore import QTimer
        self._enter_main_ui()
        # 让 slide-in 先动起来，再弹模态目录对话框（避免动画与模态事件循环抢首帧）
        QTimer.singleShot(60, self._new_project_pick_dir)

    def _new_project_pick_dir(self) -> None:
        """新建项目：选目录 → 无 project.json 则 allocate_id + 初始 manifest +
        register（registry 在项目父目录 projects_root）→ 载入 UI。

        已有 project.json → 直接载入。任何异常降级不崩（最差仅不登记/不建 manifest）。
        """
        from PySide6.QtWidgets import QFileDialog
        start = str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "新建 / 选择项目目录", start)
        if not d:
            return
        project_dir = Path(d)
        try:
            from drama_shot_master.core.compass.paths import (
                manifest_path, registry_index_path,
            )
            if not manifest_path(project_dir).is_file():
                self._init_new_project(project_dir)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "新建项目初始化失败，降级直接载入", exc_info=True)
        self._load_project_into_ui(project_dir)

    def _init_new_project(self, project_dir: Path) -> None:
        """为无 project.json 的目录分配 ID、写初始 manifest 并登记进注册表。

        registry 路径取项目父目录（projects_root）；name 取目录名（去 ID 前缀兜底）。
        """
        from drama_shot_master.core.compass.manifest import (
            ProjectManifest, save_manifest,
        )
        from drama_shot_master.core.compass.registry import ProjectRegistry
        from drama_shot_master.core.compass.paths import registry_index_path

        projects_root = project_dir.parent
        registry = ProjectRegistry(registry_index_path(projects_root))
        project_id = registry.allocate_id()
        # 项目名：目录名去掉 P-NNN_ 前缀（无前缀则用整名）。
        name = project_dir.name
        if "_" in name and name.split("_", 1)[0].startswith("P-"):
            name = name.split("_", 1)[1]
        manifest = ProjectManifest(project_id=project_id, project_name=name)
        save_manifest(manifest, project_dir)
        registry.register({
            "project_id": project_id,
            "project_name": name,
            "dir": project_dir.name + "/",
            "status": manifest.status,
            "episode_count": 0,
        })
        registry.save()

    # ------------------------------------------------------------------ #
    # 罗盘项目 scope 接线（Wave2b）：概览仪表盘 + 侧栏门禁
    # ------------------------------------------------------------------ #

    def _load_project_into_ui(self, project_dir: Path) -> None:
        """把一个项目目录接上 UI：概览 manifest / 资源库 / 门禁 / 下一步 / 落概览页。

        - state.load_project 回填 pipeline_state/next_action（项目 scope，
          与批处理 current_dir 物理分离）。
        - 概览页 set_manifest 需完整 manifest 对象——load_project 不返回 manifest，
          故此处另用 compass load_manifest/migrate 拿完整对象。
        全程异常降级不崩。
        """
        project_dir = Path(project_dir)
        self.state.load_project(project_dir)
        manifest = self._load_manifest_for(project_dir)
        overview = self.pages.get("overview")
        if overview is not None and hasattr(overview, "set_manifest"):
            overview.set_manifest(manifest)
        al = self.pages.get("asset_library")
        if al is not None and hasattr(al, "set_project"):
            al.set_project(project_dir)
        self._sync_nav_gates()
        self._display_next_actions()
        # 打开项目落在概览页。
        overview = self.pages.get("overview")
        if overview is not None:
            self.switchTo(overview)

    def _load_manifest_for(self, project_dir: Path):
        """拿完整 ProjectManifest：有 project.json → load_manifest，无 → migrate。

        load_project 只存 pipeline_state/next_action 不存 manifest 对象，
        概览 set_manifest 需完整对象，故单独取。异常 → None（概览 getattr 兜底）。
        """
        try:
            from drama_shot_master.core.compass.manifest import load_manifest
            from drama_shot_master.core.compass.migrate import migrate_project_dir
            from drama_shot_master.core.compass.paths import manifest_path
            if manifest_path(project_dir).is_file():
                return load_manifest(project_dir)
            return migrate_project_dir(project_dir)
        except Exception:
            return None

    def _sync_nav_gates(self) -> None:
        """按 pipeline_state 设侧栏阶段门禁（前序完成即解锁下一阶段 frontier）。

        可访问：已完成 / 进行中 的阶段，以及紧随「最后一个已完成阶段」之后的
        **下一个待做**阶段（否则 pending 阶段永远点不进去 → 死锁，用户无法开始）。
        再往后的阶段仍锁定。screenwriter 为入口恒可达。遍历 STAGE_NAMES，未知阶段静默。
        """
        from drama_shot_master.core.compass.manifest import STAGE_NAMES
        prev_completed = True  # 入口前视为已完成 → screenwriter 恒可达
        for stage in STAGE_NAMES:
            st = self.state.pipeline_state.get(stage)
            accessible = prev_completed or st in ("in_progress", "completed")
            self.sidebar.set_phase_accessible(stage, accessible)
            prev_completed = (st == "completed")

    def _display_next_actions(self) -> None:
        """按 next_action 逐阶段在侧栏挂「下一步」小字提示（空则隐藏）。"""
        from drama_shot_master.core.compass.manifest import STAGE_NAMES
        for stage in STAGE_NAMES:
            self.sidebar.set_next_action(
                stage, self.state.next_action.get(stage, ""))

    def _enter_main_ui(self) -> None:
        """切到主界面：内容区淡入 + 侧边栏从 0 滑入（300ms）。

        不再对欢迎页做 fade-to-transparent —— 那会露出窗口黑底形成闪烁，
        且欢迎页子卡片自带 graphicsEffect，父级再叠 OpacityEffect 渲染不稳定。
        """
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QAbstractAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from drama_shot_master.ui.widgets.flow_sidebar import EXPANDED_W

        self.welcome_page.setGraphicsEffect(None)
        self.outer_stack.setCurrentIndex(1)

        # 侧边栏 slide-in：0 → EXPANDED_W
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(0)
        slide = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        slide.setDuration(300)
        slide.setStartValue(0)
        slide.setEndValue(EXPANDED_W)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        slide.finished.connect(self._finish_sidebar_slide)
        slide.start(QAbstractAnimation.DeleteWhenStopped)
        self._slide_anim = slide

        # 内容区淡入（对 main_ui 容器加 opacity，其子控件无自带 effect，安全）
        main_ui = self.outer_stack.widget(1)
        fade_fx = QGraphicsOpacityEffect(main_ui)
        main_ui.setGraphicsEffect(fade_fx)
        fade = QPropertyAnimation(fade_fx, b"opacity", self)
        fade.setDuration(260)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.finished.connect(lambda: main_ui.setGraphicsEffect(None))
        fade.start(QAbstractAnimation.DeleteWhenStopped)
        self._fade_anim = fade

    def _finish_sidebar_slide(self) -> None:
        from drama_shot_master.ui.widgets.flow_sidebar import EXPANDED_W
        self.sidebar.setMinimumWidth(EXPANDED_W)
        self.sidebar.setMaximumWidth(EXPANDED_W)

    def _open_dir_path(self, path) -> None:
        """加载指定目录（复用 _open_dir 的实际加载逻辑，无对话框）。"""
        from drama_shot_master.ui.state import remember_dirs
        p = Path(path)
        self.state.load_dir(p)
        self._populate_batch_pages()
        remember_dirs(self.state, self.cfg)
        self.command_bar.set_dir(f"{self.state.current_dir}")
        self._refresh_counts()
        self._set_status(f"已加载 {len(self.state.images)} 张")
        self.recent_mgr.push(str(p))

    def _on_nav_changed(self, key: str):
        page = self.pages.get(key)
        if page is not None:
            self.switchTo(page)

    def _on_overview_stage(self, stage_or_key: str):
        """概览阶段卡 → 跳对应扁平 nav 页。

        概览卡 stage_key 用 compass stage 命名（screenwriter/assets/storyboard/
        production），映射到 self.pages 的 nav_key；production 默认去 video_gen。
        若已是合法 nav_key（如直接传 video_post）则原样使用。
        """
        mapping = {
            "screenwriter": "screenwriter",
            "assets": "asset_library",
            "storyboard": "storyboard",
            "production": "video_gen",
        }
        nav_key = mapping.get(stage_or_key, stage_or_key)
        page = self.pages.get(nav_key)
        if page is None:
            return
        # 门禁：若该 nav 项被锁（侧栏按钮 disabled），不跳到不可达页（忽略点击）。
        btn = self.sidebar._buttons.get(nav_key)
        if btn is not None and not btn.isEnabled():
            return
        self.switchTo(page)

    def _log_noop(self, what: str):
        """Wave2b 前的占位：信号到达仅记日志，不接后端。"""
        import logging
        logging.getLogger(__name__).info("nav signal noop: %s", what)

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
        # 恢复上次活跃功能页（默认概览）
        target_key = self.cfg.last_active_function
        key = target_key if target_key in self.pages else "overview"
        self.switchTo(self.pages[key])
        # 启动时始终先显示欢迎页
        self.welcome_page.refresh()
        self.outer_stack.setCurrentIndex(0)

    def _refresh_counts(self, *args):
        self.command_bar.set_count(
            f"{len(self.state.images)} 张  已选 {len(self.state.selected)}")

    def _populate_batch_pages(self):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        for page in self._func_pages.values():
            if isinstance(page, BatchToolPage):
                page.populate(self.state.images)

    def _refresh_batch_validity(self):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        for page in self._func_pages.values():
            if isinstance(page, BatchToolPage):
                page.refresh_validity()

    # ------------------------------------------------------------------ #
    # 导航 / 面包屑 / 状态面
    # ------------------------------------------------------------------ #

    def _current_key(self) -> str:
        return self._key_of(self.stack.currentWidget()) or "overview"

    def breadcrumb_text(self) -> str:
        key = self._current_key()
        prefix = self._phase_of.get(key) or nav_config.phase_of(key) or ""
        return f"{prefix} › {LABELS.get(key, '')}"

    def _set_status(self, msg):
        self._status_text = msg

    def _on_page_changed(self, *args):
        from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
        page = self.stack.currentWidget()
        if isinstance(page, BatchToolPage):
            self.state.selected = page.selected_order()
        self._refresh_counts()

    def _activate_task(self, kind: str, tid: str):
        # kind → (nav_key, 容器内 tab key 或 None, 底层 func_page key)
        routing = {
            "video":      ("video_gen", None, "video_gen"),
            "imggen":     ("storyboard", "imggen", "imggen"),
            "dub":        ("video_post", "dubbing", "dubbing"),
            "soundtrack": ("video_post", "soundtrack", "soundtrack"),
        }
        route = routing.get(kind)
        if route is None:
            return
        nav_key, tab_key, func_key = route
        nav_page = self.pages.get(nav_key)
        if nav_page is None:
            return
        self.switchTo(nav_page)
        # 容器页：切到对应 tab
        if tab_key is not None and hasattr(nav_page, "set_current_tab"):
            nav_page.set_current_tab(tab_key)
        # manager 从底层页取
        func_page = self._func_pages.get(func_key)
        mgr = getattr(func_page, "manager", None) if func_page is not None else None
        if mgr is not None and hasattr(mgr, "_select_task"):
            mgr._select_task(tid)

    def _persist_dock_visibility(self, v: bool):
        """dock 标题栏 X 直接关掉时也要落盘可见性。"""
        try:
            self.cfg.update_settings(task_center_visible=bool(v))
        except Exception:
            pass

    def _toggle_task_center(self, want_visible: bool):
        """toggle 任务中心 dock 显隐 + 维持主窗尺寸。

        Qt QMainWindow 在 dock 显示后可能自动撑宽主窗（如果 central widget
        没有富余宽度容纳 dock），dock 隐藏时主窗 width 又不会自动缩回 ——
        所以需要在打开前**先抓**几何、关闭后**再还原**。

        关键：在 dock.setVisible(True) 之前抓 self.size()，不能在
        visibilityChanged 信号里抓（那时主窗可能已被撑宽）。最大化/全屏窗
        不动用户布局。
        """
        try:
            self.cfg.update_settings(task_center_visible=bool(want_visible))
        except Exception:
            pass

        if want_visible:
            # 打开前抓尺寸（仅非最大化/全屏时）
            if not (self.isMaximized() or self.isFullScreen()):
                if not getattr(self, "_pre_dock_size", None):
                    self._pre_dock_size = self.size()
            self.task_center_dock.setVisible(True)
        else:
            self.task_center_dock.setVisible(False)
            # 收回时还原原始 size（用 resize，不动 position；
            # 走 singleShot 等 Qt 把 dock layout 真正拆掉再 resize 才生效）
            pre = getattr(self, "_pre_dock_size", None)
            if pre is not None and not (self.isMaximized() or self.isFullScreen()):
                from PySide6.QtCore import QTimer
                QTimer.singleShot(
                    0, lambda s=pre: self.resize(s.width(), s.height()))
            self._pre_dock_size = None

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
        if self.state.current_dir:
            self.recent_mgr.push(str(self.state.current_dir))

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
        return self._func_pages["video_gen"].manager

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
        if hasattr(self, 'task_center_dock'):
            self.task_center_dock.refresh()

    def _on_task_result(self, task_id: str, mp4: str):
        self.video_store.update(task_id, last_result=mp4)
        self._persist_tasks()
        self._video_manager().refresh()
        if hasattr(self, 'task_center_dock'):
            self.task_center_dock.refresh()

    def _on_task_renamed(self, task_id: str, name: str):
        page = self._func_pages.get("video_gen")
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
        p = self._func_pages.get("soundtrack")
        return getattr(p, "manager", None)

    def _on_soundtrack_dirty(self, task_id: str, payload: dict):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t.update(payload)        # mp4/style/output_dir
                break
        self._persist_soundtrack()

    def _on_soundtrack_renamed(self, task_id: str, name: str):
        page = self._func_pages.get("soundtrack")
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
        if hasattr(self, "task_center_dock"):
            self.task_center_dock.refresh()

    def _on_soundtrack_result(self, task_id: str, output: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["output"] = output
                break
        self._persist_soundtrack()
        m = self._soundtrack_panel()
        if m is not None and hasattr(m, "refresh"):
            m.refresh()
        if hasattr(self, "task_center_dock"):
            self.task_center_dock.refresh()

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
        return self._func_pages["dubbing"].manager

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
        if hasattr(self, 'task_center_dock'):
            self.task_center_dock.refresh()

    def _on_dub_result(self, task_id: str, flac: str):
        self.dub_store.update(task_id, last_result=flac)
        self._persist_dub_tasks(); self._dub_manager().refresh()
        if hasattr(self, 'task_center_dock'):
            self.task_center_dock.refresh()

    def _on_dub_renamed(self, task_id, name):
        self._func_pages["dubbing"].update_task_name(task_id, name)

    # ------------------------------------------------------------------ #
    # 编剧 Agent page（Task 22）
    # ------------------------------------------------------------------ #

    def _make_screenwriter_page(self):
        from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel
        # 任务栏化后，ScreenwriterPanel 仅需 cfg——内部自建 ScreenwriterClient
        # （从 cfg.screenwriter_agent_port 取端口）；lifecycle/state 不再注入。
        return ScreenwriterPanel(self.cfg)

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
        return self._func_pages["imggen"].manager

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
        if hasattr(self, 'task_center_dock'):
            self.task_center_dock.refresh()

    def _on_imggen_result(self, task_id: str, path: str):
        self.imggen_store.update(task_id, last_result=path)
        self._persist_imggen_tasks(); self._imggen_manager().refresh()
        if hasattr(self, 'task_center_dock'):
            self.task_center_dock.refresh()

    def _on_imggen_renamed(self, task_id, name):
        self._func_pages["imggen"].update_task_name(task_id, name)

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
        vp = self._func_pages.get("video_gen")
        if vp is not None and hasattr(vp, "flush_all"):
            vp.flush_all()
        self._persist_tasks()
        # 让配音任务页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        dp = self._func_pages.get("dubbing")
        if dp is not None and hasattr(dp, "flush_all"):
            dp.flush_all()
        self._persist_dub_tasks()
        # 让图片生成页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        ip = self._func_pages.get("imggen")
        if ip is not None and hasattr(ip, "flush_all"):
            ip.flush_all()
        self._persist_imggen_tasks()
        # 让配乐页落盘所有缓存编辑器（含已浮出窗），再整体持久化
        sp = self._func_pages.get("soundtrack")
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
