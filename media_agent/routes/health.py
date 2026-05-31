"""GET /health。镜像 screenwriter_agent：status+version+pid+nonce。"""
import os

from fastapi import APIRouter

from media_agent import __version__

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "pid": os.getpid(),
        # nonce：壳 spawn 时经 env 注入，识别"是不是本次 spawn 的 agent"
        "nonce": os.environ.get("MEDIA_AGENT_NONCE", ""),
    }
