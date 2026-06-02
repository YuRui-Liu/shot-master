"""运行时配置（命令行参数 + 默认值）。镜像 screenwriter_agent.config。"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path


# 爬取平台定义
_DEFAULT_PLATFORMS = [
    {"id": "hongguo", "name": "红果短剧", "url": "https://www.hongguoduanju.com/rank"},
]

# 默认 LLM 配置：复用 screenwriter 的方式 —— 从 cfg.llm_providers 取对应 provider 的
# api_key/base_url。此处仅存 provider 引用 + 默认 model，实际 key/url 由 analyzer 运行时从
# drama_shot_master.config.Config.llm_providers 解析。
_DEFAULT_LLM = {
    "provider": "deepseek",           # 对应 llm_providers 的 key
    "model": "deepseek-v4-flash",     # 默认模型（分析用，非思考）
    "temperature": 0.3,               # 分析任务低温度，结果更稳定
    "max_tokens": 4096,
}


@dataclass
class MarketIntelligenceConfig:
    """Market Intelligence Agent 运行配置。"""
    host: str = "127.0.0.1"
    port: int = 18460
    log_level: str = "info"

    # 爬取平台列表
    platforms: list[dict] = field(default_factory=lambda: list(_DEFAULT_PLATFORMS))

    # LLM 配置（用于分析任务）
    llm: dict = field(default_factory=lambda: dict(_DEFAULT_LLM))

    # 自动爬取开关
    auto_crawl: bool = False

    # 分析间隔（小时），auto_crawl 为 True 时生效
    analyze_interval_hours: int = 24

    # 数据库文件路径（相对于 agent 工作目录，默认 project_root/db/market_intel.db）
    db_path: str = ""

    # 主软件 cfg 引用（包含 llm_providers 等运行时配置），启动时由 server.run 注入。
    # 类型为 drama_shot_master.config.Config，但为避免循环导入这里不标注具体类型。
    app_cfg: object = None

    @classmethod
    def from_args(cls, argv: list[str]) -> "MarketIntelligenceConfig":
        p = argparse.ArgumentParser(prog="market_intelligence")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=18460)
        p.add_argument("--log-level", default="info",
                       choices=["debug", "info", "warning", "error"])
        p.add_argument("--db-path", default="")
        p.add_argument("--auto-crawl", action="store_true", default=False)
        ns = p.parse_args(argv)
        return cls(host=ns.host, port=ns.port, log_level=ns.log_level,
                   db_path=ns.db_path, auto_crawl=ns.auto_crawl)
