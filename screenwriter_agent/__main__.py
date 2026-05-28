"""python -m screenwriter_agent 入口。"""
from __future__ import annotations

import sys

from .config import AgentConfig
from .server import run


def main(argv: list[str] | None = None) -> int:
    cfg = AgentConfig.from_args(argv if argv is not None else sys.argv[1:])
    run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
