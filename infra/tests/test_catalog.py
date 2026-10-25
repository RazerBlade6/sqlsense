from pathlib import Path

import pytest
import yaml

CATALOG = Path(__file__).resolve().parents[2] / "catalog" / "retail.yaml"
GLUE_TYPES = {"bigint", "int", "double", "string", "date", "timestamp", "boolean"}
TABLES = yaml.safe_load(CATALOG.read_text())["tables"]


@pytest.mark.parametrize("table", TABLES, ids=lambda t: t["name"])
def test_table_fits_glue_limits(table: dict) -> None:
    assert len(table["description"]) <= 2048
    names = [c["name"] for c in table["columns"]]
    assert len(names) == len(set(names)), "duplicate column"
    for column in table["columns"]:
        assert column["type"] in GLUE_TYPES, column["name"]
        assert 0 < len(column["comment"]) <= 255, column["name"]


@pytest.mark.parametrize("table", TABLES, ids=lambda t: t["name"])
def test_partition_key_is_a_column(table: dict) -> None:
    if key := table.get("partition_by"):
        assert key in {c["name"] for c in table["columns"]}
