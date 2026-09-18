#!/usr/bin/env python3
"""Diff the official /v1/audio/asr/sse request-field table against REQUEST_PARAMS.

Why this exists: per-word timestamps were missing for months because nobody read the
request-side field table — `enable_timestamp` was documented the whole time, and the
response-side table (which was read) has no word-level field to hint at it. Parameters
are not billed separately, so a documented field we do not send is pure loss.

Exit 0 = manifest covers every documented field. Exit 1 = docs gained a field we do not
mention; decide whether to send it, then add it to REQUEST_PARAMS with a reason.
Exit 2 = could not fetch or parse the page (never silently "pass").
"""
import html
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asr_transcribe import REQUEST_PARAMS  # noqa: E402

DOC_URL = "https://stepfun.mintlify.app/zh/api-reference/audio/asr-sse"
# 实测 2026-09-18：本机代理对该文档域名的 CONNECT 返回 503（API 域名不受影响），
# 走代理会让本检查恒定 exit 2。直连。
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TYPES = r"(?:string|bool|boolean|int|integer|float|number|array)"
# object 是容器（audio / input / transcription / format），不是可传的参数；
# 它的子字段会各自作为叶子被抓到，所以容器名排除掉不会漏。
CONTAINER_TYPE = r"object"


def documented_fields(page: str) -> set[str]:
    page = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    # 页首目录里「请求头 请求参数 请求示例」是连着的，取第一个会切出 5 个字符的空区段。
    # 只认后面真的跟着字段定义的那一处。
    for m in re.finditer("请求参数", txt):
        end = txt.find("请求示例", m.end())
        if end < 0:
            continue
        body = txt[m.end():end]
        if len(body) > 200 and re.search(rf"\b[a-z][a-z0-9_]* {TYPES}\b", body):
            leaves = set(re.findall(rf"\b([a-z][a-z0-9_]*) {TYPES}\b", body))
            return leaves - set(re.findall(rf"\b([a-z][a-z0-9_]*) {CONTAINER_TYPE}\b", body))
    raise SystemExit("EXIT 2: 页面结构变了，找不到含字段定义的「请求参数」区段")


def fetch() -> str:
    with NO_PROXY.open(DOC_URL, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def selftest() -> int:
    """双向标定。不跑这个就不该相信上面的结论。"""
    try:
        doc = documented_fields(fetch())
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: 抓/解析官方文档失败: {e}", file=sys.stderr)
        return 2
    ok = True

    # 假阳性侧：真实清单必须通过，否则每次都在喊狼来了。
    missing = doc - {p.rsplit(".", 1)[-1] for p in REQUEST_PARAMS}
    print(f"[假阳性] 真实清单 vs 官方 {len(doc)} 字段 → "
          f"{'通过' if not missing else f'误报 {sorted(missing)}'}")
    ok &= not missing

    # 召回侧：用真实历史缺口。enable_timestamp 一直写在官方请求字段表里，
    # 而客户端从不发送、解析器丢弃载荷，逐词时间戳因此丢了好几个月。
    # 检测器抓不住这个历史案例，就没有装备的价值。
    holed = {k: v for k, v in REQUEST_PARAMS.items() if not k.endswith("enable_timestamp")}
    caught = doc - {p.rsplit(".", 1)[-1] for p in holed}
    hit = "enable_timestamp" in caught
    print(f"[召回]   清单挖掉 enable_timestamp → {'抓到' if hit else '没抓到（检测器无效）'}")
    ok &= hit

    print("标定通过" if ok else "标定失败：这个检查器不该被信任")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    try:
        page = fetch()
    except Exception as e:  # noqa: BLE001
        print(f"EXIT 2: 抓不到官方文档 {DOC_URL}: {e}", file=sys.stderr)
        return 2

    doc = documented_fields(page)
    if len(doc) < 5:
        print(f"EXIT 2: 只解析出 {len(doc)} 个字段，提取器多半坏了: {sorted(doc)}", file=sys.stderr)
        return 2

    ours = {p.rsplit(".", 1)[-1] for p in REQUEST_PARAMS}
    missing = sorted(doc - ours)
    if missing:
        print("官方文档有、我们清单里没有的字段：", file=sys.stderr)
        for f in missing:
            print(f"  - {f}", file=sys.stderr)
        print("\n参数不额外计费。决定发不发，然后连同理由写进 asr_transcribe.py 的 "
              "REQUEST_PARAMS。", file=sys.stderr)
        return 1

    print(f"OK: 官方 {len(doc)} 个请求字段全部在 REQUEST_PARAMS 中有交代")
    stale = sorted(ours - doc - {"data"})
    if stale:
        print(f"（清单里有、当前文档未列：{stale} —— 可能是文档改了或我们探测到的未公开字段）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
