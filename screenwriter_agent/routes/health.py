"""GET /health（占位；Task 10 实际实现）。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
