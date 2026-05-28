"""教学系列 02 schema：分镜.json 的目标形状。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str
    appearance: str = ""


class Shot(BaseModel):
    shotId: str
    description: str
    duration: float = 3.0
    composition: str = ""
    stylePrompt: str = ""


class Storyboard(BaseModel):
    title: str
    aspectRatio: str = "9:16"
    fps: int = 24
    totalDuration: float = 0.0
    globalStyle: str = ""
    characters: list[Character] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
