"""media_agent FastAPI app + uvicorn 入口。镜像 screenwriter_agent.server。"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import MediaAgentConfig


def create_app(cfg: MediaAgentConfig | None = None) -> FastAPI:
    cfg = cfg or MediaAgentConfig()
    app = FastAPI(title="media_agent", version="0.1.0")
    app.state.cfg = cfg

    from .routes.health import router as health_router
    app.include_router(health_router)

    from .routes.imaging import router as imaging_router
    app.include_router(imaging_router)

    from .routes.transition import router as transition_router
    app.include_router(transition_router)

    from .routes.imggen import router as imggen_router
    app.include_router(imggen_router)

    from .routes.soundtrack import router as soundtrack_router
    app.include_router(soundtrack_router)

    return app


def run(cfg: MediaAgentConfig | None = None) -> None:
    """启动 uvicorn。端口被占用时往后试 9 个。"""
    import uvicorn
    cfg = cfg or MediaAgentConfig()
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
