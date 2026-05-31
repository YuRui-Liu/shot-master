"""R1-T1 · ProjectManifest 单测（纯逻辑，无 Qt）。

覆盖：
- load/save round-trip（落盘再读回，字段一致）
- from_dict 缺 status/params/pipeline → 默认值迁移
- pipeline state 读写（stage_state / set_stage）
- episodes['E1'].shots_done 增量幂等（重复 add 同 shot 不重复）
- 坏 JSON → 默认不崩
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.core.compass.manifest import (
    EpisodeProgress,
    ProjectManifest,
    StageState,
    load_manifest,
    save_manifest,
)


# ---- 基本构造 / 默认值 -------------------------------------------------

def test_from_dict_empty_uses_defaults():
    """空 dict → 全部走默认值，不抛异常。"""
    m = ProjectManifest.from_dict({})
    assert m.schema_version == 1
    assert m.project_id == ""
    assert m.project_name == ""
    assert m.genre == ""
    assert m.params == {}
    assert isinstance(m.style_bible, dict)
    assert m.status == "scripted"
    # 四阶段 pipeline 默认全 pending
    assert set(m.pipeline.keys()) == {
        "screenwriter", "assets", "storyboard", "production",
    }
    for st in m.pipeline.values():
        assert st.state == "pending"
    assert m.artifacts == {}
    assert m.episodes == {}
    assert m.dependencies == {}
    assert m.archive == []


def test_from_dict_missing_status_params_pipeline_migrates():
    """缺 status/params/pipeline 字段 → 默认值迁移。"""
    m = ProjectManifest.from_dict({
        "project_id": "P-006",
        "project_name": "替嫁新娘的逆袭",
        "genre": "短剧",
    })
    assert m.project_id == "P-006"
    assert m.project_name == "替嫁新娘的逆袭"
    assert m.genre == "短剧"
    # 缺失的三组走默认
    assert m.status == "scripted"
    assert m.params == {}
    assert m.stage_state("screenwriter") == "pending"
    assert m.stage_state("production") == "pending"


# ---- pipeline state 读写 ----------------------------------------------

def test_stage_state_read_write():
    m = ProjectManifest.from_dict({})
    assert m.stage_state("screenwriter") == "pending"
    m.set_stage("screenwriter", "completed", next_action="进入 ① 素材准备")
    assert m.stage_state("screenwriter") == "completed"
    assert m.pipeline["screenwriter"].next_action == "进入 ① 素材准备"
    # 改另一个阶段不影响已设阶段
    m.set_stage("assets", "in_progress")
    assert m.stage_state("assets") == "in_progress"
    assert m.stage_state("screenwriter") == "completed"


def test_stage_state_unknown_stage_returns_pending():
    """未知阶段名读取 → pending，不抛。"""
    m = ProjectManifest.from_dict({})
    assert m.stage_state("不存在的阶段") == "pending"


def test_set_stage_unknown_stage_creates_entry():
    m = ProjectManifest.from_dict({})
    m.set_stage("custom_stage", "in_progress")
    assert m.stage_state("custom_stage") == "in_progress"


# ---- episodes 进度：shots_done 幂等 ------------------------------------

def test_mark_shot_done_increments_and_idempotent():
    m = ProjectManifest.from_dict({})
    m.mark_shot_done("E1", "S001")
    m.mark_shot_done("E1", "S002")
    assert m.episodes["E1"].shots_done == ["S001", "S002"]
    # 重复 add 同 shot 不重复
    m.mark_shot_done("E1", "S001")
    assert m.episodes["E1"].shots_done == ["S001", "S002"]


def test_mark_shot_done_creates_episode_on_demand():
    m = ProjectManifest.from_dict({})
    assert "E2" not in m.episodes
    m.mark_shot_done("E2", "S001")
    assert isinstance(m.episodes["E2"], EpisodeProgress)
    assert m.episodes["E2"].shots_done == ["S001"]


def test_mark_video_done():
    m = ProjectManifest.from_dict({})
    m.mark_video_done("E1")
    assert m.episodes["E1"].video_done is True
    # 幂等
    m.mark_video_done("E1")
    assert m.episodes["E1"].video_done is True


# ---- episodes from_dict 还原 ------------------------------------------

def test_episodes_from_dict_roundtrip_fields():
    m = ProjectManifest.from_dict({
        "episodes": {
            "E1": {
                "title": "替嫁",
                "script": "剧本_E1.md",
                "storyboard": "分镜_E1.json",
                "image_prompts": "prompts/E1/",
                "shots_done": ["S001", "S002"],
                "video_done": True,
                "markers": {"🔥": ["S004"], "💰": []},
            }
        }
    })
    ep = m.episodes["E1"]
    assert ep.title == "替嫁"
    assert ep.script == "剧本_E1.md"
    assert ep.storyboard == "分镜_E1.json"
    assert ep.image_prompts == "prompts/E1/"
    assert ep.shots_done == ["S001", "S002"]
    assert ep.video_done is True
    assert ep.markers == {"🔥": ["S004"], "💰": []}


# ---- load/save round-trip ---------------------------------------------

def test_save_load_round_trip(tmp_path: Path):
    m = ProjectManifest.from_dict({
        "project_id": "P-006",
        "project_name": "替嫁新娘的逆袭",
        "genre": "短剧",
        "params": {"split_unit": "episode", "episode_count": 12},
        "style_bible": {"ref": "real/cinematic-warm-v1", "category": "real"},
        "status": "media_ready",
        "artifacts": {"idea": "创意.json", "script_index": "剧本.json"},
        "dependencies": {"分镜_E1.json": ["剧本_E1.md"]},
        "archive": [{"version": "v1.0", "dir": "归档/v1.0/"}],
    })
    m.set_stage("screenwriter", "completed", next_action="进入 ① 素材准备")
    m.mark_shot_done("E1", "S001")
    m.mark_shot_done("E1", "S002")
    m.mark_video_done("E1")

    path = tmp_path / "project.json"
    save_manifest(m, path)
    assert path.exists()

    back = load_manifest(path)
    assert back.project_id == "P-006"
    assert back.project_name == "替嫁新娘的逆袭"
    assert back.genre == "短剧"
    assert back.params == {"split_unit": "episode", "episode_count": 12}
    assert back.style_bible["ref"] == "real/cinematic-warm-v1"
    assert back.status == "media_ready"
    assert back.stage_state("screenwriter") == "completed"
    assert back.pipeline["screenwriter"].next_action == "进入 ① 素材准备"
    assert back.artifacts == {"idea": "创意.json", "script_index": "剧本.json"}
    assert back.episodes["E1"].shots_done == ["S001", "S002"]
    assert back.episodes["E1"].video_done is True
    assert back.dependencies == {"分镜_E1.json": ["剧本_E1.md"]}
    assert back.archive == [{"version": "v1.0", "dir": "归档/v1.0/"}]


def test_save_load_accepts_dir(tmp_path: Path):
    """load/save 接受目录路径（自动拼 project.json）。"""
    m = ProjectManifest.from_dict({"project_id": "P-009"})
    save_manifest(m, tmp_path)  # 传目录
    assert (tmp_path / "project.json").exists()
    back = load_manifest(tmp_path)  # 传目录
    assert back.project_id == "P-009"


def test_save_writes_utf8_and_human_readable(tmp_path: Path):
    m = ProjectManifest.from_dict({"project_name": "替嫁新娘的逆袭"})
    path = tmp_path / "project.json"
    save_manifest(m, path)
    text = path.read_text(encoding="utf-8")
    # 不转义中文
    assert "替嫁新娘的逆袭" in text
    # 合法 JSON
    data = json.loads(text)
    assert data["project_name"] == "替嫁新娘的逆袭"


def test_save_updates_last_modified(tmp_path: Path):
    m = ProjectManifest.from_dict({"project_id": "P-001"})
    path = tmp_path / "project.json"
    save_manifest(m, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("last_modified")  # 非空时间戳


# ---- 坏 JSON → 默认不崩 ------------------------------------------------

def test_load_bad_json_returns_default(tmp_path: Path):
    path = tmp_path / "project.json"
    path.write_text("{ this is not valid json ]", encoding="utf-8")
    m = load_manifest(path)
    assert isinstance(m, ProjectManifest)
    assert m.project_id == ""
    assert m.status == "scripted"


def test_load_missing_file_returns_default(tmp_path: Path):
    m = load_manifest(tmp_path / "nope.json")
    assert isinstance(m, ProjectManifest)
    assert m.project_id == ""


def test_load_non_dict_json_returns_default(tmp_path: Path):
    path = tmp_path / "project.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    m = load_manifest(path)
    assert isinstance(m, ProjectManifest)
    assert m.project_id == ""


# ---- to_dict 形状 ------------------------------------------------------

def test_to_dict_shape():
    m = ProjectManifest.from_dict({"project_id": "P-006"})
    d = m.to_dict()
    for key in (
        "schema_version", "project_id", "project_name", "genre", "params",
        "style_bible", "status", "pipeline", "artifacts", "episodes",
        "dependencies", "archive", "created_at", "last_modified",
    ):
        assert key in d
    # pipeline 序列化为 {stage: {state, next_action}}
    assert d["pipeline"]["screenwriter"]["state"] == "pending"
