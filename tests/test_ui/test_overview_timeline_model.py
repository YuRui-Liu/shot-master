"""overview_timeline_model: _Cue dataclass + derive_* 纯函数."""
from drama_shot_master.ui.widgets.overview_timeline_model import _Cue


def test_cue_fields():
    c = _Cue(track="bgm", t_start=0.0, t_end=3.0, label="末日", seg_index=0)
    assert c.track == "bgm"
    assert c.t_start == 0.0
    assert c.t_end == 3.0
    assert c.label == "末日"
    assert c.seg_index == 0
