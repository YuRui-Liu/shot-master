"""Load configuration from .env and settings.json.

.env: 静态配置（API keys、默认值）；本进程启动时只读
settings.json: 运行时偏好（当前 provider / model / 默认输出策略）；可被 UI 改写
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

from drama_shot_master.core.video_task_store import _gen_task_id


# OpenAI 兼容 endpoints 的 key 名（在 .env 里以 {NAME}_API_KEY / {NAME}_BASE_URL 形式存在）
OPENAI_COMPAT_ENDPOINTS = [
    "openai", "deepseek", "doubao", "openrouter", "siliconflow", "vllm", "ollama"
]
# 独立 SDK 后端
INDEPENDENT_PROVIDERS = ["gemini", "anthropic", "qwen"]


@dataclass
class Config:
    default_provider: str = "doubao"
    default_model: str = "doubao-seed-2-0-pro-260215"
    current_provider: str = "doubao"
    current_model: str = "doubao-seed-2-0-pro-260215"
    api_keys: dict[str, str] = field(default_factory=dict)
    base_urls: dict[str, str] = field(default_factory=dict)
    default_output_dir: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 7866
    settings_path: Optional[Path] = None
    ui: dict = field(default_factory=lambda: {"theme": "light", "preview_thumb_size": 200})
    last_input_dir: Optional[str] = None
    last_output_dir: Optional[str] = None
    comfyui_url: str = "http://127.0.0.1:8188"
    split_resample_defaults: dict = field(default_factory=lambda: {
        "enabled": False, "aspect_w": 1, "aspect_h": 1,
        "long_edge": 2048, "algorithm": "lanczos", "ai_model": "",
    })
    runninghub_api_key: str = ""
    runninghub_workflow_id: str = ""
    runninghub_base_url: str = "https://www.runninghub.cn"
    runninghub_template_path: str = ""           # 空 = 用内置 drama_shot_master/templates/ltx_director_v23.json
    video_output_dir: str = ""                   # 空 = 用 state.output_dir
    video_timeline_cache: dict = field(default_factory=dict)
    video_tasks: list = field(default_factory=list)
    soundtrack_tasks: list = field(default_factory=list)
    dub_tasks: list = field(default_factory=list)
    dub_workflow_ids: dict = field(default_factory=lambda: {
        "voice_design": "2059260167811850242",
        "voice_clone": "2058388078015901697",
    })
    dub_node_profiles: dict = field(default_factory=dict)   # 角色→节点号 覆盖（可选）
    dub_output_dir: str = ""
    dub_sampling: dict = field(default_factory=lambda: {
        "top_k": 30, "top_p": 0.8, "temperature": 0.8, "num_beams": 3,
        "max_mel_tokens": 1500,
    })
    imggen_tasks: list = field(default_factory=list)
    imggen_provider: str = "doubao"
    imggen_base_url: str = "https://ark.cn-beijing.volces.com"
    imggen_model: str = ""
    imggen_api_key: str = ""
    imggen_output_dir: str = ""
    imggen_watermark: bool = False
    soundtrack_workflow_id: str = "2059090557116440578"
    soundtrack_output_dir: str = ""
    soundtrack_seeds_count: int = 2
    soundtrack_crossfade: float = 0.5
    accent_big_threshold: float = 0.7
    accent_snap_window: float = 0.6
    workflow_ids: dict = field(default_factory=dict)
    last_active_function: str = "inference"      # 上次退出时活跃的 panel
    # 翻译
    deeplx_url: str = ""
    current_translator: str = ""                         # "tencent" | "deeplx" (empty = post-load 决定)
    tencent_translator_secret_id: str = ""
    tencent_translator_secret_key: str = ""
    tencent_translator_region: str = "ap-beijing"
    tencent_translator_project_id: int = 0
    # 帧提示词优化（refine）独立 provider
    refine_base_url: str = ""
    refine_api_key: str = ""
    refine_model: str = ""
    refine_provider_preset: str = "ollama"     # 旧字段，保留兼容
    refine_provider: str = ""                  # 新字段：LLM 平台 id（deepseek/doubao/openai）
    refine_meta_prompt_path: str = ""
    # screenwriter_agent
    screenwriter_agent_port: int = 18430
    screenwriter_llm_api_key: str = ""
    screenwriter_llm_base_url: str = "https://api.deepseek.com"
    # 默认用 DeepSeek 当前主推的 V4 模型（参考 deepseek.com 官方定价页）。
    # deepseek-v4-flash: 快速非思考；deepseek-v4-pro: 推理思考。
    # 旧名 deepseek-chat / deepseek-reasoner 仍可用但官方计划弃用。
    screenwriter_models: dict[str, str] = field(default_factory=lambda: {
        "ideate":     "deepseek-v4-flash",
        "script":     "deepseek-v4-flash",
        "storyboard": "deepseek-v4-flash",
        "prompts":    "deepseek-v4-flash",
    })
    screenwriter_project_root: str = ""    # 默认空，UI 提示选目录
    prompts_default_grid: str = "4"        # 分镜图提示词默认宫格："single"|"4"|"9"
    # 编剧阶段映射：{"ideate":{"provider":"deepseek","model":"deepseek-chat"}, ...}
    screenwriter_stage_assignments: dict[str, dict] = field(default_factory=dict)
    # 编剧项目任务列表（绝对路径数组；与 screenwriter_project_root 区分——
    # 后者只是「新建」按钮的默认 base，前者是任务栏里被纳管的项目）
    screenwriter_projects: list[str] = field(default_factory=list)
    # LLM 平台配置（跨功能共享，由「设置→平台核心→LLM 平台」section 配）：
    # {"deepseek":{"base_url","api_key"}, "doubao":{...}, "openai":{...}}
    llm_providers: dict[str, dict] = field(default_factory=dict)
    # Sprint 0：曝光 Phase 1+2+3 后端能力
    refine_frames_per_shot: int = 3                  # 1 / 3 / 5
    refine_max_segments: int = 5
    refine_merge_threshold: float = 0.25
    accent_max_stretch: float = 0.10
    soundtrack_max_concurrency: int = 3
    soundtrack_score_weights: dict = field(
        default_factory=lambda: {"health": 0.5, "headroom": 0.3, "beat": 0.2})
    soundtrack_fade_out: bool = False                # ACE-Step prompt 末尾 [Quick smooth fade out] 标记开关；
                                                     # 开启会让 BGM 末尾约 25% 衰减到静音，默认关闭以保住完整段长。
    # UI 状态
    task_bar_collapsed: dict = field(default_factory=dict)

    # Phase 4a: SFX 音效层
    sfx_workflow_id: str = "2060218796413112321"        # Stable Audio 3 / RunningHub
    sfx_plan_frames_per_shot: int = 3                   # event_planner 抽帧数 1/3/5
    sfx_max_concurrency: int = 3                        # 并发提交上限
    sfx_default_volume: float = 0.8                     # 单条 SFX 默认音量（让对白突出）
    sfx_ducking_db: float = -6.0                        # SFX 触发时 BGM 衰减分贝
    sfx_seeds_count: int = 1                            # 单镜默认候选数

    def update_settings(self, **kwargs) -> None:
        """更新运行时设置并落盘到 settings.json"""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        if self.settings_path:
            data = {
                "current_provider": self.current_provider,
                "current_model": self.current_model,
                "ui": self.ui,
                "last_input_dir": self.last_input_dir,
                "last_output_dir": self.last_output_dir,
                "comfyui_url": self.comfyui_url,
                "split_resample_defaults": self.split_resample_defaults,
                "runninghub_api_key": self.runninghub_api_key,
                "runninghub_workflow_id": self.runninghub_workflow_id,
                "runninghub_base_url": self.runninghub_base_url,
                "runninghub_template_path": self.runninghub_template_path,
                "video_output_dir": self.video_output_dir,
                "video_timeline_cache": self.video_timeline_cache,
                "video_tasks": self.video_tasks,
                "soundtrack_tasks": self.soundtrack_tasks,
                "dub_tasks": self.dub_tasks,
                "dub_workflow_ids": self.dub_workflow_ids,
                "dub_node_profiles": self.dub_node_profiles,
                "dub_output_dir": self.dub_output_dir,
                "dub_sampling": self.dub_sampling,
                "imggen_tasks": self.imggen_tasks,
                "imggen_provider": self.imggen_provider,
                "imggen_base_url": self.imggen_base_url,
                "imggen_model": self.imggen_model,
                "imggen_api_key": self.imggen_api_key,
                "imggen_output_dir": self.imggen_output_dir,
                "imggen_watermark": self.imggen_watermark,
                "soundtrack_workflow_id": self.soundtrack_workflow_id,
                "soundtrack_output_dir": self.soundtrack_output_dir,
                "soundtrack_seeds_count": self.soundtrack_seeds_count,
                "soundtrack_crossfade": self.soundtrack_crossfade,
                "accent_big_threshold": self.accent_big_threshold,
                "accent_snap_window": self.accent_snap_window,
                "workflow_ids": self.workflow_ids,
                "last_active_function": self.last_active_function,
                "deeplx_url": self.deeplx_url,
                "current_translator": self.current_translator,
                "tencent_translator_secret_id": self.tencent_translator_secret_id,
                "tencent_translator_secret_key": self.tencent_translator_secret_key,
                "tencent_translator_region": self.tencent_translator_region,
                "tencent_translator_project_id": self.tencent_translator_project_id,
                "refine_base_url": self.refine_base_url,
                "refine_api_key": self.refine_api_key,
                "refine_model": self.refine_model,
                "refine_provider_preset": self.refine_provider_preset,
                "refine_provider": self.refine_provider,
                "refine_meta_prompt_path": self.refine_meta_prompt_path,
                "screenwriter_agent_port": self.screenwriter_agent_port,
                "screenwriter_llm_api_key": self.screenwriter_llm_api_key,
                "screenwriter_llm_base_url": self.screenwriter_llm_base_url,
                "screenwriter_models": self.screenwriter_models,
                "screenwriter_project_root": self.screenwriter_project_root,
                "prompts_default_grid": self.prompts_default_grid,
                "screenwriter_stage_assignments": self.screenwriter_stage_assignments,
                "screenwriter_projects": self.screenwriter_projects,
                "llm_providers": self.llm_providers,
                "refine_frames_per_shot": self.refine_frames_per_shot,
                "refine_max_segments": self.refine_max_segments,
                "refine_merge_threshold": self.refine_merge_threshold,
                "accent_max_stretch": self.accent_max_stretch,
                "soundtrack_max_concurrency": self.soundtrack_max_concurrency,
                "soundtrack_score_weights": self.soundtrack_score_weights,
                "soundtrack_fade_out": self.soundtrack_fade_out,
                "sfx_workflow_id": self.sfx_workflow_id,
                "sfx_plan_frames_per_shot": self.sfx_plan_frames_per_shot,
                "sfx_max_concurrency": self.sfx_max_concurrency,
                "sfx_default_volume": self.sfx_default_volume,
                "sfx_ducking_db": self.sfx_ducking_db,
                "sfx_seeds_count": self.sfx_seeds_count,
                "task_bar_collapsed": self.task_bar_collapsed,
            }
            self.settings_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8")


def load_config(env_path: Path = Path(".env"),
                settings_path: Path = Path("settings.json")) -> Config:
    env = dotenv_values(env_path) if env_path.exists() else {}

    api_keys: dict[str, str] = {}
    base_urls: dict[str, str] = {}
    for name in INDEPENDENT_PROVIDERS:
        key = env.get(f"{name.upper()}_API_KEY") or env.get(f"{name.upper()}_KEY")
        if key:
            api_keys[name] = key
        url = env.get(f"{name.upper()}_BASE_URL")
        if url:
            base_urls[name] = url
    # DashScope key 在 .env 里叫 DASHSCOPE_API_KEY；映射成 provider 名 "qwen"
    if env.get("DASHSCOPE_API_KEY"):
        api_keys["qwen"] = env["DASHSCOPE_API_KEY"]
    for name in OPENAI_COMPAT_ENDPOINTS:
        key = env.get(f"{name.upper()}_API_KEY")
        if key:
            api_keys[name] = key
        url = env.get(f"{name.upper()}_BASE_URL")
        if url:
            base_urls[name] = url

    # RunningHub
    rh_api_key = env.get("RUNNINGHUB_API_KEY") or ""
    rh_base_url = env.get("RUNNINGHUB_BASE_URL") or "https://www.runninghub.cn"

    cfg = Config(
        default_provider=env.get("DEFAULT_PROVIDER", "doubao"),
        default_model=env.get("DEFAULT_MODEL", "doubao-seed-2-0-pro-260215"),
        api_keys=api_keys,
        base_urls=base_urls,
        default_output_dir=env.get("DEFAULT_OUTPUT_DIR") or None,
        host=env.get("HOST", "127.0.0.1"),
        port=int(env.get("PORT", "7866")),
        runninghub_api_key=rh_api_key,
        runninghub_base_url=rh_base_url,
        settings_path=settings_path,
        deeplx_url=env.get("DEEPLX_URL") or "",
        tencent_translator_secret_id=(
            env.get("TENCENTCLOUD_SECRET_ID") or os.environ.get("TENCENTCLOUD_SECRET_ID") or ""),
        tencent_translator_secret_key=(
            env.get("TENCENTCLOUD_SECRET_KEY") or os.environ.get("TENCENTCLOUD_SECRET_KEY") or ""),
        tencent_translator_region=(
            env.get("TENCENTCLOUD_REGION") or os.environ.get("TENCENTCLOUD_REGION") or "ap-beijing"),
    )
    cfg.current_provider = cfg.default_provider
    cfg.current_model = cfg.default_model

    if settings_path.exists():
        try:
            # 兼容老 settings.json（Windows 默认 GBK 编码）：先 UTF-8 严格读，
            # 失败则回退按 locale 默认编码读；若仍失败则交给外层 except 走默认值
            try:
                raw = settings_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw = settings_path.read_text()    # locale 默认（Win 上为 cp936）
            data = json.loads(raw)
            if isinstance(data, dict):
                if "current_provider" in data:
                    cfg.current_provider = data["current_provider"]
                if "current_model" in data:
                    cfg.current_model = data["current_model"]
                if "ui" in data and isinstance(data["ui"], dict):
                    cfg.ui.update(data["ui"])
                if "last_input_dir" in data:
                    cfg.last_input_dir = data["last_input_dir"]
                if "last_output_dir" in data:
                    cfg.last_output_dir = data["last_output_dir"]
                if "comfyui_url" in data:
                    cfg.comfyui_url = data["comfyui_url"]
                if "split_resample_defaults" in data and isinstance(
                        data["split_resample_defaults"], dict):
                    cfg.split_resample_defaults.update(
                        data["split_resample_defaults"])
                for key in ("runninghub_api_key", "runninghub_workflow_id",
                            "runninghub_base_url",
                            "runninghub_template_path", "video_output_dir"):
                    if key in data and isinstance(data[key], str):
                        setattr(cfg, key, data[key])
                for key in ("deeplx_url", "refine_base_url", "refine_api_key",
                            "refine_model", "refine_provider_preset", "refine_provider",
                            "refine_meta_prompt_path",
                            "current_translator",
                            "tencent_translator_secret_id",
                            "tencent_translator_secret_key",
                            "tencent_translator_region"):
                    if key in data and isinstance(data[key], str):
                        setattr(cfg, key, data[key])
                if "tencent_translator_project_id" in data:
                    try:
                        cfg.tencent_translator_project_id = int(
                            data["tencent_translator_project_id"] or 0)
                    except (TypeError, ValueError):
                        cfg.tencent_translator_project_id = 0
                for key in ("screenwriter_llm_api_key", "screenwriter_llm_base_url",
                            "screenwriter_project_root", "prompts_default_grid"):
                    if key in data and isinstance(data[key], str):
                        setattr(cfg, key, data[key])
                if isinstance(data.get("screenwriter_agent_port"), int):
                    cfg.screenwriter_agent_port = data["screenwriter_agent_port"]
                if "screenwriter_models" in data and isinstance(data["screenwriter_models"], dict):
                    cfg.screenwriter_models = data["screenwriter_models"]
                if "screenwriter_stage_assignments" in data and isinstance(
                        data["screenwriter_stage_assignments"], dict):
                    cfg.screenwriter_stage_assignments = data["screenwriter_stage_assignments"]
                if "screenwriter_projects" in data and isinstance(
                        data["screenwriter_projects"], list):
                    cfg.screenwriter_projects = [
                        str(x) for x in data["screenwriter_projects"]
                        if isinstance(x, str)
                    ]
                if "llm_providers" in data and isinstance(data["llm_providers"], dict):
                    cfg.llm_providers = data["llm_providers"]
                elif "screenwriter_providers" in data and isinstance(
                        data["screenwriter_providers"], dict):
                    # 旧字段迁移：保留兼容入口
                    cfg.llm_providers = data["screenwriter_providers"]
                if "video_timeline_cache" in data and isinstance(
                        data["video_timeline_cache"], dict):
                    cfg.video_timeline_cache = data["video_timeline_cache"]
                if "video_tasks" in data and isinstance(data["video_tasks"], list):
                    cfg.video_tasks = data["video_tasks"]
                if "soundtrack_tasks" in data and isinstance(data["soundtrack_tasks"], list):
                    cfg.soundtrack_tasks = data["soundtrack_tasks"]
                if "dub_tasks" in data and isinstance(data["dub_tasks"], list):
                    cfg.dub_tasks = data["dub_tasks"]
                if "dub_workflow_ids" in data and isinstance(data["dub_workflow_ids"], dict):
                    cfg.dub_workflow_ids = data["dub_workflow_ids"]
                if "dub_node_profiles" in data and isinstance(data["dub_node_profiles"], dict):
                    cfg.dub_node_profiles = data["dub_node_profiles"]
                if "dub_output_dir" in data and isinstance(data["dub_output_dir"], str):
                    cfg.dub_output_dir = data["dub_output_dir"]
                if "dub_sampling" in data and isinstance(data["dub_sampling"], dict):
                    cfg.dub_sampling = data["dub_sampling"]
                if "imggen_tasks" in data and isinstance(data["imggen_tasks"], list):
                    cfg.imggen_tasks = data["imggen_tasks"]
                if "imggen_provider" in data and isinstance(data["imggen_provider"], str):
                    cfg.imggen_provider = data["imggen_provider"]
                if "imggen_base_url" in data and isinstance(data["imggen_base_url"], str):
                    cfg.imggen_base_url = data["imggen_base_url"]
                if "imggen_model" in data and isinstance(data["imggen_model"], str):
                    cfg.imggen_model = data["imggen_model"]
                if "imggen_api_key" in data and isinstance(data["imggen_api_key"], str):
                    cfg.imggen_api_key = data["imggen_api_key"]
                if "imggen_output_dir" in data and isinstance(data["imggen_output_dir"], str):
                    cfg.imggen_output_dir = data["imggen_output_dir"]
                if "imggen_watermark" in data and isinstance(data["imggen_watermark"], bool):
                    cfg.imggen_watermark = data["imggen_watermark"]
                if isinstance(data.get("soundtrack_workflow_id"), str):
                    cfg.soundtrack_workflow_id = data["soundtrack_workflow_id"]
                if isinstance(data.get("soundtrack_output_dir"), str):
                    cfg.soundtrack_output_dir = data["soundtrack_output_dir"]
                if isinstance(data.get("soundtrack_seeds_count"), int):
                    cfg.soundtrack_seeds_count = data["soundtrack_seeds_count"]
                if isinstance(data.get("soundtrack_crossfade"), (int, float)):
                    cfg.soundtrack_crossfade = float(data["soundtrack_crossfade"])
                if isinstance(data.get("accent_big_threshold"), (int, float)):
                    cfg.accent_big_threshold = float(data["accent_big_threshold"])
                if isinstance(data.get("accent_snap_window"), (int, float)):
                    cfg.accent_snap_window = float(data["accent_snap_window"])
                if "workflow_ids" in data and isinstance(data["workflow_ids"], dict):
                    cfg.workflow_ids = data["workflow_ids"]
                if "last_active_function" in data and isinstance(
                        data["last_active_function"], str):
                    cfg.last_active_function = data["last_active_function"]
                # Sprint 0 新字段（与现有 settings.json 字段读取同位置追加）
                for fld, caster in [
                    ("refine_frames_per_shot", int),
                    ("refine_max_segments", int),
                    ("accent_max_stretch", float),
                    ("soundtrack_max_concurrency", int),
                ]:
                    if fld in data:
                        try:
                            setattr(cfg, fld, caster(data[fld]))
                        except (TypeError, ValueError):
                            pass
                if "refine_merge_threshold" in data:
                    try:
                        cfg.refine_merge_threshold = float(data["refine_merge_threshold"])
                    except (TypeError, ValueError):
                        pass
                if "soundtrack_score_weights" in data and isinstance(data["soundtrack_score_weights"], dict):
                    cfg.soundtrack_score_weights = dict(data["soundtrack_score_weights"])
                if "soundtrack_fade_out" in data:
                    cfg.soundtrack_fade_out = bool(data["soundtrack_fade_out"])
                for fld, caster in [
                    ("sfx_workflow_id", str),
                    ("sfx_plan_frames_per_shot", int),
                    ("sfx_max_concurrency", int),
                    ("sfx_default_volume", float),
                    ("sfx_ducking_db", float),
                    ("sfx_seeds_count", int),
                ]:
                    if fld in data:
                        try:
                            setattr(cfg, fld, caster(data[fld]))
                        except (TypeError, ValueError):
                            pass
                if "task_bar_collapsed" in data and isinstance(
                        data["task_bar_collapsed"], dict):
                    cfg.task_bar_collapsed = dict(data["task_bar_collapsed"])
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    if not cfg.video_tasks and cfg.video_timeline_cache:
        cfg.video_tasks = [{
            "id": _gen_task_id(),
            "name": "默认任务",
            "timeline": cfg.video_timeline_cache,
            "updated_at": time.time(),
            "last_result": "",
        }]

    if not cfg.workflow_ids and cfg.runninghub_workflow_id:
        cfg.workflow_ids = {"director": cfg.runninghub_workflow_id}

    if cfg.deeplx_url:
        os.environ["DEEPLX_URL"] = cfg.deeplx_url
    if cfg.current_translator:
        os.environ["_CURRENT_TRANSLATOR"] = cfg.current_translator
    if cfg.tencent_translator_secret_id:
        os.environ["TENCENTCLOUD_SECRET_ID"] = cfg.tencent_translator_secret_id
    if cfg.tencent_translator_secret_key:
        os.environ["TENCENTCLOUD_SECRET_KEY"] = cfg.tencent_translator_secret_key
    if cfg.tencent_translator_region:
        os.environ["TENCENTCLOUD_REGION"] = cfg.tencent_translator_region
    _post_load_migrate(cfg)
    return cfg


def _post_load_migrate(cfg) -> None:
    """旧用户升级兼容：若只配过 DeepLX 没配腾讯，沿用 DeepLX。"""
    if not cfg.current_translator:
        if cfg.deeplx_url and not cfg.tencent_translator_secret_id:
            cfg.current_translator = "deeplx"
        else:
            cfg.current_translator = "tencent"
