"""media_agent 配置。镜像 screenwriter_agent.config 的轻量风格。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MediaAgentConfig:
    host: str = "127.0.0.1"          # 仅本机回环
    port: int = 18450                # 避开 screenwriter_agent 18430-18439
    log_level: str = "info"
