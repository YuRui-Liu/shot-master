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


def test_stage_rows_have_mini_bar():
    """每个分阶段行带迷你进度条（复刻 mockup .mini）。"""
    _app()
    sp = SplashScreen()
    for row in sp._stage_rows:
        assert row._mini is not None
        # 状态应同步到迷你条
        row.set_state("done")
        assert row._mini._state == "done"


def test_advance_anim_updates_ring_angle():
    """动画时基推进后环角度被更新（复刻 spin 2.4s linear）。"""
    _app()
    sp = SplashScreen()
    sp._elapsed_ms = 0.0
    sp._advance_anim()
    assert sp._elapsed_ms > 0.0
    # 2.4s 一圈 → 角度处于 [0,360)
    assert 0.0 <= sp._ring_angle < 360.0


def test_top_row_has_pill_and_skip():
    """顶部行含 LOADING pill 与「跳过 →」（复刻 mockup .pill / .skip）。"""
    _app()
    sp = SplashScreen()
    assert "LOADING" in sp._pill.text()
    assert "跳过" in sp._skip_lbl.text()


def test_paint_does_not_crash():
    """offscreen 触发一次绘制（grid/双色环/pill 圆点/流光进度条）不崩。"""
    from PySide6.QtGui import QPixmap
    _app()
    sp = SplashScreen()
    sp.set_stage(0, "done")
    sp.set_stage(1, "active")
    sp.set_progress(0.5)
    sp._advance_anim()
    pm = QPixmap(sp.size())
    pm.fill()
    sp.render(pm)  # 渲染到 QPaintDevice，触发 paintEvent 全链路
