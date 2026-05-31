"""StyleBibleDialog smoke：风格圣经选择器（②b STYLE BIBLE）。

offscreen QApplication；构造→按分类列出风格卡(real/2D/3D)→选→result 含 ref；
切分类过滤；取消→None。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _make(app):
    from drama_shot_master.ui.dialogs.style_bible_dialog import StyleBibleDialog
    return StyleBibleDialog()


def test_constructs_with_template_tab_and_real_cards(app):
    """默认进入「模板」tab + 真人(real)分类，列出 real 风格卡。"""
    dlg = _make(app)
    # 默认分类 real，卡片 style_id 全是 real/*
    ids = dlg.visible_style_ids()
    assert ids, "应至少有一张 real 风格卡"
    assert all(sid.startswith("real/") for sid in ids)
    # 卡上能看到中文名（电影感暖调等）
    assert any("电影感暖调" in t for t in dlg.visible_card_titles())


def test_category_filter_2d_and_3d(app):
    """切到 2D / 3D 分类→卡片随分类过滤。"""
    dlg = _make(app)

    dlg.set_category("2D")
    ids2d = dlg.visible_style_ids()
    assert ids2d and all(sid.startswith("2D/") for sid in ids2d)

    dlg.set_category("3D")
    ids3d = dlg.visible_style_ids()
    assert ids3d and all(sid.startswith("3D/") for sid in ids3d)

    dlg.set_category("real")
    idsr = dlg.visible_style_ids()
    assert idsr and all(sid.startswith("real/") for sid in idsr)


def test_select_then_result_value_has_ref_and_category(app):
    """选中一张卡→result_value 含 ref(style_id)+category。"""
    dlg = _make(app)
    dlg.set_category("2D")
    sid = dlg.visible_style_ids()[0]
    dlg.select_style(sid)
    dlg.accept()
    res = dlg.result_value()
    assert res == {"ref": sid, "category": "2D"}


def test_cancel_returns_none(app):
    """取消（reject 或未选）→ result_value None。"""
    dlg = _make(app)
    dlg.set_category("real")
    dlg.select_style(dlg.visible_style_ids()[0])
    dlg.reject()
    assert dlg.result_value() is None


def test_no_selection_returns_none(app):
    """未选直接确认 → None。"""
    dlg = _make(app)
    dlg.accept()
    assert dlg.result_value() is None


def test_has_three_tabs_template_custom_ai(app):
    """顶部三 tab：模板/自定义/AI生成（本期只实模板，另两占位）。"""
    dlg = _make(app)
    labels = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "模板" in labels[0]
    assert any("自定义" in t for t in labels)
    assert any("AI" in t for t in labels)
