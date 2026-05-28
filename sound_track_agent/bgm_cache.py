"""BGM 生成结果缓存：内容寻址，按 work_dir 作用域。纯逻辑 + 薄文件 IO，可单测。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def cache_key(workflow_id: str, tags: str, bpm: int,
              duration: float, seed: int) -> str:
    """对决定输出的输入算 sha256 前 16 hex。duration 定精度避免浮点 repr 漂移。"""
    raw = f"{workflow_id}|{tags}|{int(bpm)}|{float(duration):.3f}|{int(seed)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_path(cache_dir, key: str) -> Path:
    return Path(cache_dir) / f"{key}.mp3"


def lookup(cache_dir, key: str):
    """命中返回缓存路径，未命中返回 None。"""
    p = cache_path(cache_dir, key)
    return p if p.exists() else None


def store(cache_dir, key: str, src) -> Path:
    """把 src 移入缓存（同盘 rename，原子），返回缓存路径。"""
    dest = cache_path(cache_dir, key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Path(src).replace(dest)
    return dest
