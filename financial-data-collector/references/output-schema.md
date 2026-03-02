# Output Schema — financial-data-collector

All monetary values in millions USD unless noted. Null means "not available from source."

## Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | string | Stock ticker symbol (e.g., "META") |
| `company_name` | string | Full company name from yfinance |
| `data_date` | string | ISO date when data was collected |
| `currency` | string | Always "USD" for US equities |
| `unit` | string | Always "millions_usd" |
| `data_sources` | object | Attribution for each data section |

## market_data

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `current_price` | float | `yf.Ticker.info["currentPrice"]` | USD per share |
| `shares_outstanding_millions` | float | `info["sharesOutstanding"] / 1e6` | Diluted if available |
| `market_cap_millions` | float | `info["marketCap"] / 1e6` | |
| `beta_5y_monthly` | float\|null | `info["beta"]` | May be null for recent IPOs |

## income_statement (keyed by year string)

| Field | Type | Source Row Index |
|-------|------|-----------------|
| `revenue` | float\|null | "Total Revenue" or "Revenue" |
| `ebit` | float\|null | "Operating Income" or "EBIT" |
| `ebitda` | float\|null | "EBITDA" (if available) |
| `tax_expense` | float\|null | "Tax Provision" or "Income Tax Expense" |
| `net_income` | float\|null | "Net Income" |
| `sbc` | float\|null | "Stock Based Compensation" (in cash_flow) |
| `_source` | string | Data provenance |

## cash_flow (keyed by year string)

| Field | Type | Source Row Index | Sign |
|-------|------|-----------------|------|
| `operating_cash_flow` | float\|null | "Operating Cash Flow" | Positive = inflow |
| `capex` | float\|null | "Capital Expenditure" | **Negative = outflow** |
| `depreciation_amortization` | float\|null | "Depreciation And Amortization" | Positive |
| `free_cash_flow` | float\|null | "Free Cash Flow" | yfinance definition (see metadata) |
| `change_in_nwc` | float\|null | "Change In Working Capital" | Negative = use of cash |
| `_source` | string | | |

## balance_sheet (latest year only by default)

| Field | Type | Source Row Index |
|-------|------|-----------------|
| `total_debt` | float\|null | "Total Debt" or "Long Term Debt" + "Short Long Term Debt" |
| `cash_and_equivalents` | float\|null | "Cash And Cash Equivalents" + "Other Short Term Investments" |
| `net_debt` | float\|null | Computed: total_debt - cash_and_equivalents |
| `current_assets` | float\|null | "Current Assets" |
| `current_liabilities` | float\|null | "Current Liabilities" |
| `total_assets` | float\|null | "Total Assets" |
| `total_equity` | float\|null | "Stockholders Equity" |
| `_source` | string | |

## wacc_inputs

| Field | Type | Source |
|-------|------|--------|
| `risk_free_rate` | float\|null | yfinance ^TNX (10Y Treasury) |
| `beta` | float\|null | Same as market_data.beta_5y_monthly |
| `credit_rating` | string\|null | Not available from yfinance — null unless user provides |

## analyst_estimates

| Field | Type | Source |
|-------|------|--------|
| `revenue_next_fy` | float\|null | `yf.Ticker.analyst_price_targets` or `revenue_estimate` |
| `revenue_fy_after` | float\|null | Same |
| `eps_next_fy` | float\|null | `yf.Ticker.analyst_price_targets` or `eps_trend` |

## metadata

| Field | Value |
|-------|-------|
| `_capex_convention` | "negative = cash outflow (yfinance convention)" |
| `_fcf_note` | "yfinance FCF = OperatingCF + CapEx. Does NOT deduct SBC." |
| `_nan_years` | List of years where yfinance returned NaN |
| `_collection_duration_seconds` | Time taken to collect all data |
