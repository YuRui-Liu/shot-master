"""FastAPI app + uvicorn 启动入口。"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import AgentConfig


def create_app(cfg: AgentConfig | None = None) -> FastAPI:
    """构造 FastAPI app；路由由各 router 模块挂载。
    cfg 在路由 handler 内通过 dependency injection 取（暂用 module-level 闭包）。"""
    cfg = cfg or AgentConfig()
    app = FastAPI(title="screenwriter_agent", version="0.1.0")
    app.state.cfg = cfg

    # CORS：放行本地来源，使 /ui 同源页（media_agent 18450，Origin: 127.0.0.1:*）
    # 与 file:// 页（Origin: null）跨端口 fetch 本 agent 的 SSE，
    # 不再依赖浏览器 --disable-web-security。镜像 media_agent.server。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null"],
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .routes.health import router as health_router
    app.include_router(health_router)

    from .routes.project import router as project_router
    app.include_router(project_router)

    from .routes.ideate import router as ideate_router
    app.include_router(ideate_router)

    from .routes.script_outline import router as script_outline_router
    app.include_router(script_outline_router)

    from .routes.script_episode import router as script_episode_router
    app.include_router(script_episode_router)

    from .routes.storyboard import router as storyboard_router
    app.include_router(storyboard_router)

    from .routes.prompts import router as prompts_router
    app.include_router(prompts_router)

    from .routes.video_prompt import router as video_prompt_router
    app.include_router(video_prompt_router)

    from .routes.audio_prompt import router as audio_prompt_router
    app.include_router(audio_prompt_router)

    return app


def run(cfg: AgentConfig) -> None:
    """启动 uvicorn。端口被占用时往后试到 18439。"""
    import uvicorn
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
