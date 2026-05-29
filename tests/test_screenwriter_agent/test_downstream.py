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
    purge_downstream(tmp_path, stage="script_outline")
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
    purge_downstream(tmp_path, stage="script_outline")
    purge_downstream(tmp_path, stage="ideate")


# ---------------------------------------------------------------------------
# v2 集感知测试
# ---------------------------------------------------------------------------
import json  # noqa: E402


def _setup_multi_ep(tmp_path):
    (tmp_path / "创意.json").write_text("{}", encoding="utf-8")
    (tmp_path / "剧本.json").write_text(json.dumps({
        "episode_count": 3,
        "episodes": [{"id": f"E{i}", "title": "t", "summary": "s"}
                      for i in (1, 2, 3)],
    }), encoding="utf-8")
    for i in (1, 2, 3):
        (tmp_path / f"剧本_E{i}.md").write_text("md", encoding="utf-8")
        (tmp_path / f"分镜_E{i}.json").write_text("{}", encoding="utf-8")
        ep_dir = tmp_path / "prompts" / f"E{i}" / "角色参考图"
        ep_dir.mkdir(parents=True)
        (ep_dir / "x.md").write_text("x", encoding="utf-8")


def test_purge_script_outline_clears_everything_below(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="script_outline")
    assert (tmp_path / "创意.json").is_file()
    assert not (tmp_path / "剧本.json").exists()
    for i in (1, 2, 3):
        assert not (tmp_path / f"剧本_E{i}.md").exists()
        assert not (tmp_path / f"分镜_E{i}.json").exists()
    assert not (tmp_path / "prompts").exists()


def test_purge_script_episode_only_clears_single_episode_below(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="script_episode", episode_id="E2")
    assert (tmp_path / "剧本.json").is_file()
    assert (tmp_path / "剧本_E1.md").is_file()
    assert not (tmp_path / "剧本_E2.md").exists()
    assert (tmp_path / "剧本_E3.md").is_file()
    assert (tmp_path / "分镜_E1.json").is_file()
    assert not (tmp_path / "分镜_E2.json").exists()
    assert (tmp_path / "prompts" / "E1").is_dir()
    assert not (tmp_path / "prompts" / "E2").exists()


def test_purge_storyboard_with_episode_id(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="storyboard", episode_id="E2")
    assert (tmp_path / "剧本_E2.md").is_file()
    assert not (tmp_path / "分镜_E2.json").exists()
    assert not (tmp_path / "prompts" / "E2").exists()


def test_purge_prompts_with_episode_id(tmp_path):
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="prompts", episode_id="E2")
    assert (tmp_path / "分镜_E2.json").is_file()
    assert not (tmp_path / "prompts" / "E2").exists()


def test_purge_storyboard_no_episode_id_clears_all(tmp_path):
    """不传 episode_id 时清所有集（向后兼容 v1 单文件路径）。"""
    _setup_multi_ep(tmp_path)
    purge_downstream(tmp_path, stage="storyboard")
    for i in (1, 2, 3):
        assert not (tmp_path / f"分镜_E{i}.json").exists()
    # 兼容旧名也清
    legacy_sb = tmp_path / "分镜.json"
    assert not legacy_sb.exists()
