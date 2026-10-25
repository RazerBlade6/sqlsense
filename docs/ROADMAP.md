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
| LLMs | Claude on Bedrock: Haiku 5.5 for the planner and data-quality summaries, Sonnet 5.5 for SQL and synthesis. Amazon Nova Micro/Pro until Claude access is live. Model IDs set in config. | Cost and latency split |
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

## Platform constraints

The AWS account is a single-Region project in **ap-southeast-2**, and its managed service control policies shape a few choices:

| Constraint | Consequence |
|---|---|
| One Region only | Everything deploys to ap-southeast-2. Bedrock calls go through `au.*` (Claude) or `apac.*` (Nova) cross-Region inference profiles. |
| IAM Identity Center unavailable | Human sign-in is managed by the platform (`aws login` locally). |
| App Runner unavailable | Confirms Lambda for hosting. |

## Phase 0: Foundations ✅

- [x] AWS Budgets alarm ($25/month; alerts at 50%, 100% and forecast 100%). The alert email lives in SSM (`/sqlsense/budget-email`), not the repo.
- [x] Bedrock model access: Nova and Titan working. Claude agreements accepted; invocation is pending account review.
- [x] `cdk bootstrap`; CDK app in `infra/` with a `SqlSenseFoundation` stack.
- [x] GitHub OIDC with no stored AWS keys: `sqlsense-github-ci` (Bedrock invoke only; branches and PRs) and `sqlsense-github-deploy` (can only assume the CDK bootstrap roles; GitHub `production` environment only). Sessions last at most 1 hour.
- [x] Backend moved to `uv` and Python 3.13. `app/llm.py` wraps `ChatBedrockConverse` with model IDs set in config; OpenAI removed. Claude uses Bedrock JSON-schema structured output, because newer Claude models reject forced tool choice.
- [x] `ci.yml`: ruff, pytest, frontend lint/build and `cdk synth` on every PR, plus a live Bedrock test.

**Done when:** the SQL agent generates safe SQL through Bedrock (verified by `pytest -m live`) and CI is green. *Running v1 end to end on local Postgres was dropped: Phase 1 replaces Postgres with DuckDB/Athena.*

## Delivery pipeline

Single `production` environment. Branch flow: `dev` → PR → `main`.

| Stage | Trigger | What runs |
|---|---|---|
| CI | push to `dev`/`main`, any PR | ruff, pytest, frontend lint/build, `cdk synth`, live Bedrock test (OIDC) |
| Plan | PR into `main` | `cdk diff` posted as a PR comment (read-only CI role) |
| Deploy | merge to `main` | GitHub `production` environment (manual approval, `main` only) → `sqlsense-github-deploy` → `cdk deploy` |
| Verify | after deploy | smoke test (Athena row counts equal the build manifest), then the eval on Athena |

`main` is protected: changes go through a PR, all CI checks must pass on an up-to-date branch, and force pushes and deletion are blocked. `SqlSenseFoundation` (budget, OIDC roles) is deployed manually and never by CD, so the pipeline can't change its own permissions.

Hardening backlog: cdk-nag in `cdk synth`; re-bootstrap with a least-privilege CloudFormation execution policy instead of the default `AdministratorAccess`; a staging environment with eval-gated promotion.

## Phase 1: Data lake + SQL agent on Athena ✅

**Data** (details in [DATA.md](DATA.md))
- [x] `catalog/retail.yaml` is the single source of truth for 9 tables (star schema: transactions, promotions, products, household demographics, campaigns, coupons, dates). Every column has a comment the agent reads.
- [x] `data/build.py`: pinned, checksummed download of The Complete Journey 2.0 (CC0) → strict casts → zstd Parquet, with the large fact tables partitioned by `week`. Builds are deterministic, and a row-count manifest is written.
- [x] **CDK `SqlSenseData`:** private, TLS-only bucket; data published as a CDK asset; explicit Glue tables with partition projection (no crawler); Athena workgroup with enforced settings, a 100 MB per-query scan cap and managed query results; read-only `sqlsense-warehouse-read` policy.

**SQL agent**
- [x] `Warehouse` interface: `athena.py` (Glue schema, polling with backoff, typed results, bytes scanned) and `duckdb_local.py` (same Parquet, Athena SQL transpiled by sqlglot, sandboxed to the warehouse directory).
- [x] Safety rewritten on the syntax tree: single SELECT only, an allowlist of catalog tables and CTEs (rejects table functions such as `read_csv`), comment detection by tokenizing, and a LIMIT added when missing.
- [x] Retry loop feeds validation and Athena errors back, and records each attempt for the UI trace.
- [x] Postgres/SQLAlchemy removed.
- Dropped: an `EXPLAIN` pre-check. Athena doesn't bill queries that fail at planning, so it would add about 1s per question with no savings.
- Deferred: schema pruning (unnecessary at 9 tables) and few-shot examples. Examples drawn from the eval set would inflate scores; they come back with a held-out set.

**Eval v0** (details in [EVALS.md](EVALS.md))
- [x] 15 questions with gold SQL, scored by execution accuracy. Baseline on Nova Pro: **87% DuckDB / 80% Athena**; every miss is a definition question.
- [x] CI runs the eval on DuckDB for every push and PR; CD runs it on Athena after each deploy. Both gates are set at 70%.

**CD**
- [x] `cd.yml`: on merge to `main` → `production` approval → `cdk deploy SqlSenseData` (OIDC deploy role) → smoke test (Athena row counts equal the build manifest) → Athena eval.
- [x] PRs into `main` get a `cdk diff` comment from the read-only CI role.

**Done when:** `POST /query` answers "top 10 categories by sales in the last 13 weeks" against Athena ✅ (weeks 41–53, partition-filtered, 1.7 MB scanned, 1.3 s). Baseline recorded ✅.

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
