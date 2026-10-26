---
doc_id: table-dim-product
doc_type: dictionary
title: "Table dim_product"
table: dim_product
terms: [dim_product]
---
# Table dim_product

## Purpose
Product master data. One row per product_id.

## Columns
| Column | Type | Description |
|---|---|---|
| `product_id` | bigint | Product key. |
| `manufacturer_id` | bigint | Manufacturer of the product. |
| `department` | string | Top-level department, e.g. GROCERY, DRUG GM, PRODUCE, MEAT, FUEL. |
| `brand` | string | 'National' or 'Private' (private label, the store's own brand). |
| `product_category` | string | Category within the department, e.g. SOFT DRINKS. |
| `product_type` | string | Most granular product grouping. |
| `package_size` | string | Free-text package size, e.g. 12 OZ. |

## Joins
Joined from `fact_transactions`, `fact_promotion` and `dim_coupon` on `product_id`.

## Notes
- `brand` is `'National'` or `'Private'`; private label is the store's own brand. See [Private label share](../metrics/private-label-share.md).
- Department `DRUG GM` is health and beauty, over-the-counter medicine and general merchandise.
- 4,836 transaction lines have no matching product row.
