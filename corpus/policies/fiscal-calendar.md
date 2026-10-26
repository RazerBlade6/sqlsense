---
doc_id: policy-fiscal-calendar
doc_type: policy
title: Fiscal calendar
terms: [fiscal year, fiscal quarter, Q1, Q2, Q3, Q4, last quarter, holiday period, holiday season, trading week, reporting week, Thanksgiving week]
---
# Fiscal calendar

## Fiscal year and weeks
Fiscal year 2017 is dataset weeks 1 to 53 (`fact_transactions.week`). A reporting week runs Monday to Sunday: week 2 starts on Monday 2 January 2017 and week 52 ends on Sunday 24 December 2017.

Week 1 is a two-day stub (1 and 2 January) and week 53 runs from 26 December 2017 to 1 January 2018. Exclude week 1 from week-over-week comparisons and averages of weekly sales, because it is not a full week.

## Fiscal quarters
Quarters are blocks of 13 weeks, with week 53 added to the fourth quarter.

| Quarter | Weeks |
|---|---|
| Q1 | 1 to 13 |
| Q2 | 14 to 26 |
| Q3 | 27 to 39 |
| Q4 | 40 to 53 |

Fiscal quarters do not match calendar quarters (`dim_date.quarter`). When a question says "quarter", "Q3" or "last quarter" without saying "calendar", use fiscal quarters. "Last quarter" means Q4, the most recent quarter in the data. Filter on `week`, not on dates.

## Holiday period
The **holiday period** is weeks 48 to 52: from the Monday of Thanksgiving week (20 November 2017) to Christmas Eve (24 December 2017). Holiday comparisons use the same number of weeks immediately before, weeks 43 to 47, as the baseline.

## Store closures
Stores close on Christmas Day, so there are no transactions on 25 December 2017.
