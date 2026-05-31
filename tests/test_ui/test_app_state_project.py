"""B1 · AppState.load_project（项目 scope 回填）单测。

R2-2 阶段B「兼容扩展」：load_project 为纯新增方法，
load_dir() / current_dir（批处理态）完全不动、物理分离。

覆盖：
- 有 project.json → 走 compass.load_manifest，回填
  current_project_dir/current_project_id/pipeline_state(4 阶段 state)/next_action 正确。
- 无 project.json → 走 compass.migrate（migrate_project_dir）回填。
- load_project 不影响 current_dir / images / 批处理态。
- 缺失/坏目录 → 降级不崩。

AppState 不依赖 PySide6，本测试可纯跑（无需 QApplication）。
"""
from __future__ import annotations

import json
from pathlib import Path

from drama_shot_master.core.compass.manifest import (
    STAGE_NAMES,
    ProjectManifest,
    StageState,
    save_manifest,
)
from drama_shot_master.ui.state import AppState


# ---- 夹具：构造带 project.json 的罗盘项目 -----------------------------

def _make_manifest_project(root: Path) -> Path:
    """造一个已有 project.json 的项目目录，返回项目根。"""
    pdir = root / "P-007_demo"
    pdir.mkdir(parents=True, exist_ok=True)
    manifest = ProjectManifest(
        project_id="P-007",
        project_name="演示项目",
        pipeline={
            "screenwriter": StageState(state="completed", next_action="进入 ① 素材准备"),
            "assets": StageState(state="in_progress", next_action="准备角色参考"),
            "storyboard": StageState(),
            "production": StageState(),
        },
    )
    save_manifest(manifest, pdir)
    return pdir


def _make_legacy_project(root: Path) -> Path:
    """造一个无 project.json 的旧项目目录（含剧本.json），返回项目根。"""
    pdir = root / "P-009_legacy"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "创意.json").write_text(
        json.dumps({"title": "旧项目"}, ensure_ascii=False), encoding="utf-8"
    )
    (pdir / "剧本.json").write_text(
        json.dumps(
            {
                "title": "旧项目",
                "episodes": [{"id": "E1", "title": "第一集", "summary": "..."}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pdir / "剧本_E1.md").write_text("# 第一集\n", encoding="utf-8")
    return pdir


# ---- 默认字段 ---------------------------------------------------------

def test_defaults_are_none_and_empty():
    st = AppState()
    assert st.current_project_dir is None
    assert st.current_project_id is None
    assert st.pipeline_state == {}
    assert st.next_action == {}


# ---- 有 project.json → load_manifest 回填 -----------------------------

def test_load_project_with_manifest(tmp_path):
    pdir = _make_manifest_project(tmp_path)
    st = AppState()
    st.load_project(pdir)

    assert st.current_project_dir == pdir
    assert st.current_project_id == "P-007"
    # 4 阶段 state 全回填
    assert set(st.pipeline_state.keys()) == set(STAGE_NAMES)
    assert st.pipeline_state["screenwriter"] == "completed"
    assert st.pipeline_state["assets"] == "in_progress"
    assert st.pipeline_state["storyboard"] == "pending"
    # next_action 回填
    assert st.next_action["screenwriter"] == "进入 ① 素材准备"
    assert st.next_action["assets"] == "准备角色参考"


# ---- 无 project.json → migrate 回填 -----------------------------------

def test_load_project_without_manifest_runs_migrate(tmp_path):
    pdir = _make_legacy_project(tmp_path)
    assert not (pdir / "project.json").exists()

    st = AppState()
    st.load_project(pdir)

    # migrate 落盘 project.json
    assert (pdir / "project.json").exists()
    assert st.current_project_dir == pdir
    assert st.current_project_id == "P-009"
    assert set(st.pipeline_state.keys()) == set(STAGE_NAMES)
    # 有剧本 → screenwriter completed
    assert st.pipeline_state["screenwriter"] == "completed"


# ---- load_project 不影响批处理态（物理分离） --------------------------

def test_load_project_does_not_touch_batch_state(tmp_path):
    pdir = _make_manifest_project(tmp_path)
    st = AppState()
    # 模拟批处理态已有值
    batch_dir = Path("/some/batch/dir")
    st.current_dir = batch_dir
    st.images = ["sentinel"]  # type: ignore[list-item]
    st.selected = [0]

    st.load_project(pdir)

    # 批处理态完全不动
    assert st.current_dir == batch_dir
    assert st.images == ["sentinel"]
    assert st.selected == [0]
    # 项目态独立回填
    assert st.current_project_dir == pdir


# ---- 缺失/坏目录降级不崩 ----------------------------------------------

def test_load_project_missing_dir_degrades(tmp_path):
    st = AppState()
    missing = tmp_path / "does_not_exist"
    st.load_project(missing)  # 不抛
    assert st.current_project_dir is None
    assert st.current_project_id is None
    assert st.pipeline_state == {}
    assert st.next_action == {}


def test_load_project_none_degrades():
    st = AppState()
    st.load_project(None)  # type: ignore[arg-type]
    assert st.current_project_dir is None
    assert st.pipeline_state == {}
