"""GET /health。返回 status + version + default_models。"""
from fastapi import APIRouter, Request

from screenwriter_agent import __version__

router = APIRouter()


@router.get("/health")
def health(request: Request):
    cfg = request.app.state.cfg
    return {
        "status": "ok",
        "version": __version__,
        "default_models": cfg.default_models,
    }
