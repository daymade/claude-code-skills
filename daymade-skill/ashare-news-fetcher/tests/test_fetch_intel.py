"""Minimal pytest suite for fetch_intel.py — no live network calls."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


# Ensure the script directory is on the path so we can import internal names
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from fetch_intel import (  # noqa: E402
    CnNewsItem,
    InfoItem,
    SymbolExtractor,
    GubaFetcher,
    PolicyNewsFetcher,
    PolicyItem,
    _strip_html,
    _to_markdown,
)


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------


class TestSymbolExtractor:
    def test_shanghai_code(self):
        text = "600519 大涨，机构看好"
        extractor = SymbolExtractor()
        assert extractor.extract(text) == ["600519"]

    def test_shenzhen_code(self):
        text = "000002 万科发布年报"
        extractor = SymbolExtractor()
        assert extractor.extract(text) == ["000002"]

    def test_chinext_code(self):
        text = "300750 宁德时代定增"
        extractor = SymbolExtractor()
        assert extractor.extract(text) == ["300750"]

    def test_kcb_code(self):
        text = "688981 中芯国际财报"
        extractor = SymbolExtractor()
        assert extractor.extract(text) == ["688981"]

    def test_bse_code_not_matched_by_regex(self):
        # BSE (83xxxx) is not covered by the current regex; this test documents that.
        text = "830899 某北交所公司上市"
        extractor = SymbolExtractor()
        assert extractor.extract(text) == []

    def test_excludes_index_codes(self):
        text = "上证指数 000001 大跌，但个股 600519 上涨"
        extractor = SymbolExtractor()
        codes = extractor.extract(text)
        # 000001 is the 上证指数 index code and must be excluded
        assert "000001" not in codes
        assert "600519" in codes

    def test_multiple_codes_sorted(self):
        text = "600519 和 000002 以及 300750 齐涨"
        extractor = SymbolExtractor()
        assert extractor.extract(text) == ["000002", "300750", "600519"]

    def test_no_false_positive_13digit_timestamp(self):
        text = "时间戳 1776870300212 不代表股票"
        extractor = SymbolExtractor()
        assert extractor.extract(text) == []

    def test_extra_names_mapping(self):
        extractor = SymbolExtractor(extra_names={"600519": "贵州茅台"})
        text = "贵州茅台发布利好"
        assert extractor.extract(text) == ["600519"]

    def test_akshare_chinese_column_mapping(self, monkeypatch):
        class FakeDF:
            columns = ["代码", "名称"]
            empty = False

            def iterrows(self):
                yield (0, {"代码": "600519", "名称": "贵州茅台"})
                yield (1, {"代码": "000001", "名称": "平安银行"})

        class FakeAK:
            @staticmethod
            def stock_info_a_code_name():
                return FakeDF()

        monkeypatch.setitem(sys.modules, "akshare", FakeAK())
        extractor = SymbolExtractor()
        assert extractor.extract("贵州茅台大涨") == ["600519"]
        assert extractor.extract("平安银行财报") == ["000001"]


# ---------------------------------------------------------------------------
# Sentiment scoring
# ---------------------------------------------------------------------------


class TestSentimentScoring:
    def test_bullish_simple(self):
        fetcher = GubaFetcher()
        posts = [{"title": "涨停了，翻倍预期", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        assert sentiment == "bullish"
        assert score > 0.15

    def test_bearish_simple(self):
        fetcher = GubaFetcher()
        posts = [{"title": "跌停，暴雷了", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        assert sentiment == "bearish"
        assert score < -0.15

    def test_neutral_no_keywords(self):
        fetcher = GubaFetcher()
        posts = [{"title": "今天天气不错", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        assert sentiment == "neutral"
        assert score == 0.0

    def test_neutral_balanced(self):
        fetcher = GubaFetcher()
        posts = [{"title": "涨停但也跌停", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        # equal bull/bear weights → neutral
        assert sentiment == "neutral"
        assert score == 0.0

    def test_negation_flips_bull_to_bear(self):
        fetcher = GubaFetcher()
        posts = [{"title": "不涨停就废了", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        # "不" is a negation prefix before "涨停"
        assert sentiment == "bearish"

    def test_negation_flips_bear_to_bull(self):
        fetcher = GubaFetcher()
        posts = [{"title": "未跌停说明稳住", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        # "未" negates "跌停"
        assert sentiment == "bullish"

    def test_sentiment_score_bounds(self):
        fetcher = GubaFetcher()
        posts = [{"title": "涨停涨停涨停", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        assert sentiment == "bullish"
        assert -1.0 <= score <= 1.0

    def test_multi_char_negation(self):
        fetcher = GubaFetcher()
        posts = [{"title": "没有涨停", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        assert sentiment == "bearish"

    def test_negation_with_punctuation(self):
        fetcher = GubaFetcher()
        posts = [{"title": "不，涨停了", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        assert sentiment == "bearish"

    def test_multiple_occurrences_counted(self):
        fetcher = GubaFetcher()
        posts = [{"title": "涨停涨停", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        # Two occurrences of 涨停 (weight 3 each) → bullish and score above single occurrence.
        assert sentiment == "bullish"
        assert score > 0.15

    def test_overlapping_keywords_not_double_counted(self):
        fetcher = GubaFetcher()
        # "涨停" (bull 3) and "跌停" (bear 3) are adjacent; a naïve scan would also
        # count the sub-keyword "跌" (bear 1) inside "跌停", skewing toward bearish.
        posts = [{"title": "涨停跌停", "post_content": ""}]
        sentiment, score = fetcher._extract_sentiment(posts)
        assert sentiment == "neutral"
        assert score == 0.0


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_unix_seconds(self):
        from fetch_intel import _parse_datetime

        dt = _parse_datetime(1782464400)
        assert dt is not None
        assert dt.year == 2026

    def test_unix_milliseconds(self):
        from fetch_intel import _parse_datetime

        dt = _parse_datetime(1782464400000)
        assert dt is not None
        assert dt.year == 2026

    def test_formatted_string(self):
        from fetch_intel import _parse_datetime

        dt = _parse_datetime("2026-06-26 17:00:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.hour == 17

    def test_returns_utc_aware(self):
        from fetch_intel import _parse_datetime

        dt = _parse_datetime("2026-06-26 17:00:00")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 0

    def test_invalid_returns_none(self):
        from fetch_intel import _parse_datetime

        assert _parse_datetime("not-a-date") is None
        assert _parse_datetime("") is None


# ---------------------------------------------------------------------------
# InfoItem serialization
# ---------------------------------------------------------------------------


class TestInfoItem:
    def test_fields_present(self):
        item = InfoItem(
            source_id="cn_cls",
            source_name="cls",
            title="Test title",
            summary="summary",
            url="https://example.com",
            category="market",
            priority="normal",
            tags=["tag1"],
            related_symbols=["600519"],
            published_at="2026-06-26 12:00:00",
        )
        d = item.to_dict()
        assert d["source_id"] == "cn_cls"
        assert d["title"] == "Test title"
        assert d["related_symbols"] == ["600519"]
        assert "item_id" in d
        assert "fetched_at" in d

    def test_item_id_deterministic(self):
        item1 = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t1",
            url="https://a.com",
            published_at="2026-06-26 12:00:00",
        )
        item2 = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t1",
            url="https://a.com",
            published_at="2026-06-26 12:00:00",
        )
        assert item1.item_id == item2.item_id
        assert len(item1.item_id) == 16

    def test_item_id_changes_with_fields(self):
        item1 = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t1",
            url="https://a.com",
            published_at="2026-06-26 12:00:00",
        )
        item2 = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t2",
            url="https://a.com",
            published_at="2026-06-26 12:00:00",
        )
        assert item1.item_id != item2.item_id

    def test_item_id_includes_published_at(self):
        item1 = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t1",
            url="https://a.com",
            published_at="2026-06-26 12:00:00",
        )
        item2 = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t1",
            url="https://a.com",
            published_at="2026-06-26 13:00:00",
        )
        assert item1.item_id != item2.item_id

    def test_json_round_trip(self):
        item = InfoItem(
            source_id="cn_cls",
            source_name="cls",
            title="Test title",
            summary="summary",
            url="https://example.com",
            category="market",
            priority="normal",
            tags=["tag1"],
            related_symbols=["600519"],
            published_at="2026-06-26 12:00:00",
        )
        d = item.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        loaded = json.loads(json_str)
        assert loaded["item_id"] == item.item_id
        assert loaded["title"] == "Test title"
        assert loaded["related_symbols"] == ["600519"]


# ---------------------------------------------------------------------------
# Policy high-impact detection
# ---------------------------------------------------------------------------


class TestPolicyHighImpact:
    def test_fiscal_keyword_flags_high_impact(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="国务院宣布减税新政",
            source="mof",
            source_name="财政部",
            impact_category="fiscal",
        )
        assert fetcher._check_high_impact(item) is True

    def test_monetary_keyword_flags_high_impact(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="央行降准0.5个百分点",
            source="pboc",
            source_name="央行",
            impact_category="monetary",
        )
        assert fetcher._check_high_impact(item) is True

    def test_neutral_title_not_high_impact(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="财政部召开日常工作会议",
            source="mof",
            source_name="财政部",
            impact_category="fiscal",
        )
        assert fetcher._check_high_impact(item) is False

    def test_regulatory_keyword_flags_high_impact(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="证监会发布IPO新规",
            source="csrc",
            source_name="证监会",
            impact_category="regulatory",
        )
        assert fetcher._check_high_impact(item) is True

    def test_exchange_keyword_flags_high_impact(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="上交所调整停牌规则",
            source="sse",
            source_name="上交所",
            impact_category="exchange",
        )
        assert fetcher._check_high_impact(item) is True


class TestGubaFetcher:
    def test_fetch_returns_none_when_no_posts(self, monkeypatch):
        fetcher = GubaFetcher()
        monkeypatch.setattr(fetcher, "_fetch_posts", lambda _code: [])
        assert fetcher.fetch("600519") is None

    def test_fetch_batch_skips_none_results(self, monkeypatch):
        fetcher = GubaFetcher()
        monkeypatch.setattr(fetcher, "_fetch_posts", lambda _code: [])
        assert fetcher.fetch_batch(["600519", "000001"]) == []


# ---------------------------------------------------------------------------
# Keyword filtering
# ---------------------------------------------------------------------------


class TestKeywordFilter:
    def test_case_insensitive_filter(self, monkeypatch):
        from fetch_intel import CnNewsFetcher, fetch_intel

        fake_item = CnNewsItem(
            title="降准预期升温",
            content="",
            source="cls",
            publish_time=datetime.now(UTC),
        )
        monkeypatch.setattr(
            CnNewsFetcher, "fetch_all", lambda _self, _limit: [fake_item]
        )
        items = fetch_intel(["cn"], keywords=["jiangzhun"])
        assert len(items) == 0

        items = fetch_intel(["cn"], keywords=["降准"])
        assert len(items) == 1
        assert items[0].title == "降准预期升温"


# ---------------------------------------------------------------------------
# HTML strip helper
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<b>bold</b>") == "bold"

    def test_removes_multiple_tags(self):
        assert _strip_html("<p>hello <a href='x'>world</a></p>") == "hello world"

    def test_empty_string(self):
        assert _strip_html("") == ""


# ---------------------------------------------------------------------------
# Markdown output sanity
# ---------------------------------------------------------------------------


class TestToMarkdown:
    def test_contains_title(self):
        item = InfoItem(
            source_id="s1",
            source_name="n1",
            title="Market moves",
            summary="Summary text",
            url="https://example.com",
            category="market",
            priority="normal",
            related_symbols=["600519"],
            published_at="2026-06-26 12:00:00",
        )
        md = _to_markdown([item])
        assert "Market moves" in md
        assert "600519" in md
        assert "https://example.com" in md

    def test_empty_items(self):
        md = _to_markdown([])
        assert "A 股消息面情报" in md
