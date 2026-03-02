# yfinance Pitfalls & Field Mapping

## NaN Year Patterns

yfinance frequently returns NaN for older fiscal years. Observed patterns:

| Ticker | NaN Years | Notes |
|--------|-----------|-------|
| META | 2020, 2021 | All fields NaN; must supplement from 10-K |
| General | Varies | Older years (>3 years back) are less reliable |

**Workaround**: Check every field with `pd.notna()`. Report NaN years to user. Never fill with estimates.

## Field Name Variants

yfinance row index names are not fully stable across versions. Use fallback chains:

```python
FIELD_ALIASES = {
    "revenue": ["Total Revenue", "Revenue", "Operating Revenue"],
    "ebit": ["Operating Income", "EBIT"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "tax": ["Tax Provision", "Income Tax Expense", "Tax Effect Of Unusual Items"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "capex": ["Capital Expenditure", "Capital Expenditures"],
    "ocf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "da": ["Depreciation And Amortization", "Depreciation Amortization Depletion"],
    "fcf": ["Free Cash Flow"],
    "nwc": ["Change In Working Capital", "Changes In Working Capital"],
    "total_debt": ["Total Debt"],
    "cash": ["Cash And Cash Equivalents"],
    "short_investments": ["Other Short Term Investments", "Short Term Investments"],
    "sbc": ["Stock Based Compensation"],
}

def safe_get(df, aliases, col):
    for alias in aliases:
        if alias in df.index:
            val = df.loc[alias, col]
            return float(val) if pd.notna(val) else None
    return None
```

## Datetime Column Index

yfinance returns DataFrame columns as `pandas.Timestamp`, not integer years:

```python
# ❌ WRONG
financials[2024]  # KeyError

# ✅ RIGHT
year_col = [c for c in financials.columns if c.year == 2024][0]
financials.loc["Total Revenue", year_col]
```

## Shares Outstanding Variants

```python
# Preferred: diluted
shares = info.get("sharesOutstanding")  # Basic shares
# Alternative
shares = info.get("impliedSharesOutstanding")  # May be more accurate
```

## Risk-Free Rate via ^TNX

```python
tnx = yf.Ticker("^TNX")
hist = tnx.history(period="1d")
risk_free_rate = hist["Close"].iloc[-1] / 100  # Convert from percentage
```

**Pitfall**: ^TNX returns yield as percentage (e.g., 4.3), not decimal (0.043). Divide by 100.

## Analyst Estimates

```python
ticker = yf.Ticker("META")

# Revenue estimates
rev_est = ticker.revenue_estimate  # DataFrame with columns: avg, low, high, ...
# Rows: "0q" (current quarter), "+1q", "0y" (current year), "+1y"

# EPS estimates
eps_est = ticker.eps_trend  # Similar structure
```

**Pitfall**: These APIs change between yfinance versions. Always wrap in try/except.

## FCF Definition Mismatch

| Source | FCF Definition | META 2024 |
|--------|---------------|-----------|
| yfinance | Operating CF + CapEx | ~$54.1B |
| Morgan Stanley DCF | EBITDA - Taxes - CapEx - NWC - SBC | ~$37.9B |
| Difference | SBC (~$22B) + other adjustments | ~30% gap |

**Always flag this in output metadata.** Downstream DCF skills need to decide whether to use yfinance FCF or reconstruct from components.
