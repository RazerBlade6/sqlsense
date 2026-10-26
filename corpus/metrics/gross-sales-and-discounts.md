---
doc_id: metric-gross-sales-and-discounts
doc_type: metric
title: Gross sales and discounts
metric_name: discount_rate
terms: [gross sales, shelf value, total discount, discount rate, markdown]
---
# Gross sales and discounts

## Definition
- **Total discount** = `retail_disc + coupon_disc + coupon_match_disc`. All three are stored as positive dollar amounts.
- **Gross sales** (shelf value) = net sales plus total discount: what the lines would have cost at shelf price.
- **Discount rate** = total discount / gross sales, as a percentage.

Loyalty-card discounts (`retail_disc`) are funded by the retailer. Manufacturer coupons (`coupon_disc`) are reimbursed by the manufacturer, and `coupon_match_disc` is the retailer topping up a manufacturer coupon.

## Calculation
```sql
SELECT
  round(sum(retail_disc + coupon_disc + coupon_match_disc), 2) AS total_discount,
  round(sum(sales_value + retail_disc + coupon_disc + coupon_match_disc), 2) AS gross_sales,
  round(100 * sum(retail_disc + coupon_disc + coupon_match_disc)
        / sum(sales_value + retail_disc + coupon_disc + coupon_match_disc), 2) AS discount_rate_pct
FROM fact_transactions
```
