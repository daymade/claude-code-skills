"""Network-mocked tests for fetch_intel.py fetchers.

These tests exercise the request/response paths without calling real upstream
servers by replacing ``_create_session`` with a fake session.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from fetch_intel import (  # noqa: E402
    CnNewsFetcher,
    PolicyNewsFetcher,
    _HAS_BS4,
    _POLICY_SOURCE_CONFIG,
)


def _single_source_config(source_id: str) -> dict:
    return {
        "sources": {source_id: _POLICY_SOURCE_CONFIG["sources"][source_id]},
        "high_impact_keywords": _POLICY_SOURCE_CONFIG["high_impact_keywords"],
    }


class FakeResponse:
    def __init__(
        self,
        json_data: dict | None = None,
        text: str = "",
        status_code: int = 200,
    ) -> None:
        self._json = json_data
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        if self._json is None:
            raise ValueError("no JSON")
        return self._json


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        if not self.responses:
            raise RuntimeError("unexpected request")
        return self.responses.pop(0)


@pytest.fixture
def patch_session(monkeypatch: pytest.MonkeyPatch):
    def _patch(responses: list[FakeResponse]) -> FakeSession:
        session = FakeSession(responses)
        monkeypatch.setattr("fetch_intel._create_session", lambda **kw: session)
        return session

    return _patch


# ---------------------------------------------------------------------------
# Policy sources
# ---------------------------------------------------------------------------


class TestPolicyNetwork:
    @pytest.mark.skipif(
        not _HAS_BS4, reason="beautifulsoup4 not installed"
    )
    def test_pboc_html_source(self, patch_session):
        html = """\
<html>
<body>
<table>
  <tr>
    <td><font class="newslist_style"><a href="/a/b/c.html">央行降准0.5个百分点</a></font><span class="hui12">2026-06-26</span></td>
  </tr>
  <tr>
    <td><font class="newslist_style"><a href="/a/b/d.html">央行召开例会</a></font><span class="hui12">2026-06-25</span></td>
  </tr>
