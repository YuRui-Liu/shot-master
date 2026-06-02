"""GET 接口：hot_themes / cold_topics / platform_stats / trend / report。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/analysis")


def _get_db(request: Request):
    return request.app.state.db


@router.get("/hot_themes")
def hot_themes(request: Request, limit: int = 10, days: int = 7,
               platform: str = "") -> list[dict]:
    """热门主题列表（按 heat_score 降序）。"""
    db = _get_db(request)
    return db.get_hot_themes(limit=limit, days=days, platform=platform)


@router.get("/cold_topics")
def cold_topics(request: Request, limit: int = 6,
                platform: str = "") -> list[dict]:
    """冷门机会列表（mention_count 低但最近活跃）。"""
    db = _get_db(request)
    return db.get_cold_topics(limit=limit, platform=platform)


@router.get("/platform_stats")
def platform_stats(request: Request) -> list[dict]:
    """按平台维度汇总爬取统计。"""
    db = _get_db(request)
    return db.get_platform_stats()


@router.get("/trend")
def trend(request: Request, theme: str = Query(...),
          months: int = 6) -> list[dict]:
    """某主题的历史趋势数据。"""
    db = _get_db(request)
    return db.get_theme_trend(theme_name=theme, months=months)


@router.get("/report")
def report(request: Request, latest: bool = True) -> dict[str, Any] | None:
    """获取最新分析报告全文。latest=false 时返回列表预览。"""
    db = _get_db(request)
    if latest:
        r = db.get_latest_analysis()
        if r:
            # 将 JSON 字符串反序列化回对象
            import json
            for key in ("report_json", "hot_themes_json", "cold_topics_json"):
                if key in r and isinstance(r[key], str):
                    try:
                        r[key] = json.loads(r[key])
                    except json.JSONDecodeError:
                        pass
        return r
    else:
        return db.get_analyses(limit=20)
