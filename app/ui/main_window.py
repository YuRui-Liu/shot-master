"""主窗口：三栏布局 + 菜单 + 信号总线 + 目录记忆。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QStackedWidget, QButtonGroup, QStatusBar, QProgressBar,
    QFileDialog, QMessageBox,
)

from app.config import load_config
import app.providers  # noqa: F401  触发 provider 注册

from app.ui.state import AppState, restore_from_config, remember_dirs
from app.ui.thumbnail_grid import ThumbnailGrid
from app.ui.preview_dialog import PreviewDialog
from app.ui.panels.inference_panel import InferencePanel
from app.ui.panels.split_panel import SplitPanel
from app.ui.panels.combine_panel import CombinePanel
from app.ui.panels.trim_panel import TrimPanel
from app.ui.panels.video_panel import VideoPanel
from app.ui.dialogs.runninghub_settings_dialog import RunningHubSettingsDialog


FUNCS = [("反推", "inference"), ("拆图", "split"),
         ("拼图", "combine"), ("去白边", "trim"),
         ("视频生成", "video_gen")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shot-Prompt-Backwards · 分镜工具")
        self.resize(1360, 860)
        self.cfg = load_config()
        self.state = AppState()

        self._build_ui()
        self._wire()

        restore_from_config(self.state, self.cfg)
        if self.state.current_dir:
            self.dir_label.setText(f"当前目录:\n{self.state.current_dir}")
            self.thumb.populate(self.state.images)
        if self.state.output_dir:
            self.out_label.setText(f"输出目录:\n{self.state.output_dir}")
        self._refresh_counts()
        # 恢复上次活跃的 panel（settings.json 持久化）
        target_key = self.cfg.last_active_function
        start_idx = next(
            (i for i, (_, key) in enumerate(FUNCS) if key == target_key), 0)
        # 同步左上 button group 的选中状态
        btn = self.func_group.button(start_idx)
        if btn is not None:
            btn.setChecked(True)
        self._on_func_changed(start_idx)

    def _build_ui(self):
        menu = self.menuBar()
        fm = menu.addMenu("文件")
        a_open = QAction("打开目录…", self); a_open.setShortcut("Ctrl+O")
        a_open.triggered.connect(self._open_dir)
        a_out = QAction("设置输出目录…", self)
        a_out.triggered.connect(self._set_out_dir)
        fm.addAction(a_open); fm.addAction(a_out)
        fm.addSeparator()
        a_quit = QAction("退出", self); a_quit.triggered.connect(self.close)
        fm.addAction(a_quit)

        sm = menu.addMenu("设置")
        a_rh = QAction("RunningHub 配置…", self)
        a_rh.triggered.connect(self._open_runninghub_settings)
        sm.addAction(a_rh)

        sp = QSplitter(Qt.Horizontal)

        left = QWidget(); lv = QVBoxLayout(left)
        self.dir_label = QLabel("当前目录:\n(未打开)")
        self.dir_label.setWordWrap(True)
        b_open = QPushButton("打开目录"); b_open.clicked.connect(self._open_dir)
        self.out_label = QLabel("输出目录:\n(未设置)")
        self.out_label.setWordWrap(True)
        b_out = QPushButton("设置输出目录")
        b_out.clicked.connect(self._set_out_dir)
        self.count_label = QLabel("0 张  已选 0")
        lv.addWidget(self.dir_label); lv.addWidget(b_open)
        lv.addWidget(self.out_label); lv.addWidget(b_out)
        lv.addWidget(self.count_label)
        lv.addStretch(1)
        left.setMinimumWidth(200); left.setMaximumWidth(260)

        self.thumb = ThumbnailGrid()

        right = QWidget(); rv = QVBoxLayout(right)
        switch = QHBoxLayout()
        self.func_group = QButtonGroup(self)
        for i, (label, key) in enumerate(FUNCS):
            b = QPushButton(label); b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self.func_group.addButton(b, i)
            switch.addWidget(b)
        rv.addLayout(switch)

        self.stack = QStackedWidget()
        self.panels = [
            InferencePanel(self.state, self.cfg),
            SplitPanel(self.state, self.cfg),
            CombinePanel(self.state, self.cfg),
            TrimPanel(self.state, self.cfg),
            VideoPanel(self.state, self.cfg),
        ]
        for p in self.panels:
            self.stack.addWidget(p)
        rv.addWidget(self.stack, 1)

        act = QHBoxLayout()
        self.btn_preview = QPushButton("预览")
        self.btn_preview.clicked.connect(self._do_preview)
        self.btn_exec = QPushButton("执行")
        self.btn_exec.clicked.connect(self._do_execute)
        self.exec_hint = QLabel("")
        self.exec_hint.setStyleSheet("color:#888")
        act.addWidget(self.btn_preview); act.addWidget(self.btn_exec)
        act.addWidget(self.exec_hint, 1)
        rv.addLayout(act)
        right.setMinimumWidth(340); right.setMaximumWidth(420)

        sp.addWidget(left); sp.addWidget(self.thumb); sp.addWidget(right)
        sp.setStretchFactor(0, 0); sp.setStretchFactor(1, 1)
        sp.setStretchFactor(2, 0)
        sp.setSizes([220, 800, 360])
        self.setCentralWidget(sp)

        sb = QStatusBar()
        self.status = QLabel(
            f"后端: {self.cfg.current_provider} · {self.cfg.current_model}")
        self.progress = QProgressBar(); self.progress.setMaximumWidth(180)
        self.progress.hide()
        sb.addWidget(self.status, 1)
        sb.addPermanentWidget(self.progress)
        self.setStatusBar(sb)

        ts = self.cfg.ui.get("thumb_size")
        if isinstance(ts, int):
            self.thumb.set_thumb_size(ts)

    def _wire(self):
        self.func_group.idClicked.connect(self._on_func_changed)
        self.thumb.selectionChanged.connect(self._on_selection)
        self.thumb.previewRequested.connect(self._on_thumb_double)
        self.thumb.thumbSizeChanged.connect(self._on_thumb_size)
        for p in self.panels:
            p.validityChanged.connect(self._refresh_validity)
            p.statusMessage.connect(self.status.setText)

    def _open_dir(self):
        start = str(self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "打开目录", start)
        if not d:
            return
        self.state.load_dir(Path(d))
        self.dir_label.setText(f"当前目录:\n{self.state.current_dir}")
        self.thumb.populate(self.state.images)
        self._refresh_counts()
        remember_dirs(self.state, self.cfg)
        self.status.setText(f"已加载 {len(self.state.images)} 张")

    def _set_out_dir(self):
        start = str(self.state.output_dir or self.state.current_dir or Path.home())
        d = QFileDialog.getExistingDirectory(self, "设置输出目录", start)
        if not d:
            return
        self.state.output_dir = Path(d)
        self.out_label.setText(f"输出目录:\n{d}")
        remember_dirs(self.state, self.cfg)
        self._refresh_validity()

    def _open_runninghub_settings(self):
        RunningHubSettingsDialog(self.cfg, parent=self).exec()

    def _on_func_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.state.active_function = FUNCS[idx][1]
        panel = self.panels[idx]
        self.thumb.set_mode(panel.select_mode())
        is_video = (FUNCS[idx][1] == "video_gen")
        # 视频生成时：隐藏中栏 thumb + 隐藏底部 preview/execute 控制
        self.thumb.setVisible(not is_video)
        self.btn_preview.setVisible(not is_video and (
            panel.has_preview() or FUNCS[idx][1] == "split"))
        self.btn_exec.setVisible(not is_video)
        self.exec_hint.setVisible(not is_video)
        # 视频生成模式下让右栏拓宽（取消 maxWidth）
        right_widget = self.btn_exec.parentWidget()
        if right_widget:
            if is_video:
                right_widget.setMaximumWidth(16777215)
                right_widget.setMinimumWidth(800)
            else:
                right_widget.setMaximumWidth(420)
                right_widget.setMinimumWidth(340)
        self._refresh_validity()

    def _on_selection(self, order: list[int]):
        self.state.selected = list(order)
        self._refresh_counts()
        self._refresh_validity()

    def _refresh_counts(self):
        self.count_label.setText(
            f"{len(self.state.images)} 张  已选 {len(self.state.selected)}")

    def _refresh_validity(self):
        panel = self.panels[self.stack.currentIndex()]
        ok, why = panel.validate()
        self.btn_exec.setEnabled(ok)
        self.exec_hint.setText(why)

    def _on_thumb_size(self, size: int):
        self.cfg.ui["thumb_size"] = size
        self.cfg.update_settings()

    def _on_thumb_double(self, row: int):
        if not (0 <= row < len(self.state.images)):
            return
        path = self.state.images[row].path
        overlay = None
        idx = self.stack.currentIndex()
        if FUNCS[idx][1] == "split":
            overlay = self.panels[idx].overlay_spec()
        PreviewDialog(path, overlay_spec=overlay, parent=self).exec()

    def _do_preview(self):
        idx = self.stack.currentIndex()
        if FUNCS[idx][1] != "split":
            return
        sel = self.state.selected_paths()
        if not sel:
            QMessageBox.information(self, "预览", "请先选一张图")
            return
        PreviewDialog(sel[0],
                      overlay_spec=self.panels[idx].overlay_spec(),
                      parent=self).exec()

    def _do_execute(self):
        panel = self.panels[self.stack.currentIndex()]
        ok, why = panel.validate()
        if not ok:
            QMessageBox.warning(self, "无法执行", why)
            return
        panel.execute()

    def closeEvent(self, e):
        # 保存视频面板缓存（VideoPanel 自己处理）
        for w in self.panels:
            if isinstance(w, VideoPanel):
                w.save_cache()
                break
        # 持久化当前活跃 panel
        try:
            self.cfg.update_settings(
                last_active_function=self.state.active_function or "inference")
        except Exception:
            pass
        super().closeEvent(e)
