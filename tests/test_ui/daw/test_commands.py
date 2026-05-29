"""7 Command 类 execute / undo 测试。"""
from sound_track_agent.session import SegmentScore, ScoringSession, BGMCandidate
from sound_track_agent.sfx.session import SFXSession, SFXShot, SFXCandidate
from drama_shot_master.ui.widgets.daw.selection import _CueRef
from drama_shot_master.ui.widgets.daw.commands import (
    MoveCue, ResizeCue, DeleteCue, SplitCue, DuplicateCue,
    ChangePrompt, ChooseCandidate,
)


def _bgm_sess():
    return ScoringSession(
        source_mp4="/m.mp4", source_hash="h", global_style="x", frame_rate=24.0,
        segments=[
            SegmentScore(0, 0.0, 5.0, music_prompt="末日",
                         candidates=[BGMCandidate(path="/a.mp3", seed=1, prompt="末日")],
                         chosen_candidate=0, status="generated"),
            SegmentScore(1, 5.0, 10.0, music_prompt="紧张"),
        ])


def _sfx_sess():
    return SFXSession(
        source_mp4="/m.mp4", source_hash="h", frame_rate=24.0,
        shots=[
            SFXShot(0, 0.0, 3.0, duration=3.0, prompt_short="门",
                    candidates=[SFXCandidate(path="/a.mp3", seed=1, prompt="门")],
                    chosen_candidate=0, status="generated"),
            SFXShot(1, 3.0, 6.0, duration=3.0, prompt_short="脚步"),
        ])


# ------- MoveCue (4 tests) -------

def test_move_cue_bgm_shifts_both_t_start_t_end():
    bgm = _bgm_sess()
    cmd = MoveCue(bgm, None, [_CueRef("bgm", 0)], dt_sec=2.0)
    cmd.execute()
    assert bgm.segments[0].t_start == 2.0
    assert bgm.segments[0].t_end == 7.0
    assert bgm.segments[0].user_edited is True


def test_move_cue_sfx_shifts_only_t_start():
    sfx = _sfx_sess()
    cmd = MoveCue(None, sfx, [_CueRef("sfx", 0)], dt_sec=1.5)
    cmd.execute()
    assert sfx.shots[0].t_start == 1.5
    assert sfx.shots[0].duration == 3.0


def test_move_cue_undo_reverses():
    bgm = _bgm_sess()
    cmd = MoveCue(bgm, None, [_CueRef("bgm", 0)], dt_sec=2.0)
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].t_start == 0.0
    assert bgm.segments[0].t_end == 5.0


def test_move_cue_multiple_refs():
    bgm = _bgm_sess()
    cmd = MoveCue(bgm, None,
                  [_CueRef("bgm", 0), _CueRef("bgm", 1)], dt_sec=1.0)
    cmd.execute()
    assert bgm.segments[0].t_start == 1.0
    assert bgm.segments[1].t_start == 6.0


# ------- ResizeCue (4 tests) -------

def test_resize_bgm_start_changes_t_start():
    bgm = _bgm_sess()
    cmd = ResizeCue(bgm, None, _CueRef("bgm", 0), side="start", dt_sec=1.0)
    cmd.execute()
    assert bgm.segments[0].t_start == 1.0
    assert bgm.segments[0].t_end == 5.0


def test_resize_bgm_end_changes_t_end():
    bgm = _bgm_sess()
    cmd = ResizeCue(bgm, None, _CueRef("bgm", 0), side="end", dt_sec=2.0)
    cmd.execute()
    assert bgm.segments[0].t_end == 7.0


def test_resize_sfx_end_changes_duration():
    sfx = _sfx_sess()
    cmd = ResizeCue(None, sfx, _CueRef("sfx", 0), side="end", dt_sec=1.0)
    cmd.execute()
    assert sfx.shots[0].duration == 4.0


def test_resize_undo_reverses():
    bgm = _bgm_sess()
    cmd = ResizeCue(bgm, None, _CueRef("bgm", 0), side="end", dt_sec=2.0)
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].t_end == 5.0


# ------- DeleteCue (3 tests) -------

def test_delete_bgm_sets_chosen_none_and_disabled():
    bgm = _bgm_sess()
    cmd = DeleteCue(bgm, None, [_CueRef("bgm", 0)])
    cmd.execute()
    assert bgm.segments[0].chosen_candidate is None
    assert bgm.segments[0].disabled is True


