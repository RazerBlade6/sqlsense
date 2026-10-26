---
doc_id: metric-net-sales
doc_type: metric
title: Net sales
metric_name: net_sales
terms: [net sales, merchandise sales]
---
# Net sales

## Definition
**Net sales** (also "sales" or "revenue") is the money the retailer received: the sum of `sales_value` in `fact_transactions`. `sales_value` is already net of loyalty discounts and coupons.

**Merchandise sales** is net sales excluding the `FUEL` department. Use it when a question is about the store's products or shopping behaviour rather than total revenue. Fuel is about 7% of net sales.

## Calculation
```sql
-- Net sales
SELECT round(sum(sales_value), 2) AS net_sales FROM fact_transactions

-- Merchandise sales (LEFT JOIN keeps lines whose product is missing from dim_product)
SELECT round(sum(t.sales_value), 2) AS merchandise_sales
FROM fact_transactions t LEFT JOIN dim_product p ON t.product_id = p.product_id
WHERE p.department IS NULL OR p.department <> 'FUEL'
```

## Notes
- Never add the discount columns to `sales_value` when reporting sales. See [Gross sales and discounts](gross-sales-and-discounts.md).
- Totals that join to `dim_product` must use a LEFT JOIN: 4,836 transaction lines have no product record.
