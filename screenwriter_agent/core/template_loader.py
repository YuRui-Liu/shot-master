"""模板加载 — 向后兼容 shim。

实际实现已迁移至 screenwriter_agent.templates.template_loader。
本模块保留全部公开名称的 re-export，供旧 caller 无感升级。
"""
from __future__ import annotations

from screenwriter_agent.templates.template_loader import (  # noqa: F401
    BUILTIN_IDS,
    GLOBAL_TEMPLATE_DIR,
    _BUILTIN_DIR,
    global_template_path,
    write_global_template,
    load_template,
)

__all__ = [
    "BUILTIN_IDS",
    "GLOBAL_TEMPLATE_DIR",
    "_BUILTIN_DIR",
    "global_template_path",
    "write_global_template",
    "load_template",
]
