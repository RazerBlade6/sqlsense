"""Download The Complete Journey and build the warehouse as Parquet, shaped by catalog/retail.yaml.

uv run python build.py            # download (if needed) and build into data/warehouse/
"""

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

import duckdb
import pyreadr
import yaml

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUT = ROOT / "warehouse"
CATALOG = ROOT.parent / "catalog" / "retail.yaml"

# completejourney R package (CC0), pinned for reproducibility.
SOURCE_COMMIT = "5b5d06192b9856edd04e4d405787af2f2e4a1fef"
SOURCE_URL = (
    f"https://raw.githubusercontent.com/bradleyboehmke/completejourney/{SOURCE_COMMIT}/data/{{}}"
)
SOURCE_FILES = {
    "campaign_descriptions.rda": "601bd17ea1a6de92cc288f393164813fbaf293b997d44054dcf1f3ebbe8dacee",
    "campaigns.rda": "33c7b3dc1bc722d465f97416fb1327c6a9a640190e464c73e354bce8c001a772",
    "coupon_redemptions.rda": "4b68148175ed19300bb2615d68d1a0300a5f971db3240819ab5d92e5919e1598",
    "coupons.rda": "4d87effce5b8813c0934b581a83292707347577743320ca746878de89cc16f34",
    "demographics.rda": "8b80455bc841003b64e47f5e5c2221f6093b995e923d59e72a1f852c7e268980",
    "products.rda": "a80c6df33623b4af296ae9f317a6647e369db7e8ce7e7baed0e1bf44b9d979e5",
    "promotions.rds": "15a729fdad31b10d3afedb058da31bcd6e9e68cb0207a43b3121264cd80198ba",
    "transactions.rds": "1fa0700033f1e5d9bb6b09e2be063d8d68474d346e95c50f2833e09d083e0007",
}

# Strict casts: a value that doesn't fit fails the build rather than becoming null.
# bigint goes through double because a few IDs were serialized in scientific notation.
CASTS = {
    "bigint": "CAST(CAST({col} AS DOUBLE) AS BIGINT)",
    "int": "CAST({col} AS INTEGER)",
    "double": "CAST({col} AS DOUBLE)",
    "string": "CAST({col} AS VARCHAR)",
    "date": "CAST({col} AS DATE)",
    "timestamp": "CAST({col} AS TIMESTAMP)",
    "boolean": "CAST({col} AS BOOLEAN)",
}

# Columns not present in the source, keyed by table.
DERIVED_COLUMNS = {
    "fact_transactions": {"transaction_date": "CAST(transaction_timestamp AS DATE)"},
}

DIM_DATE_SQL = """
SELECT
    CAST(d AS DATE) AS date_day,
    dayname(d) AS day_of_week,
    dayofweek(d) IN (0, 6) AS is_weekend,
    CAST(month(d) AS INTEGER) AS month,
    monthname(d) AS month_name,
    CAST(quarter(d) AS INTEGER) AS quarter,
    CAST(year(d) AS INTEGER) AS year
FROM range(DATE '2017-01-01', DATE '2018-01-02', INTERVAL 1 DAY) t(d)
ORDER BY 1
"""


def download() -> None:
    RAW.mkdir(exist_ok=True)
    for name, expected in SOURCE_FILES.items():
        path = RAW / name
        if not path.exists():
            print(f"downloading {name}")
            urllib.request.urlretrieve(SOURCE_URL.format(name), path)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"checksum mismatch for {name}: {actual}")


def load_sources(con: duckdb.DuckDBPyConnection) -> None:
    for name in SOURCE_FILES:
        frames = pyreadr.read_r(RAW / name)
        df = next(iter(frames.values()))
        con.register(f"src_{name.split('.')[0]}", df)


def table_sql(table: dict) -> str:
    if table["source"] == "derived":
        return DIM_DATE_SQL
    derived = DERIVED_COLUMNS.get(table["name"], {})
    exprs = []
    for column in table["columns"]:
        name = column["name"]
        source_expr = derived.get(name, name)
        exprs.append(f"{CASTS[column['type']].format(col=source_expr)} AS {name}")
    return f"SELECT {', '.join(exprs)} FROM src_{table['source']}"


def build() -> None:
    catalog = yaml.safe_load(CATALOG.read_text())
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / catalog["database"]).mkdir(parents=True)
    # Single-threaded so the Parquet bytes are identical on every build: the files are a CDK
    # asset, and a changed hash would republish the data and show up in every deploy plan.
    con = duckdb.connect(config={"threads": 1})
    load_sources(con)
    row_counts: dict[str, int] = {}

    for table in catalog["tables"]:
        name = table["name"]
        target = OUT / catalog["database"] / name
        con.execute(f"CREATE TABLE {name} AS {table_sql(table)}")
        partition = table.get("partition_by")
        if partition:
            con.execute(
                f"COPY {name} TO '{target}' (FORMAT parquet, PARTITION_BY ({partition}), COMPRESSION zstd)"
            )
        else:
            target.mkdir(parents=True)
            con.execute(
                f"COPY {name} TO '{target}/data.parquet' (FORMAT parquet, COMPRESSION zstd)"
            )
        rows = con.execute(f"SELECT count(*) FROM {name}").fetchall()[0][0]
        row_counts[name] = rows
        size_mb = sum(f.stat().st_size for f in target.rglob("*.parquet")) / 1e6
        print(f"{name:28s} {rows:>12,} rows  {size_mb:7.1f} MB")

    # Expected row counts, used by the post-deploy smoke test to check what Athena serves.
    manifest = {"source_commit": SOURCE_COMMIT, "row_counts": row_counts}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    download()
    build()
