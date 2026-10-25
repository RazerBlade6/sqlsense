# Local Setup

How to run SQLSense locally and deploy its infrastructure. This changes as v2 lands (see [ROADMAP.md](ROADMAP.md)).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 for you)
- Node.js 24
- AWS CLI v2, signed in with `aws login`, with the default Region set to `ap-southeast-2`
- A Docker engine (Colima or Docker Desktop), only needed for the local Postgres

## Backend

```bash
cd backend
uv sync
cp ../.env.example .env
uv run uvicorn app.api:app --reload --port 8000
```

The LLMs run on Amazon Bedrock using your AWS credentials; there is no API key to set. Choose models in `.env`:

```env
SQL_MODEL_ID=apac.amazon.nova-pro-v1:0
PLANNER_MODEL_ID=apac.amazon.nova-micro-v1:0
DATABASE_URL=postgresql+psycopg://readonly_user:password@localhost:5432/appdb
```

`docker compose up -d` from the repo root starts a local Postgres.

## Tests

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run pytest            # unit tests, no AWS calls
uv run pytest -m live    # calls Bedrock
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
npx cdk synth
npx cdk deploy SqlSenseFoundation
```

The `SqlSenseFoundation` stack reads the budget alert email from the SSM parameter `/sqlsense/budget-email`.

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
  "question": "How many new users signed up today?",
  "max_attempts": 3
}
```

The response includes the final SQL, rows, columns, explanation, attempt count, and a chart specification.

## MCP Server

Run the MCP server over stdio:

```bash
cd backend
uv run python -m app.mcp_server
```

It exposes:

- `ask_database(question, max_attempts)`: generate, validate, execute, and recover if needed.
- `get_database_schema()`: return the schema summary supplied to the agent.

## Safety Model

SQLSense enforces read-only access in several layers:

- The LLM prompt asks only for read-only `SELECT` statements.
- `sqlglot` parses the generated SQL before execution.
- Multiple statements, comments, DDL, DML, `SELECT INTO`, administrative commands, and risky functions are rejected.
- Queries execute inside a PostgreSQL `READ ONLY` transaction with a statement timeout.
- Failed SQL is sent back through a LangGraph recovery loop and regenerated up to the configured attempt limit.

Use a database role with read-only permissions as an additional production guard.
