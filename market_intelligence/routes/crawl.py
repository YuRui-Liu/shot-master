"""POST /crawl/now — 手动触发爬取 + LLM 分析 → 写 SQLite → 返回摘要。
GET /crawl/status — 最后爬取时间 / 计数。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from market_intelligence.crawler.hongguo import HongGuoCrawler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crawl")


def _get_db(request: Request):
    """从 app.state 取数据库实例。"""
    return request.app.state.db


def _get_analyzer(request: Request):
    """从 app.state 取分析器实例（可能为 None）。"""
    return getattr(request.app.state, "analyzer", None)


@router.post("/now")
def crawl_now(request: Request) -> dict[str, Any]:
    """手动触发全平台爬取 + LLM 分析。

    流程：爬各平台 parse → 写 crawl_logs → LLM 分析 → 写 analyses + theme_index。
    单个爬虫失败不影响其他平台（部分结果返回）。
    """
    db = _get_db(request)
    analyzer = _get_analyzer(request)
    cfg = request.app.state.cfg

    platforms = cfg.platforms
    all_entries: list[dict] = []
    crawl_ids: list[int] = []
    errors: list[dict] = []

    # ---- 1. 爬取阶段 ----
    for plat in platforms:
        pid = plat["id"]
        try:
            if pid == "hongguo":
                crawler = HongGuoCrawler()
                items = crawler.crawl(plat.get("url", ""))
            else:
                items = []
                logger.warning("Unknown platform id: %s", pid)

            for item in items:
                cid = db.insert_crawl_log(
                    platform=pid,
                    source_url=plat.get("url", ""),
                    title=item.get("title", ""),
                    rank=item.get("rank", 0),
                    raw_json=item,
                    meta_json=item.get("meta", {}),
                    crawled_at=datetime.now(timezone.utc).isoformat(),
                )
                crawl_ids.append(cid)
            all_entries.extend(items)
            logger.info("Crawled %s: %d items", pid, len(items))
        except Exception as exc:
            logger.error("Crawl failed for %s: %s", pid, exc)
            errors.append({"platform": pid, "error": str(exc)})

    # ---- 2. 分析阶段 ----
    analysis_result: dict[str, Any] = {}
    if analyzer and all_entries:
        try:
            analysis_result = analyzer.analyze(all_entries)
        except Exception as exc:
            logger.error("LLM analysis failed: %s", exc)
            analysis_result = analyzer._fallback_result(str(exc))
            errors.append({"stage": "analysis", "error": str(exc)})
    elif not all_entries:
        analysis_result = {
            "market_summary": "本次爬取未获得有效数据。",
            "hot_themes": [],
            "cold_topics": [],
            "genre_distribution": {},
            "platform_stats": {},
        }

    # ---- 3. 写入 analyses ----
    analysis_id = 0
    if crawl_ids:
        analysis_id = db.insert_analysis(
            crawl_id=crawl_ids[0],
            report_json=analysis_result,
            hot_themes_json=analysis_result.get("hot_themes", []),
            cold_topics_json=analysis_result.get("cold_topics", []),
            market_summary=analysis_result.get("market_summary", ""),
        )

    # ---- 4. 更新 theme_index ----
    for theme in analysis_result.get("hot_themes", []):
        try:
            db.upsert_theme(
                theme_name=theme.get("name", ""),
                heat_score=float(theme.get("heat", 0)),
                trend_direction=theme.get("trend", "stable"),
            )
        except Exception:
            pass
    for topic in analysis_result.get("cold_topics", []):
        try:
            db.upsert_theme(
                theme_name=topic.get("name", ""),
                heat_score=float(topic.get("rising_speed", 0)),
                trend_direction="rising",
            )
        except Exception:
            pass

    return {
        "status": "ok" if not errors else "partial",
        "crawled_items": len(all_entries),
        "platform_count": len(platforms),
        "analysis_id": analysis_id,
        "errors": errors,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
def crawl_status(request: Request, platform: str = "") -> dict[str, Any]:
    """返回最后爬取时间和计数。"""
    db = _get_db(request)
    last = db.get_last_crawl_time(platform)
    count = db.get_crawl_count(platform)
    return {
        "last_crawl_at": last,
        "total_crawl_count": count,
    }
