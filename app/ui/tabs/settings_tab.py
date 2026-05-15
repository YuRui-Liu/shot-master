"""设置 Tab：切换 provider/model + 测试连通 + 显示已配置 key。"""
from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QGroupBox, QFormLayout, QListWidget, QMessageBox, QPlainTextEdit,
)

from app.config import Config
from app.providers import factory
from app.ui.worker import FunctionWorker


class SettingsTab(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._providers: list[dict] = []
        self._main_window = parent
        self._worker = None

        root = QVBoxLayout(self)

        # 当前后端
        box = QGroupBox("当前后端")
        form = QFormLayout(box)
        self.provider_combo = QComboBox()
        self.model_combo = QComboBox()
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider", self.provider_combo)
        form.addRow("Model", self.model_combo)
        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 保存")
        btn_save.clicked.connect(self._save)
        btn_ping = QPushButton("🔌 测试连通")
        btn_ping.clicked.connect(self._ping)
        self.ping_status = QLabel("")
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_ping)
        btn_row.addWidget(self.ping_status, 1)
        form.addRow("", btn_row)
        root.addWidget(box)

        # 已配置 keys
        keys_box = QGroupBox("已配置的 API Key（.env）")
        kv = QVBoxLayout(keys_box)
        self.keys_list = QListWidget()
        kv.addWidget(self.keys_list)
        kv.addWidget(QLabel("修改 API Key 请编辑项目根目录的 .env 然后重启应用"))
        root.addWidget(keys_box)

        # 默认输出目录
        out_box = QGroupBox("默认输出目录")
        ov = QVBoxLayout(out_box)
        self.out_label = QLabel("")
        self.out_label.setWordWrap(True)
        ov.addWidget(self.out_label)
        root.addWidget(out_box)
        root.addStretch(1)

        self._populate()

    def _populate(self):
        # provider 列表（独立 + openai_compat 展开 endpoint）
        self._providers = self._enumerate_providers()
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for p in self._providers:
            self.provider_combo.addItem(f"{p['name']} ({p['kind']})", p['name'])
        self.provider_combo.blockSignals(False)

        # 选中当前
        idx = self.provider_combo.findData(self.cfg.current_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self._on_provider_changed()

        # API keys
        self.keys_list.clear()
        for k in sorted(self.cfg.api_keys.keys()):
            self.keys_list.addItem(f"● {k}")

        # 输出目录
        self.out_label.setText(self.cfg.default_output_dir or "（未设置，输出到 输入图片同目录/_prompts/）")

    def _enumerate_providers(self) -> list[dict]:
        out = []
        for name in factory.list_providers():
            cls = factory.get_provider_class(name)
            if name == "openai_compat":
                for endpoint, preset in factory.openai_compat_presets().items():
                    out.append({"name": endpoint, "kind": "openai_compat",
                                "models": preset["models"]})
            else:
                out.append({"name": name, "kind": name,
                            "models": cls.available_models()})
        return out

    def _on_provider_changed(self):
        name = self.provider_combo.currentData()
        if not name:
            return
        info = next((p for p in self._providers if p["name"] == name), None)
        self.model_combo.clear()
        if info:
            self.model_combo.addItems(info["models"])
            # 当前选择
            if self.cfg.current_model in info["models"]:
                self.model_combo.setCurrentText(self.cfg.current_model)

    def _save(self):
        p = self.provider_combo.currentData()
        m = self.model_combo.currentText()
        if not p or not m:
            QMessageBox.warning(self, "提示", "请先选 provider/model")
            return
        self.cfg.update_settings(current_provider=p, current_model=m)
        # 让主窗口刷新状态栏
        if self._main_window and hasattr(self._main_window, "refresh_status"):
            self._main_window.refresh_status()
        QMessageBox.information(self, "已保存", f"当前后端: {p} / {m}")

    def _ping(self):
        p = self.provider_combo.currentData()
        m = self.model_combo.currentText()
        if not p or not m:
            return
        self.ping_status.setText("测试中…")
        cfg = self.cfg

        def task():
            from PIL import Image
            tmp = Path("app/.cache/ping.png")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(tmp, "PNG")
            provider = factory.build_provider(cfg, p, m)
            provider.generate([tmp], "回答一个字: ok", "")
            return True

        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(lambda _: self.ping_status.setText("✓ 连通"))
        self._worker.failed.connect(lambda e: self.ping_status.setText(f"✗ {e}"))
        self._worker.start()
