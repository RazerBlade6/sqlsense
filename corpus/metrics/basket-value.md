---
doc_id: metric-basket-value
doc_type: metric
title: Basket value
metric_name: basket_value
terms: [basket value, average basket value, average transaction value, ATV, spend per trip, ticket size]
---
# Basket value

## Definition
**Basket value** is the net sales of one shopping trip: the sum of `sales_value` over all lines with the same `basket_id`.

**Average basket value** (also average transaction value, ATV, or spend per trip) is the mean of basket values: total each basket first, then average across baskets. Averaging `sales_value` directly gives the average *line* value, which is a different and much smaller number.

## Calculation
```sql
SELECT round(avg(basket_value), 2) AS avg_basket_value
FROM (
  SELECT basket_id, sum(sales_value) AS basket_value
  FROM fact_transactions
  GROUP BY basket_id
)
```

To break it down by a household attribute, keep `household_id` in the inner query and join afterwards:

```sql
SELECT h.income, round(avg(b.basket_value), 2) AS avg_basket_value
FROM (
  SELECT basket_id, household_id, sum(sales_value) AS basket_value
  FROM fact_transactions
  GROUP BY basket_id, household_id
) b
JOIN dim_household_demographics h ON b.household_id = h.household_id
GROUP BY h.income
```

## Notes
Breakdowns by demographics only cover the 801 households with demographic data. See [Demographic coverage](demographic-coverage.md).
