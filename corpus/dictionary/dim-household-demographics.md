---
doc_id: table-dim-household-demographics
doc_type: dictionary
title: "Table dim_household_demographics"
table: dim_household_demographics
terms: [dim_household_demographics]
---
# Table dim_household_demographics

## Purpose
Demographics for the 801 households (of 2,469) that provided them. Inner joins to transactions drop the other households. One row per household_id.

## Columns
| Column | Type | Description |
|---|---|---|
| `household_id` | bigint | Household key. |
| `age` | string | Age band of the head of household, e.g. 25-34, 65+. |
| `income` | string | Income band, e.g. 35-49K, 250K+. |
| `home_ownership` | string | Homeowner, Renter, Probable Homeowner or Probable Renter; null when unknown. |
| `marital_status` | string | Married or Unmarried; null when unknown. |
| `household_size` | string | Number of people, 1 to 5+. |
| `household_comp` | string | Composition, e.g. 2 Adults Kids, 1 Adult No Kids. |
| `kids_count` | string | Number of children, 0 to 3+. |

## Joins
Joins `fact_transactions`, `bridge_campaign_household` and `fact_coupon_redemption` on `household_id`.

## Notes
- Only 801 of 2,469 households have a row. See [Demographic coverage](../metrics/demographic-coverage.md).
- All attributes are bands stored as text, so sort them explicitly when ordering matters (for example income bands).
- Breakdowns must cover at least 10 households per group. See [Customer data privacy](../policies/data-privacy.md).
