"""配乐 agent 命令行入口。

run   : 新建会话并推进（接线 shot_detector 等留后续 Plan）
resume: 从已存 session.json 续跑
"""
from __future__ import annotations

import argparse

from sound_track_agent.pipeline import STAGE_ORDER


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sound_track_agent",
        description="漫剧成片后期配乐 agent")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="对成片 MP4 新建配乐会话并推进")
    pr.add_argument("mp4", help="成片 MP4 路径")
    pr.add_argument("--style", required=True, help="全剧总风格描述")
    pr.add_argument("--work-dir", default="sound_track_out",
                    help="工作目录（会话与产物落盘处）")
    pr.add_argument("--stop-after", choices=STAGE_ORDER, default="mix",
                    help="推进到该阶段后停止（半自动确认点）")

    ps = sub.add_parser("resume", help="从已存 session.json 续跑")
    ps.add_argument("session", help="session.json 路径")
    ps.add_argument("--stop-after", choices=STAGE_ORDER, default="mix")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"[sound_track_agent] command={args.command} "
          f"stop_after={args.stop_after}")
    if args.command == "run":
        print(f"  mp4={args.mp4} style={args.style!r} work_dir={args.work_dir}")
    else:
        print(f"  session={args.session}")
    print("  （管线接线见 Plan 2-4，当前为骨架）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
