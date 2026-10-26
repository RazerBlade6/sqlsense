---
doc_id: policy-data-privacy
doc_type: policy
title: Customer data privacy
terms: [privacy, personal data, PII, household identity, minimum group size, re-identification]
---
# Customer data privacy

## What the data contains
Households are identified only by a numeric `household_id`. The warehouse holds no names, addresses, emails, phone numbers or loyalty card numbers, and analysts must not try to link households to people.

## Reporting rules
- Demographic breakdowns must cover at least **10 households** per group. Suppress or merge smaller groups.
- Do not publish the purchase history of an individual household outside the analytics team. Household-level queries are for investigating data issues and building segments.
- Requests to identify, contact or locate a household are refused.

## Access
The analytics assistant has read-only access. It cannot change, delete or export warehouse data.
