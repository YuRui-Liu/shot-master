"""VideoPanel：视频生成主面板。BasePanel 子类，独占主窗口内容区。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
    QListWidget, QWidget,
)

from app.config import Config
from app.core.video_timeline_model import TimelineModel
from app.providers.runninghub import (
    RunningHubClient, LTXTaskBuilder, submit_ltx_task,
    RunningHubUnavailable, RunningHubInvalidSpec,
    RunningHubUploadError, RunningHubTaskFailed,
    resolve_api_key, resolve_template_path, resolve_video_output_dir,
)
from app.ui.panels.base_panel import BasePanel
from app.ui.state import AppState
from app.ui.widgets.image_pool_widget import ImagePoolWidget
from app.ui.widgets.segment_editor import SegmentEditor
from app.ui.widgets.timeline_widget import TimelineWidget
from app.ui.widgets.video_global_form import VideoGlobalForm
from app.ui.widgets.video_status_bar import VideoStatusBar
from app.ui.worker import FunctionWorker


log = logging.getLogger(__name__)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class VideoPanel(BasePanel):
    """视频生成主面板。

    5 层纵向：图片池 + toolbar / TimelineWidget / SegmentEditor / VideoGlobalForm / VideoStatusBar。
    所有 model 写入只在本类。
    """

    def __init__(self, state: AppState, cfg: Config, parent=None):
        super().__init__(state, cfg, parent)
        self.model = self._restore_model()
        self._worker: Optional[FunctionWorker] = None
        self._cancel_flag = {"v": False}
        self._build_ui()
        self._wire()
        self._refresh_all()

    # ---------- BasePanel override ----------

    def select_mode(self) -> str:
        return "none"

    def validate(self) -> tuple[bool, str]:
        return False, "请使用面板内「🎬 提交」按钮"

    def execute(self):
        raise NotImplementedError("video panel uses internal submit button")

    # ---------- UI ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # 1. 图片池 + toolbar
        pool_wrapper = QWidget()
        pw = QVBoxLayout(pool_wrapper)
        pw.setContentsMargins(0, 0, 0, 0)
        pool_toolbar = QHBoxLayout()
        self.btn_import = QPushButton("+ 批量导入图片")
        self.btn_import_dir = QPushButton("+ 当前目录全部")
        self.btn_clear_pool = QPushButton("🗑 清空池")
        self.btn_add_text = QPushButton("+ Add Text")
        self.btn_add_audio = QPushButton("+ Add Audio")
        for b in (self.btn_import, self.btn_import_dir, self.btn_clear_pool):
            pool_toolbar.addWidget(b)
        pool_toolbar.addStretch(1)
        pool_toolbar.addWidget(self.btn_add_text)
        pool_toolbar.addWidget(self.btn_add_audio)
        pw.addLayout(pool_toolbar)
        self.image_pool = ImagePoolWidget()
        self.image_pool.setMaximumHeight(80)
        pw.addWidget(self.image_pool, 1)
        pool_wrapper.setMinimumHeight(130)
        pool_wrapper.setMaximumHeight(140)
        root.addWidget(pool_wrapper)

        # 2. 时间轴
        self.timeline = TimelineWidget(self.model)
        self.timeline.setMinimumHeight(160)
        root.addWidget(self.timeline, 3)

        # 3. per-seg 编辑器
        self.seg_editor = SegmentEditor()
        self.seg_editor.setMaximumHeight(180)
        root.addWidget(self.seg_editor)

        # 4. 全局参数
        self.global_form = VideoGlobalForm()
        self.global_form.setMaximumHeight(260)
        root.addWidget(self.global_form)

        # 5. 状态栏
        self.video_status_bar = VideoStatusBar()
        root.addWidget(self.video_status_bar)

    def _wire(self):
        # toolbar
        self.btn_import.clicked.connect(self._on_import_images)
        self.btn_import_dir.clicked.connect(self._on_import_current_dir)
        self.btn_clear_pool.clicked.connect(self._on_clear_pool)
        self.btn_add_text.clicked.connect(self._on_add_text)
        self.btn_add_audio.clicked.connect(self._on_add_audio)

        # image pool（OS 拖入 → 加池）
        self.image_pool.imagesAdded.connect(self._on_pool_images_added)

        # timeline
        self.timeline.imageDroppedAt.connect(self._on_image_dropped_at)
        self.timeline.segmentSelected.connect(self._on_segment_selected)
        self.timeline.segmentChanged.connect(self._on_segment_resized)
        self.timeline.segmentReordered.connect(self._on_segments_reordered)
        self.timeline.segmentDeleteRequested.connect(self._on_segment_delete)
        self.timeline.audioChanged.connect(self._on_audio_changed)
        self.timeline.audioDeleteRequested.connect(self._on_audio_delete)

        # seg editor
        self.seg_editor.segmentEdited.connect(self._on_segment_edited)

        # global form
        self.global_form.globalChanged.connect(self._on_global_changed)

        # status bar
        self.video_status_bar.submitRequested.connect(self._on_submit)
        self.video_status_bar.cancelRequested.connect(self._on_cancel)
        self.video_status_bar.openFolderRequested.connect(self._on_open_folder)

    def _refresh_all(self):
        self._refresh_pool()
        self.global_form.set_state(self.model)
        self.timeline.rebuild()
        self.seg_editor.bind_to(None,
                                 self.model.display_mode, self.model.frame_rate)
        self.video_status_bar.set_idle()

    def _refresh_pool(self):
        self.image_pool.set_paths(self.model.pool)
        self.image_pool.refresh_usage(self.model.pool_usage())

    # ---------- slots: toolbar ----------

    def _on_import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "批量导入图片",
            str(self.state.current_dir or Path.home()),
            "图片 (*.png *.jpg *.jpeg *.webp)")
        if not paths:
            return
        added = self.model.add_to_pool([Path(p) for p in paths])
        self._refresh_pool()
        self.statusMessage.emit(f"图片池新增 {added} 张")

    def _on_import_current_dir(self):
        if not self.state.current_dir:
            QMessageBox.information(self, "无当前目录",
                                     "先用「文件 → 打开目录」选一个目录")
            return
        paths = [p for p in sorted(self.state.current_dir.iterdir())
                 if p.suffix.lower() in IMG_EXTS]
        added = self.model.add_to_pool(paths)
        self._refresh_pool()
        self.statusMessage.emit(f"从当前目录加入 {added} 张")

    def _on_clear_pool(self):
        if QMessageBox.question(
                self, "清空池", "确定清空图片池？时间轴上的段不受影响。",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.model.clear_pool()
        self._refresh_pool()

    def _on_add_text(self):
        self.model.add_text_segment(length_frames=12, local_prompt="")
        self.timeline.rebuild()

    def _on_add_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频", str(self.state.current_dir or Path.home()),
            "音频 (*.mp3 *.wav *.flac)")
        if not path:
            return
        self.model.add_audio(Path(path), start_frame=0, length_frames=24)
        self.timeline.rebuild()

    # ---------- slots: image pool ----------

    def _on_pool_images_added(self, paths: list[Path]):
        added = self.model.add_to_pool(paths)
        self._refresh_pool()
        self.statusMessage.emit(f"图片池新增 {added} 张")

    # ---------- slots: timeline ----------

    def _on_image_dropped_at(self, path, insert_idx: int):
        path = Path(path)
        if path not in self.model.pool:
            self.model.add_to_pool([path])
        seg_id = self.model.add_image_segment(path, length_frames=24)
        # 新段被 append 到末尾，需要移到 insert_idx
        if insert_idx < len(self.model.segments) - 1:
            seg = self.model.segments.pop()
            self.model.segments.insert(insert_idx, seg)
        self.timeline.rebuild()
        self._refresh_pool()

    def _on_segment_selected(self, seg_id: str):
        seg = next((s for s in self.model.segments if s.seg_id == seg_id), None)
        self.seg_editor.bind_to(seg,
                                  self.model.display_mode, self.model.frame_rate)

    def _on_segment_resized(self, seg_id: str, new_length: int):
        self.model.update_segment(seg_id, length_frames=new_length)
        self.timeline.rebuild()
        # 重新绑定编辑器（length 文案也要刷）
        seg = next((s for s in self.model.segments if s.seg_id == seg_id), None)
        self.seg_editor.bind_to(seg,
                                  self.model.display_mode, self.model.frame_rate)

    def _on_segments_reordered(self, ordered_ids: list):
        self.model.reorder_segments(ordered_ids)
        self.timeline.rebuild()

    def _on_segment_delete(self, seg_id: str):
        self.model.remove_segment(seg_id)
        self.timeline.rebuild()
        self.seg_editor.bind_to(None,
                                  self.model.display_mode, self.model.frame_rate)
        self._refresh_pool()

    def _on_audio_changed(self, audio_id: str, start: int, length: int):
        self.model.update_audio(
            audio_id, start_frame=start, length_frames=length)
        self.timeline.rebuild()

    def _on_audio_delete(self, audio_id: str):
        self.model.remove_audio(audio_id)
        self.timeline.rebuild()

    # ---------- slots: editor & global ----------

    def _on_segment_edited(self, seg_id: str, field: str, value):
        self.model.update_segment(seg_id, **{field: value})
        self.timeline.rebuild()

    def _on_global_changed(self):
        st = self.global_form.get_state()
        for key, val in st.items():
            setattr(self.model, key, val)
        # display_mode / frame_rate 影响 timeline + seg_editor
        cur_seg_id = self.timeline.currently_selected_seg_id()
        cur = next((s for s in self.model.segments
                    if s.seg_id == cur_seg_id), None)
        self.seg_editor.bind_to(cur,
                                  self.model.display_mode, self.model.frame_rate)
        self.timeline.rebuild()

    # ---------- slots: status bar / 提交链路 ----------

    def _on_submit(self):
        ok, msg = self.model.validate()
        if not ok:
            QMessageBox.warning(self, "校验失败", msg)
            return
        try:
            api_key = resolve_api_key(self.cfg)
            template_path = resolve_template_path(self.cfg)
            out_dir = resolve_video_output_dir(self.cfg, self.state.output_dir)
        except (RunningHubUnavailable, RunningHubInvalidSpec) as e:
            QMessageBox.warning(
                self, "配置缺失",
                f"{e}\n\n请在「设置 → RunningHub…」补充。")
            return

        spec = self.model.to_ltx_spec(out_dir)
        self._cancel_flag["v"] = False

        cancel_flag = self._cancel_flag
        cfg = self.cfg

        def task():
            with RunningHubClient(api_key,
                                    base_url=cfg.runninghub_base_url) as client:
                builder = LTXTaskBuilder(template_path)
                handle = submit_ltx_task(
                    client, spec, builder,
                    mode=cfg.runninghub_submit_mode,
                    workflow_id=cfg.runninghub_workflow_id,
                    upload_progress_cb=lambda d, t, p: self._post(
                        "upload", (d, t, p.name)),
                )
                return handle.wait_for_result(
                    timeout=1800, poll_interval=8,
                    progress_cb=lambda s: self._post("status", s),
                    cancel_check=lambda: cancel_flag["v"],
                )

        self.video_status_bar.set_status("提交中…")
        self._worker = FunctionWorker(task)
        self._worker.finished_with_result.connect(self._on_submit_done)
        self._worker.failed.connect(self._on_submit_failed)
        self._worker.start()

    def _post(self, kind: str, payload):
        """worker 线程 → UI 线程的回调转发。"""
        QTimer.singleShot(0, lambda: self._apply_status(kind, payload))

    def _apply_status(self, kind: str, payload):
        if kind == "upload":
            d, t, name = payload
            self.video_status_bar.set_uploading(d, t, name)
        elif kind == "status":
            self.video_status_bar.set_status(payload)

    def _on_submit_done(self, mp4_path):
        self.video_status_bar.set_done(Path(mp4_path))
        self.statusMessage.emit(f"视频已保存：{mp4_path}")

    def _on_submit_failed(self, err_msg: str):
        self.video_status_bar.set_failed(err_msg)

    def _on_cancel(self):
        self._cancel_flag["v"] = True
        self.video_status_bar.set_status("取消中…")

    def _on_open_folder(self, folder):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---------- 缓存 ----------

    def save_cache(self):
        """MainWindow.closeEvent 调用。"""
        try:
            self.cfg.update_settings(
                video_timeline_cache=self.model.to_dict())
        except Exception as e:
            log.warning("video_timeline_cache 保存失败：%s", e)

    def _restore_model(self) -> TimelineModel:
        data = getattr(self.cfg, "video_timeline_cache", None) or {}
        if data:
            try:
                return TimelineModel.from_dict(data)
            except Exception as e:
                log.warning("video_timeline_cache 解析失败，走空 model：%s", e)
        return TimelineModel()
