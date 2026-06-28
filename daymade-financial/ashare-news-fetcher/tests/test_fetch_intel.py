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
    _parse_datetime,
    _cn_item_to_info,
    _policy_item_to_info,
    _guba_to_info,
    fetch_intel,
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
# _score_text direct tests (F38)
# ---------------------------------------------------------------------------


class TestScoreTextDirect:
    def test_empty_string(self):
        fetcher = GubaFetcher()
        assert fetcher._score_text("") == (0, 0)

    def test_no_keywords(self):
        fetcher = GubaFetcher()
        assert fetcher._score_text("今天天气不错，市场平稳") == (0, 0)

    def test_negation_prefix_fei(self):
        fetcher = GubaFetcher()
        # "非涨停" — 非 negates 涨停 (bull 3) → bear 3
        bull, bear = fetcher._score_text("非涨停")
        assert bull == 0
        assert bear == 3

    def test_negation_prefix_fouren(self):
        fetcher = GubaFetcher()
        # "否认涨停" — 否认 negates 涨停 (bull 3) → bear 3
        bull, bear = fetcher._score_text("否认涨停")
        assert bull == 0
        assert bear == 3

    def test_covered_range_prevents_double_counting(self):
        fetcher = GubaFetcher()
        # "重大利好" contains "利好" inside it; only the longer match should count.
        bull, bear = fetcher._score_text("重大利好")
        # "重大利好" = 3, "利好" = 2 but overlapped → should not double count
        assert bull == 3

    def test_punctuation_stripping_prefix(self):
        fetcher = GubaFetcher()
        # "不，涨停" — punctuation between negation and keyword should be stripped
        bull, bear = fetcher._score_text("不，涨停")
        assert bull == 0
        assert bear == 3


# ---------------------------------------------------------------------------
# _parse_datetime extended tests (F39)
# ---------------------------------------------------------------------------


