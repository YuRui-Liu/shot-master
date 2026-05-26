from sound_track_agent.cli import build_parser


def test_run_subcommand_parses():
    p = build_parser()
    ns = p.parse_args(["run", "ep1.mp4", "--style", "冷色调末日",
                       "--work-dir", "out", "--stop-after", "generate"])
    assert ns.command == "run"
    assert ns.mp4 == "ep1.mp4"
    assert ns.style == "冷色调末日"
    assert ns.work_dir == "out"
    assert ns.stop_after == "generate"


def test_resume_subcommand_parses():
    p = build_parser()
    ns = p.parse_args(["resume", "out/h1/session.json", "--stop-after", "mix"])
    assert ns.command == "resume"
    assert ns.session == "out/h1/session.json"
    assert ns.stop_after == "mix"


def test_run_stop_after_defaults_to_mix():
    p = build_parser()
    ns = p.parse_args(["run", "ep1.mp4", "--style", "x"])
    assert ns.stop_after == "mix"


def test_run_parse_includes_workflow_and_seeds():
    p = build_parser()
    ns = p.parse_args(["run", "ep.mp4", "--style", "x"])
    assert ns.workflow_id == "2059090557116440578"   # 默认 ACE-Step workflowId
    assert ns.seeds_count == 2
    ns2 = p.parse_args(["run", "ep.mp4", "--style", "x",
                        "--workflow-id", "wf-custom", "--seeds-count", "3"])
    assert ns2.workflow_id == "wf-custom"
    assert ns2.seeds_count == 3
