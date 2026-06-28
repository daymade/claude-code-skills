#!/usr/bin/env python3
"""Fetch A-share market intelligence from public Chinese financial sources.

Standalone CLI extracted from the ashare-ai-analyst intelligence pipeline.
No platform dependencies — only ``requests`` and optionally ``beautifulsoup4``
for policy-source HTML parsing.

Examples:
    python scripts/fetch_intel.py --sources cn --limit 20
    python scripts/fetch_intel.py --symbols 000001,600519 --sources guba
    python scripts/fetch_intel.py --sources cn,policy,guba --limit 30 --format markdown
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional third-party dependencies
# ---------------------------------------------------------------------------

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "requests is required. Install with: pip install requests"
    ) from exc

_HAS_BS4 = False
try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:  # pragma: no cover
    logger.debug("beautifulsoup4 not installed; policy HTML parsing disabled")

_HAS_JIEBA = False
try:
    import jieba

    _HAS_JIEBA = True
except ImportError:  # pragma: no cover
    logger.debug("jieba not installed; name-based symbol extraction uses substring match")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ASHARE_CODE_RE = re.compile(
    r"(?<!\d)"
    r"("
    r"6(?:0[0-9]|8[89])\d{3}"  # Shanghai (main + STAR Market 688)
    r"|"
    r"(?:00[0-3]|30[01])\d{3}"  # Shenzhen (main + ChiNext 300)
    r"|"
    r"8[3-9]\d{4}"  # BSE (Beijing)
    r")"
    r"(?!\d)"
)

_INDEX_CODES = frozenset(
    {
        "000001",  # 上证指数
        "399001",  # 深证成指
        "399006",  # 创业板指
        "000300",  # 沪深300
        "000016",  # 上证50
        "000905",  # 中证500
        "000688",  # 科创50
        "899050",  # 北证50
    }
)

_MIN_NAME_LENGTH = 2

_BULL_KEYWORDS: list[tuple[str, int]] = [
    ("涨停", 3),
    ("翻倍", 3),
    ("重大利好", 3),
    ("连板", 3),
    ("一字板", 3),
    ("大涨", 2),
    ("新高", 2),
    ("突破", 2),
    ("利好", 2),
    ("增持", 2),
    ("回购", 2),
    ("主力", 2),
    ("龙头", 2),
    ("机构买入", 2),
    ("低估", 2),
    ("业绩超预期", 2),
    ("看好", 1),
    ("买入", 1),
    ("加仓", 1),
    ("反弹", 1),
    ("企稳", 1),
    ("放量", 1),
    ("底部", 1),
    ("上车", 1),
    ("牛", 1),
    ("起飞", 1),
    ("稳了", 1),
    ("冲", 1),
]

_BEAR_KEYWORDS: list[tuple[str, int]] = [
    ("跌停", 3),
    ("退市", 3),
    ("暴雷", 3),
    ("财务造假", 3),
    ("重大利空", 3),
    ("ST", 3),
    ("大跌", 2),
    ("暴跌", 2),
    ("新低", 2),
    ("破位", 2),
    ("利空", 2),
    ("减持", 2),
    ("质押", 2),
    ("亏损", 2),
    ("割肉", 2),
    ("套牢", 2),
    ("闪崩", 2),
    ("踩雷", 2),
    ("下跌", 1),
    ("走弱", 1),
    ("承压", 1),
    ("缩量", 1),
    ("卖出", 1),
    ("清仓", 1),
    ("垃圾", 1),
    ("坑人", 1),
    ("骗子", 1),
    ("完了", 1),
    ("凉了", 1),
    ("跑", 1),
]

_NEGATION_PREFIXES = ["不", "未", "没有", "非", "否认", "难以"]

_POLICY_SOURCE_CONFIG: dict[str, Any] = {
    "sources": {
        "csrc": {
            "name": "证监会",
            # CSRC list pages are now served through a WCM search JSON API.
            # channelid "a1a078ee0bc54721ab6b148884c784a8" corresponds to the
            # "证监会要闻" column (c100028). Verified live on 2026-06-26.
            "url": "https://www.csrc.gov.cn/searchList/a1a078ee0bc54721ab6b148884c784a8?_isAgg=true&_isJson=true&_pageSize=20&_template=index&page=1",
            "impact_category": "regulatory",
            "selectors": {},
            "enabled": True,
            "fetch_mode": "json",
            "json_path": "data.results",
            "title_field": "title",
            "url_field": "url",
            "date_field": "publishedTimeStr",
            "date_format": "%Y-%m-%d %H:%M:%S",
        },
        "pboc": {
            "name": "央行",
            "url": "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
            "impact_category": "monetary",
            "selectors": {
                "list": "td:has(font.newslist_style)",
                "title": "a",
                "date": "span.hui12",
            },
            "enabled": True,
        },
        "sse": {
            "name": "上交所",
            "url": "https://www.sse.com.cn/disclosure/announcement/general/",
            "impact_category": "exchange",
            "selectors": {
                "list": ".sse_list_1 dl",
                "title": "a",
                "date": "span",
            },
            "enabled": True,
        },
        "mof": {
            "name": "财政部",
            "url": "https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/",
            "impact_category": "fiscal",
            "selectors": {
                "list": "ul.xwfb_listbox li",
                "title": "a",
                "date": "span",
            },
            "enabled": True,
        },
    },
    "high_impact_keywords": {
        "monetary": [
            "降准",
            "降息",
            "LPR",
            "MLF",
            "逆回购",
            "公开市场操作",
            "货币政策",
            "利率",
        ],
        "regulatory": [
            "退市",
            "IPO",
            "注册制",
            "减持",
            "融资融券",
            "印花税",
            "转融通",
            "T+0",
        ],
        "fiscal": ["减税", "专项债", "财政赤字", "国债", "消费券"],
        "exchange": ["停牌", "复牌", "熔断", "交易规则", "涨跌幅"],
    },
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class InfoItem:
    """A single market-intelligence item."""

    source_id: str
    source_name: str
    title: str
    summary: str = ""
    url: str = ""
    category: str = "market"
    priority: str = "normal"
    tags: list[str] = field(default_factory=list)
    related_symbols: list[str] = field(default_factory=list)
    published_at: str = ""
    fetched_at: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    )
    extra: dict[str, Any] = field(default_factory=dict)
    item_id: str = ""

    def __post_init__(self) -> None:
        if not self.item_id:
            self.item_id = self._generate_id()
        if not self.published_at:
            self.published_at = self.fetched_at

    def _generate_id(self) -> str:
        raw = f"{self.source_id}:{self.title}:{self.url}:{self.published_at}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "category": self.category,
            "priority": self.priority,
            "tags": self.tags,
            "related_symbols": self.related_symbols,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "extra": self.extra,
        }


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _create_session(timeout: tuple[float, float] = (5.0, 15.0)) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    session._default_timeout = timeout  # type: ignore[attr-defined]

    retries = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        raise_on_status=True,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Inject default timeout into session.get so callers don't have to repeat it.
    _original_get = session.get

    def _get_with_timeout(url: str, **kwargs: Any) -> Any:
        if "timeout" not in kwargs:
            kwargs["timeout"] = session._default_timeout  # type: ignore[attr-defined]
        return _original_get(url, **kwargs)

    session.get = _get_with_timeout  # type: ignore[method-assign]
    return session


def _parse_datetime(value: Any) -> datetime | None:
    """Parse a timestamp from various upstream formats.

    Handles:
    - Unix seconds or milliseconds (int/float/numeric string)
    - Formatted strings such as "YYYY-MM-DD HH:MM:SS"
    - ISO-8601 strings

    Returns ``None`` when the value cannot be parsed.
    """
    if value is None or value == "":
        return None

    # Numeric timestamp (seconds or milliseconds). Treat as UTC.
    try:
        ts = float(value)
    except (ValueError, TypeError):
        ts = None
    if ts is not None and ts >= 0:
        # Milliseconds are common for CLS; seconds for Wallstreetcn/Sina.
        if ts > 1e11:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=UTC)
        except (ValueError, OSError):
            pass

    # Formatted strings. Interpret as UTC if no offset is given.
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue

    # ISO-8601.
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        pass

    return None


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------


class SymbolExtractor:
    """Extract A-share stock codes from text.

    Uses regex by default. If ``akshare`` is available and a local cache of
    code→name mappings exists, it also tries name-based matching.
    """

    def __init__(self, extra_names: dict[str, str] | None = None) -> None:
        self._extra_names = extra_names or {}
        self._all_names: dict[str, str] | None = None
        self._name_to_codes: dict[str, list[str]] | None = None

    def extract(self, text: str) -> list[str]:
        codes: set[str] = set()

        for match in _ASHARE_CODE_RE.finditer(text):
            code = match.group(1)
            if code not in _INDEX_CODES:
                codes.add(code)

        name_map = self._get_name_to_codes()
        if _HAS_JIEBA:
            tokens = set(_jieba_tokenize(text))
            for name, code_list in name_map.items():
                if name in tokens:
                    codes.update(code_list)
        else:
            for name, code_list in name_map.items():
                if name in text:
                    codes.update(code_list)

        return sorted(codes)

    def _get_name_to_codes(self) -> dict[str, list[str]]:
        if self._name_to_codes is not None:
            return self._name_to_codes

        all_names = self._load_names()
        name_to_codes: dict[str, list[str]] = {}
        for code, name in all_names.items():
            if len(name) < _MIN_NAME_LENGTH:
                continue
            name_to_codes.setdefault(name, []).append(code)

        self._name_to_codes = name_to_codes
        return name_to_codes

    def _load_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        try:
            import akshare as ak

            df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                # akshare column names vary between releases and locales.
                code_col = _find_column(df.columns, "code")
                name_col = _find_column(df.columns, "name")
                for _, row in df.iterrows():
                    code = str(row.get(code_col, ""))
                    name = str(row.get(name_col, ""))
                    if code and name and len(name) >= _MIN_NAME_LENGTH:
                        names[code] = name
        except Exception:
            logger.debug("akshare not available or failed; using regex-only extraction")
        # User-provided aliases always override fetched names so tests and custom
        # mappings remain stable regardless of corporate-action renamings.
        names.update(self._extra_names)
        return names


def _find_column(columns: Any, field: str) -> str:
    """Return the best matching English or Chinese column name."""
    normalized = {str(c).strip().lower(): str(c) for c in columns}
    candidates = {
        "code": ["code", "股票代码", "代码", "证券代码", "stk_code"],
        "name": ["name", "股票名称", "名称", "股票简称", "简称", "stk_name"],
    }.get(field, [field])
    for cand in candidates:
        if cand.lower() in normalized:
            return normalized[cand.lower()]
    return field


def _jieba_tokenize(text: str) -> list[str]:
    """Segment Chinese text for whole-name matching."""
    tokens: list[str] = []
    for token in jieba.lcut(text):
        token = token.strip()
        if len(token) >= _MIN_NAME_LENGTH:
            tokens.append(token)
    return tokens


# ---------------------------------------------------------------------------
# Chinese financial news (CLS / WSCN / Jin10 / Sina / EastMoney)
# ---------------------------------------------------------------------------


@dataclass
class CnNewsItem:
    title: str
    content: str
    source: str
    publish_time: datetime
    url: str = ""
    is_important: bool = False
    tags: list[str] = field(default_factory=list)


class CnNewsFetcher:
    """Direct fetcher for Chinese financial telegraph/news APIs."""

    def __init__(self) -> None:
        self._session = _create_session()
        self._last_request_ts = 0.0

    def _polite_sleep(self, interval: float = 0.3) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_ts = time.monotonic()

    def fetch_cls(self, limit: int = 30) -> list[CnNewsItem]:
        self._polite_sleep()
        try:
            # The legacy v3 depth endpoint now requires a signature and returns a
            # loading placeholder. The public cache endpoint is signature-free and
            # still exposes the telegraph roll_data list.
            resp = self._session.get(
                "https://www.cls.cn/api/cache",
                params={
                    "app": "CailianpressWeb",
                    "name": "telegraph",
                    "os": "web",
                    "sv": "8.7.9",
                },
                headers={"Referer": "https://www.cls.cn/telegraph"},
            )
            resp.raise_for_status()
            data = _safe_json(resp, ("data",))
            if data is None:
                return []

            data_payload = data.get("data") or {}
            items_raw = data_payload.get("roll_data", [])
            if not items_raw and isinstance(data_payload, list):
                items_raw = data_payload
            if not items_raw and isinstance(data_payload, dict):
                for key in ("telegraph", "roll", "depth_list"):
                    items_raw = data_payload.get(key, [])
                    if items_raw:
                        break

            if not items_raw and not any(
                k in data_payload for k in ("roll_data", "telegraph", "roll", "depth_list")
            ):
                logger.warning(
                    "CLS cache endpoint schema drift: none of roll_data/telegraph/roll/depth_list present in response keys %s",
                    list(data_payload.keys()) if isinstance(data_payload, dict) else "<list>",
                )
                return []

            results: list[CnNewsItem] = []
            count = 0
            for item in items_raw:
                title = _strip_html(str(item.get("title", "")))
                brief = _strip_html(str(item.get("brief", "")))
                content = _strip_html(str(item.get("content", brief)))
                if not title and not content:
                    continue

                pub_time = _parse_datetime(item.get("ctime", 0)) or datetime.now()

                tags = [
                    s.get("subject_name", "")
                    for s in item.get("subjects", [])
                    if s.get("subject_name")
                ][:5]

                item_id = item.get("id", "")
                detail_url = (
                    f"https://www.cls.cn/detail/{item_id}" if item_id else ""
                )

                results.append(
                    CnNewsItem(
                        title=title or brief[:50],
                        content=content,
                        source="cls",
                        publish_time=pub_time,
                        url=detail_url,
                        is_important=str(item.get("level", "")).upper() in ("A", "B", "1"),
                        tags=tags,
                    )
                )
                count += 1
                if count >= limit:
                    break
            logger.info("CLS: fetched %d items", len(results))
            return results
        except Exception as exc:
            logger.warning("CLS fetch failed: %s", type(exc).__name__)
            return []

    def fetch_wallstreetcn(self, limit: int = 30) -> list[CnNewsItem]:
        self._polite_sleep()
        try:
            resp = self._session.get(
                "https://api-one.wallstcn.com/apiv1/content/lives",
                params={"channel": "global-channel", "limit": str(limit)},
                headers={
                    "Referer": "https://wallstreetcn.com/",
                    "Origin": "https://wallstreetcn.com",
                },
            )
            resp.raise_for_status()
            data = _safe_json(resp, ("data",))
            if data is None:
                return []

            results: list[CnNewsItem] = []
            for item in data.get("data", {}).get("items", [])[:limit]:
                title = str(item.get("content_text", ""))
                if not title:
                    continue
                pub_time = (
                    _parse_datetime(item.get("display_time", 0)) or datetime.now()
                )

                uri = str(item.get("uri", ""))
                results.append(
                    CnNewsItem(
                        title=title,
                        content=title,
                        source="wallstreetcn",
                        publish_time=pub_time,
                        url=f"https://wallstreetcn.com/articles/{uri}" if uri else "",
                        is_important=item.get("is_important") in (True, 1, "1"),
                    )
                )
            logger.info("Wallstreetcn: fetched %d items", len(results))
            return results
        except Exception as exc:
            logger.warning("Wallstreetcn fetch failed: %s", type(exc).__name__)
            return []

    def fetch_jin10(self, limit: int = 30) -> list[CnNewsItem]:
        self._polite_sleep()
        app_id = os.environ.get("JIN10_APP_ID")
        if not app_id:
            logger.warning("JIN10_APP_ID not set; skipping Jin10 source")
            return []
        try:
            resp = self._session.get(
                "https://flash-api.jin10.com/get_flash_list",
                params={"max_time": "", "channel": "-8200"},
                headers={
                    "Referer": "https://www.jin10.com/",
                    "Origin": "https://www.jin10.com",
                    "x-app-id": app_id,
                    "x-version": "1.0.0",
                },
            )
            resp.raise_for_status()
            data = _safe_json(resp, ("data",))
            if data is None:
                return []

            results: list[CnNewsItem] = []
            for item in data.get("data", [])[:limit]:
                payload = item.get("data") or {}
                content = _strip_html(
                    str(payload.get("content") or item.get("content", ""))
                )
                if not content:
                    continue
                pub_time = _parse_datetime(item.get("time", "")) or datetime.now(UTC)

                results.append(
                    CnNewsItem(
                        title=content[:60],
                        content=content,
                        source="jin10",
                        publish_time=pub_time,
                        is_important=item.get("important") in (True, 1, "1"),
                    )
                )
            logger.info("Jin10: fetched %d items", len(results))
            return results
        except Exception as exc:
            logger.warning("Jin10 fetch failed: %s", type(exc).__name__)
            return []

    def fetch_sina_7x24(self, limit: int = 30) -> list[CnNewsItem]:
        self._polite_sleep()
        try:
            resp = self._session.get(
                "https://zhibo.sina.com.cn/api/zhibo/feed",
                params={
                    "page": "1",
                    "page_size": str(limit),
                    "zhibo_id": "152",
                    "tag_id": "0",
                    "type": "0",
                },
                headers={"Referer": "https://finance.sina.com.cn/7x24/"},
            )
            resp.raise_for_status()
            data = _safe_json(resp, ("result",))
            if data is None:
                return []

            items_raw = (
                data.get("result", {}).get("data", {}).get("feed", {}).get("list", [])
            )
            results: list[CnNewsItem] = []
            for item in items_raw:
                rich_text = str(item.get("rich_text", ""))
                if not rich_text:
                    continue
                content = _strip_html(rich_text)
                create_time = item.get("create_time", "")
                pub_time = _parse_datetime(create_time) or datetime.now(UTC)

                tags = [t.get("name", "") for t in item.get("tag", []) if t.get("name")]
                results.append(
                    CnNewsItem(
                        title=content[:60],
                        content=content,
                        source="sina",
                        publish_time=pub_time,
                        is_important=item.get("is_top") in (True, 1, "1"),
                        tags=tags,
                    )
                )
            logger.info("Sina 7x24: fetched %d items", len(results))
            return results
        except Exception as exc:
            logger.warning("Sina 7x24 fetch failed: %s", type(exc).__name__)
            return []

    def fetch_eastmoney_kuaixun(self, limit: int = 30) -> list[CnNewsItem]:
        self._polite_sleep()
        try:
            url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
            params = {
                "client": "web",
                "biz": "web_home_channel",
                "column": "350,35,466,467",
                "order": "1",
                "needInteractData": "0",
                "page_index": "1",
                "page_size": str(limit),
                # EastMoney now requires a trace id; any UUID works.
                "req_trace": str(uuid.uuid4()),
            }
            resp = self._session.get(url, params=params)
            resp.raise_for_status()
            data = _safe_json(resp, ("data",))
            if data is None:
                return []

            data_payload = data.get("data") or {}
            results: list[CnNewsItem] = []
            for item in data_payload.get("list", [])[:limit]:
                title = item.get("title", "").strip()
                digest = item.get("summary", "")
                content = digest or title
                art_url = item.get("uniqueUrl", item.get("url", ""))
                pub_time = _parse_datetime(item.get("showTime", "")) or datetime.now(UTC)

                media = item.get("mediaName", "")
                tags = [media] if media else []
                is_important = any(
                    k in title
                    for k in ["国务院", "发改委", "工信部", "证监会", "央行", "政策"]
                ) or any(k in str(tags) for k in ["政策", "要闻"])

                results.append(
                    CnNewsItem(
                        title=title,
                        content=content[:500],
                        source="eastmoney",
                        publish_time=pub_time,
                        url=art_url,
                        is_important=is_important,
                        tags=tags[:5],
                    )
                )
            logger.info("EastMoney kuaixun: fetched %d items", len(results))
            return results
        except Exception as exc:
            logger.warning("EastMoney kuaixun fetch failed: %s", type(exc).__name__)
            return []

    def fetch_all(self, limit: int = 50) -> list[CnNewsItem]:
        """Fetch from all CN sources and return merged results up to *limit*.

        The *limit* is applied to the merged result set, not per source.
        """
        sources = [
            self.fetch_eastmoney_kuaixun,
            self.fetch_sina_7x24,
            self.fetch_wallstreetcn,
            self.fetch_jin10,
            self.fetch_cls,
        ]
        per_source_cap = limit // len(sources) + 1
        all_items: list[CnNewsItem] = []
        for fetcher in sources:
            try:
                all_items.extend(fetcher(per_source_cap))
            except Exception:
                continue
        all_items.sort(key=lambda x: x.publish_time, reverse=True)
        return all_items[:limit]


# ---------------------------------------------------------------------------
# Policy news
# ---------------------------------------------------------------------------


@dataclass
class PolicyItem:
    title: str
    source: str
    source_name: str
    url: str = ""
    date: str = ""
    impact_category: str = ""
    is_high_impact: bool = False


class PolicyNewsFetcher:
    """Fetch policy/regulatory news from official Chinese sources."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or _POLICY_SOURCE_CONFIG
        self._sources = self._config.get("sources", {})
        self._high_impact_keywords = self._config.get("high_impact_keywords", {})
        self._session = _create_session()

    def fetch_all(self) -> list[PolicyItem]:
        all_items: list[PolicyItem] = []
        for source_id, source_cfg in self._sources.items():
            if not source_cfg.get("enabled", True):
                continue
            is_json = source_cfg.get("fetch_mode") == "json"
            if not _HAS_BS4 and not is_json:
                logger.warning(
                    "beautifulsoup4 not installed; skipping HTML policy source '%s'",
                    source_id,
                )
                continue
            try:
                items = self._fetch_source(source_id, source_cfg)
                for item in items:
                    item.is_high_impact = self._check_high_impact(item)
                all_items.extend(items)
            except Exception as exc:
                logger.warning("Policy source '%s' failed: %s", source_id, type(exc).__name__)
        all_items.sort(key=lambda x: x.date, reverse=True)
        return all_items

    def _fetch_source(
        self, source_id: str, source_cfg: dict[str, Any]
    ) -> list[PolicyItem]:
        url = source_cfg.get("url", "")
        if not url:
            return []

        if source_cfg.get("fetch_mode") == "json":
            return self._fetch_json_source(source_id, source_cfg)

        if not _HAS_BS4:
            logger.warning(
                "beautifulsoup4 not installed; cannot fetch HTML source '%s'", source_id
            )
            return []

        resp = self._session.get(url)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")
        selectors = source_cfg.get("selectors", {})
        list_selector = selectors.get("list", "li")
        title_selector = selectors.get("title", "a")
        date_selector = selectors.get("date", "span")

        items: list[PolicyItem] = []
        source_name = source_cfg.get("name", source_id)
        impact_category = source_cfg.get("impact_category", "")

        for elem in soup.select(list_selector)[:20]:
            title_elem = elem.select_one(title_selector)
            date_elem = elem.select_one(date_selector)
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            if not title:
                continue
            href = title_elem.get("href", "")
            if href and not href.startswith("http"):
                href = urljoin(url, href)
            date_text = date_elem.get_text(strip=True) if date_elem else ""
            items.append(
                PolicyItem(
                    title=title,
                    source=source_id,
                    source_name=source_name,
                    url=href,
                    date=date_text,
                    impact_category=impact_category,
                )
            )
        logger.info("Policy source %s: fetched %d items", source_name, len(items))
        return items

    def _fetch_json_source(
        self, source_id: str, source_cfg: dict[str, Any]
    ) -> list[PolicyItem]:
        url = source_cfg["url"]
        resp = self._session.get(url)
        resp.raise_for_status()
        data = _safe_json(resp)
        if data is None:
            return []

        # Walk the configured JSON path, defaulting to data.results.
        path_parts = source_cfg.get("json_path", "data.results").split(".") or [
            "data",
            "results",
        ]
        for key in path_parts:
            if isinstance(data, dict):
                data = data.get(key, [])
            else:
                data = []
                break
        results = data if isinstance(data, list) else []

        title_field = source_cfg.get("title_field", "title")
        url_field = source_cfg.get("url_field", "url")
        date_field = source_cfg.get("date_field", "publishedTimeStr")
        date_format = source_cfg.get("date_format", "")
        source_name = source_cfg.get("name", source_id)
        impact_category = source_cfg.get("impact_category", "")

        items: list[PolicyItem] = []
        for entry in results[:20]:
            if not isinstance(entry, dict):
                continue
            title = (entry.get(title_field) or "").strip()
            if not title:
                continue
            href = (entry.get(url_field) or "").strip()
            if href.startswith("//"):
                href = f"https:{href}"
            elif href and not href.startswith("http"):
                href = urljoin(url, href)

            date_text = (entry.get(date_field) or "").strip()
            if date_format and date_text:
                try:
                    date_text = datetime.strptime(date_text, date_format).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    pass

            items.append(
                PolicyItem(
                    title=title,
                    source=source_id,
                    source_name=source_name,
                    url=href,
                    date=date_text,
                    impact_category=impact_category,
                )
            )
        logger.info("Policy source %s: fetched %d JSON items", source_name, len(items))
        return items

    def _check_high_impact(self, item: PolicyItem) -> bool:
        category_keywords = self._high_impact_keywords.get(item.impact_category, [])
        all_keywords = []
        for kw_list in self._high_impact_keywords.values():
            all_keywords.extend(kw_list)
        keywords = category_keywords or all_keywords
        return any(kw in item.title for kw in keywords)


