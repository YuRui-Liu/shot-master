"""资源库 RefImageGenerator 服务单测（纯逻辑、可注入、绝不真连网络）。

覆盖（波次1 · A4 资源库出图服务）：
- generate_ref：style_bible 注入 ref 阶段 prompt → 组 Task(type=image) →
  经 compass.ImageProvider + TaskRunner 落盘 → done 则登记 ref_index
  (source=ai-generated / status=ready) 并落盘 ref_index.json → 返回 (True, 绝对路径)。
- 注入假 image_backend(写空文件) → True；backend 不写 → (False, err) 且不落 ref_index。
- batch_generate：多条 name → {name: (ok, msg)}。
- kind 限 characters/scenes/props；非法 kind → 报错。
- style_loader 可注入（不读真实风格库即可测注入文本）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from drama_shot_master.core.compass.ref_index import load_ref_index
from drama_shot_master.services.ref_generator import RefImageGenerator


# ---- 假底层出图函数（记录入参 + 落盘，绝不真连网络）-------------------

class _FakeBackend:
    """模拟底层出图：记录每次 (prompt, ref_files, abs_out)，并把产物写到 abs_out。

    write_file=False 模拟「底层返回但未落盘」，用于验证失败判定看文件。
    """

    def __init__(self, *, write_file: bool = True):
        self.calls: list[dict] = []
        self.write_file = write_file

    def __call__(self, task, abs_out: Path) -> None:
        self.calls.append({
            "prompt": task.prompt,
            "ref_files": list(task.ref_files),
            "abs_out": abs_out,
        })
        if self.write_file:
            abs_out.parent.mkdir(parents=True, exist_ok=True)
            abs_out.write_bytes(b"")  # 空文件即视为落盘成功


def _fake_style_loader(style_id: str) -> dict:
    """假风格加载器：返回带 prompt_suffix/ref_fingerprint/negative_suffix 的实体。"""
    return {
        "style_id": style_id,
        "prompt_suffix": "电影感真人写实",
        "ref_fingerprint": "中性平光 三视图",
        "negative_suffix": "no subtitles, no watermark",
    }


def _make_gen(tmp_path: Path, backend) -> RefImageGenerator:
    return RefImageGenerator(
        cfg=object(),
        project_root=tmp_path,
        image_backend=backend,
        style_loader=_fake_style_loader,
    )


# ---- generate_ref 成功路径 -------------------------------------------

def test_generate_ref_success_writes_file_and_ref_index(tmp_path: Path):
    backend = _FakeBackend()
    gen = _make_gen(tmp_path, backend)

    ok, path = gen.generate_ref(
        "characters", "女主", base_prompt="少女特写", style_id="real_cinema"
    )

    assert ok is True
    abs_out = tmp_path / "characters" / "女主_ref.png"
    assert Path(path) == abs_out
    assert abs_out.exists()

    # ref_index.json 落盘且 status=ready / source=ai-generated
    idx = load_ref_index(tmp_path / "characters")
    entry = idx.get("女主")
    assert entry is not None
    assert entry.status == "ready"
    assert entry.source == "ai-generated"
    assert entry.path  # 有落盘路径


def test_generate_ref_injects_style_at_ref_stage(tmp_path: Path):
    """注入文本走 ref 阶段：含 ref_fingerprint + prompt_suffix + negative_suffix。"""
    backend = _FakeBackend()
    gen = _make_gen(tmp_path, backend)

    gen.generate_ref("scenes", "古城", base_prompt="黄昏城墙", style_id="s1")

    assert len(backend.calls) == 1
    prompt = backend.calls[0]["prompt"]
    assert "黄昏城墙" in prompt
    assert "中性平光 三视图" in prompt   # ref_fingerprint 仅 ref 阶段
    assert "电影感真人写实" in prompt     # prompt_suffix
    assert "no subtitles" in prompt       # negative_suffix


def test_generate_ref_passes_ref_files(tmp_path: Path):
    backend = _FakeBackend()
    gen = _make_gen(tmp_path, backend)

    gen.generate_ref(
        "props", "宝剑", base_prompt="古剑特写", style_id="s1",
        ref_files=["characters/女主_ref.png"],
    )
    assert backend.calls[0]["ref_files"] == ["characters/女主_ref.png"]


# ---- generate_ref 失败路径 -------------------------------------------

def test_generate_ref_backend_no_write_returns_false(tmp_path: Path):
    """底层未落盘 → (False, err)，且不登记 ref_index。"""
    backend = _FakeBackend(write_file=False)
    gen = _make_gen(tmp_path, backend)

    ok, msg = gen.generate_ref("characters", "男主", base_prompt="少年", style_id="s1")

    assert ok is False
    assert isinstance(msg, str) and msg
    # 未落盘 → ref_index 不应登记该条
    idx = load_ref_index(tmp_path / "characters")
    assert idx.get("男主") is None


# ---- kind 校验 -------------------------------------------------------

def test_generate_ref_rejects_invalid_kind(tmp_path: Path):
    backend = _FakeBackend()
    gen = _make_gen(tmp_path, backend)
    with pytest.raises(ValueError):
        gen.generate_ref("invalid", "x", base_prompt="y", style_id="s1")


@pytest.mark.parametrize("kind", ["characters", "scenes", "props"])
def test_generate_ref_accepts_valid_kinds(tmp_path: Path, kind: str):
    backend = _FakeBackend()
    gen = _make_gen(tmp_path, backend)
    ok, path = gen.generate_ref(kind, "n", base_prompt="p", style_id="s1")
    assert ok is True
    assert (tmp_path / kind / "n_ref.png").exists()


# ---- batch_generate --------------------------------------------------

def test_batch_generate_multiple(tmp_path: Path):
    backend = _FakeBackend()
    gen = _make_gen(tmp_path, backend)

    result = gen.batch_generate(
        "characters",
        ["女主", "男主", "配角"],
        base_prompts={"女主": "少女", "男主": "少年", "配角": "老者"},
        style_id="s1",
    )

    assert set(result.keys()) == {"女主", "男主", "配角"}
    assert all(ok for ok, _ in result.values())
    for name in ("女主", "男主", "配角"):
        assert (tmp_path / "characters" / f"{name}_ref.png").exists()

    # 三条都登记进同一个 ref_index.json
    idx = load_ref_index(tmp_path / "characters")
    assert {e.name for e in idx.entries} == {"女主", "男主", "配角"}
    assert all(e.status == "ready" for e in idx.entries)


def test_batch_generate_partial_failure(tmp_path: Path):
    """某条缺 base_prompt 或底层失败 → 该条 (False, msg)，其余成功不受影响。"""
    class _SelectiveBackend(_FakeBackend):
        def __call__(self, task, abs_out: Path) -> None:
            # 名字含「坏」的不落盘，模拟失败
            self.calls.append({"prompt": task.prompt, "abs_out": abs_out,
                               "ref_files": list(task.ref_files)})
            if "坏" not in task.prompt:
                abs_out.parent.mkdir(parents=True, exist_ok=True)
                abs_out.write_bytes(b"")

    gen = _make_gen(tmp_path, _SelectiveBackend())
    result = gen.batch_generate(
        "scenes", ["好场景", "坏场景"],
        base_prompts={"好场景": "晴天", "坏场景": "坏 雨夜"},
        style_id="s1",
    )
    assert result["好场景"][0] is True
    assert result["坏场景"][0] is False

    idx = load_ref_index(tmp_path / "scenes")
    assert idx.get("好场景") is not None
    assert idx.get("坏场景") is None
