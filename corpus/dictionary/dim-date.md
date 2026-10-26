---
doc_id: table-dim-date
doc_type: dictionary
title: "Table dim_date"
table: dim_date
terms: [dim_date]
---
# Table dim_date

## Purpose
Calendar for 2017-01-01 to 2018-01-01. For dataset weeks, use fact_transactions.week. One row per date_day.

## Columns
| Column | Type | Description |
|---|---|---|
| `date_day` | date | Calendar date. Joins fact_transactions.transaction_date. |
| `day_of_week` | string | Monday to Sunday. |
| `is_weekend` | boolean | True on Saturday and Sunday. |
| `month` | int | Month number, 1-12. |
| `month_name` | string | January to December. |
| `quarter` | int | Quarter, 1-4. |
| `year` | int | Calendar year. |

## Joins
Joins `fact_transactions` on `date_day = transaction_date`.

## Notes
- `quarter` is the calendar quarter. Business questions about quarters use fiscal quarters, which are ranges of `week`. See [Fiscal calendar](../policies/fiscal-calendar.md).
- There is no week column: use `fact_transactions.week`.