# ---------------------------------------------------------------------------
# EastMoney Guba sentiment
# ---------------------------------------------------------------------------


@dataclass
class GubaMetrics:
    symbol: str
    post_count_24h: int = 0
    read_count_avg: float = 0.0
    comment_count_avg: float = 0.0
    sentiment: str = "neutral"
    sentiment_score: float = 0.0
    hot_topics: list[str] = field(default_factory=list)
    institutional_post_count: int = 0
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class GubaFetcher:
    """Fetch retail sentiment from EastMoney Guba (股吧)."""

    API_URL = "https://gbapi.eastmoney.com/stkpost/api/v1/post/listbystock"
    BASE_URL = "https://guba.eastmoney.com"

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._session = _create_session()
        self._last_request_ts = 0.0

    def _rate_limit(self, interval: float = 0.5) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_ts = time.monotonic()

    def _convert_symbol(self, symbol: str) -> str:
        symbol = symbol.strip()
        for prefix in ("SH", "SZ", "BJ", "sh", "sz", "bj"):
            if symbol.startswith(prefix):
                return symbol[2:]
        return symbol

    def fetch(self, symbol: str) -> GubaMetrics | None:
        symbol_code = self._convert_symbol(symbol)
        try:
            posts = self._fetch_posts(symbol_code)
        except Exception as exc:
            logger.warning("Guba fetch failed for %s: %s", symbol_code, type(exc).__name__)
            return None

        if not posts:
            return GubaMetrics(symbol=symbol_code)

        total_reads = sum(int(p.get("read_count", 0) or 0) for p in posts)
        total_comments = sum(int(p.get("comment_count", 0) or 0) for p in posts)
        post_count = len(posts)

        sentiment, score = self._extract_sentiment(posts)
        topics = self._extract_topics(posts)
        inst_count = self._count_institutional(posts)

        return GubaMetrics(
            symbol=symbol_code,
            post_count_24h=post_count,
            read_count_avg=round(total_reads / post_count, 1),
            comment_count_avg=round(total_comments / post_count, 1),
            sentiment=sentiment,
            sentiment_score=score,
            hot_topics=topics,
            institutional_post_count=inst_count,
        )

    def fetch_batch(self, symbols: list[str]) -> list[GubaMetrics]:
        results: list[GubaMetrics] = []
        for symbol in symbols:
            metrics = self.fetch(symbol)
            if metrics is not None:
                results.append(metrics)
        return results

    def _fetch_posts(self, symbol_code: str) -> list[dict[str, Any]]:
        def _do_fetch() -> list[dict[str, Any]]:
            self._rate_limit()
            resp = self._session.get(
                self.API_URL,
                params={
                    "stockcode": symbol_code,
                    "pageindex": "1",
                    "pagesize": "30",
                    "sort": "posttime",
                    "source": "web",
                },
            )
            if resp.status_code == 200:
                try:
                    data = _safe_json(resp, ("re",))
                    if data is not None:
                        posts = data.get("re", [])
                        if isinstance(posts, list) and posts:
                            return posts
                except json.JSONDecodeError as exc:
                    logger.debug("Guba JSON decode error for %s: %s — text[:200]=%r", symbol_code, exc, resp.text[:200])
                except Exception:
                    pass
            # JSON endpoint failed or empty — try HTML fallback.
            return self._fetch_posts_html(symbol_code)
        return _retry_with_backoff(_do_fetch, retries=3, backoff_factor=1.0)

    def _fetch_posts_html(self, symbol_code: str) -> list[dict[str, Any]]:
        if not re.fullmatch(r"\d{6}", symbol_code):
            raise ValueError(f"Invalid symbol code for Guba HTML fetch: {symbol_code!r}")

        def _do_fetch() -> list[dict[str, Any]]:
            self._rate_limit()
            resp = self._session.get(
                f"{self.BASE_URL}/list,{symbol_code}.html",
            )
            if resp.status_code != 200:
                return []
            return self._parse_html_posts(resp.text)
        return _retry_with_backoff(_do_fetch, retries=3, backoff_factor=1.0)

    def _parse_html_posts(self, html_text: str) -> list[dict[str, Any]]:
        if _HAS_BS4:
            try:
                soup = BeautifulSoup(html_text, "html.parser")
                posts: list[dict[str, Any]] = []
                for item in soup.select(".articleh"):
                    read_elem = item.select_one(".read")
                    reply_elem = item.select_one(".reply")
                    title_elem = item.select_one(".title a")
                    if title_elem:
                        posts.append(
                            {
                                "read_count": int(read_elem.get_text(strip=True)) if read_elem else 0,
                                "comment_count": int(reply_elem.get_text(strip=True)) if reply_elem else 0,
                                "title": title_elem.get_text(strip=True),
                            }
                        )
                if posts:
                    return posts
            except Exception:
                pass

        row_pattern = re.compile(
            r'class="read"[^>]*>(\d+)</\w+>'
            r'.*?class="reply"[^>]*>(\d+)</\w+>'
            r'.*?class="title"[^>]*>.*?<a[^>]*>([^<]+)</a>',
            re.DOTALL,
        )
        simple_pattern = re.compile(
            r'"read_count"[:\s]*(\d+).*?"comment_count"[:\s]*(\d+).*?"title"[:\s]*"([^"]+)"',
            re.DOTALL,
        )
        posts: list[dict[str, Any]] = []
        for match in row_pattern.finditer(html_text):
            posts.append(
                {
                    "read_count": int(match.group(1)),
                    "comment_count": int(match.group(2)),
                    "title": match.group(3).strip(),
                }
            )
        if not posts:
            for match in simple_pattern.finditer(html_text):
                posts.append(
                    {
                        "read_count": int(match.group(1)),
                        "comment_count": int(match.group(2)),
                        "title": match.group(3).strip(),
                    }
                )
        if not posts:
            logger.debug(
                "Guba HTML regex returned no posts; HTML[:500]=%r",
                html_text[:500],
            )
        return posts

    def _extract_sentiment(self, posts: list[dict[str, Any]]) -> tuple[str, float]:
        bull_score = 0
        bear_score = 0
        for post in posts:
            text = post.get("title", "") or post.get("post_title", "") or ""
            content = post.get("post_content", "") or post.get("content", "") or ""
            text = _strip_html(f"{text} {content}")
            b_delta, br_delta = self._score_text(text)
            bull_score += b_delta
            bear_score += br_delta

        total = bull_score + bear_score
        if total == 0:
            return "neutral", 0.0
        raw_score = max(-1.0, min(1.0, (bull_score - bear_score) / total))
        if raw_score > 0.15:
            return "bullish", round(raw_score, 3)
        if raw_score < -0.15:
            return "bearish", round(raw_score, 3)
        return "neutral", round(raw_score, 3)

    def _score_text(self, text: str) -> tuple[int, int]:
        """Score all keyword occurrences, preferring longer matches and flipping on negation.

        A naïve scan would double-count overlapping keywords such as ``跌`` inside
        ``跌停`` or ``利好`` inside ``重大利好``. We collect all candidate matches,
        sort by length descending, and mark matched character ranges so only the
        longest non-overlapping keyword counts at each position.
        """
        keywords = [
            (kw, weight, True) for kw, weight in _BULL_KEYWORDS
        ] + [(kw, weight, False) for kw, weight in _BEAR_KEYWORDS]
        # Longest-first avoids sub-keyword double counting.
        keywords.sort(key=lambda x: len(x[0]), reverse=True)

        matches: list[tuple[int, int, str, int, bool]] = []
        for kw, weight, is_bull in keywords:
            start = 0
            while True:
                idx = text.find(kw, start)
                if idx < 0:
                    break
                matches.append((idx, idx + len(kw), kw, weight, is_bull))
                start = idx + len(kw)

        # Process left-to-right so the first/longest match wins at overlaps.
        matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        covered = [False] * len(text)
        bull_delta = 0
        bear_delta = 0
        for start, end, _kw, weight, is_bull in matches:
            if any(covered[start:end]):
                continue
            for i in range(start, end):
                covered[i] = True
            prefix = text[max(0, start - 6) : start]
            # Strip trailing whitespace/punctuation so "不 涨停" and "不，涨停"
            # are treated the same as "不涨停".
            prefix = re.sub(r"[\s，。！？、；：\"'（）\[\]]+$", "", prefix)
            negated = any(prefix.endswith(neg) for neg in _NEGATION_PREFIXES)
            if is_bull:
                if negated:
                    bear_delta += weight
                else:
                    bull_delta += weight
            else:
                if negated:
                    bull_delta += weight
                else:
                    bear_delta += weight
        return bull_delta, bear_delta

    def _extract_topics(self, posts: list[dict[str, Any]]) -> list[str]:
        titles: list[str] = []
        for post in posts:
            title = post.get("title", "") or post.get("post_title", "") or ""
            title = _strip_html(title).strip()
            if title and len(title) >= 4:
                titles.append(title)
        if not titles:
            return []
        phrase_counts: dict[str, int] = {}
        for title in titles:
            for phrase in re.findall(r"[一-鿿]{2,6}", title):
                if phrase in (
                    "大家",
                    "今天",
                    "明天",
                    "请问",
                    "怎么",
                    "什么",
                    "为什么",
                    "有没有",
                    "是不是",
                    "可以",
                    "已经",
                    "东方财富",
                    "股吧",
                    "网友",
                ):
                    continue
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
        sorted_phrases = sorted(phrase_counts.items(), key=lambda x: x[1], reverse=True)
        return [phrase for phrase, _ in sorted_phrases[:3]]

    def _count_institutional(self, posts: list[dict[str, Any]]) -> int:
        count = 0
        markers = ["机构", "研报", "评级", "目标价", "研究所", "券商", "分析师"]
        for post in posts:
            user_type = post.get("user_type", "") or post.get("source_type", "")
            if "机构" in str(user_type) or "研报" in str(user_type):
                count += 1
                continue
            title = post.get("title", "") or post.get("post_title", "") or ""
            if any(marker in title for marker in markers):
                count += 1
        return count


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _retry_with_backoff(
    fn: Any,
    retries: int = 3,
    backoff_factor: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Any:
    """Call *fn* up to *retries* times with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt < retries - 1:
                sleep_time = backoff_factor * (2 ** attempt)
                logger.debug("Retry %d/%d after %.1fs: %s", attempt + 1, retries - 1, sleep_time, type(exc).__name__)
                time.sleep(sleep_time)
    raise last_exc  # type: ignore[misc]


def _safe_json(resp: Any, expected_keys: tuple[str, ...] = ()) -> dict[str, Any] | list[Any] | None:
    """Parse JSON response and validate expected top-level keys."""
    try:
        data = resp.json()
    except Exception as exc:
        logger.debug("JSON decode failed: %s — text[:200]=%r", type(exc).__name__, resp.text[:200])
        return None
    if not expected_keys:
        return data
    if isinstance(data, dict):
        for key in expected_keys:
            if key in data:
                return data
        logger.debug("JSON missing expected keys %s; got %s", expected_keys, list(data.keys()))
        return None
    return data


def _cn_item_to_info(item: CnNewsItem, extractor: SymbolExtractor) -> InfoItem:
    text = f"{item.title} {item.content}"
    symbols = extractor.extract(text)
    category_map = {
        "cls": "market",
        "wallstreetcn": "market",
        "jin10": "market",
        "sina": "global",
        "eastmoney": "market",
    }
    priority = "breaking" if item.is_important else "normal"
    return InfoItem(
        source_id=f"cn_{item.source}",
        source_name=item.source,
        title=item.title,
        summary=item.content,
        url=item.url,
        category=category_map.get(item.source, "market"),
        priority=priority,
        tags=item.tags,
        related_symbols=symbols,
        published_at=item.publish_time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _policy_item_to_info(item: PolicyItem, extractor: SymbolExtractor) -> InfoItem:
    symbols = extractor.extract(item.title)
    priority = "high" if item.is_high_impact else "normal"
    return InfoItem(
        source_id=f"policy_{item.source}",
        source_name=item.source_name,
        title=item.title,
        summary="",
        url=item.url,
        category="policy",
        priority=priority,
        related_symbols=symbols,
        published_at=item.date,
        extra={"impact_category": item.impact_category},
    )


def _guba_to_info(metrics: GubaMetrics, extractor: SymbolExtractor) -> InfoItem:
    title = (
        f"{metrics.symbol} 股吧情绪: {metrics.sentiment} ({metrics.sentiment_score})"
    )
    summary = (
        f"24h发帖 {metrics.post_count_24h}, 平均阅读 {metrics.read_count_avg}, "
        f"平均评论 {metrics.comment_count_avg}, 机构相关帖 {metrics.institutional_post_count}"
    )
    if metrics.hot_topics:
        summary += f", 热议: {', '.join(metrics.hot_topics)}"
    return InfoItem(
        source_id=f"guba_{metrics.symbol}",
        source_name="东方财富股吧",
        title=title,
        summary=summary,
        url=f"https://guba.eastmoney.com/list,{metrics.symbol}.html",
        category="social",
        priority="normal",
        tags=metrics.hot_topics,
        related_symbols=[metrics.symbol],
        published_at=metrics.fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
        extra={
            "sentiment": metrics.sentiment,
            "sentiment_score": metrics.sentiment_score,
            "post_count_24h": metrics.post_count_24h,
        },
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _to_markdown(items: list[InfoItem]) -> str:
    lines = ["# A 股消息面情报\n"]
    for item in items:
        tags = " ".join(f"`{t}`" for t in item.tags) if item.tags else ""
        symbols = (
            " ".join(f"`{s}`" for s in item.related_symbols)
            if item.related_symbols
            else ""
        )
        lines.append(f"## {item.title}")
        lines.append(f"- **来源**: {item.source_name} (`{item.source_id}`)")
        lines.append(f"- **时间**: {item.published_at}")
        lines.append(f"- **分类/优先级**: {item.category} / {item.priority}")
        if symbols:
            lines.append(f"- **相关代码**: {symbols}")
        if tags:
            lines.append(f"- **标签**: {tags}")
        if item.url:
            lines.append(f"- **链接**: {item.url}")
        if item.summary:
            lines.append(f"\n{item.summary}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main fetch dispatcher
# ---------------------------------------------------------------------------


def fetch_intel(
    sources: list[str],
    symbols: list[str] | None = None,
    keywords: list[str] | None = None,
    limit: int = 30,
) -> list[InfoItem]:
    """Fetch A-share intelligence from selected sources.

    Args:
        sources: List of source groups. Supported: ``cn``, ``policy``, ``guba``.
        symbols: Stock codes for ``guba`` source.
        keywords: Optional keywords to filter items by title/summary.
        limit: Max items applied to the merged result set, not per source.

    Returns:
        List of InfoItem, sorted by published time descending.
    """
    extractor = SymbolExtractor()
    items: list[InfoItem] = []

    if "cn" in sources:
        fetcher = CnNewsFetcher()
        cn_items = fetcher.fetch_all(limit)
        for it in cn_items:
            items.append(_cn_item_to_info(it, extractor))

    if "policy" in sources:
        policy_fetcher = PolicyNewsFetcher()
        for it in policy_fetcher.fetch_all()[:limit]:
            items.append(_policy_item_to_info(it, extractor))

    if "guba" in sources:
        if not symbols:
            logger.warning("guba source selected but no --symbols provided; skipped")
        else:
            guba = GubaFetcher()
            for metrics in guba.fetch_batch(symbols):
                items.append(_guba_to_info(metrics, extractor))

    if keywords:
        keyword_list = [k.lower() for k in keywords]
        filtered: list[InfoItem] = []
        for item in items:
            text = f"{item.title} {item.summary} {' '.join(item.tags)}".lower()
            if any(kw in text for kw in keyword_list):
                filtered.append(item)
        items = filtered

    items.sort(key=lambda x: x.published_at, reverse=True)
    return items


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _positive_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}") from exc
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("--limit must be a positive integer")
    return ivalue


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch A-share market intelligence from public sources."
    )
    parser.add_argument(
        "--sources",
        default="cn",
        help="Comma-separated source groups: cn,policy,guba (default: cn)",
    )
    parser.add_argument(
        "--symbols",
        default="",
        help="Comma-separated stock codes for guba source, e.g. 000001,600519",
    )
    parser.add_argument(
        "--keywords",
        default="",
        help="Comma-separated keywords to filter results",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=30,
        help="Max items per source group (default: 30)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path. Prints to stdout if omitted.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    source_list = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    symbol_list = [s.strip() for s in args.symbols.split(",") if s.strip()] or None
    keyword_list = [k.strip() for k in args.keywords.split(",") if k.strip()] or None

    items = fetch_intel(
        sources=source_list,
        symbols=symbol_list,
        keywords=keyword_list,
        limit=args.limit,
    )

    if args.format == "json":
        output = json.dumps(
            [it.to_dict() for it in items], ensure_ascii=False, indent=2
        )
    else:
        output = _to_markdown(items)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Wrote {len(items)} items to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
