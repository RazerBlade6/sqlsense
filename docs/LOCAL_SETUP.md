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

The LLMs and embeddings run on Amazon Bedrock using your AWS credentials; there is no API key to set. Everything else defaults to local:

| Setting | Local default | Deployed |
|---|---|---|
| `WAREHOUSE` | `duckdb` over `data/warehouse/` | `athena` |
| `RETRIEVAL_STORE` | `local`: the corpus is embedded in memory at the first question (a few seconds) | `pgvector`, with `DB_CLUSTER_ARN` and `DB_SECRET_ARN` |
| `MEMORY_STORE` | `local` (in-process) | `dynamodb` (`SESSIONS_TABLE`) |
| `DAILY_QUESTION_LIMIT` | `0` (no limit) | `300` |

Model IDs (`PLANNER_MODEL_ID`, `SQL_MODEL_ID`, `SYNTHESIZER_MODEL_ID`, `EMBEDDING_MODEL_ID`) are set in `.env.example`.

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

By default, the frontend calls `http://localhost:8000`. The deployed site reads the API URL from `/config.json`, which the CDK deploy writes next to the static files. `npm run build` produces the static export in `frontend/out/`.

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
| `SqlSenseRetrieval` | CD on merge to `main` | Aurora Serverless v2 with pgvector, isolated VPC, database secrets, corpus ingest custom resource |
| `SqlSenseApp` | CD on merge to `main` | API Lambda (container image) with a Function URL, DynamoDB sessions table, S3 + CloudFront site |

The budget alert email is read from the SSM parameter `/sqlsense/budget-email`. Synthesis needs a built `data/warehouse/` and `frontend/out/`; deploying needs Docker to build the Lambda image (`backend/Dockerfile`, built from the repository root).

### CI/CD credentials

GitHub Actions authenticates with OIDC; no AWS keys are stored in the repo or its secrets.

| Role | Trusted for | Can do |
|---|---|---|
| `sqlsense-github-ci` | any branch push or pull request in this repo | invoke the configured Bedrock models |
| `sqlsense-github-deploy` | jobs in the `production` GitHub environment | assume the CDK bootstrap roles (`cdk deploy`) |

## API

`POST /chat` is the assistant. Send the returned `session_id` back for follow-up questions.

```http
POST /chat
Content-Type: application/json

{"question": "And in Q2?", "session_id": "3f0c..."}
```

The response has the route, the standalone question the planner understood, the answer, citations, the SQL result (if any) and the trace: each step's duration, tokens and bytes scanned, every SQL attempt and its error, and the retrieved documents with their vector and keyword ranks.

`POST /query` runs the SQL agent alone:

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

- `ask_assistant(question)`: the full assistant (route, answer, citations, SQL result, trace).
- `ask_warehouse(question, max_attempts)`: generate, validate, execute, and recover if needed.
- `get_warehouse_schema()`: return the tables, columns and descriptions the agent sees.

## Safety Model

Generated SQL passes several independent layers before and during execution:

- **Validator (`app/safety.py`):** parses the SQL into a syntax tree (Athena dialect). It requires exactly one SELECT and rejects any write or DDL node. Every table must be a catalog table or a CTE, which rules out other databases and table functions such as `read_csv`. Comments are rejected, and a LIMIT is added when one is missing.
- **Athena:** queries run as the read-only `sqlsense-warehouse-read` policy (no writes anywhere). The workgroup's settings are enforced and it refuses queries that would scan more than 100 MB.
- **DuckDB (local):** file access is confined to the warehouse directory, and the configuration is locked before any generated SQL runs.
- **Recovery:** validation and execution errors go back to the agent, which gets up to the configured number of attempts.
- **Planner:** routes requests to change data, identify households or go off topic to `refuse`. This saves cost and gives a clear message; the layers above enforce safety regardless of the route.

### The public endpoint

The deployed API is a public Lambda Function URL so the demo works without sign-in, and every question costs Bedrock calls. Phase 3 adds authentication. Until then:
- **Daily budget:** an atomic, conditional DynamoDB counter caps questions per day at 300, and further requests get HTTP 429.
- **Concurrency:** reserved concurrency of 10 caps parallel requests.
- **Least privilege:** the function's role can:
  - read the warehouse;
  - invoke the listed models;
  - run Data API statements as the `SELECT`-only database role;
  - query, put and update items in its own table.
  It cannot delete items or read the database admin secret, and infra tests enforce this.
- **Logging:** errors are logged server-side, and clients get a generic message.
- **CORS:** only the CloudFront site's origin is allowed.
