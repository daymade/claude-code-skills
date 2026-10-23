#!/usr/bin/env python3
"""Normalize timestamp/source metadata without inferring reset completion.

Read saved public responses only. Keep complete bodies in the input file; output
locators rather than echoing potentially unbounded post text or tracker history.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


def timestamp(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string, null, or empty")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return result.astimezone(timezone.utc).isoformat()


def post_id(url):
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.hostname not in ("x.com", "www.x.com", "twitter.com", "www.twitter.com"):
        return None
    match = re.search(r"/status/(\d+)(?:/|$)", parsed.path)
    return match.group(1) if match else None


def posts_index(payload):
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("posts response requires a data array")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("post entries must be objects")
        ident = row.get("id")
        when = timestamp(row.get("createdAtISO"))
        if isinstance(ident, str) and ident and when:
            if ident in result and result[ident] != when:
                raise ValueError("conflicting publication times for one post id")
            result[ident] = when
    return result


def tracker_readings(payload, source, checked_at, posts=None):
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        raise ValueError("tracker response requires an events array")
    known_posts = posts_index(posts) if posts is not None else {}
    rows = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError("tracker entries must be objects")
        provenance = event.get("source")
        source_object = provenance if isinstance(provenance, dict) else {}
        operator = provenance in ("operator", "operator-observed") if isinstance(provenance, str) \
            else source_object.get("origin") == "operator"
        url = event.get("url") or source_object.get("url")
        ident = post_id(url)
        announced = timestamp(event.get("announced_at") if source == "radar"
                              else event.get("announcedAt"))
        original = known_posts.get(ident)
        # A tracker operator can repurpose announced_at for its own observation.
        # Only the separately read original post supplies its publication time.
        posted = original if operator else original or announced if ident else None
        rows.append({"source_record": f"/events/{index}", "source_kind":
                     "operator_observation" if operator else "x_post" if ident else "unknown",
                     "source_url": url, "source_post_id": ident,
                     "source_posted_at": posted, "index_announced_at": announced,
                     "operator_observed_at": timestamp(event.get("observed_at")),
                     "queried_at": checked_at,
                     "tracker_completion_label": event.get("observation_result") or event.get("kind"),
                     "official_completion": "not_inferred"})
    return {"source": source, "queried_at": checked_at, "examined": len(events),
            "records": rows, "coverage": "provided_response_only"}


def community_readings(payload, checked_at, window_start):
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("community response requires a data array")
    start = datetime.fromisoformat(window_start)
    end = datetime.fromisoformat(checked_at)
    if start > end:
        raise ValueError("window_start must not follow checked_at")
    readings, observed = [], []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("community entries must be objects")
        posted = timestamp(row.get("createdAtISO"))
        when = datetime.fromisoformat(posted) if posted else None
        relation = ("unknown" if when is None else "future" if when > end
                    else "pre_window" if when < start else "in_window")
        if when and relation != "future":
            observed.append(when)
        author = row.get("author")
        readings.append({"source_record": f"/data/{index}", "body_pointer": f"/data/{index}/text",
                         "id": row.get("id"), "author": author.get("screenName")
                         if isinstance(author, dict) else None,
                         "source_posted_at": posted, "queried_at": checked_at,
                         "window_relation": relation, "arrival_claim": "not_inferred"})
    return {"source": "community-x", "queried_at": checked_at, "window_start": window_start,
            "examined": len(rows), "coverage": "sampled_not_exhaustive",
            "oldest_observed_at": min(observed).isoformat() if observed else None,
            "latest_observed_at": max(observed).isoformat() if observed else None,
            "window_counts": {k: sum(r["window_relation"] == k for r in readings)
                              for k in ("in_window", "pre_window", "future", "unknown")},
            "records": readings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("radar", "runway", "community-x"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--checked-at", required=True, help="actual retrieval time, timezone required")
    parser.add_argument("--posts-file", type=Path, help="separately read original X posts, for publication times")
    parser.add_argument("--window-start", help="UTC/offset start for a community feedback window")
    parser.add_argument("--limit", type=int, default=10, help="metadata rows to display; full bodies stay in input")
    args = parser.parse_args()
    try:
        checked = timestamp(args.checked_at)
        if checked is None or args.limit < 0:
            raise ValueError("checked_at must be nonempty and limit nonnegative")
        payload = json.loads(args.input.read_text())
        if args.source == "community-x":
            start = timestamp(args.window_start)
            if start is None:
                raise ValueError("community-x requires a nonempty --window-start")
            result = community_readings(payload, checked, start)
        else:
            posts = json.loads(args.posts_file.read_text()) if args.posts_file else None
            result = tracker_readings(payload, args.source, checked, posts)
        records = result["records"]
        result.update(input_file=str(args.input.resolve()), displayed=min(len(records), args.limit),
                      omitted=max(0, len(records) - args.limit), records=records[:args.limit])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
