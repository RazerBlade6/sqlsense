# SQLSense

Natural-language analytics over SQL data, built with agents.

> **Status: v2 upgrade in progress.** v1 (working today) turns plain-English questions into safe, read-only PostgreSQL queries. v2 makes it a multi-agent analytics assistant over a retail data warehouse on AWS.

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
docs/       Roadmap, setup and design docs
```

## Quickstart (v1)

```bash
docker compose up -d
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

Full setup, the API and the safety model are in [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).
