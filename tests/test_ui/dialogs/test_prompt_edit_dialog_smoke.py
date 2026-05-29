import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_prompt_edit_bgm_mode(app):
    from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
    dlg = PromptEditDialog(initial_prompt="末日", title="BGM 段 0")
    dlg.prompt_edit.setPlainText("末日新版")
    assert dlg.to_payload() == "末日新版"


def test_prompt_edit_sfx_mode(app):
    from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
    dlg = PromptEditDialog(initial_prompt="门吱呀", title="SFX 镜 0")
    dlg.prompt_edit.setPlainText("门吱呀打开")
    assert dlg.to_payload() == "门吱呀打开"


def test_prompt_edit_empty_strips_whitespace(app):
    from drama_shot_master.ui.dialogs.prompt_edit_dialog import PromptEditDialog
    dlg = PromptEditDialog(initial_prompt="x", title="x")
    dlg.prompt_edit.setPlainText("   text  ")
    assert dlg.to_payload() == "text"
