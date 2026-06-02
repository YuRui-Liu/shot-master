"""media_agent 转场端点 — 无 Qt。analyze 用假路径降级中性帧；ffmpeg_args 干跑。"""
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from media_agent.server import create_app

client = TestClient(create_app())

# 跨平台假绝对路径（不存在但格式正确），让 _resolve_and_validate_clip_paths
# 走"绝对 + 不存在 = missing"分支（而非"相对 + 无 project = missing"分支）。
_FAKE_BASE = str(Path(tempfile.gettempdir()) / "__test_nonexistent_transition__")


def _comp(n=2):
    return {
        "clips": [
            {"path": f"{_FAKE_BASE}/clip_{i}.mp4", "duration": 5.0, "keep": True}
            for i in range(n)
        ],
        "width": 640, "height": 360, "fps": 30,
    }


def test_analyze_neutral_on_missing_files():
    """假路径 → 抽帧空 → 中性评分，不崩，回填 cv_scores/auto_transition。"""
    r = client.post("/transition/analyze", json={"composition": _comp(2)})
    assert r.status_code == 200, r.text
    clips = r.json()["composition"]["clips"]
    assert clips[0]["cv_scores"]          # 首切口被回填
    assert clips[0]["auto_transition"]


def test_ffmpeg_args_dry_run():
    r = client.post("/transition/ffmpeg_args", json={
        "composition": _comp(2), "out_path": "/out/final.mp4"})
    assert r.status_code == 200, r.text
    args = r.json()["args"]
    assert isinstance(args, list) and len(args) > 0
    assert "-i" in args and "/out/final.mp4" in args


def test_render_rejects_empty_composition():
    comp = _comp(1)
    comp["clips"][0]["keep"] = False      # 无保留片段 → validate 失败
    r = client.post("/transition/ffmpeg_args", json={
        "composition": comp, "out_path": "/out/x.mp4"})
    assert r.status_code == 400
