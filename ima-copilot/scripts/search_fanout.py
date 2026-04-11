#!/usr/bin/env python3
"""
search_fanout.py — Fan-out search across all IMA knowledge bases with
user-defined priority boosting and subset-KB skipping.

Rationale for this shape:
  IMA's OpenAPI has three constraints that force every serious search tool
  into the same pattern:
    1. No cross-KB endpoint — search_knowledge takes a single knowledge_base_id.
    2. No relevance score in results — ranking must be client-side.
    3. Silent 100-hit truncation with no cursor — queries that saturate a KB
       are invisibly capped.

  Given those constraints, the most useful thing a personal wrapper can do
  is (a) fan out to every KB in parallel, (b) warn the user about truncated
  KBs, and (c) group results by KB with user-declared priority groups
  floated to the top. That's what this script does.

Config:
  ~/.config/ima/copilot.json — optional. Shape:
    {
      "priority_kbs": ["kb name 1", "kb name 2"],  # hits from these go first
      "skip_kbs":     ["kb name 3"],               # silently skip (e.g. strict
                                                   # subset of a priority KB)
      "fanout_strategy": "parallel-then-merge"     # reserved for future modes
    }

Credentials:
  Env vars IMA_OPENAPI_CLIENTID and IMA_OPENAPI_APIKEY take precedence.
  Falls back to ~/.config/ima/client_id and ~/.config/ima/api_key.

Usage:
  python3 search_fanout.py "your query here"
  python3 search_fanout.py --max-results 5 "your query"
  python3 search_fanout.py --json "your query"
"""

import argparse
import concurrent.futures
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://ima.qq.com/openapi"
HARD_HIT_CAP = 100  # search_knowledge silently caps at 100, no cursor


def load_credentials():
    client_id = os.environ.get("IMA_OPENAPI_CLIENTID", "").strip()
    api_key = os.environ.get("IMA_OPENAPI_APIKEY", "").strip()

    config_dir = Path.home() / ".config" / "ima"
    if not client_id:
        p = config_dir / "client_id"
        if p.is_file():
            client_id = p.read_text().strip()
    if not api_key:
        p = config_dir / "api_key"
        if p.is_file():
            api_key = p.read_text().strip()

    if not client_id or not api_key:
        sys.exit(
            "error: credentials not found.\n"
            "  set IMA_OPENAPI_CLIENTID and IMA_OPENAPI_APIKEY, or write them to\n"
            "  ~/.config/ima/client_id and ~/.config/ima/api_key (mode 600)."
        )
    return client_id, api_key


def load_config():
    """
    Return (priority_kbs, skip_kbs, strategy). Missing config → empty preferences.

    Config path is resolved in this order:
      1. $IMA_COPILOT_CONFIG if set — used by tests and advanced users
      2. ~/.config/ima/copilot.json — the default XDG location
    """
    env_override = os.environ.get("IMA_COPILOT_CONFIG", "").strip()
    if env_override:
        p = Path(env_override)
    else:
        p = Path.home() / ".config" / "ima" / "copilot.json"
    if not p.is_file():
        return [], [], "parallel-then-merge"
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"error: ~/.config/ima/copilot.json is not valid JSON: {e}")
    return (
        list(data.get("priority_kbs", []) or []),
        list(data.get("skip_kbs", []) or []),
        data.get("fanout_strategy", "parallel-then-merge"),
    )


def api_post(path, body, client_id, api_key):
    """POST JSON to the IMA API. Returns parsed dict on success, raises on failure."""
    url = f"{API_BASE}/{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "ima-openapi-clientid": client_id,
            "ima-openapi-apikey": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error: {e.reason}")
    data = json.loads(payload)
    if data.get("code") != 0:
        raise RuntimeError(f"API error code={data.get('code')} msg={data.get('msg')}")
    return data.get("data", {})


def list_all_kbs(client_id, api_key):
    """Paginate through search_knowledge_base with query='' to enumerate every KB."""
    kbs = []
    cursor = ""
    while True:
        data = api_post(
            "wiki/v1/search_knowledge_base",
            {"query": "", "cursor": cursor, "limit": 50},
            client_id,
            api_key,
        )
        kbs.extend(data.get("info_list", []))
        if data.get("is_end") or not data.get("next_cursor"):
            break
        cursor = data["next_cursor"]
        if len(kbs) > 500:  # defensive upper bound
            break
    return kbs


def search_one_kb(kb, query, client_id, api_key):
    """Returns a dict with kb info + hits + truncation flag. Never raises; errors captured."""
    try:
        data = api_post(
            "wiki/v1/search_knowledge",
            {"query": query, "knowledge_base_id": kb["kb_id"], "cursor": ""},
            client_id,
            api_key,
        )
    except RuntimeError as e:
        return {"kb": kb, "hits": [], "truncated": False, "error": str(e)}

    hits = data.get("info_list", []) or []
    # Silent truncation detection: exact 100 hits with no is_end/next_cursor
    # in the response is the upstream tell-tale.
    truncated = len(hits) >= HARD_HIT_CAP and not data.get("is_end") and not data.get("next_cursor")
    return {"kb": kb, "hits": hits, "truncated": truncated, "error": None}


PERMISSION_DENIED_MARKER = "220030"


def is_permission_denied(result):
    return result["error"] is not None and PERMISSION_DENIED_MARKER in result["error"]


