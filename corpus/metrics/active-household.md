---
doc_id: metric-active-household
doc_type: metric
title: Active household
metric_name: active_households
terms: [active household, active customer, active shopper, customer base]
---
# Active household

## Definition
A household is **active** in a period if it made at least one shopping trip (basket) in that period.

When a question asks for "active households" without naming a period, use the **trailing 8 weeks**: the 8 most recent weeks of data. For the 2017 data that is **weeks 46 to 53**.

## Calculation
```sql
-- Active households (trailing 8 weeks)
SELECT count(DISTINCT household_id) AS active_households
FROM fact_transactions
WHERE week BETWEEN 46 AND 53
```

## Notes
- A household that shopped in the year but not in the trailing 8 weeks is **lapsed**. See [Lapsed household](lapsed-household.md).
- For a named period (a quarter, a campaign window), count households with a basket in that period instead.
