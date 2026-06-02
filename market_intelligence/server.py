"""FastAPI app + uvicorn 启动入口。镜像 screenwriter_agent.server。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import MarketIntelligenceConfig

_AGENT_DIR = Path(__file__).resolve().parent


def _resolve_db_path(cfg: MarketIntelligenceConfig) -> Path:
    """解析数据库路径：优先 cfg.db_path，否则 agent 目录下的 db/。"""
    if cfg.db_path:
        return Path(cfg.db_path)
    return _AGENT_DIR.parent / "db" / "market_intel.db"


def _build_analyzer(cfg: MarketIntelligenceConfig):
    """从配置构造 MarketAnalyzer。

    优先从 cfg.app_cfg.llm_providers 取 api_key/base_url；
    否则回退到 cfg.llm 里可能存的环境变量。
    """
    provider = cfg.llm.get("provider", "deepseek")
    model = cfg.llm.get("model", "deepseek-v4-flash")
    temperature = cfg.llm.get("temperature", 0.3)
    max_tokens = cfg.llm.get("max_tokens", 4096)

    api_key = ""
    base_url = ""

    # 尝试从主软件 cfg 的 llm_providers 取
    app_cfg = getattr(cfg, "app_cfg", None)
    if app_cfg and hasattr(app_cfg, "llm_providers"):
        providers = getattr(app_cfg, "llm_providers", {}) or {}
        pconf = providers.get(provider, {})
        api_key = pconf.get("api_key", "")
        base_url = pconf.get("base_url", "")

    # 回退：从 cfg.llm 直接取（如果配了）
    if not api_key:
        api_key = cfg.llm.get("api_key", "")
    if not base_url:
        base_url = cfg.llm.get("base_url", "")

    if not api_key or not base_url:
        logging.getLogger(__name__).warning(
            "LLM credentials missing for provider=%s; analyzer disabled.", provider)
        return None

    from .analyzer import MarketAnalyzer
    return MarketAnalyzer(
        api_key=api_key, base_url=base_url, model=model,
        temperature=temperature, max_tokens=max_tokens,
    )


def create_app(cfg: MarketIntelligenceConfig | None = None) -> FastAPI:
    """构造 FastAPI app。"""
    cfg = cfg or MarketIntelligenceConfig()
    app = FastAPI(title="market_intelligence", version="0.1.0")
    app.state.cfg = cfg

    # CORS：镜像 screenwriter_agent
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null"],
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 数据库（线程安全 WAL + check_same_thread=False）
    from .database import MarketDB
    db_path = _resolve_db_path(cfg)
    app.state.db = MarketDB(db_path)
    logging.getLogger(__name__).info("MarketDB at %s", db_path)

    # 分析器（LLM 可用则构造，否则置 None；爬取/查询仍可工作）
    app.state.analyzer = _build_analyzer(cfg)

    from .routes.health import router as health_router
    app.include_router(health_router)

    from .routes.crawl import router as crawl_router
    app.include_router(crawl_router)

    from .routes.analysis import router as analysis_router
    app.include_router(analysis_router)

    return app


def run(cfg: MarketIntelligenceConfig | None = None) -> None:
    """启动 uvicorn。端口被占用时往后试到 18469。"""
    import uvicorn
    cfg = cfg or MarketIntelligenceConfig()
    logging.basicConfig(level=cfg.log_level.upper())
    for offset in range(10):
        port = cfg.port + offset
        try:
            cfg.port = port
            uvicorn.run(create_app(cfg), host=cfg.host, port=port,
                        log_level=cfg.log_level)
            return
        except OSError as e:
            if "address already in use" not in str(e).lower():
                raise
    raise RuntimeError(f"端口 {cfg.port}+1..+9 都被占用")


if __name__ == "__main__":
    run()
