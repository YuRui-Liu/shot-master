"""SQLite 管理器：crawl_logs / analyses / theme_index 三表。
线程安全：WAL 模式 + check_same_thread=False。
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS crawl_logs (
    crawl_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT    NOT NULL,
    source_url  TEXT    NOT NULL DEFAULT '',
    title       TEXT    NOT NULL DEFAULT '',
    rank        INTEGER NOT NULL DEFAULT 0,
    raw_json    TEXT    NOT NULL DEFAULT '{}',
    meta_json   TEXT    NOT NULL DEFAULT '{}',
    crawled_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_id        INTEGER NOT NULL,
    report_json     TEXT    NOT NULL DEFAULT '{}',
    hot_themes_json TEXT    NOT NULL DEFAULT '[]',
    cold_topics_json TEXT   NOT NULL DEFAULT '[]',
    market_summary  TEXT    NOT NULL DEFAULT '',
    generated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (crawl_id) REFERENCES crawl_logs(crawl_id)
);

CREATE TABLE IF NOT EXISTS theme_index (
    theme_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    theme_name     TEXT    NOT NULL,
    platform       TEXT    NOT NULL DEFAULT '',
    first_seen     TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen      TEXT    NOT NULL DEFAULT (datetime('now')),
    mention_count  INTEGER NOT NULL DEFAULT 1,
    trend_direction TEXT   NOT NULL DEFAULT 'stable',
    heat_score     REAL    NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_crawl_logs_platform   ON crawl_logs(platform);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_crawled_at   ON crawl_logs(crawled_at);
CREATE INDEX IF NOT EXISTS idx_analyses_crawl_id       ON analyses(crawl_id);
CREATE INDEX IF NOT EXISTS idx_theme_index_theme_name  ON theme_index(theme_name);
CREATE INDEX IF NOT EXISTS idx_theme_index_platform    ON theme_index(platform);
"""


