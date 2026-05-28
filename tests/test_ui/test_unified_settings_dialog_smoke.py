import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QTreeWidget, QStackedWidget

from drama_shot_master.ui.dialogs.unified_settings_dialog import UnifiedSettingsDialog


def _app():
    return QApplication.instance() or QApplication([])


def _cfg():
    # 提供各 section load_from 期望的字段；保留 update_settings 可调
    c = type("C", (), {
        "runninghub_api_key": "k", "runninghub_base_url": "",
        "video_output_dir": "", "workflow_ids": {"director": "test-wf-1"},
        "runninghub_workflow_id": "", "runninghub_template_path": "",
        "deeplx_url": "",
        "refine_provider_preset": "", "refine_base_url": "https://example.com", "refine_api_key": "",
        "refine_model": "gpt-4o-mini", "refine_meta_prompt_path": "",
        "imggen_provider": "", "imggen_base_url": "", "imggen_model": "",
        "imggen_api_key": "", "imggen_output_dir": "", "imggen_watermark": True,
        "dub_workflow_ids": {}, "dub_output_dir": "",
        "soundtrack_workflow_id": "", "soundtrack_output_dir": "",
        "soundtrack_seeds_count": 2, "soundtrack_crossfade": 0.5,
        "accent_big_threshold": 0.7, "accent_snap_window": 0.6,
        "theme": "dark",
    })()
    c.update_settings = lambda **kw: [setattr(c, k, v) for k, v in kw.items()]
    return c


@pytest.fixture(scope="module")
def dlg():
    _app()
    cfg = _cfg()
    d = UnifiedSettingsDialog(QApplication.instance(), cfg)
    yield d
    d.deleteLater()


def test_dialog_has_tree_and_stack(dlg):
    assert isinstance(dlg.tree, QTreeWidget)
    assert isinstance(dlg.stack, QStackedWidget)


def test_dialog_has_9_sections(dlg):
    # 9 sections: RunningHub / LLMPlatforms / Translation / Refine / ImgGen / Dub / Soundtrack / Screenwriter / Theme
    assert dlg.stack.count() == 9


def test_dialog_tree_categories(dlg):
    cats = []
    for i in range(dlg.tree.topLevelItemCount()):
        cats.append(dlg.tree.topLevelItem(i).text(0))
    # "外观" 类别已随主题切换 section 一起退役；仅余 3 个功能性类别
    assert "平台核心" in cats and "生成功能" in cats and "辅助" in cats


def test_select_leaf_switches_stack(dlg):
    from drama_shot_master.ui.widgets.settings_sections.soundtrack_section import SoundtrackSection
    for i in range(dlg.tree.topLevelItemCount()):
        top = dlg.tree.topLevelItem(i)
        for j in range(top.childCount()):
            leaf = top.child(j)
            if leaf.text(0) == "配乐":
                dlg.tree.setCurrentItem(leaf)
                assert isinstance(dlg.stack.currentWidget(), SoundtrackSection)
                return
    pytest.fail("no 配乐 leaf found")


def test_save_calls_each_section_save(monkeypatch):
    # 兜底：保存路径里若 validate 失败会弹模态 QMessageBox，在 offscreen 测试里会挂死
    import drama_shot_master.ui.dialogs.unified_settings_dialog as m
    monkeypatch.setattr(m.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    _app()
    cfg = _cfg()
    d = UnifiedSettingsDialog(QApplication.instance(), cfg)
    # 把 RunningHub api key 改掉，且确保 director workflow_id 满足校验
    for sec in d._sections:
        if sec.__class__.__name__ == "RunningHubSection":
            sec.api_key_edit.setText("new_key")
            sec.workflow_id_edits["director"].setText("test-wf-director")
            break
    d._on_save()
    assert cfg.runninghub_api_key == "new_key"
