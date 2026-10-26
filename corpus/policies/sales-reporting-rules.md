---
doc_id: policy-sales-reporting-rules
doc_type: policy
title: Sales reporting rules
terms: [returns, refunds, zero-value lines, unmatched products, reporting rules]
---
# Sales reporting rules

## Returns and refunds
The warehouse contains sales only. Returns are processed in the store system and removed before the data is loaded, so there are no negative quantities or sales values and nothing needs to be netted out. Questions about return rates cannot be answered from this data.

## Zero-value lines
About 11,200 transaction lines have a `sales_value` of 0: free items and items fully paid for by coupons. Keep them in basket counts, product counts and unit counts. They do not affect sales totals.

## Fuel
Fuel is sold at forecourts attached to some stores. Fuel lines count towards net sales but are excluded from merchandise sales and from unit counts, because their quantity is volume. See [Net sales](../metrics/net-sales.md) and [Basket size](../metrics/basket-size.md).

## Products missing from the product table
4,836 transaction lines reference a `product_id` that is not in `dim_product`. They are real sales. Department and category breakdowns show them as an unknown department; company totals include them, which requires a LEFT JOIN to `dim_product`.

## Rounding
Report money to 2 decimal places and percentages to 2 decimal places, as a number from 0 to 100.
