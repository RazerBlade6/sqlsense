---
doc_id: metric-basket-size
doc_type: metric
title: Basket size
metric_name: basket_size
terms: [basket size, items per basket, units per basket, lines per basket]
---
# Basket size

## Definition
**Basket size** is the average number of distinct products per basket: count distinct `product_id` within each basket, then average across baskets.

**Units per basket** is the average total `quantity` per basket. It excludes the `FUEL` department and the `COUPON/MISC ITEMS` category, because their quantity records volume (for example gallons) rather than items.

## Calculation
```sql
-- Basket size
SELECT round(avg(products), 2) AS avg_basket_size
FROM (SELECT basket_id, count(DISTINCT product_id) AS products FROM fact_transactions GROUP BY basket_id)

-- Units per basket
SELECT round(avg(units), 2) AS avg_units_per_basket
FROM (
  SELECT t.basket_id, sum(t.quantity) AS units
  FROM fact_transactions t LEFT JOIN dim_product p ON t.product_id = p.product_id
  WHERE coalesce(p.department, '') <> 'FUEL' AND coalesce(p.product_category, '') <> 'COUPON/MISC ITEMS'
  GROUP BY t.basket_id
)
```
