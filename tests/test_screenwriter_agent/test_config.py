from screenwriter_agent.config import AgentConfig


def test_default_port_in_valid_range():
    cfg = AgentConfig()
    assert 18430 <= cfg.port < 18500


def test_from_args_overrides_port():
    cfg = AgentConfig.from_args(["--port", "18444"])
    assert cfg.port == 18444


def test_default_models_present():
    cfg = AgentConfig()
    assert set(cfg.default_models.keys()) == {"ideate", "script", "storyboard", "prompts"}
