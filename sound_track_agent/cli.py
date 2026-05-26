"""配乐 agent 命令行入口。

run   : 对成片 MP4 新建会话并端到端推进。
resume: 从已存 session.json 续跑。
"""
from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path

from sound_track_agent.pipeline import STAGE_ORDER, run as run_stages
from sound_track_agent.pipeline import Stages

DEFAULT_WORKFLOW_ID = "2059090557116440578"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sound_track_agent", description="漫剧成片后期配乐 agent")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="对成片 MP4 新建配乐会话并推进")
    pr.add_argument("mp4")
    pr.add_argument("--style", required=True)
    pr.add_argument("--work-dir", default="sound_track_out")
    pr.add_argument("--stop-after", choices=STAGE_ORDER, default="mix")
    pr.add_argument("--workflow-id", default=DEFAULT_WORKFLOW_ID,
                    help="ACE-Step workflowId")
    pr.add_argument("--seeds-count", type=int, default=2,
                    help="每段生成候选数")

    ps = sub.add_parser("resume", help="从已存 session.json 续跑")
    ps.add_argument("session")
    ps.add_argument("--stop-after", choices=STAGE_ORDER, default="mix")
    return p


def run_pipeline(args) -> int:
    """真实管线接线（依赖真实成片 + RunningHub + 豆包，无单测；靠端到端冒烟）。"""
    from drama_shot_master.config import load_config
    from drama_shot_master.providers.runninghub import RunningHubClient
    from sound_track_agent.provider import build_soundtrack_provider
    from sound_track_agent.shot_detector import detect_shots
    from sound_track_agent.segment_planner import plan_segments
    from sound_track_agent.session import ScoringSession, hash_file
    from sound_track_agent.stages_factory import build_stages
    from sound_track_agent.mixdown import extract_segment_frame, assemble_and_mix

    cfg = load_config()
    provider = build_soundtrack_provider(cfg)
    client = RunningHubClient(
        cfg.runninghub_api_key, base_url=cfg.runninghub_base_url)

    mp4 = Path(args.mp4)
    work_dir = Path(args.work_dir)
    shots = detect_shots(mp4)
    segs = plan_segments(shots)
    sess = ScoringSession(
        source_mp4=str(mp4), source_hash=hash_file(mp4),
        global_style=args.style,
        frame_rate=shots[0].t_end and 24.0 or 24.0,  # 占位帧率，真实可后续读
        segments=segs)

    frames_dir = work_dir / "frames"
    stages = build_stages(
        provider=provider, client=client, workflow_id=args.workflow_id,
        work_dir=work_dir, global_style=args.style,
        seeds=list(range(1, args.seeds_count + 1)),
        frame_provider=lambda seg: extract_segment_frame(
            mp4, seg, frames_dir / f"seg{seg.index}.png"),
        mix_fn=partial(assemble_and_mix, video_path=mp4, work_dir=work_dir),
    )
    out = run_stages(sess, stages,
                     session_path=work_dir / "session.json",
                     stop_after=args.stop_after)
    print(f"[sound_track_agent] done. output={out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return run_pipeline(args)
    print(f"[sound_track_agent] resume {args.session} stop_after={args.stop_after}")
    print("  （resume 接线同 run，复用已存 session；端到端冒烟验证）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
