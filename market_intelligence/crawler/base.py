"""爬虫基类：httpx Client + 限速 + 反爬 UA 轮换。
子类覆盖 parse(html) → list[dict{title, rank, meta}]。
"""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx


# 反爬 UA 池
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]


class BaseCrawler(ABC):
    """爬虫基类。

    Attributes:
        name: 平台 id（如 "hongguo"）。
        base_url: 目标站首页/榜单页 URL。
        rate_limit: 两次请求最小间隔（秒）。
        timeout: httpx 请求超时（秒）。
    """

    name: str = ""
    base_url: str = ""

    def __init__(self, rate_limit: float = 2.0, timeout: float = 30.0):
        self.rate_limit = rate_limit
        self.timeout = timeout
        self._last_request: float = 0.0

    def _rotate_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;"
                      "q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def _rate_limit_wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

    def fetch_page(self, url: str = "") -> str:
        """请求页面，返回 HTML 文本。失败抛异常（由上层统一捕获）。"""
        target = url or self.base_url
        self._rate_limit_wait()
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True,
                              headers=self._rotate_headers()) as client:
                resp = client.get(target)
                resp.raise_for_status()
                return resp.text
        finally:
            self._last_request = time.monotonic()

    @abstractmethod
    def parse(self, html: str) -> list[dict[str, Any]]:
        """解析 HTML，返回结构化条目列表。

        Returns:
            list[dict]: 每项含 title(str), rank(int), meta(dict)。
        """
        ...

    def crawl(self, url: str = "") -> list[dict[str, Any]]:
        """完整爬取流程：fetch → parse。异常由调用方捕获。"""
        html = self.fetch_page(url)
        if not html or not html.strip():
            return []
        return self.parse(html)
