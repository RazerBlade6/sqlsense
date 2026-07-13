from mcp.server.fastmcp import FastMCP

from app.agent import SQLQueryAgent
from app.config import get_settings
from app.db import get_engine
from app.schema import build_schema_summary


mcp = FastMCP("sqlsense")


@mcp.tool()
def ask_database(question: str, max_attempts: int = 3) -> dict:
    """Answer a natural-language analytics question using safe PostgreSQL SELECT queries."""
    settings = get_settings()
    agent = SQLQueryAgent(get_engine(), settings)
    return agent.run(question, max_attempts).model_dump(mode="json")


@mcp.tool()
def get_database_schema() -> dict:
    """Return the database schema summary visible to the SQL generation agent."""
    settings = get_settings()
    return {
        "schemas": settings.schema_names,
        "summary": build_schema_summary(get_engine(), settings.schema_names),
    }


if __name__ == "__main__":
    mcp.run()
