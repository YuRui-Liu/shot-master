"""OverlayMixer：叠加音轨状态机 + 漂移纠偏阈值。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from drama_shot_master.ui.widgets.overlay_audio import OverlayMixer


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_should_resync_threshold():
    assert OverlayMixer._should_resync(0.0, 0.3) is True     # 漂移 0.3s > 0.2
    assert OverlayMixer._should_resync(1.0, 1.1) is False    # 漂移 0.1s < 0.2


def test_set_track_and_enabled(app, tmp_path):
    wav = tmp_path / "bgm.wav"; wav.write_bytes(b"x")
    m = OverlayMixer()
    m.set_track("bgm", str(wav))
    assert m.track_path("bgm") == str(wav)
    assert m.is_enabled("bgm") is False          # 默认不启用
    m.set_enabled("bgm", True)
    assert m.is_enabled("bgm") is True


def test_set_track_none_clears(app):
    m = OverlayMixer()
    m.set_track("sfx", None)
    assert m.track_path("sfx") is None


def test_volume_clamped(app, tmp_path):
    wav = tmp_path / "b.wav"; wav.write_bytes(b"x")
    m = OverlayMixer()
    m.set_track("bgm", str(wav))
    m.set_volume("bgm", 2.0)
    assert m.volume("bgm") == 1.5                # clamp 上限 1.5
    m.set_volume("bgm", -1.0)
    assert m.volume("bgm") == 0.0


def test_play_pause_does_not_crash_without_tracks(app):
    m = OverlayMixer()
    m.play(); m.pause(); m.stop(); m.seek(1.0); m.sync(1.0)   # 无轨不崩


# ── 时间表轨（叠加播放，零渲染）─────────────────────────────────────────

def test_active_clip_index_boundaries():
    sched = [(0.0, 20.0, "/a.mp3"), (20.0, 51.0, "/b.mp3")]
    assert OverlayMixer._active_clip_index(sched, 0.0) == 0
    assert OverlayMixer._active_clip_index(sched, 19.9) == 0
    assert OverlayMixer._active_clip_index(sched, 20.0) == 1     # 边界归下一段
    assert OverlayMixer._active_clip_index(sched, 50.0) == 1
    assert OverlayMixer._active_clip_index(sched, 51.0) == -1    # 超尾 → 空隙
    assert OverlayMixer._active_clip_index([], 1.0) == -1


def test_set_schedule_keeps_existing_files(app, tmp_path):
    a = tmp_path / "a.mp3"; a.write_bytes(b"x")
    m = OverlayMixer()
    m.set_schedule("bgm", [(0.0, 5.0, str(a)), (5.0, 9.0, "/no/such.mp3")])
    assert m.schedule_len("bgm") == 1          # 缺失文件被剔除


class _FakePlayer:
    def __init__(self):
        self.src = None; self.pos = 0; self.state = "stopped"
    def setSource(self, url): self.src = url; self.state = "loaded"
    def setPosition(self, ms): self.pos = ms
    def position(self): return self.pos
    def play(self): self.state = "playing"
    def pause(self): self.state = "paused"
    def stop(self): self.state = "stopped"


def test_sync_switches_clip_source_on_boundary(app, tmp_path):
    a = tmp_path / "a.mp3"; a.write_bytes(b"x")
    b = tmp_path / "b.mp3"; b.write_bytes(b"x")
    m = OverlayMixer()
    m.set_schedule("bgm", [(0.0, 20.0, str(a)), (20.0, 51.0, str(b))])
    m.set_enabled("bgm", True)
    fp = _FakePlayer()
    m._track("bgm").player = fp           # 注入 fake
    m._playing = True
    m.sync(5.0)
    assert fp.src.toLocalFile() == str(a)   # 段0
    assert m._track("bgm").active_idx == 0
    m.sync(25.0)
    assert fp.src.toLocalFile() == str(b)   # 切到段1
    assert m._track("bgm").active_idx == 1
    assert fp.state == "playing"


def test_sync_gap_pauses(app, tmp_path):
    """从段内推进到空隙 → 暂停（从未进段则保持不播，避免每 tick 重复 pause）。"""
    a = tmp_path / "a.mp3"; a.write_bytes(b"x")
    m = OverlayMixer()
    m.set_schedule("bgm", [(0.0, 20.0, str(a))])
    m.set_enabled("bgm", True)
    fp = _FakePlayer()
    m._track("bgm").player = fp
    m._playing = True
    m.sync(5.0)                             # 先进段0（playing）
    assert fp.state == "playing"
    m.sync(30.0)                            # 推进到空隙 → 暂停
    assert fp.state == "paused"
    assert m._track("bgm").active_idx == -1


# ── 卡顿修复：稳态播放不打断（不每 tick play/setPosition）─────────────────

class _CountingPlayer:
    def __init__(self):
        self.src = None; self.pos = 0
        self.set_src = 0; self.set_pos = 0; self.play_n = 0; self.pause_n = 0
    def setSource(self, url): self.src = url; self.set_src += 1
    def setPosition(self, ms): self.pos = ms; self.set_pos += 1
    def position(self): return self.pos
    def play(self): self.play_n += 1
    def pause(self): self.pause_n += 1
    def stop(self): pass


def test_steady_sync_within_segment_is_noop(app, tmp_path):
    """同段稳态推进：sync 不应反复 setSource/setPosition/play（否则卡顿）。"""
    a = tmp_path / "a.mp3"; a.write_bytes(b"x")
    m = OverlayMixer()
    m.set_schedule("bgm", [(0.0, 20.0, str(a))])
    m.set_enabled("bgm", True)
    fp = _CountingPlayer()
    m._track("bgm").player = fp
    m._playing = True
    m.sync(5.0)                       # 首次进段0 → 一次 setSource/setPosition/play
    base = (fp.set_src, fp.set_pos, fp.play_n)
    fp.pos = 5500                      # 模拟播放器自然推进
    m.sync(5.5)
    fp.pos = 6000
    m.sync(6.0)
    fp.pos = 7000
    m.sync(7.0)
    # 稳态三次 sync：不再换源/定位/重播
    assert (fp.set_src, fp.set_pos, fp.play_n) == base


def test_segment_switch_still_reloads(app, tmp_path):
    a = tmp_path / "a.mp3"; a.write_bytes(b"x")
    b = tmp_path / "b.mp3"; b.write_bytes(b"x")
    m = OverlayMixer()
    m.set_schedule("bgm", [(0.0, 20.0, str(a)), (20.0, 40.0, str(b))])
    m.set_enabled("bgm", True)
    fp = _CountingPlayer()
    m._track("bgm").player = fp
    m._playing = True
    m.sync(5.0); n0 = fp.set_src
    m.sync(25.0)                       # 跨入段1 → 必须换源一次
    assert fp.set_src == n0 + 1
    assert fp.src.toLocalFile() == str(b)


def test_seek_forces_reposition_in_same_segment(app, tmp_path):
    a = tmp_path / "a.mp3"; a.write_bytes(b"x")
    m = OverlayMixer()
    m.set_schedule("bgm", [(0.0, 20.0, str(a))])
    m.set_enabled("bgm", True)
    fp = _CountingPlayer()
    m._track("bgm").player = fp
    m._playing = True
    m.sync(5.0); n = fp.set_pos
    m.seek(12.0)                       # 同段内显式 seek → 必须 setPosition
    assert fp.set_pos == n + 1
    assert fp.pos == 12000