class MarketDB:
    """SQLite 数据库管理器。"""

    def __init__(self, db_path: str | Path = ""):
        if not db_path:
            db_path = Path(__file__).resolve().parent.parent / "db" / "market_intel.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库连接 + 建表。"""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        self._conn = conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        """获取游标上下文管理器。"""
        assert self._conn is not None
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    # ------------------------------------------------------------------ crawl_logs

    def insert_crawl_log(self, platform: str, source_url: str = "",
                         title: str = "", rank: int = 0,
                         raw_json: dict | None = None,
                         meta_json: dict | None = None,
                         crawled_at: str = "") -> int:
        if not crawled_at:
            crawled_at = datetime.now(timezone.utc).isoformat()
        raw_s = json.dumps(raw_json or {}, ensure_ascii=False)
        meta_s = json.dumps(meta_json or {}, ensure_ascii=False)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO crawl_logs(platform, source_url, title, rank, "
                "raw_json, meta_json, crawled_at) VALUES (?,?,?,?,?,?,?)",
                (platform, source_url, title, rank, raw_s, meta_s, crawled_at),
            )
            self._conn.commit()  # type: ignore[union-attr]
            return cur.lastrowid or 0

    def get_last_crawl_time(self, platform: str = "") -> Optional[str]:
        with self._cursor() as cur:
            if platform:
                cur.execute(
                    "SELECT MAX(crawled_at) FROM crawl_logs WHERE platform=?",
                    (platform,),
                )
            else:
                cur.execute("SELECT MAX(crawled_at) FROM crawl_logs")
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def get_crawl_count(self, platform: str = "", since_days: int = 0) -> int:
        with self._cursor() as cur:
            sql = "SELECT COUNT(*) FROM crawl_logs"
            params: tuple = ()
            conditions: list[str] = []
            if platform:
                conditions.append("platform=?")
                params = (platform,)
            if since_days > 0:
                conditions.append("crawled_at >= datetime('now', ?)")
                params = params + (f"-{since_days} days",)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else 0

    def get_crawl_logs(self, platform: str = "", limit: int = 100,
                       offset: int = 0) -> list[dict]:
        with self._cursor() as cur:
            sql = "SELECT * FROM crawl_logs"
            params: tuple = ()
            if platform:
                sql += " WHERE platform=?"
                params = (platform,)
            sql += " ORDER BY crawled_at DESC LIMIT ? OFFSET ?"
            cur.execute(sql, params + (limit, offset))
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------ analyses

    def insert_analysis(self, crawl_id: int, report_json: dict | None = None,
                        hot_themes_json: list | None = None,
                        cold_topics_json: list | None = None,
                        market_summary: str = "",
                        generated_at: str = "") -> int:
        if not generated_at:
            generated_at = datetime.now(timezone.utc).isoformat()
        report_s = json.dumps(report_json or {}, ensure_ascii=False)
        hot_s = json.dumps(hot_themes_json or [], ensure_ascii=False)
        cold_s = json.dumps(cold_topics_json or [], ensure_ascii=False)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO analyses(crawl_id, report_json, hot_themes_json, "
                "cold_topics_json, market_summary, generated_at) "
                "VALUES (?,?,?,?,?,?)",
                (crawl_id, report_s, hot_s, cold_s, market_summary, generated_at),
            )
            self._conn.commit()  # type: ignore[union-attr]
            return cur.lastrowid or 0

    def get_latest_analysis(self) -> dict | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM analyses ORDER BY generated_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_analyses(self, limit: int = 20, offset: int = 0) -> list[dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM analyses ORDER BY generated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------ theme_index

    def upsert_theme(self, theme_name: str, platform: str = "",
                     heat_score: float = 0.0,
                     trend_direction: str = "stable") -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._cursor() as cur:
            cur.execute(
                "SELECT theme_id, mention_count FROM theme_index "
                "WHERE theme_name=? AND platform=?",
                (theme_name, platform),
            )
            row = cur.fetchone()
            if row:
                new_count = int(row["mention_count"]) + 1
                cur.execute(
                    "UPDATE theme_index SET last_seen=?, mention_count=?, "
                    "heat_score=?, trend_direction=? WHERE theme_id=?",
                    (now, new_count, heat_score, trend_direction, row["theme_id"]),
                )
                self._conn.commit()  # type: ignore[union-attr]
                return row["theme_id"]
            else:
                cur.execute(
                    "INSERT INTO theme_index(theme_name, platform, first_seen, "
                    "last_seen, mention_count, heat_score, trend_direction) "
                    "VALUES (?,?,?,?,1,?,?)",
                    (theme_name, platform, now, now, heat_score, trend_direction),
                )
                self._conn.commit()  # type: ignore[union-attr]
                return cur.lastrowid or 0

    def get_hot_themes(self, limit: int = 10, days: int = 7,
                       platform: str = "") -> list[dict]:
        with self._cursor() as cur:
            sql = ("SELECT * FROM theme_index "
                   "WHERE last_seen >= datetime('now', ?)")
            params: tuple = (f"-{days} days",)
            if platform:
                sql += " AND platform=?"
                params = params + (platform,)
            sql += " ORDER BY heat_score DESC LIMIT ?"
            cur.execute(sql, params + (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_cold_topics(self, limit: int = 6, platform: str = "") -> list[dict]:
        """冷门机会：mention_count 低但最近出现、heat_score 在上升通道的主题。"""
        with self._cursor() as cur:
            sql = ("SELECT * FROM theme_index "
                   "WHERE last_seen >= datetime('now', '-30 days') "
                   "AND trend_direction IN ('rising','stable')")
            params: tuple = ()
            if platform:
                sql += " AND platform=?"
                params = (platform,)
            sql += " ORDER BY mention_count ASC, heat_score DESC LIMIT ?"
            cur.execute(sql, params + (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_platform_stats(self) -> list[dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT platform, COUNT(*) as entry_count, "
                "MAX(crawled_at) as last_crawl "
                "FROM crawl_logs GROUP BY platform"
            )
            return [dict(r) for r in cur.fetchall()]

    def get_theme_trend(self, theme_name: str, months: int = 6) -> list[dict]:
        """返回某主题按月的提及趋势（基于 theme_index 的 last_seen/mention_count）。"""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM theme_index WHERE theme_name=? "
                "AND last_seen >= datetime('now', ?)",
                (theme_name, f"-{months} months"),
            )
            rows = cur.fetchall()
            if not rows:
                return []
            return [dict(r) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
