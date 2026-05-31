import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.app_shell import AppShell
from drama_shot_master.ui.nav_config import NAV_ITEMS, FUNCS, LABELS


def _app():
    return QApplication.instance() or QApplication([])


def _make_project(w, dirname):
    """造一个最小 project.json 并 load 进 UI（设 current_project_dir）。返回目录。"""
    import json
    import tempfile
    from pathlib import Path
    base = Path(tempfile.mkdtemp())
    pdir = base / dirname
    pdir.mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps({"project_id": dirname.split("_")[0],
                    "project_name": dirname}, ensure_ascii=False),
        encoding="utf-8",
    )
    w._load_project_into_ui(pdir)
    return pdir


def test_shell_constructs_and_registers_flat_nav_pages():
    """Wave2a：self.pages 为扁平 6 项；底层 8 页存 self._func_pages。"""
    _app()
    w = AppShell()
    w.show()
    QApplication.instance().processEvents()
    assert len(w.pages) == len(NAV_ITEMS)
    assert set(w.pages.keys()) == {k for _l, k in NAV_ITEMS}
    assert set(w._func_pages.keys()) == {k for _l, k in FUNCS}


def test_breadcrumb_for_known_pages():
    _app()
    w = AppShell()
    w.switchTo(w.pages["storyboard"])
    assert w.breadcrumb_text() == "分镜板 › 分镜板"
    w.switchTo(w.pages["screenwriter"])
    # 剧本创作：阶段标题前缀（兼容 phase_of）
    assert "剧本创作" in w.breadcrumb_text()


def test_batch_pages_are_batch_tool_page():
    _app()
    from drama_shot_master.ui.pages.batch_tool_page import BatchToolPage
    w = AppShell()
    # 底层批处理页迁入 _func_pages（嵌于分镜板容器 tab）
    for key in ("split", "combine", "trim"):
        assert isinstance(w._func_pages[key], BatchToolPage)


def test_storyboard_container_holds_func_tabs():
    """分镜板容器页含 出图/拆图/拼图/裁边 4 tab，且 widget 即底层 func 页。"""
    _app()
    from drama_shot_master.ui.pages.storyboard_page import StoryboardPage
    from drama_shot_master.ui.nav_config import STORYBOARD_TABS
    w = AppShell()
    sb = w.pages["storyboard"]
    assert isinstance(sb, StoryboardPage)
    assert sb.tabs.count() == len(STORYBOARD_TABS)
    for i, (k, _label) in enumerate(STORYBOARD_TABS):
        assert sb.tabs.widget(i) is w._func_pages[k]


def test_video_post_container_holds_func_tabs():
    """视频后期容器页含 配音/配乐 2 tab，widget 即底层 func 页。"""
    _app()
    from drama_shot_master.ui.pages.video_post_page import VideoPostPage
    from drama_shot_master.ui.nav_config import VIDEOPOST_TABS
    w = AppShell()
    vp = w.pages["video_post"]
    assert isinstance(vp, VideoPostPage)
    assert vp.tabs.count() == len(VIDEOPOST_TABS)
    for i, (k, _label) in enumerate(VIDEOPOST_TABS):
        assert vp.tabs.widget(i) is w._func_pages[k]


def test_overview_and_asset_library_pages():
    _app()
    from drama_shot_master.ui.pages.overview_page import OverviewPage
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    w = AppShell()
    assert isinstance(w.pages["overview"], OverviewPage)
    assert isinstance(w.pages["asset_library"], AssetLibraryPage)


def test_switching_every_nav_key_does_not_crash():
    """offscreen 下切换每个 nav_key 不崩，且 stack 当前页正确。"""
    _app()
    w = AppShell()
    for _label, key in NAV_ITEMS:
        w.sidebar.currentChanged.emit(key)
        assert w.stack.currentWidget() is w.pages[key]


def test_soundtrack_page_is_task_workspace():
    # 配乐已随 video/imggen/dub 迁移到 TaskWorkspacePage（详见 test_soundtrack_workspace_smoke）。
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
    w = AppShell()
    page = w._func_pages["soundtrack"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, SoundtrackPanel)


def test_open_dir_method_exists():
    _app()
    w = AppShell()
    assert hasattr(w, "_open_dir")


def test_shell_exposes_settings_and_about_entries():
    _app()
    w = AppShell()
    assert hasattr(w, "_open_unified_settings")
    assert hasattr(w, "_open_about")


def test_status_message_is_captured_not_dropped():
    _app()
    w = AppShell()
    w._set_status("hello")
    assert w._status_text == "hello"


def test_command_bar_present_with_dir_actions():
    _app()
    w = AppShell()
    assert w.command_bar is not None
    assert hasattr(w.command_bar, "btn_open_dir")
    assert hasattr(w.command_bar, "btn_set_output")


