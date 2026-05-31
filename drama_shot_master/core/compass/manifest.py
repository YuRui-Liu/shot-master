"""文件罗盘协议 · 项目清单 manifest（project.json）。

三层 manifest 的中间层：身份 / genre / params / style_bible 引用 /
阶段状态机 pipeline / 产物路径 artifacts / 逐集进度 episodes /
依赖图 dependencies / 归档 archive。

纯逻辑、无 Qt，全单测。字段形状照 research §2.3。
原则「升级不推倒」：只新增「总线」层，不改既有 创意.json/剧本.json 等文件。
完成判定与续跑靠 episodes.EN.shots_done[] 幂等回填。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

# project.json 在项目目录下的固定文件名
MANIFEST_FILENAME = "project.json"

# 四阶段（对齐侧栏 ⓪剧本→①素材→②分镜→③出片）
STAGE_NAMES = ("screenwriter", "assets", "storyboard", "production")

# status 三态（粗粒度门禁）；pipeline.*.state 细粒度（进度条）
DEFAULT_STATUS = "scripted"
DEFAULT_STAGE_STATE = "pending"


def _now_iso() -> str:
    """本地时区 ISO 时间戳。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


@dataclass
class StageState:
    """单个阶段的状态机条目：state(pending|in_progress|completed) + 下一步建议。"""
    state: str = DEFAULT_STAGE_STATE
    next_action: str = ""

    def to_dict(self) -> dict:
        return {"state": self.state, "next_action": self.next_action}

    @classmethod
    def from_dict(cls, d: dict) -> "StageState":
        d = d or {}
        return cls(
            state=str(d.get("state") or DEFAULT_STAGE_STATE),
            next_action=str(d.get("next_action") or ""),
        )


@dataclass
class EpisodeProgress:
    """逐集（或逐片段）进度索引：路径 + shots_done 幂等进度 + markers。

    单镜 prompt 正文不进 manifest（留 分镜_EN.json / prompts/EN/）；
    这里只记 shots_done[] 进度，支持断点续跑。
    """
    title: str = ""
    script: str = ""
    storyboard: str = ""
    image_prompts: str = ""
    video_prompts: str = ""
    audio_prompts: str = ""
    shots_done: list[str] = field(default_factory=list)
    video_done: bool = False
    markers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "script": self.script,
            "storyboard": self.storyboard,
            "image_prompts": self.image_prompts,
            "video_prompts": self.video_prompts,
            "audio_prompts": self.audio_prompts,
            "shots_done": list(self.shots_done),
            "video_done": self.video_done,
            "markers": dict(self.markers),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EpisodeProgress":
        d = d or {}
        return cls(
            title=str(d.get("title") or ""),
            script=str(d.get("script") or ""),
            storyboard=str(d.get("storyboard") or ""),
            image_prompts=str(d.get("image_prompts") or ""),
            video_prompts=str(d.get("video_prompts") or ""),
            audio_prompts=str(d.get("audio_prompts") or ""),
            shots_done=list(d.get("shots_done") or []),
            video_done=bool(d.get("video_done") or False),
            markers=dict(d.get("markers") or {}),
        )


def _default_pipeline() -> dict[str, StageState]:
    """四阶段默认全 pending。"""
    return {name: StageState() for name in STAGE_NAMES}


