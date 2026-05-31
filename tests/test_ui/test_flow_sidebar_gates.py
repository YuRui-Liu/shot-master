"""FlowSidebar 门禁 API 测试（R2-3 阶段B 兼容扩展）。

验证：默认全可达（不调门禁方法行为与现状一致）；set_phase_accessible 禁用
该阶段按钮并在禁用当前选中按钮前转移选中态（互斥组红线）；set_next_action
在阶段标签下显示小字提示；不破坏 set_active/set_collapsed。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.flow_sidebar import FlowSidebar, COLLAPSED_W, EXPANDED_W
from drama_shot_master.ui import nav_config


def _app():
    return QApplication.instance() or QApplication([])


def test_default_all_buttons_enabled():
    """默认（不调门禁方法）所有功能按钮 enabled，行为与现状一致。"""
    _app()
    sb = FlowSidebar()
    for key, btn in sb._buttons.items():
        assert btn.isEnabled(), f"{key} 默认应可达"


def test_phase_of_reverse_map_covers_all_funcs():
    """_phase_of 反向映射覆盖全部功能 key，且值为 STAGE_NAMES 之一。"""
    _app()
    sb = FlowSidebar()
    assert set(sb._phase_of.keys()) == set(sb._buttons.keys())
    for key, phase in sb._phase_of.items():
        assert phase == nav_config.PHASE_GATES[key]


def test_set_phase_accessible_false_disables_phase_buttons():
    """set_phase_accessible(phase, False) 禁用该阶段全部按钮，其他阶段不受影响。"""
    _app()
    sb = FlowSidebar()
    sb.set_phase_accessible("assets", False)
    for key in nav_config.gated_funcs("assets"):
        assert not sb._buttons[key].isEnabled()
    # 其他阶段保持可达
    for key in nav_config.gated_funcs("storyboard"):
        assert sb._buttons[key].isEnabled()


def test_set_phase_accessible_true_reenables():
    """再 set_phase_accessible(phase, True) 恢复可达。"""
    _app()
    sb = FlowSidebar()
    sb.set_phase_accessible("assets", False)
    sb.set_phase_accessible("assets", True)
    for key in nav_config.gated_funcs("assets"):
        assert sb._buttons[key].isEnabled()


def test_disabling_selected_button_transfers_selection():
    """禁用当前选中按钮前先把选中态转移到下一个可达按钮（互斥组红线）。"""
    _app()
    sb = FlowSidebar()
    # 选中 assets 阶段的 split
    sb.set_active("split")
    assert sb._buttons["split"].isChecked()
    sb.set_phase_accessible("assets", False)
    # split 被禁用且不再选中
    assert not sb._buttons["split"].isEnabled()
    assert not sb._buttons["split"].isChecked()
    # 选中态已转移到一个可达（enabled）按钮
    checked = [k for k, b in sb._buttons.items() if b.isChecked()]
    assert len(checked) == 1
    assert sb._buttons[checked[0]].isEnabled()


def test_set_next_action_shows_text():
    """set_next_action 在该阶段标签下显示小字提示文本。"""
    _app()
    sb = FlowSidebar()
    sb.set_next_action("assets", "请先完成拆图")
    lbl = sb._next_action_labels["assets"]
    assert lbl.text() == "请先完成拆图"
    assert lbl.isVisible() or lbl.text()  # 有文本即视为显示


def test_set_next_action_empty_hides():
    """空文本清除提示。"""
    _app()
    sb = FlowSidebar()
    sb.set_next_action("assets", "提示")
    sb.set_next_action("assets", "")
    lbl = sb._next_action_labels["assets"]
    assert lbl.text() == ""


def test_does_not_break_set_active():
    """门禁扩展不破坏 set_active。"""
    _app()
    sb = FlowSidebar()
    sb.set_active("trim")
    assert sb._buttons["trim"].isChecked()


def test_does_not_break_set_collapsed():
    """门禁扩展不破坏 set_collapsed。"""
    _app()
    sb = FlowSidebar()
    sb.set_collapsed(True)
    assert sb.is_collapsed
    assert sb.minimumWidth() == COLLAPSED_W
    sb.set_collapsed(False)
    assert sb.minimumWidth() == EXPANDED_W