def test_command_bar_count_reflects_state():
    _app()
    w = AppShell()
    w._refresh_counts()
    assert "已选 0" in w.command_bar.count_text()


def test_command_bar_signals_wire_to_shell():
    _app()
    w = AppShell()
    # 信号存在且为已连接的入口（不弹真实文件框）
    assert hasattr(w, "_open_dir") and hasattr(w, "_set_out_dir")
    assert callable(w._open_dir) and callable(w._set_out_dir)
    # Headless-safe wiring proof: the real slots open a blocking QFileDialog,
    # so we never emit them while connected to AppShell. Instead disconnect the
    # shell slot, attach a spy, and confirm clicking the button emits the signal
    # (proving button.clicked -> signal wiring inside ProjectCommandBar). The
    # AppShell-side connection is re-established right after, with the spy
    # disconnected first so the signal ends with exactly its original wiring.
    try:
        w.command_bar.openDirRequested.disconnect(w._open_dir)
    except (RuntimeError, TypeError):
        pass
    fired = {}
    spy = lambda: fired.setdefault("open", True)
    w.command_bar.openDirRequested.connect(spy)
    w.command_bar.btn_open_dir.click()
    assert fired.get("open") is True
    # disconnect spy before re-attaching real slot → exactly 1 receiver
    try:
        w.command_bar.openDirRequested.disconnect(spy)
    except (RuntimeError, TypeError):
        pass
    w.command_bar.openDirRequested.connect(w._open_dir)
    assert w.command_bar.openDirRequested is not None


def test_switching_to_batch_page_syncs_selection_and_count():
    _app()
    w = AppShell()
    # 拆图批处理页迁入 _func_pages（嵌于分镜板容器 tab）
    split_page = w._func_pages["split"]
    w.stack.setCurrentWidget(w.pages["storyboard"])
    w.pages["storyboard"].set_current_tab("split")
    # 新构造、未选任何图 → 计数为 0
    w._on_page_changed()
    assert "已选 0" in w.command_bar.count_text()
    # selected_order 暴露在页与网格上
    assert split_page.selected_order() == []


def test_appshell_is_qmainwindow_and_fluent_free():
    import inspect
    from PySide6.QtWidgets import QMainWindow
    import drama_shot_master.ui.app_shell as m
    assert "qfluentwidgets" not in inspect.getsource(m)
    _app()
    w = m.AppShell()
    assert isinstance(w, QMainWindow)


def test_appshell_has_flow_sidebar():
    _app()
    from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar
    w = AppShell()
    assert isinstance(w.sidebar, FlowSidebar)


def test_sidebar_click_switches_page():
    _app()
    w = AppShell()
    w.sidebar.currentChanged.emit("video_gen")
    assert w.stack.currentWidget() is w.pages["video_gen"]
    # 视频生成属 production 阶段；标签从 nav_config 单一源读取（标签可由用户改名）
    assert w.breadcrumb_text() == f"③ 视频出片 › {LABELS['video_gen']}"


def test_video_page_is_task_workspace():
    _app()
    from drama_shot_master.ui.pages.task_workspace_page import TaskWorkspacePage
    from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
    w = AppShell()
    page = w.pages["video_gen"]
    assert isinstance(page, TaskWorkspacePage)
    assert isinstance(page.manager, VideoTaskManagerPanel)


def test_video_manager_accessor_returns_page_manager():
    _app()
    w = AppShell()
    assert w._video_manager() is w.pages["video_gen"].manager


def test_video_select_creates_editor_inline():
    _app()
    w = AppShell()
    page = w.pages["video_gen"]
    mgr = page.manager
    if not mgr.store.all():
        mgr.store.add("T1", {}); mgr.refresh()
    t = mgr.store.all()[0]
    mgr.taskSelected.emit(t)
    from drama_shot_master.ui.panels.video_panel import VideoPanel
    assert isinstance(page._editors[t.id], VideoPanel)


def test_task_center_dock_present_and_hidden_by_default():
    _app()
    from drama_shot_master.ui.widgets.task_center_dock import TaskCenterDock
    w = AppShell()
    assert hasattr(w, "task_center_dock")
    assert isinstance(w.task_center_dock, TaskCenterDock)
    # 默认隐藏
    assert w.task_center_dock.isVisible() is False


def test_activate_task_switches_page_and_selects():
    _app()
    w = AppShell()
    # 加一个 video task 后激活
    mgr = w._video_manager()
    if not mgr.store.all():
        mgr.store.add("T1", {})
        mgr.refresh()
    tid = mgr.store.all()[0].id
    w._activate_task("video", tid)
    assert w.stack.currentWidget() is w.pages["video_gen"]


