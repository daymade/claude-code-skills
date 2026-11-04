#!/usr/bin/env python3
"""Preview/apply an exact, audited review-domain metadata repair."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from core.review_queue import ReviewQueue, ReviewQueueError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="JSON: ids,file,from_domain,to_domain,reason,by")
    parser.add_argument("--db", help="Existing queue database; omitted uses the configured transcript-fixer store")
    parser.add_argument("--apply", action="store_true", help="Commit the exact metadata change; default is preview")
    args = parser.parse_args()
    try:
        plan = json.loads(Path(args.plan).read_text())
        expected = {"ids", "file", "from_domain", "to_domain", "reason", "by"}
        if not isinstance(plan, dict) or set(plan) != expected:
            raise ValueError("plan must contain exactly: " + ", ".join(sorted(expected)))
        if not isinstance(plan["ids"], list):
            raise ValueError("ids must be an array")
        if args.db:
            queue = ReviewQueue(Path(args.db))
        else:
            from cli.commands import _get_review_queue
            queue = _get_review_queue()
        result = queue.repair_domain(plan["ids"], file_path=plan["file"],
                                     from_domain=plan["from_domain"], to_domain=plan["to_domain"],
                                     reason=plan["reason"], by=plan["by"], apply=args.apply)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ReviewQueueError) as exc:
        print(json.dumps({"error": str(exc), "applied": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
