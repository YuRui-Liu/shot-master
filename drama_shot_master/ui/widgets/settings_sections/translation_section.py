"""TranslationSection: provider 分页（腾讯/DeepLX）+ 凭证编辑 + 测试连接。

风格对齐现有 refine_section / dub_section：QFormLayout + theme tokens 提示。
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from drama_shot_master.ui.theme import _tokens, current_theme


_REGIONS = [
    "ap-beijing", "ap-shanghai", "ap-guangzhou", "ap-chengdu",
    "ap-hongkong", "ap-singapore", "ap-tokyo", "ap-seoul",
    "ap-bangkok", "ap-mumbai", "na-siliconvalley", "na-ashburn",
    "eu-frankfurt",
]


class TranslationSection(QWidget):
    title = "翻译"
    category = "平台核心"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._test_worker = None  # FunctionWorker handle to prevent GC
        # cfg 是否“显式声明”了翻译 provider；若否，validate 保持宽松，
        # 以兼容旧 cfg 结构（避免 unified dialog 保存路径被新校验卡死）。
        self._provider_explicit = hasattr(cfg, "current_translator") \
            and bool(getattr(cfg, "current_translator", "") or "")
        self._build_ui()
        self.load_from(cfg)

    # ───────── UI ─────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Provider selector row
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("翻译服务："))
        self.rb_tencent = QRadioButton("腾讯云机器翻译（推荐）")
        self.rb_deeplx = QRadioButton("DeepLX (自部署)")
        self.provider_group = QButtonGroup(self)
        self.provider_group.addButton(self.rb_tencent, 0)
        self.provider_group.addButton(self.rb_deeplx, 1)
        sel_row.addWidget(self.rb_tencent)
        sel_row.addWidget(self.rb_deeplx)
        sel_row.addStretch(1)
        root.addLayout(sel_row)

        # Stack with two panes
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_tencent_pane())
        self.stack.addWidget(self._build_deeplx_pane())
        root.addWidget(self.stack)

        # Test connection row
        test_row = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        self.btn_test.clicked.connect(self._on_test)
        self.lbl_test = QLabel("")
        self.lbl_test.setWordWrap(True)
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.lbl_test, 1)
        root.addLayout(test_row)
        root.addStretch(1)

        # idToggled also fires on programmatic setChecked(); filter for "checked".
        self.provider_group.idToggled.connect(
            lambda idx, checked: checked and self.stack.setCurrentIndex(idx))

    def _build_tencent_pane(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.tc_sid = QLineEdit()
        self.tc_skey = QLineEdit()
        self.tc_skey.setEchoMode(QLineEdit.EchoMode.Password)
        self.tc_region = QComboBox()
        self.tc_region.addItems(_REGIONS)
        self.tc_pid = QSpinBox()
        self.tc_pid.setRange(0, 999999)
        f.addRow("SecretId", self.tc_sid)
        f.addRow("SecretKey", self.tc_skey)
        f.addRow("Region", self.tc_region)
        f.addRow("ProjectId", self.tc_pid)
        tip = QLabel(
            '去 <a href="https://console.cloud.tencent.com/cam/capi">'
            '腾讯云控制台</a> 创建访问密钥，免费 5 万字符/月。')
        tip.setOpenExternalLinks(True)
        tip.setWordWrap(True)
        self._style_muted(tip)
        f.addRow(tip)
        return w

    def _build_deeplx_pane(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.dl_url = QLineEdit()
        # Back-compat alias: 旧 test_settings_sections_smoke 用 sec.url_edit。
        self.url_edit = self.dl_url
        self.dl_url.setPlaceholderText(
            "https://api.deeplx.org/translate（或自部署 http://localhost:1188/translate）")
        f.addRow("DeepLX URL", self.dl_url)
        tip = QLabel("公共实例不稳定，建议自部署或切到腾讯云。")
        tip.setWordWrap(True)
        self._style_muted(tip)
        f.addRow(tip)
        return w

    def _style_muted(self, lbl: QLabel) -> None:
        try:
            t = _tokens(current_theme(self._cfg))
            lbl.setStyleSheet(f"color:{t['fg_muted']}")
        except Exception:
            pass

    # ───────── load / save / validate ─────────

    def load_from(self, cfg) -> None:
        provider = (getattr(cfg, "current_translator", "") or "tencent").lower()
        if provider == "deeplx":
            self.rb_deeplx.setChecked(True)
            self.stack.setCurrentIndex(1)
        else:
            self.rb_tencent.setChecked(True)
            self.stack.setCurrentIndex(0)
        self.tc_sid.setText(getattr(cfg, "tencent_translator_secret_id", "") or "")
        self.tc_skey.setText(getattr(cfg, "tencent_translator_secret_key", "") or "")
        region = getattr(cfg, "tencent_translator_region", "ap-beijing") \
            or "ap-beijing"
        idx = self.tc_region.findText(region)
        self.tc_region.setCurrentIndex(idx if idx >= 0 else 0)
        self.tc_pid.setValue(int(getattr(cfg, "tencent_translator_project_id", 0) or 0))
        self.dl_url.setText(getattr(cfg, "deeplx_url", "") or "")

    def save_to(self, cfg) -> None:
        provider = "tencent" if self.rb_tencent.isChecked() else "deeplx"
        cfg.update_settings(
            current_translator=provider,
            tencent_translator_secret_id=self.tc_sid.text().strip(),
            tencent_translator_secret_key=self.tc_skey.text().strip(),
            tencent_translator_region=self.tc_region.currentText(),
            tencent_translator_project_id=self.tc_pid.value(),
            deeplx_url=self.dl_url.text().strip(),
        )
        # 同步到 os.environ（让旧 translate_en_to_zh 立刻看到新值）
        os.environ["_CURRENT_TRANSLATOR"] = provider
        if cfg.tencent_translator_secret_id:
            os.environ["TENCENTCLOUD_SECRET_ID"] = cfg.tencent_translator_secret_id
        if cfg.tencent_translator_secret_key:
            os.environ["TENCENTCLOUD_SECRET_KEY"] = cfg.tencent_translator_secret_key
        if cfg.tencent_translator_region:
            os.environ["TENCENTCLOUD_REGION"] = cfg.tencent_translator_region
        if cfg.deeplx_url:
            os.environ["DEEPLX_URL"] = cfg.deeplx_url
        # 清缓存（provider/凭证 已变）
        from drama_shot_master.providers.translator import clear_cache
        clear_cache()

    def validate(self) -> tuple[bool, str]:
        # 旧 cfg（无 current_translator 字段）保持宽松：不强卡，避免老路径回归。
        if not self._provider_explicit and not self._user_touched():
            return True, ""
        if self.rb_tencent.isChecked():
            if not self.tc_sid.text().strip() or not self.tc_skey.text().strip():
                return False, "腾讯云需要填 SecretId 和 SecretKey"
        else:
            if not self.dl_url.text().strip():
                return False, "DeepLX 需要填 URL"
        return True, ""

    def _user_touched(self) -> bool:
        """若用户在 UI 里填了任意凭证/URL，则视为已显式选择 provider。"""
        return bool(
            self.tc_sid.text().strip() or self.tc_skey.text().strip()
            or self.dl_url.text().strip())

    def cancel_workers(self) -> None:
        # FunctionWorker terminates when dialog closes; we just drop the handle.
        self._test_worker = None

    # ───────── test connection ─────────

    def _on_test(self) -> None:
        from drama_shot_master.providers.translator import translate
        from drama_shot_master.ui.worker import FunctionWorker
        # 先保存当前表单（用户点测试 = 同意落盘）
        self.save_to(self._cfg)
        self.lbl_test.setText("测试中…")
        self.lbl_test.setStyleSheet("")
        self.btn_test.setEnabled(False)
        worker = FunctionWorker(translate, "hello", "en", "zh", self._cfg)
        worker.finished_with_result.connect(self._on_test_done)
        worker.failed.connect(self._on_test_failed)
        worker.finished.connect(lambda: self.btn_test.setEnabled(True))
        self._test_worker = worker  # prevent GC
        worker.start()

    def _on_test_done(self, result) -> None:
        if result.ok:
            self.lbl_test.setText(f"✓ 通过：hello → {result.text}")
            self.lbl_test.setStyleSheet("color:#4ec98f")
        else:
            self.lbl_test.setText(f"✗ {result.error.hint}")
            self.lbl_test.setStyleSheet("color:#ff5c5c")
        self._test_worker = None

    def _on_test_failed(self, msg: str) -> None:
        self.lbl_test.setText(f"✗ {msg}")
        self.lbl_test.setStyleSheet("color:#ff5c5c")
        self._test_worker = None
