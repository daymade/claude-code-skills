#!/usr/bin/env python3
"""
Validate financial data JSON output from collect_data.py.
Checks completeness, consistency, and sanity of collected data.

Usage:
    python validate_data.py path/to/output.json

Returns JSON validation report to stdout.
"""
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import json
import sys
from pathlib import Path


def validate(data: dict) -> dict:
    """Validate financial data JSON. Returns validation report."""
    errors = []
    warnings = []

    # 1. Required top-level fields
    for field in ["ticker", "company_name", "data_date", "market_data",
                  "income_statement", "cash_flow", "balance_sheet", "wacc_inputs"]:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return {"status": "error", "errors": errors, "warnings": warnings}

    md = data["market_data"]

    # 2. Market data sanity
    if md.get("current_price") is not None:
        if md["current_price"] <= 0:
            errors.append(f"Invalid stock price: {md['current_price']}")
        if md["current_price"] > 10000:
            warnings.append(f"Unusually high stock price: ${md['current_price']}")

    if md.get("shares_outstanding_millions") is not None:
        if md["shares_outstanding_millions"] <= 0:
            errors.append(f"Invalid shares outstanding: {md['shares_outstanding_millions']}")

    if md.get("beta_5y_monthly") is not None:
        beta = md["beta_5y_monthly"]
        if beta < 0.1 or beta > 5.0:
            warnings.append(f"Unusual beta: {beta} (expected 0.3-3.0)")

    # 3. Market cap cross-check
    if md.get("current_price") and md.get("shares_outstanding_millions") and md.get("market_cap_millions"):
        computed = md["current_price"] * md["shares_outstanding_millions"]
        reported = md["market_cap_millions"]
        pct_diff = abs(computed - reported) / reported
        if pct_diff > 0.05:
            # yfinance sharesOutstanding is basic; marketCap may use diluted. Known discrepancy.
            warnings.append(f"Market cap mismatch ({pct_diff:.1%}): Price×Shares(basic)={computed:.0f}M vs Reported={reported:.0f}M. Likely basic vs diluted shares.")

    # 4. Income statement completeness
    is_data = data.get("income_statement", {})
    years_with_data = 0
    for year, vals in is_data.items():
        if isinstance(vals, dict) and vals.get("revenue") is not None:
            years_with_data += 1
            # Revenue should be positive
            if vals["revenue"] <= 0:
                warnings.append(f"Non-positive revenue in {year}: {vals['revenue']}")
            # EBIT margin sanity
            if vals.get("ebit") is not None and vals["revenue"] > 0:
                margin = vals["ebit"] / vals["revenue"]
                if margin < -1.0 or margin > 0.8:
                    warnings.append(f"Unusual EBIT margin in {year}: {margin:.1%}")

    if years_with_data == 0:
        errors.append("No income statement data available for any year")
    elif years_with_data < 3:
        warnings.append(f"Only {years_with_data} years of income statement data (recommend ≥3)")

    # 5. Cash flow: CapEx sign convention
    cf_data = data.get("cash_flow", {})
    for year, vals in cf_data.items():
        if isinstance(vals, dict) and vals.get("capex") is not None:
            if vals["capex"] > 0:
                warnings.append(f"CapEx is positive in {year} ({vals['capex']}). Expected negative (outflow).")

    # 6. Balance sheet: Net debt consistency
    bs_data = data.get("balance_sheet", {})
    for year, vals in bs_data.items():
        if isinstance(vals, dict):
            td = vals.get("total_debt")
            ce = vals.get("cash_and_equivalents")
            nd = vals.get("net_debt")
            if td is not None and ce is not None and nd is not None:
                expected_nd = td - ce
                if abs(expected_nd - nd) > 1.0:  # Allow $1M rounding
                    errors.append(f"Net debt inconsistency in {year}: total_debt({td}) - cash({ce}) = {expected_nd} ≠ {nd}")

    # 7. WACC inputs
    wacc = data.get("wacc_inputs", {})
    rfr = wacc.get("risk_free_rate")
    if rfr is not None:
        if rfr < 0 or rfr > 0.15:
            warnings.append(f"Unusual risk-free rate: {rfr:.2%} (expected 1-8%)")
    else:
        warnings.append("Risk-free rate is missing")

    # 8. NaN years tracking
    meta = data.get("metadata", {})
    nan_years = meta.get("_nan_years", [])
    if nan_years:
        warnings.append(f"NaN years detected: {nan_years}. Supplement from 10-K before using in models.")

    # 9. Data source attribution
    for section in ["income_statement", "cash_flow", "balance_sheet"]:
        section_data = data.get(section, {})
        for year, vals in section_data.items():
            if isinstance(vals, dict) and "_source" not in vals:
                warnings.append(f"Missing _source attribution in {section}.{year}")

    status = "error" if errors else ("warning" if warnings else "success")
    return {
        "status": status,
        "ticker": data.get("ticker"),
        "years_with_data": years_with_data,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_data.py <json_file>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    if not Path(json_path).exists():
        print(json.dumps({"status": "error", "errors": [f"File not found: {json_path}"]}))
        sys.exit(1)

    data = json.loads(Path(json_path).read_text())
    report = validate(data)

    print(json.dumps(report, indent=2))

    if report["status"] == "error":
        sys.exit(1)
    elif report["status"] == "warning":
        sys.exit(0)  # Warnings are OK, just informational
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
