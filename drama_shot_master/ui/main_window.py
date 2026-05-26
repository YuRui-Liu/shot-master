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

from drama_shot_master.config import load_config
import drama_shot_master.providers  # noqa: F401  触发 provider 注册

from drama_shot_master.ui.state import AppState, restore_from_config, remember_dirs
from drama_shot_master.ui.thumbnail_grid import ThumbnailGrid
from drama_shot_master.ui.preview_dialog import PreviewDialog
from drama_shot_master.ui.panels.inference_panel import InferencePanel
from drama_shot_master.ui.panels.split_panel import SplitPanel
from drama_shot_master.ui.panels.combine_panel import CombinePanel
from drama_shot_master.ui.panels.trim_panel import TrimPanel
from drama_shot_master.core.video_task_store import VideoTaskStore
from drama_shot_master.ui.panels.video_task_manager_panel import VideoTaskManagerPanel
from drama_shot_master.ui.windows.video_task_window import VideoTaskWindow
from drama_shot_master.ui.theme import apply_dark_titlebar
from drama_shot_master.ui.dialogs.runninghub_settings_dialog import RunningHubSettingsDialog
from drama_shot_master.ui.dialogs.translation_settings_dialog import TranslationSettingsDialog
from drama_shot_master.ui.dialogs.refine_settings_dialog import RefineSettingsDialog


