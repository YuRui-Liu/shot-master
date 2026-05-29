"""7 类 Command + 撤销/重做。每个 Command 持有 (before, after) 状态。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional


class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...
    @abstractmethod
    def undo(self) -> None: ...
    def redo(self) -> None:
        self.execute()
    @abstractmethod
    def describe(self) -> str: ...


def _get_cue_obj(bgm_session, sfx_session, ref):
    if ref.track == "bgm":
        return bgm_session.segments[ref.seg_index] if bgm_session else None
    if ref.track == "sfx":
        return sfx_session.shots[ref.seg_index] if sfx_session else None
    return None


@dataclass
class MoveCue(Command):
    bgm_session: object
    sfx_session: object
    refs: list
    dt_sec: float

    def execute(self):
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            cue.t_start += self.dt_sec
            if r.track == "bgm":
                cue.t_end += self.dt_sec
            cue.user_edited = True

    def undo(self):
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            cue.t_start -= self.dt_sec
            if r.track == "bgm":
                cue.t_end -= self.dt_sec

    def describe(self):
        return f"Move {len(self.refs)} cue(s) by {self.dt_sec:.2f}s"


@dataclass
class ResizeCue(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    side: str          # "start" or "end"
    dt_sec: float

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            if self.side == "start":
                cue.t_start += self.dt_sec
            else:
                cue.t_end += self.dt_sec
        else:
            if self.side == "start":
                cue.t_start += self.dt_sec
                cue.duration -= self.dt_sec
            else:
                cue.duration += self.dt_sec
        cue.user_edited = True

    def undo(self):
        original_dt = self.dt_sec
        self.dt_sec = -self.dt_sec
        self.execute()
        self.dt_sec = original_dt

    def describe(self):
        return f"Resize {self.ref.track} cue {self.side} by {self.dt_sec:.2f}s"


@dataclass
class DeleteCue(Command):
    bgm_session: object
    sfx_session: object
    refs: list
    _backup: list = field(default_factory=list)

    def execute(self):
        self._backup = []
        for r in self.refs:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            if r.track == "bgm":
                self._backup.append((r, cue.chosen_candidate,
                                     getattr(cue, "disabled", False)))
                cue.chosen_candidate = None
                cue.disabled = True
            else:
                self._backup.append((r, None, cue.enabled))
                cue.enabled = False

    def undo(self):
        for r, prev_chosen, prev_flag in self._backup:
            cue = _get_cue_obj(self.bgm_session, self.sfx_session, r)
            if cue is None:
                continue
            if r.track == "bgm":
                cue.chosen_candidate = prev_chosen
                cue.disabled = prev_flag
            else:
                cue.enabled = prev_flag

    def describe(self):
        return f"Delete {len(self.refs)} cue(s)"


@dataclass
class ChangePrompt(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    new_prompt: str
    _old_prompt: str = ""
    _old_candidates: list = field(default_factory=list)
    _old_chosen: Optional[int] = None
    _old_status: str = ""

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            self._old_prompt = getattr(cue, "music_prompt", "")
            self._old_candidates = list(cue.candidates)
            self._old_chosen = cue.chosen_candidate
            self._old_status = cue.status
            cue.music_prompt = self.new_prompt
            cue.candidates = []
            cue.chosen_candidate = None
            cue.status = "prompted"
        else:
            self._old_prompt = cue.prompt_short
            self._old_candidates = list(cue.candidates)
            self._old_chosen = cue.chosen_candidate
            self._old_status = cue.status
            cue.prompt_short = self.new_prompt
            cue.candidates = []
            cue.chosen_candidate = None
            cue.status = "planned"
        cue.user_edited = True

    def undo(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            cue.music_prompt = self._old_prompt
        else:
            cue.prompt_short = self._old_prompt
        cue.candidates = self._old_candidates
        cue.chosen_candidate = self._old_chosen
        cue.status = self._old_status

    def describe(self):
        return f"Change {self.ref.track} prompt"


@dataclass
class ChooseCandidate(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    new_idx: int
    _old_idx: Optional[int] = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        self._old_idx = cue.chosen_candidate
        cue.chosen_candidate = self.new_idx

    def undo(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        cue.chosen_candidate = self._old_idx

    def describe(self):
        return f"Choose candidate {self.new_idx} for {self.ref.track}"


@dataclass
class SplitCue(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    at_t: float
    _inserted_idx: Optional[int] = None
    _old_t_end: Optional[float] = None
    _old_duration: Optional[float] = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        new_cue = deepcopy(cue)
        if self.ref.track == "bgm":
            self._old_t_end = cue.t_end
            new_cue.t_start = self.at_t
            cue.t_end = self.at_t
            new_cue.candidates = []
            new_cue.chosen_candidate = None
            new_cue.status = "prompted"
            self.bgm_session.segments.insert(self.ref.seg_index + 1, new_cue)
        else:
            self._old_duration = cue.duration
            new_dur = (cue.t_start + cue.duration) - self.at_t
            cue.duration = self.at_t - cue.t_start
            new_cue.t_start = self.at_t
            new_cue.duration = new_dur
            new_cue.candidates = []
            new_cue.chosen_candidate = None
            new_cue.status = "planned"
            self.sfx_session.shots.insert(self.ref.seg_index + 1, new_cue)
        cue.user_edited = True
        new_cue.user_edited = True
        self._inserted_idx = self.ref.seg_index + 1

    def undo(self):
        if self._inserted_idx is None:
            return
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        if self.ref.track == "bgm":
            cue.t_end = self._old_t_end
            del self.bgm_session.segments[self._inserted_idx]
        else:
            cue.duration = self._old_duration
            del self.sfx_session.shots[self._inserted_idx]

    def describe(self):
        return f"Split {self.ref.track} at {self.at_t:.2f}s"


@dataclass
class DuplicateCue(Command):
    bgm_session: object
    sfx_session: object
    ref: object
    _inserted_idx: Optional[int] = None

    def execute(self):
        cue = _get_cue_obj(self.bgm_session, self.sfx_session, self.ref)
        if cue is None:
            return
        new_cue = deepcopy(cue)
        if self.ref.track == "bgm":
            dur = cue.t_end - cue.t_start
            new_cue.t_start = cue.t_end
            new_cue.t_end = cue.t_end + dur
            self.bgm_session.segments.insert(self.ref.seg_index + 1, new_cue)
        else:
            new_cue.t_start = cue.t_start + cue.duration
            self.sfx_session.shots.insert(self.ref.seg_index + 1, new_cue)
        new_cue.user_edited = True
        self._inserted_idx = self.ref.seg_index + 1

    def undo(self):
        if self._inserted_idx is None:
            return
        if self.ref.track == "bgm":
            del self.bgm_session.segments[self._inserted_idx]
        else:
            del self.sfx_session.shots[self._inserted_idx]

    def describe(self):
        return "Duplicate cue"
