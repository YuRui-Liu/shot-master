"""导出 media_agent 的 OpenAPI 契约到 docs/explorer/media_agent_openapi.json。

作为前端契约源。用法：python -m media_agent.export_openapi
"""
from __future__ import annotations

import json
from pathlib import Path

from .server import create_app

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUT_PATH = _REPO_ROOT / "docs" / "explorer" / "media_agent_openapi.json"


def export(out_path: Path | None = None) -> Path:
    out_path = out_path or _OUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    out_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


if __name__ == "__main__":
    path = export()
    print(f"OpenAPI 已写入 {path}")
