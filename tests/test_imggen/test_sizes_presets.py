from drama_shot_master.core import imggen_sizes as S
from drama_shot_master.core import imggen_presets as P


def test_resolve_size_2k():
    assert S.resolve_size("2K", "16:9") == "2304x1296"
    assert S.resolve_size("2K", "1:1") == "2048x2048"
    assert S.resolve_size("2K", "3:4") == "1728x2304"


def test_resolve_size_1k():
    assert S.resolve_size("1K", "16:9") == "1152x648"
    assert S.resolve_size("1K", "9:16") == "648x1152"


def test_resolve_size_auto_returns_quality_keyword():
    assert S.resolve_size("2K", "自动") == "2K"
    assert S.resolve_size("1K", "自动") == "1K"


def test_quick_prompts():
    labels = [p[0] for p in P.QUICK_PROMPTS]
    assert labels == ["三视图", "人设", "2D", "360°", "3D", "国漫", "特写", "中焦", "广角"]
    d = dict(P.QUICK_PROMPTS)
    assert d["3D"] == "3D建模风格，CG渲染，"
    assert "360度水平无死角" in d["360°"]
    assert d["广角"] == "广角镜头，透视变形，场景开阔，"
