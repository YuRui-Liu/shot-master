"""创意候选 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class IdeaCandidate(BaseModel):
    id: str
    title: str
    angle: str = ""
    summary: str = ""
    highlights: str = ""
    est_duration: int = 0


class IdeaFile(BaseModel):
    input: dict
    messages: list[dict] = Field(default_factory=list)
    candidates: list[IdeaCandidate] = Field(default_factory=list)
    selected_id: str = ""
    updated_at: str = ""
