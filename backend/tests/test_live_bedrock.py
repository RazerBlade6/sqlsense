"""Live checks against Amazon Bedrock. Run with: uv run pytest -m live"""

import pytest

from app.agents.sql_agent import SQLQueryAgent
from app.config import Settings
from app.safety import validate_select_sql

SCHEMA = (
    "Table public.users: id integer primary key, email text not null, "
    "plan text, created_at timestamp not null"
)


@pytest.mark.live
def test_sql_agent_generates_safe_sql() -> None:
    settings = Settings(DATABASE_URL="postgresql+psycopg://unused@localhost/unused")
    agent = SQLQueryAgent(engine=None, settings=settings)  # type: ignore[arg-type]

    state = agent._generate_sql(
        {"question": "How many users are on each plan?", "schema": SCHEMA, "attempts": 0}
    )

    sql = validate_select_sql(state["sql"])
    assert "users" in sql.lower()
    assert "group by" in sql.lower()
    assert state["attempts"] == 1
