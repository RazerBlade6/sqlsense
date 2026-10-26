# SQLSense

Natural-language analytics over SQL data, built with agents.

> **Status: Phase 2.** A planner routes each question to warehouse SQL, document retrieval or both, and the UI shows an agent trace for every answer. The assistant scores 94–97% on a 36-question eval; on questions that depend on a business definition it improved from 1/3 to 12/13 (see [docs/EVALS.md](docs/EVALS.md)). Next: the production layer (observability, auth, data-quality agent).

## v2 at a glance

- **Planner agent** routes each question to warehouse SQL, document retrieval, or both
- **SQL agent** reads the Glue Data Catalog, writes Athena SQL over an S3 Parquet lake, and retries on errors
- **Retrieval agent** does hybrid search over metric definitions, a data dictionary and campaign docs (Bedrock embeddings + pgvector)
- **Data-quality agent** checks each pipeline refresh for anomalies and schema drift
- **Production layer:** eval suite in CI, read-only IAM with Athena scan limits, audit logging, CloudWatch/X-Ray tracing, all infrastructure in AWS CDK

See [docs/ROADMAP.md](docs/ROADMAP.md) for the architecture, decisions and phased plan, and [docs/RETRIEVAL.md](docs/RETRIEVAL.md) for how a question flows through the agents.

## Stack

FastAPI · LangGraph · sqlglot · Next.js + Recharts · MCP. v2 adds Amazon Bedrock, Athena, Glue, S3, Aurora (pgvector), DynamoDB, Step Functions, Lambda and AWS CDK.

## Layout

```text
backend/    FastAPI app, LangGraph agents (planner, retrieval, SQL, synthesizer), MCP server
frontend/   Next.js UI with Recharts visualizations
infra/      AWS CDK app (Python)
catalog/    Warehouse catalog (single source of truth for tables)
corpus/     Business documents for retrieval (synthetic)
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
