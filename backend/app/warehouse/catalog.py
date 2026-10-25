"""Schema text for the SQL agent, built from catalog/retail.yaml or the Glue Data Catalog."""

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[3] / "catalog" / "retail.yaml"


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def table_names(catalog: dict[str, Any]) -> set[str]:
    return {table["name"] for table in catalog["tables"]}


def format_table(
    database: str,
    name: str,
    description: str,
    grain: str | None,
    partition_key: str | None,
    columns: list[tuple[str, str, str]],
) -> str:
    header = f"Table {database}.{name}: {description}"
    if grain:
        header += f" Grain: one row per {grain}."
    if partition_key:
        header += f" Partitioned by {partition_key}; filter on it to scan less data."
    lines = [header] + [f"  - {col} {col_type}: {comment}" for col, col_type, comment in columns]
    return "\n".join(lines)


def summary_from_catalog(catalog: dict[str, Any]) -> str:
    return "\n\n".join(
        format_table(
            catalog["database"],
            table["name"],
            table["description"],
            table.get("grain"),
            table.get("partition_by"),
            [(c["name"], c["type"], c["comment"]) for c in table["columns"]],
        )
        for table in catalog["tables"]
    )


def summary_from_glue(glue_tables: list[dict[str, Any]], database: str) -> str:
    """Same format as summary_from_catalog, from glue:GetTables output."""
    blocks = []

    def position(table: dict[str, Any]) -> tuple[int, str]:
        return (int(table.get("Parameters", {}).get("catalog_position", 10**6)), table["Name"])

    for table in sorted(glue_tables, key=position):
        storage_columns = table["StorageDescriptor"]["Columns"]
        partition_keys = table.get("PartitionKeys", [])
        columns = [
            (c["Name"], c["Type"], c.get("Comment", "")) for c in storage_columns + partition_keys
        ]
        blocks.append(
            format_table(
                database,
                table["Name"],
                table.get("Description", ""),
                table.get("Parameters", {}).get("grain"),
                partition_keys[0]["Name"] if partition_keys else None,
                columns,
            )
        )
    return "\n\n".join(blocks)