FUNCS = [("反推", "inference"), ("拆图", "split"),
         ("拼图", "combine"), ("去白边", "trim"),
         ("视频生成", "video_gen"), ("配乐", "soundtrack")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drama-Shot-Master · 分镜工具")
        self.resize(1360, 860)
        self.cfg = load_config()
        self.state = AppState()
        self.video_store = VideoTaskStore.from_list(self.cfg.video_tasks)
        self._open_task_windows: dict[str, VideoTaskWindow] = {}

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
        a_tr = QAction("翻译配置…", self)
        a_tr.triggered.connect(self._open_translation_settings)
        sm.addAction(a_tr)
        a_rf = QAction("提示词优化配置…", self)
        a_rf.triggered.connect(self._open_refine_settings)
        sm.addAction(a_rf)

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
            VideoTaskManagerPanel(
                self.state, self.cfg, self.video_store,
                self._open_task_window, self._close_task_window,
                self._persist_tasks),
            self._try_make_soundtrack_panel(),
        ]
        for p in self.panels:
            self.stack.addWidget(p)
        rv.addWidget(self.stack, 1)

        act = QHBoxLayout()
        self.btn_preview = QPushButton("预览")
        self.btn_preview.clicked.connect(self._do_preview)
        self.btn_exec = QPushButton("执行")
        self.btn_exec.setObjectName("AccentButton")
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
            if hasattr(p, "validityChanged"):
                p.validityChanged.connect(self._refresh_validity)
            if hasattr(p, "statusMessage"):
                p.statusMessage.connect(self.status.setText)
        self._video_manager().taskRenamed.connect(self._on_task_renamed)

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

    def _open_translation_settings(self):
        TranslationSettingsDialog(self.cfg, parent=self).exec()

    def _open_refine_settings(self):
        RefineSettingsDialog(self.cfg, parent=self).exec()

    def _video_manager(self):
        idx = next((i for i, (_l, k) in enumerate(FUNCS) if k == "video_gen"), -1)
        return self.panels[idx]

    def _persist_tasks(self):
        try:
            self.cfg.update_settings(video_tasks=self.video_store.to_list())
        except Exception:
            pass

    def _open_task_window(self, task):
        existing = self._open_task_windows.get(task.id)
        if existing is not None:
            existing.raise_(); existing.activateWindow()
            return
        win = VideoTaskWindow(task, self.state, self.cfg)
        win.timelineDirty.connect(self._on_task_dirty)
        win.statusChanged.connect(self._on_task_status)
        win.resultReady.connect(self._on_task_result)
        win.closed.connect(self._on_task_window_closed)
        self._open_task_windows[task.id] = win
        win.show()

    def _close_task_window(self, task_id: str):
        win = self._open_task_windows.get(task_id)
        if win is not None:
            win.close()

    def _on_task_dirty(self, task_id: str, timeline: dict):
        self.video_store.update(task_id, timeline=timeline)
        self._persist_tasks()

    def _on_task_status(self, task_id: str, status: str):
        self._video_manager().set_task_status(task_id, status)

    def _on_task_result(self, task_id: str, mp4: str):
        self.video_store.update(task_id, last_result=mp4)
        self._persist_tasks()
        self._video_manager().refresh()

    def _on_task_window_closed(self, task_id: str):
        self._open_task_windows.pop(task_id, None)
        self._video_manager().clear_task_status(task_id)
        self._video_manager().refresh()

    def _on_task_renamed(self, task_id: str, name: str):
        win = self._open_task_windows.get(task_id)
        if win is not None:
            win.set_title_name(name)

    # ------------------------------------------------------------------ #
    # 配乐 tab helpers
    # ------------------------------------------------------------------ #

    def _try_make_soundtrack_panel(self):
        """try-import 注册配乐面板；agent/面板缺失则返回占位空面板，宿主照常启动。"""
        try:
            from drama_shot_master.ui.panels.soundtrack_panel import SoundtrackPanel
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("配乐面板不可用，已跳过: %s", e)
            from PySide6.QtWidgets import QWidget
            return QWidget()
        self._soundtrack_windows = {}
        return SoundtrackPanel(
            self.state, self.cfg,
            open_window_cb=self._open_soundtrack_window,
            persist_cb=self._persist_soundtrack)

    def _persist_soundtrack(self):
        try:
            self.cfg.update_settings(soundtrack_tasks=self.cfg.soundtrack_tasks)
        except Exception:
            pass

    def _soundtrack_panel(self):
        idx = next((i for i, (_l, k) in enumerate(FUNCS) if k == "soundtrack"), -1)
        return self.panels[idx] if 0 <= idx < len(self.panels) else None

    def _open_soundtrack_window(self, task: dict):
        from drama_shot_master.ui.windows.soundtrack_task_window import (
            SoundtrackTaskWindow)
        wins = getattr(self, "_soundtrack_windows", None)
        if wins is None:
            wins = self._soundtrack_windows = {}
        tid = task.get("id")
        existing = wins.get(tid)
        if existing is not None:
            existing.raise_(); existing.activateWindow(); return
        work_root = Path(
            getattr(self.cfg, "video_output_dir", "") or ".") / "soundtrack"
        win = SoundtrackTaskWindow(task, self.cfg, work_root=work_root)
        win.statusChanged.connect(self._on_soundtrack_status)
        win.resultReady.connect(self._on_soundtrack_result)
        wins[tid] = win
        win.show()

    def _on_soundtrack_status(self, task_id: str, status: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["status"] = status
        p = self._soundtrack_panel()
        if hasattr(p, "refresh"):
            p.refresh()

    def _on_soundtrack_result(self, task_id: str, output: str):
        for t in getattr(self.cfg, "soundtrack_tasks", []):
            if t.get("id") == task_id:
                t["output"] = output
        self._persist_soundtrack()
        p = self._soundtrack_panel()
        if hasattr(p, "refresh"):
            p.refresh()

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

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_titlebar_themed", False):
            self._titlebar_themed = True
            apply_dark_titlebar(self)

    def closeEvent(self, e):
        # 让每个打开的任务窗口存一次 timeline，再整体落盘
        for win in list(self._open_task_windows.values()):
            try:
                self.video_store.update(win.task_id, timeline=win.model.to_dict())
            except Exception:
                pass
        self._persist_tasks()
        # 持久化当前活跃 panel
        try:
            self.cfg.update_settings(
                last_active_function=self.state.active_function or "inference")
        except Exception:
            pass
        # 关闭软件时删除提交诊断日志（崩溃未正常关闭则保留，便于事后溯源）
        try:
            from drama_shot_master.core import submit_debug
            submit_debug.reset()
        except Exception:
            pass
        super().closeEvent(e)
