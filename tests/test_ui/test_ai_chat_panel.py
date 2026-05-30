"""AIChatPanel：渲染对话/方向 + 双按钮 emit + busy 禁用。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from sound_track_agent.session import SoundtrackDirective
from drama_shot_master.ui.widgets.soundtrack_ai_chat import AIChatPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_construct(app):
    w = AIChatPanel()
    assert w is not None


def test_set_directive_renders_conversation(app):
    w = AIChatPanel()
    d = SoundtrackDirective(global_directive="史诗管弦",
        conversation=[{"role": "user", "text": "史诗感"},
                      {"role": "assistant", "text": "已更新"}])
    w.set_directive(d)
    assert w._bubble_count() == 2
    assert "史诗管弦" in w._direction_text()


def test_update_only_button_emits_apply_false(app):
    w = AIChatPanel()
    w._input.setPlainText("史诗感")
    got = []
    w.directiveRequested.connect(lambda t, a: got.append((t, a)))
    w.btn_update_only.click()
    assert got == [("史诗感", False)]


def test_update_apply_button_emits_apply_true(app):
    w = AIChatPanel()
    w._input.setPlainText("史诗感")
    got = []
    w.directiveRequested.connect(lambda t, a: got.append((t, a)))
    w.btn_update_apply.click()
    assert got == [("史诗感", True)]


def test_empty_input_does_not_emit(app):
    w = AIChatPanel()
    w._input.setPlainText("   ")
    got = []
    w.directiveRequested.connect(lambda t, a: got.append(1))
    w.btn_update_apply.click()
    assert got == []


def test_set_busy_disables_buttons(app):
    w = AIChatPanel()
    w.set_busy(True)
    assert w.btn_update_apply.isEnabled() is False
    w.set_busy(False)
    assert w.btn_update_apply.isEnabled() is True
