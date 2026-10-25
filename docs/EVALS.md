# Evaluation

## Method

[`evals/questions.yaml`](../evals/questions.yaml) holds questions with hand-written gold SQL. For each question the runner executes the gold SQL and the agent's SQL on the same warehouse and compares the results (**execution accuracy**). It never compares SQL text, since many different queries are correct.

The comparison:
- **Columns:** the agent may alias, reorder or add columns. Each gold column must match a distinct result column by value.
- **Rows:** compared as a multiset, or in order when the question is marked `ordered`.
- **Numbers:** must agree within 0.01 absolute or 0.01% relative.
- **Labels:** for time series, `compare` restricts matching to the value columns, so month labels such as `3`, `March` and `2017-03` are all accepted.

Each question has a category: `aggregate`, `join`, `time`, `promotion`, or `definition`. Definition questions need a metric definition that the schema alone doesn't provide (for example, that basket value is the sum per basket). They are the target of Phase 2's document retrieval.

## Running

```bash
cd backend
uv run python -m evaluation.runner                      # local DuckDB
WAREHOUSE=athena uv run python -m evaluation.runner     # deployed Athena
uv run python -m evaluation.runner --only q12 q13       # a subset
```

Results are written to `evals/results/<timestamp>-<engine>.json`. In GitHub Actions a summary table is also added to the job page.

## Where it runs

| Pipeline | Warehouse | Why |
|---|---|---|
| CI, every push and PR | DuckDB, built from the branch | Reflects the branch's own catalog and prompt changes |
| CD, after each deploy | Athena | The number that matches production |

Both gates fail below 70% accuracy.

**DuckDB is more lenient than Athena**, so local runs can overstate accuracy. For example, DuckDB accepts `ORDER BY month` with `GROUP BY month_name`; Athena rejects it with `EXPRESSION_NOT_AGGREGATE`. That's why the post-deploy run on Athena is the reported number.

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

All the misses are definition questions, for example averaging per product line instead of per basket, or an inner join dropping households without demographics.

### Fixes that came out of building the eval

Each of these was a real defect rather than eval tuning:
- **Catalog comment with a wrong value:** it said brands were "National or Private label", but the value is `'Private'`. Agent filters on `'Private label'` returned 0%.
- **Two competing "week" columns:** `dim_date.week` was removed (see [DATA.md](DATA.md)).
- **Gold SQL bug:** q05 used an inner join and dropped sales for products missing from `dim_product`.
- **Scorer bug:** it reported "no matching column" for right-values-wrong-order. Columns are now matched without regard to order, and order is checked afterwards.
- **Prompt differed between engines:** Glue listed tables alphabetically, so the agent saw a different prompt locally than on AWS. Glue tables now carry `catalog_position`, and a test enforces identical schema text.
