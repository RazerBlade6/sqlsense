# SQLSense

Natural-language analytics over SQL data, built with agents.

> **Status: Phase 1 done.** The SQL agent answers plain-English questions over a retail warehouse on S3/Glue/Athena, scoring 80% on the eval suite (see [docs/EVALS.md](docs/EVALS.md)). Next: document retrieval, a planner, memory and the UI.

## v2 at a glance

- **Planner agent** routes each question to warehouse SQL, document retrieval, or both
- **SQL agent** reads the Glue Data Catalog, writes Athena SQL over an S3 Parquet lake, and retries on errors
- **Retrieval agent** does hybrid search over metric definitions, a data dictionary and campaign docs (Bedrock embeddings + pgvector)
- **Data-quality agent** checks each pipeline refresh for anomalies and schema drift
- **Production layer:** eval suite in CI, read-only IAM with Athena scan limits, audit logging, CloudWatch/X-Ray tracing, all infrastructure in AWS CDK

See [docs/ROADMAP.md](docs/ROADMAP.md) for the architecture, decisions and phased plan.

## Stack

FastAPI · LangGraph · sqlglot · Next.js + Recharts · MCP. v2 adds Amazon Bedrock, Athena, Glue, S3, Aurora (pgvector), DynamoDB, Step Functions, Lambda and AWS CDK.

## Layout

```text
backend/    FastAPI app, LangGraph agent, MCP server, SQL safety checks
frontend/   Next.js UI with Recharts visualizations
infra/      AWS CDK app (Python)
catalog/    Warehouse catalog (single source of truth for tables)
data/       Dataset download and Parquet build
evals/      Eval questions and results
docs/       Roadmap, setup, data and eval docs
```

## Quickstart

```bash
cd data && uv sync && uv run python build.py      # build the retail warehouse
cd backend && uv sync && uv run uvicorn app.api:app --reload --port 8000
cd frontend && npm install && npm run dev
```

Requires AWS credentials with Bedrock access (`aws login`). Full setup, tests, infrastructure and the safety model are in [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).
