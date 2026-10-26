---
doc_id: table-bridge-campaign-household
doc_type: dictionary
title: "Table bridge_campaign_household"
table: bridge_campaign_household
terms: [bridge_campaign_household]
---
# Table bridge_campaign_household

## Purpose
Which households received which campaigns. One row per campaign_id, household_id.

## Columns
| Column | Type | Description |
|---|---|---|
| `campaign_id` | bigint | Joins dim_campaign. |
| `household_id` | bigint | Household that received the campaign. |

## Joins
Joins `dim_campaign` on `campaign_id` and `dim_household_demographics` on `household_id`.

## Notes
- A household can receive several campaigns.
- This is the denominator of the [Coupon redemption rate](../metrics/coupon-redemption-rate.md).
