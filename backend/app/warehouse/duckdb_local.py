"""Local warehouse: DuckDB over the same Parquet files that back Athena."""

import time
from pathlib import Path
from typing import Any

import duckdb
import sqlglot

from app.warehouse.base import QueryResult, WarehouseError
from app.warehouse.catalog import summary_from_catalog

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse"


class DuckDBWarehouse:
    engine = "duckdb"

    def __init__(self, catalog: dict[str, Any], data_path: Path = DEFAULT_DATA_PATH):
        self.catalog = catalog
        root = data_path / catalog["database"]
        if not root.exists():
            raise WarehouseError(f"No local warehouse at {root}. Run data/build.py first.")
        self.con = duckdb.connect()
        database = catalog["database"]
        self.con.execute(f"CREATE SCHEMA {database}")
        for table in catalog["tables"]:
            name = table["name"]
            self.con.execute(f"CREATE VIEW {database}.{name} AS {self._scan(root, table)}")
            # Each cursor is a fresh session, so unqualified names resolve through main.
            self.con.execute(f"CREATE VIEW main.{name} AS SELECT * FROM {database}.{name}")
        # Agent SQL runs after this point: confine file access to the warehouse and freeze settings.
        self.con.execute(f"SET allowed_directories = ['{root}']")
        self.con.execute("SET enable_external_access = false")
        self.con.execute("SET lock_configuration = true")

    @staticmethod
    def _scan(root: Path, table: dict[str, Any]) -> str:
        path = root / table["name"]
        partition_key = table.get("partition_by")
        if partition_key:
            key_type = next(c["type"] for c in table["columns"] if c["name"] == partition_key)
            duck_type = {"int": "INTEGER", "bigint": "BIGINT", "string": "VARCHAR"}[key_type]
            return (
                f"SELECT * FROM read_parquet('{path}/*/*.parquet', hive_partitioning = true, "
                f"hive_types = {{'{partition_key}': {duck_type}}})"
            )
        return f"SELECT * FROM read_parquet('{path}/*.parquet')"

    def schema_summary(self) -> str:
        return summary_from_catalog(self.catalog)

    def run(self, sql: str, max_rows: int) -> QueryResult:
        try:
            local_sql = sqlglot.transpile(sql, read="athena", write="duckdb")[0]
        except sqlglot.errors.SqlglotError as exc:
            raise WarehouseError(f"SQL could not be translated: {exc}") from exc
        started = time.perf_counter()
        try:
            cursor = self.con.cursor()
            cursor.execute(local_sql)
            columns = [d[0] for d in cursor.description]
            fetched = cursor.fetchmany(max_rows + 1)
        except duckdb.Error as exc:
            raise WarehouseError(str(exc)) from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        rows = [dict(zip(columns, row, strict=True)) for row in fetched[:max_rows]]
        return QueryResult(
            columns=columns,
            rows=rows,
            engine=self.engine,
            execution_ms=elapsed_ms,
            truncated=len(fetched) > max_rows,
        )
