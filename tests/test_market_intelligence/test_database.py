"""零网络验证 MarketDB schema + CRUD 操作。"""
from __future__ import annotations

import pytest

from market_intelligence.database import MarketDB


@pytest.fixture
def db(tmp_path):
    """每个测试用独立临时数据库。"""
    db_path = tmp_path / "test_market.db"
    _db = MarketDB(db_path)
    yield _db
    _db.close()


class TestSchema:
    """验证三张表存在且可写入。"""

    def test_tables_exist(self, db):
        with db._cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}
        assert "crawl_logs" in tables
        assert "analyses" in tables
        assert "theme_index" in tables

    def test_indexes_exist(self, db):
        with db._cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {r[0] for r in cur.fetchall()}
        assert len(indexes) >= 5


class TestCrawlLogsCRUD:

    def test_insert_and_retrieve(self, db):
        cid = db.insert_crawl_log(
            platform="hongguo",
            source_url="https://example.com/rank",
            title="测试短剧A",
            rank=1,
            raw_json={"title": "测试短剧A", "tags": ["甜宠"]},
            meta_json={"duration": "2min"},
        )
        assert cid > 0

        logs = db.get_crawl_logs(platform="hongguo", limit=10)
        assert len(logs) >= 1
        assert logs[0]["title"] == "测试短剧A"
        assert logs[0]["rank"] == 1

    def test_get_last_crawl_time(self, db):
        # 初始无记录
        assert db.get_last_crawl_time() is None

        db.insert_crawl_log(platform="hongguo", title="A", rank=1)
        last = db.get_last_crawl_time()
        assert last is not None

    def test_get_crawl_count(self, db):
        assert db.get_crawl_count() == 0
        db.insert_crawl_log(platform="hongguo", title="A", rank=1)
        db.insert_crawl_log(platform="hongguo", title="B", rank=2)
        assert db.get_crawl_count() == 2
        assert db.get_crawl_count(platform="hongguo") == 2
        assert db.get_crawl_count(platform="unknown") == 0


class TestAnalysesCRUD:

    def test_insert_and_retrieve(self, db):
        cid = db.insert_crawl_log(platform="hongguo", title="X", rank=1)
        aid = db.insert_analysis(
            crawl_id=cid,
            report_json={"market_summary": "整体繁荣"},
            hot_themes_json=[{"name": "甜宠", "heat": 90}],
            cold_topics_json=[{"name": "科幻短剧", "rising_speed": 70}],
            market_summary="整体繁荣",
        )
        assert aid > 0

        latest = db.get_latest_analysis()
        assert latest is not None
        assert latest["market_summary"] == "整体繁荣"

    def test_get_analyses_list(self, db):
        cid = db.insert_crawl_log(platform="hongguo", title="X", rank=1)
        db.insert_analysis(crawl_id=cid, market_summary="A")
        db.insert_analysis(crawl_id=cid, market_summary="B")
        items = db.get_analyses(limit=10)
        assert len(items) == 2

    def test_get_latest_empty(self, db):
        assert db.get_latest_analysis() is None


class TestThemeIndexCRUD:

    def test_upsert_new_theme(self, db):
        tid = db.upsert_theme("甜宠逆袭", platform="hongguo", heat_score=85.0,
                              trend_direction="rising")
        assert tid > 0

        themes = db.get_hot_themes(limit=10)
        assert len(themes) >= 1
        assert themes[0]["theme_name"] == "甜宠逆袭"
        assert themes[0]["mention_count"] == 1

    def test_upsert_existing_theme_increments(self, db):
        db.upsert_theme("甜宠", platform="hongguo", heat_score=80, trend_direction="stable")
        db.upsert_theme("甜宠", platform="hongguo", heat_score=90, trend_direction="rising")
        themes = db.get_hot_themes(limit=10)
        found = [t for t in themes if t["theme_name"] == "甜宠"]
        assert len(found) == 1
        assert found[0]["mention_count"] == 2
        assert float(found[0]["heat_score"]) == 90.0

    def test_cold_topics(self, db):
        db.upsert_theme("冷门A", platform="hongguo", heat_score=30, trend_direction="rising")
        db.upsert_theme("冷门A", platform="hongguo", heat_score=35, trend_direction="rising")
        db.upsert_theme("热门B", platform="hongguo", heat_score=90, trend_direction="stable")
        db.upsert_theme("热门B", platform="hongguo", heat_score=92, trend_direction="stable")
        cold = db.get_cold_topics(limit=10)
        assert len(cold) >= 1
        names = {t["theme_name"] for t in cold}
        assert "冷门A" in names

    def test_platform_stats(self, db):
        db.insert_crawl_log(platform="hongguo", title="A", rank=1)
        db.insert_crawl_log(platform="hongguo", title="B", rank=2)
        db.insert_crawl_log(platform="kuai", title="C", rank=1)
        stats = db.get_platform_stats()
        platforms = {s["platform"] for s in stats}
        assert "hongguo" in platforms
        assert "kuai" in platforms

    def test_theme_trend(self, db):
        db.upsert_theme("甜宠", platform="hongguo", heat_score=80, trend_direction="rising")
        trend = db.get_theme_trend("甜宠", months=12)
        assert len(trend) >= 1
        assert trend[0]["theme_name"] == "甜宠"

    def test_theme_trend_nonexistent(self, db):
        trend = db.get_theme_trend("不存在主题", months=6)
        assert trend == []

    def test_crawl_logs_pagination(self, db):
        for i in range(5):
            db.insert_crawl_log(platform="hongguo", title=f"剧{i}", rank=i + 1)
        page = db.get_crawl_logs(limit=2, offset=1)
        assert len(page) == 2
