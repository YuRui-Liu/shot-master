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


class LLMCreds(BaseModel):
    """OpenAI 兼容协议下，请求体直接带 LLM 凭据——主软件作为单一可信来源
    每个请求注入；agent 不再依赖 env 配置（避免 spawn 时 cfg 没准备好、
    僵尸 agent 残留旧 env、用户改设置不重启不生效等长尾问题）。"""
    api_key: str | None = None
    base_url: str | None = None


class IdeateChatReq(BaseModel):
    project_dir: str
    context: IdeateContext
    messages: list[ChatMessage] = Field(default_factory=list)
    model: str | None = None
    reasoning_effort: str = "high"
    auto_save_idea_json: bool = True
    creds: LLMCreds | None = None         # 主软件每请求注入


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
    creds: LLMCreds | None = None


class StoryboardOptions(BaseModel):
    aspect_ratio: str = "9:16"
    fps: int = 24
    shot_duration_default: float = 3.0          # 向后兼容：缺时长的兜底单值
    shot_duration_min: float = 4.0              # 镜头时长范围下限（秒）
    shot_duration_max: float = 10.0             # 镜头时长范围上限（秒）
    density: str = "常规"


class StoryboardReq(BaseModel):
    project_dir: str
    episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")
    options: StoryboardOptions = Field(default_factory=StoryboardOptions)
    model: str | None = None
    reasoning_effort: str = "max"
    creds: LLMCreds | None = None


class PromptsOptions(BaseModel):
    grid_mode: str = "9"                  # "single" | "4" | "9"
    include_character_refs: bool = True
    style_extra: str = ""
    negative_preset: str = "标准 SDXL"
    quality_boost: bool = True


class PromptsReq(BaseModel):
    project_dir: str
    episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")
    options: PromptsOptions = Field(default_factory=PromptsOptions)
    model: str | None = None
    reasoning_effort: str = "high"
    creds: LLMCreds | None = None


class ScriptOutlineReq(BaseModel):
    project_dir: str
    episode_count: int = Field(..., ge=1, le=20)
    options: ScriptOptions = Field(default_factory=ScriptOptions)
    model: str | None = None
    reasoning_effort: str = "high"
    creds: LLMCreds | None = None


class ScriptEpisodeReq(BaseModel):
    project_dir: str
    episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")
    options: ScriptOptions = Field(default_factory=ScriptOptions)
    model: str | None = None
    reasoning_effort: str = "high"
    creds: LLMCreds | None = None


class VideoPromptOptions(BaseModel):
    fps: int = 24
    aspect_ratio: str = "9:16"
    style_note: str = ""
    template_id: str = "ltx"        # "ltx"=画面/运镜/音效 LTX2.3增强(默认) | "simple"=Camera:…
    language: str = "en"            # "en"=全英文(默认) | "zh"=全中文


class VideoPromptReq(BaseModel):
    project_dir: str
    episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")
    options: VideoPromptOptions = Field(default_factory=VideoPromptOptions)
    model: str | None = None
    reasoning_effort: str = "high"
    creds: LLMCreds | None = None


class AudioPromptOptions(BaseModel):
    language: str = "zh"
    include_bgm_tags: bool = True


class AudioPromptReq(BaseModel):
    project_dir: str
    episode_id: str = Field(..., pattern=r"^E[1-9]\d*$")
    options: AudioPromptOptions = Field(default_factory=AudioPromptOptions)
    model: str | None = None
    reasoning_effort: str = "high"
    creds: LLMCreds | None = None
