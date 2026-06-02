"""LLM 分析器：加载 prompt 模板 + 喂爬取结果 → 结构化 JSON。

复用 screenwriter_agent 的 OpenAI 兼容 LLM 调用方式（api_key/base_url/model 从 cfg 取）。
支持 monkeypatch（_raw_stream 可替换）便于测试。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "analyze.md"


def _load_template() -> str:
    """加载分析 prompt 模板。"""
    if _TEMPLATE_PATH.is_file():
        return _TEMPLATE_PATH.read_text(encoding="utf-8")
    logger.warning("analyze.md not found at %s, using built-in fallback", _TEMPLATE_PATH)
    return (
        "# Role\n你是短剧市场分析师。\n"
        "# Task\n分析下方爬虫数据，返回 JSON。\n"
        "# Input Data\n{{crawl_data}}\n"
    )


class MarketAnalyzer:
    """LLM 驱动的市场分析器。"""

    def __init__(self, api_key: str, base_url: str, model: str,
                 temperature: float = 0.3, max_tokens: int = 4096,
                 timeout: float = 300.0):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _raw_call(self, messages: list[dict]) -> str:
        """调用 LLM 非流式返回全文。可 monkeypatch 用于测试。"""
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                        timeout=self.timeout)
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content or ""

    def analyze(self, crawl_data: list[dict]) -> dict[str, Any]:
        """喂爬虫结果给 LLM，返回结构化 JSON 分析报告。

        Args:
            crawl_data: 爬虫解析后的条目列表 [{title, rank, meta}, ...]。

        Returns:
            dict: 包含 market_summary, hot_themes, cold_topics,
                  genre_distribution, platform_stats。
        """
        template = _load_template()
        data_text = json.dumps(crawl_data, ensure_ascii=False, indent=2)
        prompt = template.replace("{{crawl_data}}", data_text)

        messages = [
            {"role": "system", "content": "你是一个专业的短剧市场分析师。请用中文回复。"},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = self._raw_call(messages)
            return self._parse_response(raw)
        except Exception as exc:
            logger.error("LLM analysis failed: %s", exc)
            return self._fallback_result(str(exc))

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """解析 LLM 返回的 JSON（清理可能的 markdown 包裹）。"""
        text = raw.strip()
        # 去可能的前后 markdown 代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("JSON parse failed, raw: %.200s...", raw)
            return self._fallback_result("JSON parse error")

    @staticmethod
    def _fallback_result(error_msg: str = "") -> dict[str, Any]:
        return {
            "market_summary": f"分析暂时不可用（{error_msg}），请稍后重试。",
            "hot_themes": [],
            "cold_topics": [],
            "genre_distribution": {},
            "platform_stats": {},
        }