def rank_groups(results, priority_kbs, skip_kbs):
    """
    Partition the per-KB results into four buckets:

      - priority: kbs named in priority_kbs (in that order), with >0 hits
      - others:   every other searchable kb with >0 hits, sorted by hit count
      - denied:   kbs that came back with "no permission" — this is common for
                  subscribed (read-only) KBs where the user doesn't own search
                  access. Collected separately so the user sees the list but
                  it doesn't drown out real results.
      - empty:    searchable kbs that simply had 0 hits for this query
                  (silenced in the text renderer to keep output tight)
    """
    skip_set = set(skip_kbs)
    priority_order = list(priority_kbs)

    by_name = {r["kb"]["kb_name"]: r for r in results}

    priority, denied, others, empty = [], [], [], []

    # Priority group — walk in user-declared order so the output matches intent
    for name in priority_order:
        r = by_name.pop(name, None)
        if r is None or name in skip_set:
            continue
        if is_permission_denied(r):
            denied.append(r)
        elif r["hits"]:
            priority.append(r)
        else:
            empty.append(r)

    # Everyone else
    for name, r in by_name.items():
        if name in skip_set:
            continue
        if is_permission_denied(r):
            denied.append(r)
        elif r["hits"]:
            others.append(r)
        else:
            empty.append(r)

    others.sort(key=lambda r: len(r["hits"]), reverse=True)
    return priority, others, denied, empty


def truncate(s, n=120):
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def render_text(query, priority, others, denied, skipped_cfg, total_kbs_listed, max_per_kb):
    searchable_with_hits = len(priority) + len(others)
    total_hits = sum(len(r["hits"]) for r in priority + others)
    truncated_kbs = [r["kb"]["kb_name"] for r in priority + others if r["truncated"]]

    print(f'\n🔍 Searched "{query}" across {total_kbs_listed} knowledge bases')
    if skipped_cfg:
        names = ", ".join(r["kb"]["kb_name"] for r in skipped_cfg)
        print(f"   skipped via config: {names}")
    print()

    def render_group(prefix, group, note=""):
        for r in group:
            kb = r["kb"]
            hits = r["hits"]
            label = f"{prefix} {kb['kb_name']} — {len(hits)} hit{'s' if len(hits) != 1 else ''}"
            if note:
                label += f" {note}"
            if r["truncated"]:
                label += " (⚠️ truncated at 100)"
            print(label)
            for i, hit in enumerate(hits[:max_per_kb], 1):
                title = hit.get("title", "(no title)")
                print(f"  {i}. {title}")
                snippet = hit.get("highlight_content", "") or ""
                if snippet:
                    print(f"     {truncate(snippet)}")
            if len(hits) > max_per_kb:
                print(f"  … ({len(hits) - max_per_kb} more)")
            print()

    if priority:
        render_group("🥇", priority, "(priority)")
    if others:
        render_group("📚", others)

    if not priority and not others:
        print("(no hits in any searchable knowledge base)\n")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Total: {total_hits} hits across {searchable_with_hits} kb(s) with results")

    if denied:
        print(
            f"\nℹ️  {len(denied)} kb(s) returned 'no permission' (typical for subscribed/read-only KBs):"
        )
        for r in denied:
            print(f"   - {r['kb']['kb_name']}")

    if truncated_kbs:
        print(
            f"\n⚠️  {len(truncated_kbs)} kb(s) hit the 100-result ceiling; try a narrower query:"
        )
        for name in truncated_kbs:
            print(f"   - {name}")


def render_json(query, priority, others, denied, skipped_cfg):
    def export(group):
        return [
            {
                "kb_id": r["kb"]["kb_id"],
                "kb_name": r["kb"]["kb_name"],
                "hit_count": len(r["hits"]),
                "truncated": r["truncated"],
                "error": r["error"],
                "hits": [
                    {
                        "title": h.get("title"),
                        "media_id": h.get("media_id"),
                        "parent_folder_id": h.get("parent_folder_id"),
                        "highlight_content": h.get("highlight_content"),
                    }
                    for h in r["hits"]
                ],
            }
            for r in group
        ]

    out = {
        "query": query,
        "priority": export(priority),
        "others": export(others),
        "denied": [r["kb"]["kb_name"] for r in denied],
        "skipped_by_config": [r["kb"]["kb_name"] for r in skipped_cfg],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("query", help="Search query string")
    ap.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Max hits to render per KB in text mode (default: 5)",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Parallel worker count for fan-out calls (default: 12)",
    )
    ap.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = ap.parse_args(argv)

    client_id, api_key = load_credentials()
    priority_kbs, skip_kbs, _strategy = load_config()

    try:
        all_kbs = list_all_kbs(client_id, api_key)
    except RuntimeError as e:
        sys.exit(f"error listing knowledge bases: {e}")
    if not all_kbs:
        sys.exit("no knowledge bases accessible with these credentials")

    to_search = [kb for kb in all_kbs if kb["kb_name"] not in set(skip_kbs)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(
                lambda kb: search_one_kb(kb, args.query, client_id, api_key),
                to_search,
            )
        )

    # Enumerate config-skipped KBs separately so the user sees which ones
    # were intentionally filtered out vs which ones genuinely had no results.
    skipped_cfg_results = [
        {"kb": kb, "hits": [], "truncated": False, "error": None}
        for kb in all_kbs
        if kb["kb_name"] in set(skip_kbs)
    ]

    priority, others, denied, _empty = rank_groups(results, priority_kbs, skip_kbs)

    if args.json:
        render_json(args.query, priority, others, denied, skipped_cfg_results)
    else:
        render_text(
            args.query,
            priority,
            others,
            denied,
            skipped_cfg_results,
            total_kbs_listed=len(all_kbs),
            max_per_kb=args.max_results,
        )


if __name__ == "__main__":
    main()
