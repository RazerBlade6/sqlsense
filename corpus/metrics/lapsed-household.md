---
doc_id: metric-lapsed-household
doc_type: metric
title: Lapsed household
metric_name: lapsed_households
terms: [lapsed household, lapsed customer, churned household, churn, inactive household]
---
# Lapsed household

## Definition
A **lapsed** household shopped at least once during the year but made no trips in the trailing 8 weeks (weeks 46 to 53). Lapsed households are the target of win-back campaigns.

**Churn rate** is lapsed households as a percentage of all households that shopped during the year.

## Calculation
```sql
SELECT
  count(*) FILTER (WHERE last_week < 46) AS lapsed_households,
  round(100.0 * count(*) FILTER (WHERE last_week < 46) / count(*), 2) AS churn_rate_pct
FROM (SELECT household_id, max(week) AS last_week FROM fact_transactions GROUP BY household_id)
```
