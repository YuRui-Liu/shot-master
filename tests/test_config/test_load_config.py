def test_sfx_fields_have_defaults():
    from drama_shot_master.config import Config
    cfg = Config()
    assert cfg.sfx_workflow_id == "2060218796413112321"
    assert cfg.sfx_plan_frames_per_shot == 3
    assert cfg.sfx_max_concurrency == 3
    assert abs(cfg.sfx_default_volume - 0.8) < 1e-6
    assert abs(cfg.sfx_ducking_db - (-6.0)) < 1e-6
    assert cfg.sfx_seeds_count == 1


def test_sfx_fields_update_settings_roundtrip(tmp_path):
    """改 6 字段 → 写盘 → reload → 值保留。"""
    import json
    from drama_shot_master.config import Config, load_config
    cfg = Config()
    cfg.settings_path = tmp_path / "settings.json"
    cfg.update_settings(
        sfx_workflow_id="wf-new",
        sfx_plan_frames_per_shot=5,
        sfx_max_concurrency=6,
        sfx_default_volume=1.1,
        sfx_ducking_db=-9.0,
        sfx_seeds_count=2,
    )
    data = json.loads(cfg.settings_path.read_text(encoding="utf-8"))
    assert data["sfx_workflow_id"] == "wf-new"
    assert data["sfx_plan_frames_per_shot"] == 5
    cfg2 = load_config(env_path=tmp_path / ".env.nonexistent", settings_path=cfg.settings_path)
    assert cfg2.sfx_workflow_id == "wf-new"
    assert cfg2.sfx_plan_frames_per_shot == 5
    assert cfg2.sfx_max_concurrency == 6
    assert abs(cfg2.sfx_default_volume - 1.1) < 1e-6
    assert abs(cfg2.sfx_ducking_db - (-9.0)) < 1e-6
    assert cfg2.sfx_seeds_count == 2


def test_task_bar_collapsed_default():
    from drama_shot_master.config import Config
    cfg = Config()
    assert cfg.task_bar_collapsed == {}


def test_task_bar_collapsed_update_settings_roundtrip(tmp_path):
    import json
    from drama_shot_master.config import Config, load_config
    cfg = Config()
    cfg.settings_path = tmp_path / "settings.json"
    cfg.update_settings(task_bar_collapsed={"screenwriter": True, "imggen": False})
    data = json.loads(cfg.settings_path.read_text(encoding="utf-8"))
    assert data["task_bar_collapsed"] == {"screenwriter": True, "imggen": False}
    cfg2 = load_config(env_path=tmp_path / ".env.nonexistent",
                       settings_path=cfg.settings_path)
    assert cfg2.task_bar_collapsed == {"screenwriter": True, "imggen": False}
