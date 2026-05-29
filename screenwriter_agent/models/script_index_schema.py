"""剧本.json schema（集索引）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EpisodeEntry(BaseModel):
    id: str = Field(..., pattern=r"^E[1-9]\d*$")
    title: str
    summary: str


class ScriptIndex(BaseModel):
    title: str = ""
    episode_count: int = Field(..., ge=1, le=20)
    selected_episode: str = ""
    episodes: list[EpisodeEntry] = Field(default_factory=list)
    input: dict = Field(default_factory=dict)
    updated_at: str = ""
