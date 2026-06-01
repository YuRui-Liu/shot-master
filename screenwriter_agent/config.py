"""运行时配置（命令行参数 + 环境变量 + 默认值）。"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field

# 默认每阶段模型（spec 3.1）
_DEFAULT_MODELS = {
    "ideate":     "doubao-1-5-thinking-pro-250415",
    "script":     "doubao-1-5-thinking-pro-250415",
    "storyboard": "deepseek-v4-pro",
    "prompts":    "deepseek-v4-flash",
}


@dataclass
class AgentConfig:
    """Agent 运行配置。"""
    host: str = "127.0.0.1"
    port: int = 18430
    log_level: str = "info"
    default_models: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_MODELS))
    # 换立意时归档（而非删除）旧下游产物；关则回退旧 purge 行为（不建议）。
    idea_switch_archive_enabled: bool = True
    # 是否把 imggen/video/soundtrack 大产物也纳入归档（默认否，避免搬运大文件）。
    idea_archive_include_media: bool = False

    @classmethod
    def from_args(cls, argv: list[str]) -> "AgentConfig":
        p = argparse.ArgumentParser(prog="screenwriter_agent")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=18430)
        p.add_argument("--log-level", default="info",
                       choices=["debug", "info", "warning", "error"])
        ns = p.parse_args(argv)
        return cls(host=ns.host, port=ns.port, log_level=ns.log_level)
