"""红果短剧爬虫：榜单页提取标题/排名/标签。

选择器为占位——待真机访问 hongguoduanju.com 后根据实际 DOM 调整。
"""
from __future__ import annotations

from typing import Any

from .base import BaseCrawler


class HongGuoCrawler(BaseCrawler):
    name = "hongguo"
    base_url = "https://www.hongguoduanju.com/rank"

    def parse(self, html: str) -> list[dict[str, Any]]:
        from html.parser import HTMLParser

        items: list[dict[str, Any]] = []

        class _RankParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self._in_item = False
                self._in_title = False
                self._in_rank = False
                self._current: dict[str, Any] = {}
                self._text_buf: str = ""

            def handle_starttag(self, tag, attrs):
                attrs_d = dict(attrs)
                cls = attrs_d.get("class", "")
                # TODO(真机调): 以下选择器为占位，需根据红果短剧真实 DOM 调整。
                # 预期结构：每个短剧卡片有 class="rank-item"，
                # 标题在 class="title" 内，排名在 class="rank-num" 内。
                if "rank-item" in cls or "drama-card" in cls:
                    self._in_item = True
                    self._current = {"title": "", "rank": 0, "meta": {}}
                elif self._in_item:
                    if "title" in cls or "drama-name" in cls:
                        self._in_title = True
                        self._text_buf = ""
                    elif "rank-num" in cls or "rank-index" in cls:
                        self._in_rank = True
                        self._text_buf = ""
                    elif "tag" in cls or "label" in cls:
                        self._text_buf = ""

            def handle_endtag(self, tag):
                if self._in_item and tag in ("div", "li", "article"):
                    if self._current.get("title"):
                        items.append(self._current)
                    self._in_item = False
                    self._current = {}
                    self._text_buf = ""
                elif self._in_title:
                    self._in_title = False
                    self._current["title"] = self._text_buf.strip()
                    self._text_buf = ""
                elif self._in_rank:
                    self._in_rank = False
                    try:
                        self._current["rank"] = int(self._text_buf.strip())
                    except ValueError:
                        pass
                    self._text_buf = ""

            def handle_data(self, data):
                if self._in_title or self._in_rank:
                    self._text_buf += data

        parser = _RankParser()
        parser.feed(html)
        # 填充 rank（未从 HTML 取到则按列表位置补）
        for i, item in enumerate(items, start=1):
            if item.get("rank", 0) == 0:
                item["rank"] = i
        return items
