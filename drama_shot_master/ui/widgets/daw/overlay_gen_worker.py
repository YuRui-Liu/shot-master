"""框选生成异步 worker：在线程池里跑 generate_overlay_clip，只发信号。

子项目 #3d-D5。被 SoundtrackEditor 起一个实例丢进 QThreadPool；worker 不碰
UI/session，只在 run() 里调真正的生成函数（overlay_gen.generate_overlay_clip）：
- 成功 → finished(seg_id, audio_path)
- 失败 → failed(seg_id, error)

UI 槽（主线程）收到信号后再改 OverlaySession + 刷新渲染（见 D7 接线）。
QObject + QRunnable 双继承：QObject 提供信号，QRunnable 让 QThreadPool 可调度。
测试一律注入假 generate_overlay_clip 并直接调 run()，不依赖真线程/网络。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from sound_track_agent.overlay_gen import generate_overlay_clip


class OverlayGenWorker(QObject, QRunnable):
    """异步生成一个 overlay 片段；只发信号，不触碰 UI/session。"""

    finished = Signal(str, str)   # (seg_id, audio_path)
    failed = Signal(str, str)     # (seg_id, error)

    def __init__(self, seg_id: str, kind: str, prompt: str, duration: float,
                 work_dir, cfg, *, client=None, parent=None):
        QObject.__init__(self, parent)
        QRunnable.__init__(self)
        self._seg_id = seg_id
        self._kind = kind
        self._prompt = prompt
        self._duration = float(duration)
        self._work_dir = work_dir
        self._cfg = cfg
        self._client = client

    @property
    def seg_id(self) -> str:
        return self._seg_id

    def run(self) -> None:
        """在工作线程跑生成；异常不外泄，转成 failed 信号。"""
        try:
            path = generate_overlay_clip(
                self._kind, self._prompt, self._duration,
                work_dir=self._work_dir, cfg=self._cfg, client=self._client)
            self.finished.emit(self._seg_id, str(path))
        except Exception as e:  # noqa: BLE001 — 任何生成异常都降级为 failed
            self.failed.emit(self._seg_id, str(e))
