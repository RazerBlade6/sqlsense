from datetime import date

import pytest
from botocore.stub import Stubber

from app.warehouse import WarehouseError
from app.warehouse.athena import AthenaWarehouse
from app.warehouse.catalog import load_catalog, summary_from_catalog, summary_from_glue
from app.warehouse.duckdb_local import DEFAULT_DATA_PATH, DuckDBWarehouse

CATALOG = load_catalog()


@pytest.fixture(scope="module")
def duck() -> DuckDBWarehouse:
    if not (DEFAULT_DATA_PATH / CATALOG["database"]).exists():
        pytest.skip("run data/build.py first")
    return DuckDBWarehouse(CATALOG)


def test_glue_summary_matches_catalog_summary() -> None:
    """The agent sees exactly the same schema text locally (YAML) and on AWS (Glue)."""
    glue_tables = []
    for position, table in enumerate(CATALOG["tables"]):
        key = table.get("partition_by")
        cols = [
            {"Name": c["name"], "Type": c["type"], "Comment": c["comment"]}
            for c in table["columns"]
        ]
        glue_tables.append(
            {
                "Name": table["name"],
                "Description": table["description"],
                "Parameters": {"grain": table["grain"], "catalog_position": str(position)},
                "StorageDescriptor": {"Columns": [c for c in cols if c["Name"] != key]},
                "PartitionKeys": [c for c in cols if c["Name"] == key],
            }
        )
    # Glue returns tables alphabetically; the summary must still follow catalog order.
    glue_tables.sort(key=lambda t: t["Name"])
    assert summary_from_glue(glue_tables, "retail") == summary_from_catalog(CATALOG)


def test_duckdb_runs_athena_dialect(duck: DuckDBWarehouse) -> None:
    result = duck.run(
        "SELECT date_format(transaction_date, '%Y-%m') AS month, count(*) AS n "
        "FROM fact_transactions WHERE week BETWEEN 1 AND 2 GROUP BY 1 ORDER BY 1",
        max_rows=10,
    )
    assert result.columns == ["month", "n"]
    assert result.rows[0]["month"] == "2017-01"


def test_duckdb_partition_and_row_counts(duck: DuckDBWarehouse) -> None:
    rows = duck.run(
        "SELECT count(*) AS n, min(week) AS lo, max(week) AS hi FROM fact_transactions", 1
    ).rows
    assert rows == [{"n": 1_469_307, "lo": 1, "hi": 53}]


def test_duckdb_truncates_to_max_rows(duck: DuckDBWarehouse) -> None:
    result = duck.run("SELECT date_day FROM dim_date ORDER BY 1", max_rows=3)
    assert len(result.rows) == 3 and result.truncated
    assert result.rows[0]["date_day"] == date(2017, 1, 1)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_text('/etc/hosts')",
        "COPY (SELECT 1) TO '/tmp/sqlsense-escape.csv'",
    ],
)
def test_duckdb_blocks_file_access_outside_warehouse(duck: DuckDBWarehouse, sql: str) -> None:
    """Second layer of defense if the SQL validator ever missed something."""
    with pytest.raises(WarehouseError):
        duck.run(sql, max_rows=1)


def test_duckdb_configuration_is_locked(duck: DuckDBWarehouse) -> None:
    with pytest.raises(WarehouseError):
        duck.run("SET enable_external_access = true", max_rows=1)


def test_athena_run_converts_types() -> None:
    warehouse = AthenaWarehouse(region="ap-southeast-2", workgroup="sqlsense", database="retail")
    stub = Stubber(warehouse.athena)
    stub.add_response("start_query_execution", {"QueryExecutionId": "q1"})
    stub.add_response(
        "get_query_execution",
        {
            "QueryExecution": {
                "QueryExecutionId": "q1",
                "Status": {"State": "SUCCEEDED"},
                "Statistics": {"DataScannedInBytes": 2048, "TotalExecutionTimeInMillis": 900},
            }
        },
    )
    stub.add_response(
        "get_query_results",
        {
            "ResultSet": {
                "ResultSetMetadata": {
                    "ColumnInfo": [
                        {"Name": "department", "Type": "varchar"},
                        {"Name": "sales", "Type": "double"},
                        {"Name": "baskets", "Type": "bigint"},
                        {"Name": "first_day", "Type": "date"},
                    ]
                },
                "Rows": [
                    {
                        "Data": [
                            {"VarCharValue": h}
                            for h in ("department", "sales", "baskets", "first_day")
                        ]
                    },
                    {
                        "Data": [
                            {"VarCharValue": "GROCERY"},
                            {"VarCharValue": "10.5"},
                            {"VarCharValue": "3"},
                            {"VarCharValue": "2017-01-01"},
                        ]
                    },
                    {
                        "Data": [
                            {"VarCharValue": "PRODUCE"},
                            {},
                            {"VarCharValue": "1"},
                            {"VarCharValue": "2017-01-02"},
                        ]
                    },
                ],
            }
        },
    )
    with stub:
        result = warehouse.run("SELECT 1", max_rows=10)
    assert result.bytes_scanned == 2048 and result.query_id == "q1"
    assert result.rows == [
        {"department": "GROCERY", "sales": 10.5, "baskets": 3, "first_day": date(2017, 1, 1)},
        {"department": "PRODUCE", "sales": None, "baskets": 1, "first_day": date(2017, 1, 2)},
    ]


def test_athena_failure_surfaces_reason() -> None:
    warehouse = AthenaWarehouse(region="ap-southeast-2", workgroup="sqlsense", database="retail")
    stub = Stubber(warehouse.athena)
    stub.add_response("start_query_execution", {"QueryExecutionId": "q2"})
    stub.add_response(
        "get_query_execution",
        {
            "QueryExecution": {
                "QueryExecutionId": "q2",
                "Status": {"State": "FAILED", "StateChangeReason": "COLUMN_NOT_FOUND: line 1:8"},
            }
        },
    )
    with stub, pytest.raises(WarehouseError, match="COLUMN_NOT_FOUND"):
        warehouse.run("SELECT nope FROM dim_date", max_rows=1)
