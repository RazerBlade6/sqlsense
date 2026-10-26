---
doc_id: table-fact-transactions
doc_type: dictionary
title: "Table fact_transactions"
table: fact_transactions
terms: [fact_transactions]
---
# Table fact_transactions

## Purpose
One row per product line in a shopping basket. 2,469 households, 2017. One row per basket_id, product_id. It is partitioned by `week`.

## Columns
| Column | Type | Description |
|---|---|---|
| `household_id` | bigint | Household making the purchase. Joins dim_household_demographics (only 801 households have demographics). |
| `store_id` | bigint | Store where the basket was purchased. No store dimension exists. |
| `basket_id` | bigint | Shopping trip (basket). Count distinct basket_id to count trips. |
| `product_id` | bigint | Product purchased. Joins dim_product; 4,836 lines have no match, so use a LEFT JOIN when totals must include all sales. |
| `quantity` | double | Units purchased. FUEL department and COUPON/MISC ITEMS category lines record volume, not item counts; exclude them only when counting units. sales_value is unaffected. |
| `sales_value` | double | Dollars received by the retailer for this line after discounts. Use for revenue/sales. |
| `retail_disc` | double | Loyalty-card discount in dollars (positive number). |
| `coupon_disc` | double | Manufacturer coupon discount in dollars (positive number). |
| `coupon_match_disc` | double | Retailer match of the manufacturer coupon in dollars (positive number). |
| `transaction_timestamp` | timestamp | Date and time of purchase. |
| `transaction_date` | date | Calendar date of purchase. Joins dim_date. |
| `week` | int | Dataset week number, 1-53 (partition key). Filter on week to reduce data scanned. |

## Joins
Joins `dim_product` on `product_id`, `dim_household_demographics` on `household_id`, and `dim_date` on `transaction_date = date_day`.

## Notes
- The table is partitioned by `week`; filtering on `week` reduces the data scanned and the cost.
- Count distinct `basket_id` for trips. See [Shopping trips](../metrics/shopping-trips.md).
- There are no returns or negative values. See [Sales reporting rules](../policies/sales-reporting-rules.md).
