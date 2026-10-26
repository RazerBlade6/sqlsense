---
doc_id: metric-demographic-coverage
doc_type: metric
title: Demographic coverage
metric_name: demographic_coverage
terms: [demographic coverage, households with demographics, demographic data, demographic match rate]
---
# Demographic coverage

## Definition
**Demographic coverage** is the percentage of purchasing households that have a row in `dim_household_demographics`. Only 801 of the 2,469 households that shopped provided demographics, so coverage is about 32%.

Any metric broken down by age, income or household composition describes those 801 households only. Report the coverage alongside such breakdowns.

## Calculation
```sql
SELECT round(100.0 * count(DISTINCT h.household_id) / count(DISTINCT t.household_id), 2) AS coverage_pct
FROM fact_transactions t
LEFT JOIN dim_household_demographics h ON t.household_id = h.household_id
```