def test_delete_sfx_sets_enabled_false():
    sfx = _sfx_sess()
    cmd = DeleteCue(None, sfx, [_CueRef("sfx", 0)])
    cmd.execute()
    assert sfx.shots[0].enabled is False


def test_delete_undo_restores():
    bgm = _bgm_sess()
    cmd = DeleteCue(bgm, None, [_CueRef("bgm", 0)])
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].chosen_candidate == 0
    assert bgm.segments[0].disabled is False


# ------- ChangePrompt (3 tests) -------

def test_change_prompt_bgm_clears_candidates():
    bgm = _bgm_sess()
    cmd = ChangePrompt(bgm, None, _CueRef("bgm", 0), new_prompt="赛博")
    cmd.execute()
    assert bgm.segments[0].music_prompt == "赛博"
    assert bgm.segments[0].candidates == []
    assert bgm.segments[0].chosen_candidate is None
    assert bgm.segments[0].status == "prompted"


def test_change_prompt_sfx_clears_candidates():
    sfx = _sfx_sess()
    cmd = ChangePrompt(None, sfx, _CueRef("sfx", 0), new_prompt="开窗")
    cmd.execute()
    assert sfx.shots[0].prompt_short == "开窗"
    assert sfx.shots[0].candidates == []
    assert sfx.shots[0].status == "planned"


def test_change_prompt_undo_restores_all():
    bgm = _bgm_sess()
    cmd = ChangePrompt(bgm, None, _CueRef("bgm", 0), new_prompt="赛博")
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].music_prompt == "末日"
    assert len(bgm.segments[0].candidates) == 1
    assert bgm.segments[0].chosen_candidate == 0
    assert bgm.segments[0].status == "generated"


# ------- ChooseCandidate (2 tests) -------

def test_choose_candidate_changes_chosen():
    bgm = _bgm_sess()
    bgm.segments[0].candidates.append(
        BGMCandidate(path="/b.mp3", seed=2, prompt="末日"))
    cmd = ChooseCandidate(bgm, None, _CueRef("bgm", 0), new_idx=1)
    cmd.execute()
    assert bgm.segments[0].chosen_candidate == 1


def test_choose_candidate_undo_restores():
    bgm = _bgm_sess()
    bgm.segments[0].candidates.append(
        BGMCandidate(path="/b.mp3", seed=2, prompt="末日"))
    cmd = ChooseCandidate(bgm, None, _CueRef("bgm", 0), new_idx=1)
    cmd.execute()
    cmd.undo()
    assert bgm.segments[0].chosen_candidate == 0


# ------- SplitCue (3 tests) -------

def test_split_bgm_inserts_new_after():
    bgm = _bgm_sess()
    cmd = SplitCue(bgm, None, _CueRef("bgm", 0), at_t=3.0)
    cmd.execute()
    assert len(bgm.segments) == 3
    assert bgm.segments[0].t_end == 3.0
    assert bgm.segments[1].t_start == 3.0
    assert bgm.segments[1].t_end == 5.0
    assert bgm.segments[1].status == "prompted"
    assert bgm.segments[1].candidates == []


def test_split_sfx_changes_duration():
    sfx = _sfx_sess()
    cmd = SplitCue(None, sfx, _CueRef("sfx", 0), at_t=2.0)
    cmd.execute()
    assert len(sfx.shots) == 3
    assert sfx.shots[0].duration == 2.0
    assert sfx.shots[1].t_start == 2.0
    assert sfx.shots[1].duration == 1.0
    assert sfx.shots[1].status == "planned"


def test_split_undo_restores():
    bgm = _bgm_sess()
    orig_t_end = bgm.segments[0].t_end
    cmd = SplitCue(bgm, None, _CueRef("bgm", 0), at_t=3.0)
    cmd.execute()
    cmd.undo()
    assert len(bgm.segments) == 2
    assert bgm.segments[0].t_end == orig_t_end


# ------- DuplicateCue (2 tests) -------

def test_duplicate_bgm_inserts_after():
    bgm = _bgm_sess()
    cmd = DuplicateCue(bgm, None, _CueRef("bgm", 0))
    cmd.execute()
    assert len(bgm.segments) == 3
    assert bgm.segments[1].t_start == 5.0
    assert bgm.segments[1].t_end == 10.0


def test_duplicate_undo_removes():
    sfx = _sfx_sess()
    cmd = DuplicateCue(None, sfx, _CueRef("sfx", 0))
    cmd.execute()
    cmd.undo()
    assert len(sfx.shots) == 2
