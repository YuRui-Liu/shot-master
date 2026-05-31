"""GenrePickerDialog smoke 测试（offscreen QApplication）。

覆盖 RED/GREEN：
- 构造 → 渲染 6 张题材卡（list_genres 驱动）；
- 选主题材 → result_value() 含 genre；
- 选副题材（主+副 ≤3，0xsline 叠加规则）→ result_value().sub 含副 id；
- 副题材选超过 3（含主）被限制；
- 取消 → result_value() 为 None。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_renders_six_genre_cards(app):
    from drama_shot_master.ui.dialogs.genre_picker_dialog import GenrePickerDialog
    dlg = GenrePickerDialog()
    assert len(dlg.cards) == 6
    # 卡片显示 display_name + identity.one_liner
    ids = {c.genre_id for c in dlg.cards}
    assert "short-drama" in ids
    card = next(c for c in dlg.cards if c.genre_id == "short-drama")
    assert "短剧" in card.title_text
    assert card.one_liner_text  # 非空一句话


def test_pick_primary_sets_genre(app):
    from drama_shot_master.ui.dialogs.genre_picker_dialog import GenrePickerDialog
    dlg = GenrePickerDialog()
    dlg.set_primary("short-drama")
    dlg.accept()
    result = dlg.result_value()
    assert result is not None
    assert result["genre"] == "short-drama"
    assert result["sub"] == []


def test_pick_subgenres_overlay(app):
    from drama_shot_master.ui.dialogs.genre_picker_dialog import GenrePickerDialog
    dlg = GenrePickerDialog()
    dlg.set_primary("short-drama")
    dlg.toggle_sub("mv")
    dlg.toggle_sub("vlog")
    dlg.accept()
    result = dlg.result_value()
    assert result["genre"] == "short-drama"
    assert set(result["sub"]) == {"mv", "vlog"}


def test_sub_limited_to_stack_max(app):
    # 主 + 副 ≤3：主占 1 名额，副至多 2 个；选第 3 个副被拒
    from drama_shot_master.ui.dialogs.genre_picker_dialog import GenrePickerDialog
    dlg = GenrePickerDialog()
    dlg.set_primary("short-drama")
    assert dlg.toggle_sub("mv") is True
    assert dlg.toggle_sub("vlog") is True
    # 第三个副超出上限，被拒（返回 False），不计入
    assert dlg.toggle_sub("commercial") is False
    dlg.accept()
    result = dlg.result_value()
    assert len(result["sub"]) == 2
    assert "commercial" not in result["sub"]


def test_primary_excluded_from_sub(app):
    # 主题材不能同时是副题材
    from drama_shot_master.ui.dialogs.genre_picker_dialog import GenrePickerDialog
    dlg = GenrePickerDialog()
    dlg.set_primary("short-drama")
    assert dlg.toggle_sub("short-drama") is False
    dlg.accept()
    assert dlg.result_value()["sub"] == []


def test_cancel_returns_none(app):
    from drama_shot_master.ui.dialogs.genre_picker_dialog import GenrePickerDialog
    dlg = GenrePickerDialog()
    dlg.set_primary("short-drama")
    dlg.reject()
    assert dlg.result_value() is None
