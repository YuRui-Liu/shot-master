from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class EmptyInspector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("无选中。点 cue 查看属性，Ctrl+click 多选。"))
        lay.addStretch(1)
