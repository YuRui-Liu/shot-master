import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.screenwriter._shots_table_model import _ShotsTableModel


def _app():
    return QApplication.instance() or QApplication([])


def test_table_model_basic_dimensions():
    _app()
    shots = [
        {"shotId": "S01", "duration": 6, "composition": "中景",
         "description": "雨夜", "stylePrompt": "古风水墨，雨夜松林"},
        {"shotId": "S02", "duration": 5, "composition": "近景",
         "description": "书生", "stylePrompt": "古风水墨，书生撑伞"},
    ]
    m = _ShotsTableModel()
    m.set_shots(shots)
    assert m.rowCount() == 2
    assert m.columnCount() == 5


def test_table_model_set_data_writes_back_and_emits():
    _app()
    shots = [{"shotId": "S01", "duration": 6, "composition": "中景",
              "description": "雨夜", "stylePrompt": "古风水墨"}]
    m = _ShotsTableModel()
    m.set_shots(shots)
    changes = []
    m.dataChanged.connect(lambda *a: changes.append(True))
    idx = m.index(0, 3)   # description 列
    ok = m.setData(idx, "改后描述", Qt.EditRole)
    assert ok
    assert shots[0]["description"] == "改后描述"
    assert changes
