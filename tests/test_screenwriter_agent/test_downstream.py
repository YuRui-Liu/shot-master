"""purge_downstream 删除链路测试。"""
from screenwriter_agent.core.downstream import purge_downstream


def _setup_full(tmp_path):
    """造一个 4 阶段全产物的项目目录。"""
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本.md").write_text("x", encoding="utf-8")
    (tmp_path / "分镜.json").write_text("{}", encoding="utf-8")
    (tmp_path / "prompts" / "角色参考图").mkdir(parents=True)
    (tmp_path / "prompts" / "角色参考图" / "x.md").write_text("y", encoding="utf-8")


def test_purge_script_clears_script_and_below(tmp_path):
    _setup_full(tmp_path)
    purge_downstream(tmp_path, stage="script")
    assert (tmp_path / "创意.json").is_file()       # 上游保留
    assert not (tmp_path / "剧本.md").exists()       # 本阶段清
    assert not (tmp_path / "分镜.json").exists()     # 下游清
    assert not (tmp_path / "prompts").exists()       # 下游清


def test_purge_storyboard_keeps_script(tmp_path):
    _setup_full(tmp_path)
    purge_downstream(tmp_path, stage="storyboard")
    assert (tmp_path / "创意.json").is_file()
    assert (tmp_path / "剧本.md").is_file()
    assert not (tmp_path / "分镜.json").exists()
    assert not (tmp_path / "prompts").exists()


def test_purge_prompts_only_clears_prompts_dir(tmp_path):
    _setup_full(tmp_path)
    purge_downstream(tmp_path, stage="prompts")
    assert (tmp_path / "剧本.md").is_file()
    assert (tmp_path / "分镜.json").is_file()
    assert not (tmp_path / "prompts").exists()


def test_purge_ideate_clears_everything(tmp_path):
    _setup_full(tmp_path)
    purge_downstream(tmp_path, stage="ideate")
    assert not (tmp_path / "创意.json").exists()
    assert not (tmp_path / "剧本.md").exists()
    assert not (tmp_path / "分镜.json").exists()
    assert not (tmp_path / "prompts").exists()


def test_purge_safe_on_missing_files(tmp_path):
    # 空目录 + 不抛
    purge_downstream(tmp_path, stage="script")
    purge_downstream(tmp_path, stage="ideate")
