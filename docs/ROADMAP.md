# SQLSense v2 Roadmap

SQLSense v2 upgrades the v1 natural-language-to-SQL tool into a **multi-agent analytics assistant over a retail data warehouse on AWS**. Business users ask questions in plain English; a planner decides whether the answer lives in warehouse tables, in unstructured documents, or both, then the agents query, check, and answer with the SQL and sources shown.

## Architecture

```
            React UI (answer, SQL, citations, chart, agent trace)
                                  │
                    FastAPI on Lambda (audit log)
                                  │
   DynamoDB memory ◄──►     Planner agent      (route: sql | docs | both | clarify | refuse)
                         ┌────────┴────────┐
                    SQL agent        Retrieval agent
                         │                 │
             Athena + Glue Catalog   pgvector on Aurora Serverless v2
          (read-only role, scan cap)  (Bedrock Titan embeddings)
                         │
                  S3 data lake (Parquet)  ◄──  Data-quality agent
                                               (runs after each pipeline refresh)

Shared: Bedrock LLMs · CloudWatch/X-Ray traces · eval suite in CI · AWS CDK
```

## What carries over from v1

| v1 piece | Fate in v2 |
|---|---|
| LangGraph generate → validate → execute → retry loop (`backend/app/agent.py`) | **Keep the pattern.** It becomes the SQL agent's subgraph. Swap Postgres for Athena and OpenAI for Bedrock. |
| sqlglot safety layer (`backend/app/safety.py`) | **Keep and adapt.** Switch the dialect to Athena/Trino, swap the Postgres function blocklist for a Trino one, and add a rule that forces a `LIMIT`. |
| Schema introspection via SQLAlchemy (`backend/app/schema.py`) | **Replace** with the Glue Data Catalog, with column comments taken from the data dictionary |
| FastAPI `/query`, `/schema` | **Keep and extend:** add `/chat` (session-aware) and `/trace/{id}` |
| MCP server | **Keep.** The assistant is also exposed as an MCP tool. |
| Next.js + Recharts UI | **Keep and extend.** No rewrite. |
| `test_safety.py` | Keep and expand |

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Dataset | Dunnhumby "The Complete Journey" (alternative: M5) | It's relational (transactions, products, households, demographics, campaigns, coupons, causal data), so SQL questions with joins come naturally, and the campaign tables give the RAG side real material |
| API hosting | FastAPI container on **Lambda** (Lambda Web Adapter) behind a Function URL, outside any VPC | About $0 when idle; reaches Bedrock, Athena and DynamoDB without NAT or VPC endpoints. App Runner is closed to new customers as of April 30, 2026. |
| Vector store | **Aurora PostgreSQL Serverless v2 + pgvector**, min 0 ACU, accessed through the **RDS Data API** | The Data API (HTTPS) lets the Lambda stay out of a VPC. The cost is a ~15s cold resume. |
| Hosting fallback | ECS Fargate in a public subnet (no NAT), RDS in a private subnet | Use this if Lambda + Data API causes friction. About $35–40/month idle because of the ALB. |
| Frontend | Static Next export on S3 + CloudFront | Cheap and simple |
| LLMs | Claude on Bedrock: Haiku-class for the planner and data-quality summaries, Sonnet-class for SQL and synthesis. Model IDs set in config. | Cost and latency split |
| Embeddings | Titan Text Embeddings V2 (1024-dim) | Native to Bedrock, cheap |
| Orchestration | LangGraph supervisor graph | Already a dependency; supports planning, tool use and loops |
| Memory | DynamoDB, `PK=session_id`, `SK=turn#<ts>`, with TTL | Supports follow-up questions |
| Audit log | DynamoDB `audit` table plus structured JSON in CloudWatch Logs | Every query: user, question, SQL, bytes scanned, status |
| Tracing | OpenTelemetry span per graph node → X-Ray / CloudWatch, plus EMF custom metrics | Per-agent-step observability |

### Principles

1. **CDK from day one.** Every phase adds its own stack. No resources created by clicking in the console.
2. **Eval-driven development.** The eval suite starts in Phase 1 and grows with the system, so every change is measured.
3. **`Warehouse` interface with Athena and DuckDB backends** over the same Parquet files. Unit tests and local dev run offline for free, and the real Athena + Bedrock evals run in CI.
4. **Fault injection for data quality,** so the data-quality agent has real problems to find.

## Target repo layout

