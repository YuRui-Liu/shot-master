"""Load configuration from .env and settings.json.

.env: 静态配置（API keys、默认值）；本进程启动时只读
settings.json: 运行时偏好（当前 provider / model / 默认输出策略）；可被 UI 改写
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values


# OpenAI 兼容 endpoints 的 key 名（在 .env 里以 {NAME}_API_KEY / {NAME}_BASE_URL 形式存在）
OPENAI_COMPAT_ENDPOINTS = [
    "openai", "deepseek", "doubao", "openrouter", "siliconflow", "vllm"
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
    last_active_function: str = "inference"      # 上次退出时活跃的 panel

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
                "last_active_function": self.last_active_function,
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
                if "video_timeline_cache" in data and isinstance(
                        data["video_timeline_cache"], dict):
                    cfg.video_timeline_cache = data["video_timeline_cache"]
                if "last_active_function" in data and isinstance(
                        data["last_active_function"], str):
                    cfg.last_active_function = data["last_active_function"]
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    return cfg
