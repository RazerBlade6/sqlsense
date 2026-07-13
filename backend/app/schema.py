from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def build_schema_summary(engine: Engine, schema_names: list[str]) -> str:
    inspector = inspect(engine)
    lines: list[str] = []

    for schema in schema_names:
        tables = inspector.get_table_names(schema=schema)
        views = inspector.get_view_names(schema=schema)
        for table_name in sorted(tables + views):
            columns = inspector.get_columns(table_name, schema=schema)
            primary_key = inspector.get_pk_constraint(table_name, schema=schema).get(
                "constrained_columns", []
            )
            foreign_keys = inspector.get_foreign_keys(table_name, schema=schema)
            column_bits = []
            for column in columns:
                bit = f"{column['name']} {column['type']}"
                if column["name"] in primary_key:
                    bit += " primary key"
                if not column.get("nullable", True):
                    bit += " not null"
                column_bits.append(bit)

            qualified_name = f"{schema}.{table_name}"
            lines.append(f"Table {qualified_name}: {', '.join(column_bits)}")
            for fk in foreign_keys:
                referred = f"{fk.get('referred_schema') or schema}.{fk['referred_table']}"
                lines.append(
                    "  FK "
                    f"{', '.join(fk['constrained_columns'])} -> "
                    f"{referred}({', '.join(fk['referred_columns'])})"
                )

    if not lines:
        return "No tables or views were found in the configured schemas."

    return "\n".join(lines)


def execute_read_only_sql(
    engine: Engine,
    sql: str,
    max_rows: int,
    statement_timeout_ms: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
            result = connection.execute(text(sql))
            rows = result.fetchmany(max_rows)
            columns = list(result.keys())
            payload = [dict(zip(columns, row, strict=False)) for row in rows]
            transaction.commit()
            return columns, payload
        except Exception:
            transaction.rollback()
            raise
