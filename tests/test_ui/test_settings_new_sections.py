"""设置页新增：项目管理(删除项目) / 流程锁 + 翻译归「其他」分类。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


class _Cfg:
    pipeline_lock_enabled = False
    settings_path = ""
    def __init__(self):
        self.saved = {}
    def update_settings(self, **kw):
        self.saved.update(kw)
        for k, v in kw.items():
            setattr(self, k, v)


def _mgr(tmp_path):
    from drama_shot_master.core.recent_projects import RecentProjectsManager
    return RecentProjectsManager(tmp_path / "recent.json")


def test_translation_section_category_is_other():
    from drama_shot_master.ui.widgets.settings_sections import TranslationSection
    assert TranslationSection.category == "其他"


def test_pipeline_section_saves_toggle():
    _app()
    from drama_shot_master.ui.widgets.settings_sections import PipelineSection
    cfg = _Cfg()
    sec = PipelineSection(cfg)
    assert sec.lock_cb.isChecked() is False        # cfg 默认关
    sec.lock_cb.setChecked(True)
    sec.save_to(cfg)
    assert cfg.saved.get("pipeline_lock_enabled") is True


def test_project_mgmt_remove_keeps_folder(tmp_path):
    _app()
    from drama_shot_master.ui.widgets.settings_sections import ProjectManagementSection
    proj = tmp_path / "P-001_demo"; proj.mkdir()
    mgr = _mgr(tmp_path); mgr.push(str(proj), "demo")
    sec = ProjectManagementSection(_Cfg(), recent_mgr=mgr)
    sec.remove_from_list(str(proj))
    assert mgr.load() == []            # 列表移除
    assert proj.exists()                # 文件夹保留


def test_project_mgmt_delete_removes_both(tmp_path):
    _app()
    from drama_shot_master.ui.widgets.settings_sections import ProjectManagementSection
    proj = tmp_path / "P-002_demo"; proj.mkdir()
    (proj / "a.txt").write_text("x", encoding="utf-8")
    mgr = _mgr(tmp_path); mgr.push(str(proj), "demo")
    sec = ProjectManagementSection(_Cfg(), recent_mgr=mgr)
    sec.delete_folder(str(proj))
    assert mgr.load() == []            # 列表移除
    assert not proj.exists()            # 文件夹删除


def test_settings_dialog_has_new_sections_under_categories(tmp_path):
    _app()
    from drama_shot_master.ui.dialogs.unified_settings_dialog import UnifiedSettingsDialog
    dlg = UnifiedSettingsDialog(app=None, cfg=_Cfg())
    # 收集 树里 category→[leaf titles]
    cat_leaves = {}
    for i in range(dlg.tree.topLevelItemCount()):
        top = dlg.tree.topLevelItem(i)
        cat_leaves[top.text(0)] = [top.child(j).text(0) for j in range(top.childCount())]
    assert "项目管理" in cat_leaves.get("应用", [])
    assert "流程 & 调试" in cat_leaves.get("应用", [])
    assert "翻译" in cat_leaves.get("其他", [])
