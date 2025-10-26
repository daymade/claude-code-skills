#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chartkit.py - Minimal chart renderer for ppt-creator
Usage:
  python resources/scripts/chartkit.py \
    --data path/to/data.csv \
    --type line \
    --x date \
    --y sales profit \
    --out output/assets \
    --filename kpi_trend.png \
    --title "Monthly KPIs"

Notes:
- Requires: pandas, matplotlib
- Fallback: If packages are unavailable, print an instruction message and exit(0)
- Does not set brand-specific colors; relies on matplotlib defaults to remain readable.
"""
import argparse, sys, os

def _lazy_imports():
    try:
        import pandas as pd  # noqa: F401
        import matplotlib.pyplot as plt  # noqa: F401
        return True
    except Exception as e:
        sys.stdout.write(f"[chartkit] Missing dependency: {e}\n")
        sys.stdout.write("[chartkit] Fallback: describe chart spec in text instead of rendering PNG.\n")
        return False

def _read_data(path):
    import pandas as pd
    if path.lower().endswith(".csv"):
        return pd.read_csv(path)
    elif path.lower().endswith((".json", ".ndjson")):
        return pd.read_json(path, lines=path.lower().endswith(".ndjson"))
    else:
        raise ValueError("Only CSV/JSON supported")

def _ensure_outdir(p):
    os.makedirs(p, exist_ok=True)

def render_chart(df, chart_type, x, y_cols, title, out_path):
    import matplotlib.pyplot as plt
    fig = plt.figure()
    ax = fig.gca()
    if chart_type in ("line", "area"):
        for col in y_cols:
            ax.plot(df[x], df[col], label=str(col))
        if chart_type == "area":
            ax.fill_between(df[x], df[y_cols[0]], alpha=0.2)
    elif chart_type in ("bar", "barh"):
        import numpy as np
        idx = np.arange(len(df[x]))
        width = 0.8/ max(1, len(y_cols))
        for i, col in enumerate(y_cols):
            if chart_type == "bar":
                ax.bar(idx + i*width, df[col], width, label=str(col))
            else:
                ax.barh(idx + i*width, df[col], width, label=str(col))
        ax.set_xticks(idx + width*(len(y_cols)-1)/2)
        ax.set_xticklabels(df[x], rotation=0, ha="center")
    elif chart_type == "scatter":
        for col in y_cols:
            ax.scatter(df[x], df[col], label=str(col))
    elif chart_type == "hist":
        ax.hist(df[y_cols[0]], bins=20)
    elif chart_type == "waterfall":
        # Simple waterfall for a single series
        import numpy as np
        vals = df[y_cols[0]].values
        cum = np.cumsum(vals) - vals
        ax.bar(df[x], vals, bottom=cum)
        ax.plot(df[x], cum + vals, marker="o")
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")
    ax.set_title(title if title else "")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--type", required=True, choices=["line","area","bar","barh","scatter","hist","waterfall"])
    ap.add_argument("--x", required=True)
    ap.add_argument("--y", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--filename", required=True)
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    if not _lazy_imports():
        # Soft fail: print instructions for textual fallback
        sys.stdout.write(f"[chartkit] Would have rendered {args.type} chart to {args.out}/{args.filename}\n")
        return 0

    import pandas as pd
    df = _read_data(args.data)
    if args.x not in df.columns:
        raise SystemExit(f"[chartkit] Missing x column: {args.x}")
    for c in args.y:
        if c not in df.columns:
            raise SystemExit(f"[chartkit] Missing y column: {c}")
    _ensure_outdir(args.out)
    out_path = os.path.join(args.out, args.filename)
    render_chart(df, args.type, args.x, args.y, args.title, out_path)
    sys.stdout.write(f"[chartkit] Saved {out_path}\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