def test_load_project_into_ui_drives_overview_and_gates(tmp_path):
    """Wave2b：_load_project_into_ui 接 compass —— 概览落页 + 侧栏门禁 + 资源库 set_project。

    造 tmp 项目（project.json：screenwriter=completed/assets=in_progress/
    storyboard=pending/production=pending）→ 调 _load_project_into_ui →
    断言落概览页、storyboard/production 锁、screenwriter/assets 可达、不崩。
    """
    import json
    _app()
    w = AppShell()
    pdir = tmp_path / "P-031_demo"
    pdir.mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps({
            "project_id": "P-031",
            "project_name": "门禁演示",
            "pipeline": {
                "screenwriter": {"state": "completed", "next_action": "进入素材"},
                "assets": {"state": "in_progress", "next_action": "准备角色参考"},
                "storyboard": {"state": "pending", "next_action": ""},
                "production": {"state": "pending", "next_action": ""},
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    w.cfg.pipeline_lock_enabled = True   # 显式开流程锁，测门禁行为
    w._load_project_into_ui(pdir)

    # 落在概览页
    assert w.stack.currentWidget() is w.pages["overview"]
    # 项目 scope 已回填，批处理 current_dir 未被污染（红线：物理分离）
    assert w.state.current_project_dir == pdir
    assert w.state.current_dir is None or w.state.current_dir != pdir
    # 侧栏门禁：screenwriter/assets 可达，storyboard/production 锁
    assert w.sidebar._buttons["screenwriter"].isEnabled()
    assert w.sidebar._buttons["asset_library"].isEnabled()
    assert not w.sidebar._buttons["storyboard"].isEnabled()
    assert not w.sidebar._buttons["video_gen"].isEnabled()
    assert not w.sidebar._buttons["video_post"].isEnabled()
    # 资源库已 set_project（_project_dir 落到该项目目录）
    assert w.pages["asset_library"]._project_dir == pdir
    # 下一步提示已挂（assets 阶段有文案）
    assert w.sidebar._next_action_labels["assets"].text() == "准备角色参考"


def test_pending_frontier_stage_is_accessible(tmp_path):
    """Wave2b 门禁修正（回归「资源库无法点击」bug）：前序完成则下一个 pending
    阶段（frontier）可达，不死锁。screenwriter=completed / assets=pending →
    资源库(assets) 应可点，storyboard/production 仍锁。
    """
    import json
    _app()
    w = AppShell()
    pdir = tmp_path / "P-040_frontier"
    pdir.mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps({
            "project_id": "P-040",
            "project_name": "frontier",
            "pipeline": {
                "screenwriter": {"state": "completed", "next_action": ""},
                "assets": {"state": "pending", "next_action": ""},
                "storyboard": {"state": "pending", "next_action": ""},
                "production": {"state": "pending", "next_action": ""},
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    w.cfg.pipeline_lock_enabled = True   # 显式开流程锁，测 frontier
    w._load_project_into_ui(pdir)
    assert w.sidebar._buttons["screenwriter"].isEnabled()
    assert w.sidebar._buttons["asset_library"].isEnabled()      # frontier，可达
    assert not w.sidebar._buttons["storyboard"].isEnabled()     # 前序未完成，锁
    assert not w.sidebar._buttons["video_gen"].isEnabled()
    assert not w.sidebar._buttons["video_post"].isEnabled()


def test_pipeline_lock_off_all_accessible(tmp_path):
    """流程锁关（默认）→ 全部阶段可达（便于快速调试）。"""
    import json
    _app()
    w = AppShell()
    assert getattr(w.cfg, "pipeline_lock_enabled", False) is False   # 默认关
    pdir = tmp_path / "P-050_unlocked"
    pdir.mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps({"project_id": "P-050", "project_name": "unlocked",
                    "pipeline": {"screenwriter": {"state": "completed"},
                                 "assets": {"state": "pending"},
                                 "storyboard": {"state": "pending"},
                                 "production": {"state": "pending"}}},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    w._load_project_into_ui(pdir)
    # 默认关 → 即便后续阶段 pending，也全部可点
    for key in ("screenwriter", "asset_library", "storyboard", "video_gen", "video_post"):
        assert w.sidebar._buttons[key].isEnabled()


def test_overview_stage_click_ignores_locked_page(tmp_path):
    """锁定阶段点击不跳到不可达页（忽略），可达阶段正常跳。"""
    import json
    _app()
    w = AppShell()
    pdir = tmp_path / "P-032_lock"
    pdir.mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps({
            "project_id": "P-032",
            "project_name": "锁定演示",
            "pipeline": {
                "screenwriter": {"state": "completed", "next_action": ""},
                "assets": {"state": "in_progress", "next_action": ""},
                "storyboard": {"state": "pending", "next_action": ""},
                "production": {"state": "pending", "next_action": ""},
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    w.cfg.pipeline_lock_enabled = True   # 显式开锁，测锁定阶段点击被忽略
    w._load_project_into_ui(pdir)
    # 起点：概览页
    assert w.stack.currentWidget() is w.pages["overview"]
    # 点锁定的 storyboard → 不跳（仍停概览）
    w._on_overview_stage("storyboard")
    assert w.stack.currentWidget() is w.pages["overview"]
    # 点可达的 assets → 跳资源库
    w._on_overview_stage("assets")
    assert w.stack.currentWidget() is w.pages["asset_library"]


def test_overview_genre_edit_wired(monkeypatch):
    """概览 genreEditRequested → 弹 GenrePickerDialog（mock）→ 写 project.json.params.genre。"""
    import json
    _app()
    w = AppShell()
    pdir = _make_project(w, "P-050_genre")

    # mock GenrePickerDialog：exec noop，result_value 返回固定题材
    import drama_shot_master.ui.dialogs.genre_picker_dialog as gpd

    class _FakeGenre:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 1

        def result_value(self):
            return {"genre": "short_drama", "sub": ["mv"]}

    monkeypatch.setattr(gpd, "GenrePickerDialog", _FakeGenre)
    w.pages["overview"].genreEditRequested.emit()

    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert data["params"]["genre"] == "short_drama"
    assert data["params"]["sub"] == ["mv"]


def test_overview_style_bible_edit_wired(monkeypatch):
    """概览 styleBibleEditRequested → 弹 StyleBibleDialog（mock）→ 写 style_bible。"""
    import json
    _app()
    w = AppShell()
    pdir = _make_project(w, "P-051_style")

    import drama_shot_master.ui.dialogs.style_bible_dialog as sbd

    class _FakeStyle:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 1

        def result_value(self):
            return {"ref": "real/cinematic-warm-v1", "category": "real"}

    monkeypatch.setattr(sbd, "StyleBibleDialog", _FakeStyle)
    w.pages["overview"].styleBibleEditRequested.emit()

    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert data["style_bible"]["ref"] == "real/cinematic-warm-v1"


def test_asset_generate_calls_ref_generator(monkeypatch):
    """资源库 generateRequested(name) → _on_asset_generate 构造 RefImageGenerator 并调 generate_ref。"""
    _app()
    w = AppShell()
    pdir = _make_project(w, "P-052_gen")

    calls = {}

    # patch RefImageGenerator（_make_ref_generator 内按模块属性 import）
    import drama_shot_master.services.ref_generator as rg

    def _fake_init(self, cfg, project_root, *, image_backend=None, **k):
        calls["project_root"] = project_root
        calls["has_backend"] = image_backend is not None

    def _fake_generate_ref(self, kind, name, base_prompt, style_id, **k):
        calls["kind"] = kind
        calls["name"] = name
        calls["style_id"] = style_id
        return (True, "/tmp/x.png")

    monkeypatch.setattr(rg.RefImageGenerator, "__init__", _fake_init)
    monkeypatch.setattr(rg.RefImageGenerator, "generate_ref", _fake_generate_ref)

    w.pages["asset_library"].generateRequested.emit("林晚")

    assert calls.get("name") == "林晚"
    assert calls.get("kind") == "characters"   # 默认首 tab
    assert calls.get("has_backend") is True


def test_new_project_writes_genre_and_style(monkeypatch, tmp_path):
    """新建项目向导（mock 两弹窗）→ project.json 写入 genre + style_bible。"""
    import json
    _app()
    w = AppShell()

    import drama_shot_master.ui.dialogs.genre_picker_dialog as gpd
    import drama_shot_master.ui.dialogs.style_bible_dialog as sbd

    class _FakeGenre:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 1

        def result_value(self):
            return {"genre": "short_drama", "sub": []}

    class _FakeStyle:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 1

        def result_value(self):
            return {"ref": "real/cinematic-warm-v1", "category": "real"}

    monkeypatch.setattr(gpd, "GenrePickerDialog", _FakeGenre)
    monkeypatch.setattr(sbd, "StyleBibleDialog", _FakeStyle)

    pdir = tmp_path / "P-060_new"
    pdir.mkdir(parents=True)
    w._init_new_project(pdir)

    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert data["params"]["genre"] == "short_drama"
    assert data["style_bible"]["ref"] == "real/cinematic-warm-v1"


def test_command_bar_toggle_task_center():
    _app()
    w = AppShell()
    w.show()
    QApplication.instance().processEvents()
    assert w.task_center_dock.isVisible() is False
    w.command_bar.btn_task_center.setChecked(True)
    QApplication.instance().processEvents()
    # toggled → setVisible(True)
    assert w.task_center_dock.isVisible() is True
    w.command_bar.btn_task_center.setChecked(False)
    QApplication.instance().processEvents()
    assert w.task_center_dock.isVisible() is False
