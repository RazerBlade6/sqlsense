# Document corpus

Business documents the retrieval agent searches: metric definitions, policies, campaign briefs and a data dictionary.

**The documents are synthetic.** The retailer behind The Complete Journey published no documents, so these were written for SQLSense. Facts about the data (campaign dates, household counts, table contents) come from the warehouse. Business rules, goals and targets (for example the fiscal calendar or a campaign's objective) are invented but consistent with the data.

| Folder | Contents |
|---|---|
| `metrics/` | One definition per metric, with the Athena SQL pattern |
| `policies/` | Fiscal calendar, sales reporting rules, data privacy |
| `campaigns/` | Campaign types and one brief per campaign |
| `dictionary/` | One page per warehouse table: purpose, joins and caveats |

Each file starts with front matter: `doc_id`, `doc_type`, `title`, `terms` (the business terms it defines, which the planner sees), and `metric_name` or `campaign_id` where relevant. This README is not indexed.
