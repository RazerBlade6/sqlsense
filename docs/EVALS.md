# Evaluation

## Method

[`evals/questions.yaml`](../evals/questions.yaml) holds 36 questions. Each goes through the whole assistant (planner, retrieval, SQL agent, synthesizer) and is scored on up to three measures:

| Measure | Applies to | Correct when |
|---|---|---|
| **Execution accuracy** | questions with gold SQL (28) | the assistant's result matches the gold SQL's result |
| **Routing accuracy** | all | the planner chose the expected route (`sql`, `docs`, `both`, `clarify` or `refuse`) |
| **Retrieval recall@5** | questions with expected documents (21) | the expected documents are among the 5 chunks retrieved (reported as the mean share) |

The headline accuracy counts a question as correct when its result matches the gold SQL. A docs-only question instead needs its answer to contain the expected phrases (`answer_contains`). A clarify or refuse question needs the right route. Follow-up questions carry their earlier turns in `history`.

The SQL comparison never compares SQL text, since many different queries are correct. It works as follows:
- **Columns:** the agent may alias, reorder or add columns. Each gold column must match a distinct result column by value.
- **Rows:** compared as a multiset, or in order when the question is marked `ordered`.
- **Numbers:** must agree within 0.01 absolute or 0.01% relative.
- **Labels:** for time series, `compare` restricts matching to the value columns, so month labels such as `3`, `March` and `2017-03` are all accepted.

Categories: `aggregate`, `join`, `time`, `promotion`, `definition` (needs a metric, period or target from the documents), `docs`, `followup`, `clarify` and `refuse`.

## Running

```bash
cd backend
uv run python -m evaluation.runner                      # local DuckDB
WAREHOUSE=athena uv run python -m evaluation.runner     # deployed Athena
uv run python -m evaluation.runner --only q12 q13       # a subset
WAREHOUSE=athena uv run python -m evaluation.runner --api-url https://<function-url>/   # deployed API
```

Results are written to `evals/results/<timestamp>-<engine>.json`. In GitHub Actions a summary table is also added to the job page.

## Where it runs

| Pipeline | Warehouse | Why |
|---|---|---|
| CI, every push and PR | in-process assistant, DuckDB and local retrieval, built from the branch | Reflects the branch's own catalog, corpus and prompt changes |
| CD, after each deploy | the deployed API (Lambda, pgvector, DynamoDB memory); gold SQL on Athena | The number that matches production. Follow-ups replay their history into a real session |

Both gates fail below 70% accuracy.

**DuckDB is more lenient than Athena**, so local runs can overstate accuracy. For example, DuckDB accepts `ORDER BY month` with `GROUP BY month_name`; Athena rejects it with `EXPRESSION_NOT_AGGREGATE`. That's why the post-deploy run on Athena is the reported number.

## Phase 2 results

Same models: Nova Micro (planner), Nova Pro (SQL and synthesis), Titan Embeddings V2. Run locally on DuckDB with local retrieval.

| | Phase 1 (SQL agent only) | Phase 2 (assistant) |
|---|---|---|
| Questions | 15 | 36 |
| Definition questions | 1/3 | 12/13 |
| Overall accuracy | 87% | 94–97% (two runs: 34/36, 35/36) |
| Routing accuracy | n/a | 97–100% |
| Retrieval recall@5 | n/a | 90–95% |
| p50 latency | 1.7 s | 3.6 s |

What moved the numbers, measured on the eval:
- **Retrieval alone helped little:** the planner routed metric questions to `sql`, so the definitions were never fetched (81% routing accuracy). The glossary guard (see [RETRIEVAL.md](RETRIEVAL.md)) fixed this.
- **Interleaving per-query rankings** instead of summing them kept specific documents (a campaign brief) from being crowded out by broad ones (every brief mentions a redemption target).
- **Nova Micro rejected nullable fields:** it produced malformed tool calls (`ModelErrorException`) for an `Optional` field in the plan schema. The field is now a plain string.

Known gaps:
- **Recall:** q30 ("redemption target for Type B campaigns") retrieves 5 Type B briefs, which all state the target, instead of the campaign types overview. The answer is right, but the recall miss is real. Diversity re-ranking is a Phase 3 candidate.
- **Model reasoning:** Nova Pro sometimes ignores a documented SQL pattern (for example an inner join instead of the documented LEFT JOIN for the redemption rate). It has also stated that 100% is below a 15% target. These are expected to improve with Claude.
- **Optimistic numbers:** the corpus, the glossary guard and the new questions were written together, so these numbers are likely higher than on unseen questions. Phase 3 adds a held-out question set and reports the mean of several runs.

## Baseline (Phase 1)

Amazon Nova Pro (`apac.amazon.nova-pro-v1:0`) at temperature 0, 15 questions:

| Category | DuckDB | Athena |
|---|---|---|
| aggregate | 3/3 | 3/3 |
| join | 4/4 | 4/4 |
| time | 4/4 | 4/4 |
| promotion | 1/1 | 1/1 |
| definition | 1/3 | 0/3 |
| **Total** | **13/15 (87%)** | **12/15 (80%)** |

Runs vary by about one question even at temperature 0, because Bedrock output isn't fully deterministic (CI scored 14/15 on DuckDB for the same commit). Phase 3 will report the mean of several runs.

All the misses are definition questions, for example averaging per product line instead of per basket, or an inner join dropping households without demographics.

### Fixes that came out of building the eval

Each of these was a real defect rather than eval tuning:
- **Catalog comment with a wrong value:** it said brands were "National or Private label", but the value is `'Private'`. Agent filters on `'Private label'` returned 0%.
- **Two competing "week" columns:** `dim_date.week` was removed (see [DATA.md](DATA.md)).
- **Gold SQL bug:** q05 used an inner join and dropped sales for products missing from `dim_product`.
- **Scorer bug:** it reported "no matching column" for right-values-wrong-order. Columns are now matched without regard to order, and order is checked afterwards.
- **Prompt differed between engines:** Glue listed tables alphabetically, so the agent saw a different prompt locally than on AWS. Glue tables now carry `catalog_position`, and a test enforces identical schema text.
