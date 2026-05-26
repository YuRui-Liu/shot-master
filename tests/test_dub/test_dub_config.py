import json
from drama_shot_master.config import load_config


def test_dub_fields_default_and_persist(tmp_path):
    sp = tmp_path / "settings.json"
    cfg = load_config(env_path=tmp_path / ".env", settings_path=sp)
    # 默认值
    assert cfg.dub_tasks == []
    assert isinstance(cfg.dub_workflow_ids, dict)
    assert isinstance(cfg.dub_sampling, dict)
    # 写入后能从磁盘读回
    cfg.update_settings(dub_tasks=[{"id": "1", "name": "A", "mode": "clone",
                                    "payload": {}, "updated_at": 0, "last_result": ""}],
                        dub_output_dir="D:/out")
    raw = json.loads(sp.read_text(encoding="utf-8"))
    assert raw["dub_tasks"][0]["name"] == "A"
    assert raw["dub_output_dir"] == "D:/out"
    cfg2 = load_config(env_path=tmp_path / ".env", settings_path=sp)
    assert cfg2.dub_tasks[0]["name"] == "A"
    assert cfg2.dub_output_dir == "D:/out"
