---
doc_id: table-fact-coupon-redemption
doc_type: dictionary
title: "Table fact_coupon_redemption"
table: fact_coupon_redemption
terms: [fact_coupon_redemption]
---
# Table fact_coupon_redemption

## Purpose
Coupons redeemed by households. One row per household_id, coupon_upc, campaign_id, redemption_date.

## Columns
| Column | Type | Description |
|---|---|---|
| `household_id` | bigint | Household redeeming the coupon. |
| `coupon_upc` | string | Coupon redeemed. Joins dim_coupon. |
| `campaign_id` | bigint | Campaign the coupon came from. |
| `redemption_date` | date | Date of redemption. |

## Joins
Joins `dim_coupon` on `coupon_upc` and `campaign_id`, and `bridge_campaign_household` on `campaign_id` and `household_id`.

## Notes
- Count distinct households, not rows, for campaign response.
