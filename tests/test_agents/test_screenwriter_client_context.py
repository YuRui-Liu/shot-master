"""T3 客户端组装 context（非 GUI）：

发请求前读 project.json(params.genre / style_bible.ref) → load_genre + get_style
→ gen_context.build_genre_context / build_style_context → 填进 request 的
genre_context / style_context。缺 genre/style → 空串（降级，行为不变）。

纯函数 assemble_gen_context(project_dir, stage) -> (genre_context, style_context)
便于测；HTTP 发送全 mock，不连真服务。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from drama_shot_master.agents.screenwriter_client import (
    ScreenwriterClient,
    assemble_gen_context,
)

# 用真实内置题材 / 风格 id（随包分发），保证组装出非空且含关键词。
_GENRE_ID = "short-drama"
_STYLE_ID = "real/cinematic-warm-v1"


def _write_manifest(project_dir: Path, *, genre=None, ref=None) -> None:
    data: dict = {"schema_version": 1, "project_id": "p1", "params": {}, "style_bible": {}}
    if genre is not None:
        data["params"]["genre"] = genre
    if ref is not None:
        data["style_bible"]["ref"] = ref
    (project_dir / "project.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---- assemble_gen_context 纯函数 -------------------------------------------

def test_assemble_full_context_nonempty(tmp_path):
    """project.json 含 genre + style_bible.ref → 组装出非空 context 含题材/风格关键词。"""
    _write_manifest(tmp_path, genre={"genre": _GENRE_ID, "sub": []}, ref=_STYLE_ID)

    genre_ctx, style_ctx = assemble_gen_context(tmp_path, stage="render")

    assert genre_ctx  # 非空
    assert "题材特征" in genre_ctx  # 题材骨架关键词
    assert style_ctx  # 非空
    assert "cinematic" in style_ctx  # 风格 prompt_suffix 关键词


def test_assemble_genre_accepts_plain_string(tmp_path):
    """params.genre 也可能是裸字符串（非 {genre,sub} dict）→ 仍能解析。"""
    _write_manifest(tmp_path, genre=_GENRE_ID, ref=_STYLE_ID)

    genre_ctx, _ = assemble_gen_context(tmp_path, stage="render")

    assert "题材特征" in genre_ctx


def test_assemble_missing_genre_and_style_returns_empty(tmp_path):
    """缺 genre / style → 空串（降级，行为不变）。"""
    _write_manifest(tmp_path)  # 无 genre / 无 ref

    genre_ctx, style_ctx = assemble_gen_context(tmp_path, stage="render")

    assert genre_ctx == ""
    assert style_ctx == ""


def test_assemble_missing_manifest_returns_empty(tmp_path):
    """没有 project.json → 空串不崩。"""
    genre_ctx, style_ctx = assemble_gen_context(tmp_path, stage="render")
    assert (genre_ctx, style_ctx) == ("", "")


def test_assemble_unknown_genre_id_degrades(tmp_path):
    """未知 genre id（load_genre 抛 FileNotFoundError）→ 降级空串，不崩。"""
    _write_manifest(tmp_path, genre={"genre": "no-such-genre"}, ref="no/such-style")

    genre_ctx, style_ctx = assemble_gen_context(tmp_path, stage="render")

    assert genre_ctx == ""
    assert style_ctx == ""


def test_assemble_ref_stage_includes_fingerprint(tmp_path):
    """stage='ref'（角色 ref）→ style_context 含指纹，比 render 更长。"""
    _write_manifest(tmp_path, genre={"genre": _GENRE_ID}, ref=_STYLE_ID)

    _, style_render = assemble_gen_context(tmp_path, stage="render")
    _, style_ref = assemble_gen_context(tmp_path, stage="ref")

    assert style_ref != style_render
    assert len(style_ref) >= len(style_render)


# ---- 通过 client 填进 request（mock HTTP，不连真服务） ---------------------

class _FakeResp:
    status_code = 200

    def iter_lines(self):
        return iter([])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeClient:
    def __init__(self, captured):
        self._captured = captured

    def stream(self, method, url, json=None, params=None):
        self._captured["json"] = json
        self._captured["url"] = url
        return _FakeResp()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_httpx(monkeypatch, captured):
    import drama_shot_master.agents.screenwriter_client as m
    monkeypatch.setattr(
        m, "httpx",
        type("X", (), {"Client": staticmethod(lambda *a, **kw: _FakeClient(captured))}),
    )


def test_stream_post_injects_context_from_project(tmp_path, monkeypatch):
    """body 缺 genre_context/style_context 时，client 按 project_dir 自动注入。"""
    _write_manifest(tmp_path, genre={"genre": _GENRE_ID}, ref=_STYLE_ID)
    captured: dict = {}
    _patch_httpx(monkeypatch, captured)

    c = ScreenwriterClient("http://localhost:18430")
    body = {"project_dir": str(tmp_path)}
    list(c.stream_post("/storyboard", body, stage="render"))

    sent = captured["json"]
    assert sent["genre_context"]
    assert "题材特征" in sent["genre_context"]
    assert sent["style_context"]
    assert "cinematic" in sent["style_context"]


def test_stream_post_does_not_overwrite_existing_context(tmp_path, monkeypatch):
    """body 已带 context → 不覆盖（调用方显式传入优先）。"""
    _write_manifest(tmp_path, genre={"genre": _GENRE_ID}, ref=_STYLE_ID)
    captured: dict = {}
    _patch_httpx(monkeypatch, captured)

    c = ScreenwriterClient("http://localhost:18430")
    body = {
        "project_dir": str(tmp_path),
        "genre_context": "PRESET",
        "style_context": "PRESET",
    }
    list(c.stream_post("/storyboard", body, stage="render"))

    sent = captured["json"]
    assert sent["genre_context"] == "PRESET"
    assert sent["style_context"] == "PRESET"


def test_stream_post_without_project_dir_no_context(tmp_path, monkeypatch):
    """body 无 project_dir → 不注入 context（保持原行为）。"""
    captured: dict = {}
    _patch_httpx(monkeypatch, captured)

    c = ScreenwriterClient("http://localhost:18430")
    list(c.stream_post("/storyboard", {"foo": 1}, stage="render"))

    sent = captured["json"]
    assert "genre_context" not in sent
    assert "style_context" not in sent
