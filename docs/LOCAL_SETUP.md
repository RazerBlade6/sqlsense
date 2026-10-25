# Local Setup

How to run SQLSense locally and deploy its infrastructure. This changes as v2 lands (see [ROADMAP.md](ROADMAP.md)).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 for you)
- Node.js 24
- AWS CLI v2, signed in with `aws login`, with the default Region set to `ap-southeast-2`

## Data

```bash
cd data
uv sync
uv run python build.py     # ~40 MB download (cached in data/raw), ~10 s build
```

This writes the Parquet warehouse to `data/warehouse/`. See [DATA.md](DATA.md).

## Backend

```bash
cd backend
uv sync
cp ../.env.example .env
uv run uvicorn app.api:app --reload --port 8000
```

The LLMs run on Amazon Bedrock using your AWS credentials; there is no API key to set. By default, queries run on a local DuckDB over `data/warehouse/`. Set `WAREHOUSE=athena` to query the deployed warehouse instead.

```env
WAREHOUSE=duckdb             # or athena
SQL_MODEL_ID=apac.amazon.nova-pro-v1:0
```

## Tests

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run pytest            # unit tests, no AWS calls
uv run pytest -m live    # calls Bedrock
uv run python -m evaluation.runner   # eval suite, see EVALS.md
WAREHOUSE=athena uv run python -m evaluation.smoke   # deployed data matches the build
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

By default, the frontend calls `http://localhost:8000`.

## Infrastructure

```bash
cd infra
npm ci && uv sync
uv run pytest             # catalog checks and CDK assertions on security controls
npx cdk synth
```

| Stack | Deployed by | Contents |
|---|---|---|
| `SqlSenseFoundation` | hand (`npx cdk deploy SqlSenseFoundation`) | budget alarm, GitHub OIDC roles |
| `SqlSenseData` | CD on merge to `main` | warehouse bucket and data, Glue tables, Athena workgroup, read policy |

The budget alert email is read from the SSM parameter `/sqlsense/budget-email`. Synthesizing `SqlSenseData` requires a built `data/warehouse/`.

### CI/CD credentials

GitHub Actions authenticates with OIDC; no AWS keys are stored in the repo or its secrets.

| Role | Trusted for | Can do |
|---|---|---|
| `sqlsense-github-ci` | any branch push or pull request in this repo | invoke the configured Bedrock models |
| `sqlsense-github-deploy` | jobs in the `production` GitHub environment | assume the CDK bootstrap roles (`cdk deploy`) |

## API

```http
POST /query
Content-Type: application/json

{
  "question": "Which 5 departments had the highest sales?",
  "max_attempts": 3
}
```

The response includes the final SQL, rows and columns, an explanation, a chart specification, each attempt (with any error), and the engine, bytes scanned and execution time.

## MCP Server

Run the MCP server over stdio:

```bash
cd backend
uv run python -m app.mcp_server
```

It exposes:

- `ask_warehouse(question, max_attempts)`: generate, validate, execute, and recover if needed.
- `get_warehouse_schema()`: return the tables, columns and descriptions the agent sees.

## Safety Model

Generated SQL passes several independent layers before and during execution:

- **Validator (`app/safety.py`):** parses the SQL into a syntax tree (Athena dialect). It requires exactly one SELECT and rejects any write or DDL node. Every table must be a catalog table or a CTE, which rules out other databases and table functions such as `read_csv`. Comments are rejected, and a LIMIT is added when one is missing.
- **Athena:** queries run as the read-only `sqlsense-warehouse-read` policy (no writes anywhere). The workgroup's settings are enforced and it refuses queries that would scan more than 100 MB.
- **DuckDB (local):** file access is confined to the warehouse directory, and the configuration is locked before any generated SQL runs.
- **Recovery:** validation and execution errors go back to the agent, which gets up to the configured number of attempts.
