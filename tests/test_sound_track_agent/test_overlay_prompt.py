"""suggest_overlay_prompt：LLM 预填生成提示词建议，可降级。

测试一律 mock provider，绝不真连网络/LLM。
"""
from __future__ import annotations

import json

import sound_track_agent.overlay_prompt as op
from sound_track_agent.overlay_prompt import suggest_overlay_prompt


class _Cfg:
    """模拟宿主 Config 最小子集。"""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeProvider:
    """记录 generate 调用并返回预置文本。"""
    def __init__(self, ret="", raises=None):
        self._ret = ret
        self._raises = raises
        self.calls = []

    def generate(self, images, system_prompt, user_supplement):
        self.calls.append((list(images), system_prompt, user_supplement))
        if self._raises is not None:
            raise self._raises
        return self._ret


def test_returns_provider_text_stripped(monkeypatch, tmp_path):
    """provider 返回文本 → 透传并去首尾空白。"""
    fake = _FakeProvider(ret="  紧张的悬疑弦乐 \n")
    monkeypatch.setattr(op, "build_soundtrack_provider", lambda cfg: fake)

    out = suggest_overlay_prompt(
        "bgm", 10.0, 18.0,
        work_dir=tmp_path, cfg=_Cfg(), dialogue_text="你到底是谁")

    assert out == "紧张的悬疑弦乐"
    # 只调一次；纯文本（无图）
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == []


def test_prompt_carries_kind_and_dialogue_and_style(monkeypatch, tmp_path):
    """组的 prompt 应带上 kind、对白字幕、global_style 上下文。"""
    # 写一个 session.json 提供 global_style
    (tmp_path / "session.json").write_text(
        json.dumps({"source_mp4": "x", "source_hash": "h",
                    "global_style": "赛博朋克夜雨", "frame_rate": 24.0}),
        encoding="utf-8")
    fake = _FakeProvider(ret="电子节拍")
    monkeypatch.setattr(op, "build_soundtrack_provider", lambda cfg: fake)

    suggest_overlay_prompt(
        "sfx", 3.0, 5.0,
        work_dir=tmp_path, cfg=_Cfg(), dialogue_text="脚步声逼近")

    sys_p, user_p = fake.calls[0][1], fake.calls[0][2]
    blob = sys_p + "\n" + user_p
    assert "sfx" in blob.lower()
    assert "脚步声逼近" in blob
    assert "赛博朋克夜雨" in blob


def test_provider_raises_returns_empty(monkeypatch, tmp_path):
    """provider.generate 抛异常 → 降级返回空串。"""
    fake = _FakeProvider(raises=RuntimeError("boom"))
    monkeypatch.setattr(op, "build_soundtrack_provider", lambda cfg: fake)

    out = suggest_overlay_prompt(
        "bgm", 0.0, 4.0, work_dir=tmp_path, cfg=_Cfg())
    assert out == ""


def test_build_provider_raises_returns_empty(monkeypatch, tmp_path):
    """构造 provider 阶段抛（未配置）→ 降级返回空串。"""
    def _boom(cfg):
        raise RuntimeError("no creds")
    monkeypatch.setattr(op, "build_soundtrack_provider", _boom)

    out = suggest_overlay_prompt(
        "sfx", 1.0, 2.0, work_dir=tmp_path, cfg=_Cfg())
    assert out == ""


def test_provider_returns_none_returns_empty(monkeypatch, tmp_path):
    """provider 返回 None → 视作空，返回空串（不崩）。"""
    fake = _FakeProvider(ret=None)
    monkeypatch.setattr(op, "build_soundtrack_provider", lambda cfg: fake)

    out = suggest_overlay_prompt(
        "bgm", 0.0, 4.0, work_dir=tmp_path, cfg=_Cfg())
    assert out == ""
