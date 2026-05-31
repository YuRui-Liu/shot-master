"""片段缩略图：ClipStrip 缓存缩略图跨重建保留 + ComposePanel 抽帧注入。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPixmap, QColor


def _app():
    return QApplication.instance() or QApplication([])


def _solid_qimage(color="red", w=80, h=120):
    img = QImage(w, h, QImage.Format_RGB888)
    img.fill(QColor(color))
    return img


class _Cfg:
    video_output_dir = ""


def test_clipstrip_thumb_survives_rebuild():
    """set_thumb 后即使 refresh/reorder 触发卡片重建，缩略图仍在。"""
    _app()
    from drama_shot_master.core.composition_model import ReelClip, CompositionModel
    from drama_shot_master.ui.widgets.compose.clip_strip import ClipStrip
    m = CompositionModel(clips=[ReelClip.new(path="/0.mp4", duration=8),
                                ReelClip.new(path="/1.mp4", duration=6)])
    s = ClipStrip()
    s.set_model(m)
    cid = m.clips[0].clip_id
    s.set_thumb(cid, QPixmap.fromImage(_solid_qimage()))
    assert s.has_thumb(cid)
    assert not s._cards[cid].thumb.pixmap().isNull()
    s.refresh()                       # 重建卡片
    assert not s._cards[cid].thumb.pixmap().isNull()   # 缩略图保留


def test_compose_panel_loads_thumbs_sync():
    """_load_thumbs_sync 用注入 provider 给每个片段抽帧并落到卡片。"""
    _app()
    from drama_shot_master.ui.panels.compose_panel import ComposePanel
    payload = {"clips": [{"path": "/a/x.mp4", "duration": 8},
                         {"path": "/a/y.mp4", "duration": 6}]}
    p = ComposePanel(_Cfg(), payload=payload)
    ids = [c.clip_id for c in p._model.clips]
    calls = []
    def provider(path, t_sec):
        calls.append((path, t_sec))
        return _solid_qimage()
    p._load_thumbs_sync(provider=provider)
    assert len(calls) == 2
    for cid in ids:
        assert not p._strip._cards[cid].thumb.pixmap().isNull()


def test_frame_bgr_to_qimage_roundtrip():
    """BGR ndarray → QImage 尺寸正确、非空。"""
    import numpy as np
    from drama_shot_master.ui.widgets.compose.thumbs import frame_bgr_to_qimage
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    frame[:, :, 2] = 255   # BGR 红通道
    img = frame_bgr_to_qimage(frame)
    assert img is not None and not img.isNull()
    assert img.width() == 60 and img.height() == 40
