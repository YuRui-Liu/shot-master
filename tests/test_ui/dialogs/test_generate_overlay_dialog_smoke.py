import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_duration_label_shows_framed_length(app):
    from drama_shot_master.ui.dialogs.generate_overlay_dialog import GenerateOverlayDialog
    dlg = GenerateOverlayDialog(10, 18)
    # 时长 = t_end - t_start = 8
    assert "8" in dlg.duration_label.text()


def test_default_kind_is_bgm(app):
    from drama_shot_master.ui.dialogs.generate_overlay_dialog import GenerateOverlayDialog
    dlg = GenerateOverlayDialog(10, 18)
    assert dlg.current_kind() == "bgm"


def test_switch_to_sfx_changes_kind(app):
    from drama_shot_master.ui.dialogs.generate_overlay_dialog import GenerateOverlayDialog
    dlg = GenerateOverlayDialog(10, 18)
    dlg.sfx_btn.setChecked(True)
    assert dlg.current_kind() == "sfx"


def test_suggest_fn_prefills_prompt(app):
    from drama_shot_master.ui.dialogs.generate_overlay_dialog import GenerateOverlayDialog
    calls = []

    def suggest(kind, t_start, t_end):
        calls.append((kind, t_start, t_end))
        return "xx"

    dlg = GenerateOverlayDialog(10, 18, suggest_fn=suggest)
    # 同步驱动异步预填
    dlg._run_suggest()
    assert dlg.prompt_edit.toPlainText() == "xx"
    assert calls and calls[0][0] == "bgm"


def test_accept_returns_kind_and_prompt(app):
    from drama_shot_master.ui.dialogs.generate_overlay_dialog import GenerateOverlayDialog
    dlg = GenerateOverlayDialog(10, 18)
    dlg.prompt_edit.setPlainText("末日鼓点")
    dlg.accept()
    assert dlg.result_value() == ("bgm", "末日鼓点")


def test_cancel_returns_none(app):
    from drama_shot_master.ui.dialogs.generate_overlay_dialog import GenerateOverlayDialog
    dlg = GenerateOverlayDialog(10, 18)
    dlg.prompt_edit.setPlainText("不要")
    dlg.reject()
    assert dlg.result_value() is None
