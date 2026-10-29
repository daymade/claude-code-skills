#!/usr/bin/env python3
"""Emit deterministic synthetic oversized JSON for the source eval corpus."""
import json
import sys

records = [{"id": f"record-{n:04d}", "text": "synthetic", "detail": "x" * 1024}
           for n in range(257)]
records[-1]["text"] = "中文粘贴与编辑已送达"
requests = [
    {"request_kind": "turn", "thread_source": "user", "turn": "first"},
    {"request_kind": "turn", "thread_source": "thread_title", "turn": "title"},
    {"request_kind": "turn", "thread_source": "user", "turn": "continued"},
]
json.dump({"diagnostic_padding": {"unexpected_nested_body": "y" * 65536},
           "record_count": len(records), "records": records, "requests": requests},
          sys.stdout, ensure_ascii=False)
sys.stdout.write("\n")
sys.stderr.write("synthetic producer completed\n")
