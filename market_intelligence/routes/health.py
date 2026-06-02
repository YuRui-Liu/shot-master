"""GET /health。返回 status + version + pid。镜像 screenwriter_agent。"""
import os

from fastapi import APIRouter

from market_intelligence import __version__

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "pid": os.getpid(),
        "nonce": os.environ.get("MARKET_INTEL_AGENT_NONCE", ""),
    }
