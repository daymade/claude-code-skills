"""统一入口：一个 BigdataClient 暴露两种能力
=====================================================

1. **SDK 高层能力**（`self.bd`）—— 官方 `bigdata_client.Bigdata`
   封装好的 search / knowledge_graph / subscription / chat / watchlists。

2. **ad hoc REST 逃生舱**（`self.http`）—— `bd._api.http`
   （`RateLimitedHTTPWrapper`，base url = ``https://api.bigdata.com/``）。
   SDK 高层没暴露的 endpoint（events-calendar / analyst-estimates /
   latest-surprise / target-price / company-screener / quotas ...）全部
   走这里。认证（ApiKeyAuth 注 JWT）+ 代理（靠 ``HTTPS_PROXY`` 环境变量）
   **自动复用**，无需自己拼 header。

为什么需要逃生舱
----------------
``bigdata_client`` 的 ``BigdataConnection`` 只 wrap 了
search / chunks / knowledge-graph / chat / watchlists / uploads。
一整套 RavenPack 遗留的 ``/v1/*`` 结构化金融数据产品线（前瞻财报日历、
一致预期、财报 surprise、评级、目标价、screener）SDK 一个高层方法都没写，
但同一后端、同一 JWT，raw http 直达。

机制证据链（运行时 L4 实测，非文档推断）
-----------------------------------------
- ``bd._api`` 是 ``bigdata_client.connection.BigdataConnection``。
- 它持有 ``bd._api.http``（``RateLimitedHTTPWrapper``），``api_url='https://api.bigdata.com/'``。
- SDK 高层方法（query_chunks / by_ids / autosuggest / get_my_quota ...）
  全都内部 delegate 到 ``self.http.post(endpoint, json=...)`` /
  ``self.http.get(endpoint, params=...)``。
- 所以打 SDK 没暴露的 endpoint = 直接调 ``self.http.<verb>(相对路径, ...)``。

路由形态规律（避免踩坑）
------------------------
- 业务面是 ``POST /v1/<resource>/query``，**裸 ``GET /v1/<resource>`` 会 404**。
- 平台面（quotas）是 ``GET /v1/subscription/quotas``。
- ``403 'Missing Authentication Token'`` = API Gateway 说该路径上无此路由
  （不是权限拒绝），``404`` = 路径不存在。需用文档（docs.bigdata.com/llms.txt）
  确认确切 path，不要瞎猜。
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Optional, Union

from bigdata_client import Bigdata

__all__ = ["BigdataClient", "require_env"]


def require_env(name: str) -> str:
    """读环境变量，缺失立即 fail-fast（NO FALLBACK 原则）。

    禁止用明文 default 兜底 secret —— 这正是会被 scanner 扫到的反模式。
    """
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required env var: {name}. "
            f"Set it before constructing BigdataClient, e.g. "
            f"`export {name}=...`"
        )
    return value


class BigdataClient:
    """Bigdata.com 统一客户端 —— SDK 高层 + REST 逃生舱二合一。

    Parameters
    ----------
    api_key:
        Bigdata API key（``bd_v2_...`` 形态）。默认从 ``BIGDATA_API_KEY``
        环境变量读取（**绝不**硬编码）。
    check_proxy:
        若为 True（默认）且未显式传 ``proxy``，构造时检查 ``HTTPS_PROXY``
        是否设置，未设则提醒（出站代理可走 env var 或 ``proxy=`` 参数，二选一）。
    verify_ssl:
        透传给官方 ``Bigdata(verify_ssl=...)``（``False`` 关校验，或传 CA 路径
        字符串，见 ssl_verification.md）。代理做 TLS 拦截 / 自签证书时，传代理
        CA 路径是正道，优于盲重试。默认 None（用 SDK 默认）。⚠️ 不建议 ``False``。
    proxy:
        透传给官方 ``Bigdata(proxy=...)``（构造方式见 proxy_configuration.md）；
        与 ``HTTPS_PROXY`` env 二选一。默认 None（走 env var 路径）。

    Examples
    --------
    >>> import os
    >>> os.environ["BIGDATA_API_KEY"] = "bd_v2_xxx"
    >>> os.environ["HTTPS_PROXY"] = "http://127.0.0.1:8080"  # 仅在需要出站代理时
    >>> client = BigdataClient()                  # doctest: +SKIP
    >>> companies = client.bd.knowledge_graph.find_companies("Apple")  # doctest: +SKIP
    >>> quota = client.get_quota_raw()            # doctest: +SKIP  # REST 逃生舱
    """

    #: REST 业务面路由前缀（仅文档用途，方法里仍传完整 endpoint）
    API_BASE = "https://api.bigdata.com/"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        check_proxy: bool = True,
        verify_ssl: Optional[Union[bool, str]] = None,
        proxy: Optional[Any] = None,
    ) -> None:
        self.api_key = api_key or require_env("BIGDATA_API_KEY")

        if check_proxy and proxy is None and not (
            os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        ):
            # 不抛错 —— 海外/无代理环境本就不需要。仅提醒。
            import warnings

            warnings.warn(
                "HTTPS_PROXY 未设置。若你的网络需要出站代理才能访问 "
                "api.bigdata.com，可 `export HTTPS_PROXY=http://<host>:<port>`，"
                "或给 BigdataClient(proxy=...) 传官方 Proxy 对象（二选一，见 "
                "proxy_configuration.md）。WebSocket（chat）另需 WSS_PROXY。",
                stacklevel=2,
            )

        # ---- SDK 高层入口（verify_ssl / proxy 是官方构造器参数，仅在显式
        #      传入时透传，默认不改 SDK 行为）----
        sdk_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if verify_ssl is not None:
            sdk_kwargs["verify_ssl"] = verify_ssl
        if proxy is not None:
            sdk_kwargs["proxy"] = proxy
        self.bd = Bigdata(**sdk_kwargs)

    # ------------------------------------------------------------------ #
    # REST 逃生舱直通                                                     #
    # ------------------------------------------------------------------ #
    @property
    def http(self):
        """``bd._api.http`` —— RateLimitedHTTPWrapper（REST 直通入口）。

        签名（运行时确认）::

            http.get(endpoint: str, params: dict = None) -> dict | list
            http.post(endpoint: str, json: dict | list[dict]) -> dict | list
            http.put(endpoint: str, json) -> dict | list
            http.patch(endpoint: str, json) -> dict | list
            http.delete(endpoint: str) -> dict | list
            http.get_chunks(endpoint: str, chunk_size: int) -> Iterable[bytes]
            http.async_get(list[...]) -> 并发 GET

        endpoint 是相对路径（如 ``"v1/events-calendar/query"``），内部
        ``urljoin(api_url, endpoint)`` 拼成绝对 URL；也接受绝对 URL。
        """
        return self.bd._api.http

    @property
    def conn(self):
        """``bd._api`` —— BigdataConnection（"for internal use only"）。

        除 ``.http`` 外，它还有一批高层封装方法可直接复用：
        ``query_chunks`` / ``by_ids`` / ``autosuggest`` /
        ``query_discovery_panel`` / ``download_annotated_dict`` /
        ``get_my_quota`` / ``get_companies_by_isin`` 等。需要时优先用这些
        （它们内部已处理 request/response model），而非自己拼 raw http。
        """
        return self.bd._api

    def rest_get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """REST GET（平台面，如 quotas）。薄封装 ``self.http.get``。

        endpoint 形如 ``"v1/subscription/quotas"``（不带前导斜杠）。
        """
        return self.http.get(endpoint, params)

    def rest_post(self, endpoint: str, json: Any) -> Any:
        """REST POST（业务面，统一 ``/v1/<resource>/query`` 形态）。

        薄封装 ``self.http.post``。endpoint 形如
        ``"v1/events-calendar/query"``。
        """
        return self.http.post(endpoint, json)

    # ------------------------------------------------------------------ #
    # 配额 / 计量（成本意识入口，详见 cost.py）                          #
    # ------------------------------------------------------------------ #
    def get_quota_raw(self) -> dict:
        """原始 chunk 级配额（走 SDK 的 ``get_my_quota`` 封装方法）。

        返回 ``MyBigdataQuotaResponse.model_dump()``，含
        ``organization_quota.contextual_units_max_read`` 和
        ``organization_consumed.contextual_units_read``。
        **这是 chunk 计数器**（1 query_unit = 10 chunks），是成本模型的
        承重字段。SDK 高层 ``subscription.get_details()`` 把它 ÷10 包装成
        query_unit 会丢失 chunk 语义，所以用这条 raw 路径。
        """
        resp = self.conn.get_my_quota()
        return resp.model_dump()

    def get_quotas_v1(self) -> Any:
        """实时细分配额（REST GET ``v1/subscription/quotas``）。

        返回结构 ``{'results': ..., 'errors': ..., 'metadata': ...}``，
        含 credits limit/usage/remaining + billing 周期 + units 细分
        （search:web_unit_read 等）。**这个 endpoint SDK 完全没有高层方法**，
        是逃生舱能打 SDK 缺失路由的直接证据。可在冷启动中途轮询做
        chunk→credit 换算率实测校准（免费，不按 chunk 计费）。
        """
        return self.rest_get("v1/subscription/quotas")

    # ------------------------------------------------------------------ #
    # 调试辅助                                                            #
    # ------------------------------------------------------------------ #
    def introspect_conn(self, max_chars: int = 2000) -> str:
        """introspect ``bd._api`` 的方法 + 源码（开新 REST 路由前先看）。

        新 endpoint 不确定怎么打时，先看 ``query_chunks`` 等已有方法是
        怎么 delegate 到 ``self.http`` 的，照葫芦画瓢。
        """
        methods = [m for m in dir(self.conn) if not m.startswith("_")]
        try:
            src = inspect.getsource(type(self.conn))[:max_chars]
        except (OSError, TypeError):
            src = "<source unavailable>"
        return f"methods={methods}\n\n--- source head ---\n{src}"
