"""片段缩略图抽帧工具：从视频抽一帧 → QImage。

抽帧用 transition_analyzer 已有的 cv2 读帧逻辑（复用，不重复造轮子）；
QImage 在后台线程构造是安全的，QPixmap 转换留给 GUI 线程。cv2/文件缺失 → None。
"""
from __future__ import annotations


def frame_bgr_to_qimage(frame):
    """OpenCV BGR ndarray → RGB QImage（深拷贝，脱离 numpy 缓冲）。失败 → None。"""
    if frame is None:
        return None
    from PySide6.QtGui import QImage
    h, w = frame.shape[:2]
    rgb = frame[:, :, ::-1].copy()          # BGR→RGB 且连续
    img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return img.copy()                        # 拷贝一份，避免引用临时 numpy 数据


def grab_thumb_qimage(path: str, t_sec: float = 0.0):
    """从 path 视频在 t_sec 处抽 1 帧 → QImage。读不到/无 cv2 → None。"""
    try:
        from drama_shot_master.core.transition_analyzer import _read_frames_cv2
        frames = _read_frames_cv2(path, max(0.0, float(t_sec)), 1)
    except Exception:
        return None
    if not frames:
        return None
    return frame_bgr_to_qimage(frames[0])
