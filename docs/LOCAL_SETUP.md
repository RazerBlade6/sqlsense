# Local Setup (v1)

These instructions run the current v1 stack: FastAPI + LangGraph against a local PostgreSQL, with the Next.js frontend. They will change as v2 lands (see [ROADMAP.md](ROADMAP.md)).

## Backend

```bash
docker compose up -d          # local PostgreSQL
cd backend
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000
```

Set at least:

```env
OPENAI_API_KEY=...
DATABASE_URL=postgresql+psycopg://readonly_user:password@localhost:5432/appdb
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

By default, the frontend calls `http://localhost:8000`.

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
python -m app.mcp_server
```

It exposes:

- `ask_database(question, max_attempts)`: generate, validate, execute, and recover if needed.
- `get_database_schema()`: return the schema summary supplied to the agent.

## Safety Model

SQLSense enforces read-only access in several layers:

- The LLM prompt asks only for PostgreSQL `SELECT` statements.
- `sqlglot` parses the generated SQL before execution.
- Multiple statements, comments, DDL, DML, `SELECT INTO`, administrative commands, and risky functions are rejected.
- Queries execute inside a PostgreSQL `READ ONLY` transaction with a statement timeout.
- Failed SQL is sent back through a LangGraph recovery loop and regenerated up to the configured attempt limit.

Use a database role with read-only permissions as an additional production guard.
