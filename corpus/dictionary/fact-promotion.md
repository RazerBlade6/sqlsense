---
doc_id: table-fact-promotion
doc_type: dictionary
title: "Table fact_promotion"
table: fact_promotion
terms: [fact_promotion]
---
# Table fact_promotion

## Purpose
Weekly in-store display and mailer placement for products, by store. One row per product_id, store_id, week. It is partitioned by `week`.

## Columns
| Column | Type | Description |
|---|---|---|
| `product_id` | bigint | Promoted product. Joins dim_product. |
| `store_id` | bigint | Store running the promotion. |
| `display_location` | string | In-store display code: 0 not on display, 1 store front, 2 store rear, 3 front end cap, 4 mid-aisle end cap, 5 rear end cap, 6 side-aisle end cap, 7 in-aisle, 9 secondary location display, A in-shelf. |
| `mailer_location` | string | Mailer code: 0 not on ad, A interior feature, C interior line item, D front page feature, F back page feature, H wrap front, J wrap interior coupon, L wrap back, P interior coupon, X free interior, Z free front/back/wrap. |
| `week` | int | Dataset week number, 1-53 (partition key). |

## Joins
Joins `dim_product` on `product_id`, and `fact_transactions` on `product_id`, `store_id` and `week`.

## Notes
- About 21 million rows: always filter on `week` or `product_id`.
- A row with both codes `'0'` means the product was tracked but not promoted that week.
- Mailer code `D` is the front page feature, the most prominent placement. Display code `3` is the front end cap.
- Used for [Promotion lift](../metrics/promo-lift.md).
