---
name: financial-data-collector
description: "Collect real financial data for any US publicly traded company from free public sources (yfinance). Output structured JSON consumable by downstream financial skills (DCF modeling, comps analysis, earnings review). Handles market data (price, shares, beta), historical financials (income statement, cash flow, balance sheet), WACC inputs, and analyst estimates. Use when users request collect data for ticker, get financials for company, pull market data, gather DCF inputs, or any task requiring structured financial data before analysis. Also triggers on financial data, company data, stock data."
---

# Financial Data Collector

Collect and validate real financial data for US public companies using free data sources.
Output is a standardized JSON file ready for consumption by other financial skills.

## Critical Constraints

**NO FALLBACK values.** If a field cannot be retrieved, set it to `null` with `_source: "missing"`.
Never substitute defaults (e.g., `beta or 1.0`). The downstream skill decides how to handle missing data.

**Data source attribution is mandatory.** Every data section must have a `_source` field.

**CapEx sign convention:** yfinance returns CapEx as negative (cash outflow). Preserve the original sign. Document the convention in output metadata. Do NOT flip signs.

**yfinance FCF ≠ Investment bank FCF.** yfinance FCF = Operating CF + CapEx (no SBC deduction). Flag this in output metadata so downstream DCF skills don't overstate FCF.

## Workflow

### Step 1: Collect Data

Run the collection script:

```bash
python scripts/collect_data.py TICKER [--years 5] [--output path/to/output.json]
```

The script collects in this priority:
1. **yfinance** — market data, historical financials, beta, analyst estimates
2. **yfinance ^TNX** — 10Y Treasury yield as risk-free rate proxy
3. **User supplement** — for years where yfinance returns NaN (report to user, do not guess)

### Step 2: Validate Data

```bash
python scripts/validate_data.py path/to/output.json
```

Checks: field completeness, cross-field consistency (Market Cap = Price × Shares), range sanity (WACC 5-20%, beta 0.3-3.0), sign conventions.

### Step 3: Deliver JSON

Single file: `{TICKER}_financial_data.json`. Schema in `references/output-schema.md`.

**Do NOT create**: README, CSV, summary reports, or any auxiliary files.

## Output Schema (Summary)

```json
{
  "ticker": "META",
  "company_name": "Meta Platforms, Inc.",
  "data_date": "2026-03-02",
  "currency": "USD",
  "unit": "millions_usd",
  "data_sources": { "market_data": "...", "2022_to_2024": "..." },
  "market_data": { "current_price": 648.18, "shares_outstanding_millions": 2187, "market_cap_millions": 1639607, "beta_5y_monthly": 1.284 },
  "income_statement": { "2024": { "revenue": 164501, "ebit": 69380, "tax_expense": ..., "net_income": ..., "_source": "yfinance" } },
  "cash_flow": { "2024": { "operating_cash_flow": ..., "capex": -37256, "depreciation_amortization": 15498, "free_cash_flow": ..., "change_in_nwc": ..., "_source": "yfinance" } },
  "balance_sheet": { "2024": { "total_debt": 30768, "cash_and_equivalents": 77815, "net_debt": -47047, "current_assets": ..., "current_liabilities": ..., "_source": "yfinance" } },
  "wacc_inputs": { "risk_free_rate": 0.0396, "beta": 1.284, "credit_rating": null, "_source": "yfinance + ^TNX" },
  "analyst_estimates": { "revenue_next_fy": 251113, "revenue_fy_after": 295558, "eps_next_fy": 29.59, "_source": "yfinance" },
  "metadata": { "_capex_convention": "negative = cash outflow", "_fcf_note": "yfinance FCF = OperatingCF + CapEx. Does NOT deduct SBC." }
}
```

Full schema with all field definitions: `references/output-schema.md`

<correct_patterns>

### Handling Missing Years

```python
if pd.isna(revenue):
    result[year] = {"revenue": None, "_source": "yfinance returned NaN — supplement from 10-K"}
# Report missing years to the user. Do NOT skip or fill with estimates.
```

### CapEx Sign Preservation

```python
capex = cash_flow.loc["Capital Expenditure", year_col]  # -37256.0
result["capex"] = float(capex)  # Preserve negative
```

### Datetime Column Indexing

```python
year_col = [c for c in financials.columns if c.year == target_year][0]
revenue = financials.loc["Total Revenue", year_col]
```

### Field Name Guards

```python
if "Total Revenue" in financials.index:
    revenue = financials.loc["Total Revenue", year_col]
elif "Revenue" in financials.index:
    revenue = financials.loc["Revenue", year_col]
else:
    revenue = None
```

</correct_patterns>

<common_mistakes>

### Mistake 1: Default Values for Missing Data

```python
# ❌ WRONG
beta = info.get("beta", 1.0)
growth = data.get("growth") or 0.02

# ✅ RIGHT
beta = info.get("beta")  # May be None — that's OK
```

### Mistake 2: Assuming All Years Have Data

```python
# ❌ WRONG — 2020-2021 may be NaN
revenue = float(financials.loc["Total Revenue", year_col])

# ✅ RIGHT
value = financials.loc["Total Revenue", year_col]
revenue = float(value) if pd.notna(value) else None
```

### Mistake 3: Using yfinance FCF in DCF Models Directly

yfinance FCF does NOT deduct SBC. For mega-caps like META, SBC can be $20-30B/yr, making yfinance FCF ~30% higher than investment-bank FCF. Always flag this in output.

### Mistake 4: Flipping CapEx Sign

```python
# ❌ WRONG — double-negation risk downstream
capex = abs(cash_flow.loc["Capital Expenditure", year_col])

# ✅ RIGHT — preserve original, document convention
capex = float(cash_flow.loc["Capital Expenditure", year_col])  # -37256.0
```

</common_mistakes>

## Known yfinance Pitfalls

See `references/yfinance-pitfalls.md` for detailed field mapping and workarounds.
