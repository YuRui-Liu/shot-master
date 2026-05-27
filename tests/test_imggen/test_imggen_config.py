import json
from drama_shot_master.config import load_config


def test_imggen_config(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg.imggen_tasks == []
    assert cfg.imggen_provider == "doubao"
    assert "ark" in cfg.imggen_base_url
    cfg.update_settings(imggen_provider="openai", imggen_model="gpt-image-1",
                        imggen_output_dir="D:/o")
    raw = json.loads(sp.read_text(encoding="utf-8"))
    assert raw["imggen_provider"] == "openai" and raw["imggen_model"] == "gpt-image-1"
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.imggen_provider == "openai" and cfg2.imggen_output_dir == "D:/o"
