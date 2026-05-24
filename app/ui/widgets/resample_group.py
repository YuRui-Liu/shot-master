"""ResampleGroup: 拆图重采样控件组（启用开关 + 比例 + 长边 + 算法 + AI 模型）。"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QFormLayout, QCheckBox,
    QComboBox, QSpinBox, QPushButton, QWidget, QLabel, QMessageBox,
)

from app.grid_ops import ResampleAlgo, ResampleSpec


# 比例预设：(显示名, w, h)；w=h=0 表示「跟随原图」（Auto）
ASPECT_PRESETS = [
    ("跟随原图", 0, 0),
    ("1:1", 1, 1),
    ("16:9", 16, 9),
    ("9:16", 9, 16),
    ("自定义", -1, -1),    # -1 哨兵；选中时从 w/h spin 读
]


class ResampleGroup(QGroupBox):
    """重采样控件组。发出 specChanged 让外部刷新 validate 状态。"""

    specChanged = Signal()

    def __init__(self,
                 list_models_fn: Callable[[], list[str]],
                 initial: Optional[dict] = None,
                 parent=None):
        """
        Args:
            list_models_fn: 无参函数，返回 upscaler 模型名列表；失败抛异常。
                由外部注入（通常是 lambda: ComfyUIUpscaler(cfg.comfyui_url).list_models()）。
            initial: 从 settings.json 读出的初始字段 dict。
        """
        super().__init__("重采样", parent)
        self._list_models_fn = list_models_fn
        self._models_loaded = False

        v = QVBoxLayout(self)

        self.enable_cb = QCheckBox("启用重采样")
        v.addWidget(self.enable_cb)

        form = QFormLayout()

        # 比例行：下拉 + (w):(h) 两个 spin（仅"自定义"时显示）
        aspect_row = QHBoxLayout()
        self.aspect_combo = QComboBox()
        for label, _, _ in ASPECT_PRESETS:
            self.aspect_combo.addItem(label)
        self.aspect_w = QSpinBox(); self.aspect_w.setRange(1, 9999); self.aspect_w.setValue(1)
        self.aspect_h = QSpinBox(); self.aspect_h.setRange(1, 9999); self.aspect_h.setValue(1)
        self.aspect_colon = QLabel(":")
        aspect_row.addWidget(self.aspect_combo, 1)
        aspect_row.addWidget(self.aspect_w)
        aspect_row.addWidget(self.aspect_colon)
        aspect_row.addWidget(self.aspect_h)
        aspect_w_h = QWidget(); aspect_w_h.setLayout(aspect_row)
        form.addRow("比例", aspect_w_h)

        # 长边
        self.long_edge = QSpinBox()
        self.long_edge.setRange(256, 8192)
        self.long_edge.setSingleStep(64)
        self.long_edge.setValue(2048)
        self.long_edge.setSuffix(" px")
        form.addRow("长边", self.long_edge)

        # 算法
        self.algo_combo = QComboBox()
        self.algo_combo.addItem("LANCZOS", ResampleAlgo.LANCZOS)
        self.algo_combo.addItem("AI 超分", ResampleAlgo.AI)
        form.addRow("算法", self.algo_combo)

        # AI 模型 + 刷新按钮（仅 AI 档显示）
        ai_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(200)
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setMaximumWidth(40)
        self.refresh_btn.setToolTip("从 ComfyUI 重新拉取 upscale 模型列表")
        ai_row.addWidget(self.model_combo, 1)
        ai_row.addWidget(self.refresh_btn)
        self.ai_row_widget = QWidget(); self.ai_row_widget.setLayout(ai_row)
        form.addRow("AI 模型", self.ai_row_widget)

        v.addLayout(form)

        # 初始状态
        self._set_form_enabled(False)
        self._on_aspect_changed(self.aspect_combo.currentText())
        self._on_algo_changed(self.algo_combo.currentText())

        # 信号
        self.enable_cb.toggled.connect(self._set_form_enabled)
        self.enable_cb.toggled.connect(lambda _: self.specChanged.emit())
        self.aspect_combo.currentTextChanged.connect(self._on_aspect_changed)
        self.aspect_combo.currentTextChanged.connect(lambda _: self.specChanged.emit())
        self.aspect_w.valueChanged.connect(lambda _: self.specChanged.emit())
        self.aspect_h.valueChanged.connect(lambda _: self.specChanged.emit())
        self.long_edge.valueChanged.connect(lambda _: self.specChanged.emit())
        self.algo_combo.currentTextChanged.connect(self._on_algo_changed)
        self.algo_combo.currentTextChanged.connect(lambda _: self.specChanged.emit())
        self.model_combo.currentTextChanged.connect(lambda _: self.specChanged.emit())
        self.refresh_btn.clicked.connect(self._force_refresh_models)

        # 应用 initial
        if initial:
            self.set_from_dict(initial)

    def _set_form_enabled(self, on: bool):
        for w in (self.aspect_combo, self.aspect_w, self.aspect_h, self.aspect_colon,
                  self.long_edge, self.algo_combo, self.model_combo, self.refresh_btn):
            w.setEnabled(on)
        if on:
            self._on_aspect_changed(self.aspect_combo.currentText())
            self._on_algo_changed(self.algo_combo.currentText())

    def _on_aspect_changed(self, text: str):
        is_custom = (text == "自定义")
        self.aspect_w.setVisible(is_custom)
        self.aspect_h.setVisible(is_custom)
        self.aspect_colon.setVisible(is_custom)

    def _on_algo_changed(self, text: str):
        is_ai = (text == "AI 超分")
        self.ai_row_widget.setVisible(is_ai)
        if is_ai and not self._models_loaded:
            self._lazy_load_models()

    def _lazy_load_models(self):
        self._models_loaded = True    # 即使失败也只懒加载一次（用户点🔄强刷）
        try:
            models = self._list_models_fn()
        except Exception as e:
            self.model_combo.clear()
            QMessageBox.warning(self, "ComfyUI 不可达",
                                f"无法拉取 upscale 模型列表：{e}\n\n"
                                "你可以手动在下拉框输入模型文件名（如 4x-UltraSharp.pth），"
                                "或点🔄按钮重试。")
            return
        self._populate_models(models)

    def _force_refresh_models(self):
        self._models_loaded = False
        self._lazy_load_models()

    def _populate_models(self, models: list[str]):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if current and current in models:
            self.model_combo.setCurrentText(current)
        elif models:
            self.model_combo.setCurrentIndex(0)

    # ----- 与外部交换数据 -----

    def get_spec(self) -> ResampleSpec:
        text = self.aspect_combo.currentText()
        if text == "跟随原图":
            w, h = 0, 0
        elif text == "自定义":
            w, h = self.aspect_w.value(), self.aspect_h.value()
        else:
            for label, pw, ph in ASPECT_PRESETS:
                if label == text:
                    w, h = pw, ph
                    break
            else:
                w, h = 0, 0
        # PySide6 把 (str, Enum) 的 userData 扁平化成 plain str，需要再转回 Enum
        algo_data = self.algo_combo.currentData()
        if isinstance(algo_data, ResampleAlgo):
            algo = algo_data
        elif isinstance(algo_data, str):
            try:
                algo = ResampleAlgo(algo_data)
            except ValueError:
                algo = ResampleAlgo.LANCZOS
        else:
            algo = ResampleAlgo.LANCZOS
        return ResampleSpec(
            enabled=self.enable_cb.isChecked(),
            aspect_w=w, aspect_h=h,
            long_edge=self.long_edge.value(),
            algorithm=algo,
            ai_model=self.model_combo.currentText().strip(),
        )

    def to_dict(self) -> dict:
        s = self.get_spec()
        return {
            "enabled": s.enabled,
            "aspect_w": s.aspect_w, "aspect_h": s.aspect_h,
            "long_edge": s.long_edge,
            "algorithm": s.algorithm.value,
            "ai_model": s.ai_model,
        }

    def set_from_dict(self, d: dict):
        self.enable_cb.setChecked(bool(d.get("enabled", False)))
        w, h = int(d.get("aspect_w", 1)), int(d.get("aspect_h", 1))
        # 匹配预设
        matched = False
        for label, pw, ph in ASPECT_PRESETS:
            if (pw, ph) == (w, h):
                self.aspect_combo.setCurrentText(label)
                matched = True
                break
        if not matched:
            self.aspect_combo.setCurrentText("自定义")
            self.aspect_w.setValue(max(w, 1))
            self.aspect_h.setValue(max(h, 1))
        self.long_edge.setValue(int(d.get("long_edge", 2048)))
        algo_str = d.get("algorithm", "lanczos")
        for i in range(self.algo_combo.count()):
            item_data = self.algo_combo.itemData(i)
            # PySide6 quirk: (str, Enum) userData 可能扁平化为 plain str
            item_value = item_data.value if hasattr(item_data, "value") else item_data
            if item_value == algo_str:
                self.algo_combo.setCurrentIndex(i)
                break
        self.model_combo.setEditText(d.get("ai_model", ""))
