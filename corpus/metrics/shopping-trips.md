---
doc_id: metric-shopping-trips
doc_type: metric
title: Shopping trips and purchase frequency
metric_name: purchase_frequency
terms: [purchase frequency, trips per household]
---
# Shopping trips and purchase frequency

## Definition
A **shopping trip** (visit) is one basket: count distinct `basket_id`. Each row of `fact_transactions` is a product line, so counting rows overstates trips.

**Purchase frequency** is shopping trips per active household in the period: distinct baskets divided by distinct households that shopped in the period. Unless stated, report it for the whole year.

## Calculation
```sql
SELECT
  count(DISTINCT basket_id) AS trips,
  round(1.0 * count(DISTINCT basket_id) / count(DISTINCT household_id), 2) AS trips_per_household
FROM fact_transactions
```
