---
doc_id: metric-household-retention
doc_type: metric
title: Household retention
metric_name: retention_rate
terms: [retention, retention rate, repeat rate, quarter-over-quarter retention]
---
# Household retention

## Definition
**Retention rate** from one fiscal quarter to the next is the percentage of households active in the first quarter that are also active in the following quarter. Active means at least one basket. Fiscal quarters are defined in the [fiscal calendar](../policies/fiscal-calendar.md).

## Calculation
```sql
-- Retention from fiscal Q3 (weeks 27-39) to fiscal Q4 (weeks 40-53)
WITH q3 AS (SELECT DISTINCT household_id FROM fact_transactions WHERE week BETWEEN 27 AND 39),
     q4 AS (SELECT DISTINCT household_id FROM fact_transactions WHERE week BETWEEN 40 AND 53)
SELECT round(100.0 * count(q4.household_id) / count(*), 2) AS retention_rate_pct
FROM q3 LEFT JOIN q4 ON q3.household_id = q4.household_id
```
