from unittest.mock import patch
import numpy as np
import cv2
import pytest

from sound_track_agent.shot_detector import detect_shots, _video_duration_seconds
from sound_track_agent.segment_planner import Shot


def _write_hardcut_video(path, fps=24, seconds_each=1, colors=(0, 255, 128)):
    """造一个每 `seconds_each` 秒硬切一次纯色的视频（scenedetect 能检出切点）。"""
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         float(fps), (64, 64))
    assert vw.isOpened()
    for c in colors:
        for _ in range(fps * seconds_each):
            vw.write(np.full((64, 64, 3), c, np.uint8))
    vw.release()


def test_detect_shots_finds_cuts(tmp_path):
    v = tmp_path / "hc.mp4"
    _write_hardcut_video(v, fps=24, seconds_each=1, colors=(0, 255, 128))
    shots = detect_shots(v)
    assert len(shots) == 3
    assert all(isinstance(s, Shot) for s in shots)
    assert shots[0].t_start == 0.0
    assert abs(shots[0].t_end - 1.0) < 0.15
    assert abs(shots[1].t_start - 1.0) < 0.15
    assert shots[-1].t_end > 2.5
    assert [s.index for s in shots] == [0, 1, 2]


def test_detect_shots_falls_back_to_single_when_no_cuts(tmp_path):
    v = tmp_path / "x.mp4"
    _write_hardcut_video(v, fps=24, seconds_each=1, colors=(0,))
    with patch("sound_track_agent.shot_detector.detect", return_value=[]):
        shots = detect_shots(v)
    assert len(shots) == 1
    assert shots[0].index == 0
    assert shots[0].t_start == 0.0
    assert shots[0].t_end > 0.5


def test_video_duration_seconds(tmp_path):
    v = tmp_path / "d.mp4"
    _write_hardcut_video(v, fps=24, seconds_each=1, colors=(0, 255))
    dur = _video_duration_seconds(v)
    assert abs(dur - 2.0) < 0.15
