from mcp.server.mcpserver import MCPServer

from app.agents.sql_agent import SQLQueryAgent
from app.api import get_assistant
from app.config import get_settings
from app.warehouse.factory import get_warehouse

mcp = MCPServer("sqlsense")


@mcp.tool()
def ask_assistant(question: str) -> dict:
    """Answer a question about the retail business from the warehouse and business documents.

    Returns the answer, the route taken, any SQL and results, document citations and a trace.
    """
    return get_assistant().ask(question).model_dump(mode="json")


@mcp.tool()
def ask_warehouse(question: str, max_attempts: int = 3) -> dict:
    """Answer a natural-language question about the retail warehouse with a safe, read-only query."""
    agent = SQLQueryAgent(get_warehouse(), get_settings())
    return agent.run(question, max_attempts).model_dump(mode="json")


@mcp.tool()
def get_warehouse_schema() -> dict:
    """Return the tables, columns and descriptions the SQL agent sees."""
    warehouse = get_warehouse()
    return {"engine": warehouse.engine, "summary": warehouse.schema_summary()}


if __name__ == "__main__":
    mcp.run()
