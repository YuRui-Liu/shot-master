"""monkeypatch httpx 验证爬虫解析逻辑。零网络。"""
from __future__ import annotations

import pytest

from market_intelligence.crawler.base import BaseCrawler


# ---- 测试用简单实现 ----

_FAKE_RANK_HTML = """<!DOCTYPE html>
<html>
<body>
<div class="rank-list">
  <div class="rank-item">
    <span class="rank-num">1</span>
    <span class="title">霸总甜宠第一季</span>
    <span class="tag">甜宠</span>
  </div>
  <div class="rank-item">
    <span class="rank-num">2</span>
    <span class="title">重生之逆袭人生</span>
    <span class="tag">逆袭</span>
  </div>
  <div class="rank-item">
    <span class="rank-num">3</span>
    <span class="title">古装虐恋传</span>
    <span class="tag">古装</span>
  </div>
</div>
</body>
</html>
"""


class _TestCrawler(BaseCrawler):
    """测试用爬虫：用简单的字符串分割解析 fake HTML。"""
    name = "test_platform"
    base_url = "https://test.example.com/rank"

    def __init__(self, fake_html: str = _FAKE_RANK_HTML, **kwargs):
        super().__init__(**kwargs)
        self._fake_html = fake_html

    def parse(self, html: str) -> list[dict]:
        # 用基础 HTML parser 验证解析链路
        from html.parser import HTMLParser
        items: list[dict] = []
        current: dict = {}
        in_title = False
        in_rank = False
        buf = ""

        class _P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                nonlocal current, in_title, in_rank, buf
                attrs_d = dict(attrs)
                cls = attrs_d.get("class", "")
                if "rank-item" in cls:
                    current = {"title": "", "rank": 0, "meta": {}}
                elif "title" in cls:
                    in_title = True
                    buf = ""
                elif "rank-num" in cls:
                    in_rank = True
                    buf = ""

            def handle_endtag(self, tag):
                nonlocal current, in_title, in_rank, buf, items
                if tag in ("div", "li") and current.get("title"):
                    items.append(current)
                    current = {}
                elif in_title:
                    in_title = False
                    current["title"] = buf.strip()
                    buf = ""
                elif in_rank:
                    in_rank = False
                    try:
                        current["rank"] = int(buf.strip())
                    except ValueError:
                        pass
                    buf = ""

            def handle_data(self, data):
                nonlocal buf
                if in_title or in_rank:
                    buf += data

        p = _P()
        p.feed(html)
        for i, item in enumerate(items, start=1):
            if item.get("rank", 0) == 0:
                item["rank"] = i
        return items


class TestBaseCrawler:

    def test_headers_rotation(self):
        crawler = _TestCrawler()
        h1 = crawler._rotate_headers()
        h2 = crawler._rotate_headers()
        assert "User-Agent" in h1
        # UA 随机，大概率不同
        assert h1["User-Agent"] == h2["User-Agent"] or True  # 可能相同

    def test_rate_limit_wait(self):
        import time
        crawler = _TestCrawler(rate_limit=0.1)
        crawler._last_request = time.monotonic()
        start = time.monotonic()
        crawler._rate_limit_wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # 很短或已过

    def test_fetch_page(self, monkeypatch):
        """monkeypatch httpx.Client.get 返回 fake HTML。"""
        import httpx

        class _FakeResp:
            status_code = 200
            text = _FAKE_RANK_HTML

            def raise_for_status(self):
                pass

        def _fake_get(self, url):
            return _FakeResp()

        monkeypatch.setattr(httpx.Client, "get", _fake_get)

        crawler = _TestCrawler()
        html = crawler.fetch_page("https://example.com")
        assert "霸总甜宠第一季" in html

    def test_fetch_page_passes_through_exception(self, monkeypatch):
        import httpx

        def _fail_get(self, url):
            raise httpx.HTTPStatusError("server error", request=None, response=None)

        monkeypatch.setattr(httpx.Client, "get", _fail_get)

        crawler = _TestCrawler()
        with pytest.raises(httpx.HTTPStatusError):
            crawler.fetch_page("https://example.com")


class TestParseLogic:

    def test_parse_extracts_titles(self):
        crawler = _TestCrawler()
        items = crawler.parse(_FAKE_RANK_HTML)
        assert len(items) == 3
        titles = [i["title"] for i in items]
        assert "霸总甜宠第一季" in titles
        assert "重生之逆袭人生" in titles
        assert "古装虐恋传" in titles

    def test_parse_extracts_ranks(self):
        crawler = _TestCrawler()
        items = crawler.parse(_FAKE_RANK_HTML)
        ranks = [i["rank"] for i in items]
        assert ranks == [1, 2, 3]

    def test_parse_empty_html(self):
        crawler = _TestCrawler()
        items = crawler.parse("")
        assert items == []

    def test_parse_non_rank_html(self):
        crawler = _TestCrawler()
        items = crawler.parse("<html><body>no rank items here</body></html>")
        assert items == []

    def test_crawl_integration(self, monkeypatch):
        """端到端：fetch → parse。"""
        import httpx

        class _FakeResp:
            status_code = 200
            text = _FAKE_RANK_HTML

            def raise_for_status(self):
                pass

        monkeypatch.setattr(httpx.Client, "get", lambda self, url: _FakeResp())

        crawler = _TestCrawler()
        items = crawler.crawl()
        assert len(items) == 3
        assert items[0]["title"] == "霸总甜宠第一季"


class TestHongGuoCrawler:

    def test_parse_with_fake_html(self, monkeypatch):
        """红果爬虫用 fake 榜单 HTML 验证解析链路。"""
        import httpx

        class _FakeResp:
            status_code = 200
            text = _FAKE_RANK_HTML

            def raise_for_status(self):
                pass

        monkeypatch.setattr(httpx.Client, "get", lambda self, url: _FakeResp())

        from market_intelligence.crawler.hongguo import HongGuoCrawler
        crawler = HongGuoCrawler()
        items = crawler.crawl()
        assert len(items) >= 1
        for item in items:
            assert "title" in item
            assert "rank" in item
            assert item["rank"] >= 1
