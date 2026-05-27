"""画质×比例 → 像素 size 字符串。'自动' 返回 None（不向模型指定尺寸）。"""
from __future__ import annotations

QUALITIES = ["2K", "1K"]
RATIOS = ["自动", "1:1", "16:9", "9:16", "4:3", "3:4"]

_SIZES = {
    "2K": {"1:1": "2048x2048", "16:9": "2304x1296", "9:16": "1296x2304",
           "4:3": "2304x1728", "3:4": "1728x2304"},
    "1K": {"1:1": "1024x1024", "16:9": "1152x648", "9:16": "648x1152",
           "4:3": "1152x864", "3:4": "864x1152"},
}


def resolve_size(quality: str, ratio: str) -> str | None:
    if ratio == "自动":
        return None
    return _SIZES.get(quality, _SIZES["2K"]).get(ratio)