```
sqlsense/
├─ backend/app/
│  ├─ graph.py                 # supervisor LangGraph
│  ├─ agents/  planner.py  sql_agent.py  retrieval_agent.py  synthesizer.py
│  ├─ warehouse/  base.py  athena.py  duckdb_local.py  catalog.py (Glue)
│  ├─ retrieval/  embed.py  store.py (pgvector via Data API)  ingest.py
│  ├─ memory.py  audit.py  observability.py  safety.py  llm.py (Bedrock)
│  ├─ api.py  mcp_server.py
├─ dq_agent/                   # Lambda: checks + LLM summary
├─ data/      download.py  to_parquet.py  replay.py (simulated refresh)
├─ corpus/    data_dictionary/  metrics/  campaigns/  policies/   (markdown)
├─ evals/     questions.yaml  run_eval.py  scorers.py  results/
├─ infra/     CDK app: Data, Retrieval, App, Pipeline, Observability stacks
├─ frontend/
├─ docs/
└─ .github/workflows/  ci.yml  eval.yml  deploy.yml
```

---

## Phase 0: Foundations (~2–3 days)

- [ ] AWS Budgets alarms ($10 and $25) before anything else; turn on Cost Anomaly Detection.
- [ ] Sign in through IAM Identity Center (no root use, no long-lived access keys). Enable Bedrock model access in one region.
- [ ] `cdk bootstrap`; create an empty CDK app in `infra/`.
- [ ] GitHub OIDC → IAM role for CI (no stored AWS keys).
- [ ] Restructure the backend into the target layout. Add `llm.py` using `ChatBedrockConverse` (langchain-aws) and drop OpenAI.
- [ ] Set up `uv`, `ruff` and `pytest` in `ci.yml` (lint plus unit tests on every PR).

**Done when:** v1 still works on local Postgres, but through Bedrock, and CI is green.

## Phase 1: Data lake + SQL agent on Athena (~1.5–2 weeks)

**Data**
- [ ] `data/to_parquet.py`: convert the CSVs to Parquet (pyarrow), with `transaction_data` partitioned by `week_no`.
- [ ] Star schema: `fact_transactions`, `dim_product`, `dim_household`, `dim_campaign`, `fact_coupon_redemption`, `fact_causal`, plus a `dim_date` built from the integer `DAY`/`WEEK_NO` so date questions read naturally.
- [ ] Load into `s3://…/raw/` and `…/curated/`; run a Glue crawler into a `retail` database. Add column comments to Glue tables (the SQL agent reads them).
- [ ] **CDK `DataStack`:** encrypted buckets with public access blocked and lifecycle rules on Athena results; Glue DB + crawler; Athena workgroup with `EnforceWorkGroupConfiguration` and `BytesScannedCutoffPerQuery` (e.g. 1 GB); `QueryRole` limited to Athena on that workgroup, `glue:Get*` on `retail`, and `s3:GetObject` on `curated/`.

**SQL agent**
- [ ] `warehouse/athena.py`: start the query, poll, page results, return rows plus `bytes_scanned` and the execution ID.
- [ ] `warehouse/duckdb_local.py`: same interface, reading the local Parquet files.
- [ ] `catalog.py`: compact schema text from Glue. Once there are 6+ tables, prune the schema per question by picking relevant tables from embeddings of table and column descriptions.
- [ ] Safety: `read="athena"`, a Trino function blocklist, reject anything not a SELECT, enforce `LIMIT`. Keep the existing tests and add Athena-specific cases.
- [ ] Retry loop: feed Athena error messages back. Add an `EXPLAIN` pre-check that catches syntax errors before paying for a scan.
- [ ] Few-shot examples: 8–10 verified question → SQL pairs, retrieved by similarity.

**Eval v0**
- [ ] `evals/questions.yaml` with 15 questions that each have gold SQL. Score by result-set match (order-insensitive, numeric tolerance), not by comparing SQL text.
- [ ] Run it from the CLI; record the baseline in `evals/results/`.

**Done when:** `POST /query` answers "top 10 commodities by sales in the last 13 weeks" against Athena, and the baseline accuracy is recorded.

## Phase 2: RAG, planner, memory, UI (~2 weeks)

