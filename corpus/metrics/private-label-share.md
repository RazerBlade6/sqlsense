---
doc_id: metric-private-label-share
doc_type: metric
title: Private label share
metric_name: private_label_share
terms: [private label share, own brand share, store brand penetration]
---
# Private label share

## Definition
**Private label share** is the percentage of net sales from products with `brand = 'Private'` (the store's own brand) in `dim_product`. The denominator is all net sales, including lines with no product record, so use a LEFT JOIN.

## Calculation
```sql
SELECT round(100 * sum(CASE WHEN p.brand = 'Private' THEN t.sales_value ELSE 0 END) / sum(t.sales_value), 2)
       AS private_label_share_pct
FROM fact_transactions t LEFT JOIN dim_product p ON t.product_id = p.product_id
```
