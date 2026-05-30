"""瞬时网络/SSL 错误重试穿透（无 IO 纯工具）
==============================================

打海外 API（``api.bigdata.com``）时，**首发握手**常因网络抖动抛
``SSLError: UNEXPECTED_EOF`` / ``Connection reset`` / ``RemoteDisconnected``——
尤其经本地出站代理转发时。``bigdata-client`` 的 HTTP 层（直接依赖是
``requests`` + ``aiohttp``）对 **SSL 握手阶段的 EOF** 不做重试，官方异常
体系（见 sdk-reference/exceptions）也不建模这类握手错——所以一次抖动
就直接冒泡成异常，让整个 backfill 中断。

``rc()`` 在 SDK/REST 调用外面再包一层：识别这些**瞬时**错误标记就退避重试，
其它错误（400/认证失败/schema 错）立即抛出不掩盖（NO FALLBACK——只重试
确定瞬时的，不把真错误吞掉）。**限流（429）单独排除**：它该长退避或交给
调用方降速，固定 ``delay``×N 硬重试只会加剧限流，故命中限流标记直接抛。

为什么 marker 用子串匹配
------------------------
这些异常跨 ``ssl`` / ``urllib3`` / ``requests`` / ``http.client`` 多层包装，
类型不统一但 ``str(e)`` 里稳定带这些词。子串匹配比 except 一堆具体异常类
更鲁棒，也不会误吞业务错误（业务错误的文案里不含 'SSL'/'EOF' 这些词）。

用法
----
>>> from bigdata_toolkit import BigdataClient, EntityResolver, rc
>>> client = BigdataClient()                                  # doctest: +SKIP
>>> er = EntityResolver(client)                               # doctest: +SKIP
>>> nvda = rc(lambda: er.resolve_id("NVIDIA", country="US"))  # doctest: +SKIP

循环里注意闭包陷阱（务必绑定循环变量）::

    for kw, dr, lim in jobs:
        # ✅ 绑定，否则所有 lambda 共享最后一次的 kw/dr/lim
        docs = rc(lambda kw=kw, dr=dr, lim=lim:
                  searcher.search_entity(nvda, keyword=kw, chunk_limit=lim, date_range=dr))
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

__all__ = ["rc", "with_retry", "RETRYABLE_MARKERS"]

T = TypeVar("T")

#: ``str(exc)`` 命中任一即视为**瞬时**错误，可退避重试。
#: 来源：实测打 api.bigdata.com 首发握手抖动的异常文案（SSL/EOF/连接重置/超时）。
RETRYABLE_MARKERS = (
    "SSL",
    "EOF",
    "Connection",
    "Max retries",
    "timeout",
    "RemoteDisconnected",
)

#: 即使 ``str(exc)`` 里含上面的瞬时词，命中这些**限流/配额**标记也**不**重试——
#: 429 该长退避或交调用方降速，固定 ``delay``×N 硬重试会加剧限流；配额耗尽重试无意义。
NON_RETRYABLE_MARKERS = (
    "429",
    "Too Many Requests",
    "rate limit",
    "ratelimit",
    "quota",
)


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc)
    # 限流/配额优先级高于瞬时：命中即不重试（避免硬重试加剧限流）。
    low = msg.lower()
    if any(m in low for m in NON_RETRYABLE_MARKERS):
        return False
    return any(marker in msg for marker in RETRYABLE_MARKERS)


def rc(fn: Callable[[], T], *, tries: int = 8, delay: float = 2.0) -> T:
    """跑 ``fn()``，遇到**瞬时**网络/SSL 错误就退避重试，其它错误立即抛。

    Parameters
    ----------
    fn:
        无参 thunk（用 ``lambda: ...`` 包住真正的调用；循环里记得绑定变量）。
    tries:
        最多尝试次数（含首次）。默认 8。
    delay:
        每次重试前 sleep 秒数（固定退避，够穿透首发抖动；不做指数退避避免
        长尾等待）。默认 2.0。

    Returns
    -------
    ``fn()`` 的返回值。

    Raises
    ------
    最后一次的原始异常（重试用尽），或任何**非瞬时**异常（立即抛，不掩盖）。
    """
    last_exc: Exception | None = None
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 —— 故意宽捕获后按 marker 区分
            last_exc = exc
            if i < tries - 1 and _is_retryable(exc):
                time.sleep(delay)
                continue
            raise
    # 理论不可达（循环里要么 return 要么 raise）；为类型完整性兜底。
    assert last_exc is not None
    raise last_exc


def with_retry(*, tries: int = 8, delay: float = 2.0):
    """装饰器版 :func:`rc`，把瞬时重试包到一个函数上。

    >>> @with_retry(tries=5)
    ... def pull(entity_id):                 # doctest: +SKIP
    ...     return rest.latest_surprise(entity_id)
    """

    def deco(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            return rc(lambda: func(*args, **kwargs), tries=tries, delay=delay)

        wrapper.__name__ = getattr(func, "__name__", "wrapped")
        wrapper.__doc__ = func.__doc__
        return wrapper

    return deco
