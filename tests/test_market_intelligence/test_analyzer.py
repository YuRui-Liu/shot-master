"""monkeypatch LLM 验证 prompt→JSON 解析链路。零网络。"""
from __future__ import annotations

import json

import pytest

from market_intelligence.analyzer import MarketAnalyzer


_FAKE_LLM_RESPONSE = json.dumps({
    "market_summary": "当前短剧市场以甜宠和逆袭为主流，科幻题材供给不足但增长迅速。",
    "hot_themes": [
        {"name": "甜宠霸总", "heat": 95, "freq": 28, "trend": "stable"},
        {"name": "赘婿逆袭", "heat": 88, "freq": 22, "trend": "rising"},
        {"name": "虐恋重生", "heat": 80, "freq": 18, "trend": "declining"},
    ],
    "cold_topics": [
        {"name": "科幻悬疑短剧", "rising_speed": 75, "supply_gap": "当前供给极少，但受众增长快"},
        {"name": "女性职场", "rising_speed": 60, "supply_gap": "蓝海品类，竞争少"},
    ],
    "genre_distribution": {
        "甜宠": 35,
        "逆袭": 25,
        "虐恋": 15,
        "悬疑": 10,
        "古装": 8,
        "都市": 5,
        "科幻": 2,
    },
    "platform_stats": {
        "hongguo": {"total": 50, "top3_concentration": 0.4},
    },
}, ensure_ascii=False)


@pytest.fixture
def analyzer():
    return MarketAnalyzer(
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model="test-model",
    )


class TestAnalyzerBasic:

    def test_parse_valid_json(self, analyzer, monkeypatch):
        monkeypatch.setattr(analyzer, "_raw_call",
                            lambda messages: _FAKE_LLM_RESPONSE)
        result = analyzer.analyze([{"title": "测试剧", "rank": 1, "meta": {}}])
        assert result["market_summary"].startswith("当前短剧市场")
        assert len(result["hot_themes"]) == 3
        assert len(result["cold_topics"]) == 2
        assert "甜宠" in result["genre_distribution"]

    def test_parse_json_with_markdown_fence(self, analyzer, monkeypatch):
        fenced = "```json\n" + _FAKE_LLM_RESPONSE + "\n```"
        monkeypatch.setattr(analyzer, "_raw_call", lambda messages: fenced)
        result = analyzer.analyze([])
        assert len(result["hot_themes"]) == 3

    def test_fallback_on_llm_error(self, analyzer, monkeypatch):
        def _fail(messages):
            raise RuntimeError("模拟 LLM 不可用")
        monkeypatch.setattr(analyzer, "_raw_call", _fail)
        result = analyzer.analyze([{"title": "X", "rank": 1, "meta": {}}])
        assert "暂时不可用" in result["market_summary"]
        assert result["hot_themes"] == []

    def test_fallback_on_bad_json(self, analyzer, monkeypatch):
        monkeypatch.setattr(analyzer, "_raw_call",
                            lambda messages: "这不是合法的 JSON 格式")
        result = analyzer.analyze([])
        assert "JSON parse error" in result["market_summary"]
        assert result["hot_themes"] == []

    def test_hot_themes_fields(self, analyzer, monkeypatch):
        monkeypatch.setattr(analyzer, "_raw_call",
                            lambda messages: _FAKE_LLM_RESPONSE)
        result = analyzer.analyze([])
        for theme in result["hot_themes"]:
            assert "name" in theme
            assert "heat" in theme
            assert "freq" in theme
            assert "trend" in theme
            assert 0 <= theme["heat"] <= 100

    def test_cold_topics_fields(self, analyzer, monkeypatch):
        monkeypatch.setattr(analyzer, "_raw_call",
                            lambda messages: _FAKE_LLM_RESPONSE)
        result = analyzer.analyze([])
        for topic in result["cold_topics"]:
            assert "name" in topic
            assert "rising_speed" in topic
            assert "supply_gap" in topic
            assert 0 <= topic["rising_speed"] <= 100

    def test_genre_distribution_is_dict(self, analyzer, monkeypatch):
        monkeypatch.setattr(analyzer, "_raw_call",
                            lambda messages: _FAKE_LLM_RESPONSE)
        result = analyzer.analyze([])
        assert isinstance(result["genre_distribution"], dict)
        total_pct = sum(result["genre_distribution"].values())
        assert total_pct > 0


class TestTemplateLoading:

    def test_fallback_template_used_when_file_missing(self, monkeypatch):
        """如果模板文件不存在，使用内置 fallback。"""
        # 强制让 _TEMPLATE_PATH 指向不存在的路径
        import market_intelligence.analyzer as am
        monkeypatch.setattr(am, "_TEMPLATE_PATH",
                            am.Path("/nonexistent/template.md"))
        # 重新加载 _load_template（因为模块级已加载过）
        template = am._load_template()
        assert "{{crawl_data}}" in template
