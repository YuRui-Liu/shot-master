def test_lifecycle_module_importable():
    from drama_shot_master.agents.screenwriter_lifecycle import ScreenwriterLifecycle
    lc = ScreenwriterLifecycle()
    assert hasattr(lc, "spawn") and hasattr(lc, "terminate") and hasattr(lc, "port")
