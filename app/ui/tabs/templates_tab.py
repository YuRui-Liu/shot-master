"""模板 CRUD Tab。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QPlainTextEdit, QSplitter, QMessageBox, QInputDialog, QLabel,
)
from PySide6.QtCore import Qt

from app.config import Config
from app.core.template_engine import list_templates, load_template


TEMPLATES_DIR = Path("templates")
ID_PATTERN_HINT = "字母、数字、下划线、连字符"

DEFAULT_NEW = """---
name: 新模板
suggest_when: image_count == 1
variables:
  - {name: style_note, type: textarea, label: 风格备注, optional: true}
---
你是 ...（在这里写 system prompt，{{style_note}} 等占位符会被表单值替换）
"""


class TemplatesTab(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)

        # 左：列表 + 按钮
        left = QWidget()
        lv = QVBoxLayout(left)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._load_current)
        lv.addWidget(QLabel("模板列表"))
        lv.addWidget(self.list, 1)
        btn_row = QHBoxLayout()
        btn_new = QPushButton("新建")
        btn_new.clicked.connect(self._new)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._delete)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._reload)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_refresh)
        lv.addLayout(btn_row)

        # 右：编辑器
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(QLabel("Markdown 内容（YAML frontmatter + 正文）"))
        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px")
        rv.addWidget(self.editor, 1)
        save_row = QHBoxLayout()
        btn_save = QPushButton("💾 保存当前模板")
        btn_save.clicked.connect(self._save)
        save_row.addWidget(btn_save)
        save_row.addStretch(1)
        rv.addLayout(save_row)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([260, 720])
        root.addWidget(split, 1)

        self._reload()

    def _reload(self):
        self.list.clear()
        for t in list_templates(TEMPLATES_DIR):
            it = QListWidgetItem(f"{t.name}  ({t.id})")
            it.setData(Qt.UserRole, t.id)
            self.list.addItem(it)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _current_id(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _current_path(self) -> Path | None:
        tid = self._current_id()
        return TEMPLATES_DIR / f"{tid}.md" if tid else None

    def _load_current(self):
        p = self._current_path()
        if p and p.exists():
            self.editor.setPlainText(p.read_text(encoding="utf-8"))

    def _save(self):
        p = self._current_path()
        if not p:
            QMessageBox.warning(self, "提示", "请先选模板")
            return
        try:
            p.write_text(self.editor.toPlainText(), encoding="utf-8")
            # 验证能解析
            load_template(p)
            QMessageBox.information(self, "已保存", str(p))
            self._reload()
        except Exception as e:
            QMessageBox.critical(self, "保存失败/解析失败", str(e))

    def _new(self):
        tid, ok = QInputDialog.getText(self, "新建模板",
                                       f"模板 ID（{ID_PATTERN_HINT}）：")
        if not ok or not tid.strip():
            return
        import re
        if not re.match(r"^[a-zA-Z0-9_\-]+$", tid):
            QMessageBox.warning(self, "非法 ID", "只允许字母、数字、下划线、连字符")
            return
        p = TEMPLATES_DIR / f"{tid}.md"
        if p.exists():
            QMessageBox.warning(self, "已存在", f"{tid}.md 已存在")
            return
        p.write_text(DEFAULT_NEW, encoding="utf-8")
        self._reload()
        # 选中新建的
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == tid:
                self.list.setCurrentRow(i)
                break

    def _delete(self):
        p = self._current_path()
        if not p or not p.exists():
            return
        r = QMessageBox.question(self, "删除", f"确定删除 {p.name}？")
        if r == QMessageBox.Yes:
            p.unlink()
            self._reload()
