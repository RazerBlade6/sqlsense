---
doc_id: table-dim-campaign
doc_type: dictionary
title: "Table dim_campaign"
table: dim_campaign
terms: [dim_campaign]
---
# Table dim_campaign

## Purpose
Marketing campaigns and when they ran. Some start before 2017 or end after it, outside the transaction period. One row per campaign_id.

## Columns
| Column | Type | Description |
|---|---|---|
| `campaign_id` | bigint | Campaign key. |
| `campaign_type` | string | Type A, Type B or Type C. See campaign documentation for how each type targets households. |
| `start_date` | date | First day of the campaign. |
| `end_date` | date | Last day of the campaign. |

## Joins
Joins `bridge_campaign_household`, `dim_coupon` and `fact_coupon_redemption` on `campaign_id`.

## Notes
- See [Campaign types](../campaigns/campaign-types.md) for how each type targets households, and the campaign briefs for each campaign's objective and target.
