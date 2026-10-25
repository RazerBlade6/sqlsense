"""Live checks against Amazon Bedrock. Run with: uv run pytest -m live"""

import pytest

from app.agents.sql_agent import SQLQueryAgent
from app.config import Settings
from app.warehouse.catalog import load_catalog
from app.warehouse.duckdb_local import DEFAULT_DATA_PATH, DuckDBWarehouse


@pytest.mark.live
def test_sql_agent_answers_from_local_warehouse() -> None:
    catalog = load_catalog()
    if not (DEFAULT_DATA_PATH / catalog["database"]).exists():
        pytest.skip("run data/build.py first")
    agent = SQLQueryAgent(DuckDBWarehouse(catalog), Settings())

    response = agent.run("How many distinct households made a purchase?")

    assert response.error is None, response.attempt_log
    assert response.rows and list(response.rows[0].values()) == [2469]