**Document corpus** (synthetic, and labeled as synthetic)
- [ ] **Data dictionary:** generated from Glue, then edited by hand (grain, caveats like "SALES_VALUE excludes coupon discounts").
- [ ] **Metric definitions (~12):** active household, basket size, promo lift, coupon redemption rate, retention, and so on.
- [ ] **Campaign briefs (~15–30):** one per campaign (TypeA/B/C), with goal, target segment and dates, based on the real `campaign_desc` and `coupon` tables.
- [ ] **Policy docs:** fiscal calendar, returns handling.

**Retrieval agent**
- [ ] Chunk by markdown heading (~400–800 tokens), with metadata (`doc_type`, `campaign_id`, `metric_name`).
- [ ] Hybrid search: pgvector cosine plus Postgres `tsvector` keyword search, merged with reciprocal rank fusion (RRF). Return chunks with citations.
- [ ] **CDK `RetrievalStack`:** Aurora Serverless v2 (min 0 ACU), Data API enabled, credentials in Secrets Manager, plus an ingest script.

**Planner and graph**
- [ ] The planner outputs structured `{route: sql | docs | both | clarify | refuse, sub_questions, needs_definitions[]}`.
- [ ] The **"both" route runs in sequence:** retrieval first resolves definitions (e.g. "active household = ≥1 purchase in the trailing 8 weeks"), and those go to the SQL agent as context.
- [ ] A synthesizer writes the final answer with the numbers, the SQL, the citations and a chart spec.
- [ ] Memory: load the last N turns from DynamoDB; the planner rewrites follow-ups into standalone questions.

**UI** (extend the existing Next app)
- [ ] Chat thread with session ID; answer card; collapsible SQL; citations; Recharts chart.
- [ ] Agent trace panel: a timeline of planner → retrieval → SQL attempts (with errors) → synthesis, with latency, tokens and bytes scanned per step.

**Eval v1:** grow to ~35 questions and add scoring for routing accuracy and retrieval recall@5.

## Phase 3: Production layer (~2 weeks)

**Eval in CI**
- [ ] ~50 questions across categories: simple aggregates (10), joins (10), time windows (8), definition-dependent "both" questions (8), docs-only (6), follow-ups (4), and adversarial/refusal cases (4).
- [ ] Metrics: execution accuracy, routing accuracy, retrieval recall@k, docs-answer faithfulness (an LLM judge checked against reference answers), p50/p95 latency, $/question, average bytes scanned.
- [ ] `eval.yml`: run on PRs that touch `backend/`, `corpus/` or `evals/` (via the OIDC role). Post a markdown table comment with the change against `main`, and fail if accuracy drops by more than 3 points.

**Observability and governance**
- [ ] OTel span per node (question ID, route, attempt, tokens, bytes) → X-Ray. EMF metrics → CDK CloudWatch dashboard plus alarms (error rate, p95 latency, Bedrock spend).
- [ ] Audit record for every query. Rate limiting, plus a demo password or Cognito in front of the public endpoint.
- [ ] *Stretch:* Lake Formation column-level permissions that hide household income fields from a restricted analyst role.

**Pipeline and data-quality agent**
- [ ] `data/replay.py` simulates a refresh by appending the next week's partition from data held back.
- [ ] **CDK `PipelineStack`:** EventBridge schedule → Step Functions: `Ingest week → Crawl/add partition → DQ Agent Lambda → SNS (email)`.
- [ ] Deterministic checks: row-count z-score against a trailing 8-week window, null rates, sales by store against history, schema diff via Glue `GetTableVersions`. The LLM investigates flagged anomalies (using the SQL agent as a tool to drill down) and writes the summary. It never decides what counts as an anomaly.
- [ ] Fault-injection flag: drop a column, zero out a store, duplicate a day.

**Ship**
- [ ] `cdk deploy --all` from a clean account works, verified once in a fresh region.
- [ ] README: architecture diagram, eval results table (with history), cost breakdown, design decisions and trade-offs, and scaling notes (Redshift/Iceberg, semantic layer, query caching).
- [ ] 2-minute demo: a "both" question → trace panel → follow-up → data-quality alert from an injected fault.

---

## Cost guardrails (dev)

| Service | Expected |
|---|---|
| Athena | < $1/month |
| Bedrock (including CI evals) | ~$5–15/month |
| Aurora Serverless v2 at 0 ACU | storage only, ~$1/month |
| Lambda, DynamoDB, S3 | ~$0 |
| Glue crawler | < $1/month |
| **Total** | **~$10–20/month** |

Avoid NAT gateways, OpenSearch Serverless, always-on ALBs, and VPC interface endpoints. These cause most of the surprise bills on side projects.
