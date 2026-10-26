---
doc_id: table-dim-coupon
doc_type: dictionary
title: "Table dim_coupon"
table: dim_coupon
terms: [dim_coupon]
---
# Table dim_coupon

## Purpose
Coupons and the products each coupon can be redeemed on, per campaign. One row per coupon_upc, product_id, campaign_id.

## Columns
| Column | Type | Description |
|---|---|---|
| `coupon_upc` | string | Coupon identifier. |
| `product_id` | bigint | Product the coupon applies to. |
| `campaign_id` | bigint | Campaign that issued the coupon. |

## Joins
Joins `dim_campaign` on `campaign_id`, `dim_product` on `product_id`, and `fact_coupon_redemption` on `coupon_upc` and `campaign_id`.

## Notes
- One coupon can apply to many products, so count distinct `coupon_upc` to count coupons.
- Type A campaigns have a pool of coupons; each household receives 16 of them.
