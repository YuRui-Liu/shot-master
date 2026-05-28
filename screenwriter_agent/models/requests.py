"""路由请求体 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class IdeateContext(BaseModel):
    core_idea: str = ""
    genre_tags: list[str] = Field(default_factory=list)
    format: str = "短剧"
    tone_tags: list[str] = Field(default_factory=list)
    visual_style: str = ""
    candidate_count: int = 3
    duration_sec: int = 60
    extra_constraints: str = ""


class ChatMessage(BaseModel):
    role: str           # "user" | "assistant" | "system"
    content: str


class IdeateChatReq(BaseModel):
    project_dir: str
    context: IdeateContext
    messages: list[ChatMessage] = Field(default_factory=list)
    model: str | None = None
    reasoning_effort: str = "high"
    auto_save_idea_json: bool = True


class IdeateSelectReq(BaseModel):
    project_dir: str
    selected_id: str


class ScriptOptions(BaseModel):
    length_preset: str = "完整版"
    language_style: str = "口语化"
    fps: int = 24
    duration_sec: int = 60


class ScriptReq(BaseModel):
    project_dir: str
    options: ScriptOptions = Field(default_factory=ScriptOptions)
    model: str | None = None
    reasoning_effort: str = "high"


class StoryboardOptions(BaseModel):
    aspect_ratio: str = "9:16"
    fps: int = 24
    shot_duration_default: float = 3.0
    density: str = "常规"


class StoryboardReq(BaseModel):
    project_dir: str
    options: StoryboardOptions = Field(default_factory=StoryboardOptions)
    model: str | None = None
    reasoning_effort: str = "max"
