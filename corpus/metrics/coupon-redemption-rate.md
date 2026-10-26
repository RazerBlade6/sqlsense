---
doc_id: metric-coupon-redemption-rate
doc_type: metric
title: Coupon redemption rate
metric_name: coupon_redemption_rate
terms: [coupon redemption rate, redemption rate, campaign response rate, campaign uptake]
---
# Coupon redemption rate

## Definition
A campaign's **coupon redemption rate** is the percentage of the households that received the campaign that redeemed at least one of its coupons.

- Numerator: distinct households in `fact_coupon_redemption` for the campaign that are also in `bridge_campaign_household` for it.
- Denominator: distinct households in `bridge_campaign_household` for the campaign.

Counting redemptions instead of households overstates response, because one household can redeem many coupons.

## Calculation
```sql
SELECT b.campaign_id,
       count(DISTINCT b.household_id) AS households_targeted,
       count(DISTINCT r.household_id) AS households_redeemed,
       round(100.0 * count(DISTINCT r.household_id) / count(DISTINCT b.household_id), 2) AS redemption_rate_pct
FROM bridge_campaign_household b
LEFT JOIN fact_coupon_redemption r
  ON r.campaign_id = b.campaign_id AND r.household_id = b.household_id
GROUP BY b.campaign_id
ORDER BY b.campaign_id
```
