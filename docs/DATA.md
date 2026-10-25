# Retail Warehouse

## Source

**The Complete Journey 2.0** from 84.51° is one year (2017) of grocery purchases by 2,469 households. The data comes from the [`completejourney`](https://github.com/bradleyboehmke/completejourney) R package, which is CC0-licensed. `data/build.py` downloads its data files at a pinned commit and checks their SHA-256 hashes, so the warehouse is reproducible.

## Tables

[`catalog/retail.yaml`](../catalog/retail.yaml) is the single source of truth: every table, column, type and comment is defined there. Everything else is derived from it:

| Consumer | Uses the catalog to |
|---|---|
| `data/build.py` | cast each column to its declared type and write Parquet |
| `infra/stacks/data.py` | define the Glue tables (with comments, grain and partition projection) |
| `backend/app/warehouse` | create the local DuckDB views and produce the schema text the SQL agent reads |

| Table | Rows | Grain |
|---|---:|---|
| `fact_transactions` | 1,469,307 | basket + product (partitioned by `week`) |
| `fact_promotion` | 20,940,529 | product + store + week (partitioned by `week`) |
| `dim_product` | 92,331 | product |
| `dim_household_demographics` | 801 | household |
| `dim_campaign` | 27 | campaign |
| `bridge_campaign_household` | 6,589 | campaign + household |
| `dim_coupon` | 116,204 | coupon + product + campaign |
| `fact_coupon_redemption` | 2,102 | redemption |
| `dim_date` | 366 | calendar day |

The whole warehouse is about 37 MB of zstd-compressed Parquet.

## Modeling decisions

- **Explicit Glue tables, not a crawler.** The column comments are what the SQL agent relies on, so they are written and versioned by hand. A crawler would infer types and drop that context. Schema-drift detection, which is what crawlers are good at, comes with the data-quality agent in Phase 3.
- **Partition projection on `week`.** Athena computes the partitions from the range 1–53, so there is no crawler run or `MSCK REPAIR` step when new weeks land.
- **One definition of "week".** `dim_date` has no week column. An earlier version derived one (the most common transaction week for each date), but it disagreed with `fact_transactions.week` on boundary days, and the agent's joins through it returned the wrong weeks.
- **Deterministic build.** The build runs single-threaded, so identical input produces byte-identical Parquet. The files are a CDK asset, so this keeps deploys and PR plans free of spurious data changes.

## Known data issues

| Issue | Handling |
|---|---|
| Two IDs were serialized in scientific notation upstream (`9e+05`, `4.0128e+10`) | Cast through `double`. The product ID is recovered exactly; one basket ID loses precision (1 row). |
| 4,836 transaction lines have no matching `dim_product` row | Documented on `fact_transactions.product_id`: use a `LEFT JOIN` when totals must include all sales. |
| Only 801 of 2,469 households have demographics | Stated in the table description, because inner joins silently drop two-thirds of households. |
| `FUEL` and `COUPON/MISC ITEMS` lines record volume, not item counts | Documented on `quantity`; `sales_value` is unaffected. |
| Missing home ownership and marital status values | Left as `null`, not "Unknown". |

## Publishing

`SqlSenseData` uploads `data/warehouse/retail/` to the warehouse bucket as a CDK asset (`BucketDeployment`). Publishing data is therefore part of a normal deploy, and CD needs no S3 permissions of its own. After each deploy, `evaluation/smoke.py` checks that Athena returns exactly the row counts recorded in the build manifest.

Athena queries run in the `sqlsense` workgroup. Its settings are enforced, it refuses any query that would scan more than 100 MB, and it uses managed query results, so there is no results bucket. A typical query scans 1–2 MB.
