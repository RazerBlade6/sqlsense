---
doc_id: metric-spend-per-household
doc_type: metric
title: Spend per household
metric_name: spend_per_household
terms: [spend per household, average household spend, customer value, share of wallet]
---
# Spend per household

## Definition
**Spend per household** is net sales divided by the number of households that shopped in the same period. Households that made no trips in the period are not in the denominator.

## Calculation
```sql
SELECT round(sum(sales_value) / count(DISTINCT household_id), 2) AS spend_per_household
FROM fact_transactions
```

For a segment (for example an income band), compute it per segment from the households with demographic data. See [Demographic coverage](demographic-coverage.md).
