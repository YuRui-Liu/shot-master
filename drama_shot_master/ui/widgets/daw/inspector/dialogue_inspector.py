from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit


class DialogueInspector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("对白片段")
        lay.addWidget(self.title)
        lay.addWidget(QLabel("文件:"))
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        lay.addWidget(self.path_edit)
        lay.addWidget(QLabel("时间:"))
        self.time_label = QLabel("0:00 → 0:00")
        lay.addWidget(self.time_label)
        lay.addWidget(QLabel("角色:"))
        self.role_edit = QLineEdit()
        self.role_edit.setReadOnly(True)
        lay.addWidget(self.role_edit)
        lay.addWidget(QLabel("来源: 配音智能体（只读）"))
        lay.addStretch(1)

    def set_cue_ref(self, ref, timeline_dict):
        if not timeline_dict:
            return
        audios = timeline_dict.get("audios") or []
        if not (0 <= ref.seg_index < len(audios)):
            return
        a = audios[ref.seg_index]
        fps = float(timeline_dict.get("frame_rate", 24.0)) or 24.0
        t_start = float(a.get("start_frame", 0)) / fps
        t_end = t_start + float(a.get("length_frames", 0)) / fps
        path = a.get("audio_path") or ""
        self.title.setText(f"对白 {ref.seg_index}")
        self.path_edit.setText(path)
        self.time_label.setText(f"{t_start:.2f}s → {t_end:.2f}s")
        basename = path.rsplit("/", 1)[-1]
        parts = basename.split("_")
        self.role_edit.setText(parts[1] if len(parts) > 1 else "(未知)")