</table>
</body>
</html>
"""
        session = patch_session([FakeResponse(text=html)])
        fetcher = PolicyNewsFetcher(config=_single_source_config("pboc"))
        items = fetcher.fetch_all()

        assert len(items) == 2
        assert session.calls[0][0].startswith("https://www.pbc.gov.cn/")
        assert items[0].title == "央行降准0.5个百分点"
        assert items[0].url.startswith("https://www.pbc.gov.cn/")
        assert items[0].is_high_impact is True
        assert items[1].is_high_impact is False

    def test_csrc_json_source(self, patch_session):
        csrc_json = {
            "data": {
                "results": [
                    {
                        "title": "证监会发布IPO新规",
                        "url": "//www.csrc.gov.cn/csrc/c100028/c7641653/content.shtml",
                        "publishedTimeStr": "2026-06-26 17:04:01",
                    },
                    {
                        "title": "  ",
                        "url": "//www.csrc.gov.cn/csrc/c100028/c7641654/content.shtml",
                        "publishedTimeStr": "2026-06-26 16:00:00",
                    },
                    {
                        "title": "证监会召开日常工作会议",
                        "url": "/csrc/c100028/c7641655/content.shtml",
                        "publishedTimeStr": "2026-06-25 09:00:00",
                    },
                ]
            }
        }
        session = patch_session([FakeResponse(json_data=csrc_json)])
        fetcher = PolicyNewsFetcher(config=_single_source_config("csrc"))
        items = fetcher.fetch_all()

        assert len(items) == 2
        assert session.calls[0][0].startswith("https://www.csrc.gov.cn/searchList/")
        assert "_isJson=true" in session.calls[0][0]

        titles = [i.title for i in items]
        assert "证监会发布IPO新规" in titles
        assert "证监会召开日常工作会议" in titles

        # Protocol-relative URLs are rewritten to HTTPS.
        assert items[0].url.startswith("https://www.csrc.gov.cn/")
        assert items[1].url.startswith("https://www.csrc.gov.cn/")

        # Date is normalised to the configured format.
        assert items[0].date == "2026-06-26 17:04:01"

        # High-impact keywords are flagged.
        assert items[0].is_high_impact is True
        assert items[1].is_high_impact is False

    def test_csrc_json_edge_cases(self, patch_session):
        """Relative href, malformed date, and non-dict entry in results."""
        csrc_json = {
            "data": {
                "results": [
                    {
                        "title": "Relative href test",
                        "url": "/relative/path.html",
                        "publishedTimeStr": "2026-06-26 17:04:01",
                    },
                    {
                        "title": "Bad date test",
                        "url": "//www.csrc.gov.cn/bad-date.html",
                        "publishedTimeStr": "not-a-date",
                    },
                    "not-a-dict",
                    {
                        "title": "After non-dict",
                        "url": "//www.csrc.gov.cn/after.html",
                        "publishedTimeStr": "2026-06-25 09:00:00",
                    },
                ]
            }
        }
        session = patch_session([FakeResponse(json_data=csrc_json)])
        fetcher = PolicyNewsFetcher(config=_single_source_config("csrc"))
        items = fetcher.fetch_all()

        assert len(items) == 3
        # Relative href joined to base URL.
        assert items[0].url == "https://www.csrc.gov.cn/searchList/relative/path.html"
        # Malformed date falls back to raw string.
        assert items[1].date == "not-a-date"
        # Non-dict entry is skipped, remaining items still parsed.
        assert items[2].title == "After non-dict"

    def test_policy_html_skipped_when_bs4_missing(self, monkeypatch, patch_session):
        monkeypatch.setattr("fetch_intel._HAS_BS4", False)
        # Only a PBOC HTML source is enabled in the test config.
        session = patch_session([])
        fetcher = PolicyNewsFetcher(config=_single_source_config("pboc"))
        items = fetcher.fetch_all()
        assert items == []
        assert session.calls == []


# ---------------------------------------------------------------------------
# CN news sources
# ---------------------------------------------------------------------------


class TestCnNewsNetwork:
    def test_wallstreetcn_fetch(self, patch_session):
        api_resp = {
            "data": {
                "items": [
                    {
                        "content_text": "Test live content",
                        "display_time": 1782464400,
                        "uri": "1",
                        "is_important": True,
                    },
                    {
                        "content_text": "Second item",
                        "display_time": 1782460800,
                        "uri": "2",
                        "is_important": False,
                    },
                ]
            }
        }
        session = patch_session([FakeResponse(json_data=api_resp)])
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_wallstreetcn(10)

        assert len(items) == 2
        assert session.calls[0][0].startswith("https://api-one.wallstcn.com/")
        assert items[0].title == "Test live content"
        assert items[0].url == "https://wallstreetcn.com/articles/1"
        assert items[0].is_important is True
        assert items[1].is_important is False
        # display_time is a Unix seconds integer in the real API.
        assert items[0].publish_time.year == 2026

    def test_cls_fetch(self, patch_session):
        api_resp = {
            "data": {
                "roll_data": [
                    {
                        "title": "CLS title",
                        "brief": "brief",
                        "content": "CLS content",
                        "ctime": 1782464400,
                        "id": "123",
                        "level": "B",
                        "subjects": [{"subject_name": "宏观"}],
                    }
                ]
            }
        }
        session = patch_session([FakeResponse(json_data=api_resp)])
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_cls(10)

        assert len(items) == 1
        call_url, call_kwargs = session.calls[0]
        assert call_url.startswith("https://www.cls.cn/api/cache")
        assert call_kwargs.get("params", {}).get("name") == "telegraph"
        assert items[0].title == "CLS title"
        assert items[0].source == "cls"
        assert items[0].tags == ["宏观"]
        # ctime is a Unix seconds integer in the cache API.
        assert items[0].publish_time.year == 2026

    def test_eastmoney_kuaixun_fetch(self, patch_session):
        api_resp = {
            "data": {
                "list": [
                    {
                        "title": "EastMoney title",
                        "summary": "digest text",
                        "showTime": "2026-06-26 17:00:00",
                        "uniqueUrl": "https://finance.eastmoney.com/a/1.html",
                        "mediaName": "市场",
                    }
                ]
            }
        }
        session = patch_session([FakeResponse(json_data=api_resp)])
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_eastmoney_kuaixun(10)

        assert len(items) == 1
        call_url, call_kwargs = session.calls[0]
        assert call_url.startswith("https://np-listapi.eastmoney.com/")
        assert call_kwargs.get("params", {}).get("req_trace")
        assert items[0].title == "EastMoney title"
        assert items[0].source == "eastmoney"
        assert items[0].tags == ["市场"]
        assert items[0].publish_time.year == 2026

    def test_jin10_fetch(self, monkeypatch, patch_session):
        monkeypatch.setenv("JIN10_APP_ID", "test-app-id")
        api_resp = {
            "data": [
                {
                    "data": {"content": "Jin10 content"},
                    "time": "2026-06-26 17:00:00",
                    "important": 1,
                },
                {
                    # Fallback to top-level content field.
                    "content": "Top-level content",
                    "time": "2026-06-26 16:00:00",
                    "important": 0,
                },
            ]
        }
        session = patch_session([FakeResponse(json_data=api_resp)])
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_jin10(10)

        assert len(items) == 2
        assert session.calls[0][1]["headers"]["x-app-id"] == "test-app-id"
        assert items[0].title == "Jin10 content"
        assert items[0].is_important is True
        assert items[1].title == "Top-level content"
        assert items[1].is_important is False

    def test_jin10_skipped_without_app_id(self, monkeypatch, patch_session):
        monkeypatch.delenv("JIN10_APP_ID", raising=False)
        session = patch_session([])
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_jin10(10)
        assert items == []
        assert session.calls == []

    def test_sina_7x24_fetch(self, patch_session):
        api_resp = {
            "result": {
                "data": {
                    "feed": {
                        "list": [
                            {
                                "rich_text": "Sina item",
                                "create_time": 1782464400,
                                "is_top": 1,
                                "tag": [{"name": "市场"}],
                            },
                            {
                                "rich_text": "Normal item",
                                "create_time": 1782460800,
                                "is_top": False,
                                "tag": [],
                            },
                        ]
                    }
                }
            }
        }
        session = patch_session([FakeResponse(json_data=api_resp)])
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_sina_7x24(10)

        assert len(items) == 2
        assert items[0].title == "Sina item"
        assert items[0].is_important is True
        assert items[1].is_important is False
        assert items[0].tags == ["市场"]

    def test_http_error_returns_empty(self, patch_session):
        session = patch_session([FakeResponse(status_code=503)])
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_wallstreetcn(10)
        assert items == []

    def test_cn_fetcher_aggregates_sources(self, monkeypatch, patch_session):
        monkeypatch.setenv("JIN10_APP_ID", "test-app-id")
        session = patch_session(
            [
                FakeResponse(json_data={"data": {"list": []}}),  # eastmoney
                FakeResponse(
                    json_data={"result": {"data": {"feed": {"list": []}}}}
                ),  # sina
                FakeResponse(json_data={"data": {"items": []}}),  # wallstreetcn
                FakeResponse(json_data={"data": []}),  # jin10
                FakeResponse(json_data={"data": {"roll_data": []}}),  # cls
            ]
        )
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_all(20)
        assert items == []
        assert len(session.calls) == 5

    def test_cn_fetcher_fetch_all_sorting_and_limit(self, monkeypatch, patch_session):
        """fetch_all merges and sorts items from multiple sources in descending chronological order."""
        monkeypatch.setenv("JIN10_APP_ID", "test-app-id")
        session = patch_session(
            [
                # eastmoney — 1 item
                FakeResponse(
                    json_data={
                        "data": {
                            "list": [
                                {
                                    "title": "EastMoney oldest",
                                    "summary": "",
                                    "showTime": "2026-06-24 10:00:00",
                                    "uniqueUrl": "https://em.com/1.html",
                                    "mediaName": "",
                                }
                            ]
                        }
                    }
                ),
                # sina — 1 item
                FakeResponse(
                    json_data={
                        "result": {
                            "data": {
                                "feed": {
                                    "list": [
                                        {
                                            "rich_text": "Sina middle",
                                            "create_time": 1782892800,  # 2026-06-25 00:00:00 UTC
                                            "is_top": 0,
                                            "tag": [],
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ),
                # wallstreetcn — 1 item
                FakeResponse(
                    json_data={
                        "data": {
                            "items": [
                                {
                                    "content_text": "WSCN newest",
                                    "display_time": 1782979200,  # 2026-06-26 00:00:00 UTC
                                    "uri": "3",
                                    "is_important": False,
                                }
                            ]
                        }
                    }
                ),
                # jin10 — empty
                FakeResponse(json_data={"data": []}),
                # cls — empty
                FakeResponse(json_data={"data": {"roll_data": []}}),
            ]
        )
        fetcher = CnNewsFetcher()
        items = fetcher.fetch_all(2)

        assert len(items) == 2
        # Descending chronological order: newest first.
        assert items[0].title == "WSCN newest"
        assert items[1].title == "Sina middle"
        # Limit respected.
        assert len(items) == 2
