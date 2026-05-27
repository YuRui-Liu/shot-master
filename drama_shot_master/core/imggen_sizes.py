"""画质×比例 → ARK size 参数。
- 指定比例 → 精确 "宽x高"（锁画布纵横比，适合 N×N 宫格合图）。
- '自动' → 返回画质关键字 "2K"/"1K"（ARK 接受；纵横比交给提示词/参考图推断，
  与豆包官方 size="2K" 调用一致，避免无 size 时退化成方图导致宫格比例错）。"""
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
    q = quality if quality in _SIZES else "2K"
    if ratio == "自动":
        return q                       # 关键字 "2K"/"1K"，纵横比由提示词决定
    return _SIZES[q].get(ratio)