@dataclass
class ProjectManifest:
    """项目清单 project.json 的内存模型 + 字段访问器。"""

    schema_version: int = 1
    project_id: str = ""
    project_name: str = ""
    genre: str = ""
    params: dict = field(default_factory=dict)
    style_bible: dict = field(default_factory=dict)
    status: str = DEFAULT_STATUS
    pipeline: dict[str, StageState] = field(default_factory=_default_pipeline)
    artifacts: dict = field(default_factory=dict)
    episodes: dict[str, EpisodeProgress] = field(default_factory=dict)
    dependencies: dict = field(default_factory=dict)
    archive: list = field(default_factory=list)
    created_at: str = ""
    last_modified: str = ""

    # ---- 访问器：pipeline 阶段状态 ------------------------------------

    def stage_state(self, name: str) -> str:
        """读取阶段 state；未知阶段 → pending（不抛）。"""
        st = self.pipeline.get(name)
        return st.state if st is not None else DEFAULT_STAGE_STATE

    def set_stage(self, name: str, state: str,
                  next_action: Optional[str] = None) -> None:
        """写阶段 state；阶段不存在则新建。next_action 省略则保留原值。"""
        st = self.pipeline.get(name)
        if st is None:
            st = StageState()
            self.pipeline[name] = st
        st.state = state
        if next_action is not None:
            st.next_action = next_action

    # ---- 访问器：episodes 进度（幂等） --------------------------------

    def _episode(self, ep: str) -> EpisodeProgress:
        e = self.episodes.get(ep)
        if e is None:
            e = EpisodeProgress()
            self.episodes[ep] = e
        return e

    def mark_shot_done(self, ep: str, shot: str) -> None:
        """把 shot 加进该集 shots_done；重复同 shot 不重复（幂等）。"""
        e = self._episode(ep)
        if shot not in e.shots_done:
            e.shots_done.append(shot)

    def mark_video_done(self, ep: str) -> None:
        """标记该集出片完成（幂等）。"""
        self._episode(ep).video_done = True

    # ---- 序列化 ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "genre": self.genre,
            "params": dict(self.params),
            "style_bible": dict(self.style_bible),
            "status": self.status,
            "pipeline": {k: v.to_dict() for k, v in self.pipeline.items()},
            "artifacts": dict(self.artifacts),
            "episodes": {k: v.to_dict() for k, v in self.episodes.items()},
            "dependencies": dict(self.dependencies),
            "archive": list(self.archive),
            "created_at": self.created_at,
            "last_modified": self.last_modified,
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "ProjectManifest":
        """从 dict 还原；缺 status/params/pipeline 等字段 → 默认值迁移。"""
        d = d or {}

        # pipeline：缺则默认四阶段；存在则合并（保证四阶段都在）
        pipeline = _default_pipeline()
        raw_pipeline = d.get("pipeline")
        if isinstance(raw_pipeline, dict):
            for name, st in raw_pipeline.items():
                pipeline[name] = StageState.from_dict(st)

        # episodes
        episodes: dict[str, EpisodeProgress] = {}
        raw_eps = d.get("episodes")
        if isinstance(raw_eps, dict):
            for ep, val in raw_eps.items():
                episodes[ep] = EpisodeProgress.from_dict(val)

        return cls(
            schema_version=int(d.get("schema_version") or 1),
            project_id=str(d.get("project_id") or ""),
            project_name=str(d.get("project_name") or ""),
            genre=str(d.get("genre") or ""),
            params=dict(d.get("params") or {}),
            style_bible=dict(d.get("style_bible") or {}),
            status=str(d.get("status") or DEFAULT_STATUS),
            pipeline=pipeline,
            artifacts=dict(d.get("artifacts") or {}),
            episodes=episodes,
            dependencies=dict(d.get("dependencies") or {}),
            archive=list(d.get("archive") or []),
            created_at=str(d.get("created_at") or ""),
            last_modified=str(d.get("last_modified") or ""),
        )


# ---- 落盘读写 ---------------------------------------------------------

def _resolve_path(path: Union[str, Path]) -> Path:
    """传目录则自动拼 project.json；传文件则原样。"""
    p = Path(path)
    if p.is_dir() or p.suffix == "":
        return p / MANIFEST_FILENAME
    return p


def load_manifest(path: Union[str, Path]) -> ProjectManifest:
    """读 project.json → ProjectManifest；缺失/坏 JSON/非 dict → 默认不崩。"""
    p = _resolve_path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return ProjectManifest()
    if not isinstance(data, dict):
        return ProjectManifest()
    return ProjectManifest.from_dict(data)


def save_manifest(manifest: ProjectManifest, path: Union[str, Path]) -> Path:
    """落盘 project.json：刷新 last_modified（缺 created_at 则补），utf-8 缩进。"""
    p = _resolve_path(path)
    now = _now_iso()
    if not manifest.created_at:
        manifest.created_at = now
    manifest.last_modified = now
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p
