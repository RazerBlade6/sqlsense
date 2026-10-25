"""Amazon Athena warehouse: Glue catalog for schema, sqlsense workgroup for execution."""

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.warehouse.base import QueryResult, WarehouseError
from app.warehouse.catalog import summary_from_glue

POLL_START_S = 0.2
POLL_MAX_S = 1.0

_CONVERTERS: dict[str, Any] = {
    "tinyint": int,
    "smallint": int,
    "integer": int,
    "bigint": int,
    "double": float,
    "float": float,
    "real": float,
    "decimal": Decimal,
    "boolean": lambda v: v == "true",
    "date": date.fromisoformat,
    "timestamp": lambda v: datetime.fromisoformat(v),
}


class AthenaWarehouse:
    engine = "athena"

    def __init__(self, region: str, workgroup: str, database: str, timeout_s: float = 60.0):
        self.athena = boto3.client("athena", region_name=region)
        self.glue = boto3.client("glue", region_name=region)
        self.workgroup = workgroup
        self.database = database
        self.timeout_s = timeout_s
        self._schema: str | None = None

    def schema_summary(self) -> str:
        if self._schema is None:
            paginator = self.glue.get_paginator("get_tables")
            tables = [
                table
                for page in paginator.paginate(DatabaseName=self.database)
                for table in page["TableList"]
            ]
            self._schema = summary_from_glue(tables, self.database)
        return self._schema

    def run(self, sql: str, max_rows: int) -> QueryResult:
        try:
            query_id = self.athena.start_query_execution(
                QueryString=sql,
                WorkGroup=self.workgroup,
                QueryExecutionContext={"Database": self.database},
            )["QueryExecutionId"]
        except ClientError as exc:
            raise WarehouseError(exc.response["Error"]["Message"]) from exc

        execution = self._wait(query_id)
        statistics = execution.get("Statistics", {})
        columns, rows, truncated = self._results(query_id, max_rows)
        return QueryResult(
            columns=columns,
            rows=rows,
            engine=self.engine,
            bytes_scanned=statistics.get("DataScannedInBytes"),
            execution_ms=statistics.get("TotalExecutionTimeInMillis"),
            query_id=query_id,
            truncated=truncated,
        )

    def _wait(self, query_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        delay = POLL_START_S
        while True:
            execution = self.athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
            status = execution["Status"]
            if status["State"] == "SUCCEEDED":
                return execution
            if status["State"] in ("FAILED", "CANCELLED"):
                raise WarehouseError(status.get("StateChangeReason", status["State"]))
            if time.monotonic() > deadline:
                self.athena.stop_query_execution(QueryExecutionId=query_id)
                raise WarehouseError(f"Query timed out after {self.timeout_s:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, POLL_MAX_S)

    def _results(self, query_id: str, max_rows: int) -> tuple[list[str], list[dict], bool]:
        paginator = self.athena.get_paginator("get_query_results")
        columns: list[str] = []
        converters: list[Any] = []
        rows: list[dict[str, Any]] = []
        first_page = True
        for page in paginator.paginate(QueryExecutionId=query_id):
            result_set = page["ResultSet"]
            if first_page:
                info = result_set["ResultSetMetadata"]["ColumnInfo"]
                columns = [c["Name"] for c in info]
                converters = [_CONVERTERS.get(c["Type"], str) for c in info]
            data = result_set["Rows"][1:] if first_page else result_set["Rows"]
            first_page = False
            for row in data:
                if len(rows) == max_rows:
                    return columns, rows, True
                values = [cell.get("VarCharValue") for cell in row["Data"]]
                rows.append(
                    {
                        col: None if value is None else convert(value)
                        for col, convert, value in zip(columns, converters, values, strict=True)
                    }
                )
        return columns, rows, False
