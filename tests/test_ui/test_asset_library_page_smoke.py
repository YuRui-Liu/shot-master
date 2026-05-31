# tests/test_ui/test_asset_library_page_smoke.py
"""资源库新页 smoke：offscreen QApplication，tmp project_dir 造三类 ref_index.json。

覆盖：set_project 后三 tab 卡片数正确、完备性条数字正确、
工具栏按钮发对应信号（QSignalSpy）、空/缺失目录降级不崩。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QSignalSpy


def _app():
    return QApplication.instance() or QApplication([])


def _write_ref_index(project_dir: Path, kind: str, refs: list[dict]) -> None:
    """在 <project>/<kind>/ref_index.json 落盘一份索引。"""
    d = project_dir / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / "ref_index.json").write_text(
        json.dumps({"schema_version": 1, "refs": refs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """造 characters/scenes/props 三类索引：含 ready/generating/empty 三态。"""
    # 角色：2 ready + 1 generating + 1 empty = 4 条，2 就绪
    _write_ref_index(tmp_path, "characters", [
        {"name": "周翠英", "path": "周翠英_ref.png", "source": "custom", "status": "ready"},
        {"name": "沈墨", "path": "沈墨_ref.png", "source": "custom", "status": "ready"},
        {"name": "陆夫人", "path": "", "source": "ai-generated", "status": "generating"},
        {"name": "管家老张", "path": "", "source": "", "status": "empty"},
    ])
    # 场景：1 ready + 1 empty = 2 条，1 就绪
    _write_ref_index(tmp_path, "scenes", [
        {"name": "宅院", "path": "宅院_ref.png", "source": "custom", "status": "ready"},
        {"name": "后厨", "path": "", "source": "", "status": "empty"},
    ])
    # 道具：1 ready = 1 条，1 就绪
    _write_ref_index(tmp_path, "props", [
        {"name": "玉佩", "path": "玉佩_ref.png", "source": "custom", "status": "ready"},
    ])
    return tmp_path


def test_set_project_fills_three_tabs_card_counts(project_dir):
    _app()
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    page = AssetLibraryPage()
    page.set_project(project_dir)
    # 三 tab 卡片数 = 各 ref_index 条目数
    assert page.card_count("characters") == 4
    assert page.card_count("scenes") == 2
    assert page.card_count("props") == 1


def test_completeness_bar_numbers(project_dir):
    _app()
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    page = AssetLibraryPage()
    page.set_project(project_dir)
    # 总 7 条，就绪 4（3 ready 落盘存在 + ...），缺图 3
    # completeness_check 看 status!=ready 与文件存在；这里 path 文件未真实落盘
    # → 就绪计数按 status==ready 的条目数（4），缺图 = 总 - 就绪（3）
    ready, total = page.completeness()
    assert total == 7
    assert ready == 4
    assert page.missing_count() == 3
    text = page.completeness_text()
    assert "4" in text and "7" in text


def test_card_status_mapping(project_dir):
    _app()
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    page = AssetLibraryPage()
    page.set_project(project_dir)
    statuses = page.card_statuses("characters")
    # 顺序与索引一致
    assert statuses == ["ready", "ready", "generating", "empty"]


def test_toolbar_buttons_emit_signals(project_dir):
    _app()
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    page = AssetLibraryPage()
    page.set_project(project_dir)

    spy_import = QSignalSpy(page.importRequested)
    spy_extract = QSignalSpy(page.extractRequested)
    spy_generate = QSignalSpy(page.generateRequested)

    page.importBtn.click()
    page.extractBtn.click()
    page.generateBtn.click()

    assert spy_import.count() == 1
    assert spy_extract.count() == 1
    assert spy_generate.count() == 1


def test_generate_signal_carries_name(project_dir):
    _app()
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    page = AssetLibraryPage()
    page.set_project(project_dir)
    spy = QSignalSpy(page.generateRequested)
    page.request_generate("管家老张")
    assert spy.count() == 1
    assert spy.at(0)[0] == "管家老张"


def test_empty_project_dir_does_not_crash(tmp_path):
    _app()
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    page = AssetLibraryPage()
    # 空目录：无任何 ref_index.json → 降级空网格不崩
    page.set_project(tmp_path)
    assert page.card_count("characters") == 0
    assert page.card_count("scenes") == 0
    assert page.card_count("props") == 0
    ready, total = page.completeness()
    assert (ready, total) == (0, 0)
    assert page.missing_count() == 0


def test_none_project_does_not_crash():
    _app()
    from drama_shot_master.ui.pages.asset_library_page import AssetLibraryPage
    page = AssetLibraryPage()
    # 构造即可显示，未 set_project 时三 tab 空网格
    assert page.card_count("characters") == 0
    assert page.completeness() == (0, 0)
