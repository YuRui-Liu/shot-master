import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.aspect_ratio_selector import (
    AspectRatioSelector, parse_ratio, DEFAULT_RATIO,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_parse_ratio():
    assert parse_ratio("16:9") == "16:9"
    assert parse_ratio(" 9 ： 16 ") == "9:16"   # 全角冒号 + 空格
    assert parse_ratio("21:9") == "21:9"
    assert parse_ratio("abc") is None
    assert parse_ratio("16:0") is None
    assert parse_ratio("") is None


def test_default_is_16_9():
    _app()
    w = AspectRatioSelector()
    assert w.value() == "16:9" == DEFAULT_RATIO
    assert w._preset_btns["16:9"].isChecked()


def test_four_presets_present():
    _app()
    w = AspectRatioSelector()
    assert set(w._preset_btns.keys()) == {"9:16", "16:9", "1:1", "4:5"}


def test_select_preset_emits_changed():
    _app()
    w = AspectRatioSelector()
    got = []
    w.changed.connect(got.append)
    w._on_preset("9:16")
    assert w.value() == "9:16"
    assert got == ["9:16"]


def test_set_value_no_emit_and_roundtrip():
    _app()
    w = AspectRatioSelector()
    got = []
    w.changed.connect(got.append)
    w.set_value("1:1")           # 程序设值不发 changed
    assert w.value() == "1:1"
    assert w._preset_btns["1:1"].isChecked()
    assert got == []


def test_custom_ratio():
    _app()
    w = AspectRatioSelector()
    got = []
    w.changed.connect(got.append)
    w.set_value("21:9")          # 自定义 → 选「自定义」+ 填框
    assert w.value() == "21:9"
    assert w._custom_btn.isChecked()
    assert not w._custom_edit.isHidden()   # offscreen 下 isVisible() 不可靠，用 isHidden
    assert w._custom_edit.text() == "21:9"
    # 编辑自定义框 → 规范化 + 发 changed
    w._custom_edit.setText("2 : 3")
    w._on_custom_edit()
    assert w.value() == "2:3"
    assert got[-1] == "2:3"


def test_invalid_set_value_falls_back_default():
    _app()
    w = AspectRatioSelector()
    w.set_value("garbage")
    assert w.value() == DEFAULT_RATIO
