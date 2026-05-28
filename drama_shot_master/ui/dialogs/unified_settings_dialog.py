"""统一设置：左树 + 右 QStackedWidget；7 个 section 合一。
主题 section 实时持久化，其他 section 走底栏 [保存]。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QPushButton, QMessageBox,
)

from drama_shot_master.ui.widgets.settings_sections import (
    RunningHubSection, TranslationSection, RefineSection,
    ImgGenSection, DubSection, SoundtrackSection, ThemeSection,
)


class UnifiedSettingsDialog(QDialog):
    def __init__(self, app, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(800, 600)
        self._app = app
        self._cfg = cfg
        self._sections = self._build_sections()
        self._build_ui()
        self._restore_last_section()

    def _build_sections(self):
        return [
            RunningHubSection(self._cfg),
            TranslationSection(self._cfg),
            RefineSection(self._cfg),
            ImgGenSection(self._cfg),
            DubSection(self._cfg),
            SoundtrackSection(self._cfg),
            ThemeSection(self._app, self._cfg),
        ]

    def _build_ui(self):
        # 左：QTreeWidget 分类
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumWidth(220)
        cats: dict[str, QTreeWidgetItem] = {}
        ORDER = ["平台核心", "生成功能", "辅助", "外观"]
        for cat in ORDER:
            top = QTreeWidgetItem([cat])
            self.tree.addTopLevelItem(top)
            cats[cat] = top
        for sec in self._sections:
            top = cats.get(sec.category)
            if top is None:
                top = QTreeWidgetItem([sec.category])
                self.tree.addTopLevelItem(top)
                cats[sec.category] = top
            leaf = QTreeWidgetItem([sec.title])
            leaf.setData(0, Qt.UserRole, sec)
            top.addChild(leaf)
        self.tree.expandAll()
        self.tree.itemSelectionChanged.connect(self._on_tree_sel)

        # 右：QStackedWidget
        self.stack = QStackedWidget()
        for sec in self._sections:
            self.stack.addWidget(sec)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tree)
        split.addWidget(self.stack)
        split.setSizes([200, 600])

        # 底栏
        bar = QHBoxLayout()
        bar.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("保存")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save)
        bar.addWidget(self.btn_cancel)
        bar.addWidget(self.btn_save)

        root = QVBoxLayout(self)
        root.addWidget(split, 1)
        root.addLayout(bar)

    def _on_tree_sel(self):
        sec = self._current_section()
        if sec is None:
            return
        self.stack.setCurrentWidget(sec)

    def _current_section(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)  # 顶层 category item 没有 UserRole → None

    def _restore_last_section(self):
        last = getattr(self._cfg, "last_settings_section", "")
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                leaf = top.child(j)
                if leaf.text(0) == last:
                    self.tree.setCurrentItem(leaf)
                    return
        # fallback: 选第一个有 section 的叶子
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.childCount() > 0:
                self.tree.setCurrentItem(top.child(0))
                return

    def _on_save(self):
        for sec in self._sections:
            ok, why = sec.validate()
            if not ok:
                QMessageBox.warning(self, "设置无效", why)
                self.stack.setCurrentWidget(sec)
                return
        for sec in self._sections:
            sec.save_to(self._cfg)
        cur = self._current_section()
        if cur is not None:
            try:
                self._cfg.update_settings(last_settings_section=cur.title)
            except Exception:
                pass
        self.accept()

    def reject(self):
        for sec in self._sections:
            if hasattr(sec, "cancel_workers"):
                sec.cancel_workers()
        super().reject()
