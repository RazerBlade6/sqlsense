---
doc_id: campaign-types
doc_type: campaign
title: Campaign types
terms: [campaign type, Type A, Type B, Type C, targeted campaign, personalised campaign, pilot campaign]
---
# Campaign types

The retailer ran 27 coupon campaigns in or around 2017, of three types that differ in how households are targeted and which coupons they receive. Campaigns are recorded in `dim_campaign`. Households that received a campaign are in `bridge_campaign_household`, the coupons in `dim_coupon` and redemptions in `fact_coupon_redemption`.

## Type A: personalised events
Targeting: by spend and purchase history. Large seasonal events sent to about 1,100 of the highest-spending households (campaigns 8, 13, 18 and 27). Each campaign has a pool of about 200 coupons, and each household receives **16 coupons chosen from its own purchase history**, so two households in the same campaign get different offers. They run for 7 to 8 weeks. Redemption target: **15%**.

## Type B: themed campaigns
Targeting: by the theme's product affinity. Campaigns built around a theme or season, such as Easter baking or cold and flu season, sent to 10 to 300 households. **Every targeted household receives every coupon**, usually 10 to 30 coupons. They run for about 5 weeks. Redemption target: **8%**.

## Type C: pilots
Targeting: small test groups. Small or long-running tests of a new offer, sent to between 12 and 250 households. Every targeted household receives every coupon. They can run for several months (campaign 15 ran from September 2017 to February 2018). Redemption target: **5%**.

## Campaigns outside 2017
Campaigns 24, 25 and 26 started in late 2016, and campaigns 15, 20, 21, 22 and 23 end in 2018. Only the part inside 2017 has transactions.
