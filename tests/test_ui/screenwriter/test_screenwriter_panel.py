"""ScreenwriterPanel 装配的端到端测试。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.panels.screenwriter_panel import ScreenwriterPanel


def _app():
    return QApplication.instance() or QApplication([])


class _StubCfg:
    def __init__(self, projects=None, root=""):
        self.screenwriter_projects = list(projects or [])
        self.screenwriter_project_root = root
        self.screenwriter_agent_port = 18999
        self.screenwriter_stage_assignments = {}
        self.screenwriter_llm_api_key = ""
        self.screenwriter_llm_base_url = ""
        self.llm_providers = {}
        self._saved = {}

    def update_settings(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._saved.update(kw)


def test_panel_builds_with_splitter_and_4_pages():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    assert panel._task_manager is not None
    assert panel._wizard_host is not None
    assert panel._wizard_host._stack.count() == 4


def test_task_selection_propagates_to_all_pages(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)
    # 模拟用户选第 0 行
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    # 4 个 page 的 _project_dir 都应是 pA
    for i in range(4):
        page = panel._wizard_host._stack.widget(i)
        # PromptsPage placeholder 可能是 QLabel，没有 _project_dir
        if hasattr(page, "_project_dir"):
            assert page._project_dir == pA


def test_stage_stepper_unconditional_switch():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    panel._wizard_host.set_stage(2)
    assert panel._wizard_host._stack.currentIndex() == 2
    panel._wizard_host.set_stage(0)
    assert panel._wizard_host._stack.currentIndex() == 0


def test_dirty_page_blocks_task_switch(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    panel = ScreenwriterPanel(cfg)
    # 先选 A
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    # 注入：让所有 page 的 try_release 返 False
    for i in range(4):
        page = panel._wizard_host._stack.widget(i)
        if hasattr(page, "try_release"):
            page.try_release = lambda: False  # type: ignore
    # 试着切到 B
    panel._task_manager._table.selectRow(1)
    panel._task_manager._on_selection_changed()
    # 各 page 的 _project_dir 仍是 pA（切换被拒）
    for i in range(4):
        page = panel._wizard_host._stack.widget(i)
        if hasattr(page, "_project_dir"):
            assert page._project_dir == pA


def test_active_worker_query_aggregates_across_pages(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)
    # 默认无 worker → False
    assert panel._any_page_streaming(pA) is False
    # 给 IdeatePage 注入 mock
    page = panel._wizard_host._stack.widget(0)
    class _W:
        def isRunning(self): return True
    page._workers[pA] = _W()
    assert panel._any_page_streaming(pA) is True


def test_two_projects_streaming_concurrently_keeps_both_workers(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    panel = ScreenwriterPanel(cfg)

    ideate = panel._pages[0]  # IdeatePage
    storyboard = panel._pages[2]  # StoryboardPage

    class _W:
        def __init__(self): self._running = True
        def isRunning(self): return self._running
        def stop(self): self._running = False

    # 在 IdeatePage 给 A 灌 worker
    wA = _W()
    ideate._workers[pA] = wA
    # 在 StoryboardPage 给 B 灌 worker
    wB = _W()
    storyboard._workers[pB] = wB

    # 选 A
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    # A 的 worker 显示在 IdeatePage
    assert ideate._project_dir == pA
    assert ideate._active_worker() is wA

    # 切到 B
    panel._task_manager._table.selectRow(1)
    panel._task_manager._on_selection_changed()
    # A 的 worker 没死
    assert wA.isRunning() is True
    # B 的 worker 仍在 StoryboardPage
    assert wB.isRunning() is True
    # 当前显示 B
    assert ideate._project_dir == pB
    assert storyboard._project_dir == pB


def test_external_dir_removal_prunes_on_refresh(tmp_path):
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    pB = tmp_path / "B"; pB.mkdir()
    cfg = _StubCfg(projects=[str(pA), str(pB)])
    panel = ScreenwriterPanel(cfg)
    # 外部删 A
    import shutil
    shutil.rmtree(pA)
    panel._task_manager.refresh()
    assert str(pA) not in cfg.screenwriter_projects
    assert str(pB) in cfg.screenwriter_projects


def test_prompts_page_is_real_not_placeholder():
    _app()
    panel = ScreenwriterPanel(_StubCfg())
    # 第 4 个 page 应该是 PromptsPage（不是 placeholder QLabel）
    from drama_shot_master.ui.widgets.screenwriter.prompts_page import PromptsPage
    assert isinstance(panel._pages[3], PromptsPage)


def test_stage_advance_triggers_auto_generation_on_target_page(tmp_path):
    """Bug regression：用户点'推进'后，下一阶段不应只切换 stack，还应该
    自动触发 LLM 生成（如果上游已就绪、本阶段产物缺失、且 idle 状态）。"""
    import json as _json
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    (pA / "创意.json").write_text(_json.dumps({
        "selected_id": "c1",
        "candidates": [{"id": "c1", "title": "守株待兔"}],
    }), encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    # Mock 下一阶段 page 的 start_generation_if_idle
    called = []
    panel._pages[1].start_generation_if_idle = lambda: called.append(True)
    # IdeatePage emit stageAdvanceRequested(1)
    panel._pages[0].stageAdvanceRequested.emit(1)
    # 1) wizard 切到 stage 1（ScriptPage）
    assert panel._wizard_host._stack.currentIndex() == 1
    # 2) start_generation_if_idle 被调
    assert called == [True], "stageAdvanceRequested 应同时触发下一 page 自动生成"


def test_stage_advance_target_with_existing_output_skips_auto_gen(tmp_path):
    """已有 剧本.md 时再点'推进'：切到 ScriptPage 但不强制再生（避免覆盖）。"""
    _app()
    pA = tmp_path / "A"; pA.mkdir()
    (pA / "创意.json").write_text("{}", encoding="utf-8")
    (pA / "剧本.md").write_text("# 已有剧本", encoding="utf-8")
    cfg = _StubCfg(projects=[str(pA)])
    panel = ScreenwriterPanel(cfg)
    panel._task_manager._table.selectRow(0)
    panel._task_manager._on_selection_changed()
    called = []
    panel._pages[1].start_generation_if_idle = lambda: called.append(True)
    panel._pages[0].stageAdvanceRequested.emit(1)
    # ScriptPage.start_generation_if_idle 应自检：剧本.md 存在 → 不调 _on_generate
    # 但 panel 仍调它（page 自己决定 skip）；测的是 panel 在切换后调了
    assert called == [True]
