# SQLSense

MCP-ready agentic natural-language SQL querying for PostgreSQL.

The system turns questions like "How many new users signed up today?" into safe PostgreSQL `SELECT` statements, executes them, and returns rows plus a chart hint for the frontend. It uses OpenAI GPT-4.1 through LangChain, LangGraph for orchestration, SQLAlchemy for database access, sqlglot for SQL validation, and Next/Recharts for the UI.

## Safety Model

SQLSense enforces read-only access in several layers:

- The LLM prompt asks only for PostgreSQL `SELECT` statements.
- `sqlglot` parses the generated SQL before execution.
- Multiple statements, comments, DDL, DML, `SELECT INTO`, administrative commands, and risky functions are rejected.
- Queries execute inside a PostgreSQL `READ ONLY` transaction with a statement timeout.
- Failed SQL is sent back through a LangGraph recovery loop and regenerated up to the configured attempt limit.

Use a database role with read-only permissions as an additional production guard.

## Project Layout

```text
backend/    FastAPI app, LangGraph agent, MCP server, SQL safety checks
frontend/   Next + React UI with Recharts visualizations
```

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

Set at least:

```env
OPENAI_API_KEY=...
DATABASE_URL=postgresql+psycopg://readonly_user:password@localhost:5432/appdb
```

## MCP Server

Run the MCP server over stdio:

```bash
cd backend
python -m app.mcp_server
```

It exposes:

- `ask_database(question, max_attempts)` - generate, validate, execute, and recover if needed.
- `get_database_schema()` - return the schema summary supplied to the agent.

## Frontend Setup

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
