#!/usr/bin/env python3
"""
Collect real financial data for a US publicly traded company.
Output: structured JSON consumable by downstream financial skills.

Usage:
    python collect_data.py TICKER [--years 5] [--output path/to/output.json]

Examples:
    python collect_data.py META
    python collect_data.py AAPL --years 3 --output /tmp/aapl_data.json
    python collect_data.py NVDA --years 5

Dependencies: yfinance, pandas (via uv inline or pip)
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["yfinance>=0.2.0", "pandas>=2.0.0"]
# ///

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

# Field name aliases — yfinance row indices vary across versions
FIELD_ALIASES = {
    "revenue": ["Total Revenue", "Revenue", "Operating Revenue"],
    "ebit": ["Operating Income", "EBIT"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "tax_expense": ["Tax Provision", "Income Tax Expense"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "capex": ["Capital Expenditure", "Capital Expenditures"],
    "operating_cash_flow": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "depreciation_amortization": ["Depreciation And Amortization", "Depreciation Amortization Depletion"],
    "free_cash_flow": ["Free Cash Flow"],
    "change_in_nwc": ["Change In Working Capital", "Changes In Working Capital"],
    "sbc": ["Stock Based Compensation"],
    "total_debt": ["Total Debt"],
    "long_term_debt": ["Long Term Debt"],
    "short_term_debt": ["Short Long Term Debt", "Current Debt"],
    "cash": ["Cash And Cash Equivalents"],
    "short_investments": ["Other Short Term Investments", "Short Term Investments"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "total_assets": ["Total Assets"],
    "total_equity": ["Stockholders Equity", "Total Equity Gross Minority Interest"],
}


def safe_get(df: pd.DataFrame, field_key: str, col) -> float | None:
    """Safely extract a value from a DataFrame using alias chain."""
    aliases = FIELD_ALIASES.get(field_key, [field_key])
    for alias in aliases:
        if alias in df.index:
            val = df.loc[alias, col]
            if pd.notna(val):
                return float(val)
    return None


def get_year_col(df: pd.DataFrame, year: int):
    """Find the column matching a target year in a yfinance DataFrame."""
    matches = [c for c in df.columns if c.year == year]
    return matches[0] if matches else None


def collect_market_data(ticker_obj: yf.Ticker) -> dict:
    """Collect real-time market data."""
    info = ticker_obj.info
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    shares_raw = info.get("sharesOutstanding")
    shares = shares_raw / 1e6 if shares_raw else None
    mcap_raw = info.get("marketCap")
    mcap = mcap_raw / 1e6 if mcap_raw else None
    beta = info.get("beta")

    return {
        "current_price": price,
        "shares_outstanding_millions": round(shares, 2) if shares else None,
        "market_cap_millions": round(mcap, 2) if mcap else None,
        "beta_5y_monthly": round(beta, 3) if beta else None,
    }


def collect_risk_free_rate() -> float | None:
    """Get 10Y Treasury yield as risk-free rate proxy."""
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="5d")
        if hist.empty:
            return None
        yield_pct = hist["Close"].iloc[-1]
        return round(float(yield_pct) / 100, 4)  # Convert percentage to decimal
    except Exception:
        return None


def collect_income_statement(ticker_obj: yf.Ticker, years: list[int]) -> dict:
    """Collect income statement data for specified years."""
    try:
        financials = ticker_obj.financials
    except Exception:
        return {str(y): {"_source": "yfinance error"} for y in years}

    if financials is None or financials.empty:
        return {str(y): {"_source": "yfinance returned empty"} for y in years}

    result = {}
    nan_years = []
    for year in years:
        col = get_year_col(financials, year)
        if col is None:
            result[str(year)] = {"_source": f"yfinance has no column for {year}"}
            nan_years.append(year)
            continue

        revenue = safe_get(financials, "revenue", col)
        ebit = safe_get(financials, "ebit", col)

        if revenue is None and ebit is None:
            nan_years.append(year)
            result[str(year)] = {
                "revenue": None, "ebit": None, "ebitda": None,
                "tax_expense": None, "net_income": None,
                "_source": f"yfinance returned NaN for {year} — supplement from 10-K filing",
            }
        else:
            result[str(year)] = {
                "revenue": revenue,
                "ebit": ebit,
                "ebitda": safe_get(financials, "ebitda", col),
                "tax_expense": safe_get(financials, "tax_expense", col),
                "net_income": safe_get(financials, "net_income", col),
                "_source": "yfinance",
            }

    return result, nan_years


def collect_cash_flow(ticker_obj: yf.Ticker, years: list[int]) -> dict:
    """Collect cash flow data."""
    try:
        cf = ticker_obj.cashflow
    except Exception:
        return {str(y): {"_source": "yfinance error"} for y in years}, []

    if cf is None or cf.empty:
        return {str(y): {"_source": "yfinance returned empty"} for y in years}, years

    result = {}
    nan_years = []
    for year in years:
        col = get_year_col(cf, year)
        if col is None:
            result[str(year)] = {"_source": f"yfinance has no column for {year}"}
            nan_years.append(year)
            continue

        ocf = safe_get(cf, "operating_cash_flow", col)
        capex = safe_get(cf, "capex", col)

        if ocf is None and capex is None:
            nan_years.append(year)
            result[str(year)] = {
                "operating_cash_flow": None, "capex": None,
                "depreciation_amortization": None, "free_cash_flow": None,
                "change_in_nwc": None, "sbc": None,
                "_source": f"yfinance returned NaN for {year}",
            }
        else:
            result[str(year)] = {
                "operating_cash_flow": ocf,
                "capex": capex,  # Negative = outflow (preserved)
                "depreciation_amortization": safe_get(cf, "depreciation_amortization", col),
                "free_cash_flow": safe_get(cf, "free_cash_flow", col),
                "change_in_nwc": safe_get(cf, "change_in_nwc", col),
                "sbc": safe_get(cf, "sbc", col),
                "_source": "yfinance",
            }

    return result, nan_years


def collect_balance_sheet(ticker_obj: yf.Ticker, latest_year: int) -> dict:
    """Collect balance sheet data for the latest year."""
    try:
        bs = ticker_obj.balance_sheet
    except Exception:
        return {str(latest_year): {"_source": "yfinance error"}}

    if bs is None or bs.empty:
        return {str(latest_year): {"_source": "yfinance returned empty"}}

    col = get_year_col(bs, latest_year)
    if col is None:
        return {str(latest_year): {"_source": f"yfinance has no column for {latest_year}"}}

    total_debt = safe_get(bs, "total_debt", col)
    if total_debt is None:
        lt = safe_get(bs, "long_term_debt", col) or 0
        st = safe_get(bs, "short_term_debt", col) or 0
        total_debt = lt + st if (lt or st) else None

    cash = safe_get(bs, "cash", col)
    short_inv = safe_get(bs, "short_investments", col)
    cash_equiv = (cash or 0) + (short_inv or 0) if (cash is not None or short_inv is not None) else None
    net_debt = (total_debt - cash_equiv) if (total_debt is not None and cash_equiv is not None) else None

    return {
        str(latest_year): {
            "total_debt": total_debt,
            "cash_and_equivalents": cash_equiv,
            "net_debt": round(net_debt, 2) if net_debt is not None else None,
            "current_assets": safe_get(bs, "current_assets", col),
            "current_liabilities": safe_get(bs, "current_liabilities", col),
            "total_assets": safe_get(bs, "total_assets", col),
            "total_equity": safe_get(bs, "total_equity", col),
            "_source": "yfinance",
        }
    }


def collect_analyst_estimates(ticker_obj: yf.Ticker) -> dict:
    """Collect analyst consensus estimates."""
    result = {"revenue_next_fy": None, "revenue_fy_after": None, "eps_next_fy": None, "_source": "missing"}

    try:
        rev_est = ticker_obj.revenue_estimate
        if rev_est is not None and not rev_est.empty:
            if "0y" in rev_est.index:
                result["revenue_next_fy"] = float(rev_est.loc["0y", "avg"]) / 1e6 if pd.notna(rev_est.loc["0y", "avg"]) else None
            if "+1y" in rev_est.index:
                result["revenue_fy_after"] = float(rev_est.loc["+1y", "avg"]) / 1e6 if pd.notna(rev_est.loc["+1y", "avg"]) else None
            result["_source"] = "yfinance revenue_estimate"
    except Exception:
        pass

    try:
        eps = ticker_obj.eps_trend
        if eps is not None and not eps.empty:
            if "0y" in eps.index:
                val = eps.loc["0y", "current"] if "current" in eps.columns else eps.iloc[eps.index.get_loc("0y"), 0]
                result["eps_next_fy"] = float(val) if pd.notna(val) else None
    except Exception:
        pass

    return result


def main():
    parser = argparse.ArgumentParser(description="Collect financial data for a US public company")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., META, AAPL)")
    parser.add_argument("--years", type=int, default=5, help="Number of historical years (default: 5)")
    parser.add_argument("--output", help="Output JSON file path (default: {TICKER}_financial_data.json)")
    args = parser.parse_args()

    ticker_symbol = args.ticker.upper()
    current_year = date.today().year
    # Exclude current year if annual report not yet filed (typically before Q4 earnings)
    latest_full_year = current_year - 1
    target_years = list(range(latest_full_year - args.years + 1, latest_full_year + 1))

    output_path = args.output or f"{ticker_symbol}_financial_data.json"

    print(f"Collecting data for {ticker_symbol} ({target_years[0]}-{target_years[-1]})...")
    start_time = time.time()

    ticker_obj = yf.Ticker(ticker_symbol)

    # Verify ticker is valid
    info = ticker_obj.info
    if not info or info.get("regularMarketPrice") is None:
        print(f"ERROR: {ticker_symbol} not found or no market data available", file=sys.stderr)
        sys.exit(1)

    company_name = info.get("longName") or info.get("shortName") or ticker_symbol

    # Collect all data
    print("  Market data...", end=" ", flush=True)
    market_data = collect_market_data(ticker_obj)
    print("OK")

    print("  Risk-free rate...", end=" ", flush=True)
    rfr = collect_risk_free_rate()
    print(f"{rfr:.4f}" if rfr else "MISSING")

    print("  Income statement...", end=" ", flush=True)
    income_data, is_nan_years = collect_income_statement(ticker_obj, target_years)
    print(f"OK (NaN years: {is_nan_years or 'none'})")

    print("  Cash flow...", end=" ", flush=True)
    cf_data, cf_nan_years = collect_cash_flow(ticker_obj, target_years)
    print(f"OK (NaN years: {cf_nan_years or 'none'})")

    print("  Balance sheet...", end=" ", flush=True)
    bs_data = collect_balance_sheet(ticker_obj, latest_full_year)
    print("OK")

    print("  Analyst estimates...", end=" ", flush=True)
    estimates = collect_analyst_estimates(ticker_obj)
    print("OK" if estimates["_source"] != "missing" else "PARTIAL/MISSING")

    elapsed = round(time.time() - start_time, 1)
    all_nan_years = sorted(set(is_nan_years + cf_nan_years))

    # Assemble output
    output = {
        "ticker": ticker_symbol,
        "company_name": company_name,
        "data_date": date.today().isoformat(),
        "currency": "USD",
        "unit": "millions_usd",
        "data_sources": {
            "market_data": "yfinance (live)",
            "historical_financials": "yfinance annual financials",
            "risk_free_rate": "yfinance ^TNX (10Y Treasury)",
        },
        "market_data": market_data,
        "income_statement": income_data,
        "cash_flow": cf_data,
        "balance_sheet": bs_data,
        "wacc_inputs": {
            "risk_free_rate": rfr,
            "beta": market_data.get("beta_5y_monthly"),
            "credit_rating": None,
            "_source": "yfinance + ^TNX",
        },
        "analyst_estimates": estimates,
        "metadata": {
            "_capex_convention": "negative = cash outflow (yfinance convention)",
            "_fcf_note": "yfinance FCF = OperatingCF + CapEx. Does NOT deduct SBC.",
            "_nan_years": all_nan_years,
            "_collection_duration_seconds": elapsed,
            "_target_years": target_years,
        },
    }

    # Write output
    Path(output_path).write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nSaved to {output_path} ({elapsed}s)")

    # Summary
    if all_nan_years:
        print(f"\n⚠️  WARNING: Years {all_nan_years} have missing data (NaN from yfinance).")
        print("   Supplement from 10-K filings or SEC EDGAR before using in models.")

    # Quick sanity check
    if market_data["current_price"] and market_data["shares_outstanding_millions"]:
        computed_mcap = market_data["current_price"] * market_data["shares_outstanding_millions"]
        reported_mcap = market_data["market_cap_millions"]
        if reported_mcap and abs(computed_mcap - reported_mcap) / reported_mcap > 0.05:
            print(f"⚠️  Market cap mismatch: Price×Shares={computed_mcap:.0f}M vs Reported={reported_mcap:.0f}M")


if __name__ == "__main__":
    main()
