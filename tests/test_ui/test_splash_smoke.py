import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.splash import SplashScreen


def _app():
    return QApplication.instance() or QApplication([])


def test_construct_does_not_crash():
    """构造不崩，标题=糯米AI分镜影视创作台，默认 3 步清单。"""
    _app()
    sp = SplashScreen()
    assert sp.brand_title() == "糯米AI分镜影视创作台"
    assert len(sp._stages) == 3


def test_set_stage_active_updates_state():
    """set_stage(1,'active') 后第 2 步状态 = active。"""
    _app()
    sp = SplashScreen()
    sp.set_stage(1, "active")
    assert sp.stage_state(1) == "active"


def test_set_stage_done_and_pending():
    _app()
    sp = SplashScreen()
    sp.set_stage(0, "done")
    sp.set_stage(2, "pending")
    assert sp.stage_state(0) == "done"
    assert sp.stage_state(2) == "pending"


def test_set_progress_clamps():
    _app()
    sp = SplashScreen()
    sp.set_progress(0.5)
    assert abs(sp.progress() - 0.5) < 1e-6
    sp.set_progress(2.0)
    assert sp.progress() == 1.0
    sp.set_progress(-1.0)
    assert sp.progress() == 0.0


def test_set_credits_business_shown_when_filled():
    """填了商务 → 商务可见。"""
    _app()
    sp = SplashScreen()
    sp.set_credits("二进制糯米", business="商务合作 xxx")
    assert sp.author() == "二进制糯米"
    # 未 show() 时用 isHidden() 反映显式可见意图（不受祖先未显示影响）
    assert not sp._business_label.isHidden()
    assert "商务" in sp._business_label.text()


def test_set_credits_business_hidden_when_empty():
    """空商务 → 商务隐藏，仅显示作者。"""
    _app()
    sp = SplashScreen()
    sp.set_credits("二进制糯米", business="")
    assert sp.author() == "二进制糯米"
    assert sp._business_label.isHidden()


def test_set_tip_updates_text():
    _app()
    sp = SplashScreen()
    sp.set_tip("提示：测试一下")
    assert "提示" in sp._tip_label.text()
