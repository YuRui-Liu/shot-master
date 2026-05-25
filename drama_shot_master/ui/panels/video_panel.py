"""VideoPanel：视频生成主面板。BasePanel 子类，独占主窗口内容区。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
    QListWidget, QWidget, QDialog, QComboBox, QLabel,
)

from drama_shot_master.config import Config
from drama_shot_master.core.video_timeline_model import TimelineModel
from drama_shot_master.core.workflow_profiles import (
    PROFILES, get_profile, template_path_for,
)
from drama_shot_master.providers.runninghub import (
    RunningHubClient, LTXTaskBuilder, submit_ltx_task,
    RunningHubUnavailable, RunningHubInvalidSpec,
    RunningHubUploadError, RunningHubTaskFailed,
    resolve_api_key, resolve_video_output_dir, resolve_template_path,
)
from drama_shot_master.ui.panels.base_panel import BasePanel
from drama_shot_master.ui.state import AppState
from drama_shot_master.ui.widgets.image_pool_widget import ImagePoolWidget
from drama_shot_master.ui.widgets.segment_editor import SegmentEditor
from drama_shot_master.ui.widgets.timeline_widget import TimelineWidget
from drama_shot_master.ui.widgets.video_global_form import VideoGlobalForm
from drama_shot_master.ui.widgets.video_status_bar import VideoStatusBar
from drama_shot_master.ui.worker import FunctionWorker
from drama_shot_master.core.prompt_refiner import (
    build_refine_request, parse_refine_response, load_refine_meta_prompt,
    build_refine_provider,
)
from drama_shot_master.ui.widgets.refine_review_dialog import (
    RefineReviewDialog, RefineRow,
)


log = logging.getLogger(__name__)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class VideoPanel(BasePanel):
    """视频生成主面板。

    5 层纵向：图片池 + toolbar / TimelineWidget / SegmentEditor / VideoGlobalForm / VideoStatusBar。
    所有 model 写入只在本类。
    """

    submitStarted = Signal()
    submitDone = Signal(str)     # mp4 path
    submitFailed = Signal(str)   # error message

    def __init__(self, state: AppState, cfg: Config,
                 model: Optional[TimelineModel] = None, parent=None):
        super().__init__(state, cfg, parent)
        self.model = model if model is not None else TimelineModel()
        self._worker: Optional[FunctionWorker] = None
        self._refine_worker: Optional[FunctionWorker] = None
        self._cancel_flag = {"v": False}
        self._build_ui()
        self._wire()
        self._refresh_all()
        self._sync_workflow_combo()

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
        self.workflow_combo = QComboBox()
        for key, prof in PROFILES.items():
            self.workflow_combo.addItem(prof.name, key)
        pool_toolbar.addWidget(QLabel("工作流"))
        pool_toolbar.addWidget(self.workflow_combo)
        self.btn_import = QPushButton("+ 批量导入图片")
        self.btn_import_dir = QPushButton("+ 当前目录全部")
        self.btn_clear_pool = QPushButton("🗑 清空池")
        self.btn_add_text = QPushButton("+ Add Text")
        self.btn_add_audio = QPushButton("+ Add Audio")
        self.btn_refine = QPushButton("✨ 优化提示词")
        for b in (self.btn_import, self.btn_import_dir, self.btn_clear_pool):
            pool_toolbar.addWidget(b)
        pool_toolbar.addStretch(1)
        pool_toolbar.addWidget(self.btn_add_text)
        pool_toolbar.addWidget(self.btn_add_audio)
        pool_toolbar.addWidget(self.btn_refine)
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
        self.seg_editor.setMaximumHeight(250)
        root.addWidget(self.seg_editor)

        # 4. 全局参数
        self.global_form = VideoGlobalForm()
        self.global_form.setMaximumHeight(290)
        root.addWidget(self.global_form)

        # 5. 状态栏
        self.video_status_bar = VideoStatusBar()
        root.addWidget(self.video_status_bar)

    def _wire(self):
        # toolbar
        self.workflow_combo.currentIndexChanged.connect(self._on_workflow_changed)
        self.btn_import.clicked.connect(self._on_import_images)
        self.btn_import_dir.clicked.connect(self._on_import_current_dir)
        self.btn_clear_pool.clicked.connect(self._on_clear_pool)
        self.btn_add_text.clicked.connect(self._on_add_text)
        self.btn_add_audio.clicked.connect(self._on_add_audio)
        self.btn_refine.clicked.connect(self._on_refine)

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
        self._refresh_total_length()

    def _refresh_pool(self):
        self.image_pool.set_paths(self.model.pool)
        self.image_pool.refresh_usage(self.model.pool_usage())

    def _refresh_total_length(self):
        """根据 model 重算总时长，刷新 status bar 显示。"""
        total_frames = sum(s.length_frames for s in self.model.segments)
        total_seconds = total_frames / max(self.model.frame_rate, 1)
        self.video_status_bar.set_total_length(total_frames, total_seconds)

    # ---------- slots: toolbar ----------

    def _sync_workflow_combo(self):
        idx = self.workflow_combo.findData(self.model.workflow_key)
        if idx >= 0:
            self.workflow_combo.blockSignals(True)
            self.workflow_combo.setCurrentIndex(idx)
            self.workflow_combo.blockSignals(False)

    def _on_workflow_changed(self, _idx: int):
        key = self.workflow_combo.currentData()
        if key:
            self.model.workflow_key = key

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
        self._refresh_total_length()

    def _on_add_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频", str(self.state.current_dir or Path.home()),
            "音频 (*.mp3 *.wav *.flac)")
        if not path:
            return
        self.model.add_audio(Path(path), start_frame=0, length_frames=24)
        self.timeline.rebuild()

    def _on_refine(self):
        if not self.model.segments:
            QMessageBox.information(self, "无内容", "时间轴为空，先添加分镜段")
            return
        if not self.cfg.refine_base_url or not self.cfg.refine_model:
            QMessageBox.warning(
                self, "未配置",
                "请先在「设置 → 提示词优化配置」填 Base URL 和 Model")
            return
        provider = build_refine_provider(self.cfg)
        try:
            system_prompt = load_refine_meta_prompt(self.cfg.refine_meta_prompt_path)
        except FileNotFoundError:
            QMessageBox.critical(
                self, "缺少 meta-prompt",
                f"找不到 meta-prompt 文件："
                f"{self.cfg.refine_meta_prompt_path or 'templates/ltx_refine_meta_prompt.md'}")
            return
        req = build_refine_request(self.model)

        def task():
            raw = provider.generate(req.images, system_prompt, req.user_message)
            return parse_refine_response(raw, req.seg_ids)

        self.video_status_bar.set_status("优化中…")
        self.btn_refine.setEnabled(False)
        self._refine_worker = FunctionWorker(task)
        self._refine_worker.finished_with_result.connect(self._on_refine_done)
        self._refine_worker.failed.connect(self._on_refine_failed)
        self._refine_worker.start()

    def _on_refine_failed(self, err_msg: str):
        self.btn_refine.setEnabled(True)
        self.video_status_bar.set_idle()
        QMessageBox.critical(self, "优化失败", err_msg)

    def _on_refine_done(self, result):
        self.btn_refine.setEnabled(True)
        self.video_status_bar.set_idle()
        rows: list[RefineRow] = []
        if result.global_prompt is not None:
            rows.append(RefineRow("global", "全局",
                                  self.model.global_prompt,
                                  result.global_prompt))
        for seg_id, refined in result.segment_locals:
            seg = next((s for s in self.model.segments
                        if s.seg_id == seg_id), None)
            if seg is None:
                continue
            idx = self.model.segments.index(seg)
            rows.append(RefineRow(
                seg_id, f"段 {idx}（{seg.segment_type}）",
                seg.local_prompt, refined))
        if result.warnings:
            self.statusMessage.emit("；".join(result.warnings))
        if not rows:
            QMessageBox.information(self, "无可替换项", "模型未返回有效的精炼结果")
            return
        dlg = RefineReviewDialog(rows, self)
        if dlg.exec() != QDialog.Accepted:
            return
        accepted = dlg.accepted_keys()
        if "global" in accepted and result.global_prompt is not None:
            self.model.global_prompt = result.global_prompt
        for seg_id, refined in result.segment_locals:
            if seg_id in accepted:
                self.model.update_segment(seg_id, local_prompt=refined)
        self.global_form.set_state(self.model)
        self.timeline.rebuild()
        self.statusMessage.emit(f"已应用 {len(accepted)} 项优化")

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
        self._refresh_total_length()

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
        self._refresh_total_length()

    def _on_segments_reordered(self, ordered_ids: list):
        self.model.reorder_segments(ordered_ids)
        self.timeline.rebuild()

    def _on_segment_delete(self, seg_id: str):
        self.model.remove_segment(seg_id)
        self.timeline.rebuild()
        self.seg_editor.bind_to(None,
                                  self.model.display_mode, self.model.frame_rate)
        self._refresh_pool()
        self._refresh_total_length()

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
        self._refresh_total_length()

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
        self._refresh_total_length()

    # ---------- slots: status bar / 提交链路 ----------

    def _on_submit(self):
        ok, msg = self.model.validate()
        if not ok:
            QMessageBox.warning(self, "校验失败", msg)
            return
        try:
            api_key = resolve_api_key(self.cfg)
            out_dir = resolve_video_output_dir(self.cfg, self.state.output_dir)
        except (RunningHubUnavailable, RunningHubInvalidSpec) as e:
            QMessageBox.warning(
                self, "配置缺失",
                f"{e}\n\n请在「设置 → RunningHub…」补充。")
            return

        profile = get_profile(self.model.workflow_key)
        # 导演台 profile 仍尊重「自定义模板路径」设置（resolve_template_path 自带兜底）；
        # 其它 profile 用各自内置模板。
        if profile.key == "director":
            template_path = resolve_template_path(self.cfg)
        else:
            template_path = template_path_for(profile)
        wf_id = (self.cfg.workflow_ids or {}).get(profile.key) or (
            self.cfg.runninghub_workflow_id if profile.key == "director" else "")
        if not wf_id:
            QMessageBox.warning(
                self, "未配置 workflow_id",
                f"请在「设置 → RunningHub」填「{profile.name}」的 workflow_id")
            return

        spec = self.model.to_ltx_spec(out_dir)
        self._cancel_flag["v"] = False

        cancel_flag = self._cancel_flag
        cfg = self.cfg

        def task():
            with RunningHubClient(api_key,
                                    base_url=cfg.runninghub_base_url) as client:
                builder = LTXTaskBuilder(template_path, profile)
                handle = submit_ltx_task(
                    client, spec, builder,
                    workflow_id=wf_id,
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
        self.submitStarted.emit()

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
        self.submitDone.emit(str(mp4_path))

    def _on_submit_failed(self, err_msg: str):
        self.video_status_bar.set_failed(err_msg)
        self.submitFailed.emit(err_msg)

    def _on_cancel(self):
        self._cancel_flag["v"] = True
        self.video_status_bar.set_status("取消中…")

    def _on_open_folder(self, folder):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
