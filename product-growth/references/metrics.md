# Define metrics around value

Record each selected metric's question, unit, identity/deduplication key, qualifying
event, numerator/denominator, eligibility, cohort origin, return/completion window,
timezone, source and observation cutoff. Distinguish missing, immature, invalid
and measured zero. Version definitions when instrumentation changes. Show counts
with rates and uncertainty.

Build a small tree from business outcome to value delivered, first/repeated use,
qualified demand and acquisition. Inspect segments and expected recoverable value;
do not assume the earliest or lowest-percentage funnel step is the best investment.

## Select common measures deliberately

| Measure | Define and check |
|---|---|
| Qualified acquisition | Count eligible new units; separate reach, visits and qualified demand |
| Conversion | Divide unique eligible completers within the agreed window by entrants; specify open versus sequential funnel |
| Activation | Define first realized value and time-to-value; test candidate high-retention behaviors before attributing intervention effects |
| Task success | Define accepted work; separate invocation, output delivery, correctness and external confirmation |
| Retention | Fix cohort and meaningful return event; distinguish exact-period, bounded-window and unbounded return; compare equal maturity |
| Churn/resurrection | Define lapse/re-entry relative to natural opportunities; separate no need, unobserved use and failed value |
| Referral/loops | Measure qualified recipients and activation/reuse per participating source unit; include lag, incentives and overlap |
| Acquisition cost | Match stated acquisition/sales costs and acquired customers/cohorts over compatible windows; separate paid/blended scope |
| Lifetime value | Prefer observed cohort contribution; label modeled tail, horizon and assumptions; avoid unstable revenue/churn shortcuts |
| Contribution | Subtract agreed variable fulfillment, inference, review, support, payment, incentives and refunds; disclose omissions |

Avoid default daily activity for annual, episodic, durable-goods or workflow tools.
Measure return when relevant tasks recur; state interpretation limits when task
opportunities cannot be observed. Inspect composition shifts and within-segment
behavior before attributing an aggregate change to product quality.

## Adapt to the business model

| Model | Add relevant measures | Avoid |
|---|---|---|
| B2B / sales-led | Organization activation, workflows/seats, qualified pipeline, stage conversion, sales cycle, win/loss, renewal/expansion | Equating signups with buying accounts or contracts with recognized revenue/cash |
| Subscription | Paying-customer retention, recurring-revenue bridge, GRR/NRR, involuntary churn, paid conversion | Letting expansion hide customer loss or equating MRR with profit |
| Commerce | Net paid orders, first/second purchase cohorts, natural cadence, refunds/returns, repeat contribution | Treating subsidized GMV or pulled-forward purchases as durable growth |
| Marketplace | Supply/demand activation and retention, eligible-request fill rate, time-to-match, local liquidity and quality | Letting global totals hide local failures or one-sided gains harm the other side |
| Open source / developer tools | Successful first/repeat tasks, independent integrations, current versions, migration friction, maintenance burden | Treating stars/clones/downloads/listings as active users |
| Content / community / services | Relevant consumption/participation, completed service outcomes, repeat need, conversion and delivery economics | Maximizing empty engagement or volume without value |
| AI products | Correct accepted tasks, observed time saved, retries, latency, inference/review cost per accepted result | Counting generation as success or assuming negligible marginal cost |

For a fixed starting recurring-revenue cohort, calculate NRR as
`(starting revenue + expansion - contraction - churn) / starting revenue` and GRR
as `(starting revenue - contraction - churn) / starting revenue`. Exclude new
customers from both. Bind currency, recurring items and reactivation policy;
reconcile to the billing system's documented definition. Keep customer retention,
cash and profit separate. Avoid dividing by zero or forecasting a lifetime from
an unstable cohort.

Choose guardrails tied to the action: correctness, refunds, reliability, support,
privacy, supplier experience or contribution. Explain tensions between influence,
customer value and revenue rather than inventing a composite score.
