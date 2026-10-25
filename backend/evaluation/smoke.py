"""Post-deploy smoke test: Athena must serve exactly the rows data/build.py produced.

uv run python -m evaluation.smoke [--manifest ../data/warehouse/manifest.json]
"""

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.warehouse.athena import AthenaWarehouse

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    expected = json.loads(args.manifest.read_text())["row_counts"]
    settings = Settings()
    warehouse = AthenaWarehouse(
        settings.aws_region, settings.athena_workgroup, settings.glue_database
    )

    counts_sql = " UNION ALL ".join(
        f"SELECT '{table}' AS table_name, count(*) AS row_count FROM {table}" for table in expected
    )
    result = warehouse.run(counts_sql, max_rows=len(expected))
    actual = {row["table_name"]: row["row_count"] for row in result.rows}

    mismatches = {t: (n, actual.get(t)) for t, n in expected.items() if actual.get(t) != n}
    for table, rows in expected.items():
        status = "ok" if table not in mismatches else f"MISMATCH (athena {actual.get(table)})"
        print(f"{table:28s} {rows:>12,}  {status}")
    print(f"scanned {result.bytes_scanned or 0:,} bytes in {result.execution_ms} ms")
    if mismatches:
        raise SystemExit(f"{len(mismatches)} table(s) don't match the build")


if __name__ == "__main__":
    main()
