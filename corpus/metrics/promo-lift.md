---
doc_id: metric-promo-lift
doc_type: metric
title: Promotion lift
metric_name: promo_lift
terms: [promo lift, promotion lift, display lift, mailer lift, promotional uplift]
---
# Promotion lift

## Definition
**Promotion lift** measures how many more units a product sells in a store in the weeks it is promoted there, compared with that product in that store in weeks it is not.

- A product is **promoted** in a store and week when `fact_promotion` has a row for it with `display_location <> '0'` or `mailer_location <> '0'`. Display lift and mailer lift use only one of the two conditions.
- Lift is measured in **units** (`quantity`), not dollars. Promoted items are usually discounted, so dollar sales can fall even when units rise.
- Compare each product with itself in the same store: for every product-store pair that sold in both promoted and non-promoted weeks, take the average weekly units in each. Lift = (sum of promoted averages / sum of non-promoted averages) - 1, as a percentage.
- Only store-weeks in which the product sold count; weeks with no sales are not zero-filled.

## Calculation
```sql
WITH units AS (
  SELECT product_id, store_id, week, sum(quantity) AS units
  FROM fact_transactions
  GROUP BY 1, 2, 3
),
promoted AS (
  SELECT DISTINCT product_id, store_id, week
  FROM fact_promotion
  WHERE display_location <> '0' OR mailer_location <> '0'
),
by_pair AS (
  SELECT u.product_id, u.store_id,
         avg(CASE WHEN p.product_id IS NOT NULL THEN u.units END) AS promoted_units,
         avg(CASE WHEN p.product_id IS NULL THEN u.units END) AS baseline_units
  FROM units u
  LEFT JOIN promoted p ON u.product_id = p.product_id AND u.store_id = p.store_id AND u.week = p.week
  GROUP BY 1, 2
)
SELECT round(100 * (sum(promoted_units) / sum(baseline_units) - 1), 2) AS promo_lift_pct
FROM by_pair
WHERE promoted_units IS NOT NULL AND baseline_units IS NOT NULL
```

## Notes
- Across all products the lift is about 14%: about 11% for in-store display and 16% for mailer placement.
- To measure one department or category, join `dim_product` in the `units` step and filter there.