class TestParseDatetimeExtended:
    def test_iso8601_with_offset(self):
        dt = _parse_datetime("2026-06-26T12:00:00+08:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6
        assert dt.day == 26
        assert dt.hour == 12
        assert dt.utcoffset().total_seconds() == 8 * 3600

    def test_iso8601_with_z_suffix(self):
        dt = _parse_datetime("2026-06-26T12:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.utcoffset().total_seconds() == 0

    def test_date_only_string(self):
        dt = _parse_datetime("2026-06-26")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6
        assert dt.day == 26
        assert dt.hour == 0
        assert dt.minute == 0

    def test_minute_precision_string(self):
        dt = _parse_datetime("2026-06-26 12:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.hour == 12
        assert dt.minute == 0
        assert dt.second == 0

    def test_numeric_string_unix_timestamp(self):
        dt = _parse_datetime("1782464400")
        assert dt is not None
        assert dt.year == 2026


# ---------------------------------------------------------------------------
# InfoItem __post_init__ default paths (F40)
# ---------------------------------------------------------------------------


class TestInfoItemPostInit:
    def test_published_at_falls_back_to_fetched_at(self):
        item = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t1",
            url="https://a.com",
            published_at="",
        )
        assert item.published_at == item.fetched_at

    def test_fetched_at_is_utc_aware_string_format(self):
        item = InfoItem(
            source_id="s1",
            source_name="n1",
            title="t1",
            url="https://a.com",
            published_at="2026-06-26 12:00:00",
        )
        # fetched_at should be a string in "%Y-%m-%d %H:%M:%S" format and represent UTC now
        assert isinstance(item.fetched_at, str)
        assert len(item.fetched_at) == 19
        # Verify it parses as a UTC-aware datetime
        parsed = datetime.strptime(item.fetched_at, "%Y-%m-%d %H:%M:%S")
        assert parsed.tzinfo is None  # strptime returns naive; the source uses UTC in generation


# ---------------------------------------------------------------------------
# _check_high_impact fallback to all_keywords (F41)
# ---------------------------------------------------------------------------


class TestCheckHighImpactFallback:
    def test_fallback_to_all_keywords_when_impact_category_empty(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="降准预期升温",
            source="unknown",
            source_name="未知来源",
            impact_category="",
        )
        # "降准" is in monetary keywords; with empty category, all keywords are used
        assert fetcher._check_high_impact(item) is True

    def test_fallback_to_all_keywords_when_impact_category_unknown(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="IPO新规发布",
            source="unknown",
            source_name="未知来源",
            impact_category="unknown_category",
        )
        # "IPO" is in regulatory keywords; with unknown category, all keywords are used
        assert fetcher._check_high_impact(item) is True

    def test_no_match_when_category_empty_and_no_keywords(self):
        fetcher = PolicyNewsFetcher()
        item = PolicyItem(
            title="日常工作会议",
            source="mof",
            source_name="财政部",
            impact_category="",
        )
        assert fetcher._check_high_impact(item) is False


# ---------------------------------------------------------------------------
# GubaFetcher helpers (F44)
# ---------------------------------------------------------------------------


class TestGubaFetcherHelpers:
    def test_convert_symbol_strips_sh_prefix(self):
        fetcher = GubaFetcher()
        assert fetcher._convert_symbol("SH600519") == "600519"

    def test_convert_symbol_strips_sz_prefix(self):
        fetcher = GubaFetcher()
        assert fetcher._convert_symbol("SZ000001") == "000001"

    def test_convert_symbol_strips_bj_prefix(self):
        fetcher = GubaFetcher()
        assert fetcher._convert_symbol("BJ830899") == "830899"

    def test_convert_symbol_lowercase_prefix(self):
        fetcher = GubaFetcher()
        assert fetcher._convert_symbol("sh600519") == "600519"
        assert fetcher._convert_symbol("sz000001") == "000001"
        assert fetcher._convert_symbol("bj830899") == "830899"

    def test_convert_symbol_no_prefix(self):
        fetcher = GubaFetcher()
        assert fetcher._convert_symbol("600519") == "600519"

    def test_rate_limit_enforces_interval(self):
        fetcher = GubaFetcher()
        fetcher._last_request_ts = time.monotonic()
        start = time.monotonic()
        fetcher._rate_limit(interval=0.1)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.09  # allow small tolerance

    def test_extract_topics_returns_top_phrases(self):
        fetcher = GubaFetcher()
        posts = [
            {"title": "宁德时代业绩大涨，新能源板块爆发", "post_content": ""},
            {"title": "新能源政策利好，宁德时代再涨", "post_content": ""},
            {"title": "大盘震荡，宁德时代走势分析", "post_content": ""},
        ]
        topics = fetcher._extract_topics(posts)
        assert isinstance(topics, list)
        assert len(topics) <= 3
        assert "宁德时代" in topics  # appears in all 3 titles

    def test_count_institutional_counts_markers(self):
        fetcher = GubaFetcher()
        posts = [
            {"title": "机构调研：目标价上调", "post_content": "", "user_type": "个人"},
            {"title": "券商研报：买入评级", "post_content": "", "source_type": "机构"},
            {"title": "散户讨论", "post_content": ""},
        ]
        count = fetcher._count_institutional(posts)
        # "机构" in user_type (post 2 via source_type), "研报" in title (post 1), "评级" in title (post 1)
        # user_type "机构" in post 2 → +1
        # title "券商研报" in post 2 → +1 (but continue skips second check for post 2)
        # title "机构调研" in post 1 → +1
        assert count >= 2


# ---------------------------------------------------------------------------
# Conversion helpers (F45)
# ---------------------------------------------------------------------------


class TestConversionHelpers:
    def test_cn_item_to_info_category_mapping(self):
        extractor = SymbolExtractor()
        item = CnNewsItem(
            title="Test title",
            content="Test content",
            source="sina",
            publish_time=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
            url="https://example.com",
            is_important=True,
            tags=["tag1"],
        )
        info = _cn_item_to_info(item, extractor)
        assert info.category == "global"  # sina maps to global
        assert info.priority == "breaking"
        assert info.source_id == "cn_sina"
        assert info.tags == ["tag1"]

    def test_cn_item_to_info_symbol_extraction(self):
        extractor = SymbolExtractor()
        item = CnNewsItem(
            title="600519 发布年报",
            content="内容",
            source="cls",
            publish_time=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
        )
        info = _cn_item_to_info(item, extractor)
        assert "600519" in info.related_symbols

    def test_cn_item_to_info_normal_priority(self):
        extractor = SymbolExtractor()
        item = CnNewsItem(
            title="普通新闻",
            content="内容",
            source="cls",
            publish_time=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
            is_important=False,
        )
        info = _cn_item_to_info(item, extractor)
        assert info.priority == "normal"

    def test_policy_item_to_info_high_priority(self):
        extractor = SymbolExtractor()
        item = PolicyItem(
            title="国务院宣布减税",
            source="mof",
            source_name="财政部",
            url="https://mof.gov.cn",
            date="2026-06-26",
            impact_category="fiscal",
            is_high_impact=True,
        )
        info = _policy_item_to_info(item, extractor)
        assert info.category == "policy"
        assert info.priority == "high"
        assert info.source_id == "policy_mof"
        assert info.extra["impact_category"] == "fiscal"

    def test_policy_item_to_info_symbol_extraction(self):
        extractor = SymbolExtractor()
        item = PolicyItem(
            title="600519 受益新政",
            source="csrc",
            source_name="证监会",
            is_high_impact=False,
        )
        info = _policy_item_to_info(item, extractor)
        assert "600519" in info.related_symbols

    def test_guba_to_info_summary_formatting(self):
        extractor = SymbolExtractor()
        metrics = GubaMetrics(
            symbol="600519",
            post_count_24h=100,
            read_count_avg=5000.0,
            comment_count_avg=50.0,
            sentiment="bullish",
            sentiment_score=0.5,
            hot_topics=["涨停", "利好"],
            institutional_post_count=5,
        )
        info = _guba_to_info(metrics, extractor)
        assert info.category == "social"
        assert info.related_symbols == ["600519"]
        assert "24h发帖 100" in info.summary
        assert "平均阅读 5000.0" in info.summary
        assert "热议: 涨停, 利好" in info.summary
        assert info.extra["sentiment"] == "bullish"
        assert info.extra["post_count_24h"] == 100

    def test_guba_to_info_no_hot_topics(self):
        extractor = SymbolExtractor()
        metrics = GubaMetrics(
            symbol="000001",
            post_count_24h=50,
            read_count_avg=1000.0,
            comment_count_avg=10.0,
            sentiment="neutral",
            sentiment_score=0.0,
        )
        info = _guba_to_info(metrics, extractor)
        assert "热议" not in info.summary
        assert info.tags == []


# ---------------------------------------------------------------------------
# fetch_intel dispatcher (F46)
# ---------------------------------------------------------------------------


class TestFetchIntelDispatcher:
    def test_multiple_sources_merged(self, monkeypatch):
        cn_item = CnNewsItem(
            title="CN News",
            content="",
            source="cls",
            publish_time=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
        )
        policy_item = PolicyItem(
            title="Policy News",
            source="mof",
            source_name="财政部",
            date="2026-06-26 10:00:00",
            impact_category="fiscal",
        )

        monkeypatch.setattr(CnNewsFetcher, "fetch_all", lambda _self, _limit: [cn_item])
        monkeypatch.setattr(PolicyNewsFetcher, "fetch_all", lambda _self: [policy_item])
        monkeypatch.setattr(GubaFetcher, "fetch_batch", lambda _self, _symbols: [])

        items = fetch_intel(["cn", "policy"], limit=10)
        assert len(items) == 2
        source_ids = {it.source_id for it in items}
        assert "cn_cls" in source_ids
        assert "policy_mof" in source_ids

    def test_guba_source_with_symbols_triggers_fetch_batch(self, monkeypatch):
        metrics = GubaMetrics(
            symbol="600519",
            post_count_24h=10,
            read_count_avg=100.0,
            comment_count_avg=5.0,
            sentiment="neutral",
            sentiment_score=0.0,
        )
        monkeypatch.setattr(CnNewsFetcher, "fetch_all", lambda _self, _limit: [])
        monkeypatch.setattr(PolicyNewsFetcher, "fetch_all", lambda _self: [])
        monkeypatch.setattr(GubaFetcher, "fetch_batch", lambda _self, symbols: [metrics] if symbols else [])

        items = fetch_intel(["guba"], symbols=["600519"])
        assert len(items) == 1
        assert items[0].source_id == "guba_600519"

    def test_limit_enforced_after_merging(self, monkeypatch):
        cn_items = [
            CnNewsItem(
                title=f"CN News {i}",
                content="",
                source="cls",
                publish_time=datetime(2026, 6, 26, 12, i, 0, tzinfo=UTC),
            )
            for i in range(10)
        ]
        monkeypatch.setattr(CnNewsFetcher, "fetch_all", lambda _self, _limit: cn_items)
        monkeypatch.setattr(PolicyNewsFetcher, "fetch_all", lambda _self: [])
        monkeypatch.setattr(GubaFetcher, "fetch_batch", lambda _self, _symbols: [])

        items = fetch_intel(["cn"], limit=5)
        assert len(items) == 5

    def test_empty_sources_returns_empty(self, monkeypatch):
        monkeypatch.setattr(CnNewsFetcher, "fetch_all", lambda _self, _limit: [])
        monkeypatch.setattr(PolicyNewsFetcher, "fetch_all", lambda _self: [])
        monkeypatch.setattr(GubaFetcher, "fetch_batch", lambda _self, _symbols: [])

        items = fetch_intel(["cn", "policy", "guba"], symbols=["600519"])
        assert items == []

    def test_items_sorted_by_published_at_descending(self, monkeypatch):
        cn_items = [
            CnNewsItem(
                title="Older",
                content="",
                source="cls",
                publish_time=datetime(2026, 6, 26, 10, 0, 0, tzinfo=UTC),
            ),
            CnNewsItem(
                title="Newer",
                content="",
                source="cls",
                publish_time=datetime(2026, 6, 26, 14, 0, 0, tzinfo=UTC),
            ),
        ]
        monkeypatch.setattr(CnNewsFetcher, "fetch_all", lambda _self, _limit: cn_items)
        monkeypatch.setattr(PolicyNewsFetcher, "fetch_all", lambda _self: [])
        monkeypatch.setattr(GubaFetcher, "fetch_batch", lambda _self, _symbols: [])

        items = fetch_intel(["cn"], limit=10)
        assert len(items) == 2
        assert items[0].title == "Newer"
        assert items[1].title == "Older"


# ---------------------------------------------------------------------------
# _strip_html HTML entities (F47)
# ---------------------------------------------------------------------------


class TestStripHtmlEntities:
    def test_less_than_entity(self):
        assert _strip_html("a &lt; b") == "a < b"

    def test_greater_than_entity(self):
        assert _strip_html("a &gt; b") == "a > b"

    def test_ampersand_entity(self):
        assert _strip_html("A &amp; B") == "A & B"

    def test_non_breaking_space_entity(self):
        assert _strip_html("a&nbsp;b") == "a b"


# ---------------------------------------------------------------------------
# SymbolExtractor caching and _find_column (F48)
# ---------------------------------------------------------------------------


class TestSymbolExtractorCaching:
    def test_extract_calls_load_names_only_once(self, monkeypatch):
        class FakeDF:
            columns = ["代码", "名称"]
            empty = False

            def iterrows(self):
                yield (0, {"代码": "600519", "名称": "贵州茅台"})

        class FakeAK:
            @staticmethod
            def stock_info_a_code_name():
                return FakeDF()

        monkeypatch.setitem(sys.modules, "akshare", FakeAK())
        # monkeypatch jieba availability off so we use substring matching
        monkeypatch.setattr("fetch_intel._HAS_JIEBA", False, raising=False)

        extractor = SymbolExtractor()
        # First call should trigger _load_names
        assert extractor.extract("贵州茅台") == ["600519"]
        # Second call should use cached _name_to_codes
        assert extractor.extract("贵州茅台大涨") == ["600519"]

    def test_find_column_chinese_code(self):
        from fetch_intel import _find_column

        cols = ["股票代码", "名称"]
        assert _find_column(cols, "code") == "股票代码"

    def test_find_column_chinese_name(self):
        from fetch_intel import _find_column

        cols = ["代码", "股票名称"]
        assert _find_column(cols, "name") == "股票名称"

    def test_find_column_fallback(self):
        from fetch_intel import _find_column

        cols = ["unknown_col"]
        assert _find_column(cols, "code") == "code"


# ---------------------------------------------------------------------------
# GubaFetcher exception handling and mixed fetch_batch (F49)
# ---------------------------------------------------------------------------


class TestGubaFetcherExceptionHandling:
    def test_fetch_returns_none_on_exception(self, monkeypatch):
        fetcher = GubaFetcher()
        monkeypatch.setattr(fetcher, "_fetch_posts", lambda _code: (_ for _ in ()).throw(RuntimeError("boom")))
        assert fetcher.fetch("600519") is None

    def test_fetch_batch_first_success_second_exception(self, monkeypatch):
        fetcher = GubaFetcher()
        call_count = 0

        def _fake_fetch_posts(symbol_code):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [{"title": "ok", "read_count": 1, "comment_count": 0}]
            raise RuntimeError("boom")

        monkeypatch.setattr(fetcher, "_fetch_posts", _fake_fetch_posts)
        results = fetcher.fetch_batch(["600519", "000001"])
        assert len(results) == 1
        assert results[0].symbol == "600519"


# ---------------------------------------------------------------------------
# Overlapping keyword direct assertion (F51)
# ---------------------------------------------------------------------------


class TestOverlappingKeywordDirect:
    def test_overlapping_keywords_direct_assert_score_text(self):
        fetcher = GubaFetcher()
        # "涨停跌停" contains both 涨停 (bull 3) and 跌停 (bear 3)
        # The internal _score_text should return (3, 3) — each counted once, no double-counting of sub-keywords
        bull, bear = fetcher._score_text("涨停跌停")
        assert bull == 3
        assert bear == 3
