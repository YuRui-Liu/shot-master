"""动态叠加片段的只读查看器（子项目 #3c）。

与 empty/bgm/sfx/dialogue inspector 并列，但纯只读：仅展示选中 overlay
片段的标题/时间/prompt/音量/启用/音频状态，编辑走 lane 头控件或留 3d。
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class OverlayInspector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._seg = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("叠加片段")
        lay.addWidget(self.title)
        self.time_label = QLabel("")
        lay.addWidget(self.time_label)
        lay.addWidget(QLabel("描述:"))
        self.prompt_label = QLabel("")
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            "background:#1a1a1a;padding:4px;border-radius:2px;")
        lay.addWidget(self.prompt_label)
        self.volume_label = QLabel("音量: -")
        lay.addWidget(self.volume_label)
        self.enabled_label = QLabel("启用: -")
        lay.addWidget(self.enabled_label)
        self.audio_label = QLabel("音频: -")
        lay.addWidget(self.audio_label)
        lay.addStretch(1)

    def set_segment(self, seg) -> None:
        self._seg = seg
        if seg is None:
            return
        kind = (getattr(seg, "kind", "") or "").upper()
        lane = getattr(seg, "lane", 0)
        self.title.setText(f"{kind}·lane{lane}")
        t_start = float(getattr(seg, "t_start", 0.0))
        t_end = float(getattr(seg, "t_end", 0.0))
        dur = t_end - t_start
        self.time_label.setText(
            f"{t_start:.1f}s–{t_end:.1f}s ({dur:.1f}s)")
        self.prompt_label.setText(getattr(seg, "prompt", "") or "(空)")
        vol = int(round(float(getattr(seg, "volume", 1.0)) * 100))
        self.volume_label.setText(f"音量: {vol}%")
        enabled = getattr(seg, "enabled", True)
        self.enabled_label.setText(f"启用: {'是' if enabled else '否'}")
        has_audio = bool(getattr(seg, "audio_path", "") or "")
        self.audio_label.setText(
            f"音频: {'已生成' if has_audio else '未生成'}")
